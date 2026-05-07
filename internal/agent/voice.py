from __future__ import annotations

import logging
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiohttp

if TYPE_CHECKING:
    from internal.config.config import VoiceConfig


@dataclass(slots=True)
class VoiceResult:
    file_path: str
    duration_ms: int | None = None


class GPTSoVITSVoiceClient:
    """Small client for the common GPT-SoVITs /tts HTTP API."""

    def __init__(self, config: VoiceConfig) -> None:
        self.config = config

    async def synthesize(self, text: str) -> VoiceResult | None:
        if not self.config.enabled:
            return None

        clean_text = text.strip()
        if not clean_text:
            return None
        max_chars = max(0, int(self.config.max_tts_chars))
        if max_chars and len(clean_text) > max_chars:
            clean_text = clean_text[:max_chars]

        payload = self._build_payload(clean_text)
        timeout = aiohttp.ClientTimeout(total=max(1, self.config.timeout_seconds))
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                if self.config.method.upper() == "POST":
                    response_context = session.post(self.config.endpoint, json=payload)
                else:
                    response_context = session.get(self.config.endpoint, params=payload)

                async with response_context as response:
                    audio_bytes = await response.read()
                    if response.status < 200 or response.status >= 300:
                        logging.warning(
                            "GPT-SoVITs request failed with HTTP %s: %s",
                            response.status,
                            audio_bytes[:200].decode("utf-8", errors="replace"),
                        )
                        return None
                    if not audio_bytes:
                        logging.warning("GPT-SoVITs returned an empty audio response")
                        return None
                    return self._save_audio(audio_bytes, response.headers.get("Content-Type", ""))
        except Exception as exc:
            logging.warning("GPT-SoVITs voice synthesis failed: %s", exc, exc_info=True)
            return None

    def _build_payload(self, text: str) -> dict[str, Any]:
        return {
            "text": text,
            "text_lang": self.config.text_lang,
            "ref_audio_path": self.config.ref_audio_path,
            "prompt_text": self.config.prompt_text,
            "prompt_lang": self.config.prompt_lang,
            "text_split_method": self.config.text_split_method,
            "batch_size": self.config.batch_size,
            "speed_factor": self.config.speed_factor,
            "streaming_mode": self.config.streaming_mode,
        }

    def _save_audio(self, audio_bytes: bytes, content_type: str) -> VoiceResult:
        suffix = ".wav"
        if "mpeg" in content_type or "mp3" in content_type:
            suffix = ".mp3"
        elif "ogg" in content_type:
            suffix = ".ogg"

        temp_file = tempfile.NamedTemporaryFile(prefix="live2oder-voice-", suffix=suffix, delete=False)
        file_path = temp_file.name
        try:
            temp_file.write(audio_bytes)
        finally:
            temp_file.close()
        del audio_bytes

        duration_ms = _read_wav_duration_ms(file_path) if suffix == ".wav" else None
        return VoiceResult(file_path=file_path, duration_ms=duration_ms)


class QtAudioPlayer:
    """Plays one temporary audio file at a time through QtMultimedia."""

    def __init__(self, volume: float = 1.0) -> None:
        self.volume = volume
        self._player: Any | None = None
        self._audio_output: Any | None = None
        self._current_file: str | None = None
        self._available = True
        try:
            from PySide6.QtCore import QUrl
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        except Exception as exc:
            logging.warning("QtMultimedia is unavailable; voice playback disabled: %s", exc)
            self._available = False
            self._qurl = None
            self._audio_output_type = None
            self._player_type = None
            return

        self._qurl = QUrl
        self._audio_output_type = QAudioOutput
        self._player_type = QMediaPlayer

    def play(self, file_path: str) -> bool:
        if not self._available or self._player_type is None or self._audio_output_type is None or self._qurl is None:
            delete_file(file_path)
            return False

        try:
            self.stop()
            player = self._player_type()
            audio_output = self._audio_output_type()
            audio_output.setVolume(max(0.0, min(float(self.volume), 1.0)))
            player.setAudioOutput(audio_output)
            player.setSource(self._qurl.fromLocalFile(file_path))
            player.mediaStatusChanged.connect(lambda status: self._on_media_status_changed(status, file_path))

            self._player = player
            self._audio_output = audio_output
            self._current_file = file_path
            player.play()
            return True
        except Exception as exc:
            logging.warning("Failed to start voice playback: %s", exc, exc_info=True)
            self._player = None
            self._audio_output = None
            self._current_file = None
            delete_file(file_path)
            return False

    def stop(self) -> None:
        if self._player is not None:
            self._player.stop()
        if self._current_file is not None:
            delete_file(self._current_file)
        self._player = None
        self._audio_output = None
        self._current_file = None

    def dispose(self) -> None:
        self.stop()

    def _on_media_status_changed(self, status: Any, file_path: str) -> None:
        if self._player_type is None:
            return
        end_status = getattr(self._player_type.MediaStatus, "EndOfMedia", None)
        invalid_status = getattr(self._player_type.MediaStatus, "InvalidMedia", None)
        if status not in {end_status, invalid_status}:
            return
        if self._current_file == file_path:
            self._player = None
            self._audio_output = None
            self._current_file = None
        delete_file(file_path)


def _read_wav_duration_ms(file_path: str) -> int | None:
    try:
        with wave.open(file_path, "rb") as wav_file:
            frames = wav_file.getnframes()
            frame_rate = wav_file.getframerate()
            if frame_rate <= 0:
                return None
            return int((frames / frame_rate) * 1000)
    except Exception:
        return None


def delete_file(file_path: str) -> None:
    try:
        Path(file_path).unlink(missing_ok=True)
    except Exception as exc:
        logging.debug("Failed to delete temporary voice file %s: %s", file_path, exc)


def cleanup_voice_temp_files() -> int:
    deleted = 0
    temp_dir = Path(tempfile.gettempdir())
    for path in temp_dir.glob("live2oder-voice-*"):
        try:
            if path.is_file():
                path.unlink(missing_ok=True)
                deleted += 1
        except Exception as exc:
            logging.debug("Failed to cleanup voice temp file %s: %s", path, exc)
    return deleted
