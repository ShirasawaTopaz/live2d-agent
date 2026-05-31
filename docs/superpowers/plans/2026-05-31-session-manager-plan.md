# Session Manager Auto-Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build model-driven multi-session auto-routing — the Agent detects topic shifts and automatically creates/switches sessions without manual UI management.

**Architecture:** New `internal/session/` package wraps the existing `MemoryManager` session layer. `TopicClassifier` uses keyword+embedding two-tier detection. `Router` makes switching decisions. `SessionManager` orchestrates routing on each user message.

**Tech Stack:** Python 3.12+, asyncio, existing `EmbeddingGenerator` from `internal/rag/embeddings.py`, existing `MemoryManager` session API

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `internal/session/__init__.py` | Package exports |
| Create | `internal/session/types.py` | Session dataclass + ClassificationResult |
| Create | `internal/session/topic_classifier.py` | Two-layer topic detection |
| Create | `internal/session/router.py` | Switch/stay/create decisions |
| Create | `internal/session/session_store.py` | Session metadata persistence |
| Create | `internal/session/session_manager.py` | Orchestrator, wired into Agent |
| Modify | `internal/memory/_manager.py` | Add `get_session_messages()` method |
| Modify | `internal/agent/agent.py` | Wire session routing into chat flow |
| Modify | `internal/app/live2d_agent_app.py` | Initialize SessionManager on startup |
| Create | `test/session/__init__.py` | Test package marker |
| Create | `test/session/test_topic_classifier.py` | TopicClassifier unit tests |
| Create | `test/session/test_router.py` | Router unit tests |
| Create | `test/session/test_session_manager.py` | SessionManager integration tests |

---

### Task 1: Session Types

**Files:**
- Create: `internal/session/__init__.py`
- Create: `internal/session/types.py`

- [ ] **Step 1: Create `internal/session/__init__.py`**

```python
"""Session auto-routing package for Live2oder."""

from internal.session.types import Session, ClassificationResult
from internal.session.session_manager import SessionManager as SessionRouter
from internal.session.router import Router
from internal.session.topic_classifier import TopicClassifier

__all__ = [
    "Session",
    "ClassificationResult",
    "SessionRouter",
    "Router",
    "TopicClassifier",
]
```

- [ ] **Step 2: Create `internal/session/types.py`**

```python
"""Session type definitions for auto-routing system."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClassificationResult:
    """Output from TopicClassifier.classify()."""

    topic: str
    confidence: float  # 0.0 - 1.0
    suggested_session_id: str | None = None
    # None means no existing session matched — router should create new


@dataclass
class Session:
    """Session metadata for auto-routing.

    This is separate from memory._types.SessionInfo.
    SessionInfo is the storage-layer record.
    Session is the routing-layer record with additional fields
    needed for topic classification and context switching.
    """

    session_id: str
    topic: str                     # Auto-identified topic label
    display_name: str              # User-editable name (defaults to topic)
    summary: str                   # 200-char session summary
    created_at: float
    last_active_at: float
    message_count: int
    context_snapshot: dict[str, Any] = field(default_factory=dict)
    # Key context variables inherited when switching from another session
    # e.g. {"language": "zh", "current_project": "live2oder", "user_name": "..."}

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "topic": self.topic,
            "display_name": self.display_name,
            "summary": self.summary,
            "created_at": self.created_at,
            "last_active_at": self.last_active_at,
            "message_count": self.message_count,
            "context_snapshot": self.context_snapshot,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        return cls(
            session_id=data["session_id"],
            topic=data.get("topic", ""),
            display_name=data.get("display_name", data.get("topic", "")),
            summary=data.get("summary", ""),
            created_at=data.get("created_at", 0.0),
            last_active_at=data.get("last_active_at", 0.0),
            message_count=data.get("message_count", 0),
            context_snapshot=data.get("context_snapshot", {}),
        )
```

- [ ] **Step 3: Commit**

```bash
git add internal/session/__init__.py internal/session/types.py
git commit -m "feat(session): add session types and package init"
```

---

### Task 2: Topic Classifier

**Files:**
- Create: `internal/session/topic_classifier.py`
- Create: `test/session/__init__.py`
- Create: `test/session/test_topic_classifier.py`

- [ ] **Step 1: Create test file `test/session/__init__.py`**

```python
"""Tests for session auto-routing module."""
```

- [ ] **Step 2: Write tests for TopicClassifier in `test/session/test_topic_classifier.py`**

