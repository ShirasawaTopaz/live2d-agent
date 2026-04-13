# Skill Dynamic Loading

This feature adds hot-reload support for skills, allowing you to add, modify, and remove skills without restarting the application.

## Quick Start

### 1. Enable Dynamic Loading

```python
from internal.skill import integrate_skill_system

# During agent initialization
integration = integrate_skill_system(
    agent=agent,
    config=config,
    enable_dynamic_loading=True  # Enable hot-reload
)
```

### 2. Install Watchdog (Optional but Recommended)

```bash
pip install watchdog
```

Or:

```bash
pip install -e ".[skill-hot-reload]"
```

### 3. Test It

1. Create a new skill in `./skills/`:

```yaml
# ./skills/my_new_skill/skill.yaml
name: my_new_skill
version: 1.0.0
description: A dynamically loaded skill
author: You
category: utility
```

2. Watch the console - you'll see the skill automatically detected and loaded!

## Features

- **Hot-reload**: Changes to skills are detected and applied immediately
- **Dual mode**: Uses `watchdog` when available, falls back to polling otherwise
- **Event callbacks**: Hook into skill lifecycle events
- **Context manager**: Clean resource management

## API

### Basic Usage

```python
from internal.skill import SkillManager, DynamicSkillLoader

skill_manager = SkillManager(skill_dirs=["./skills"])
loader = DynamicSkillLoader(
    skill_manager=skill_manager,
    on_skill_added=lambda n, s: print(f"Added: {n}"),
    on_skill_removed=lambda n: print(f"Removed: {n}"),
    on_skill_reloaded=lambda n, s: print(f"Reloaded: {n}"),
)

loader.watch(["./skills"])

# ... later ...
loader.stop()
```

### Context Manager

```python
with DynamicSkillLoader(skill_manager) as loader:
    loader.watch(["./skills"])
    # Watch while in context
# Automatically stopped
```

### Force Polling Mode

```python
loader = DynamicSkillLoader(
    skill_manager=skill_manager,
    use_polling=True,  # Force polling
    poll_interval=2.0,  # Check every 2 seconds
)
```

## How It Works

### Watchdog Mode (Default)

1. Uses OS-specific file system events (inotify/epoll on Linux, FSEvents on macOS, ReadDirectoryChangesW on Windows)
2. Low CPU usage - only wakes up when files change
3. Fast detection - typically milliseconds

### Polling Mode (Fallback)

1. Periodically scans directories for changes
2. Compares modification times of `skill.yaml` files
3. Higher CPU usage but works everywhere
4. Detection delay depends on poll interval

## Troubleshooting

### Changes not detected

- Check directory permissions
- Verify the directory is being watched (check console output)
- Try forcing polling mode to test

### High CPU usage

- Install watchdog for efficient monitoring
- Reduce number of watched directories
- Increase poll interval if using polling mode

### Duplicate reload events

- This is normal due to debouncing
- Ensure your callbacks are idempotent
- Check for rapid file writes in your editor

## Examples

See `examples/dynamic_skills_example.py` for a complete working example.

## Further Reading

- Full documentation: `docs/DYNAMIC_SKILLS.md`
- API reference: `docs/SKILL_SYSTEM_API.md`
- Creating skills: `SKILL_SYSTEM_README.md`
