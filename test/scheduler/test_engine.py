"""Integration tests for SchedulerEngine."""

import asyncio
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock
import pytest
from internal.scheduler.types import CronTask, PollingTask
from internal.scheduler.store import TaskStore
from internal.scheduler.notification import NotificationManager


class TestSchedulerEngine:
    def setup_method(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = TaskStore(data_dir=self.temp_dir.name)
        self.notifier = NotificationManager()

    def teardown_method(self):
        self.temp_dir.cleanup()

    @pytest.mark.asyncio
    async def test_add_and_list_tasks(self):
        from internal.scheduler.engine import SchedulerEngine
        await self.store.init()
        engine = SchedulerEngine(store=self.store, notification=self.notifier, agent=None)
        task = CronTask(task_id="t1", prompt="test", run_at=time.time() + 3600)
        await engine.add(task)
        tasks = await engine.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].task_id == "t1"

    @pytest.mark.asyncio
    async def test_remove_task(self):
        from internal.scheduler.engine import SchedulerEngine
        await self.store.init()
        engine = SchedulerEngine(store=self.store, notification=self.notifier, agent=None)
        task = CronTask(task_id="t1", prompt="test", run_at=time.time() + 3600)
        await engine.add(task)
        assert await engine.remove("t1") is True
        assert await engine.remove("t1") is False

    @pytest.mark.asyncio
    async def test_pause_and_resume(self):
        from internal.scheduler.engine import SchedulerEngine
        await self.store.init()
        engine = SchedulerEngine(store=self.store, notification=self.notifier, agent=None)
        task = CronTask(task_id="t1", prompt="test", run_at=time.time() + 3600)
        await engine.add(task)
        await engine.pause("t1")
        tasks = await engine.list_tasks()
        assert tasks[0].enabled is False
        await engine.resume("t1")
        tasks = await engine.list_tasks()
        assert tasks[0].enabled is True

    @pytest.mark.asyncio
    async def test_task_fires_and_executes(self):
        from internal.scheduler.engine import SchedulerEngine
        await self.store.init()
        mock_agent = MagicMock()
        mock_agent.chat = AsyncMock(return_value={"content": "task done"})
        mock_agent.memory = MagicMock()
        mock_agent.memory.new_session = AsyncMock()
        mock_agent.memory.add_message = MagicMock()
        mock_agent.memory.get_current_messages = AsyncMock(return_value=[])
        engine = SchedulerEngine(store=self.store, notification=self.notifier, agent=mock_agent)
        task = CronTask(task_id="fast", prompt="say hello", run_at=time.time() + 0.2)
        await engine.add(task)
        await asyncio.sleep(0.5)
        tasks = await engine.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].last_fired_at is not None
        await engine.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_stops_all_triggers(self):
        from internal.scheduler.engine import SchedulerEngine
        await self.store.init()
        engine = SchedulerEngine(store=self.store, notification=self.notifier, agent=None)
        await engine.add(CronTask(task_id="t1", prompt="a", run_at=time.time() + 3600))
        await engine.add(PollingTask(task_id="t2", prompt="b", interval=3600))
        await engine.shutdown()