```python
"""Unit tests for TopicClassifier."""

import pytest
from internal.session.topic_classifier import TopicClassifier


class TestTopicClassifierKeywordLayer:
    """Tests for layer 1: keyword matching."""

    def setup_method(self):
        self.classifier = TopicClassifier(embedding_model=None)

    def test_coding_keyword(self):
        result = self.classifier.classify_keywords("帮我写一个Python脚本")
        assert result is not None
        assert result["topic"] == "coding"
        assert result["confidence"] >= 0.8

    def test_translation_keyword(self):
        result = self.classifier.classify_keywords("帮我把这段英文翻译成中文")
        assert result is not None
        assert result["topic"] == "translation"
        assert result["confidence"] >= 0.8

    def test_casual_keyword(self):
        result = self.classifier.classify_keywords("今天天气不错")
        assert result is not None
        assert result["topic"] == "casual"
        assert result["confidence"] >= 0.8

    def test_no_keyword_match(self):
        result = self.classifier.classify_keywords("量子力学中的纠缠现象如何解释")
        assert result is None

    def test_empty_input(self):
        result = self.classifier.classify_keywords("")
        assert result is None

    def test_very_short_input(self):
        result = self.classifier.classify_keywords("好")
        assert result is None


class TestTopicClassifierConfidenceThreshold:
    """Tests for confidence threshold behavior."""

    def setup_method(self):
        self.classifier = TopicClassifier(embedding_model=None)

    def test_below_threshold(self):
        result = self.classifier.classify("今天天气不错", sessions=[])
        assert result.confidence > 0.8
        assert result.topic == "casual"

    def test_above_threshold_with_match(self):
        sessions = [
            type("_S", (), {"session_id": "s1", "summary": "编程相关讨论", "topic": "coding"})(),
        ]
        # Without embeddings, falls back to keyword match
        result = self.classifier.classify("帮我写代码", sessions=sessions)
        assert result.confidence >= 0.8
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd D:/Source/live2oder && poetry run pytest test/session/test_topic_classifier.py -v
```
Expected: FAIL (module not found)

- [ ] **Step 4: Implement `internal/session/topic_classifier.py`**

```python
"""Two-layer topic classifier for session auto-routing.

Layer 1 (fast): keyword/regex matching against built-in and user-defined rules.
Layer 2 (fallback): embedding similarity against existing session summaries.

The embedding layer reuses internal.rag.embeddings.EmbeddingGenerator
for zero additional model dependencies.
"""

import logging
import re
import time
from typing import TYPE_CHECKING

from internal.session.types import ClassificationResult, Session

if TYPE_CHECKING:
    from internal.rag.embeddings import EmbeddingGenerator

logger = logging.getLogger(__name__)

# ── Layer 1: Keyword → Topic rules ──────────────────────────────

KEYWORD_TOPIC_MAP: list[tuple[str, str]] = [
    # (regex pattern, topic_label)
    (r"(写|帮我写|编写|写个|写一段).*(代码|脚本|程序|函数|类|API)", "coding"),
    (r"(debug|调试|报错|bug|错误|异常|修复)", "coding"),
    (r"(翻译|translate|翻一下|译成)", "translation"),
    (r"(总结|summary|summarize|概括|归纳|摘要)", "summarization"),
    (r"(天气|今天.*天|明天.*天|气温)", "casual"),
    (r"(搜索|search|查一下|帮我查|搜一下)", "search"),
    (r"(学习|learn|教程|怎么学|入门|新手|教教)", "learning"),
    (r"(待办|todo|提醒|计划|安排|日程)", "planning"),
    (r"(写作|write|写一篇文章|写一篇|写个故事|写首诗)", "writing"),
    (r"(分析|analyze|数据|统计|图表)", "analysis"),
]

_compiled_rules: list[tuple[re.Pattern[str], str]] = []


def _get_rules() -> list[tuple[re.Pattern[str], str]]:
    global _compiled_rules
    if not _compiled_rules:
        _compiled_rules = [(re.compile(p, re.IGNORECASE), t) for p, t in KEYWORD_TOPIC_MAP]
    return _compiled_rules


class TopicClassifier:
    """Detect conversation topic from user input.

    Uses a two-layer approach:
    1. Fast keyword/regex matching (always available, no dependencies)
    2. Embedding similarity fallback (requires EmbeddingGenerator)
    """

    EMBEDDING_CONFIDENCE = 0.7
    KEYWORD_CONFIDENCE = 0.85
    SIMILARITY_THRESHOLD = 0.6  # Cosine similarity below this = new topic

    def __init__(self, embedding_model: "EmbeddingGenerator | None" = None):
        self._embedding = embedding_model

    # ── Public API ──────────────────────────────────────────────

    def classify(self, text: str, sessions: list[Session]) -> ClassificationResult:
        """Classify text and suggest a session.

        Args:
            text: User input text.
            sessions: Existing session list (for similarity matching).

        Returns:
            ClassificationResult with topic, confidence, and optional
            suggested session_id.
        """
        # Layer 1: fast keyword match
        kw_result = self.classify_keywords(text)
        if kw_result is not None:
            topic = kw_result["topic"]
            # Try to find an existing session with matching topic
            for s in sessions:
                if s.topic == topic:
                    return ClassificationResult(
                        topic=topic,
                        confidence=self.KEYWORD_CONFIDENCE,
                        suggested_session_id=s.session_id,
                    )
            return ClassificationResult(
                topic=topic,
                confidence=self.KEYWORD_CONFIDENCE,
                suggested_session_id=None,
            )

        # Layer 2: embedding similarity fallback
        if self._embedding is not None and sessions:
            return self._classify_by_embedding(text, sessions)

        # No match, no embeddings — stay in current session
        return ClassificationResult(
            topic="general",
            confidence=0.3,
            suggested_session_id=None,
        )

    def classify_keywords(self, text: str) -> dict[str, object] | None:
        """Layer 1: keyword/regex matching.

        Returns dict with 'topic' and 'confidence' keys, or None if no match.
        """
        if not text or len(text.strip()) < 2:
            return None

        for pattern, topic in _get_rules():
            if pattern.search(text):
                logger.debug("Keyword match: topic=%s pattern=%s", topic, pattern.pattern)
                return {"topic": topic, "confidence": self.KEYWORD_CONFIDENCE}

        return None

    # ── Layer 2 helpers ─────────────────────────────────────────

    def _classify_by_embedding(
        self, text: str, sessions: list[Session]
    ) -> ClassificationResult:
        """Use embedding similarity to find the best matching session."""
        try:
            import torch

            query_embedding = self._embedding.embed_query(text)

            best_session_id: str | None = None
            best_similarity = 0.0
            best_topic = "general"

            for s in sessions:
                if not s.summary:
                    continue
                summary_embedding = self._embedding.embed_query(s.summary)
                similarity = torch.nn.functional.cosine_similarity(
                    query_embedding.unsqueeze(0),
                    summary_embedding.unsqueeze(0),
                ).item()

                if similarity > best_similarity:
                    best_similarity = similarity
                    best_session_id = s.session_id
                    best_topic = s.topic

            if best_similarity >= self.SIMILARITY_THRESHOLD and best_session_id is not None:
                return ClassificationResult(
                    topic=best_topic,
                    confidence=min(best_similarity, self.EMBEDDING_CONFIDENCE),
                    suggested_session_id=best_session_id,
                )

            return ClassificationResult(
                topic="general",
                confidence=best_similarity,
                suggested_session_id=None,
            )

        except Exception:
            logger.warning("Embedding-based classification failed, falling back", exc_info=True)
            return ClassificationResult(
                topic="general",
                confidence=0.3,
                suggested_session_id=None,
            )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd D:/Source/live2oder && poetry run pytest test/session/test_topic_classifier.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add internal/session/topic_classifier.py test/session/__init__.py test/session/test_topic_classifier.py
git commit -m "feat(session): add two-layer TopicClassifier with keyword and embedding detection"
```

