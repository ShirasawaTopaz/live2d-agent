import sys
from dataclasses import asdict
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from internal.config.config import AIModelConfig, AIModelType
from internal.memory import MemoryManager
from internal.memory._small_model_profile import classify_small_model_memory_profile
from internal.memory._types import MemoryConfig

def _make_model_config(
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


def _make_memory_config(
    *,
    data_dir: str,
    model_config: AIModelConfig,
) -> MemoryConfig:
    cfg = MemoryConfig()
    cfg.data_dir = data_dir
    cfg.use_mcp = True
    cfg.mcp_mode = "local"
    cfg.max_messages = 20
    cfg.max_working_messages = 8
    cfg.compression_threshold_messages = 9
    cfg.compress_on_startup = False
    cfg.enable_long_term = False
    setattr(cfg, "small_model_memory_model_config", model_config)
    return cfg


@pytest.mark.asyncio
async def test_mcp_path_selects_same_profile_as_classifier(tmp_path):
    model_config = _make_model_config(
        model_type=AIModelType.OllamaModel,
        model="qwen2.5:1.8b",
        options={"host": "http://127.0.0.1:11434"},
    )
    expected = classify_small_model_memory_profile(model_config)
    manager = MemoryManager(
        _make_memory_config(
            data_dir=str(tmp_path / "mcp-parity"),
            model_config=model_config,
        )
    )

    await manager.init()

    assert manager._small_model_profile == expected
    assert manager._mcp is not None
    assert manager._mcp.config.small_model_memory_profile == expected


@pytest.mark.asyncio
async def test_mcp_ambiguous_model_falls_back_safely(tmp_path):
    model_config = _make_model_config(
        model_type=AIModelType.OllamaModel,
        model="custom-model-without-size",
    )
    manager = MemoryManager(
        _make_memory_config(
            data_dir=str(tmp_path / "mcp-fallback"),
            model_config=model_config,
        )
    )

    await manager.init()

    assert manager._small_model_profile is not None
    assert manager._small_model_profile.enabled is False
    assert manager._small_model_profile.reason == "ollama-size-ambiguous"
    assert manager._mcp is not None
    assert manager._mcp.config.small_model_memory_profile is not None
    assert manager._mcp.config.small_model_memory_profile.enabled is False


@pytest.mark.asyncio
async def test_mcp_profile_controls_recent_preservation_count(tmp_path):
    model_config = _make_model_config(
        model_type=AIModelType.TransformersModel,
        model="Qwen2.5-1.8B-Instruct",
    )
    manager = MemoryManager(
        _make_memory_config(
            data_dir=str(tmp_path / "mcp-compression"),
            model_config=model_config,
        )
    )
    await manager.init()
    assert manager._mcp is not None
    assert manager._small_model_profile is not None
    assert manager._small_model_profile.enabled is True
    assert manager._small_model_profile.preserve_recent_count == 3

    for idx in range(10):
        manager.add_message(
            {
                "role": "user" if idx % 2 == 0 else "assistant",
                "content": f"message-{idx}",
                "tokens": 10,
            }
        )
    await manager._drain_pending_mcp_tasks()
    await manager._mcp.compress_pending("default")

    working = manager._mcp._get_working_memory("default")
    recent = manager._mcp._get_recent_chunks("default")

    assert len(working.messages) == 3
    assert len(recent) == 1
    assert recent[0].compressed is True
    assert len(recent[0].messages) <= 10
    # Default summary compression strategy keeps at most 3 newest messages in chunk.
    assert len(recent[0].messages) <= 3


def test_mcp_config_roundtrip_preserves_profile_payload():
    profile = classify_small_model_memory_profile(
        _make_model_config(
            model_type=AIModelType.TransformersModel,
            model="Qwen2.5-2B-Instruct",
        )
    )
    cfg = {
        "enabled": True,
        "mcp_mode": "local",
        "compression_strategy": "summary",
        "small_model_memory_profile": asdict(profile),
    }
    from internal.mcp.config import MCPConfig

    parsed = MCPConfig.from_dict(cfg)
    dumped = parsed.to_dict()

    assert parsed.small_model_memory_profile == profile
    assert dumped["small_model_memory_profile"] == asdict(profile)
