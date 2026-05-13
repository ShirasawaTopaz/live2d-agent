import asyncio

from internal.agent.voice import GPTSoVITSVoiceClient
from internal.config.config import VoiceConfig


def test_ensure_ready_returns_true_when_endpoint_is_available(monkeypatch):
    client = GPTSoVITSVoiceClient(VoiceConfig(enabled=True))
    monkeypatch.setattr(client, "_is_endpoint_ready", lambda: asyncio.sleep(0, result=True))

    assert asyncio.run(client.ensure_ready()) is True


def test_ensure_ready_starts_service_and_waits_for_availability(monkeypatch):
    client = GPTSoVITSVoiceClient(
        VoiceConfig(
            enabled=True,
            auto_start=True,
            startup_command="python serve.py",
            startup_timeout_seconds=2,
        )
    )
    checks = {"count": 0}

    async def fake_is_endpoint_ready():
        checks["count"] += 1
        return checks["count"] >= 2

    monkeypatch.setattr(client, "_is_endpoint_ready", fake_is_endpoint_ready)
    monkeypatch.setattr(client, "_start_service", lambda: True)

    assert asyncio.run(client.ensure_ready()) is True
    assert checks["count"] >= 2


def test_ensure_ready_does_not_start_duplicate_process(monkeypatch):
    client = GPTSoVITSVoiceClient(
        VoiceConfig(
            enabled=True,
            auto_start=True,
            startup_command="python serve.py",
            startup_timeout_seconds=1,
        )
    )
    starts = {"count": 0}

    class RunningProcess:
        def poll(self):
            return None

    monkeypatch.setattr(client, "_is_endpoint_ready", lambda: asyncio.sleep(0, result=False))
    monkeypatch.setattr(client, "_sleep", lambda _seconds: asyncio.sleep(0))
    times = iter([100.0, 102.0])
    monkeypatch.setattr(client, "_current_time", lambda: next(times, 102.0))

    def fake_start_service():
        starts["count"] += 1
        client._startup_process = RunningProcess()
        return True

    monkeypatch.setattr(client, "_start_service", fake_start_service)

    assert asyncio.run(client.ensure_ready()) is False
    assert asyncio.run(client.ensure_ready()) is False
    assert starts["count"] == 1


def test_ensure_ready_rechecks_after_cached_ready(monkeypatch):
    client = GPTSoVITSVoiceClient(VoiceConfig(enabled=True))
    client._ready = True
    checks = {"count": 0}

    async def fake_is_endpoint_ready():
        checks["count"] += 1
        return False

    monkeypatch.setattr(client, "_is_endpoint_ready", fake_is_endpoint_ready)

    assert asyncio.run(client.ensure_ready()) is False
    assert checks["count"] == 2


def test_ensure_ready_disables_voice_when_startup_fails(monkeypatch):
    client = GPTSoVITSVoiceClient(
        VoiceConfig(
            enabled=True,
            auto_start=True,
            startup_command="python serve.py",
            startup_timeout_seconds=1,
        )
    )

    monkeypatch.setattr(client, "_is_endpoint_ready", lambda: asyncio.sleep(0, result=False))
    monkeypatch.setattr(client, "_start_service", lambda: False)

    assert asyncio.run(client.ensure_ready()) is False
    assert asyncio.run(client.synthesize("hello")) is None
