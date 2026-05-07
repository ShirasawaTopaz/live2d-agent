import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from internal.agent.bubble_timing import BubbleTimingController, calculate_bubble_duration
from internal.agent import voice
from internal.agent.voice import VoiceResult


class FakeBubbleWidget:
    def __init__(self):
        self.text = ""
        self.duration = None

    def clear(self):
        return None

    def set_text(self, text):
        self.text = text

    def show_with_duration(self, duration):
        self.duration = duration


class FakeVoiceClient:
    def __init__(self, result):
        self.result = result
        self.texts = []

    async def synthesize(self, text):
        self.texts.append(text)
        return self.result


class FakeAudioPlayer:
    def __init__(self):
        self.played = []

    def play(self, file_path):
        self.played.append(file_path)
        return True


class RejectingAudioPlayer:
    def play(self, _file_path):
        return False


def test_calculate_bubble_duration_applies_minimum_weighting_and_maximum():
    assert calculate_bubble_duration("") == 5000
    assert calculate_bubble_duration("hello") == 5000
    assert calculate_bubble_duration("中" * 40) > calculate_bubble_duration("a" * 40)
    assert calculate_bubble_duration("a" * 1000) == 30000


def test_wait_for_bubble_interval_uses_previous_bubble_end_time():
    controller = BubbleTimingController(time_provider=lambda: 12.0)
    controller.last_bubble_time = 10.0
    controller.last_bubble_duration = 5000

    assert abs(controller.wait_for_bubble_interval(5000) - 3.0) < 1e-9


async def _run_send_single_bubble_parses_json_and_updates_state():
    sent_payloads = []

    async def fake_sender(_ws, _msg, _msg_id, data):
        sent_payloads.append(data)

    controller = BubbleTimingController(
        time_provider=lambda: 42.0,
        sender=fake_sender,
    )

    await controller.send_single_bubble(
        '{"data":{"id":7,"text":"Hello world","textColor":12345}}',
        object(),
        None,
    )

    assert len(sent_payloads) == 2
    expression_payload = sent_payloads[0]
    assert expression_payload.id == 7

    payload = sent_payloads[1]
    assert payload.id == 7
    assert payload.text == "Hello world"
    assert payload.textColor == 12345
    assert payload.duration == 5000
    assert controller.last_bubble_time == 42.0
    assert controller.last_bubble_duration == 5000


def test_send_single_bubble_parses_json_and_updates_state():
    asyncio.run(_run_send_single_bubble_parses_json_and_updates_state())


async def _run_send_stream_chunk_rotates_expression_once_per_bubble():
    sent_payloads = []

    async def fake_sender(_ws, _msg, _msg_id, data):
        sent_payloads.append(data)

    controller = BubbleTimingController(sender=fake_sender)

    await controller.send_stream_chunk(
        "Hello",
        5000,
        object(),
        None,
        first_chunk=True,
    )
    await controller.send_stream_chunk(
        "Hello world",
        5000,
        object(),
        None,
        first_chunk=False,
    )

    assert len(sent_payloads) == 3
    assert sent_payloads[0].id == 0
    assert sent_payloads[1].text == "Hello"
    assert sent_payloads[2].text == "Hello world"


def test_send_stream_chunk_rotates_expression_once_per_bubble():
    asyncio.run(_run_send_stream_chunk_rotates_expression_once_per_bubble())


async def _run_display_text_forwards_choices_to_websocket():
    sent_payloads = []

    async def fake_sender(_ws, _msg, _msg_id, data):
        sent_payloads.append(data)

    controller = BubbleTimingController(sender=fake_sender)

    await controller.display_text(
        "Pick one",
        object(),
        None,
        choices=["A", "B"],
        rotate_expression=False,
    )

    assert len(sent_payloads) == 1
    assert sent_payloads[0].choices == ["A", "B"]


def test_display_text_forwards_choices_to_websocket():
    asyncio.run(_run_display_text_forwards_choices_to_websocket())


