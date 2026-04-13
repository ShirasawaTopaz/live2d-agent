"""Dynamic skill loader with hot-reload support."""

import asyncio
import os
import time
import threading
from pathlib import Path
from typing import Callable, Optional

from .base import Skill
from .manager import SkillManager

# Optional watchdog import - fallback to polling if not available
try:
    from watchdog.observers import Observer
    from watchdog.events import (
        FileSystemEventHandler,
        FileModifiedEvent,
        FileCreatedEvent,
        FileDeletedEvent,
    )

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    Observer = None
    FileSystemEventHandler = object
    FileModifiedEvent = None
    FileCreatedEvent = None
    FileDeletedEvent = None


class SkillDirectoryWatcher(FileSystemEventHandler if WATCHDOG_AVAILABLE else object):
    """Watchdog event handler for skill directory changes."""

    def __init__(
        self,
        skill_manager: SkillManager,
        on_skill_added: Optional[Callable[[str, Skill], None]] = None,
        on_skill_removed: Optional[Callable[[str], None]] = None,
        on_skill_changed: Optional[Callable[[str, Skill], None]] = None,
    ):
        """Initialize the watcher.

        Args:
            skill_manager: The skill manager instance
            on_skill_added: Callback when a skill is added
            on_skill_removed: Callback when a skill is removed
            on_skill_changed: Callback when a skill is modified
        """
        self.skill_manager = skill_manager
        self.on_skill_added = on_skill_added
        self.on_skill_removed = on_skill_removed
        self.on_skill_changed = on_skill_changed

        # Debounce timers for file changes
        self._pending_changes: dict[str, float] = {}
        self._debounce_interval = 0.5  # seconds

    def on_created(self, event=None, src_path: str = None, is_directory: bool = False):
        """Handle file/directory creation."""
        if event is not None:
            src_path = event.src_path
            is_directory = (
                event.is_directory if hasattr(event, "is_directory") else False
            )

        if is_directory:
            # Check if this is a new skill directory
            skill_yaml_path = Path(src_path) / "skill.yaml"
            if skill_yaml_path.exists():
                self._handle_skill_added(src_path)
        elif src_path.endswith("skill.yaml"):
            # New skill.yaml created
            self._handle_skill_added(os.path.dirname(src_path))

    def on_deleted(self, event=None, src_path: str = None, is_directory: bool = False):
        """Handle file/directory deletion."""
        if event is not None:
            src_path = event.src_path
            is_directory = (
                event.is_directory if hasattr(event, "is_directory") else False
            )

        if is_directory:
            # Check if this was a skill directory
            skill_name = Path(src_path).name
            if self.skill_manager.registry.get(skill_name):
                self._handle_skill_removed(skill_name)

    def on_modified(self, event=None, src_path: str = None, is_directory: bool = False):
        """Handle file modification."""
        if event is not None:
            src_path = event.src_path
            is_directory = (
                event.is_directory if hasattr(event, "is_directory") else False
            )

        if is_directory:
            return

        # Debounce rapid file changes
        file_path = src_path
        current_time = time.time()

        # Only process skill.yaml changes or prompt file changes
        if "skill.yaml" in file_path or file_path.endswith(".md"):
            self._pending_changes[file_path] = current_time
            asyncio.create_task(self._process_pending_changes())

    async def _process_pending_changes(self):
        """Process pending file changes after debounce interval."""
        await asyncio.sleep(self._debounce_interval)

        current_time = time.time()
        to_process = []

        for file_path, timestamp in list(self._pending_changes.items()):
            if current_time - timestamp >= self._debounce_interval:
                to_process.append(file_path)
                del self._pending_changes[file_path]

        for file_path in to_process:
            # Find the skill directory
            path = Path(file_path)
            if path.name == "skill.yaml":
                skill_path = path.parent
            else:
                # Find parent with skill.yaml
                skill_path = path.parent
                while skill_path.parent != skill_path:
                    if (skill_path / "skill.yaml").exists():
                        break
                    skill_path = skill_path.parent

            self._handle_skill_changed(str(skill_path))

    def _handle_skill_added(self, skill_path: str):
        """Handle a new skill being added."""
        try:
            skill = asyncio.run(self.skill_manager._load_skill(skill_path))
            if skill:
                skill_name = Path(skill_path).name
                if self.on_skill_added:
                    self.on_skill_added(skill_name, skill)
        except Exception as e:
            print(f"Failed to load skill from {skill_path}: {e}")

    def _handle_skill_removed(self, skill_name: str):
        """Handle a skill being removed."""
        if self.on_skill_removed:
            self.on_skill_removed(skill_name)

    def _handle_skill_changed(self, skill_path: str):
        """Handle a skill being modified."""
        try:
            skill_name = Path(skill_path).name

            # Remove old version if exists
            if self.skill_manager.registry.get(skill_name):
                if self.on_skill_removed:
                    self.on_skill_removed(skill_name)

            # Load new version
            skill = asyncio.run(self.skill_manager._load_skill(skill_path))
            if skill and self.on_skill_changed:
                self.on_skill_changed(skill_name, skill)
        except Exception as e:
            print(f"Failed to reload skill from {skill_path}: {e}")


