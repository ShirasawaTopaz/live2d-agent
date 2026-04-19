# AGENTS.md

## Runtime Facts
- Use `poetry` for all repo commands. CI installs with `poetry install --with dev` on Python `3.14` exactly; `pyproject.toml`, `mypy.ini`, and `.ruff.toml` all target 3.14.
- Main app entrypoint is `poetry run python __main__.py`.
- First-run setup is not optional in practice: create `config.json` from `config.example.json` or `config.example-prompt-modules.json`. `Config.load()` falls back to defaults when the file is missing, but app bootstrap then calls `get_default_model_config()` and raises if no models are configured.
- The app expects a Live2D WebSocket service at `config.live2dSocket` before normal chat flow works.

## Verification
- Match CI/pre-commit order when validating changes: `poetry run pytest --collect-only`, then `poetry run ruff check __main__.py build.py internal/config internal/prompt_manager internal/websocket tests`, then `poetry run mypy __main__.py internal/config internal/prompt_manager internal/websocket`, then `poetry run pre-commit run --all-files`.
- `pytest.ini` ignores `tests/planning/test_integration.py` by default. Ruff also excludes `tests/agent/test_tool_call_parser.py`, `tests/agent/test_transformers_quantization.py`, and `tests/planning/test_integration.py`. Mypy excludes `tests/planning/test_integration.py` and ignores errors in `internal.websocket.client`.
- Async tests do not require `@pytest.mark.asyncio`; `tests/conftest.py` runs coroutine tests in a fresh event loop via a custom hook.
- For a focused check, use normal pytest node selection, for example `poetry run pytest tests/test_config.py` or `poetry run pytest tests/agent/test_tool_setup.py -q`.

## Architecture
- App startup path is `__main__.py -> internal.app.live2d_agent_app.Live2DAgentApp -> internal.app.bootstrap.bootstrap_application()`.
- `bootstrap_application()` loads `Config`, then `PromptManager`, then creates Qt app, reconnecting websocket, runtime agent, input box, and bubble widget.
- Built-in tools are registered centrally in `internal/agent/tool_setup.py`; edit that file when adding/removing default tools.
- Dynamic tool code persists under `internal/agent/tool/dynamic/tools/` with metadata in `.tools_index.json` and version history under `versions/`. Audit logs are written to `internal/agent/tool/dynamic/audit_logs/`.

## Config And Sandbox Gotchas
- `config.json` is gitignored and treated as sensitive. Default sandbox settings explicitly block `.json` files and `config.json`; do not assume agent-side file tools can read it without sandbox changes or approval.
- Default persisted runtime data lives under `data/` (`data/plans.json`, `data/memory`, `data/rag/index`); `data/` is gitignored.

## Build
- Packaging command is `poetry run python build.py`.
- `build.py` requires PyInstaller in the active environment but PyInstaller is not declared in `pyproject.toml`; install it separately before building.
- Packaged assets are defined by `live2d-agent.spec`. Current spec bundles `skills/`, `prompt_modules/`, both config examples, `README.md`, and `USER_GUIDE.md` alongside the executable.
