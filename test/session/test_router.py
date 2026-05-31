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
        """Confidence > threshold + matching session => switch."""
        result = ClassificationResult(
            topic="coding", confidence=0.85, suggested_session_id="s1"
        )
        action = self.router.decide(result, current_session_id="s3")
        assert action == RouteAction.SWITCH
        assert self.router.target_session_id == "s1"

    def test_high_confidence_new_topic(self):
        """Confidence > threshold + no matching session => create new."""
        result = ClassificationResult(
            topic="writing", confidence=0.85, suggested_session_id=None
        )
        action = self.router.decide(result, current_session_id="s1")
        assert action == RouteAction.CREATE

    def test_low_confidence_stay(self):
        """Confidence <= threshold => stay."""
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
        """Exactly at threshold => stay."""
        result = ClassificationResult(
            topic="coding", confidence=0.80, suggested_session_id="s1"
        )
        action = self.router.decide(result, current_session_id="s3")
        assert action == RouteAction.STAY

    def test_embedding_match_below_threshold(self):
        """Embedding found match but confidence still below threshold => stay."""
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
