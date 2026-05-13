# Voice Scroll Sync Timing Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the timing gap where audio playback starts before scroll synchronization is established, so subtitle scrolling tracks audio from frame zero.

**Architecture:** Split `_prepare_voice` into separate `_synthesize_voice` (synthesis only) and `_start_voice_playback` (playback only) methods. In `display_text` and `finish_stream`, reorder operations so `sync_scroll_to_audio` is called before `play()`. The `_synthesize_voice` -> setup widget+sync -> `_start_voice_playback` ordering ensures no audio frame is missed by the scroll tracker.

**Tech Stack:** Python, asyncio, PySide6 Qt

---

## File Structure

| File | Responsibility | Action |
|------|---------------|--------|
| `internal/agent/bubble_timing.py` | `BubbleTimingController` — owns bubble pacing, skip rules, voice orchestration | Modify |
| `test/agent/test_bubble_timing.py` | Unit tests for `BubbleTimingController` | Modify |

---

### Task 1: Split `_prepare_voice` into synthesize and playback methods

**Files:**
- Modify: `internal/agent/bubble_timing.py:227-242`

- [ ] **Step 1: Replace `_prepare_voice` with `_synthesize_voice`, `_voice_duration`, and `_start_voice_playback`**

Replace lines 227-242 (`_prepare_voice` method) with:

```python
    async def _synthesize_voice(self, text: str) -> object | None:
        """Synthesize voice from text. Returns VoiceResult or None. Does NOT start playback."""
        if self.voice_client is None:
            return None
        if self.audio_player is None or not hasattr(self.audio_player, "play"):
            return None
        return await self.voice_client.synthesize(text)

    @staticmethod
    def _voice_duration(voice_result: object | None, text_duration: int) -> int:
        """Compute effective display duration considering voice audio length."""
        if voice_result is None:
            return text_duration
        audio_duration = getattr(voice_result, "duration_ms", None)
        if audio_duration is None:
            return text_duration
        return max(text_duration, audio_duration)

    def _start_voice_playback(self, voice_result: object) -> bool:
        """Start playing synthesized voice audio. Cleans up file on failure."""
        if self.audio_player is None or not hasattr(self.audio_player, "play"):
            return False
        played = self.audio_player.play(voice_result.file_path)
        if played is False:
            delete_file(voice_result.file_path)
        return played
```

- [ ] **Step 2: Run existing tests to confirm they fail (old `_prepare_voice` removed)**

```bash
poetry run pytest test/agent/test_bubble_timing.py -v
```

Expected: FAIL — tests that reference `_prepare_voice` will raise `AttributeError`.

---

### Task 2: Update `display_text` to reorder sync-before-playback

**Files:**
- Modify: `internal/agent/bubble_timing.py:106-124`

- [ ] **Step 1: Rewrite the Qt bubble path in `display_text` (lines 106-124)**

Replace lines 106-124 with:

```python
        display_duration = duration if duration is not None else calculate_bubble_duration(text)

        voice_result = await self._synthesize_voice(text)
        display_duration = self._voice_duration(voice_result, display_duration)

        if rotate_expression:
            await self._send_next_expression(ws, bubble_id)

        if bubble_widget is not None:
            if clear_widget:
                bubble_widget.clear()
            bubble_widget.set_text(text)
            if show_widget:
                bubble_widget.show_with_duration(display_duration)
            else:
                bubble_widget.show()
            self._sync_widget_scroll_to_audio(bubble_widget, voice_result, display_duration)
            if voice_result is not None:
                self._start_voice_playback(voice_result)
            if update_state:
                self.update_bubble_time(display_duration)
            return display_duration
```

Note: this keeps lines 126-141 (WebSocket path) unchanged.

- [ ] **Step 2: Run tests to verify no regressions (some may still fail on finish_stream)**

```bash
poetry run pytest test/agent/test_bubble_timing.py -v
```

Expected: tests related to `display_text` should pass; `finish_stream` tests may still fail.

---

### Task 3: Update `finish_stream` to reorder sync-before-playback

**Files:**
- Modify: `internal/agent/bubble_timing.py:219-225`

- [ ] **Step 1: Rewrite `finish_stream`**

Replace lines 219-225 with:

```python
    async def finish_stream(self, final_content: str, bubble_widget: BubbleWidget | None) -> None:
        final_duration = calculate_bubble_duration(final_content)

        voice_result = await self._synthesize_voice(final_content)
        final_duration = self._voice_duration(voice_result, final_duration)

        self.update_bubble_time(final_duration)
        if bubble_widget is not None:
            bubble_widget.show_with_duration(final_duration)
            self._sync_widget_scroll_to_audio(bubble_widget, voice_result, final_duration)
            if voice_result is not None:
                self._start_voice_playback(voice_result)
```