---

### Task 3: Router

**Files:**
- Create: `internal/session/router.py`
- Create: `test/session/test_router.py`

- [ ] **Step 1: Write tests for Router in `test/session/test_router.py`**

```python
"""Unit tests for session Router."""

import time
import pytest
from internal.session.types import ClassificationResult, Session
from internal.session.router import Router, RouteAction


def make_session(session_id: str, topic: str, summary: str = "") -> Session:
    return Session(
        session_id=session_id,
        topic=topic,
        display_name=topic,
        summary=summary,
        created_at=time.time() - 3600,
        last_active_at=time.time() - 600,
        message_count=5,
        context_snapshot={"language": "zh"},
    )


class TestRouterDecide:
    """Tests for Router.decide() decision logic."""

    def setup_method(self):
        self.router = Router(confidence_threshold=0.8)
        self.sessions = [
            make_session("s1", "coding", "编写Python脚本相关讨论"),
            make_session("s2", "translation", "翻译英文文档"),
            make_session("s3", "learning", "学习机器学习基础知识"),
        ]

    def test_high_confidence_match_existing(self):
        """Confidence > threshold + matching session → switch."""
        result = ClassificationResult(
            topic="coding", confidence=0.85, suggested_session_id="s1"
        )
        action = self.router.decide(result, current_session_id="s3")
        assert action == RouteAction.SWITCH
        assert self.router.target_session_id == "s1"

    def test_high_confidence_new_topic(self):
        """Confidence > threshold + no matching session → create new."""
        result = ClassificationResult(
            topic="writing", confidence=0.85, suggested_session_id=None
        )
        action = self.router.decide(result, current_session_id="s1")
        assert action == RouteAction.CREATE

    def test_low_confidence_stay(self):
        """Confidence <= threshold → stay."""
        result = ClassificationResult(
            topic="general", confidence=0.3, suggested_session_id=None
        )
        action = self.router.decide(result, current_session_id="s1")
        assert action == RouteAction.STAY

    def test_same_session_no_switch(self):
        """Don't switch to the already-active session."""
        result = ClassificationResult(
            topic="coding", confidence=0.85, suggested_session_id="s1"
        )
        action = self.router.decide(result, current_session_id="s1")
        assert action == RouteAction.STAY

    def test_boundary_confidence(self):
        """Exactly at threshold → stay."""
        result = ClassificationResult(
            topic="coding", confidence=0.80, suggested_session_id="s1"
        )
        action = self.router.decide(result, current_session_id="s3")
        assert action == RouteAction.STAY

    def test_embedding_match_below_threshold(self):
        """Embedding found match but confidence still below threshold → stay."""
        result = ClassificationResult(
            topic="general", confidence=0.65, suggested_session_id="s2"
        )
        action = self.router.decide(result, current_session_id="s3")
        assert action == RouteAction.STAY


class TestRouterGenerateSummaryPrompt:
    """Tests for summary injection prompt generation."""

    def setup_method(self):
        self.router = Router()

    def test_generate_switch_context(self):
        prev_session = make_session("s1", "coding", "写了一个Python爬虫，讨论了BeautifulSoup用法")
        new_session = make_session("s2", "translation", "")
        context = self.router.generate_switch_context(prev_session, new_session)
        assert "coding" in context
        assert "Python爬虫" in context
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd D:/Source/live2oder && poetry run pytest test/session/test_router.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement `internal/session/router.py`**

```python
"""Session routing decision engine.

Determines whether to switch sessions, create a new one, or stay put
based on TopicClassifier output and confidence thresholds.
"""

