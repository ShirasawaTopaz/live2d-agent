# AGENTS.md

**Generated:** 2026-04-19
**Commit:** cbcd075

## OVERVIEW
Python desktop AI Agent with PySide6 UI, WebSocket Live2D integration, extensible plugin
system. The application is composed as a **cordis plugin tree** (pure-Python port of
[DeepSeek Harness's cordis](https://deepseek-harness.github.io/deepseek-harness/develop/cordis-tutorial/)):
`internal/plugins/cordis.yml` is the single composition source, the agent conversation
loop and the scrolling-text bubble output are replaceable plugin slots, and the
`self-evolution` skill lets the agent author, hot-reload, and roll back plugins at runtime.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Startup | `__main__.py` | Entry point → `Live2DAgentApp().run()` |
| Plugin tree | `internal/plugins/cordis.yml` | The composition source; edit here to swap plugins |
| Kernel | `internal/cordis/` | Context, Fiber, effects, events, schema, loader/HMR |
| App plugins | `internal/plugins/` | `core/`, `agent/`, `outputs/`, `ui/`, `integration/`, `meta/` |
| Agent loop slot | `internal/plugins/agent/loop.py` | Default loop; `loop_minimal.py` is the swap example |
| Bubble/scroll slot | `internal/plugins/outputs/typewriter.py` | Scrolling text; `plain.py` renders whole chunks |
| Self-evolution | `internal/plugins/meta/self_evolution.py` | scaffold / install / reload / rollback / status / audit |
| Self-evolution skill | `skills/self-evolution/` | Prompt package describing when and how to author plugins |
| Config | `internal/config/` | Config loading, validation |
| Agent Core | `internal/agent/` | Tool setup, API, bubble timing |
| Memory | `internal/memory/` | Session, summary, compression |
| MCP | `internal/mcp/` | Protocol, backends, manager |
| UI | `internal/ui/` | Qt widgets, input, bubble |
| Skills | `internal/skill/` | Legacy skill registry/manager/dynamic loader |
| RAG | `internal/rag/` | Embeddings, index, document |
| Tests | `test/` | Domain-matched subpackages (`test/cordis/`, `test/plugins/`) |

## STRUCTURE
```
live2oder/
├── __main__.py              # App entry
├── build.py                # PyInstaller packaging
├── pyproject.toml          # Python 3.14, poetry, pytest, ruff, mypy
├── internal/
│   ├── app/              # App bootstrap, runtime, tray
│   ├── cordis/           # Pure-Python cordis kernel (no live2oder imports)
│   ├── plugins/          # Application plugin tree + cordis.yml
│   ├── agent/            # Tools, API, bubble timing
│   ├── config/           # Config loading, editor
│   ├── memory/           # Session, summary, compression
│   ├── mcp/             # Protocol, backends, remote
│   ├── rag/             # Embeddings, index, document
│   ├── skill/            # Registry, manager, dynamic loader
│   ├── ui/              # Qt widgets
│   └── websocket/        # Client, reconnect
├── test/                 # Domain-matched test packages
├── prompt_modules/       # Prompt templates
└── skills/              # Hot-reloadable skills (+ self-evolution)
```

## Runtime Facts
- Use `poetry` for all repo commands. CI installs with `poetry install --with dev` on Python `3.14` exactly; `pyproject.toml`, `mypy.ini`, and `.ruff.toml` all target 3.14.
- Main app entrypoint is `poetry run python __main__.py`.
- First-run setup is not optional in practice: create `config.json` from `config.example.json` or `config.example-prompt-modules.json`. `Config.load()` falls back to defaults when the file is missing, but app bootstrap then calls `get_default_model_config()` and raises if no models are configured.
- The app expects a Live2D WebSocket service at `config.live2dSocket` before normal chat flow works.

## Verification
- Match CI/pre-commit order when validating changes: `poetry run pytest --collect-only`, then `poetry run ruff check __main__.py build.py internal/config internal/prompt_manager internal/websocket test`, then `poetry run mypy __main__.py internal/config internal/prompt_manager internal/websocket`, then `poetry run pre-commit run --all-files`.
- `pytest.ini` ignores `test/planning/test_integration.py` by default. Ruff also excludes `test/agent/test_tool_call_parser.py`, `test/agent/test_transformers_quantization.py`, and `test/planning/test_integration.py`. Mypy excludes `test/planning/test_integration.py` and ignores errors in `internal.websocket.client`.
- Async tests do not require `@pytest.mark.asyncio`; `test/conftest.py` runs coroutine tests in a fresh event loop via a custom hook.
- For a focused check, use normal pytest node selection, for example `poetry run pytest test/test_config.py` or `poetry run pytest test/agent/test_tool_setup.py -q`.

## Architecture
- App startup path is `__main__.py -> internal.app.live2d_agent_app.Live2DAgentApp -> internal.app.bootstrap.bootstrap_application()`.
- `Live2DAgentApp.initialize()` first mounts the cordis plugin tree (`internal.plugins.app.create_plugin_context()`), then runs the legacy bootstrap and hands the created widgets/agent to the slot plugins (`agent/loop`, `outputs/bubble`).
- The plugin tree lives in `internal/plugins/cordis.yml`. Entries mount concurrently; ordering comes from `inject` dependencies, not file position. Swapping `loop` or `output` is how the agent loop / scrolling-text output is replaced.
- Runtime-installed (AI-authored) plugins are persisted to `%APPDATA%/Live2Oder/plugins/user_entries.json` and mounted as an overlay — the shipped `cordis.yml` is never rewritten. Override the root with `LIVE2ODER_PLUGIN_ROOT`.
- A fiber that cannot see a service stays `PENDING` (not an error). Use `ctx.get("meta/diagnostics").pending()` or the `plugin_diagnose` tool to find the missing `inject` name.
- Built-in tools are registered in `internal/agent/tool_setup.py`; the `tools` plugin wraps that call, and plugins contribute extra tools with `ctx.get("tools").register(tool, owner=ctx)`.
- Dynamic tool code persists under `internal/agent/tool/dynamic/tools/` with metadata in `.tools_index.json` and version history under `versions/`. Audit logs are written to `internal/agent/tool/dynamic/audit_logs/`; plugin self-evolution audit trails go to the plugin root (`%APPDATA%/Live2Oder/plugins`).

## Config And Sandbox Gotchas
- `config.json` is gitignored and treated as sensitive. Default sandbox settings explicitly block `.json` files and `config.json`; do not assume agent-side file tools can read it without sandbox changes or approval.
- Default persisted runtime data lives under `data/` (`data/plans.json`, `data/memory`, `data/rag/index`); `data/` is gitignored.

## Build
- Packaging command is `poetry run python build.py`.
- `build.py` requires PyInstaller in the active environment but PyInstaller is not declared in `pyproject.toml`; install it separately before building.
- Packaged assets are defined by `live2d-agent.spec`. The spec bundles `skills/` (including `self-evolution`), `prompt_modules/`, `internal/plugins/` (the tree plus `cordis.yml`), both config examples, `README.md`, and `USER_GUIDE.md` alongside the executable. `test/app/test_packaging.py` asserts this inventory, so update that test when adding shipped assets.
- `pyyaml` is an explicit runtime dependency because `cordis.yml` and `skill.yaml` are YAML.

## Plugin Kernel Cheatsheet
- Write a plugin: export `apply(ctx, config=None)`, or a `Service` subclass, or a module-level `plugin_name` + `service`.
- `inject = ["service-name"]` keeps a plugin `PENDING` until a provider exists; if the provider unloads, the plugin unloads too.
- Everything registered is an effect: `ctx.service`, `ctx.on`, `ctx.effect(disposer)`, `ctx.spawn(coro)`, `tools.register(..., owner=ctx)`. Unloading undoes all of it.
- Events: `emit` (sync broadcast), `await parallel`, `await serial`, `bail`, `await waterfall(name, *args, next=...)`. A waterfall listener that only observes **must** call `next()`.
- HMR: `PluginLoader` watches entry files and the tree file; `loader.reload_entry(id)` disposes the old fiber and mounts the new code. Tests drive it with `handle_file_change(path)`.

## CONVENTIONS
- Python: `>=3.14,<3.15` exactly
- Poetry-driven CI: `poetry install --with dev`, `poetry run ...`
- Test discovery: `test/` only, files named `test_*.py`
- Domain-matched test subpackages: `test/agent/`, `test/planning/`, `test/rag/`, `test/dynamic_tool/`, etc.
- Prompt modules: Chinese primary language, modular structure in `prompt_modules/`

## ANTI-PATTERNS (THIS PROJECT)
- No `[project.scripts]` console entry in `pyproject.toml` - use `poetry run python __main__.py` explicitly
- `test/planning/test_integration.py` excluded from default pytest runs (intentionally skipped)
- Prompt module inconsistencies: English mixed in `prompt_modules/core/tool_calling.md` and capability modules