- [ ] **Step 2: Run all existing tests**

```bash
poetry run pytest test/agent/test_bubble_timing.py -v
```

Expected: all tests pass.

---

### Task 4: Add test for sync-before-playback ordering in `display_text`

**Files:**
- Modify: `test/agent/test_bubble_timing.py` (append at end)

- [ ] **Step 1: Add the ordering test**

```python
async def _run_display_text_establishes_sync_before_playback():
    call_order = []

    class SpyBubbleWidget:
        def __init__(self):
            self.text = ""
            self.duration = None
            self.audio_sync = None

        def clear(self):
            return None

        def set_text(self, text):
            self.text = text

        def show_with_duration(self, duration):
            self.duration = duration

        def show(self):
            pass

        def sync_scroll_to_audio(self, position_provider, duration_provider=None, *, duration_ms=None):
            call_order.append("sync")
            self.audio_sync = (position_provider, duration_provider, duration_ms)

    class SpyAudioPlayer:
        def __init__(self):
            self.played = []
            self.position = 0
            self.duration = 0

        def play(self, file_path):
            call_order.append("play")
            self.played.append(file_path)
            return True

        def position_ms(self):
            return self.position

        def duration_ms(self):
            return self.duration or None

    voice_client = FakeVoiceClient(VoiceResult(file_path="voice.wav", duration_ms=9000))
    widget = SpyBubbleWidget()
    audio_player = SpyAudioPlayer()
    controller = BubbleTimingController(time_provider=lambda: 7.0, voice_client=voice_client)
    controller.set_audio_player(audio_player)

    await controller.display_text("hello", object(), widget, duration=5000, rotate_expression=False)

    assert call_order == ["sync", "play"]
    assert widget.audio_sync is not None
    assert len(audio_player.played) == 1


def test_display_text_establishes_sync_before_playback():
    asyncio.run(_run_display_text_establishes_sync_before_playback())
```

- [ ] **Step 2: Run the new test**

```bash
poetry run pytest test/agent/test_bubble_timing.py::test_display_text_establishes_sync_before_playback -v
```

Expected: PASS.

---

### Task 5: Add test for sync-before-playback ordering in `finish_stream`

**Files:**
- Modify: `test/agent/test_bubble_timing.py` (append at end)

- [ ] **Step 1: Add the ordering test**

```python
async def _run_finish_stream_establishes_sync_before_playback():
    call_order = []

    class SpyBubbleWidget:
        def __init__(self):
            self.duration = None
            self.audio_sync = None

        def show_with_duration(self, duration):
            self.duration = duration

        def sync_scroll_to_audio(self, position_provider, duration_provider=None, *, duration_ms=None):
            call_order.append("sync")
            self.audio_sync = (position_provider, duration_provider, duration_ms)

    class SpyAudioPlayer:
        def __init__(self):
            self.played = []
            self.position = 0
            self.duration = 0

        def play(self, file_path):
            call_order.append("play")
            self.played.append(file_path)
            return True

        def position_ms(self):
            return self.position

        def duration_ms(self):
            return self.duration or None

    voice_client = FakeVoiceClient(VoiceResult(file_path="voice.wav", duration_ms=9000))
    widget = SpyBubbleWidget()
    audio_player = SpyAudioPlayer()
    controller = BubbleTimingController(time_provider=lambda: 7.0, voice_client=voice_client)
    controller.set_audio_player(audio_player)

    await controller.finish_stream("hello world", widget)

    assert call_order == ["sync", "play"]
    assert widget.audio_sync is not None
    assert len(audio_player.played) == 1


def test_finish_stream_establishes_sync_before_playback():
    asyncio.run(_run_finish_stream_establishes_sync_before_playback())
```

- [ ] **Step 2: Run the new test**

```bash
poetry run pytest test/agent/test_bubble_timing.py::test_finish_stream_establishes_sync_before_playback -v
```

Expected: PASS.

---

### Task 6: Run the full test suite and commit

- [ ] **Step 1: Run all bubble timing tests**

```bash
poetry run pytest test/agent/test_bubble_timing.py -v
```

Expected: all 11 tests PASS.

- [ ] **Step 2: Run the bubble widget tests (ensure no Qt-side regression)**

```bash
poetry run pytest test/ui/test_bubble_widget.py -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add internal/agent/bubble_timing.py test/agent/test_bubble_timing.py
git commit -m "fix: establish scroll sync before starting voice playback

Split _prepare_voice into _synthesize_voice and _start_voice_playback so that
BubbleWidget.sync_scroll_to_audio is called before audio_player.play(),
eliminating the timing gap where audio played without scroll tracking.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```