class PollingSkillWatcher:
    """Fallback polling-based skill watcher when watchdog is not available."""

    def __init__(
        self,
        skill_manager: SkillManager,
        directories: list[str],
        on_skill_added=None,
        on_skill_removed=None,
        on_skill_changed=None,
        poll_interval: float = 2.0,
    ):
        self.skill_manager = skill_manager
        self.directories = [os.path.abspath(d) for d in directories]
        self.on_skill_added = on_skill_added
        self.on_skill_removed = on_skill_removed
        self.on_skill_changed = on_skill_changed
        self.poll_interval = poll_interval

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._known_skills: dict[str, tuple[str, float]] = {}  # name -> (path, mtime)

    def start(self):
        """Start polling."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

        # Initial scan
        self._scan_all()

    def stop(self):
        """Stop polling."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _poll_loop(self):
        """Main polling loop."""
        while self._running:
            try:
                self._scan_all()
            except Exception as e:
                print(f"[PollingWatcher] Error during scan: {e}")

            # Sleep with early exit check
            for _ in range(int(self.poll_interval * 10)):
                if not self._running:
                    break
                time.sleep(0.1)

    def _scan_all(self):
        """Scan all directories for changes."""
        current_skills: dict[str, tuple[str, float]] = {}

        for directory in self.directories:
            if not os.path.exists(directory):
                continue

            for item in os.listdir(directory):
                path = os.path.join(directory, item)
                if not os.path.isdir(path):
                    continue

                skill_yaml = os.path.join(path, "skill.yaml")
                if not os.path.exists(skill_yaml):
                    continue

                mtime = os.path.getmtime(skill_yaml)
                current_skills[item] = (path, mtime)

        # Detect changes
        # New skills
        for name, (path, mtime) in current_skills.items():
            if name not in self._known_skills:
                self._handle_added(path)
            elif self._known_skills[name][1] != mtime:
                self._handle_changed(path)

        # Removed skills
        for name in self._known_skills:
            if name not in current_skills:
                self._handle_removed(name)

        self._known_skills = current_skills

    def _handle_added(self, path: str):
        """Handle new skill."""
        watcher = SkillDirectoryWatcher(
            skill_manager=self.skill_manager,
            on_skill_added=self.on_skill_added,
            on_skill_removed=self.on_skill_removed,
            on_skill_changed=self.on_skill_changed,
        )
        watcher._handle_skill_added(path)

    def _handle_removed(self, name: str):
        """Handle removed skill."""
        watcher = SkillDirectoryWatcher(
            skill_manager=self.skill_manager,
            on_skill_added=self.on_skill_added,
            on_skill_removed=self.on_skill_removed,
            on_skill_changed=self.on_skill_changed,
        )
        watcher._handle_skill_removed(name)

    def _handle_changed(self, path: str):
        """Handle changed skill."""
        watcher = SkillDirectoryWatcher(
            skill_manager=self.skill_manager,
            on_skill_added=self.on_skill_added,
            on_skill_removed=self.on_skill_removed,
            on_skill_changed=self.on_skill_changed,
        )
        watcher._handle_skill_changed(path)


