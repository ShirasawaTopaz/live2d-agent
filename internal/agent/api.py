from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, fields, is_dataclass
from typing import Any, TypedDict, cast

import aiohttp


@dataclass(slots=True)
class MessageData:
    role: str
    content: str


@dataclass(slots=True)
class OpenAIAPILike:
    model: str
    messages: list[MessageData]
    temperature: float
    max_tokens: int
    stream: bool


class StreamChoiceDelta(TypedDict, total=False):
    content: str


class StreamChoice(TypedDict, total=False):
    finish_reason: str | None
    delta: StreamChoiceDelta
    text: str


class StreamChunk(TypedDict, total=False):
    choices: list[StreamChoice]


class NonStreamChoiceMessage(TypedDict, total=False):
    content: str


class NonStreamChoice(TypedDict, total=False):
    message: NonStreamChoiceMessage
    text: str


class NonStreamResponse(TypedDict, total=False):
    choices: list[NonStreamChoice]


OpenAIAPILikeRequest = OpenAIAPILike


@dataclass(slots=True)
class Agent:
    url: str = ""
    contextType: str = ""
    api_key: str = ""
    OpenAIAPILike: OpenAIAPILikeRequest | None = None
    # 兼容旧行为：非流式时直接输出原始 HTTP Body（通常是 JSON）。
    RawNonStreamResponse: bool = False

    async def send_request(self, chann: asyncio.Queue[int]) -> None:
        # 保持旧接口不变，默认使用后台 context。
        await self.send_request_with_context(chann)

    async def send_request_with_context(
        self,
        chann: asyncio.Queue[int],
        timeout_seconds: float | None = None,
    ) -> None:
        logger = logging.getLogger(__name__)

        if chann is None:
            raise ValueError("channel is nil")
        if self.OpenAIAPILike is None:
            raise ValueError("OpenAIAPILike is nil")
        if self.url == "":
            raise ValueError("url is empty")

        if timeout_seconds is None:
            timeout_seconds = defaultRequestTimeout
        deadline = time.monotonic() + timeout_seconds

        try:
            json_bytes = json.dumps(
                _to_jsonable(self.OpenAIAPILike),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as err:
            raise RuntimeError(f"marshal request body: {err}") from err

        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if self.api_key.strip() != "":
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.OpenAIAPILike.stream:
            headers["Accept"] = "text/event-stream"

        request_timeout = aiohttp.ClientTimeout(total=_remaining_seconds(deadline))

        try:
            async with aiohttp.ClientSession(timeout=request_timeout) as client:
                async with client.post(
                    self.url, data=json_bytes, headers=headers
                ) as resp:
                    if resp.status < 200 or resp.status >= 300:
                        body = await resp.content.read(8 * 1024)
                        error_text = body.decode("utf-8", errors="replace").strip()
                        if error_text == "":
                            raise RuntimeError(
                                f"request failed with status {resp.status}"
                            )
                        raise RuntimeError(
                            f"request failed with status {resp.status}: {error_text}"
                        )

                    # !stream
                    if not self.OpenAIAPILike.stream:
                        # 兼容旧版本：直接透传原始响应体，不做 JSON 解析。
                        if self.RawNonStreamResponse:
                            body = await resp.read()
                            if len(body) == 0:
                                return
                            await write_bytes(chann, body, deadline)
                            return

                        # 新行为：提取文本内容，统一为“只输出模型内容”。
                        try:
                            raw_non_stream: Any = json.loads(
                                (await resp.read()).decode("utf-8", errors="replace")
                            )
                        except json.JSONDecodeError as err:
                            raise RuntimeError(
                                f"decode non-stream response: {err}"
                            ) from err

                        non_stream_resp: NonStreamResponse
                        if isinstance(raw_non_stream, dict):
                            non_stream_resp = cast(NonStreamResponse, raw_non_stream)
                        else:
                            non_stream_resp = cast(NonStreamResponse, {})

                        choices = non_stream_resp.get("choices")
                        if not isinstance(choices, list):
                            choices = []

                        has_content = False
                        for choice in choices:
                            if not isinstance(choice, dict):
                                continue

                            content = ""
                            message = choice.get("message")
                            if isinstance(message, dict):
                                message_content = message.get("content")
                                if isinstance(message_content, str):
                                    content = message_content

                            if content == "":
                                text_content = choice.get("text")
                                if isinstance(text_content, str):
                                    content = text_content

                            if content == "":
                                continue

                            has_content = True
                            await write_bytes(chann, content.encode("utf-8"), deadline)

                        if len(choices) == 0:
                            raise ValueError("non-stream response has no choices")
                        if not has_content:
                            raise ValueError(
                                "non-stream response choices have empty content"
                            )
                        return

                    # stream
                    # 默认 Scanner token 太小（64KB），SSE 长行会被截断并报错。
                    while True:
                        line_bytes = await _readline_with_deadline(
                            resp.content, deadline
                        )
                        if line_bytes == b"":
                            break
                        if len(line_bytes) > maxSSELineSize:
                            raise RuntimeError("read stream response: line too long")

                        line = line_bytes.decode("utf-8", errors="replace").strip()
                        if line == "" or line.startswith(":"):
                            continue
                        if not line.startswith("data:"):
                            continue

                        payload = line.removeprefix("data:").strip()
                        if payload == "[DONE]":
                            break

                        try:
                            raw_chunk: Any = json.loads(payload)
                        except json.JSONDecodeError as err:
                            logger.error(f"failed to parse stream chunk: {err}")
                            continue

                        chunk: StreamChunk
                        if isinstance(raw_chunk, dict):
                            chunk = cast(StreamChunk, raw_chunk)
                        else:
                            chunk = cast(StreamChunk, {})

                        raw_choices = chunk.get("choices")
                        if not isinstance(raw_choices, list):
                            continue

                        for choice in raw_choices:
                            if not isinstance(choice, dict):
                                continue

                            content = ""
                            raw_delta = choice.get("delta")
                            if isinstance(raw_delta, dict):
                                delta_content = raw_delta.get("content")
                                if isinstance(delta_content, str):
                                    content = delta_content

                            if content == "":
                                text_content = choice.get("text")
                                if isinstance(text_content, str):
                                    content = text_content

                            if content != "":
                                await write_bytes(
                                    chann, content.encode("utf-8"), deadline
                                )

                            if choice.get("finish_reason") is not None:
                                break
        except asyncio.TimeoutError as err:
            raise TimeoutError("context deadline exceeded") from err
        except aiohttp.ClientError as err:
            raise RuntimeError(f"do request: {err}") from err


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _to_jsonable(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_to_jsonable(item) for item in value]
    return value


def _remaining_seconds(deadline: float | None) -> float | None:
    if deadline is None:
        return None

    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("context deadline exceeded")
    return remaining


async def _readline_with_deadline(
    stream: aiohttp.StreamReader,
    deadline: float | None,
) -> bytes:
    remaining = _remaining_seconds(deadline)
    if remaining is None:
        return await stream.readline()
    return await asyncio.wait_for(stream.readline(), timeout=remaining)


defaultRequestTimeout = 2 * 60
maxSSELineSize = 1024 * 1024


async def write_bytes(
    chann: asyncio.Queue[int],
    data: bytes,
    deadline: float | None,
) -> None:
    # 发送过程中监听 ctx，避免消费者阻塞导致无法退出。
    for b in data:
        remaining = _remaining_seconds(deadline)
        if remaining is None:
            await chann.put(b)
            continue
        await asyncio.wait_for(chann.put(b), timeout=remaining)