import logging
from enum import Enum, auto

from internal.session.types import ClassificationResult, Session

logger = logging.getLogger(__name__)


class RouteAction(Enum):
    STAY = auto()
    SWITCH = auto()
    CREATE = auto()


class Router:
    """Makes session routing decisions based on classifier output."""

    def __init__(self, confidence_threshold: float = 0.80):
        self.confidence_threshold = confidence_threshold
        self.target_session_id: str | None = None

    def decide(
        self,
        classification: ClassificationResult,
        current_session_id: str | None,
    ) -> RouteAction:
        """Decide the routing action based on classification result.

        Args:
            classification: Output from TopicClassifier.classify().
            current_session_id: The currently active session ID.

        Returns:
            RouteAction: STAY, SWITCH, or CREATE.
        """
        self.target_session_id = None

        # Confidence too low → stay put
        if classification.confidence <= self.confidence_threshold:
            logger.debug(
                "Staying: confidence %.2f <= threshold %.2f",
                classification.confidence,
                self.confidence_threshold,
            )
            return RouteAction.STAY

        # High confidence + matched an existing session → switch
        if classification.suggested_session_id is not None:
            if classification.suggested_session_id == current_session_id:
                logger.debug("Already in target session '%s', staying", current_session_id)
                return RouteAction.STAY
            self.target_session_id = classification.suggested_session_id
            logger.info(
                "Switching to session '%s' (topic: %s)",
                self.target_session_id,
                classification.topic,
            )
            return RouteAction.SWITCH

        # High confidence + no match → create new session
        logger.info("Creating new session for topic '%s'", classification.topic)
        return RouteAction.CREATE

    def generate_switch_context(
        self,
        previous_session: Session,
        target_session: Session,
    ) -> str:
        """Generate context text for injecting into the target session
        when switching away from previous_session. Gives the model
        awareness of what was just discussed.

        Args:
            previous_session: The session being left.
            target_session: The session being entered.

        Returns:
            A string to prepend as a system message in the target session.
        """
        parts: list[str] = []
        parts.append(f"[会话切换: 从 '{previous_session.display_name}' 切换到 '{target_session.display_name}']")

        if previous_session.summary:
            parts.append(f"[上一個会话摘要] {previous_session.summary}")

        if target_session.summary:
            parts.append(f"[当前会话背景] {target_session.summary}")

        return "\n".join(parts)

    def generate_new_session_inheritance(
        self,
        previous_session: Session,
    ) -> dict[str, object]:
        """Extract key context variables from the previous session
        to inherit into a newly created session.

        Args:
            previous_session: The session being left.

        Returns:
            A context_snapshot dict for the new session.
        """
        snapshot: dict[str, object] = {}

        # Copy user preference keys from the old session
        for key in ("language", "user_name", "current_project", "preferences"):
            if key in previous_session.context_snapshot:
                snapshot[key] = previous_session.context_snapshot[key]

        return snapshot
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd D:/Source/live2oder && poetry run pytest test/session/test_router.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add internal/session/router.py test/session/test_router.py
git commit -m "feat(session): add Router with STAY/SWITCH/CREATE decision logic"
```

---

### Task 4: Session Store

**Files:**
- Create: `internal/session/session_store.py`

- [ ] **Step 1: Implement `internal/session/session_store.py`**

```python
"""Session metadata persistence layer.

Follows the storage pattern established in internal/memory/storage/:
abstract base with JSON implementation. Sessions are stored as
individual JSON files keyed by session_id.
"""