class DynamicSkillLoader:
    """Dynamic skill loader with hot-reload support.

    This class provides the ability to:
    1. Watch skill directories for changes
    2. Automatically load new skills
    3. Hot-reload modified skills
    4. Remove deleted skills

    Supports both watchdog-based file system monitoring (preferred)
    and polling-based fallback for environments where watchdog
    is not available.

    Example:
        ```python
        loader = DynamicSkillLoader(skill_manager)

        # Start watching for changes
        loader.watch(["./skills", "./custom_skills"])

        # Later, stop watching
        loader.stop()
        ```
    """

    def __init__(
        self,
        skill_manager: SkillManager,
        on_skill_added: Optional[Callable[[str, Skill], None]] = None,
        on_skill_removed: Optional[Callable[[str], None]] = None,
        on_skill_reloaded: Optional[Callable[[str, Skill], None]] = None,
        use_polling: bool = False,
        poll_interval: float = 2.0,
    ):
        """Initialize the dynamic loader.

        Args:
            skill_manager: The skill manager instance
            on_skill_added: Callback when a skill is added
            on_skill_removed: Callback when a skill is removed
            on_skill_reloaded: Callback when a skill is reloaded
            use_polling: Force use of polling instead of watchdog
            poll_interval: Polling interval in seconds (if using polling)
        """
        self.skill_manager = skill_manager
        self.on_skill_added = on_skill_added
        self.on_skill_removed = on_skill_removed
        self.on_skill_reloaded = on_skill_reloaded
        self.use_polling = use_polling or not WATCHDOG_AVAILABLE
        self.poll_interval = poll_interval

        self._observer: Optional[Observer] = None
        self._polling_watcher: Optional[PollingSkillWatcher] = None
        self._watchers: list[SkillDirectoryWatcher] = []
        self._watched_dirs: set[str] = set()

    def watch(self, directories: list[str]) -> None:
        """Start watching skill directories for changes.

        Args:
            directories: List of directory paths to watch
        """
        if self.use_polling:
            self._start_polling_watcher(directories)
        else:
            self._start_watchdog_watcher(directories)

    def _start_watchdog_watcher(self, directories: list[str]) -> None:
        """Start the watchdog-based file system watcher."""
        if self._observer is None:
            self._observer = Observer()

        for directory in directories:
            if directory in self._watched_dirs:
                continue

            # Resolve to absolute path
            abs_path = os.path.abspath(directory)
            if not os.path.exists(abs_path):
                os.makedirs(abs_path, exist_ok=True)

            # Create watcher
            watcher = SkillDirectoryWatcher(
                skill_manager=self.skill_manager,
                on_skill_added=self._on_skill_added,
                on_skill_removed=self._on_skill_removed,
                on_skill_changed=self._on_skill_reloaded,
            )

            # Schedule and start watching
            self._observer.schedule(watcher, abs_path, recursive=True)
            self._watchers.append(watcher)
            self._watched_dirs.add(directory)

            print(f"[DynamicSkillLoader] Watching {abs_path} (watchdog)")

        if not self._observer.is_alive():
            self._observer.start()

    def _start_polling_watcher(self, directories: list[str]) -> None:
        """Start the polling-based watcher."""
        self._polling_watcher = PollingSkillWatcher(
            skill_manager=self.skill_manager,
            directories=directories,
            on_skill_added=self._on_skill_added,
            on_skill_removed=self._on_skill_removed,
            on_skill_changed=self._on_skill_reloaded,
            poll_interval=self.poll_interval,
        )
        self._polling_watcher.start()

        for directory in directories:
            abs_path = os.path.abspath(directory)
            print(f"[DynamicSkillLoader] Watching {abs_path} (polling)")

    def stop(self) -> None:
        """Stop watching for changes."""
        # Stop watchdog observer
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None

        # Stop polling watcher
        if self._polling_watcher:
            self._polling_watcher.stop()
            self._polling_watcher = None

        self._watchers.clear()
        self._watched_dirs.clear()

        print("[DynamicSkillLoader] Stopped watching")

    def _on_skill_added(self, name: str, skill: Skill) -> None:
        """Internal handler for skill added."""
        print(f"[DynamicSkillLoader] Skill added: {name}")
        if self.on_skill_added:
            self.on_skill_added(name, skill)

    def _on_skill_removed(self, name: str) -> None:
        """Internal handler for skill removed."""
        print(f"[DynamicSkillLoader] Skill removed: {name}")

        # Disable the skill if enabled
        if self.skill_manager.is_enabled(name):
            asyncio.create_task(self.skill_manager.disable(name))

        # Unregister from registry
        self.skill_manager.registry.unregister(name)

        if self.on_skill_removed:
            self.on_skill_removed(name)

    def _on_skill_reloaded(self, name: str, skill: Skill) -> None:
        """Internal handler for skill reloaded."""
        print(f"[DynamicSkillLoader] Skill reloaded: {name}")

        # Check if skill was enabled
        was_enabled = self.skill_manager.is_enabled(name)

        # Disable old version if enabled
        if was_enabled:
            asyncio.create_task(self.skill_manager.disable(name))

        # Unregister old version
        self.skill_manager.registry.unregister(name)

        # Register new version
        self.skill_manager.registry.register(skill)

        # Re-enable if it was enabled
        if was_enabled:
            asyncio.create_task(self.skill_manager.enable(name))

        if self.on_skill_reloaded:
            self.on_skill_reloaded(name, skill)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
        return False


