import asyncio
import json
import logging
from time import monotonic
from dataclasses import dataclass
from typing import Any

from internal.agent.response import ToolCallParser
from internal.memory import Message
from internal.websocket.client import Client


@dataclass(frozen=True, slots=True)
class Live2DActionRule:
    priority: int
    confirmation_blocker: bool = False


@dataclass(frozen=True, slots=True)
class Live2DExpressionPlan:
    tool_calls: list[dict[str, Any]]
    consumes_assistant_content: bool
    has_confirmation_blocker: bool


class Live2DConflictController:
    """Keeps Live2D action ordering and bubble suppression deterministic."""

    ACTION_RULES: dict[str, Live2DActionRule] = {
        "trigger_motion": Live2DActionRule(priority=500, confirmation_blocker=True),
        "blink": Live2DActionRule(priority=400, confirmation_blocker=False),
        "set_expression": Live2DActionRule(priority=300, confirmation_blocker=True),
        "next_expression": Live2DActionRule(priority=300, confirmation_blocker=True),
        "clear_expression": Live2DActionRule(priority=200, confirmation_blocker=True),
        "display_bubble_text": Live2DActionRule(priority=100, confirmation_blocker=False),
    }
    ACTION_ORDER: dict[str, tuple[int, int]] = {
        "trigger_motion": (0, 0),
        "blink": (1, 0),
        "set_expression": (2, 0),
        "next_expression": (3, 0),
        "clear_expression": (4, 0),
        "display_bubble_text": (5, 0),
    }

    def __init__(self, expressions_config: Any | None = None) -> None:
        self._expressions_config = expressions_config
        self._last_confirmation_block_at: float = 0.0
        self._turn_has_blocker = False
        self._time_provider = monotonic

    def set_time_provider(self, time_provider) -> None:
        self._time_provider = time_provider

    @property
    def cooldown_seconds(self) -> float:
        cooldown_ms = getattr(self._expressions_config, "cooldown_ms", 1200)
        return max(0, int(cooldown_ms)) / 1000

    def order_key_for(self, tool_name: str) -> tuple[int, int]:
        return self.ACTION_ORDER.get(tool_name, (0, 0))

    def order_tool_calls(self, tool_calls: list[Any]) -> list[Any]:
        return sorted(
            enumerate(tool_calls),
            key=lambda item: (self.order_key_for(self._tool_name(item[1])), item[0]),
        )

    def begin_turn(self) -> None:
        self._turn_has_blocker = False

    def note_tool_execution(self, tool_name: str) -> None:
        rule = self.ACTION_RULES.get(tool_name)
        if rule is not None and rule.confirmation_blocker:
            self._turn_has_blocker = True
            self._last_confirmation_block_at = self._time_provider()

    def should_suppress_confirmation_bubble(self) -> bool:
        if self._turn_has_blocker:
            return True
        if self._last_confirmation_block_at == 0.0:
            return False
        return (self._time_provider() - self._last_confirmation_block_at) < self.cooldown_seconds

    def should_skip_bubble_tool(self, tool_name: str) -> bool:
        return tool_name == "display_bubble_text" and self.should_suppress_confirmation_bubble()

    @staticmethod
    def _tool_name(tool_call: Any) -> str:
        if isinstance(tool_call, dict):
            return tool_call.get("function", {}).get("name", "")

        if hasattr(tool_call, "function"):
            func = tool_call.function
            if isinstance(func, dict):
                return func.get("name", "")
            if hasattr(func, "name"):
                return func.name

        return getattr(tool_call, "name", "")


