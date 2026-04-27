# internal/

**Generated:** 2026-04-19

## OVERVIEW
Core application modules - app bootstrap, agent core, config, memory, MCP, RAG, skills, UI, websocket.

## WHERE TO LOOK
| Module | Purpose |
|--------|---------|
| `app/` | Live2DAgentApp, bootstrap, runtime, tray |
| `agent/` | Tool setup, API handlers, bubble timing |
| `config/` | Config loading, validation, editor |
| `memory/` | Session, summary, compression, tool offload |
| `mcp/` | Protocol, backends, manager |
| `rag/` | Embeddings, index, document |
| `skill/` | Registry, manager, dynamic loader |
| `ui/` | Qt widgets, input, bubble, styles |
| `websocket/` | Client, reconnect logic |

## CONVENTIONS
- All modules use `__init__.py` for package exports
- Agent tools registered in `agent/tool_setup.py`
- Memory uses small model for summarization (`_small_model_profile.py`)
- MCP backends: ollama, transformers, online API

## ANTI-PATTERNS
- No direct `config.json` reads by agent tools - sandbox blocks it
- `test/` has its own AGENTS.md (separate domain)
