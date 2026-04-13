import json
import aiofiles

from dataclasses import dataclass
from enum import Enum
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


class Config:
    live2dSocket: str = "ws://127.0.0.1:10086/api"
    models: list[AIModelConfig] = []
    memory: MemoryConfig | None = None
    sandbox: SandboxConfig | None = None
    planning: PlanningConfig | None = None

    @staticmethod
    async def load():
        config = Config()
        try:
            async with aiofiles.open("config.json", encoding="utf-8") as file:
                data = await file.read()
                if data != "":
                    json_data = json.loads(data)
                    config._from_dict(json_data)
        except FileNotFoundError:
            pass
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

        if "models" in data and isinstance(data["models"], list):
            for model_data in data["models"]:
                model_config = AIModelConfig(
                    name=model_data.get("name", ""),
                    model=model_data.get("model", ""),
                    system_prompt=model_data.get("system_prompt", ""),
                    type=AIModelType(model_data.get("type", "ollama")),
                    default=model_data.get("default", False),
                    config=model_data.get("options", {}),
                    temperature=model_data.get("temperature", 0.7),
                    api_key=model_data.get("api_key", None),
                    streaming=model_data.get("streaming", True),  # 默认启用流式响应
                )
                self.models.append(model_config)

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
