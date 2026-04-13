import json
import logging
import time
import asyncio
from typing import Any, Optional

from internal.agent.agent_support.ollama import OllamaModel
from internal.agent.agent_support.trait import ModelTrait
from internal.agent.agent_support.transformers import Transformers
from internal.agent.agent_support.online import OnlineModel
from internal.agent.register import ToolRegistry
from internal.agent.response import ToolCallParser
from internal.agent.tool.base import Tool
from internal.agent.tool.file import FileTool
from internal.agent.tool.office import OfficeTool
from internal.agent.tool.web_search import WebSearchTool
from internal.agent.tool.live2d.display_bubble_text import DisplayBubbleTextTool
from internal.agent.tool.live2d.trigger_motion import TriggerMotionTool
from internal.agent.tool.live2d.set_expression import SetExpressionTool
from internal.agent.tool.live2d.next_expression import NextExpressionTool
from internal.agent.tool.live2d.clear_expression import ClearExpressionTool
from internal.agent.tool.live2d.set_background import SetBackgroundTool
from internal.agent.tool.live2d.set_model import SetModelTool
from internal.agent.tool.live2d.play_sound import PlaySoundTool
from internal.agent.tool.dynamic.storage import DynamicToolStorage
from internal.agent.tool.meta.generate_tool import GenerateToolTool
from internal.agent.tool.meta.list_tools import ListToolsTool
from internal.agent.tool.meta.delete_tool import DeleteToolTool
from internal.agent.tool.meta.rollback_tool import RollbackTool
from internal.agent.sandbox import SandboxMiddleware, SandboxConfig, default_sandbox
from internal.agent.planning.planner import Planner, PlannerConfig
from internal.agent.planning.storage.json import JSONPlanStorage
from internal.agent.planning.storage.sqlite import SQLitePlanStorage
from internal.agent.planning.base import Plan
from internal.agent.planning.types import PlanStatus
from internal.config.config import AIModelConfig, AIModelType, PlanningConfig
from internal.memory import MemoryManager, MemoryConfig, Message
from internal.ui.bubble_widget import BubbleWidget
from internal.websocket.client import (
    Client,
    DisplayBubbleText,
    Live2dDisplayBubbleText,
    send_message,
)

__all__ = ["Agent", "create_agent"]