import json
import logging
import os
import time
from pathlib import Path

from internal.session.types import Session

logger = logging.getLogger(__name__)


class SessionStore:
    """Persist and load Session metadata records.

    Stores one JSON file per session under <data_dir>/sessions/.
    This is session metadata only (topic, summary, etc.) —
    full message history stays in the Memory layer.
    """

    def __init__(self, data_dir: str = "./data/sessions"):
        self.data_dir = Path(data_dir)
        self._sessions_dir = self.data_dir / "sessions"

    async def init(self) -> None:
        """Initialize storage directories."""
        self._sessions_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, session: Session) -> None:
        """Save a session record to disk."""
        filepath = self._sessions_dir / f"{session.session_id}.json"
        content = json.dumps(session.to_dict(), ensure_ascii=False, indent=2)
        # Use sync I/O for simplicity (sessions are small, saved infrequently)
        filepath.write_text(content, encoding="utf-8")
        logger.debug("Saved session '%s' to %s", session.session_id, filepath)

    async def load(self, session_id: str) -> Session | None:
        """Load a single session by ID. Returns None if not found."""
        filepath = self._sessions_dir / f"{session_id}.json"
        if not filepath.exists():
            return None
        try:
            content = filepath.read_text(encoding="utf-8")
            data = json.loads(content)
            return Session.from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to load session '%s': %s", session_id, e)
            return None

    async def list_all(self) -> list[Session]:
        """List all stored sessions, sorted by last_active_at descending."""
        sessions: list[Session] = []
        if not self._sessions_dir.exists():
            return sessions

        for filepath in self._sessions_dir.glob("*.json"):
            try:
                content = filepath.read_text(encoding="utf-8")
                data = json.loads(content)
                sessions.append(Session.from_dict(data))
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Skipping corrupt session file %s: %s", filepath, e)

        sessions.sort(key=lambda s: s.last_active_at, reverse=True)
        return sessions

    async def delete(self, session_id: str) -> bool:
        """Delete a session record. Returns True if deleted."""
        filepath = self._sessions_dir / f"{session_id}.json"
        if filepath.exists():
            filepath.unlink()
            logger.debug("Deleted session '%s'", session_id)
            return True
        return False
```

- [ ] **Step 2: Commit**

```bash
git add internal/session/session_store.py
git commit -m "feat(session): add SessionStore for session metadata persistence"
```

---

### Task 5: Session Manager Orchestrator

**Files:**
- Create: `internal/session/session_manager.py`
- Create: `test/session/test_session_manager.py`

- [ ] **Step 1: Write tests in `test/session/test_session_manager.py`**

```python
"""Integration tests for SessionManager."""

import time
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from internal.session.types import Session, ClassificationResult
from internal.session.topic_classifier import TopicClassifier
from internal.session.router import RouteAction
from internal.session.session_store import SessionStore