class SkillReloader:
    """Standalone skill reloader - handles the core reload logic.

    This class encapsulates the actual skill reload logic, separating it from
    the event handling in SkillDirectoryWatcher. This allows both the watcher
    and HotReloadManager to use the same reload logic without violating encapsulation.

    Example:
        ```python
        reloader = SkillReloader(skill_manager)

        # Reload a skill by name
        success = await reloader.reload("my_skill")

        # Reload a skill by path
        success = await reloader.reload_by_path("/path/to/skill")
        ```
    """

    def __init__(self, skill_manager: SkillManager):
        """Initialize the skill reloader.

        Args:
            skill_manager: The skill manager instance
        """
        self.skill_manager = skill_manager

    async def reload(self, name: str) -> bool:
        """Reload a skill by name.

        This method handles the complete reload process:
        1. Check if the skill exists and is enabled
        2. Disable the old version if enabled
        3. Unregister the old version
        4. Load the new version from disk
        5. Register the new version
        6. Re-enable if it was enabled

        Args:
            name: Name of the skill to reload

        Returns:
            True if reload was successful
        """
        # Get the old skill
        old_skill = self.skill_manager.registry.get(name)
        if not old_skill:
            print(f"[SkillReloader] Skill not found: {name}")
            return False

        # Check if skill was enabled
        was_enabled = self.skill_manager.is_enabled(name)

        # Get the skill path
        skill_path = getattr(old_skill, "path", None)
        if not skill_path:
            print(f"[SkillReloader] Skill {name} has no path attribute")
            return False

        print(f"[SkillReloader] Reloading skill: {name}")

        try:
            # Step 1: Disable if enabled
            if was_enabled:
                print(f"[SkillReloader] Disabling old version of {name}")
                await self.skill_manager.disable(name)

            # Step 2: Unregister old version
            print(f"[SkillReloader] Unregistering old version of {name}")
            self.skill_manager.registry.unregister(name)

            # Step 3: Load new version
            print(f"[SkillReloader] Loading new version of {name}")
            success = await self.skill_manager._load_skill(str(skill_path))
            if not success:
                raise RuntimeError(f"Failed to load skill from {skill_path}")

            # Step 4: Re-enable if it was enabled
            if was_enabled:
                print(f"[SkillReloader] Re-enabling {name}")
                await self.skill_manager.enable(name)

            print(f"[SkillReloader] Successfully reloaded skill: {name}")
            return True

        except Exception as e:
            print(f"[SkillReloader] Error reloading skill {name}: {e}")
            return False

    async def reload_by_path(self, path: str) -> bool:
        """Reload a skill by its directory path.

        This is useful when you know the path but not necessarily the name,
        such as when handling file system events.

        Args:
            path: Path to the skill directory

        Returns:
            True if reload was successful
        """
        import yaml
        from pathlib import Path

        # Try to read skill.yaml to get the name
        skill_yaml_path = Path(path) / "skill.yaml"
        if not skill_yaml_path.exists():
            print(f"[SkillReloader] No skill.yaml found at {path}")
            return False

        try:
            with open(skill_yaml_path, "r", encoding="utf-8") as f:
                skill_def = yaml.safe_load(f)
            name = skill_def.get("name")
            if not name:
                print(f"[SkillReloader] No name in skill.yaml at {path}")
                return False
        except Exception as e:
            print(f"[SkillReloader] Error reading skill.yaml at {path}: {e}")
            return False

        # Now reload by name
        return await self.reload(name)


