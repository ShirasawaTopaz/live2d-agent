import asyncio
import json

import pytest

from internal.config.config import AIModelConfig, AIModelType, Config


def load_config(
    tmp_path, content: str | None = None, *, file_name: str = "config.json"
) -> Config:
    config_path = tmp_path / file_name
    if content is not None:
        config_path.write_text(content, encoding="utf-8")
    return asyncio.run(Config.load(str(config_path)))


def test_load_missing_config_file_returns_defaults(tmp_path):
    config = load_config(tmp_path, None)

    assert config.live2dSocket == "ws://127.0.0.1:10086/api"
    assert config.models == []
    assert config.live2dExpressions.enabled is True
    assert config.live2dExpressions.default_expression == "EXP_NEUTRAL_01"
    assert config.memory is not None
    assert config.sandbox is not None


def test_load_empty_config_file_returns_defaults(tmp_path):
    config = load_config(tmp_path, "   \n\t")

    assert config.live2dSocket == "ws://127.0.0.1:10086/api"
    assert config.models == []
    assert config.live2dExpressions.fallback_policy == "neutral"


def test_load_invalid_json_raises_value_error(tmp_path):
    with pytest.raises(ValueError, match="Invalid JSON"):
        load_config(tmp_path, '{"models": [}')


def test_load_invalid_model_type_raises_value_error(tmp_path):
    invalid_config = {
        "models": [
            {
                "name": "broken-model",
                "model": "demo",
                "type": "not-a-real-type",
                "system_prompt": "hi",
                "default": True,
            }
        ]
    }

    with pytest.raises(ValueError, match="Invalid model type 'not-a-real-type'"):
        load_config(tmp_path, json.dumps(invalid_config))


def test_get_default_model_config_raises_when_no_models_configured(tmp_path):
    config = load_config(tmp_path, json.dumps({"models": []}))

    with pytest.raises(ValueError, match="No model configuration found"):
        config.get_default_model_config()


def test_get_default_model_config_falls_back_to_first_model(tmp_path):
    config_data = {
        "models": [
            {
                "name": "first-model",
                "model": "model-a",
                "type": "ollama",
                "system_prompt": "first",
            },
            {
                "name": "second-model",
                "model": "model-b",
                "type": "online",
                "system_prompt": "second",
            },
        ]
    }

    config = load_config(tmp_path, json.dumps(config_data))
    default_model = config.get_default_model_config()

    assert default_model.name == "first-model"
    assert default_model.type is AIModelType.OllamaModel


def test_repeated_loads_do_not_accumulate_models(tmp_path):
    config_data = {
        "models": [
            {
                "name": "single-model",
                "model": "model-a",
                "type": "ollama",
                "system_prompt": "hello",
                "default": True,
            }
        ]
    }
    content = json.dumps(config_data)

    first = load_config(tmp_path, content)
    second = load_config(tmp_path, content)

    assert len(first.models) == 1
    assert len(second.models) == 1
    assert first.models is not second.models
    assert second.get_default_model_config().name == "single-model"


def test_config_to_dict_roundtrip_for_known_sections():
    config_data = {
        "live2dSocket": "ws://127.0.0.1:10086/api",
        "live2dExpressions": {
            "enabled": True,
            "defaultExpression": "EXP_NEUTRAL_01",
            "cooldownMs": 1200,
            "enableMultiStage": True,
            "fallbackPolicy": "neutral",
            "stages": [
                {
                    "emotion": "happy",
                    "expression": "EXP_HAPPY_01",
                    "intensity": "low",
                    "priority": 2,
                    "cooldownMs": 900,
                    "fallback": "EXP_NEUTRAL_01",
                    "sceneTags": ["greeting", "praise"],
                }
            ],
            "emotionAliases": {"joy": "happy"},
        },
        "models": [
            {
                "name": "model-a",
                "model": "m-a",
                "type": "ollama",
                "system_prompt": {"core/base_rules": True},
                "default": True,
                "temperature": 0.2,
                "options": {"top_p": 0.9},
                "streaming": True,
            }
        ],
        "memory": {"enabled": True, "max_messages": 12},
        "sandbox": {"enabled": True, "approval": {"timeout_seconds": 45}},
        "planning": {"enabled": True, "storage_type": "json", "storage_path": "data/plans.json"},
        "rag": {"enabled": True, "document_dir": "./docs", "chunk_size": 256, "chunk_overlap": 16, "top_k": 5},
    }

    config = Config.from_dict(config_data)
    dumped = config.to_dict()
    restored = Config.from_dict(dumped)

    assert restored.live2dSocket == "ws://127.0.0.1:10086/api"
    assert restored.live2dExpressions.default_expression == "EXP_NEUTRAL_01"
    assert restored.live2dExpressions.stages[0].expression == "EXP_HAPPY_01"
    assert restored.live2dExpressions.stages[0].scene_tags == ["greeting", "praise"]
    assert restored.get_default_model_config().name == "model-a"
    assert restored.memory.max_messages == 12
    assert restored.sandbox.approval.timeout_seconds == 45
    assert restored.planning.enabled is True
    assert restored.rag.document_dir == "./docs"


def test_memory_config_preserves_mcp_fields_roundtrip():
    config_data = {
        "memory": {
            "enabled": True,
            "use_mcp": True,
            "mcp_mode": "remote",
            "compression_strategy": "sliding",
            "max_working_messages": 24,
            "max_recent_tokens": 8192,
            "max_total_tokens": 12288,
            "remote": {
                "enabled": True,
                "endpoint": "http://localhost:8080/v1",
                "api_key": "secret",
                "timeout": 45,
                "verify_ssl": False,
            },
        }
    }

    config = Config.from_dict(config_data)
    dumped = config.to_dict()
    restored = Config.from_dict(dumped)

    assert restored.memory.use_mcp is True
    assert restored.memory.mcp_mode == "remote"
    assert restored.memory.compression_strategy == "sliding"
    assert restored.memory.max_working_messages == 24
    assert restored.memory.max_recent_tokens == 8192
    assert restored.memory.max_total_tokens == 12288
    assert restored.memory.remote["enabled"] is True
    assert restored.memory.remote["verify_ssl"] is False


def test_online_model_prefers_top_level_model_fields_over_options():
    pytest.importorskip("openai")
    from internal.agent.agent_support.online import OnlineModel

    model = OnlineModel(
        AIModelConfig(
            name="online",
            model="demo-endpoint",
            system_prompt="hi",
            type=AIModelType.Online,
            default=True,
            config={"api": "https://example.invalid", "temperature": 0.1, "max_tokens": 128},
            temperature=0.55,
            api_key="top-level-key",
            top_p=0.93,
            repeat_penalty=1.07,
            max_new_tokens=256,
            enable_cot=True,
            max_tool_call_retries=3,
        )
    )

    params = model._build_request_params(tools=None, stream=False)

    assert model._api == "https://example.invalid"
    assert params["temperature"] == 0.55
    assert params["max_tokens"] == 256
    assert params["top_p"] == 0.93
    assert params["repeat_penalty"] == 1.07
    assert params["enable_cot"] is True
