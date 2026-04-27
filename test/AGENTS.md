# test/

**Generated:** 2026-04-19

## OVERVIEW
Domain-matched test subpackages - `agent/`, `planning/`, `rag/`, `dynamic_tool/`, `memory/`, `mcp/`.

## WHERE TO LOOK
| Domain | Location |
|--------|----------|
| Agent tools | `test/agent/test_tool_setup.py` |
| Planning | `test/planning/test_plan.py`, `test_executor.py` |
| RAG | `test/rag/test_index.py`, `test_embeddings.py` |
| Dynamic tools | `test/dynamic_tool/test_generator.py` |
| Memory | `test/memory/test_storage_backends.py` |
| MCP | `test/mcp/test_backends.py` |

## CONVENTIONS
- Test files: `test_*.py` only, discovered in `test/` root
- Async: `conftest.py` provides automatic coroutine runner - `@pytest.mark.asyncio` optional
- Conditional execution: `pytest.importorskip()` for optional deps
- Domain packages have `__init__.py`

## ANTI-PATTERNS
- `test/planning/test_integration.py` excluded from default runs
- `test/agent/test_tool_call_parser.py`, `test/agent/test_transformers_quantization.py` excluded from ruff
