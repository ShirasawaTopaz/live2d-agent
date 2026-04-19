import sys
from importlib import import_module
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from internal.config.config import AIModelConfig, AIModelType
from internal.memory import MemoryManager
from internal.memory._types import MemoryConfig

classify_small_model_memory_profile = import_module(
    "internal.memory._small_model_profile"
).classify_small_model_memory_profile


def make_model_config(
    *,
    model_type: AIModelType,
    model: str,
    options: dict | None = None,
) -> AIModelConfig:
    return AIModelConfig(
        name=f"{model_type.value}-{model}",
        model=model,
        system_prompt="test prompt",
        type=model_type,
        default=False,
        config=options or {},
        temperature=0.7,
    )


def make_memory_config(
    *,
    data_dir: str,
    model_config: AIModelConfig,
    use_mcp: bool = False,
) -> MemoryConfig:
    cfg = MemoryConfig()
    cfg.data_dir = data_dir
    cfg.use_mcp = use_mcp
    cfg.enable_long_term = False
    cfg.long_term_compression_enabled = False
    cfg.compress_on_startup = False
    cfg.max_working_messages = 6
    setattr(cfg, "small_model_memory_model_config", model_config)
    return cfg


def test_small_transformers_classification_enabled():
    profile = classify_small_model_memory_profile(
        make_model_config(
            model_type=AIModelType.TransformersModel,
            model="Qwen2.5-1.8B-Instruct",
        )
    )

    assert profile.enabled is True
    assert profile.reason == "transformers-small-1.8b"
    assert profile.summary_style == "compact_summary"
    assert profile.compression_aggressiveness == "aggressive"
    assert profile.preserve_recent_count == 3
    assert profile.summary_length_cap == 320
    assert profile.injection_compactness == "tight"


def test_online_model_classification_disabled():
    profile = classify_small_model_memory_profile(
        make_model_config(
            model_type=AIModelType.Online,
            model="gpt-4.1-mini",
            options={"api": "https://example.invalid"},
        )
    )

    assert profile.enabled is False
    assert profile.reason == "online-model"
    assert profile.summary_style == "default"
    assert profile.compression_aggressiveness == "default"


def test_non_small_local_transformers_classification_disabled():
    profile = classify_small_model_memory_profile(
        make_model_config(
            model_type=AIModelType.TransformersModel,
            model="Qwen2.5-7B-Instruct",
        )
    )

    assert profile.enabled is False
    assert profile.reason == "transformers-not-small-7.0b"


def test_ambiguous_local_model_fallback_disabled():
    profile = classify_small_model_memory_profile(
        make_model_config(
            model_type=AIModelType.OllamaModel,
            model="my-custom-local-model",
        )
    )

    assert profile.enabled is False
    assert profile.reason == "ollama-size-ambiguous"


def test_remote_ollama_endpoint_fallback_disabled():
    profile = classify_small_model_memory_profile(
        make_model_config(
            model_type=AIModelType.OllamaModel,
            model="qwen2.5:1.8b",
            options={"host": "https://remote.example.com"},
        )
    )

    assert profile.enabled is False
    assert profile.reason == "ollama-explicit-remote-endpoint"


def test_equivalent_metadata_yields_deterministic_output():
    first_profile = classify_small_model_memory_profile(
        make_model_config(
            model_type=AIModelType.OllamaModel,
            model="qwen2.5:1.8b",
            options={"host": "http://127.0.0.1:11434"},
        )
    )
    second_profile = classify_small_model_memory_profile(
        make_model_config(
            model_type=AIModelType.OllamaModel,
            model="qwen2.5:1.8b",
            options={"host": "127.0.0.1:11434"},
        )
    )

    assert first_profile == second_profile
    assert first_profile.enabled is True
    assert first_profile.reason == "ollama-local-endpoint-small-1.8b"


@pytest.mark.asyncio
async def test_profile_decision_logging_enabled_without_sensitive_content(
    tmp_path, caplog
):
    model_config = make_model_config(
        model_type=AIModelType.TransformersModel,
        model="Qwen2.5-1.8B-Instruct",
    )
    manager = MemoryManager(
        make_memory_config(
            data_dir=str(tmp_path / "memory-enabled"),
            model_config=model_config,
        )
    )

    with caplog.at_level("INFO"):
        await manager.init()

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "Small-model memory profile decision: enabled" in log_text
    assert "reason=transformers-small-1.8b" in log_text
    assert "test prompt" not in log_text
    assert "以下是之前对话的摘要" not in log_text


@pytest.mark.asyncio
async def test_profile_decision_logging_fallback_reason_for_ambiguous_model(
    tmp_path, caplog
):
    model_config = make_model_config(
        model_type=AIModelType.OllamaModel,
        model="custom-local-model",
    )
    manager = MemoryManager(
        make_memory_config(
            data_dir=str(tmp_path / "memory-fallback"),
            model_config=model_config,
        )
    )

    with caplog.at_level("INFO"):
        await manager.init()

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "Small-model memory profile decision: fallback=legacy-default" in log_text
    assert "reason=ollama-size-ambiguous" in log_text
