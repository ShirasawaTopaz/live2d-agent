"""Two-layer topic classifier for session auto-routing.

Layer 1 (fast): keyword/regex matching against built-in and user-defined rules.
Layer 2 (fallback): embedding similarity against existing session summaries.

The embedding layer reuses internal.rag.embeddings.EmbeddingGenerator
for zero additional model dependencies.
"""

import logging
import re
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

        except (ImportError, RuntimeError, ValueError) as e:
            logger.warning(
                "Embedding-based classification failed, falling back: %s", e, exc_info=True
            )
            return ClassificationResult(
                topic="general",
                confidence=0.3,
                suggested_session_id=None,
            )
