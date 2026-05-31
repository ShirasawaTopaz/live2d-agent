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

        # Confidence too low => stay put
        if classification.confidence <= self.confidence_threshold:
            logger.debug(
                "Staying: confidence %.2f <= threshold %.2f",
                classification.confidence,
                self.confidence_threshold,
            )
            return RouteAction.STAY

        # High confidence + matched an existing session => switch
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

        # High confidence + no match => create new session
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
        """
        parts: list[str] = []
        parts.append(
            f"[会话切换: 从 '{previous_session.display_name}' 切换到 '{target_session.display_name}']"
        )

        if previous_session.summary:
            parts.append(f"[上一个会话摘要] {previous_session.summary}")

        if target_session.summary:
            parts.append(f"[当前会话背景] {target_session.summary}")

        return "\n".join(parts)

    def generate_new_session_inheritance(
        self,
        previous_session: Session,
    ) -> dict[str, object]:
        """Extract key context variables from the previous session
        to inherit into a newly created session.
        """
        snapshot: dict[str, object] = {}

        # Copy user preference keys from the old session
        for key in ("language", "user_name", "current_project", "preferences"):
            if key in previous_session.context_snapshot:
                snapshot[key] = previous_session.context_snapshot[key]

        return snapshot
