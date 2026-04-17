import asyncio
from types import SimpleNamespace

from internal.app.runtime import QueueRuntimeCoordinator


class StubWebSocket:
    def __init__(self) -> None:
        self.started_with = None
        self.task = asyncio.create_task(asyncio.sleep(3600))

    def start_receive_loop(self, receive_queue):
        self.started_with = receive_queue
        return self.task


async def _wait_for(predicate, *, timeout: float = 1.0) -> None:
    end = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < end:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not met before timeout")


def test_attach_creates_receive_queue_and_starts_receive_loop() -> None:
    async def scenario() -> None:
        runtime = QueueRuntimeCoordinator()
        websocket = StubWebSocket()

        runtime.attach(websocket)

        assert runtime.receive_queue is websocket.started_with
        assert runtime.receive_task is websocket.task

        await runtime.stop()

    asyncio.run(scenario())


def test_start_begins_consumption_only_after_explicit_transition() -> None:
    async def scenario() -> None:
        runtime = QueueRuntimeCoordinator()
        runtime.receive_queue = asyncio.Queue()
        queue = runtime.receive_queue
        await queue.put(SimpleNamespace(msg="hello", msgId="1"))

        await asyncio.sleep(0)
        assert queue.qsize() == 1
        assert runtime.consume_task is None

        runtime.start()
        await _wait_for(lambda: queue.qsize() == 0)
        assert runtime.is_running is True
        assert runtime.consume_task is not None

        await runtime.stop()

    asyncio.run(scenario())


def test_stop_cancels_consumer_and_prevents_further_consumption() -> None:
    async def scenario() -> None:
        runtime = QueueRuntimeCoordinator()
        runtime.receive_queue = asyncio.Queue()
        queue = runtime.receive_queue
        runtime.start()
        await queue.put(SimpleNamespace(msg="before-stop", msgId="1"))
        await _wait_for(lambda: queue.qsize() == 0)

        consume_task = runtime.consume_task
        await runtime.stop()

        assert runtime.is_running is False
        assert runtime.consume_task is None
        assert consume_task is not None and consume_task.cancelled()

        await queue.put(SimpleNamespace(msg="after-stop", msgId="2"))
        await asyncio.sleep(0.05)
        assert queue.qsize() == 1

    asyncio.run(scenario())
