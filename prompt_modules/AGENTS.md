# prompt_modules/

**Generated:** 2026-04-19

## OVERVIEW
Modular prompt templates for AI model interaction - core system prompts + capability modules.

## WHERE TO LOOK
| Module | Purpose |
|--------|---------|
| `core/tool_calling.md` | Tool call format rules |
| `capabilities/web_search.md` | Web search integration |
| `capabilities/file_ops.md` | File operations |
| `capabilities/office.md` | Office documents |

## CONVENTIONS
- Chinese primary language throughout
- Tool call format enforced strictly
- Small model profiles for summarization

## ANTI-PATTERNS
- English mixed in `prompt_modules/core/tool_calling.md` (needs cleanup)
- Capability modules contain English JSON examples mixed with Chinese text