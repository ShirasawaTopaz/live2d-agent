# Dynamic Skill Loading

This document describes the dynamic skill loading system with hot-reload support in Live2oder.

## Overview

The dynamic skill loader provides:

1. **Hot-reload**: Automatically detect and reload skill changes without restarting
2. **File watching**: Monitor skill directories for changes
3. **Event callbacks**: Handle skill lifecycle events (added, removed, reloaded)
4. **Dual mode support**: Both watchdog (efficient) and polling (portable) modes

## Installation

### With Watchdog (Recommended)

For efficient file system monitoring:

```bash
pip install watchdog
```

Or install with the optional dependency:

```bash
pip install -e ".[skill-hot-reload]"
```

### Without Watchdog (Polling Mode)

If watchdog is not available, the system will automatically fall back to polling mode. This works everywhere but uses more CPU.

## Usage

### Basic Usage

```python
from internal.skill import SkillManager, DynamicSkillLoader

# Create skill manager
skill_manager = SkillManager(
    skill_dirs=["./skills"],
    prompt_manager=prompt_manager,
    tool_registry=tool_registry
)

# Create dynamic loader
dynamic_loader = DynamicSkillLoader(
    skill_manager=skill_manager,
    on_skill_added=lambda name, skill: print(f"Added: {name}"),
    on_skill_removed=lambda name: print(f"Removed: {name}"),
    on_skill_reloaded=lambda name, skill: print(f"Reloaded: {name}"),
)

# Start watching
dynamic_loader.watch(["./skills"])

# ... run your application ...

# Stop watching
dynamic_loader.stop()
```

### Context Manager

```python
with DynamicSkillLoader(skill_manager) as loader:
    loader.watch(["./skills"])
    # Watch while in context
# Automatically stopped on exit
```

### Forcing Polling Mode

```python
# Force polling mode even if watchdog is available
dynamic_loader = DynamicSkillLoader(
    skill_manager=skill_manager,
    use_polling=True,  # Force polling mode
    poll_interval=2.0,  # Poll every 2 seconds
)
```

## Integration with Agent

The skill system integration now supports dynamic loading out of the box:

```python
from internal.skill import integrate_skill_system

# During agent initialization
integration = integrate_skill_system(
    agent=agent,
    config=config,
    enable_dynamic_loading=True  # Enable hot-reload
)

# Dynamic loader is now attached to agent
# and watching configured skill directories
```

To disable dynamic loading:

```python
integration = integrate_skill_system(
    agent=agent,
    config=config,
    enable_dynamic_loading=False  # Disable hot-reload
)
```

## How It Works

### Watchdog Mode (Default)

1. Uses `watchdog` library to monitor file system events
2. Efficient - only triggers on actual changes
3. Low CPU usage
4. Platform-specific implementations (inotify on Linux, FSEvents on macOS, ReadDirectoryChangesW on Windows)

### Polling Mode (Fallback)

1. Periodically scans directories for changes
2. Compares modification times of `skill.yaml` files
3. Higher CPU usage but works everywhere
4. Configurable poll interval

### Hot-Reload Process

When a skill is modified:

1. File change detected (via watchdog or polling)
2. Debounce rapid changes (wait for writes to complete)
3. Unload old skill version
4. Load new skill definition
5. Re-enable skill if it was enabled
6. Trigger `on_skill_reloaded` callback

## Configuration Options

```python
DynamicSkillLoader(
    skill_manager=skill_manager,
    
    # Event callbacks
    on_skill_added=None,      # Called when skill is added
    on_skill_removed=None,    # Called when skill is removed
    on_skill_reloaded=None,   # Called when skill is hot-reloaded
    
    # Mode selection
    use_polling=False,        # Force polling mode
    poll_interval=2.0,        # Poll interval in seconds
)
```

## Best Practices

1. **Use watchdog mode when possible** - More efficient and responsive
2. **Handle debounce in callbacks** - Multiple rapid changes may trigger multiple events
3. **Check skill dependencies** on reload - Dependencies may have changed
4. **Save user state** before reload - User might lose in-progress work
5. **Log reload events** - Helpful for debugging issues

## Troubleshooting

### Changes not detected

- Check that the correct directory is being watched
- Verify file permissions
- For polling mode: check that poll interval is not too high

### High CPU usage

- Switch to watchdog mode if using polling
- Reduce number of watched directories
- Increase poll interval if using polling mode

### Duplicate reload events

- This is normal due to debouncing - implement idempotent callbacks
- Check for rapid successive file writes

## Example: Complete Setup

```python
import asyncio
from internal.skill import (
    SkillManager,
    SkillSystemIntegration,
    DynamicSkillLoader,
)

async def main():
    # Setup
    skill_manager = SkillManager(
        skill_dirs=["./skills"],
        prompt_manager=None,
        tool_registry=None,
    )
    
    # Load initial skills
    await skill_manager.load_all()
    
    # Create integration
    integration = SkillSystemIntegration(
        skill_manager=skill_manager,
        tool_registry=None,
    )
    
    # Create dynamic loader with all callbacks
    loader = DynamicSkillLoader(
        skill_manager=skill_manager,
        on_skill_added=lambda n, s: print(f"✓ Added: {n}"),
        on_skill_removed=lambda n: print(f"✗ Removed: {n}"),
        on_skill_reloaded=lambda n, s: print(f"↻ Reloaded: {n}"),
    )
    
    # Start watching
    loader.watch(["./skills"])
    
    print("Skill system is running with hot-reload enabled.")
    print("Make changes to skills in ./skills/ to see hot-reload in action.")
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        loader.stop()

if __name__ == "__main__":
    asyncio.run(main())
```
