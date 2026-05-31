"""Unit tests for trigger implementations."""

import asyncio
import time
import pytest
from internal.scheduler.types import Event
from internal.scheduler.triggers import CronTrigger


class TestCronTrigger:
    """Tests for CronTrigger."""

    def test_parse_cron_fields(self):
        trigger = CronTrigger(cron_expr="0 9 * * *")
        assert trigger.cron_expr == "0 9 * * *"

    def test_parse_every_30_minutes(self):
        trigger = CronTrigger(cron_expr="*/30 * * * *")
        assert trigger.cron_expr == "*/30 * * * *"

    def test_one_shot_timestamp(self):
        future = time.time() + 1
        trigger = CronTrigger(run_at=future)
        assert trigger.run_at == future
        assert trigger.cron_expr is None

    def test_next_fire_one_shot(self):
        future = time.time() + 10
        trigger = CronTrigger(run_at=future)
        next_fire = trigger._next_fire()
        assert next_fire is not None
        assert abs(next_fire - future) < 1.0

    def test_next_fire_every_minute(self):
        trigger = CronTrigger(cron_expr="* * * * *")
        now = time.time()
        next_fire = trigger._next_fire()
        assert next_fire is not None
        assert next_fire > now
        assert next_fire <= now + 60

    @pytest.mark.asyncio
    async def test_fires_and_stops(self):
        trigger = CronTrigger(run_at=time.time() + 0.1)
        events: list[Event] = []

        async def collect(event: Event):
            events.append(event)

        await trigger.start(collect)
        await asyncio.sleep(0.3)
        await trigger.stop()

        assert len(events) == 1
        assert events[0].source == "cron"

    @pytest.mark.asyncio
    async def test_stop_without_start_does_not_crash(self):
        trigger = CronTrigger(run_at=time.time())
        await trigger.stop()
