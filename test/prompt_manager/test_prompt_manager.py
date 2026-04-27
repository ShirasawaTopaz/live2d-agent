import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # pyright: ignore[reportMissingImports]

from internal.agent.agent_support.ollama import OllamaModel
from internal.agent.agent_support.trait import ModelTrait
from internal.config.config import Config
from internal.prompt_manager.prompt_manager import PromptManager


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


@pytest.fixture(autouse=True)
def reset_prompt_manager_state():
    PromptManager._instance = None
    PromptManager._modules = {}
    ModelTrait._prompt_manager = None
    OllamaModel._prompt_manager = None
    yield
    PromptManager._instance = None
    PromptManager._modules = {}
    ModelTrait._prompt_manager = None
    OllamaModel._prompt_manager = None


def _write_prompt_tree(tmp_path: Path) -> Path:
    modules_dir = tmp_path / "prompt_modules"
    (modules_dir / "core").mkdir(parents=True)
    (modules_dir / "persona").mkdir(parents=True)

    (modules_dir / "core" / "base_rules.md").write_text(
        "  Base rules  ", encoding="utf-8"
    )
    (modules_dir / "core" / "style.md").write_text("Style guide", encoding="utf-8")
    (modules_dir / "persona" / "voice.md").write_text(
        "Hello {{name}}, you have {{count}} tasks.", encoding="utf-8"
    )

    return modules_dir


async def test_load_recursively_loads_nested_markdown_modules(tmp_path):
    manager = await PromptManager.load(_write_prompt_tree(tmp_path))

    assert manager.has_module("core/base_rules") is True
    assert manager.has_module("core/style") is True
    assert manager.has_module("persona/voice") is True
    assert manager.has_module("core/base_rules.md") is False
    assert manager.get_module("core/base_rules") == "Base rules"
    assert {key: sorted(value) for key, value in manager.list_modules_by_category().items()} == {
        "core": ["core/base_rules", "core/style"],
        "persona": ["persona/voice"],
    }


async def test_compose_system_prompt_preserves_order_and_skips_missing_modules(tmp_path):
    manager = await PromptManager.load(_write_prompt_tree(tmp_path))

    prompt = await manager.compose_system_prompt(
        {
            "prefix": "Prelude",
            "modules": [
                "core/base_rules",
                "missing/module",
                "core/style",
                "persona/voice",
            ],
            "suffix": "Wrap up",
        }
    )

    assert prompt == (
        "Prelude\n\n"
        "Base rules\n\n"
        "Style guide\n\n"
        "Hello {{name}}, you have {{count}} tasks.\n\n"
        "Wrap up"
    )


async def test_compose_system_prompt_keeps_prefix_without_base_rules(tmp_path):
    manager = await PromptManager.load(_write_prompt_tree(tmp_path))

    prompt = await manager.compose_system_prompt(
        {
            "prefix": "Persona must be followed",
            "modules": ["core/style"],
        }
    )

    assert prompt == "Persona must be followed\n\nStyle guide"


async def test_render_module_substitutes_placeholders_and_missing_module_returns_empty(tmp_path):
    manager = await PromptManager.load(_write_prompt_tree(tmp_path))

    rendered = await manager.render_module("persona/voice", {"name": "Mika", "count": 3})

    assert rendered == "Hello Mika, you have 3 tasks."
    assert await manager.render_module("missing/module") == ""


async def test_ollama_model_resolves_composed_system_prompt_into_history(tmp_path):
    manager = await PromptManager.load(_write_prompt_tree(tmp_path))
    ModelTrait._prompt_manager = manager
    OllamaModel._prompt_manager = manager

    config = Config.from_dict(
        {
            "models": [
                {
                    "name": "demo",
                    "model": "llama3",
                    "type": "ollama",
                    "system_prompt": {
                        "prefix": "Prelude",
                        "modules": ["core/base_rules", "missing/module", "persona/voice"],
                        "suffix": "Wrap up",
                    },
                    "default": True,
                    "temperature": 0.7,
                    "options": {},
                }
            ]
        }
    )

    model = OllamaModel(config.get_default_model_config())
    model._client = FakeClient(
        SimpleNamespace(message=SimpleNamespace(role="assistant", content="ok"))
    )

    result = await model.chat("hello")

    assert result == {"role": "assistant", "content": "ok"}
    assert model.history[0] == {
        "role": "system",
        "content": (
            "Prelude\n\n"
            "Base rules\n\n"
            "Hello {{name}}, you have {{count}} tasks.\n\n"
            "Wrap up"
        ),
    }
    assert model.history[1] == {"role": "user", "content": "hello"}
    assert model.history[2] == {"role": "assistant", "content": "ok"}


async def test_ollama_model_prepends_system_prompt_to_existing_long_history(tmp_path):
    manager = await PromptManager.load(_write_prompt_tree(tmp_path))
    ModelTrait._prompt_manager = manager
    OllamaModel._prompt_manager = manager

    config = Config.from_dict(
        {
            "models": [
                {
                    "name": "demo",
                    "model": "llama3",
                    "type": "ollama",
                    "system_prompt": {
                        "prefix": "Persona must be followed",
                        "modules": ["core/style"],
                    },
                    "default": True,
                    "options": {},
                }
            ]
        }
    )

    long_input = "长" * 2000
    model = OllamaModel(config.get_default_model_config())
    model.history = [{"role": "user", "content": long_input}]
    fake_client = FakeClient(
        SimpleNamespace(message=SimpleNamespace(role="assistant", content="ok"))
    )
    model._client = fake_client

    await model.chat(None)

    sent_messages = fake_client.calls[0]["messages"]
    assert sent_messages[0] == {
        "role": "system",
        "content": "Persona must be followed\n\nStyle guide",
    }
    assert sent_messages[1] == {"role": "user", "content": long_input}


async def test_ollama_model_merges_prompt_before_existing_system_context(tmp_path):
    manager = await PromptManager.load(_write_prompt_tree(tmp_path))
    ModelTrait._prompt_manager = manager
    OllamaModel._prompt_manager = manager

    config = Config.from_dict(
        {
            "models": [
                {
                    "name": "demo",
                    "model": "llama3",
                    "type": "ollama",
                    "system_prompt": {
                        "prefix": "Persona must be followed",
                        "modules": ["core/style"],
                    },
                    "default": True,
                    "options": {},
                }
            ]
        }
    )

    model = OllamaModel(config.get_default_model_config())
    model.history = [
        {"role": "system", "content": "Retrieved context"},
        {"role": "user", "content": "长" * 2000},
    ]
    fake_client = FakeClient(
        SimpleNamespace(message=SimpleNamespace(role="assistant", content="ok"))
    )
    model._client = fake_client

    await model.chat(None)

    assert fake_client.calls[0]["messages"][0] == {
        "role": "system",
        "content": "Persona must be followed\n\nStyle guide\n\nRetrieved context",
    }
