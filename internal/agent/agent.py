from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional, TYPE_CHECKING

from .agent_support.ollama import OllamaModel
from .agent_support.online import OnlineModel
from .agent_support.trait import ModelTrait
from .agent_support.transformers import Transformers
from .bubble_timing import BubbleTimingController, calculate_bubble_duration
from .chat_service import ChatService, Live2DConflictController, Live2DExpressionScheduler
from .planning.base import Plan
from .planning.planner import Planner, PlannerConfig
from .planning.storage.json import JSONPlanStorage
from .planning.storage.sqlite import SQLitePlanStorage
from .planning.types import PlanStatus
from .register import ToolRegistry
from .sandbox import SandboxConfig, SandboxMiddleware, default_sandbox
from .tool.base import Tool
from .tool.dynamic.storage import DynamicToolStorage
from .tool_setup import register_default_tools
from internal.config.config import AIModelConfig, AIModelType, Config, PlanningConfig
from internal.memory import MemoryConfig, MemoryManager
from internal.rag.rag import RAGManager
from internal.websocket.client import Client

if TYPE_CHECKING:
    from internal.config.config import RAGConfig
    from internal.ui.bubble_widget import BubbleWidget

__all__ = ["Agent", "create_agent"]


class Agent:
    """AI Agent主类，处理聊天和工具调用。"""

    model: ModelTrait
    tool_registry: ToolRegistry
    memory: MemoryManager | None = None
    bubble_widget: BubbleWidget | None = None
    sandbox: SandboxMiddleware
    dynamic_tool_storage: DynamicToolStorage
    planner: Optional[Planner] = None
    rag: Optional[RAGManager] = None
    live2d_expressions: Any | None = None
    live2d_scheduler: Any | None = None
    _compression_task: asyncio.Task | None = None

    def __init__(
        self,
        model: ModelTrait,
        memory_config: MemoryConfig | None = None,
        sandbox_config: SandboxConfig | None = None,
        planning_config: PlanningConfig | None = None,
        rag_config: RAGConfig | None = None,
    ) -> None:
        self.model = model
        self.tool_registry = ToolRegistry()
        self.sandbox = SandboxMiddleware(sandbox_config) if sandbox_config else default_sandbox

        self.dynamic_tool_storage = DynamicToolStorage()
        register_default_tools(self.tool_registry, self.sandbox, self.dynamic_tool_storage)

        loaded_count = self.tool_registry.load_all_dynamic_tools(self.dynamic_tool_storage)
        if loaded_count > 0:
            logging.info(f"Loaded {loaded_count} dynamic tool(s) from storage")

        self.bubble_timing = BubbleTimingController()
        self.live2d_conflict = Live2DConflictController()
        self.live2d_expressions = None
        self.live2d_scheduler = Live2DExpressionScheduler(self.live2d_conflict)
        self.chat_service = ChatService(self, self.live2d_conflict, self.live2d_scheduler)
        self.max_tool_calls = 5
        self.memory = MemoryManager(memory_config) if memory_config and memory_config.enabled else None
        self.rag = self._initialize_rag(rag_config)
        self.planner = self._initialize_planner(planning_config)

    @staticmethod
    def calculate_bubble_duration(text: str) -> int:
        return calculate_bubble_duration(text)

    def _wait_for_bubble_interval(self, current_duration: int) -> float:
        return self.bubble_timing.wait_for_bubble_interval(current_duration)

    def _update_bubble_time(self, duration: int) -> None:
        self.bubble_timing.update_bubble_time(duration)

    def _register_default_tools(self) -> None:
        register_default_tools(self.tool_registry, self.sandbox, self.dynamic_tool_storage)

    def configure_live2d_expression_tools(self, expressions_config: Any | None) -> None:
        # Inject configured stage count so Live2D tools can wrap expression rotation locally.
        stages = getattr(expressions_config, "stages", []) if expressions_config is not None else []
        expression_count = len(stages) if isinstance(stages, list) else None
        for tool_name in ("next_expression", "display_bubble_text"):
            tool = self.tool_registry.tools.get(tool_name)
            if tool is not None and hasattr(tool, "set_expression_count"):
                tool.set_expression_count(expression_count)


    def _should_skip_content(self, content: str) -> bool:
        return self.bubble_timing.should_skip_content(content)

    async def _try_parse_and_send_bubble(self, content: str, ws: Client) -> None:
        await self.chat_service.try_parse_and_send_bubble(content, ws)

    async def _send_single_bubble(self, content: str, ws: Client) -> None:
        await self.bubble_timing.send_single_bubble(content, ws, self.bubble_widget)

    async def _execute_tool_call_fallback(self, tool_call: dict, ws: Client) -> None:
        await self.chat_service.execute_tool_call_fallback(tool_call, ws)

    def register_tool(self, tool: Tool) -> None:
        self.tool_registry.register(tool)

    async def initialize_memory(self) -> None:
        if self.memory is not None and not self.memory._initialized:
            await self.memory.init()
            if hasattr(self.memory, "compress_all_eligible") and getattr(
                self.memory.config, "compress_on_startup", True
            ):
                asyncio.create_task(self._auto_compress_inactive())

    async def _auto_compress_inactive(self) -> None:
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
        return await self.chat_service.chat(message, ws)

    async def _compress_context_in_background(self) -> None:
        try:
            if self.memory is None:
                return

            turns = self.memory.session_manager.get_turns()
            start_idx = 0
            for i, turn in enumerate(turns):
                if turn.message.get("role", "") != "system":
                    start_idx = i
                    break

            end_idx = len(turns) - 5
            if end_idx <= start_idx:
                end_idx = start_idx + 1

            summary_prompt = self.memory.summarizer.build_summary_prompt(
                turns, start_idx, end_idx
            )
            logging.debug("Generating summary in background...")
            summary_response = await self.model.chat(summary_prompt, tools=None)

            if isinstance(summary_response, dict):
                summary_text = summary_response.get("content", "")
            else:
                summary_text = getattr(summary_response, "content", "")

            if not summary_text:
                logging.warning("Empty summary generated, skipping compression")
                return

            await self.memory.compress_current(summary_text)
            self.model.history = (await self.memory.get_current_messages()).copy()
            logging.info("Background context compression completed successfully")
        except Exception as e:
            logging.error(f"Background compression failed: {e}", exc_info=True)

    async def chat_without_tools(self, message: Any, ws: Client) -> str:
        response_message = await self.model.chat(message=message, tools=None)
        if isinstance(response_message, dict):
            content = response_message.get("content", "")
        else:
            content = getattr(response_message, "content", "")
        logging.debug(f"Model response: {content}")
        return content

    async def execute_plan(self, plan: Plan) -> PlanStatus:
        if self.planner is None:
            logging.error("Cannot execute plan: planning is not enabled")
            return PlanStatus.FAILED
        return await self.planner.execute_plan(plan)

    def _initialize_rag(
        self,
        rag_config: RAGConfig | None,
    ) -> Optional[RAGManager]:
        if not rag_config or not rag_config.enabled:
            return None
        try:
            rag = RAGManager(rag_config)
            success = rag.initialize()
            if success and rag.is_enabled:
                logging.info("RAG initialized successfully")
                return rag
            logging.warning("RAG initialization failed, RAG disabled")
        except Exception as e:
            logging.error(f"Error initializing RAG: {e}", exc_info=True)
        return None

    def _initialize_planner(
        self,
        planning_config: PlanningConfig | None,
    ) -> Optional[Planner]:
        if not planning_config or not planning_config.enabled:
            return None

        if planning_config.storage_type == "json":
            storage = JSONPlanStorage(planning_config.storage_path)
        elif planning_config.storage_type == "sqlite":
            storage = SQLitePlanStorage(planning_config.storage_path)
        else:
            logging.warning(
                f"Unknown storage type '{planning_config.storage_type}', using JSON"
            )
            storage = JSONPlanStorage(planning_config.storage_path)

        planner_config = PlannerConfig(
            max_concurrency=planning_config.max_concurrency,
            max_plan_depth=getattr(planning_config, "max_plan_depth", 10),
            auto_save=getattr(planning_config, "auto_save", True),
        )
        return Planner(storage=storage, config=planner_config, agent=self)


