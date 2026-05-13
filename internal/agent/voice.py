from __future__ import annotations

import logging
import asyncio
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
import socket
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

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
        self._ready: bool | None = None
        self._startup_process: subprocess.Popen[str] | None = None

    async def ensure_ready(self) -> bool:
        if not self.config.enabled:
            self._ready = False
            return False

        if self._ready is True and await self._is_endpoint_ready():
            return True

        if await self._is_endpoint_ready():
            self._ready = True
            return True

        if not self.config.auto_start:
            self._ready = False
            return False

        if self._startup_process is not None and self._startup_process.poll() is None:
            logging.warning("GPT-SoVITs startup is still running but endpoint is unavailable")
            self._ready = False
            return False

        if not self._start_service():
            self._ready = False
            return False

        deadline = self._current_time() + max(1, int(self.config.startup_timeout_seconds))
        while self._current_time() < deadline:
            if await self._is_endpoint_ready():
                self._ready = True
                return True
            await self._sleep(0.5)

        logging.warning("GPT-SoVITs startup timed out")
        self._ready = False
        return False

    async def synthesize(self, text: str) -> VoiceResult | None:
        if not await self.ensure_ready():
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
            self._ready = False
            return None

    async def _is_endpoint_ready(self) -> bool:
        parsed = urlparse(self.config.endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False

        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        timeout = max(1, int(self.config.health_check_timeout_seconds))
        return await asyncio.to_thread(self._check_tcp_port, parsed.hostname, port, timeout)

    def _start_service(self) -> bool:
        command = self.config.startup_command.strip()
        if not command:
            logging.warning("GPT-SoVITs auto_start is enabled but startup_command is empty")
            return False

        try:
            self._startup_process = subprocess.Popen(
                command,
                cwd=self.config.startup_cwd.strip() or None,
                shell=True,
            )
            logging.info("Started GPT-SoVITs with command: %s", command)
            return True
        except Exception as exc:
            logging.warning("Failed to start GPT-SoVITs: %s", exc, exc_info=True)
            return False

    @staticmethod
    def _current_time() -> float:
        import time

        return time.monotonic()

    @staticmethod
    async def _sleep(seconds: float) -> None:
        await asyncio.sleep(seconds)

    @staticmethod
    def _check_tcp_port(host: str, port: int, timeout: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except Exception:
            return False

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

    def position_ms(self) -> int | None:
        if self._player is None or not hasattr(self._player, "position"):
            return None
        try:
            return int(self._player.position())
        except Exception:
            return None

    def duration_ms(self) -> int | None:
        if self._player is None or not hasattr(self._player, "duration"):
            return None
        try:
            duration = int(self._player.duration())
        except Exception:
            return None
        return duration if duration > 0 else None

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