class Live2DExpressionScheduler:
    """Turns an emotion contract into deterministic Live2D tool calls."""

    def __init__(
        self,
        conflict_controller: Live2DConflictController,
        expressions_config: Any | None = None,
    ) -> None:
        self._conflict = conflict_controller
        self._expressions_config = expressions_config

    def set_expressions_config(self, expressions_config: Any | None) -> None:
        self._expressions_config = expressions_config

    def build_plan(
        self,
        contract: dict[str, Any],
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> Live2DExpressionPlan:
        tool_calls = tool_calls if tool_calls is not None else self.build_tool_calls(contract)
        has_confirmation_blocker = any(
            self._conflict.ACTION_RULES.get(self._tool_name(tool_call), Live2DActionRule(priority=0)).confirmation_blocker
            for tool_call in tool_calls
        )
        return Live2DExpressionPlan(
            tool_calls=tool_calls,
            consumes_assistant_content=True,
            has_confirmation_blocker=has_confirmation_blocker,
        )

    def extract_contract(self, response_message: Any) -> dict[str, Any] | None:
        payload: Any = None
        if isinstance(response_message, dict):
            if "main_emotion" in response_message or "stage_sequence" in response_message:
                payload = response_message
            else:
                payload = response_message.get("content")
        else:
            payload = getattr(response_message, "content", None)

        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                return None

        if not isinstance(payload, dict):
            return None

        if any(key in payload for key in ("main_emotion", "stage_sequence", "confidence", "reason")):
            return payload
        return None

    def build_tool_calls(self, contract: dict[str, Any]) -> list[dict[str, Any]]:
        stage_sequence = contract.get("stage_sequence", [])
        if not isinstance(stage_sequence, list) or not stage_sequence:
            return self._fallback_tool_calls(contract)

        generated: list[dict[str, Any]] = []
        seen_blocker = False
        for stage_index, stage in enumerate(stage_sequence):
            stage_calls = self._normalize_stage(stage, contract, stage_index)
            for tool_call in self._prioritize_stage_calls(stage_calls):
                function_name = self._tool_name(tool_call)
                if not function_name:
                    continue

                if function_name == "display_bubble_text" and seen_blocker:
                    continue

                rule = self._conflict.ACTION_RULES.get(function_name)
                if rule is not None and rule.confirmation_blocker:
                    seen_blocker = True

                generated.append(tool_call)

        if generated:
            return generated
        return self._fallback_tool_calls(contract)

    def _fallback_tool_calls(self, contract: dict[str, Any]) -> list[dict[str, Any]]:
        fallback_policy = getattr(self._expressions_config, "fallback_policy", "neutral")
        if fallback_policy == "no-op":
            return []

        if fallback_policy == "defaultExpression":
            default_expression = getattr(self._expressions_config, "default_expression", "")
            expression_id = contract.get("fallback_expression_id", 0)
            if not default_expression:
                return []
            return [self._make_tool_call("set_expression", {"expression_id": expression_id})]

        return [self._make_tool_call("clear_expression", {"id": contract.get("id", 0)})]

    def _normalize_stage(
        self,
        stage: Any,
        contract: dict[str, Any],
        stage_index: int,
    ) -> list[dict[str, Any]]:
        if isinstance(stage, str):
            return [self._string_stage_to_call(stage, contract, stage_index)]

        if not isinstance(stage, dict):
            return []

        if isinstance(stage.get("tool_calls"), list):
            nested_calls: list[dict[str, Any]] = []
            for nested_index, nested_stage in enumerate(stage["tool_calls"]):
                nested_calls.extend(self._normalize_stage(nested_stage, contract, nested_index))
            return nested_calls

        tool_name = stage.get("tool") or stage.get("action")
        if not isinstance(tool_name, str) or not tool_name:
            if stage.get("motion_name") or stage.get("motion"):
                tool_name = "trigger_motion"
            elif stage.get("text") or stage.get("bubble_text"):
                tool_name = "display_bubble_text"
            else:
                tool_name = "set_expression" if stage_index == 0 else "next_expression"

        arguments: dict[str, Any] = {}
        if isinstance(stage.get("arguments"), dict):
            arguments.update(stage["arguments"])

        if tool_name == "set_expression":
            arguments.setdefault("expression_id", stage.get("expression_id", stage_index))
        elif tool_name == "next_expression":
            arguments.setdefault("id", stage.get("id", contract.get("id", 0)))
        elif tool_name == "clear_expression":
            arguments.setdefault("id", stage.get("id", contract.get("id", 0)))
        elif tool_name == "trigger_motion":
            arguments.setdefault("motion_name", stage.get("motion_name", stage.get("motion", "")))
            arguments.setdefault("id", stage.get("id", contract.get("id", 0)))
        elif tool_name == "display_bubble_text":
            arguments.setdefault("text", stage.get("text", stage.get("bubble_text", "")))

        return [self._make_tool_call(tool_name, arguments)]

    def _string_stage_to_call(
        self,
        stage: str,
        contract: dict[str, Any],
        stage_index: int,
    ) -> dict[str, Any]:
        normalized = stage.strip()
        if normalized in {"neutral", "clear_expression", "clear"}:
            return self._make_tool_call("clear_expression", {"id": contract.get("id", 0)})
        if normalized == "trigger_motion":
            return self._make_tool_call(
                "trigger_motion",
                {
                    "id": contract.get("id", 0),
                    "motion_name": contract.get("motion_name", ""),
                },
            )
        if normalized == "display_bubble_text":
            return self._make_tool_call(
                "display_bubble_text",
                {"text": contract.get("bubble_text", "")},
            )
        if normalized == "next_expression":
            return self._make_tool_call("next_expression", {"id": contract.get("id", 0)})
        return self._make_tool_call(
            "set_expression",
            {"expression_id": contract.get("expression_id", stage_index)},
        )

    def _prioritize_stage_calls(self, tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ordered = sorted(
            enumerate(tool_calls),
            key=lambda item: (self._conflict.order_key_for(self._tool_name(item[1])), item[0]),
        )
        return [tool_call for _, tool_call in ordered]

    @staticmethod
    def _make_tool_call(function_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": ToolCallParser.generate_tool_call_id(),
            "type": "function",
            "function": {
                "name": function_name,
                "arguments": arguments,
            },
        }

    @staticmethod
    def _tool_name(tool_call: Any) -> str:
        if isinstance(tool_call, dict):
            return tool_call.get("function", {}).get("name", "")
        return ""


class ChatService:
    """Coordinates chat execution, tool calls, and bubble rendering."""

    def __init__(
        self,
        agent: Any,
        conflict_controller: Live2DConflictController | None = None,
        expression_scheduler: Live2DExpressionScheduler | None = None,
    ) -> None:
        self.agent = agent
        self.live2d_conflict = conflict_controller or Live2DConflictController()
        self.live2d_scheduler = expression_scheduler or Live2DExpressionScheduler(self.live2d_conflict)

    async def chat(self, message: Any, ws: Client) -> dict:
        if self.agent.memory is not None and not self.agent.memory._initialized:
            await self.agent.initialize_memory()

        tools = None
        if not self.agent.tool_registry.is_none:
            tools = self.agent.tool_registry.get_definitions()

        model_message = message
        if self.agent.memory is not None and message is not None:
            await self._prepare_memory_and_history(message)
            model_message = None

        self.live2d_conflict.set_time_provider(monotonic)
        self.live2d_conflict.begin_turn()
        need_stream = self._should_stream(message, tools)
        if need_stream:
            stream_result = await self._stream_chat(model_message, tools, ws)
            if stream_result[2]:
                return stream_result[0]
            response_message = stream_result[0]
            content_already_sent = stream_result[1]
        else:
            response_message = await self.agent.model.chat(message=model_message, tools=tools)
            logging.debug(f"Model response: {response_message}")
            content_already_sent = False

        scheduler = self.live2d_scheduler
        emotion_contract = scheduler.extract_contract(response_message)
        if emotion_contract is not None:
            scheduled_tool_calls = scheduler.build_tool_calls(emotion_contract)
            emotion_plan = scheduler.build_plan(emotion_contract, scheduled_tool_calls)
            response_message = {
                "role": "assistant",
                "content": "",
                "tool_calls": emotion_plan.tool_calls,
            }
            content_already_sent = content_already_sent or emotion_plan.consumes_assistant_content

        response_message = await self._process_tool_calls(response_message, tools, ws)
        content, role = self._extract_content_and_role(response_message)

        await self._persist_assistant_message(role, content)

        if content and not content_already_sent:
            if not self.agent.bubble_timing.should_skip_content(content) and not self.live2d_conflict.should_suppress_confirmation_bubble():
                await self.try_parse_and_send_bubble(content, ws)

        return response_message

    async def try_parse_and_send_bubble(self, content: str, ws: Client) -> None:
        if self.agent.bubble_timing.should_skip_content(content):
            return

        if "<tool_call>" in content:
            tool_calls = ToolCallParser.extract_tool_calls_from_text(content)
            if tool_calls:
                logging.info("Detected tool_call in content, executing fallback parsing")
                for tool_call in tool_calls:
                    await self.execute_tool_call_fallback(tool_call, ws)
                return

        logging.info(f"Sending full content as single bubble ({len(content)} chars)")
        await self.agent.bubble_timing.send_single_bubble(content, ws, self.agent.bubble_widget)

    async def execute_tool_call_fallback(self, tool_call: dict, ws: Client) -> None:
        function_name = tool_call.get("function", {}).get("name", "")

        if function_name not in self.agent.tool_registry.tools:
            logging.warning(f"Tool not found in fallback: {function_name}")
            error_text = f"错误：未找到工具 '{function_name}'"
            await self.agent.bubble_timing.display_text(
                error_text,
                ws,
                self.agent.bubble_widget,
                text_color=0xFF0000,
            )
            return

        try:
            arguments = ToolCallParser.parse_arguments(tool_call)
            arguments["ws"] = ws
            arguments["bubble_widget"] = self.agent.bubble_widget
            result = await self.agent.tool_registry.tools[function_name].execute(**arguments)

            logging.info(f"Fallback executed tool: {function_name}, result: {result}")

            if result:
                result_text = str(result)
                if self.agent.bubble_timing.should_skip_content(result_text):
                    return
                await self.agent.bubble_timing.display_text(
                    result_text,
                    ws,
                    self.agent.bubble_widget,
                )
        except Exception as e:
            logging.error(
                f"Error executing fallback tool {function_name}: {e}",
                exc_info=True,
            )
            error_text = f"执行工具 '{function_name}' 时出错：{str(e)}"
            await self.agent.bubble_timing.display_text(
                error_text,
                ws,
                self.agent.bubble_widget,
                text_color=0xFF0000,
            )

    async def _prepare_memory_and_history(self, message: Any) -> None:
        user_message: Message = {"role": "user", "content": str(message)}
        self.agent.memory.add_message(user_message)

        rag_context = ""
        if self.agent.rag is not None and self.agent.rag.is_enabled and message is not None:
            documents = self.agent.rag.retrieve(str(message))
            if documents:
                rag_context = self.agent.rag.format_retrieved_context(documents)
                logging.info(f"RAG retrieved {len(documents)} relevant documents")

        model_messages = await self.agent.memory.get_current_messages()
        if rag_context:
            self._inject_rag_context(model_messages, rag_context)
        self.agent.model.history = model_messages.copy()

    @staticmethod
    def _inject_rag_context(model_messages: list[dict[str, Any]], rag_context: str) -> None:
        for index, msg in enumerate(model_messages):
            if msg["role"] == "system":
                original_content = msg.get("content", "")
                model_messages[index]["content"] = f"{original_content}\n\n{rag_context}"
                return
        if model_messages:
            model_messages.insert(0, {"role": "system", "content": rag_context})

    def _should_stream(self, message: Any, tools: list[dict] | None) -> bool:
        return (
            message is not None
            and hasattr(self.agent.model.config, "streaming")
            and getattr(self.agent.model.config, "streaming", True)
            and (tools is None or self.agent.model._tools_supported is False)
        )

    async def _stream_chat(
        self,
        message: Any,
        tools: list[dict] | None,
        ws: Client,
    ) -> tuple[dict, bool, bool]:
        bubble_id = 0
        text_frame_color = 0x000000
        text_color = 0xFFFFFF
        final_content = ""
        final_response = None
        first_chunk = True
        has_content = False

        async for chunk in self.agent.model.stream_chat(message, tools):
            current_content = chunk["content"]
            final_content = current_content
            if chunk.get("done", False) and ToolCallParser.has_tool_calls(chunk):
                final_response = chunk
                break
            if not current_content:
                continue
            if self.agent.bubble_timing.should_skip_content(current_content):
                continue

            has_content = True
            if chunk.get("done", False):
                duration = self.agent.calculate_bubble_duration(final_content)
            else:
                duration = self.agent.calculate_bubble_duration(current_content)

            await self.agent.bubble_timing.send_stream_chunk(
                current_content,
                duration,
                ws,
                self.agent.bubble_widget,
                bubble_id=bubble_id,
                first_chunk=first_chunk,
                text_frame_color=text_frame_color,
                text_color=text_color,
            )
            first_chunk = False

        if has_content:
            self.agent.bubble_timing.finish_stream(final_content, self.agent.bubble_widget)

        if final_response is None:
            final_response = {"role": "assistant", "content": final_content}
            logging.info(f"Stream completed, final length: {len(final_content)}")
            return final_response, False, True

        return final_response, True, False

    async def _process_tool_calls(
        self,
        response_message: Any,
        tools: list[dict] | None,
        ws: Client,
    ) -> Any:
        for _ in range(self.agent.max_tool_calls):
            if not ToolCallParser.has_tool_calls(response_message):
                break

            tool_calls = ToolCallParser.parse_tool_calls(response_message)
            if not tool_calls:
                break

            for _, tool_call in self.live2d_conflict.order_tool_calls(tool_calls):
                success = await self._execute_tool_call(tool_call, ws)
                if not success:
                    return response_message

            response_message = await self.agent.model.chat(message=None, tools=tools)
            logging.debug(f"Model response after tool execution: {response_message}")

            if not ToolCallParser.has_tool_calls(response_message):
                content, _ = self._extract_content_and_role(response_message)
                if self.agent.bubble_timing.should_skip_content(content):
                    self._clear_response_content(response_message)
                    break

        return response_message

    async def _execute_tool_call(self, tool_call: Any, ws: Client) -> bool:
        function_name, tool_call_id = self._extract_tool_call_identity(tool_call)

        if self.live2d_conflict.should_skip_bubble_tool(function_name):
            logging.info("Skipping confirmation bubble after Live2D expression/motion change")
            return True

        if function_name not in self.agent.tool_registry.tools:
            logging.warning(f"Tool not found: {function_name}")
            self.agent.model.history.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": f"Error: Tool '{function_name}' not found",
                }
            )
            return True

        try:
            arguments = ToolCallParser.parse_arguments(tool_call)
            arguments["ws"] = ws
            arguments["bubble_widget"] = self.agent.bubble_widget
            result = await self.agent.tool_registry.tools[function_name].execute(**arguments)
            self.live2d_conflict.note_tool_execution(function_name)
            self.agent.model.history.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": str(result) if result is not None else "OK",
                }
            )
            logging.info(f"Executed tool: {function_name}")
            return True
        except Exception as e:
            logging.error(f"Error executing tool {function_name}: {e}", exc_info=True)
            self.agent.model.history.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": f"Error: {str(e)}",
                }
            )
            return False

    @staticmethod
    def _extract_tool_call_identity(tool_call: Any) -> tuple[str, str]:
        if isinstance(tool_call, dict):
            return tool_call.get("function", {}).get("name", ""), tool_call.get("id", ToolCallParser.generate_tool_call_id())

        function_name = ""
        tool_call_id = getattr(tool_call, "id", "") if hasattr(tool_call, "id") else ""

        if hasattr(tool_call, "function"):
            func = tool_call.function
            if hasattr(func, "name"):
                function_name = func.name
            elif isinstance(func, dict) and "name" in func:
                function_name = func["name"]

        # If still no function name, try direct access
        if not function_name and hasattr(tool_call, "name"):
            function_name = tool_call.name

        # Generate an ID if none exists
        if not tool_call_id:
            tool_call_id = ToolCallParser.generate_tool_call_id()

        return function_name, tool_call_id

    @staticmethod
    def _extract_content_and_role(response_message: Any) -> tuple[str, str]:
        if isinstance(response_message, dict):
            return response_message.get("content", ""), response_message.get("role", "assistant")

        content = getattr(response_message, "content", "") if hasattr(response_message, "content") else ""
        role = getattr(response_message, "role", "assistant") if hasattr(response_message, "role") else "assistant"
        return content, role

    @staticmethod
    def _clear_response_content(response_message: Any) -> None:
        if isinstance(response_message, dict):
            response_message["content"] = ""
            return
        if hasattr(response_message, "content"):
            try:
                setattr(response_message, "content", "")
            except AttributeError:
                pass

    async def _persist_assistant_message(self, role: str, content: str) -> None:
        if self.agent.memory is None:
            return

        assistant_message: Message = {"role": role, "content": content}
        self.agent.memory.add_message(assistant_message)

        if self.agent.memory.should_compress():
            if self.agent._compression_task is not None and not self.agent._compression_task.done():
                logging.debug("Previous compression task still running, skipping new compression")
            else:
                logging.info("Context threshold reached, starting background compression")
                self.agent._compression_task = asyncio.create_task(
                    self.agent._compress_context_in_background()
                )

        await self.agent.memory.save_current()