async def _run_display_text_uses_voice_duration_for_qt_bubble():
    voice_client = FakeVoiceClient(VoiceResult(file_path="voice.wav", duration_ms=9000))
    audio_player = FakeAudioPlayer()
    widget = FakeBubbleWidget()
    controller = BubbleTimingController(time_provider=lambda: 7.0, voice_client=voice_client)
    controller.set_audio_player(audio_player)

    duration = await controller.display_text("hello", object(), widget, duration=5000, rotate_expression=False)

    assert duration == 9000
    assert widget.text == "hello"
    assert widget.duration == 9000
    assert controller.last_bubble_time == 7.0
    assert controller.last_bubble_duration == 9000
    assert voice_client.texts == ["hello"]
    assert audio_player.played == ["voice.wav"]


def test_display_text_uses_voice_duration_for_qt_bubble():
    asyncio.run(_run_display_text_uses_voice_duration_for_qt_bubble())


async def _run_display_text_falls_back_when_voice_fails():
    voice_client = FakeVoiceClient(None)
    widget = FakeBubbleWidget()
    controller = BubbleTimingController(voice_client=voice_client)

    duration = await controller.display_text("hello", object(), widget, duration=5000, rotate_expression=False)

    assert duration == 5000
    assert widget.duration == 5000


def test_display_text_falls_back_when_voice_fails():
    asyncio.run(_run_display_text_falls_back_when_voice_fails())


async def _run_display_text_skips_voice_without_audio_player(file_path: str):
    voice_client = FakeVoiceClient(VoiceResult(file_path=file_path, duration_ms=9000))
    widget = FakeBubbleWidget()
    controller = BubbleTimingController(voice_client=voice_client)

    duration = await controller.display_text("hello", object(), widget, duration=5000, rotate_expression=False)

    assert duration == 5000
    assert voice_client.texts == []
    assert Path(file_path).exists()


def test_display_text_skips_voice_without_audio_player(tmp_path):
    voice_file = tmp_path / "voice.wav"
    voice_file.write_bytes(b"fake")

    asyncio.run(_run_display_text_skips_voice_without_audio_player(str(voice_file)))


def test_save_audio_skips_wav_duration_for_mp3(monkeypatch):
    def fail_if_called(_file_path):
        raise AssertionError("WAV duration reader should not be called for MP3 audio")

    monkeypatch.setattr(voice, "_read_wav_duration_ms", fail_if_called)
    client = voice.GPTSoVITSVoiceClient.__new__(voice.GPTSoVITSVoiceClient)

    result = client._save_audio(b"fake mp3", "audio/mpeg")
    try:
        assert result.file_path.endswith(".mp3")
        assert result.duration_ms is None
    finally:
        voice.delete_file(result.file_path)


async def _run_display_text_deletes_voice_file_when_player_rejects(file_path: str):
    voice_client = FakeVoiceClient(VoiceResult(file_path=file_path, duration_ms=9000))
    widget = FakeBubbleWidget()
    controller = BubbleTimingController(voice_client=voice_client)
    controller.set_audio_player(RejectingAudioPlayer())

    await controller.display_text("hello", object(), widget, duration=5000, rotate_expression=False)

    assert not Path(file_path).exists()


def test_display_text_deletes_voice_file_when_player_rejects(tmp_path):
    voice_file = tmp_path / "voice.wav"
    voice_file.write_bytes(b"fake")

    asyncio.run(_run_display_text_deletes_voice_file_when_player_rejects(str(voice_file)))


def test_cleanup_voice_temp_files_deletes_only_voice_files(tmp_path, monkeypatch):
    voice_file = tmp_path / "live2oder-voice-old.wav"
    other_file = tmp_path / "other.wav"
    voice_file.write_bytes(b"voice")
    other_file.write_bytes(b"other")
    monkeypatch.setattr(voice.tempfile, "gettempdir", lambda: str(tmp_path))

    assert voice.cleanup_voice_temp_files() == 1
    assert not voice_file.exists()
    assert other_file.exists()
