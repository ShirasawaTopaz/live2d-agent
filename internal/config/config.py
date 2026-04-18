import json
import aiofiles

from dataclasses import dataclass
from enum import Enum
from json import JSONDecodeError
from typing import Any, Optional

from internal.memory import MemoryConfig
from internal.agent.sandbox import SandboxConfig


class AIModelType(Enum):
    OllamaModel = "ollama"
    TransformersModel = "transformers"
    Online = "online"


@dataclass
class AIModelConfig:
    name: str  # 随便给个不重复的名字就可以了
    model: str
    system_prompt: str | dict  # 支持字符串或模块配置
    type: AIModelType
    default: bool
    config: Any
    temperature: float
    api_key: str | None = None
    streaming: bool = True  # 是否启用流式响应，默认启用
    # New fields for quantization and inference configuration
    load_in_4bit: bool | None = None
    load_in_8bit: bool | None = None
    kv_cache_quantization: bool | None = None
    top_p: float | None = None
    repeat_penalty: float | None = None
    max_new_tokens: int | None = None
    enable_cot: bool | None = None
    max_tool_call_retries: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "model": self.model,
            "system_prompt": self.system_prompt,
            "type": self.type.value,
            "default": self.default,
            "options": self.config if isinstance(self.config, dict) else {},
            "temperature": self.temperature,
            "api_key": self.api_key,
            "streaming": self.streaming,
            "load_in_4bit": self.load_in_4bit,
            "load_in_8bit": self.load_in_8bit,
            "kv_cache_quantization": self.kv_cache_quantization,
            "top_p": self.top_p,
            "repeat_penalty": self.repeat_penalty,
            "max_new_tokens": self.max_new_tokens,
            "enable_cot": self.enable_cot,
            "max_tool_call_retries": self.max_tool_call_retries,
        }


@dataclass
class PlanningConfig:
    """Configuration for planning system."""

    enabled: bool = False
    storage_type: str = "json"  # "json" or "sqlite"
    storage_path: str = "data/plans.json"
    max_concurrency: int = 4
    max_plan_depth: int = 10
    auto_save: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> "PlanningConfig":
        return cls(
            enabled=data.get("enabled", False),
            storage_type=data.get("storage_type", "json"),
            storage_path=data.get("storage_path", "data/plans.json"),
            max_concurrency=data.get("max_concurrency", 4),
            max_plan_depth=data.get("max_plan_depth", 10),
            auto_save=data.get("auto_save", True),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "storage_type": self.storage_type,
            "storage_path": self.storage_path,
            "max_concurrency": self.max_concurrency,
            "max_plan_depth": self.max_plan_depth,
            "auto_save": self.auto_save,
        }


@dataclass
class RAGConfig:
    """Configuration for Retrieval-Augmented Generation."""

    enabled: bool = False
    document_dir: str = ""
    chunk_size: int = 512
    chunk_overlap: int = 50
    top_k: int = 3

    @classmethod
    def from_dict(cls, data: dict) -> "RAGConfig":
        return cls(
            enabled=data.get("enabled", False),
            document_dir=data.get("document_dir", ""),
            chunk_size=data.get("chunk_size", 512),
            chunk_overlap=data.get("chunk_overlap", 50),
            top_k=data.get("top_k", 3),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "document_dir": self.document_dir,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "top_k": self.top_k,
        }


