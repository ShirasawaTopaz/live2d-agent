"""Tests for dynamic skill loader."""

import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from internal.skill import SkillManager
from internal.skill.dynamic_loader import (
    DynamicSkillLoader,
    PollingSkillWatcher,
    SkillDirectoryWatcher,
)


class TestPollingWatcher(unittest.TestCase):
    """Test polling-based watcher."""

    def setUp(self):
        """Create temporary directory for skills."""
        self.temp_dir = tempfile.mkdtemp()
        self.skill_manager = SkillManager(
            skill_dirs=[self.temp_dir],
            prompt_manager=None,
            tool_registry=None,
        )

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_polling_detects_new_skill(self):
        """Test that polling detects a new skill."""
        events = []

        def on_added(name, skill):
            events.append(("added", name))

        watcher = PollingSkillWatcher(
            skill_manager=self.skill_manager,
            directories=[self.temp_dir],
            on_skill_added=on_added,
            poll_interval=0.1,
        )

        watcher.start()

        try:
            # Wait a bit for initial scan
            time.sleep(0.2)

            # Create a new skill
            skill_dir = os.path.join(self.temp_dir, "test_skill")
            os.makedirs(skill_dir)
            with open(os.path.join(skill_dir, "skill.yaml"), "w") as f:
                f.write("""
name: test_skill
version: 1.0.0
description: Test skill
author: Test
""")

            # Wait for polling to detect
            time.sleep(0.3)

            # Check events
            self.assertTrue(
                any(e[0] == "added" and e[1] == "test_skill" for e in events)
            )

        finally:
            watcher.stop()


class TestDynamicSkillLoader(unittest.TestCase):
    """Test dynamic skill loader."""

    def setUp(self):
        """Create temporary directory for skills."""
        self.temp_dir = tempfile.mkdtemp()
        self.skill_manager = SkillManager(
            skill_dirs=[self.temp_dir],
            prompt_manager=None,
            tool_registry=None,
        )

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_loader_creation(self):
        """Test creating dynamic loader."""
        loader = DynamicSkillLoader(
            skill_manager=self.skill_manager,
            use_polling=True,
        )
        self.assertIsNotNone(loader)

    def test_start_stop_polling(self):
        """Test starting and stopping polling watcher."""
        loader = DynamicSkillLoader(
            skill_manager=self.skill_manager,
            use_polling=True,
            poll_interval=1.0,
        )

        loader.watch([self.temp_dir])
        self.assertIsNotNone(loader._polling_watcher)

        loader.stop()
        self.assertIsNone(loader._polling_watcher)


class TestSkillDirectoryWatcher(unittest.TestCase):
    """Test skill directory watcher."""

    def setUp(self):
        """Create temporary directory for skills."""
        self.temp_dir = tempfile.mkdtemp()
        self.skill_manager = SkillManager(
            skill_dirs=[self.temp_dir],
            prompt_manager=None,
            tool_registry=None,
        )

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_watcher_creation(self):
        """Test creating watcher."""
        watcher = SkillDirectoryWatcher(
            skill_manager=self.skill_manager,
        )
        self.assertIsNotNone(watcher)


if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2)
