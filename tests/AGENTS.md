# tests/

**Generated:** 2026-04-19

## OVERVIEW
Domain-matched test subpackages - `agent/`, `planning/`, `rag/`, `dynamic_tool/`, `memory/`, `mcp/`.

## WHERE TO LOOK
| Domain | Location |
|--------|----------|
| Agent tools | `tests/agent/test_tool_setup.py` |
| Planning | `tests/planning/test_plan.py`, `test_executor.py` |
| RAG | `tests/rag/test_index.py`, `test_embeddings.py` |
| Dynamic tools | `tests/dynamic_tool/test_generator.py` |
| Memory | `tests/memory/test_storage_backends.py` |
| MCP | `tests/mcp/test_backends.py` |

## CONVENTIONS
- Test files: `test_*.py` only, discovered in `tests/` root
- Async: `conftest.py` provides automatic coroutine runner - `@pytest.mark.asyncio` optional
- Conditional execution: `pytest.importorskip()` for optional deps
- Domain packages have `__init__.py`

## ANTI-PATTERNS
- `tests/planning/test_integration.py` excluded from default runs
- `tests/agent/test_tool_call_parser.py`, `tests/agent/test_transformers_quantization.py` excluded from ruff