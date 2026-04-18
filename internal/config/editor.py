from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from internal.config.config import AIModelType, Config

KNOWN_CONFIG_KEYS = (
    "live2dSocket",
    "models",
    "memory",
    "sandbox",
    "planning",
    "rag",
)


@dataclass(slots=True)
class ValidationError:
    field: str
    message: str


@dataclass(slots=True)
class RuntimeApplyDecision:
    websocket_changed: bool
    default_model_changed: bool
    requires_restart: bool


def load_with_raw(config_path: str) -> tuple[dict[str, Any], Config]:
    path = Path(config_path)
    if not path.exists():
        return {}, Config()

    content = path.read_text(encoding="utf-8")
    if not content.strip():
        return {}, Config()

    try:
        json_data = json.loads(content)
    except JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in config file '{config_path}': {exc.msg}") from exc

    if not isinstance(json_data, dict):
        raise ValueError(
            f"Config file '{config_path}' must contain a JSON object at the top level."
        )

    return json_data, Config.from_dict(json_data)


def merge_known_fields(raw_dict: dict[str, Any], edited_dict: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(raw_dict)
    for key in KNOWN_CONFIG_KEYS:
        if key not in edited_dict:
            continue
        new_value = edited_dict[key]
        old_value = merged.get(key)
        merged[key] = _merge_value(old_value, new_value)
    return merged


def save_config_atomic(config_path: str, data: dict[str, Any]) -> None:
    target_path = Path(config_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(data, ensure_ascii=False, indent=4)
    with NamedTemporaryFile(
        "w", delete=False, encoding="utf-8", dir=str(target_path.parent), suffix=".tmp"
    ) as temp_file:
        temp_file.write(serialized)
        temp_file.write("\n")
        temp_name = temp_file.name
    Path(temp_name).replace(target_path)


def validate_config_dict(data: dict[str, Any]) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if not isinstance(data, dict):
        return [ValidationError(field="$", message="Top-level config must be an object.")]

    live2d_socket = data.get("live2dSocket")
    if not isinstance(live2d_socket, str) or not live2d_socket.strip():
        errors.append(
            ValidationError(field="live2dSocket", message="live2dSocket must be a non-empty string.")
        )
    elif not live2d_socket.startswith(("ws://", "wss://")):
        errors.append(
            ValidationError(
                field="live2dSocket",
                message="live2dSocket must start with ws:// or wss://.",
            )
        )

    models = data.get("models")
    if not isinstance(models, list) or len(models) == 0:
        errors.append(
            ValidationError(field="models", message="At least one model configuration is required.")
        )
    else:
        for idx, model in enumerate(models):
            errors.extend(_validate_model(model, idx))

    memory = data.get("memory")
    if memory is not None and not isinstance(memory, dict):
        errors.append(ValidationError(field="memory", message="memory must be an object."))
    else:
        errors.extend(_validate_memory(memory))

    sandbox = data.get("sandbox")
    if sandbox is not None and not isinstance(sandbox, dict):
        errors.append(ValidationError(field="sandbox", message="sandbox must be an object."))
    else:
        errors.extend(_validate_sandbox(sandbox))

    planning = data.get("planning")
    if planning is not None and not isinstance(planning, dict):
        errors.append(ValidationError(field="planning", message="planning must be an object."))
    else:
        errors.extend(_validate_planning(planning))

    rag = data.get("rag")
    if rag is not None and not isinstance(rag, dict):
        errors.append(ValidationError(field="rag", message="rag must be an object."))
    else:
        errors.extend(_validate_rag(rag))

    return errors


def normalize_models_default(
    models: list[dict[str, Any]], preferred_index: int | None
) -> tuple[list[dict[str, Any]], bool]:
    default_indices = [idx for idx, model in enumerate(models) if bool(model.get("default"))]
    if len(default_indices) <= 1:
        return models, False

    keep_index = default_indices[-1]
    if preferred_index is not None and preferred_index in default_indices:
        keep_index = preferred_index

    for idx, model in enumerate(models):
        model["default"] = idx == keep_index
    return models, True


def decide_runtime_apply(old_config: Config, new_config: Config) -> RuntimeApplyDecision:
    websocket_changed = old_config.live2dSocket != new_config.live2dSocket
    default_model_changed = _default_model_signature(old_config) != _default_model_signature(
        new_config
    )
    old_data = old_config.to_dict()
    new_data = new_config.to_dict()

    non_hot_changed = any(
        old_data.get(section) != new_data.get(section)
        for section in ("memory", "sandbox", "planning", "rag")
    )
    models_changed = old_data.get("models") != new_data.get("models")
    requires_restart = non_hot_changed or (models_changed and not default_model_changed)

    return RuntimeApplyDecision(
        websocket_changed=websocket_changed,
        default_model_changed=default_model_changed,
        requires_restart=requires_restart,
    )


def _merge_value(old_value: Any, new_value: Any) -> Any:
    if isinstance(old_value, dict) and isinstance(new_value, dict):
        merged = copy.deepcopy(old_value)
        for key, value in new_value.items():
            merged[key] = _merge_value(old_value.get(key), value)
        return merged
    return copy.deepcopy(new_value)


def _default_model_signature(config: Config) -> tuple[Any, ...] | None:
    try:
        default_model = config.get_default_model_config()
    except ValueError:
        return None
    return (
        default_model.name,
        default_model.model,
        default_model.type.value,
        default_model.system_prompt,
        default_model.temperature,
        default_model.api_key,
        default_model.streaming,
        default_model.load_in_4bit,
        default_model.load_in_8bit,
        default_model.kv_cache_quantization,
        default_model.top_p,
        default_model.repeat_penalty,
        default_model.max_new_tokens,
        default_model.enable_cot,
        default_model.max_tool_call_retries,
        default_model.config,
    )


def _validate_model(model: Any, idx: int) -> list[ValidationError]:
    field = f"models[{idx}]"
    errors: list[ValidationError] = []
    if not isinstance(model, dict):
        return [ValidationError(field=field, message="Model entry must be an object.")]

    name = model.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(ValidationError(field=f"{field}.name", message="name is required."))

    model_name = model.get("model")
    if not isinstance(model_name, str) or not model_name.strip():
        errors.append(ValidationError(field=f"{field}.model", message="model is required."))

    model_type = model.get("type")
    valid_types = {member.value for member in AIModelType}
    if model_type not in valid_types:
        errors.append(
            ValidationError(
                field=f"{field}.type",
                message=f"type must be one of: {', '.join(sorted(valid_types))}.",
            )
        )

    system_prompt = model.get("system_prompt")
    if not isinstance(system_prompt, (str, dict)):
        errors.append(
            ValidationError(
                field=f"{field}.system_prompt",
                message="system_prompt must be a string or object.",
            )
        )

    temperature = model.get("temperature")
    if not isinstance(temperature, (int, float)):
        errors.append(
            ValidationError(field=f"{field}.temperature", message="temperature must be a number.")
        )
    elif temperature < 0 or temperature > 2:
        errors.append(
            ValidationError(
                field=f"{field}.temperature",
                message="temperature must be between 0 and 2.",
            )
        )

    if "top_p" in model and model.get("top_p") is not None:
        errors.extend(_validate_float_range(f"{field}.top_p", model.get("top_p"), 0, 1))

    if "repeat_penalty" in model and model.get("repeat_penalty") is not None:
        errors.extend(
            _validate_float_range(f"{field}.repeat_penalty", model.get("repeat_penalty"), 0.5, 3.0)
        )

    if "max_new_tokens" in model and model.get("max_new_tokens") is not None:
        errors.extend(_validate_positive_int(f"{field}.max_new_tokens", model.get("max_new_tokens")))

    if "max_tool_call_retries" in model and model.get("max_tool_call_retries") is not None:
        retries = model.get("max_tool_call_retries")
        if not isinstance(retries, int) or retries < 0:
            errors.append(
                ValidationError(
                    field=f"{field}.max_tool_call_retries",
                    message="max_tool_call_retries must be an integer >= 0.",
                )
            )

    options = model.get("options")
    if options is not None and not isinstance(options, dict):
        errors.append(
            ValidationError(field=f"{field}.options", message="options must be an object.")
        )

    return errors


def _validate_memory(memory: dict[str, Any] | None) -> list[ValidationError]:
    if memory is None:
        return []
    errors: list[ValidationError] = []
    for key in (
        "max_messages",
        "max_tokens",
        "compression_threshold_messages",
        "compression_cutoff_days",
        "compression_min_messages",
        "max_sessions",
        "max_working_messages",
        "max_recent_tokens",
        "max_total_tokens",
    ):
        if key in memory:
            errors.extend(_validate_positive_int(f"memory.{key}", memory.get(key)))

    if "mcp_mode" in memory and memory.get("mcp_mode") not in (None, "local", "hybrid", "remote"):
        errors.append(
            ValidationError(
                field="memory.mcp_mode",
                message="memory.mcp_mode must be 'local', 'hybrid', or 'remote'.",
            )
        )

    if "compression_strategy" in memory and memory.get("compression_strategy") not in (
        None,
        "summary",
        "sliding",
        "extraction",
    ):
        errors.append(
            ValidationError(
                field="memory.compression_strategy",
                message="memory.compression_strategy must be 'summary', 'sliding', or 'extraction'.",
            )
        )

    remote_cfg = memory.get("remote")
    if remote_cfg is not None:
        if not isinstance(remote_cfg, dict):
            errors.append(ValidationError(field="memory.remote", message="memory.remote must be an object."))
        else:
            if "timeout" in remote_cfg:
                errors.extend(_validate_positive_int("memory.remote.timeout", remote_cfg.get("timeout")))
    return errors


def _validate_sandbox(sandbox: dict[str, Any] | None) -> list[ValidationError]:
    if sandbox is None:
        return []
    errors: list[ValidationError] = []
    file_cfg = sandbox.get("file")
    if file_cfg is not None:
        if not isinstance(file_cfg, dict):
            errors.append(ValidationError(field="sandbox.file", message="sandbox.file must be an object."))
        else:
            policy = file_cfg.get("default_policy")
            if policy not in (None, "allow", "deny"):
                errors.append(
                    ValidationError(
                        field="sandbox.file.default_policy",
                        message="default_policy must be 'allow' or 'deny'.",
                    )
                )
            if "max_file_size" in file_cfg:
                errors.extend(
                    _validate_positive_int("sandbox.file.max_file_size", file_cfg.get("max_file_size"))
                )

    network_cfg = sandbox.get("network")
    if network_cfg is not None:
        if not isinstance(network_cfg, dict):
            errors.append(
                ValidationError(field="sandbox.network", message="sandbox.network must be an object.")
            )
        else:
            blocked_ports = network_cfg.get("blocked_ports")
            if blocked_ports is not None:
                if not isinstance(blocked_ports, list):
                    errors.append(
                        ValidationError(
                            field="sandbox.network.blocked_ports",
                            message="blocked_ports must be an array of port numbers.",
                        )
                    )
                else:
                    for idx, port in enumerate(blocked_ports):
                        if not isinstance(port, int) or port < 1 or port > 65535:
                            errors.append(
                                ValidationError(
                                    field=f"sandbox.network.blocked_ports[{idx}]",
                                    message="port must be an integer between 1 and 65535.",
                                )
                            )

    approval_cfg = sandbox.get("approval")
    if approval_cfg is not None:
        if not isinstance(approval_cfg, dict):
            errors.append(
                ValidationError(field="sandbox.approval", message="sandbox.approval must be an object.")
            )
        elif "timeout_seconds" in approval_cfg:
            errors.extend(
                _validate_positive_int("sandbox.approval.timeout_seconds", approval_cfg.get("timeout_seconds"))
            )
    return errors


def _validate_planning(planning: dict[str, Any] | None) -> list[ValidationError]:
    if planning is None:
        return []
    errors: list[ValidationError] = []
    if "storage_type" in planning and planning.get("storage_type") not in (None, "json", "sqlite"):
        errors.append(
            ValidationError(
                field="planning.storage_type",
                message="planning.storage_type must be 'json' or 'sqlite'.",
            )
        )
    for key in ("max_concurrency", "max_plan_depth"):
        if key in planning:
            errors.extend(_validate_positive_int(f"planning.{key}", planning.get(key)))
    return errors


def _validate_rag(rag: dict[str, Any] | None) -> list[ValidationError]:
    if rag is None:
        return []
    errors: list[ValidationError] = []
    for key in ("chunk_size", "chunk_overlap", "top_k"):
        if key in rag:
            errors.extend(_validate_non_negative_int(f"rag.{key}", rag.get(key)))
    return errors


def _validate_positive_int(field: str, value: Any) -> list[ValidationError]:
    if not isinstance(value, int) or value <= 0:
        return [ValidationError(field=field, message=f"{field} must be an integer > 0.")]
    return []


def _validate_non_negative_int(field: str, value: Any) -> list[ValidationError]:
    if not isinstance(value, int) or value < 0:
        return [ValidationError(field=field, message=f"{field} must be an integer >= 0.")]
    return []


def _validate_float_range(field: str, value: Any, min_value: float, max_value: float) -> list[ValidationError]:
    if not isinstance(value, (int, float)):
        return [ValidationError(field=field, message=f"{field} must be a number.")]
    if float(value) < min_value or float(value) > max_value:
        return [
            ValidationError(
                field=field, message=f"{field} must be between {min_value} and {max_value}."
            )
        ]
    return []
