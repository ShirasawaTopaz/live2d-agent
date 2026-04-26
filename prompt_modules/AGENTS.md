# prompt_modules/

**Generated:** 2026-04-19

## OVERVIEW
Modular prompt templates for AI model interaction - core system prompts + capability modules.

## WHERE TO LOOK
| Module | Purpose |
|--------|---------|
| `core/base_rules.md` | Base assistant rules |
| `core/tool_calling.md` | Tool call format rules |
| `core/live2d_rules.md` | Live2D behavior rules |
| `core/cot.md` | Chain-of-thought guidance |
| `core/small_model_format.md` | Small-model output format |
| `capabilities/file_ops.md` | File operations |
| `capabilities/office.md` | Office documents |
| `capabilities/web_search.md` | Web search integration |
| `capabilities/live2d_ctrl.md` | Live2D control helpers |
| `capabilities/coding_expert.md` | Coding assistance |
| `capabilities/bug_fix_expert.md` | Bug-fix guidance |
| `capabilities/architecture_design_expert.md` | Architecture guidance |
| `languages/chinese.md` | Chinese language guidance |
| `personality/cute.md` | Cute personality layer |
| `scenarios/daily_chat.md` | Daily chat scenario |

## CONVENTIONS
- Chinese primary language throughout
- Tool call format enforced strictly
- Small model profiles for summarization
- Canonical layer buckets are `core/`, `capabilities/`, `languages/`, `personality/`, and `scenarios/`

## ANTI-PATTERNS
- English mixed in `prompt_modules/core/tool_calling.md` (needs cleanup)
- Capability modules contain English JSON examples mixed with Chinese text
