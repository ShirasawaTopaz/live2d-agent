import asyncio
import logging
from typing import Any

from internal.agent.response import ToolCallParser
from internal.memory import Message
from internal.websocket.client import Client


class ChatService:
    """Coordinates chat execution, tool calls, and bubble rendering."""

    def __init__(self, agent: Any) -> None:
        self.agent = agent

    async def chat(self, message: Any, ws: Client) -> dict:
        if self.agent.memory is not None and not self.agent.memory._initialized:
            await self.agent.initialize_memory()

        tools = None
        if not self.agent.tool_registry.is_none:
            tools = self.agent.tool_registry.get_definitions()

        if self.agent.memory is not None and message is not None:
            await self._prepare_memory_and_history(message)

        need_stream = self._should_stream(message, tools)
        if need_stream:
            stream_result = await self._stream_chat(message, tools, ws)
            if stream_result[2]:
                return stream_result[0]
            response_message = stream_result[0]
            content_already_sent = stream_result[1]
        else:
            response_message = await self.agent.model.chat(message=message, tools=tools)
            logging.debug(f"Model response: {response_message}")
            content_already_sent = False

        response_message = await self._process_tool_calls(response_message, tools, ws)
        content, role = self._extract_content_and_role(response_message)

        await self._persist_assistant_message(role, content)

        if content and not content_already_sent:
            if not self.agent.bubble_timing.should_skip_content(content):
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

            for tool_call in tool_calls:
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
            return tool_call.get("function", {}).get("name", ""), tool_call.get("id", "")

        function_name = ""
        if hasattr(tool_call, "function") and hasattr(tool_call.function, "name"):
            function_name = tool_call.function.name
        tool_call_id = getattr(tool_call, "id", "") if hasattr(tool_call, "id") else ""
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
