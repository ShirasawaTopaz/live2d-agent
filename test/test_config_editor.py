from internal.config.config import Config
from internal.config.editor import (
    decide_runtime_apply,
    merge_known_fields,
    normalize_models_default,
    load_with_raw,
    validate_config_dict,
)


def test_merge_known_fields_preserves_unknown_keys():
    raw = {
        "live2dSocket": "ws://old",
        "live2dExpressions": {"enabled": True, "defaultExpression": "EXP_NEUTRAL_01"},
        "memory": {
            "enabled": True,
            "max_messages": 10,
            "extra_memory_key": {"keep": "yes"},
        },
        "custom_top_level": {"abc": 123},
    }
    edited = {
        "live2dSocket": "ws://new",
        "live2dExpressions": {"enabled": False, "fallbackPolicy": "no-op"},
        "memory": {"enabled": False, "max_messages": 20},
    }

    merged = merge_known_fields(raw, edited)

    assert merged["live2dSocket"] == "ws://new"
    assert merged["live2dExpressions"]["enabled"] is False
    assert merged["live2dExpressions"]["defaultExpression"] == "EXP_NEUTRAL_01"
    assert merged["live2dExpressions"]["fallbackPolicy"] == "no-op"
    assert merged["memory"]["enabled"] is False
    assert merged["memory"]["max_messages"] == 20
    assert merged["memory"]["extra_memory_key"] == {"keep": "yes"}
    assert merged["custom_top_level"] == {"abc": 123}


def test_normalize_models_default_keeps_preferred_index():
    models = [
        {"name": "m1", "default": True},
        {"name": "m2", "default": True},
        {"name": "m3", "default": False},
    ]
    normalized, fixed = normalize_models_default(models, preferred_index=0)

    assert fixed is True
    assert [bool(model["default"]) for model in normalized] == [True, False, False]


def test_validate_config_dict_rejects_invalid_values():
    data = {
        "live2dSocket": "http://invalid",
        "live2dExpressions": [],
        "models": [
            {
                "name": "",
                "model": "",
                "type": "invalid-type",
                "system_prompt": [],
                "temperature": 3,
                "options": "not-an-object",
            }
        ],
    }

    errors = validate_config_dict(data)
    fields = {error.field for error in errors}

    assert "live2dSocket" in fields
    assert "live2dExpressions" in fields
    assert "models[0].name" in fields
    assert "models[0].model" in fields
    assert "models[0].type" in fields
    assert "models[0].system_prompt" in fields
    assert "models[0].temperature" in fields
    assert "models[0].options" in fields


def test_validate_config_dict_rejects_invalid_memory_mcp_values():
    data = {
        "live2dSocket": "ws://valid",
        "models": [
            {
                "name": "ok",
                "model": "m",
                "type": "ollama",
                "system_prompt": "x",
                "temperature": 0.7,
                "options": {},
            }
        ],
        "memory": {
            "mcp_mode": "invalid",
            "compression_strategy": "bad",
            "max_working_messages": 0,
            "remote": {"timeout": 0},
        },
    }

    errors = validate_config_dict(data)
    fields = {error.field for error in errors}

    assert "memory.mcp_mode" in fields
    assert "memory.compression_strategy" in fields
    assert "memory.max_working_messages" in fields
    assert "memory.remote.timeout" in fields


def test_load_with_raw_returns_raw_and_config(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        "{\n  \"live2dSocket\": \"ws://example\",\n  \"models\": []\n}",
        encoding="utf-8",
    )

    raw, config = load_with_raw(str(config_path))

    assert raw["live2dSocket"] == "ws://example"
    assert raw["models"] == []
    assert config.live2dSocket == "ws://example"


def test_decide_runtime_apply_detects_socket_and_default_model_change():
    old = Config.from_dict(
        {
            "live2dSocket": "ws://old",
            "models": [
                {
                    "name": "a",
                    "model": "m1",
                    "type": "ollama",
                    "system_prompt": "x",
                    "default": True,
                    "temperature": 0.7,
                    "options": {},
                }
            ],
        }
    )
    new = Config.from_dict(
        {
            "live2dSocket": "ws://new",
            "models": [
                {
                    "name": "b",
                    "model": "m2",
                    "type": "online",
                    "system_prompt": "y",
                    "default": True,
                    "temperature": 0.7,
                    "options": {},
                }
            ],
        }
    )

    decision = decide_runtime_apply(old, new)
    assert decision.websocket_changed is True
    assert decision.default_model_changed is True
    assert decision.requires_restart is False


def test_decide_runtime_apply_requires_restart_for_non_hot_sections():
    old = Config.from_dict(
        {
            "live2dSocket": "ws://same",
            "models": [
                {
                    "name": "a",
                    "model": "m1",
                    "type": "ollama",
                    "system_prompt": "x",
                    "default": True,
                    "temperature": 0.7,
                    "options": {},
                }
            ],
            "memory": {"enabled": True, "max_messages": 10},
        }
    )
    new = Config.from_dict(
        {
            "live2dSocket": "ws://same",
            "models": [
                {
                    "name": "a",
                    "model": "m1",
                    "type": "ollama",
                    "system_prompt": "x",
                    "default": True,
                    "temperature": 0.7,
                    "options": {},
                }
            ],
            "memory": {"enabled": True, "max_messages": 99},
        }
    )

    decision = decide_runtime_apply(old, new)
    assert decision.websocket_changed is False
    assert decision.default_model_changed is False
    assert decision.requires_restart is True


def test_decide_runtime_apply_requires_restart_for_live2d_expressions_change():
    old = Config.from_dict(
        {
            "live2dSocket": "ws://same",
            "models": [
                {
                    "name": "a",
                    "model": "m1",
                    "type": "ollama",
                    "system_prompt": "x",
                    "default": True,
                    "temperature": 0.7,
                    "options": {},
                }
            ],
            "live2dExpressions": {
                "enabled": True,
                "defaultExpression": "EXP_NEUTRAL_01",
                "stages": [
                    {
                        "emotion": "happy",
                        "expression": "EXP_HAPPY_01",
                        "intensity": "low",
                        "priority": 1,
                    }
                ],
            },
        }
    )
    new = Config.from_dict(
        {
            "live2dSocket": "ws://same",
            "models": [
                {
                    "name": "a",
                    "model": "m1",
                    "type": "ollama",
                    "system_prompt": "x",
                    "default": True,
                    "temperature": 0.7,
                    "options": {},
                }
            ],
            "live2dExpressions": {
                "enabled": True,
                "defaultExpression": "EXP_NEUTRAL_01",
                "stages": [
                    {
                        "emotion": "happy",
                        "expression": "EXP_HAPPY_02",
                        "intensity": "low",
                        "priority": 1,
                    }
                ],
            },
        }
    )

    decision = decide_runtime_apply(old, new)
    assert decision.requires_restart is True
