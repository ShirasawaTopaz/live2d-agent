import asyncio
import json

import pytest

from internal.config.config import AIModelType, Config


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
    assert config.memory is not None
    assert config.sandbox is not None


def test_load_empty_config_file_returns_defaults(tmp_path):
    config = load_config(tmp_path, "   \n\t")

    assert config.live2dSocket == "ws://127.0.0.1:10086/api"
    assert config.models == []


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