class Agent:
    """AI Agent主类，处理聊天和工具调用"""

    model: ModelTrait
    tool_registry: ToolRegistry
    memory: MemoryManager | None = None
    bubble_widget: "BubbleWidget" | None = None  # Qt 原生悬浮气泡窗口
    sandbox: SandboxMiddleware  # Sandbox security middleware
    dynamic_tool_storage: DynamicToolStorage  # Dynamic tool persistent storage
    planner: Optional[Planner] = None  # Task planning orchestrator

    # 气泡显示时间管理
    _last_bubble_time: float = 0.0  # 最后一次气泡显示开始时间
    _last_bubble_duration: float = 0.0  # 最后一次气泡显示时长（秒）

    # 后台上下文压缩任务
    _compression_task: asyncio.Task | None = None

    def __init__(
        self,
        model: ModelTrait,
        memory_config: MemoryConfig | None = None,
        sandbox_config: SandboxConfig | None = None,
        planning_config: PlanningConfig | None = None,
    ) -> None:
        self.model = model
        self.tool_registry = ToolRegistry()
        if sandbox_config:
            self.sandbox = SandboxMiddleware(sandbox_config)
        else:
            self.sandbox = default_sandbox

        # Initialize dynamic tool storage before registering default tools
        # because meta-tools need storage to be available
        self.dynamic_tool_storage = DynamicToolStorage()
        self._register_default_tools()

        # Load all persisted dynamic tools from previous sessions
        loaded_count = self.tool_registry.load_all_dynamic_tools(self.dynamic_tool_storage)
        if loaded_count > 0:
            logging.info(f"Loaded {loaded_count} dynamic tool(s) from storage")

        self.max_tool_calls = 5
        if memory_config and memory_config.enabled:
            self.memory = MemoryManager(memory_config)
        else:
            self.memory = None

        # Initialize planner if planning is enabled
        if planning_config and planning_config.enabled:
            # Create storage based on configured type
            if planning_config.storage_type == "json":
                storage = JSONPlanStorage(planning_config.storage_path)
            elif planning_config.storage_type == "sqlite":
                storage = SQLitePlanStorage(planning_config.storage_path)
            else:
                logging.warning(f"Unknown storage type '{planning_config.storage_type}', using JSON")
                storage = JSONPlanStorage(planning_config.storage_path)

            # Create planner config
            planner_config = PlannerConfig(
                max_concurrency=planning_config.max_concurrency,
                max_plan_depth=getattr(planning_config, 'max_plan_depth', 10),
                auto_save=getattr(planning_config, 'auto_save', True)
            )

            # Create planner with this agent instance
            self.planner = Planner(
                storage=storage,
                config=planner_config,
                agent=self
            )
        else:
            self.planner = None

    @staticmethod
    def calculate_bubble_duration(text: str) -> int:
        """
        根据文本长度计算气泡显示时长

        计算公式:
        - 基础时间: 3000ms (3秒)
        - 每10个字符增加1000ms
        - 最长不超过30000ms (30秒)
        - 最少不低于5000ms (5秒)
        """
        if not text:
            return 5000

        # 计算文本长度（中文字符算2个字符，英文算1个）
        char_count = 0
        for char in text:
            if "\u4e00" <= char <= "\u9fff":  # 中文字符
                char_count += 2
            else:
                char_count += 1

        # 基础3秒，每10个字符加1秒
        base_duration = 3000
        additional_duration = (char_count // 10) * 1000
        total_duration = base_duration + additional_duration

        # 限制在5秒到30秒之间
        min_duration = 5000
        max_duration = 30000
        total_duration = max(min_duration, min(total_duration, max_duration))

        return total_duration

    def _wait_for_bubble_interval(self, current_duration: int) -> float:
        """
        计算需要等待的时间以确保上一个气泡完全显示后再显示新气泡

        参数:
            current_duration: 当前气泡的显示时长（毫秒）

        返回需要等待的秒数（如果不需要等待返回0）
        """
        current_time = time.time()
        last_bubble_end_time = self._last_bubble_time + (
            self._last_bubble_duration / 1000
        )

        if current_time < last_bubble_end_time:
            # 需要等待到上一个气泡结束
            return last_bubble_end_time - current_time

        return 0.0

    def _update_bubble_time(self, duration: int) -> None:
        """更新最后一次气泡显示信息"""
        self._last_bubble_time = time.time()
        self._last_bubble_duration = duration

    def _register_default_tools(self) -> None:
        """注册默认工具"""
        self.tool_registry.register(DisplayBubbleTextTool())
        self.tool_registry.register(FileTool(self.sandbox))
        self.tool_registry.register(OfficeTool(self.sandbox))
        self.tool_registry.register(WebSearchTool(self.sandbox))
        self.tool_registry.register(TriggerMotionTool())
        self.tool_registry.register(SetExpressionTool())
        self.tool_registry.register(NextExpressionTool())
        self.tool_registry.register(ClearExpressionTool())
        self.tool_registry.register(SetBackgroundTool())
        self.tool_registry.register(SetModelTool())
        self.tool_registry.register(PlaySoundTool())
        # Meta-tools for dynamic tool management
        self.tool_registry.register(GenerateToolTool(self.tool_registry, self.dynamic_tool_storage))
        self.tool_registry.register(ListToolsTool(self.tool_registry, self.dynamic_tool_storage))
        self.tool_registry.register(DeleteToolTool(self.tool_registry, self.dynamic_tool_storage))
        self.tool_registry.register(RollbackTool(self.tool_registry, self.dynamic_tool_storage))

    def register_tool(self, tool: Tool) -> None:
        """注册自定义工具"""
        self.tool_registry.register(tool)

    async def initialize_memory(self) -> None:
        """初始化记忆系统，如果启用了的话"""
        if self.memory is not None and not self.memory._initialized:
            await self.memory.init()
            # 启动时自动压缩符合条件的长期会话
            if hasattr(self.memory, "compress_all_eligible") and getattr(
                self.memory.config, "compress_on_startup", True
            ):
                asyncio.create_task(self._auto_compress_inactive())

    async def _auto_compress_inactive(self) -> None:
        """后台自动压缩不活跃的长期会话"""
        if self.memory is None:
            return
        try:
            compressed = await self.memory.compress_all_eligible()
            if compressed > 0:
                logging.info(
                    f"Auto-compressed {compressed} inactive sessions on startup"
                )
        except Exception as e:
            logging.error(f"Error during auto-compression: {e}", exc_info=True)

    async def chat(self, message: Any, ws: Client) -> dict:
        """处理聊天消息，支持多轮工具调用和流式响应
        如果模型启用了流式响应且最终响应没有工具调用，则使用流式实时发送
        否则使用传统完整响应模式
        """
        # 确保内存已初始化
        if self.memory is not None and not self.memory._initialized:
            await self.initialize_memory()

        tools = None
        if not self.tool_registry.is_none:
            tools = self.tool_registry.get_definitions()

        # 获取消息列表从记忆系统
        if self.memory is not None and message is not None:
            # 添加用户消息到记忆
            user_message: Message = {"role": "user", "content": str(message)}
            self.memory.add_message(user_message)
            # 获取所有消息给模型
            model_messages = await self.memory.get_current_messages()
            # 更新模型历史以匹配记忆
            self.model.history = model_messages.copy()
        else:
            model_messages = None

        # 检查是否需要启用流式响应
        # 条件: 1. message 不为 None（新消息，不是工具调用后的继续） 2. 配置启用了流式
        # 3. 没有定义任何工具，或者已经确认模型不支持工具调用
        # 如果有工具定义，必须走非流式分支，因为工具需要多轮调用
        need_stream = (
            message is not None
            and hasattr(self.model.config, "streaming")
            and getattr(self.model.config, "streaming", True)
            and (tools is None or self.model._tools_supported is False)
        )

        # 如果需要流式响应且不需要工具调用，直接使用流式输出（只发起一次 API 调用）
        content_already_sent = False
        if need_stream:
            # 启用流式响应，从模型流式获取内容并实时发送到Live2D
            # 使用固定bubble_id=0进行覆盖更新（依赖前端覆盖实现）
            bubble_id = 0
            text_frame_color = 0x000000
            text_color = 0xFFFFFF

            final_content = ""
            final_response = None

            # 从流式生成器逐块获取内容并发送
            first_chunk = True
            has_content = False
            async for chunk in self.model.stream_chat(message, tools):
                current_content = chunk["content"]
                final_content = current_content
                if chunk.get("done", False):
                    # 如果流式内部处理了工具调用（当工具支持但流式开始后发现需要工具调用）
                    # 从最终块获取完整响应
                    if ToolCallParser.has_tool_calls(chunk):
                        final_response = chunk
                        break
                if current_content:
                    # Skip displaying if this is a system completion message or debug logs
                    if self._should_skip_content(current_content):
                        # Still keep content in final_content for history, just don't display
                        continue

                    has_content = True
                    # 使用最终内容计算完整的显示时间（为了准确计时）
                    if chunk.get("done", False):
                        duration = self.calculate_bubble_duration(final_content)
                    else:
                        duration = self.calculate_bubble_duration(current_content)

                    # 如果有 Qt 气泡组件，使用它显示
                    if self.bubble_widget is not None:
                        if first_chunk:
                            # Qt气泡可以直接替换内容，不需要等待上一个气泡消失
                            self.bubble_widget.clear()
                            self.bubble_widget.show()
                            first_chunk = False
                        # 对于流式，我们只追加新内容，current_content 已经是累积的
                        # 所以直接设置完整内容而不是追加
                        self.bubble_widget.set_text(current_content)
                    else:
                        # 使用相同的bubble_id发送，Live2D会覆盖更新内容
                        bubble_data = Live2dDisplayBubbleText(
                            id=bubble_id,
                            text=current_content,
                            choices=[],
                            textFrameColor=text_frame_color,
                            textColor=text_color,
                            duration=duration,
                        )
                        # 只有第一个chunk需要检查气泡时间间隔
                        if first_chunk:
                            wait_time = self._wait_for_bubble_interval(duration)
                            if wait_time > 0:
                                await asyncio.sleep(wait_time)
                            first_chunk = False
                        # 发送气泡
                        await send_message(
                            ws, DisplayBubbleText, DisplayBubbleText, bubble_data
                        )
                        logging.debug(f"Stream chunk sent: {current_content[:50]}...")

            # 流式响应完成后，更新气泡显示时间
            # 这样可以确保整个流式响应算一次完整的气泡显示
            if has_content:
                final_duration = self.calculate_bubble_duration(final_content)
                self._update_bubble_time(final_duration)
                # 如果使用 Qt 气泡，流式完成后启动自动消失定时器
                if self.bubble_widget is not None:
                    self.bubble_widget.show_with_duration(final_duration)

            if final_response is None:
                # 纯文本流式响应完成，构造返回字典
                final_response = {"role": "assistant", "content": final_content}
                logging.info(f"Stream completed, final length: {len(final_content)}")
                return final_response

            # 如果流式过程中发现需要工具调用，继续走工具调用流程（此时 message 已经被添加到历史）
            # 此时 content 已经在流式中发送过了，最后不要重复发送
            response_message = final_response
            content_already_sent = True
        else:
            # 非流式模式：先获取完整响应
            response_message = await self.model.chat(message=message, tools=tools)
            logging.debug(f"Model response: {response_message}")

        # 处理工具调用循环（仅在非流式或流式发现需要工具调用时执行）
        for _ in range(self.max_tool_calls):
            if not ToolCallParser.has_tool_calls(response_message):
                break

            tool_calls = ToolCallParser.parse_tool_calls(response_message)
            if not tool_calls:
                break

            for tool_call in tool_calls:
                # Get from either dict or object
                if isinstance(tool_call, dict):
                    function_name = tool_call.get("function", {}).get("name", "")
                    tool_call_id = tool_call.get("id", "")
                else:
                    if hasattr(tool_call, "function") and hasattr(
                        tool_call.function, "name"
                    ):
                        function_name = tool_call.function.name
                    else:
                        function_name = ""
                    tool_call_id = (
                        getattr(tool_call, "id", "") if hasattr(tool_call, "id") else ""
                    )

                if function_name not in self.tool_registry.tools:
                    logging.warning(f"Tool not found: {function_name}")
                    self.model.history.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": f"Error: Tool '{function_name}' not found",
                        }
                    )
                    continue

                try:
                    arguments = ToolCallParser.parse_arguments(tool_call)
                    arguments["ws"] = ws
                    # 如果有 Qt 气泡组件，传递给工具使用
                    arguments["bubble_widget"] = self.bubble_widget
                    result = await self.tool_registry.tools[function_name].execute(
                        **arguments
                    )

                    self.model.history.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": str(result) if result is not None else "OK",
                        }
                    )

                    logging.info(f"Executed tool: {function_name}")
                except Exception as e:
                    logging.error(
                        f"Error executing tool {function_name}: {e}",
                        exc_info=True,
                    )
                    self.model.history.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": f"Error: {str(e)}",
                        }
                    )
                    return response_message

            response_message = await self.model.chat(message=None, tools=tools)
            logging.debug(f"Model response after tool execution: {response_message}")

            # If response doesn't have tool calls and contains only system completion markers,
            # we can skip processing it entirely to avoid adding useless tokens to history
            if not ToolCallParser.has_tool_calls(response_message):
                # Extract content to check if it should be skipped
                if isinstance(response_message, dict):
                    content = response_message.get("content", "")
                else:
                    content = (
                        getattr(response_message, "content", "")
                        if hasattr(response_message, "content")
                        else ""
                        )
                if self._should_skip_content(content):
                    # No need to keep this response - it's just useless completion tokens
                    # The loop will exit anyway since there are no tool calls for the next iteration
                    # Clear the response content to ensure nothing gets added to history
                    if isinstance(response_message, dict):
                        response_message["content"] = ""
                    else:
                        if hasattr(response_message, "content"):
                            try:
                                setattr(response_message, "content", "")
                            except AttributeError:
                                pass
                    break

        # Get content from either dict or object
        if isinstance(response_message, dict):
            content = response_message.get("content", "")
            role = response_message.get("role", "assistant")
        else:
            content = (
                getattr(response_message, "content", "")
                if hasattr(response_message, "content")
                else ""
            )
            role = (
                getattr(response_message, "role", "assistant")
                if hasattr(response_message, "role")
                else "assistant"
            )

        # 保存助手响应到记忆系统
        if self.memory is not None:
            assistant_message: Message = {"role": role, "content": content}
            self.memory.add_message(assistant_message)

            # 检查是否需要压缩上下文（在后台执行，不阻塞用户响应）
            if self.memory.should_compress():
                # 如果已有后台压缩任务在运行，先等待它完成
                if (
                    self._compression_task is not None
                    and not self._compression_task.done()
                ):
                    logging.debug(
                        "Previous compression task still running, skipping new compression"
                    )
                else:
                    logging.info(
                        "Context threshold reached, starting background compression"
                    )
                    # 启动后台压缩任务，不阻塞当前响应
                    self._compression_task = asyncio.create_task(
                        self._compress_context_in_background()
                    )

            # 保存当前会话到存储（快速操作，不需要后台化）
            await self.memory.save_current()

        # 非流式模式下，有内容则发送完整响应
        # 跳过完成标记和系统消息，不需要显示
        if content and not content_already_sent:
            if not self._should_skip_content(content):
                await self._try_parse_and_send_bubble(content, ws)

        return response_message

    def _extract_tool_calls(self, response_text: str) -> list[dict] | None:
        """从响应文本中提取工具调用"""
        import re

        tool_calls = []

        pattern = r"<tool_call>(\{.*\})</tool_call>"
        matches = re.findall(pattern, response_text, re.DOTALL)

        if not matches:
            pattern = r"<tool_call>(\{.*\})>"
            matches = re.findall(pattern, response_text, re.DOTALL)

        if not matches:
            pattern = r"<tool_call>(\{.*)"
            matches = re.findall(pattern, response_text, re.DOTALL)

        for match in matches:
            json_str = self._extract_valid_json(match)
            if not json_str:
                continue

            try:
                tool_data = json.loads(json_str)
                tool_call = {
                    "id": ToolCallParser.generate_tool_call_id(),
                    "type": "function",
                    "function": {
                        "name": tool_data.get("name", ""),
                        "arguments": tool_data.get("arguments", {}),
                    },
                }
                tool_calls.append(tool_call)
            except json.JSONDecodeError:
                continue

        return tool_calls if tool_calls else None

    def _extract_valid_json(self, text: str) -> str | None:
        """从文本中提取有效的JSON字符串，处理嵌套的大括号"""
        text = text.strip()
        if not text.startswith("{"):
            return None

        depth = 0
        end_pos = -1

        for i, char in enumerate(text):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end_pos = i
                    break

        if end_pos >= 0:
            return text[: end_pos + 1]
        return None

    def _split_text_into_chunks(self, text: str, max_chunk_size: int = 20) -> list[str]:
        """将长文本分割成多个小块，每块不超过指定字数

        按照语义进行分割，优先在标点符号处切割，确保每块不超过max_chunk_size。
        """
        if not text or not text.strip():
            return []

        text = text.strip()
        if len(text) <= max_chunk_size:
            return [text]

        chunks = []
        current_chunk = ""

        # 按字符遍历
        for char in text:
            # 如果当前块加上新字符超过限制
            if len(current_chunk) + 1 > max_chunk_size:
                # 保存当前块
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                # 开始新块，优先保留标点在新块开头
                if char in '，。！？；：""（）【】':
                    current_chunk = ""
                else:
                    current_chunk = char
            else:
                current_chunk += char

        # 添加最后一块（关键修复：确保最后一块被添加）
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        # 额外检查：如果chunks为空但original_text不为空，返回原文
        if not chunks and text.strip():
            chunks = [text]

        return chunks

    def _should_skip_content(self, content: str) -> bool:
        """检查是否应该跳过显示该内容（系统完成标记等）"""
        content_stripped = content.strip()
        # 跳过 {"status":"done"} 类型的完成标记
        if content_stripped == '{"status":"done"}' or content_stripped == '{"status": "done"}':
            return True
        # 跳过中文系统完成标记
        if "不需要额外回复" in content_stripped or "对话已经完成" in content_stripped:
            return True
        # 跳过纯日志输出（如果日志意外混入内容）
        if " - DEBUG - " in content_stripped or " - INFO - " in content_stripped:
            return True
        return False

    async def _send_multi_bubbles(self, chunks: list[str], ws: Client) -> None:
        """顺序发送多个气泡文本，每个气泡之间有适当延迟"""
        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            if self._should_skip_content(chunk):
                continue

            duration = self.calculate_bubble_duration(chunk)

            # 使用Qt气泡组件
            if self.bubble_widget is not None:
                self.bubble_widget.clear()
                self.bubble_widget.set_text(chunk)
                self.bubble_widget.show_with_duration(duration)
                self._update_bubble_time(duration)
                logging.info(f"Qt bubble [{i + 1}/{len(chunks)}]: {chunk[:30]}...")
            else:
                # WebSocket发送
                bubble_data = Live2dDisplayBubbleText(
                    id=i,
                    text=chunk,
                    choices=[],
                    textFrameColor=0x000000,
                    textColor=0xFFFFFF,
                    duration=duration,
                )
                # 检查气泡时间间隔
                wait_time = self._wait_for_bubble_interval(duration)
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                await send_message(
                    ws, DisplayBubbleText, DisplayBubbleText, bubble_data
                )
                self._update_bubble_time(duration)
                logging.info(f"Bubble [{i + 1}/{len(chunks)}]: {chunk[:30]}...")

            # 气泡之间添加短暂延迟，让用户有时间阅读
            if i < len(chunks) - 1:
                # 根据当前气泡内容长度计算阅读时间（至少1秒）
                read_time = max(1.0, len(chunk) * 0.15)
                await asyncio.sleep(read_time)

    async def _try_parse_and_send_bubble(self, content: str, ws: Client) -> None:
        """尝试解析JSON内容并发送气泡文本，否则发送纯文本气泡"""
        # 检查是否应该跳过显示该内容
        if self._should_skip_content(content):
            return
        # 优先检查是否包含 tool_call 格式，这是 fallback 机制
        # 当模型没有正确使用 tool_calls 字段时，会将工具调用放在 content 中
        if "<tool_call>" in content:
            # 尝试提取并解析 tool_call
            tool_calls = self._extract_tool_calls(content)
            if tool_calls:
                logging.info(
                    "Detected tool_call in content, executing fallback parsing"
                )
                for tool_call in tool_calls:
                    await self._execute_tool_call_fallback(tool_call, ws)
                return

        # 直接发送完整内容作为单个气泡
        logging.info(f"Sending full content as single bubble ({len(content)} chars)")
        await self._send_single_bubble(content, ws)

    async def _send_single_bubble(self, content: str, ws: Client) -> None:
        """发送单个气泡（原始逻辑提取）"""
        # 如果有 Qt 气泡组件，直接使用它显示（非流式场景）
        if self.bubble_widget is not None:
            # Qt气泡可以直接替换内容，不需要等待上一个气泡消失
            self.bubble_widget.clear()
            self.bubble_widget.set_text(content)
            duration = self.calculate_bubble_duration(content)
            self.bubble_widget.show_with_duration(duration)
            self._update_bubble_time(duration)
            logging.info(f"Qt bubble displayed: {content[:50]}...")
            return

        # WebSocket 发送气泡（原有逻辑）
        try:
            parsed = json.loads(content.strip())
            if isinstance(parsed, dict):
                data = parsed.get("data", parsed)
                duration = data.get("duration")
                if duration is None:
                    duration = self.calculate_bubble_duration(data.get("text", content))
                bubble_data = Live2dDisplayBubbleText(
                    id=data.get("id", 0),
                    text=data.get("text", content),
                    choices=data.get("choices", []),
                    textFrameColor=data.get("textFrameColor", 0x000000),
                    textColor=data.get("textColor", 0xFFFFFF),
                    duration=duration,
                )
                wait_time = self._wait_for_bubble_interval(duration)
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                await send_message(
                    ws, DisplayBubbleText, DisplayBubbleText, bubble_data
                )
                self._update_bubble_time(duration)
                logging.info(f"Parsed JSON bubble: {bubble_data}")
        except json.JSONDecodeError:
            duration = self.calculate_bubble_duration(content)
            bubble_data = Live2dDisplayBubbleText(
                id=0,
                text=content,
                choices=[],
                textFrameColor=0x000000,
                textColor=0xFFFFFF,
                duration=duration,
            )
            wait_time = self._wait_for_bubble_interval(duration)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            await send_message(ws, DisplayBubbleText, DisplayBubbleText, bubble_data)
            self._update_bubble_time(duration)
            logging.info(f"Sent plain text bubble: {content[:50]}...")

        try:
            parsed = json.loads(content.strip())
            if isinstance(parsed, dict):
                data = parsed.get("data", parsed)
                # 如果没有指定duration，使用智能计算的显示时间
                duration = data.get("duration")
                if duration is None:
                    duration = self.calculate_bubble_duration(data.get("text", content))
                bubble_data = Live2dDisplayBubbleText(
                    id=data.get("id", 0),
                    text=data.get("text", content),
                    choices=data.get("choices", []),
                    textFrameColor=data.get("textFrameColor", 0x000000),
                    textColor=data.get("textColor", 0xFFFFFF),
                    duration=duration,
                )
                # 检查气泡时间间隔
                wait_time = self._wait_for_bubble_interval(duration)
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                await send_message(
                    ws, DisplayBubbleText, DisplayBubbleText, bubble_data
                )
                # 更新最后一次气泡显示时间
                self._update_bubble_time(duration)
                logging.info(f"Parsed JSON bubble: {bubble_data}")
        except json.JSONDecodeError:
            # 使用智能计算的显示时间
            duration = self.calculate_bubble_duration(content)
            bubble_data = Live2dDisplayBubbleText(
                id=0,
                text=content,
                choices=[],
                textFrameColor=0x000000,
                textColor=0xFFFFFF,
                duration=duration,
            )
            # 检查气泡时间间隔
            wait_time = self._wait_for_bubble_interval(duration)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            await send_message(ws, DisplayBubbleText, DisplayBubbleText, bubble_data)
            # 更新最后一次气泡显示时间
            self._update_bubble_time(duration)
            logging.info(f"Sent plain text bubble: {content[:50]}...")

    async def _execute_tool_call_fallback(self, tool_call: dict, ws: Client) -> None:
        """Fallback 方式执行工具调用（从 content 中解析出的 tool_call）"""
        function_name = tool_call.get("function", {}).get("name", "")
        _tool_call_id = tool_call.get("id", "")

        if function_name not in self.tool_registry.tools:
            logging.warning(f"Tool not found in fallback: {function_name}")
            # 如果工具不存在，发送错误消息作为气泡文本
            error_text = f"错误：未找到工具 '{function_name}'"
            duration = self.calculate_bubble_duration(error_text)
            # 如果有 Qt 气泡组件，使用它显示错误
            if self.bubble_widget is not None:
                # 新气泡直接替换旧气泡，不需要等待旧气泡显示完
                # clear 已经停止之前的定时器和动画
                self.bubble_widget.clear()
                self.bubble_widget.set_text(error_text)
                self.bubble_widget.show_with_duration(duration)
                # 更新最后一次气泡显示时间（从当前开始）
                self._update_bubble_time(duration)
                logging.info(f"Qt bubble displayed for tool not found: {error_text}")
            else:
                bubble_data = Live2dDisplayBubbleText(
                    id=0,
                    text=error_text,
                    choices=[],
                    textFrameColor=0x000000,
                    textColor=0xFF0000,
                    duration=duration,
                )
                # 检查气泡时间间隔
                wait_time = self._wait_for_bubble_interval(duration)
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                await send_message(
                    ws, DisplayBubbleText, DisplayBubbleText, bubble_data
                )
                # 更新最后一次气泡显示时间
                self._update_bubble_time(duration)
            return

        try:
            arguments = ToolCallParser.parse_arguments(tool_call)
            arguments["ws"] = ws
            # 如果有 Qt 气泡组件，传递给工具使用
            arguments["bubble_widget"] = self.bubble_widget
            result = await self.tool_registry.tools[function_name].execute(**arguments)

            logging.info(f"Fallback executed tool: {function_name}, result: {result}")

            # 如果有返回结果，发送气泡文本显示结果
            if result:
                result_text = str(result)
                # Skip displaying if this is a system completion message or debug logs
                if self._should_skip_content(result_text):
                    return
                duration = self.calculate_bubble_duration(result_text)
                # 如果有 Qt 气泡组件，使用它显示
                if self.bubble_widget is not None:
                    # 新气泡直接替换旧气泡，不需要等待旧气泡显示完
                    # clear 已经停止之前的定时器和动画
                    self.bubble_widget.clear()
                    self.bubble_widget.set_text(result_text)
                    self.bubble_widget.show_with_duration(duration)
                    # 更新最后一次气泡显示时间（从当前开始）
                    self._update_bubble_time(duration)
                    logging.info(
                        f"Qt bubble displayed for tool result: {result_text[:50]}..."
                    )
                else:
                    bubble_data = Live2dDisplayBubbleText(
                        id=0,
                        text=result_text,
                        choices=[],
                        textFrameColor=0x000000,
                        textColor=0xFFFFFF,
                        duration=duration,
                    )
                    # 检查气泡时间间隔
                    wait_time = self._wait_for_bubble_interval(duration)
                    if wait_time > 0:
                        await asyncio.sleep(wait_time)
                    await send_message(
                        ws, DisplayBubbleText, DisplayBubbleText, bubble_data
                    )
                    # 更新最后一次气泡显示时间
                    self._update_bubble_time(duration)

        except Exception as e:
            logging.error(
                f"Error executing fallback tool {function_name}: {e}", exc_info=True
            )
            error_text = f"执行工具 '{function_name}' 时出错：{str(e)}"
            duration = self.calculate_bubble_duration(error_text)
            # 如果有 Qt 气泡组件，使用它显示错误
            if self.bubble_widget is not None:
                # 新气泡直接替换旧气泡，不需要等待旧气泡显示完
                # clear 已经停止之前的定时器和动画
                self.bubble_widget.clear()
                self.bubble_widget.set_text(error_text)
                self.bubble_widget.show_with_duration(duration)
                # 更新最后一次气泡显示时间（从当前开始）
                self._update_bubble_time(duration)
                logging.info(
                    f"Qt bubble displayed for tool error: {error_text[:50]}..."
                )
            else:
                bubble_data = Live2dDisplayBubbleText(
                    id=0,
                    text=error_text,
                    choices=[],
                    textFrameColor=0x000000,
                    textColor=0xFF0000,
                    duration=duration,
                )
                # 检查气泡时间间隔
                wait_time = self._wait_for_bubble_interval(duration)
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                await send_message(
                    ws, DisplayBubbleText, DisplayBubbleText, bubble_data
                )
                # 更新最后一次气泡显示时间
                self._update_bubble_time(duration)

    async def _compress_context_in_background(self) -> None:
        """在后台执行上下文压缩，不阻塞用户响应

        这个任务在后台运行，生成摘要并压缩旧消息。
        如果失败，只记录错误，不影响用户体验。
        """
        try:
            if self.memory is None:
                return

            # 计算需要压缩的消息范围
            turns = self.memory.session_manager.get_turns()
            start_idx = 0
            # 跳过system prompt
            for i, turn in enumerate(turns):
                if turn.message.get("role", "") != "system":
                    start_idx = i
                    break
            # 保留最后4条消息不压缩
            end_idx = len(turns) - 5
            if end_idx <= start_idx:
                end_idx = start_idx + 1

            # 构建摘要提示词
            summary_prompt = self.memory.summarizer.build_summary_prompt(
                turns, start_idx, end_idx
            )

            # 调用模型生成摘要（这是耗时的操作）
            logging.debug("Generating summary in background...")
            summary_response = await self.model.chat(summary_prompt, tools=None)

            if isinstance(summary_response, dict):
                summary_text = summary_response.get("content", "")
            else:
                summary_text = (
                    getattr(summary_response, "content", "")
                    if hasattr(summary_response, "content")
                    else ""
                )

            if not summary_text:
                logging.warning("Empty summary generated, skipping compression")
                return

            # 执行压缩
            await self.memory.compress_current(summary_text)

            # 更新模型历史（需要线程安全）
            self.model.history = (await self.memory.get_current_messages()).copy()

            logging.info("Background context compression completed successfully")

        except Exception as e:
            logging.error(f"Background compression failed: {e}", exc_info=True)
            # 失败时只记录错误，不影响用户体验

    async def chat_without_tools(self, message: Any, ws: Client) -> str:
        """不使用工具的简单聊天"""
        response_message = await self.model.chat(message=message, tools=None)
        # Get content from either dict or object
        if isinstance(response_message, dict):
            content = response_message.get("content", "")
        else:
            content = (
                getattr(response_message, "content", "")
                if hasattr(response_message, "content")
                else ""
            )
        logging.debug(f"Model response: {content}")
        return content

    async def execute_plan(self, plan: Plan) -> PlanStatus:
        """Execute a plan through the planner.

        If planner is not enabled, returns FAILED status.

        Args:
            plan: The plan to execute.

        Returns:
            The final status of the plan after execution completes.
        """
        if self.planner is None:
            logging.error("Cannot execute plan: planning is not enabled")
            return PlanStatus.FAILED

        return await self.planner.execute_plan(plan)


def create_agent(
    config: AIModelConfig,
    memory_config: MemoryConfig | None = None,
    sandbox_config: SandboxConfig | None = None,
    planning_config: PlanningConfig | None = None,
) -> Agent:
    """根据配置创建Agent实例"""
    if config.type == AIModelType.OllamaModel:
        return Agent(OllamaModel(config), memory_config, sandbox_config, planning_config)
    elif config.type == AIModelType.TransformersModel:
        return Agent(Transformers(config), memory_config, sandbox_config, planning_config)
    elif config.type == AIModelType.Online:
        return Agent(OnlineModel(config), memory_config, sandbox_config, planning_config)
    else:
        raise ValueError(f"Unknown model type: {config.type}")
