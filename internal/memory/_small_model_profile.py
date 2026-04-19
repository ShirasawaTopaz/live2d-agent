from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class SmallModelMemoryProfile:
    enabled: bool
    reason: str
    summary_style: str
    compression_aggressiveness: str
    preserve_recent_count: int
    summary_length_cap: int
    injection_compactness: str


_ENABLED_PROFILE = SmallModelMemoryProfile(
    enabled=True,
    reason="",
    summary_style="compact_summary",
    compression_aggressiveness="aggressive",
    preserve_recent_count=3,
    summary_length_cap=320,
    injection_compactness="tight",
)

_DISABLED_PROFILE = SmallModelMemoryProfile(
    enabled=False,
    reason="",
    summary_style="default",
    compression_aggressiveness="default",
    preserve_recent_count=5,
    summary_length_cap=0,
    injection_compactness="default",
)

_OLLAMA_REMOTE_OPTION_KEYS = ("host", "base_url", "api", "endpoint")


def estimate_model_size_b(model_name: str) -> float:
    """Estimate model parameter count in billions from a model identifier."""
    model_name_lower = model_name.lower()

    if re.search(r"(?<!\d)(0\.8|1)b(?!\d)", model_name_lower):
        return 0.8
    if re.search(r"(?<!\d)(1\.8|2)b(?!\d)", model_name_lower):
        return 1.8
    if re.search(r"(?<!\d)(4|7)b(?!\d)", model_name_lower):
        return 4.0 if "4b" in model_name_lower else 7.0
    if re.search(r"(?<!\d)(13|14)b(?!\d)", model_name_lower):
        return 13.0
    if re.search(r"(?<!\d)32b(?!\d)", model_name_lower):
        return 32.0

    return 0.0


def classify_small_model_memory_profile(
    model_config: Any,
) -> SmallModelMemoryProfile:
    model_type = _get_model_type_value(model_config)

    if model_type == "online":
        return _disabled_profile("online-model")

    if model_type == "transformers":
        return _classify_transformers_profile(model_config)

    if model_type == "ollama":
        return _classify_ollama_profile(model_config)

    return _disabled_profile("unsupported-model-type")


def _classify_transformers_profile(
    model_config: Any,
) -> SmallModelMemoryProfile:
    model_name = getattr(model_config, "model", "") or ""
    param_count_b = estimate_model_size_b(str(model_name))

    if param_count_b <= 0:
        return _disabled_profile("transformers-size-unknown")
    if param_count_b <= 4.0:
        return _enabled_profile(f"transformers-small-{param_count_b:.1f}b")

    return _disabled_profile(f"transformers-not-small-{param_count_b:.1f}b")


def _classify_ollama_profile(model_config: Any) -> SmallModelMemoryProfile:
    endpoint = _get_ollama_endpoint(model_config)
    if endpoint and not _is_local_endpoint(endpoint):
        return _disabled_profile("ollama-explicit-remote-endpoint")

    model_name = getattr(model_config, "model", "") or ""
    param_count_b = estimate_model_size_b(str(model_name))
    if param_count_b <= 0:
        if endpoint:
            return _disabled_profile("ollama-size-ambiguous")
        if _is_local_endpoint(_get_runtime_ollama_host()):
            return _disabled_profile("ollama-size-ambiguous")
        return _disabled_profile("ollama-unknown-locality")
    if param_count_b > 4.0:
        return _disabled_profile(f"ollama-not-small-{param_count_b:.1f}b")

    if endpoint:
        return _enabled_profile(f"ollama-local-endpoint-small-{param_count_b:.1f}b")

    if _is_local_endpoint(_get_runtime_ollama_host()):
        return _enabled_profile(
            f"ollama-local-default-endpoint-small-{param_count_b:.1f}b"
        )

    return _disabled_profile("ollama-unknown-locality")


def _get_ollama_endpoint(model_config: Any) -> str | None:
    raw_options = getattr(model_config, "config", {})
    options = raw_options if isinstance(raw_options, dict) else {}

    for key in _OLLAMA_REMOTE_OPTION_KEYS:
        value = options.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


def _is_local_endpoint(endpoint: str) -> bool:
    parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False

    return hostname in {"localhost", "127.0.0.1", "::1"} or hostname.startswith(
        "127."
    )


def _get_runtime_ollama_host() -> str:
    # Mirror ollama.Client default locality (localhost:11434) when no endpoint is set.
    return "http://127.0.0.1:11434"


def _get_model_type_value(model_config: Any) -> str:
    model_type = getattr(model_config, "type", None)
    if isinstance(model_type, str):
        return model_type.lower()
    if hasattr(model_type, "value"):
        value = getattr(model_type, "value", "")
        if isinstance(value, str):
            return value.lower()
    return ""


def _enabled_profile(reason: str) -> SmallModelMemoryProfile:
    return SmallModelMemoryProfile(
        enabled=_ENABLED_PROFILE.enabled,
        reason=reason,
        summary_style=_ENABLED_PROFILE.summary_style,
        compression_aggressiveness=_ENABLED_PROFILE.compression_aggressiveness,
        preserve_recent_count=_ENABLED_PROFILE.preserve_recent_count,
        summary_length_cap=_ENABLED_PROFILE.summary_length_cap,
        injection_compactness=_ENABLED_PROFILE.injection_compactness,
    )


def _disabled_profile(reason: str) -> SmallModelMemoryProfile:
    return SmallModelMemoryProfile(
        enabled=_DISABLED_PROFILE.enabled,
        reason=reason,
        summary_style=_DISABLED_PROFILE.summary_style,
        compression_aggressiveness=_DISABLED_PROFILE.compression_aggressiveness,
        preserve_recent_count=_DISABLED_PROFILE.preserve_recent_count,
        summary_length_cap=_DISABLED_PROFILE.summary_length_cap,
        injection_compactness=_DISABLED_PROFILE.injection_compactness,
    )