class HotReloadManager:
    """High-level manager for hot-reloading skills during development.

    This class provides a simple interface for managing skill hot-reload
    during development sessions. It handles common patterns like:
    - Batch reloading multiple skills
    - Providing status updates
    - Graceful error handling

    This implementation uses the SkillReloader internally, avoiding
    the encapsulation violation of directly calling watcher methods.

    Example:
        ```python
        manager = HotReloadManager(skill_manager)

        # Start monitoring
        await manager.start(["./skills"])

        # Later, manually trigger reload
        success = await manager.reload_skill("weather_skill")

        # Get status
        status = manager.get_status()
        print(f"Watching: {status['watched_dirs']}")
        print(f"Active reloads: {status['active_reloads']}")

        # Stop monitoring
        await manager.stop()
        ```
    """

    def __init__(
        self,
        skill_manager: SkillManager,
        on_reload_start: Optional[Callable[[str], None]] = None,
        on_reload_complete: Optional[Callable[[str, bool], None]] = None,
        on_reload_error: Optional[Callable[[str, Exception], None]] = None,
    ):
        """Initialize the hot-reload manager.

        Args:
            skill_manager: The skill manager instance
            on_reload_start: Called when reload starts: (skill_name) -> None
            on_reload_complete: Called when reload completes: (skill_name, success) -> None
            on_reload_error: Called when reload fails: (skill_name, error) -> None
        """
        self.skill_manager = skill_manager
        self._skill_reloader = SkillReloader(skill_manager)
        self.on_reload_start = on_reload_start
        self.on_reload_complete = on_reload_complete
        self.on_reload_error = on_reload_error

        self._dynamic_loader: Optional[DynamicSkillLoader] = None
        self._watched_dirs: list[str] = []
        self._active_reloads: set[str] = set()
        self._reload_history: list[dict] = []

    async def start(self, directories: list[str]) -> None:
        """Start watching directories for changes.

        Args:
            directories: List of directories to watch
        """
        if self._dynamic_loader is not None:
            return  # Already started

        self._watched_dirs = directories.copy()

        self._dynamic_loader = DynamicSkillLoader(
            skill_manager=self.skill_manager,
            on_skill_added=self._handle_skill_added,
            on_skill_removed=self._handle_skill_removed,
            on_skill_reloaded=self._handle_skill_reloaded,
        )

        self._dynamic_loader.watch(directories)

    async def stop(self) -> None:
        """Stop watching directories."""
        if self._dynamic_loader:
            self._dynamic_loader.stop()
            self._dynamic_loader = None

    async def reload_skill(self, name: str) -> bool:
        """Manually trigger reload of a specific skill.

        This method uses the SkillReloader internally, avoiding the
        encapsulation violation of directly calling watcher methods.

        Args:
            name: Name of the skill to reload

        Returns:
            True if reload was successful
        """
        if name in self._active_reloads:
            return False  # Already reloading

        self._active_reloads.add(name)

        try:
            if self.on_reload_start:
                self.on_reload_start(name)

            # Use SkillReloader instead of directly calling watcher methods
            success = await self._skill_reloader.reload(name)

            if self.on_reload_complete:
                self.on_reload_complete(name, success)

        except Exception as e:
            success = False
            if self.on_reload_error:
                self.on_reload_error(name, e)
            if self.on_reload_complete:
                self.on_reload_complete(name, False)

        finally:
            self._active_reloads.discard(name)
            self._reload_history.append(
                {
                    "skill": name,
                    "success": success,
                    "timestamp": asyncio.get_event_loop().time(),
                }
            )

    def get_status(self) -> dict:
        """Get current status of the hot-reload manager.

        Returns:
            Dictionary with status information
        """
        return {
            "is_running": self._dynamic_loader is not None,
            "watched_dirs": self._watched_dirs.copy(),
            "active_reloads": list(self._active_reloads),
            "reload_history": self._reload_history[-10:],  # Last 10 reloads
            "loader_type": (
                "polling"
                if self._dynamic_loader and self._dynamic_loader.use_polling
                else "watchdog"
            )
            if self._dynamic_loader
            else "none",
        }

    def _handle_skill_added(self, name: str, skill) -> None:
        """Internal handler for skill added."""
        print(f"[HotReloadManager] Skill added: {name}")

    def _handle_skill_removed(self, name: str) -> None:
        """Internal handler for skill removed."""
        print(f"[HotReloadManager] Skill removed: {name}")

    def _handle_skill_reloaded(self, name: str, skill) -> None:
        """Internal handler for skill reloaded."""
        print(f"[HotReloadManager] Skill reloaded: {name}")