def create_agent(
    model_config: AIModelConfig,
    memory_config: MemoryConfig | None = None,
    sandbox_config: SandboxConfig | None = None,
    planning_config: PlanningConfig | None = None,
    global_config: Config | None = None,
    ) -> Agent:
    """根据配置创建Agent实例。"""
    rag_config = global_config.rag if global_config is not None else None

    if memory_config is not None:
        setattr(memory_config, "small_model_memory_model_config", model_config)

    if model_config.type == AIModelType.OllamaModel:
        model = OllamaModel(model_config)
    elif model_config.type == AIModelType.TransformersModel:
        model = Transformers(model_config)
    elif model_config.type == AIModelType.Online:
        model = OnlineModel(model_config)
    else:
        raise ValueError(f"Unknown model type: {model_config.type}")

    agent = Agent(
        model,
        memory_config=memory_config,
        sandbox_config=sandbox_config,
        planning_config=planning_config,
        rag_config=rag_config,
    )
    if global_config is not None:
        agent.live2d_conflict = Live2DConflictController(global_config.live2dExpressions)
        agent.live2d_expressions = global_config.live2dExpressions
        agent.configure_live2d_expression_tools(global_config.live2dExpressions)
        agent.live2d_scheduler = Live2DExpressionScheduler(agent.live2d_conflict, global_config.live2dExpressions)
        agent.chat_service = ChatService(agent, agent.live2d_conflict, agent.live2d_scheduler)
    return agent
