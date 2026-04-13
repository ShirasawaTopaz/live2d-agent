# Skill System for Live2oder

> **Developer-focused architecture documentation**. For user-focused instructions on creating skills, see [USAGE.md](./USAGE.md#skill-system).

The Skill System provides a modular way to bundle related tools and prompts into reusable units called "Skills".

## Overview

A **Skill** is a functional unit that can:
- Provide a set of related **Tools**
- Provide **Prompt** modules to enhance AI capabilities
- Declare **dependencies** on other skills, Python packages, or system commands
- Have its own **configuration**

## Architecture

```
internal/skill/
├── __init__.py          # Package exports
├── base.py              # Skill abstract base class
├── registry.py          # SkillRegistry (singleton)
├── manager.py           # SkillManager (lifecycle)
├── external.py          # ExternalSkill (dynamic loading)
├── integration.py       # Integration with existing systems
└── builtin/             # Built-in skills
    ├── file_ops.py
    └── ...
```

## Built-in Skills

Built-in skills are implemented in Python and reference existing tool classes.

### FileOpsSkill (`file_ops`)

Provides file operation capabilities:
- `file_read` - Read file contents
- `file_write` - Write file contents
- `file_grep` - Search file contents
- `file_run` - Execute files

## External Skills

External skills are loaded from YAML definitions on the filesystem.

### Directory Structure

```
skills/
└── my_skill/
    ├── skill.yaml      # Skill definition
    └── prompts/
        └── *.md        # Prompt modules
```

### skill.yaml Format

```yaml
name: my_skill
version: 1.0.0
description: My custom skill
author: My Name

category: utility
tags: [custom, utility]

dependencies:
  python_packages: ["requests"]
  system_commands: ["git"]
  skills: ["other_skill"]

prompts:
  - name: my_rules
    description: Rules for my skill
    required: true

tools:
  - name: my_tool
    description: Does something useful

config:
  setting1: value1
  max_retries: 3
```

## Configuration

Add to your `config.json`:

```json
{
  "skill_dirs": ["./skills", "./custom_skills"],
  "enabled_skills": ["file_ops", "web_search", "my_custom_skill"]
}
```

## Creating a Custom Skill

### Step 1: Create the Directory Structure

```bash
mkdir -p skills/my_skill/prompts
```

### Step 2: Create skill.yaml

```yaml
name: my_skill
version: 1.0.0
description: My custom skill
category: utility

prompts:
  - name: guidelines
    description: Usage guidelines
    required: true

tools: []
```

### Step 3: Create Prompt Module

Create `skills/my_skill/prompts/guidelines.md`:

```markdown
## My Skill Guidelines

This skill provides custom functionality.

### Usage

1. Follow these guidelines
2. Use the provided tools
3. Handle errors appropriately
```

### Step 4: Enable in Config

Add to `config.json`:

```json
{
  "enabled_skills": ["my_skill"]
}
```

## Integration

The Skill system integrates with existing components:

- **ToolRegistry**: Skills register their tools during enable()
- **PromptManager**: Skill prompts are included in system prompt
- **Agent**: Modified to support skill system integration

## API Reference

### Skill (Abstract Base Class)

```python
class MySkill(Skill):
    def _load_metadata(self) -> SkillMetadata:
        return SkillMetadata(...)

    def _load(self) -> None:
        # Define tools and prompts

    async def initialize(self) -> bool:
        return True

    async def shutdown(self) -> None:
        pass
```

### SkillManager

```python
manager = SkillManager(
    skill_dirs=["./skills"],
    prompt_manager=prompt_manager,
    tool_registry=tool_registry
)

await manager.load_all()
await manager.enable("my_skill")
```

### SkillSystemIntegration

```python
integration = SkillSystemIntegration(
    skill_manager=manager,
    tool_registry=tool_registry,
    prompt_manager=prompt_manager
)

await integration.enable_skill("my_skill")
prompts = integration.get_system_prompt_additions()
```
