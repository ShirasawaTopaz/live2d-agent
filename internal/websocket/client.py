from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, fields, is_dataclass
from typing import Any, Generic, TypeVar
from urllib.parse import urlsplit, urlunsplit

import aiohttp
from aiohttp import WSMsgType

LOGGER = logging.getLogger(__name__)

RegistrationModel = 10000
UnregisterModel = 10001
ReceiveModelEventNotification = 10002
DisplayBubbleText = 11000
SetBackground = 12010
SetPanoramicBackground = 12110
SetModel = 13000
RemoveModel = 13100
TriggerMotion = 13200
SetExpression = 13300
NextExpression = 13301
ClearExpression = 13302
SetModelPosition = 13400
SetModelPlaySound = 13500
StopModelSound = 13501
SetModelEffect = 14000
AddModelEffect = 14100
RemoveModelEffect = 14200


T = TypeVar("T")


class Client:
    # Conn is the long-lived websocket connection to Live2DViewerEX.
    def __init__(
        self,
        conn: aiohttp.ClientWebSocketResponse,
        session: aiohttp.ClientSession,
    ) -> None:
        self.conn = conn
        self._session = session

    async def close(self) -> None:
        # close() can be called many times safely.
        if self.conn is None:
            return

        await self.conn.close()
        self.conn = None

        if not self._session.closed:
            await self._session.close()

    async def send(self, message: bytes) -> None:
        if self.conn is None:
            raise RuntimeError("websocket connection is closed")
        if self.conn.closed or self.conn.close_code is not None:
            raise RuntimeError("websocket connection is closed")
        try:
            await self.conn.send_str(message.decode("utf-8"))
        except aiohttp.ClientConnectionResetError as e:
            # Connection is already closing, convert to clear error
            raise RuntimeError("websocket connection is closing") from e


def normalize_socket_url(raw: str) -> str:
    raw = raw.strip()
    if raw == "":
        raise ValueError("websocket url is empty")

    if "://" not in raw:
        raw = f"ws://{raw}"

    parts = urlsplit(raw)
    scheme = parts.scheme or "ws"
    path = parts.path
    if path in ("", "/"):
        path = "/api"

    return urlunsplit((scheme, parts.netloc, path, parts.query, parts.fragment))


async def new_client(raw_url: str) -> Client:
    socket_url = normalize_socket_url(raw_url)
    session = aiohttp.ClientSession()

    try:
        conn = await session.ws_connect(socket_url)
    except aiohttp.WSServerHandshakeError as err:
        await session.close()
        body = (err.message or "").strip()
        raise RuntimeError(
            f'dial websocket "{socket_url}" failed: {err} '
            f'(status={err.status} body="{body}")'
        ) from err
    except Exception:
        await session.close()
        raise

    return Client(conn=conn, session=session)


async def close_client(c: Client) -> None:
    await c.close()


@dataclass(slots=True)
class Live2dMessage(Generic[T]):
    msg: int
    msgId: int
    data: T


# Handle event 10002
@dataclass(slots=True)
class Live2dReceiveModelEventNotification:
    type: int
    id: int
    modelId: str
    hitArea: str


# Handle event 12000
@dataclass(slots=True)
class Live2dDisplayBubbleText:
    id: int
    text: str
    choices: list[str]
    textFrameColor: int
    textColor: int
    duration: int


# 12010 && 12110
@dataclass(slots=True)
class Live2dSetBackground:
    id: int
    file: str


# 13000
@dataclass(slots=True)
class Live2dSetModel:
    id: int
    file: str


# 13200
@dataclass(slots=True)
class Live2dTriggerAction:
    id: int
    type: int
    mtn: str


# 13300
@dataclass(slots=True)
class Live2dSetExpression:
    id: int
    expId: int


# 13400
@dataclass(slots=True)
class Live2dSetPosition:
    id: int
    posX: int
    posY: int


# 13500
@dataclass(slots=True)
class Live2dPlaySound:
    id: int
    channel: int
    volume: float
    delay: int
    loop: bool
    type: int
    sound: str


# 13501
@dataclass(slots=True)
class Live2dVoiceEnd:
    id: int
    channel: int


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _to_jsonable(getattr(value, field.name))
            for field in fields(value)
        }
    return value


def compose_message(msg: int, msg_id: int, data: object) -> bytes | None:
    packet = Live2dMessage(msg=msg, msgId=msg_id, data=data)
    try:
        return json.dumps(
            _to_jsonable(packet),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as err:
        LOGGER.error(str(err))
        return None


async def send_message(c: Client, msg: int, msg_id: int, data: object) -> None:
    """发送JSON到live2d"""
    message = compose_message(msg, msg_id, data)
    if message is None:
        raise ValueError("compose message failed")

    LOGGER.info(message.decode("utf-8", errors="replace"))
    try:
        await c.send(message)
    except (RuntimeError, aiohttp.ClientConnectionResetError) as e:
        # Connection is already closing/closed, log debug and ignore - this is expected during shutdown
        LOGGER.debug(f"Failed to send message during shutdown: {e}")


async def receive_message(
    c: Client, channel: asyncio.Queue[Live2dMessage[Any]]
) -> None:
    while True:
        if c.conn is None:
            raise RuntimeError("websocket connection is closed")

        ws_msg = await c.conn.receive()

        if ws_msg.type == WSMsgType.TEXT:
            raw = ws_msg.data
        elif ws_msg.type == WSMsgType.BINARY:
            raw = ws_msg.data.decode("utf-8")
        elif ws_msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
            raise ConnectionError("websocket connection closed")
        elif ws_msg.type == WSMsgType.ERROR:
            err = c.conn.exception()
            if err is None:
                raise ConnectionError("websocket receive error")
            raise err
        else:
            continue

        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as err:
            raise ValueError(f"decode websocket message failed: {err}") from err

        message = Live2dMessage(
            msg=int(decoded["msg"]),
            msgId=int(decoded["msgId"]),
            data=decoded.get("data"),
        )
        await channel.put(message)