class Config:
    DEFAULT_CONFIG_PATH = "config.json"

    def __init__(self) -> None:
        self.live2dSocket: str = "ws://127.0.0.1:10086/api"
        self.models: list[AIModelConfig] = []
        self.memory: MemoryConfig = MemoryConfig()
        self.sandbox: SandboxConfig = SandboxConfig()
        self.planning: PlanningConfig = PlanningConfig()
        self.rag: RAGConfig = RAGConfig()

    @staticmethod
    async def load(config_path: str = DEFAULT_CONFIG_PATH) -> "Config":
        try:
            async with aiofiles.open(config_path, encoding="utf-8") as file:
                data = await file.read()
        except FileNotFoundError:
            return Config()

        if not data.strip():
            return Config()

        try:
            json_data = json.loads(data)
        except JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON in config file '{config_path}': {exc.msg}"
            ) from exc

        if not isinstance(json_data, dict):
            raise ValueError(
                f"Config file '{config_path}' must contain a JSON object at the top level."
            )

        return Config.from_dict(json_data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        config = cls()
        config._from_dict(data)
        return config

    def _from_dict(self, data: dict):
        if "live2dSocket" in data:
            self.live2dSocket = data["live2dSocket"]

        if "memory" in data and isinstance(data["memory"], dict):
            self.memory = MemoryConfig.from_dict(data["memory"])
        else:
            # 使用默认配置
            self.memory = MemoryConfig()

        if "sandbox" in data and isinstance(data["sandbox"], dict):
            self.sandbox = SandboxConfig.from_dict(data["sandbox"])
        else:
            # Use default sandbox configuration with sensible defaults
            self.sandbox = SandboxConfig()

        if "planning" in data and isinstance(data["planning"], dict):
            self.planning = PlanningConfig.from_dict(data["planning"])
        else:
            # Use default planning configuration with sensible defaults
            self.planning = PlanningConfig()

        self.models = self._load_models(data.get("models"))

        # Load RAG configuration
        if "rag" in data and isinstance(data["rag"], dict):
            self.rag = RAGConfig.from_dict(data["rag"])
        else:
            # Use default RAG configuration (disabled by default)
            self.rag = RAGConfig()

    def to_dict(self) -> dict[str, Any]:
        return {
            "live2dSocket": self.live2dSocket,
            "models": [model.to_dict() for model in self.models],
            "memory": self.memory.to_dict(),
            "sandbox": self.sandbox.to_dict(),
            "planning": self.planning.to_dict(),
            "rag": self.rag.to_dict(),
        }

    # 调用最上面设置为default的模型配置，如果都没设置default=true，则默认调用第一个
    def get_default_model_config(self) -> AIModelConfig:
        for i in self.models:
            if i.default:
                return i
        if len(self.models) == 0:
            raise ValueError(
                "No model configuration found. Please check your config.json file."
            )
        return self.models[0]

    def get_model_config_by_name(self, name: str) -> Optional[AIModelConfig]:
        for i in self.models:
            if i.name == name:
                return i
        return None

    def _load_models(self, raw_models: Any) -> list[AIModelConfig]:
        if raw_models is None:
            return []

        if not isinstance(raw_models, list):
            raise ValueError("The 'models' field must be a list when provided.")

        models: list[AIModelConfig] = []
        for index, model_data in enumerate(raw_models):
            if not isinstance(model_data, dict):
                raise ValueError(f"Model entry at index {index} must be a JSON object.")

            model_name = model_data.get("name", f"models[{index}]")
            model_type_value = model_data.get("type", AIModelType.OllamaModel.value)
            try:
                model_type = AIModelType(model_type_value)
            except ValueError as exc:
                valid_types = ", ".join(model_type.value for model_type in AIModelType)
                raise ValueError(
                    f"Invalid model type '{model_type_value}' for '{model_name}'. "
                    f"Expected one of: {valid_types}."
                ) from exc

            models.append(
                AIModelConfig(
                    name=model_data.get("name", ""),
                    model=model_data.get("model", ""),
                    system_prompt=model_data.get("system_prompt", ""),
                    type=model_type,
                    default=model_data.get("default", False),
                    config=model_data.get("options", {}),
                    temperature=model_data.get("temperature", 0.7),
                    api_key=model_data.get("api_key", None),
                    streaming=model_data.get("streaming", True),
                    load_in_4bit=model_data.get("load_in_4bit", None),
                    load_in_8bit=model_data.get("load_in_8bit", None),
                    kv_cache_quantization=model_data.get("kv_cache_quantization", None),
                    top_p=model_data.get("top_p", None),
                    repeat_penalty=model_data.get("repeat_penalty", None),
                    max_new_tokens=model_data.get("max_new_tokens", None),
                    enable_cot=model_data.get("enable_cot", None),
                    max_tool_call_retries=model_data.get("max_tool_call_retries", None),
                )
            )

        return models
