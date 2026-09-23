"""Plugin slot: the language model provider (``agent/model``).

Builds the concrete :class:`ModelTrait` implementation from ``config.json``
(``Ollama`` / ``Transformers`` / ``Online``) and exposes it as ``agent/model``
so the agent loop and other plugins never construct a model themselves.
"""

from __future__ import annotations

from typing import Any

from internal.cordis import Schema, Service
from internal.agent.agent_support.ollama import OllamaModel
from internal.agent.agent_support.online import OnlineModel
from internal.agent.agent_support.trait import ModelTrait
from internal.agent.agent_support.transformers import Transformers
from internal.config.config import AIModelConfig, AIModelType

plugin_name = "agent/model"

module_schema = Schema.object({})


def build_model(model_config: AIModelConfig) -> ModelTrait:
    """Create the model implementation for a config entry."""
    if model_config.type == AIModelType.OllamaModel:
        return OllamaModel(model_config)
    if model_config.type == AIModelType.TransformersModel:
        return Transformers(model_config)
    if model_config.type == AIModelType.Online:
        return OnlineModel(model_config)
    raise ValueError(f"Unknown model type: {model_config.type}")


class ModelService(Service):
    """Exposes the active model and supports hot replacement."""

    def __init__(self, ctx: Any, name: str = "agent/model") -> None:
        super().__init__(ctx, name)
        self.model: ModelTrait | None = None

    @property
    def initialized(self) -> bool:
        return self.model is not None

    def configure(self, model_config: AIModelConfig) -> ModelTrait:
        self.model = build_model(model_config)
        self.ctx.root.emit("agent/model/changed", self.model)
        return self.model

    def configure_from_config_service(self) -> ModelTrait:
        config_service = self.ctx.get("config")
        if config_service is None or getattr(config_service, "value", None) is None:
            raise RuntimeError("config service is not initialized")
        model_config = config_service.get_default_model_config()
        if model_config is None:
            raise ValueError("No model configuration found. Please check your config.json file.")
        return self.configure(model_config)


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    _ = config
    ctx.service("agent/model", ModelService(ctx, "agent/model"))