class TestSessionManagerBasic:
    """Tests for SessionManager lifecycle operations."""

    def setup_method(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = SessionStore(data_dir=self.temp_dir.name)

    def teardown_method(self):
        self.temp_dir.cleanup()

    @pytest.mark.asyncio
    async def test_init_creates_session(self):
        from internal.session.session_manager import SessionManager

        await self.store.init()
        mgr = SessionManager(
            session_store=self.store,
            classifier=TopicClassifier(embedding_model=None),
            router=None,
            memory_manager=None,
        )
        await mgr.initialize()

        assert mgr.current_session is not None
        assert mgr.current_session.topic == "general"
        sessions = await mgr.list_sessions()
        assert len(sessions) == 1

    @pytest.mark.asyncio
    async def test_new_session_creates_with_topic(self):
        from internal.session.session_manager import SessionManager

        await self.store.init()
        mgr = SessionManager(
            session_store=self.store,
            classifier=TopicClassifier(embedding_model=None),
            router=None,
            memory_manager=None,
        )
        await mgr.initialize()

        session = await mgr.create_session(topic="coding", inherit_from=None)
        assert session.topic == "coding"
        assert session.session_id is not None

    @pytest.mark.asyncio
    async def test_list_sessions_returns_all(self):
        from internal.session.session_manager import SessionManager

        await self.store.init()
        mgr = SessionManager(
            session_store=self.store,
            classifier=TopicClassifier(embedding_model=None),
            router=None,
            memory_manager=None,
        )
        await mgr.initialize()
        await mgr.create_session(topic="coding")
        await mgr.create_session(topic="translation")

        sessions = await mgr.list_sessions()
        assert len(sessions) == 3  # default + coding + translation

    @pytest.mark.asyncio
    async def test_switch_session_updates_current(self):
        from internal.session.session_manager import SessionManager

        await self.store.init()
        mgr = SessionManager(
            session_store=self.store,
            classifier=TopicClassifier(embedding_model=None),
            router=None,
            memory_manager=None,
        )
        await mgr.initialize()
        coding = await mgr.create_session(topic="coding")

        switched = await mgr.switch_to(coding.session_id)
        assert switched is True
        assert mgr.current_session.session_id == coding.session_id


class TestSessionManagerRouting:
    """Tests for auto-routing on message input."""

    @pytest.mark.asyncio
    async def test_route_message_switches_when_classifier_matches(self):
        from internal.session.session_manager import SessionManager

        # Setup: mock memory manager
        mock_memory = MagicMock()
        mock_memory.switch_session = AsyncMock(return_value=True)
        mock_memory.new_session = AsyncMock()
        mock_memory.list_sessions = MagicMock(return_value=[])
        mock_memory.current_session_info = MagicMock(return_value=None)

        await self.store.init()
        mgr = SessionManager(
            session_store=self.store,
            classifier=TopicClassifier(embedding_model=None),
            router=None,  # uses default Router
            memory_manager=mock_memory,
        )
        await mgr.initialize()

        # First, create a coding session
        await mgr.create_session(topic="coding")

        # Now send a coding message
        action, new_messages = await mgr.route_message("帮我写一个排序算法")
        # Should match coding topic, switch to coding session
        assert action in (RouteAction.SWITCH, RouteAction.CREATE)

    @pytest.mark.asyncio
    async def test_route_message_stays_when_no_match(self):
        from internal.session.session_manager import SessionManager

        mock_memory = MagicMock()
        mock_memory.switch_session = AsyncMock(return_value=True)
        mock_memory.new_session = AsyncMock()
        mock_memory.list_sessions = MagicMock(return_value=[])
        mock_memory.current_session_info = MagicMock(return_value=None)

        await self.store.init()
        mgr = SessionManager(
            session_store=self.store,
            classifier=TopicClassifier(embedding_model=None),
            router=None,
            memory_manager=mock_memory,
        )
        await mgr.initialize()

        action, _ = await mgr.route_message("今天天气真好啊")
        assert action == RouteAction.STAY
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd D:/Source/live2oder && poetry run pytest test/session/test_session_manager.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement `internal/session/session_manager.py`**

```python
"""Session Manager — orchestrator for auto-routing.

Wires TopicClassifier + Router + SessionStore + MemoryManager together.
Called at the start of each user message to determine session routing.

Flow:
  User message → route_message(text) → classify → Router.decide →
    ├─ STAY: continue in current session, return empty context injection
    ├─ SWITCH: MemoryManager.switch_session(), inject old summary
    └─ CREATE: MemoryManager.new_session(), inherit context
"""

import logging
import time
import uuid
from typing import TYPE_CHECKING

from internal.session.types import ClassificationResult, Session
from internal.session.router import Router, RouteAction
from internal.session.topic_classifier import TopicClassifier
from internal.session.session_store import SessionStore

if TYPE_CHECKING:
    from internal.memory._manager import MemoryManager
    from internal.rag.embeddings import EmbeddingGenerator

logger = logging.getLogger(__name__)


class SessionManager:
    """Orchestrates session auto-routing.

    Dependencies:
    - TopicClassifier: detects topic from user text
    - Router: makes STAY/SWITCH/CREATE decisions
    - SessionStore: persists session metadata
    - MemoryManager: manages actual message history per session
    """

    def __init__(
        self,
        session_store: SessionStore,
        classifier: TopicClassifier,
        router: Router | None = None,
        memory_manager: "MemoryManager | None" = None,
    ):
        self._store = session_store
        self._classifier = classifier
        self._router = router or Router()
        self._memory: "MemoryManager | None" = memory_manager
        self._sessions: dict[str, Session] = {}
        self._current_session_id: str | None = None

    # ── Properties ────────────────────────────────────────────

    @property
    def current_session(self) -> Session | None:
        if self._current_session_id is None:
            return None
        return self._sessions.get(self._current_session_id)

    # ── Lifecycle ──────────────────────────────────────────────

    async def initialize(self) -> None:
        """Load existing sessions from store, create default if none."""
        await self._store.init()

        loaded = await self._store.list_all()
        self._sessions = {s.session_id: s for s in loaded}
        logger.info("Loaded %d sessions from store", len(self._sessions))

        if not self._sessions:
            session = await self.create_session(topic="general", inherit_from=None)
            self._current_session_id = session.session_id
        else:
            # Restore the most recently active session
            self._current_session_id = loaded[0].session_id

    async def create_session(
        self,
        topic: str,
        inherit_from: Session | None = None,
    ) -> Session:
        """Create a new session with the given topic.

        Args:
            topic: Topic label for the new session.
            inherit_from: Optional session to inherit context from.
        """
        session_id = str(uuid.uuid4())[:8]
        now = time.time()

        snapshot: dict[str, object] = {}
        if inherit_from is not None:
            snapshot = self._router.generate_new_session_inheritance(inherit_from)

        session = Session(
            session_id=session_id,
            topic=topic,
            display_name=topic,
            summary="",
            created_at=now,
            last_active_at=now,
            message_count=0,
            context_snapshot=snapshot,
        )

        self._sessions[session_id] = session
        await self._store.save(session)

        # Also create the session in MemoryManager if available
        if self._memory is not None:
            await self._memory.new_session(topic)

        logger.info(
            "Created session '%s' topic='%s' (inherited from %s)",
            session_id,
            topic,
            inherit_from.session_id if inherit_from else "none",
        )
        return session

    async def switch_to(self, session_id: str) -> bool:
        """Switch to an existing session.

        Returns True if the switch succeeded.
        """
        if session_id not in self._sessions:
            logger.warning("Session '%s' not found", session_id)
            return False

        if session_id == self._current_session_id:
            return True

        # Save old session's context snapshot
        if self._current_session_id and self._current_session_id in self._sessions:
            old = self._sessions[self._current_session_id]
            old.last_active_at = time.time()
            await self._store.save(old)

        self._current_session_id = session_id
        session = self._sessions[session_id]
        session.last_active_at = time.time()
        await self._store.save(session)

        # Switch in MemoryManager if available
        if self._memory is not None:
            await self._memory.switch_session(session_id)

        logger.info("Switched to session '%s'", session_id)
        return True

    async def list_sessions(self) -> list[Session]:
        """List all sessions sorted by last_active_at descending."""
        return sorted(
            self._sessions.values(),
            key=lambda s: s.last_active_at,
            reverse=True,
        )

    async def update_summary(self, session_id: str, summary: str) -> None:
        """Update a session's summary (called after compression)."""
        if session_id in self._sessions:
            self._sessions[session_id].summary = summary
            await self._store.save(self._sessions[session_id])

    # ── Core routing ─────────────────────────────────────────

    async def route_message(
        self,
        text: str,
    ) -> tuple[RouteAction, str]:
        """Route an incoming user message to the appropriate session.

        Called at the start of every user message processing flow.

        Args:
            text: The user input text.

        Returns:
            (RouteAction, context_injection_string)
            context_injection_string is an empty string for STAY,
            or a system-message-ready string for SWITCH/CREATE
            describing the previous session context.
        """
        # Classify the input
        session_list = list(self._sessions.values())
        classification = self._classifier.classify(text, session_list)

        # Decide what to do
        action = self._router.decide(classification, self._current_session_id)

        context_injection = ""

        if action == RouteAction.STAY:
            pass

        elif action == RouteAction.SWITCH:
            target_id = self._router.target_session_id
            if target_id is not None and target_id != self._current_session_id:
                prev = self.current_session
                target = self._sessions.get(target_id)
                if prev is not None and target is not None:
                    context_injection = self._router.generate_switch_context(prev, target)
                await self.switch_to(target_id)

        elif action == RouteAction.CREATE:
            prev = self.current_session
            new_session = await self.create_session(
                topic=classification.topic,
                inherit_from=prev,
            )
            # Also switch MemoryManager to the new session
            if self._memory is not None:
                await self._memory.new_session(classification.topic)

            if prev is not None:
                context_injection = f"[新会话已创建] 主题: {classification.topic}。上一会话摘要: {prev.summary}"

            self._current_session_id = new_session.session_id

        return action, context_injection
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd D:/Source/live2oder && poetry run pytest test/session/test_session_manager.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add internal/session/session_manager.py test/session/test_session_manager.py
git commit -m "feat(session): add SessionManager orchestrator with auto-routing"
```

---

### Task 6: MemoryManager Integration

**Files:**
- Modify: `internal/memory/_manager.py`

`MemoryManager` already has `switch_session()` and `new_session()`. We need to add one method: `get_session_messages()` for loading a specific session's messages without switching to it (used by Router to pre-fetch context). Also verify the existing `switch_session` signature matches what `internal/session/session_manager.py` calls.

- [ ] **Step 1: Check existing `switch_session` and `new_session` signatures**

The existing `MemoryManager` delegates to `SessionManager` (the memory-layer one). The method signatures are:

```python
# _manager.py
async def switch_session(self, session_id: str) -> bool: ...
async def new_session(self, title: Optional[str] = None) -> SessionInfo: ...
```

These are already compatible with what `internal/session/session_manager.py` calls. No changes needed to existing methods.

- [ ] **Step 2: Add `get_session_messages()` to `internal/memory/_manager.py`**

Add after the existing `switch_session` method (around line 289):

```python
    async def get_session_messages(self, session_id: str) -> list[Message]:
        """Get messages for a specific session without switching to it.

        Used by the session auto-router to peek at a session's context
        before deciding whether to switch.
        """
        assert self._initialized
        if self._mcp is not None:
            # MCP: load from scope (read-only, no switch)
            response = await self._mcp.get_context(scope=session_id)
            legacy_messages: list[Message] = []
            for msg in response.messages:
                legacy_msg: Message = {
                    "role": msg.role.value,
                    "content": msg.content,
                    "tokens": msg.tokens,
                    "tool_name": msg.tool_name,
                    "tool_call_id": msg.tool_call_id,
                    "metadata": msg.metadata,
                }
                legacy_messages.append(legacy_msg)
            return legacy_messages

        # Legacy: load from storage
        if self._storage is None:
            return []
        data = await self._storage.load_session(session_id)
        if data is None:
            return []
        from internal.memory._types import ConversationTurn
        turns = [ConversationTurn.from_dict(t) for t in data.get("turns", [])]
        return [turn.message for turn in turns]
```

- [ ] **Step 3: Commit**

```bash
git add internal/memory/_manager.py
git commit -m "feat(memory): add get_session_messages() for session auto-router"
```

---

### Task 7: Wire into Agent and App

**Files:**
- Modify: `internal/agent/agent.py`
- Modify: `internal/app/live2d_agent_app.py`

- [ ] **Step 1: Add session routing to `internal/agent/agent.py`**

In `Agent.__init__`, after the memory initialization, add optional session manager:

```python
        # Session auto-routing (optional)
        self.session_router: Any | None = None
```

In `Agent.process_message` (or equivalent chat entry point), add session routing before model call. The `process_message` likely lives in `agent.py` or `chat_service.py`. We add a hook method:

```python
    async def _route_session(self, text: str) -> str:
        """Route user input through session auto-router.

        Returns a context injection string (empty if no routing needed).
        """
        if self.session_router is None:
            return ""

        try:
            from internal.session.router import RouteAction
            action, context = await self.session_router.route_message(text)
            logger.info("Session routing: action=%s", action.name)
            return context
        except Exception:
            logger.warning("Session routing failed, continuing in current session", exc_info=True)
            return ""
```

Call `_route_session(text)` at the start of chat processing, before composing the system prompt. If `context` is non-empty, prepend it as a system message to the conversation.

- [ ] **Step 2: Initialize SessionManager in `internal/app/live2d_agent_app.py`**

In `bootstrap_application()` (or `Live2DAgentApp.initialize()`), create and initialize the session router:

```python
from internal.session import SessionRouter, TopicClassifier
from internal.session.session_store import SessionStore


async def _initialize_session_router(config, agent):
    """Initialize the session auto-router if enabled in config."""
    session_config = getattr(config, "session", None)
    if session_config is None or not getattr(session_config, "enabled", True):
        return None

    store = SessionStore(data_dir=getattr(session_config, "data_dir", "./data/sessions"))
    classifier = TopicClassifier(embedding_model=None)  # Start without embeddings

    # Try to load embedding model for better classification
    try:
        from internal.rag.embeddings import EmbeddingGenerator
        emb = EmbeddingGenerator()
        emb.load()
        classifier = TopicClassifier(embedding_model=emb)
    except Exception:
        pass  # Keyword-only classification is fine

    memory = agent.memory if hasattr(agent, "memory") else None
    router = SessionRouter(
        session_store=store,
        classifier=classifier,
        memory_manager=memory,
    )
    await router.initialize()

    # Attach to agent
    agent.session_router = router

    return router
```

Call `_initialize_session_router(config, agent)` during bootstrap, after the agent is created.

- [ ] **Step 3: Run all session tests**

```bash
cd D:/Source/live2oder && poetry run pytest test/session/ -v
```
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add internal/agent/agent.py internal/app/live2d_agent_app.py
git commit -m "feat(session): wire SessionManager into Agent and App bootstrap"
```

---

### Task 8: Manual Verification & Edge Cases

- [ ] **Step 1: Verify session routing with real input**

Run the app and test:
1. Type a coding question → verify new session is created
2. Type a translation request → verify session switches or creates
3. Type casual chat → verify stays in same session
4. Check log output for routing decisions

```bash
cd D:/Source/live2oder && poetry run python __main__.py
# Manually test the above scenarios
```

- [ ] **Step 2: Run full test suite to check for regressions**

```bash
cd D:/Source/live2oder && poetry run pytest test/ -v --timeout=30
```
Expected: No regressions from existing tests.

- [ ] **Step 3: Commit any fixes**

```bash
git add -A
git commit -m "fix(session): address issues found during manual verification"
```
