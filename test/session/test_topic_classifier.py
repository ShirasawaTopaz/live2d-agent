"""Unit tests for TopicClassifier."""

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
        from internal.session.types import Session
        import time
        sessions = [
            Session(session_id="s1", topic="coding", display_name="coding", summary="编程相关讨论", created_at=time.time(), last_active_at=time.time(), message_count=5),
        ]
        result = self.classifier.classify("帮我写代码", sessions=sessions)
        assert result.confidence >= 0.8
