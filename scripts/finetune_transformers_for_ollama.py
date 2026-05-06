#!/usr/bin/env python3
"""Source-only fine-tuning CLI for Ollama Transformers workflows.

This utility is intentionally source-only: it is not bundled into the
PyInstaller/exe package and is intended to be run from a source checkout with
`poetry run python scripts/finetune_transformers_for_ollama.py`.

Supports LoRA/QLoRA fine-tuning with the Transformers or Unsloth backends,
adapter merging, GGUF export via llama.cpp, and Ollama model creation.
Use --dry-run to validate inputs and inspect the staged workflow without
executing training, or --run to execute the full pipeline.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, TypeAlias, cast

ArgumentParser = argparse.ArgumentParser
Namespace = argparse.Namespace
DatasetFormat = Literal["messages", "prompt-completion"]
DiagnosticLevel = Literal["ok", "warning", "error"]
JsonObject: TypeAlias = dict[str, object]
SUPPORTED_DATASET_FORMATS = ("messages", "prompt-completion", "auto")
MAX_VALIDATION_ERRORS = 5
OPTIONAL_PACKAGES = ("torch", "transformers", "datasets", "trl", "peft", "bitsandbytes", "unsloth")
REQUIRED_BACKEND_PACKAGES: dict[str, tuple[str, ...]] = {
    "transformers": ("torch", "transformers", "datasets", "trl", "peft"),
    "unsloth": ("torch", "transformers", "datasets", "trl", "peft", "unsloth"),
}

_find_spec = importlib.util.find_spec
_which = shutil.which
_urlopen = urllib.request.urlopen
_subprocess_run = subprocess.run


class HttpResponse(Protocol):
    status: int

    def __enter__(self) -> "HttpResponse": ...

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> object: ...


@dataclass(frozen=True)
class DatasetValidationResult:
    path: Path
    dataset_format: DatasetFormat
    record_count: int


@dataclass(frozen=True)
class Diagnostic:
    key: str
    level: DiagnosticLevel
    message: str


@dataclass(frozen=True)
class PlannedStep:
    stage: str
    description: str
    commands: tuple[str, ...] = ()
    skipped: bool = False


@dataclass(frozen=True)
class TrainingConfig:
    base_model: str
    backend: str
    method: str
    dataset_path: Path
    dataset_format: DatasetFormat
    output_dir: Path
    adapter_dir: Path
    merged_dir: Path
    gguf_path: Path
    modelfile_path: Path
    ollama_model: str
    quantization: str
    learning_rate: float = 2e-4
    batch_size: int = 2
    max_steps: int = 1000
    gradient_accumulation_steps: int = 4
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    max_seq_length: int = 4096


def _summarize_validation_errors(errors: list[str], total_errors: int) -> str:
    if total_errors > len(errors):
        errors.append(f"... and {total_errors - len(errors)} more validation error(s)")
    return "; ".join(errors)


def _add_validation_error(errors: list[str], message: str) -> None:
    if len(errors) < MAX_VALIDATION_ERRORS:
        errors.append(message)


def _detect_record_format(record: object) -> DatasetFormat | None:
    if not isinstance(record, dict):
        return None
    if "messages" in record:
        return "messages"
    if "prompt" in record or "completion" in record:
        return "prompt-completion"
    return None


def _validate_messages_record(record: object) -> str | None:
    if not isinstance(record, dict):
        return "record must be a JSON object"
    json_record = cast(JsonObject, record)
    messages = json_record.get("messages")
    if not isinstance(messages, list) or not messages:
        return "messages must be a non-empty list"
    message_items = cast(list[object], messages)
    for index, message in enumerate(message_items):
        if not isinstance(message, dict):
            return f"messages[{index}] must be an object"
        json_message = cast(JsonObject, message)
        if not isinstance(json_message.get("role"), str):
            return f"messages[{index}].role must be a string"
        if not isinstance(json_message.get("content"), str):
            return f"messages[{index}].content must be a string"
    return None


def _validate_prompt_completion_record(record: object) -> str | None:
    if not isinstance(record, dict):
        return "record must be a JSON object"
    json_record = cast(JsonObject, record)
    if not isinstance(json_record.get("prompt"), str):
        return "prompt must be a string"
    if not isinstance(json_record.get("completion"), str):
        return "completion must be a string"
    return None


def _validate_record(record: object, dataset_format: DatasetFormat) -> str | None:
    if dataset_format == "messages":
        return _validate_messages_record(record)
    return _validate_prompt_completion_record(record)


def validate_dataset(
    path: Path,
    dataset_format: str = "auto",
) -> DatasetValidationResult:
    """Validate a local JSONL fine-tuning dataset without loading ML packages."""
    if dataset_format not in SUPPORTED_DATASET_FORMATS:
        choices = ", ".join(SUPPORTED_DATASET_FORMATS)
        raise ValueError(f"Unsupported dataset format '{dataset_format}'. Expected one of: {choices}")
    requested_format = cast(DatasetFormat | Literal["auto"], dataset_format)

    errors: list[str] = []
    total_errors = 0
    inferred_format: DatasetFormat | None = None
    record_count = 0

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"Unable to read dataset: {exc.strerror or exc}") from exc

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue

        try:
            record = cast(object, json.loads(line))
        except json.JSONDecodeError as exc:
            total_errors += 1
            _add_validation_error(
                errors,
                f"line {line_number}: invalid JSON ({exc.msg})",
            )
            continue

        expected_format: DatasetFormat
        if requested_format == "auto":
            detected_format = _detect_record_format(record)
            if detected_format is None:
                total_errors += 1
                _add_validation_error(
                    errors,
                    f"line {line_number}: unable to infer dataset format from required keys",
                )
                continue
            if inferred_format is None:
                inferred_format = detected_format
            elif detected_format != inferred_format:
                total_errors += 1
                _add_validation_error(
                    errors,
                    f"line {line_number}: mixed dataset format; expected {inferred_format}",
                )
                continue
            expected_format = inferred_format
        else:
            expected_format = requested_format

        validation_error = _validate_record(record, expected_format)
        if validation_error is not None:
            total_errors += 1
            _add_validation_error(errors, f"line {line_number}: {validation_error}")
            continue

        record_count += 1

    if record_count == 0 and total_errors == 0:
        raise ValueError("Dataset contains no valid records")
    if total_errors:
        raise ValueError(_summarize_validation_errors(errors, total_errors))

    validated_format = inferred_format if requested_format == "auto" else requested_format
    if validated_format is None:
        raise ValueError("Dataset contains no valid records")
    return DatasetValidationResult(path=path, dataset_format=validated_format, record_count=record_count)


def check_optional_dependencies(packages: Sequence[str] = OPTIONAL_PACKAGES) -> dict[str, Diagnostic]:
    """Check optional ML packages without importing them."""
    diagnostics: dict[str, Diagnostic] = {}
    for package in packages:
        if _find_spec(package) is None:
            diagnostics[package] = Diagnostic(
                key=f"package:{package}",
                level="warning",
                message=f"Optional package '{package}' is not installed.",
            )
        else:
            diagnostics[package] = Diagnostic(
                key=f"package:{package}",
                level="ok",
                message=f"Optional package '{package}' is installed.",
            )
    return diagnostics


def _check_ollama_server(timeout_seconds: float = 1.0) -> Diagnostic:
    try:
        response = cast(HttpResponse, _urlopen("http://127.0.0.1:11434/api/tags", timeout=timeout_seconds))
        with response:
            status = response.status
    except (OSError, urllib.error.URLError) as exc:
        return Diagnostic(
            key="ollama_server",
            level="warning",
            message=f"Ollama server is unreachable at 127.0.0.1:11434 ({exc}).",
        )
    if 200 <= int(status) < 500:
        return Diagnostic(
            key="ollama_server",
            level="ok",
            message="Ollama server responded at 127.0.0.1:11434.",
        )
    return Diagnostic(
        key="ollama_server",
        level="warning",
        message=f"Ollama server returned HTTP status {status}.",
    )


def _is_non_empty_directory(path: Path) -> bool:
    return path.is_dir() and any(path.iterdir())


def check_environment(options: Namespace, dependencies: dict[str, Diagnostic] | None = None) -> list[Diagnostic]:
    """Collect lightweight, mockable environment diagnostics for the planned workflow."""
    dependency_diagnostics = dependencies if dependencies is not None else check_optional_dependencies()
    diagnostics: list[Diagnostic] = []

    python_version = (sys.version_info.major, sys.version_info.minor)
    if python_version >= (3, 14):
        diagnostics.append(
            Diagnostic(
                key="python_version",
                level="warning",
                message=(
                    f"Python {sys.version_info.major}.{sys.version_info.minor} is supported by the app, "
                    "but some ML training stacks may lag behind Python 3.14."
                ),
            )
        )
    else:
        diagnostics.append(
            Diagnostic(
                key="python_version",
                level="ok",
                message=f"Python {sys.version_info.major}.{sys.version_info.minor} detected for the source-only helper.",
            )
        )

    backend = cast(str, options.backend)
    missing_backend_packages = [
        package
        for package in REQUIRED_BACKEND_PACKAGES[backend]
        if dependency_diagnostics[package].level != "ok"
    ]
    if missing_backend_packages:
        diagnostics.append(
            Diagnostic(
                key="backend",
                level="error" if backend == "unsloth" else "warning",
                message=(
                    f"Backend '{backend}' is unavailable until optional package(s) are installed: "
                    f"{', '.join(missing_backend_packages)}."
                ),
            )
        )
    else:
        diagnostics.append(
            Diagnostic(
                key="backend",
                level="ok",
                message=f"Backend '{backend}' dependencies are present.",
            )
        )

    if cast(bool, options.run_ollama_create):
        if _which("ollama") is None:
            diagnostics.append(
                Diagnostic(
                    key="ollama_cli",
                    level="warning",
                    message="Ollama CLI is missing; install Ollama before running `ollama create`.",
                )
            )
        else:
            diagnostics.append(
                Diagnostic(key="ollama_cli", level="ok", message="Ollama CLI is available on PATH.")
            )
        diagnostics.append(_check_ollama_server())
    else:
        diagnostics.append(
            Diagnostic(
                key="ollama_cli",
                level="warning",
                message="Ollama create stage is planned but disabled unless --run-ollama-create is passed.",
            )
        )

    llama_cpp_path = cast(Path | None, options.llama_cpp_path)
    if cast(bool, options.export_gguf):
        if llama_cpp_path is None or not llama_cpp_path.exists():
            diagnostics.append(
                Diagnostic(
                    key="llama_cpp_path",
                    level="warning",
                    message="llama.cpp path is missing; GGUF export is planned but cannot run yet.",
                )
            )
        else:
            diagnostics.append(
                Diagnostic(key="llama_cpp_path", level="ok", message=f"llama.cpp path exists: {llama_cpp_path}")
            )
    else:
        diagnostics.append(
            Diagnostic(
                key="llama_cpp_path",
                level="warning",
                message="GGUF export is described for Ollama import; pass --export-gguf and --llama-cpp-path to enable it later.",
            )
        )

    output_dir = cast(Path | None, options.output_dir)
    if output_dir is not None and _is_non_empty_directory(output_dir):
        level: DiagnosticLevel = "ok" if cast(bool, options.overwrite) else "error"
        message = (
            f"Output directory exists and is non-empty: {output_dir}."
            if cast(bool, options.overwrite)
            else f"Output directory exists and is non-empty: {output_dir}. Pass --overwrite to continue."
        )
        diagnostics.append(Diagnostic(key="output_dir", level=level, message=message))
    elif output_dir is not None:
        diagnostics.append(Diagnostic(key="output_dir", level="ok", message=f"Output directory is safe to use: {output_dir}"))

    return diagnostics


def generate_training_config(options: Namespace, dataset: DatasetValidationResult) -> TrainingConfig:
    output_dir = cast(Path, options.output_dir)
    modelfile_path = cast(Path | None, options.modelfile_path) or output_dir / "Modelfile"
    quantization = cast(str, options.quantization).upper()
    return TrainingConfig(
        base_model=cast(str, options.base_model),
        backend=cast(str, options.backend),
        method=cast(str, options.method),
        dataset_path=dataset.path,
        dataset_format=dataset.dataset_format,
        output_dir=output_dir,
        adapter_dir=output_dir / "adapter",
        merged_dir=output_dir / "merged",
        gguf_path=output_dir / f"model-{quantization}.gguf",
        modelfile_path=modelfile_path,
        ollama_model=cast(str, options.ollama_model),
        quantization=cast(str, options.quantization),
        learning_rate=cast(float, options.learning_rate),
        batch_size=cast(int, options.batch_size),
        max_steps=cast(int, options.max_steps),
        gradient_accumulation_steps=cast(int, options.gradient_accumulation_steps),
        lora_r=cast(int, options.lora_r),
        lora_alpha=cast(int, options.lora_alpha),
        lora_dropout=cast(float, options.lora_dropout),
        max_seq_length=cast(int, options.max_seq_length),
    )


def generate_modelfile_content(
    config: TrainingConfig,
    temperature: float = 0.7,
    num_ctx: int = 4096,
    system_prompt: str = "",
) -> str:
    """Generate deterministic Ollama Modelfile content from a TrainingConfig."""
    gguf_basename = config.gguf_path.name
    lines = [
        f"FROM ./{gguf_basename}",
        f"PARAMETER temperature {temperature}",
        f"PARAMETER num_ctx {num_ctx}",
    ]
    if system_prompt:
        lines.append(f'SYSTEM """{system_prompt}"""')
    else:
        lines.append('SYSTEM """You are a helpful Live2oder assistant."""')
    lines.append("")
    return "\n".join(lines)


def backup_and_update_config(
    config_path: Path,
    ollama_model: str,
    *,
    backup: bool = True,
    model_name: str = "",
) -> Path:
    """Create a backup of config.json and append a non-default Ollama model entry.

    Returns the config_path that was updated.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    if backup:
        timestamp = __import__("datetime").datetime.now().strftime("%Y%m%dT%H%M%S")
        backup_path = config_path.with_suffix(f".json.bak.{timestamp}")
        config_path.replace(backup_path)
        original_content = backup_path.read_text(encoding="utf-8")
        config_path.write_text(original_content, encoding="utf-8")
    else:
        original_content = config_path.read_text(encoding="utf-8")

    config_data = json.loads(original_content)
    models: list[dict[str, object]] = config_data.setdefault("models", [])

    entry_name = model_name or ollama_model
    new_entry: dict[str, object] = {
        "name": entry_name,
        "model": ollama_model,
        "type": "ollama",
        "system_prompt": "You are a helpful Live2oder assistant.",
        "default": False,
        "streaming": True,
        "options": {"temperature": 0.7},
    }
    models.append(new_entry)
    config_data["models"] = models

    with config_path.open("w", encoding="utf-8") as handle:
        json.dump(config_data, handle, indent=4, ensure_ascii=False)
    return config_path


def run_modelfile_generation(config: TrainingConfig, overwrite: bool = False) -> Path:
    """Write the Modelfile to disk, returning its path."""
    if config.modelfile_path.exists() and not overwrite:
        raise FileExistsError(
            f"Modelfile already exists at {config.modelfile_path}. Pass --overwrite to replace."
        )
    content = generate_modelfile_content(config)
    config.modelfile_path.write_text(content, encoding="utf-8")
    return config.modelfile_path


def plan_training_commands(config: TrainingConfig) -> list[PlannedStep]:
    method_label = "QLoRA" if config.method == "qlora" else "LoRA"
    command = (
        "python -m trl.sft_train "
        f"--model_name_or_path {config.base_model} "
        f"--dataset_path {config.dataset_path} "
        f"--output_dir {config.adapter_dir} "
        f"--peft_method {config.method}"
    )
    if config.backend == "unsloth":
        command = "python -m unsloth.cli.train " + command.removeprefix("python -m trl.sft_train ")
    return [
        PlannedStep(
            stage=f"{method_label} adapter training",
            description=(
                f"Prepare adapter-only training with backend '{config.backend}' for "
                f"{config.dataset_format} JSONL data."
            ),
            commands=(command,),
        )
    ]


def plan_merge_export_commands(config: TrainingConfig, options: Namespace) -> list[PlannedStep]:
    steps = [
        PlannedStep(
            stage="Merge/export",
            description=(
                "Merge the trained adapter into a local Transformers model before preparing artifacts for Ollama import."
                if cast(bool, options.merge)
                else "Adapter merge is not requested; keep adapter and base model separate until a future merge step."
            ),
            commands=(
                f"python -m peft.merge_adapter --base-model {config.base_model} --adapter {config.adapter_dir} --output {config.merged_dir}",
            )
            if cast(bool, options.merge)
            else (),
            skipped=not cast(bool, options.merge),
        )
    ]
    steps.append(
        PlannedStep(
            stage="GGUF/Modelfile",
            description=(
                f"Convert merged model to {config.quantization.upper()} GGUF at {config.gguf_path} and prepare Modelfile at {config.modelfile_path}."
                if cast(bool, options.export_gguf)
                else f"Plan GGUF path {config.gguf_path} and Modelfile path {config.modelfile_path}; conversion is disabled until --export-gguf is passed."
            ),
            commands=(
                f"python <llama.cpp>/convert_hf_to_gguf.py {config.merged_dir} --outfile {config.gguf_path} --outtype {config.quantization}",
            )
            if cast(bool, options.export_gguf)
            else (),
            skipped=not cast(bool, options.export_gguf),
        )
    )
    steps.append(
        PlannedStep(
            stage="Ollama create",
            description=(
                f"Create Ollama model '{config.ollama_model}' from the planned Modelfile."
                if cast(bool, options.run_ollama_create)
                else f"Ollama create is skipped by default; planned model name is '{config.ollama_model}'."
            ),
            commands=(f"ollama create {config.ollama_model} -f {config.modelfile_path}",)
            if cast(bool, options.run_ollama_create)
            else (),
            skipped=not cast(bool, options.run_ollama_create),
        )
    )
    steps.append(
        PlannedStep(
            stage="Config behavior",
            description=(
                f"Config update requested for {cast(Path | None, options.config_path) or 'config.json'}; backup requested={cast(bool, options.backup_config)}."
                if cast(bool, options.update_config)
                else "Config update skipped; non-interactive mode never modifies config unless --update-config is passed."
            ),
            skipped=not cast(bool, options.update_config),
        )
    )
    return steps


# ---------------------------------------------------------------------------
# Execution helpers
# ---------------------------------------------------------------------------


def _run_subprocess(
    cmd: Sequence[str],
    *,
    timeout: int | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess command with captured output.

    Raises RuntimeError on FileNotFoundError or TimeoutExpired.
    Caller is responsible for checking returncode.
    """
    try:
        return _subprocess_run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd, check=False)
    except FileNotFoundError:
        raise RuntimeError(f"Command not found: {cmd[0]}")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Command timed out after {timeout}s: {' '.join(cmd)}")


def _format_record(record: dict[str, object], dataset_format: DatasetFormat, tokenizer: object) -> str:
    """Format a single JSONL record into a training text string."""
    if dataset_format == "messages":
        messages = cast(list[object], record["messages"])
        return cast(str, tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False))  # type: ignore[union-attr]
    return cast(str, record["prompt"]) + cast(str, record["completion"])


def _load_base_model(config: TrainingConfig) -> tuple[object, object]:
    """Load base model with LoRA/QLoRA and return (model, tokenizer)."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    cuda_available = torch.cuda.is_available()
    torch_dtype = torch.bfloat16 if cuda_available else torch.float32
    device_map = "auto" if cuda_available else None

    tokenizer = AutoTokenizer.from_pretrained(config.base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    if config.backend == "unsloth":
        from unsloth import FastLanguageModel

        model, tokenizer_unsloth = FastLanguageModel.from_pretrained(
            model_name=config.base_model,
            max_seq_length=config.max_seq_length,
            dtype=None,
            load_in_4bit=(config.method == "qlora"),
        )
        model = FastLanguageModel.get_peft_model(
            model,
            r=config.lora_r,
            target_modules=[
                "q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj",
            ],
            lora_alpha=config.lora_alpha,
            lora_dropout=0,
            bias="none",
            use_gradient_checkpointing="unsloth",
        )
        return model, tokenizer_unsloth

    # Transformers backend
    from peft import LoraConfig, TaskType, get_peft_model

    model_kwargs: dict[str, object] = {
        "torch_dtype": torch_dtype,
        "device_map": device_map,
    }

    if config.method == "qlora":
        from transformers import BitsAndBytesConfig

        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )

    model = AutoModelForCausalLM.from_pretrained(config.base_model, **model_kwargs)  # type: ignore[arg-type]

    if config.method == "qlora":
        from peft import prepare_model_for_kbit_training

        model = prepare_model_for_kbit_training(model)

    lora_config = LoraConfig(
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(model, lora_config)
    return model, tokenizer


def prepare_dataset(config: TrainingConfig, tokenizer: object) -> object:
    """Load and format the JSONL dataset for SFT training.

    Returns a HuggingFace Dataset with a single "text" column.
    """
    import json as _json

    from datasets import Dataset

    records: list[dict[str, object]] = []
    for line in config.dataset_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(cast(dict[str, object], _json.loads(line)))

    texts = [_format_record(record, config.dataset_format, tokenizer) for record in records]
    return Dataset.from_dict({"text": texts})


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------


def run_training(config: TrainingConfig) -> Path:
    """Execute LoRA/QLoRA fine-tuning and return the adapter directory path."""
    import torch
    from transformers import TrainingArguments
    from trl import SFTTrainer

    print(f"\n[1/5] Loading base model '{config.base_model}' ({config.backend}/{config.method})...")
    model, tokenizer = _load_base_model(config)

    print(f"[2/5] Loading dataset from {config.dataset_path}...")
    dataset = prepare_dataset(config, tokenizer)
    print(f"  {len(dataset)} records loaded")  # type: ignore[arg-type]

    config.adapter_dir.mkdir(parents=True, exist_ok=True)

    cuda_available = torch.cuda.is_available()
    if not cuda_available:
        print("  WARNING: CUDA not available, training on CPU will be very slow.")

    training_args = TrainingArguments(
        output_dir=str(config.adapter_dir),
        per_device_train_batch_size=config.batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        learning_rate=config.learning_rate,
        max_steps=config.max_steps,
        save_strategy="steps",
        save_steps=min(config.max_steps // 2, 500),
        logging_steps=10,
        report_to="none",
        push_to_hub=False,
        remove_unused_columns=False,
        fp16=False,
        bf16=cuda_available,
        optim="adamw_torch",
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        args=training_args,
        train_dataset=dataset,  # type: ignore[arg-type]
        max_seq_length=config.max_seq_length,
        dataset_text_field="text",
    )

    print(f"[3/5] Training (max_steps={config.max_steps}, batch_size={config.batch_size})...")
    trainer.train()

    print(f"[4/5] Saving adapter to {config.adapter_dir}...")
    trainer.save_model(str(config.adapter_dir))
    tokenizer.save_pretrained(str(config.adapter_dir))  # type: ignore[attr-defined]

    print("[5/5] Training complete.")
    return config.adapter_dir


def merge_adapter(config: TrainingConfig) -> Path:
    """Merge the trained LoRA adapter back into the base model."""
    if not config.adapter_dir.exists():
        raise FileNotFoundError(f"Adapter directory not found: {config.adapter_dir}")

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    print(f"\n[Merge] Loading base model and adapter from {config.adapter_dir}...")

    cuda_available = torch.cuda.is_available()
    torch_dtype = torch.bfloat16 if cuda_available else torch.float32
    device_map = "auto" if cuda_available else None

    model = AutoModelForCausalLM.from_pretrained(
        config.base_model,
        torch_dtype=torch_dtype,
        device_map=device_map,
    )
    model = PeftModel.from_pretrained(model, str(config.adapter_dir))
    model = model.merge_and_unload()

    config.merged_dir.mkdir(parents=True, exist_ok=True)
    print(f"[Merge] Saving merged model to {config.merged_dir}...")
    model.save_pretrained(str(config.merged_dir))

    tokenizer = AutoTokenizer.from_pretrained(config.base_model)
    tokenizer.save_pretrained(str(config.merged_dir))

    return config.merged_dir


def export_gguf(config: TrainingConfig, llama_cpp_path: Path) -> Path:
    """Convert the merged model to GGUF format via llama.cpp."""
    convert_script = llama_cpp_path / "convert_hf_to_gguf.py"
    if not convert_script.exists():
        raise FileNotFoundError(
            f"llama.cpp conversion script not found: {convert_script}\n"
            "Install llama.cpp and pass --llama-cpp-path pointing to its root directory."
        )
    if not config.merged_dir.exists():
        raise FileNotFoundError(f"Merged model directory not found: {config.merged_dir}")

    config.gguf_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(convert_script),
        str(config.merged_dir),
        "--outfile", str(config.gguf_path),
        "--outtype", config.quantization,
    ]
    print(f"\n[GGUF] Converting merged model to {config.quantization} GGUF...")
    print(f"  {' '.join(cmd)}")

    result = _run_subprocess(cmd, timeout=3600)
    if result.returncode != 0:
        raise RuntimeError(
            f"GGUF conversion failed (exit {result.returncode}):\n{result.stderr}"
        )
    print(f"[GGUF] Saved to {config.gguf_path}")
    return config.gguf_path


def ollama_create_model(config: TrainingConfig) -> str:
    """Register the model in Ollama via `ollama create`."""
    if not config.modelfile_path.exists():
        raise FileNotFoundError(f"Modelfile not found: {config.modelfile_path}")

    cmd = ["ollama", "create", config.ollama_model, "-f", str(config.modelfile_path)]
    print(f"\n[Ollama] Creating model '{config.ollama_model}'...")
    print(f"  {' '.join(cmd)}")

    result = _run_subprocess(cmd, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(
            f"ollama create failed (exit {result.returncode}):\n{result.stderr}"
        )
    print(f"[Ollama] Model '{config.ollama_model}' created successfully.")
    return config.ollama_model


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_execution(options: Namespace) -> int:
    """Execute the full fine-tuning pipeline (--run path)."""
    # 0. Validate required inputs
    try:
        _require_required_inputs(options)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    # 1. Validate dataset
    try:
        dataset = validate_dataset(
            cast(Path, options.dataset),
            cast(str, options.dataset_format),
        )
    except ValueError as exc:
        print(f"ERROR: Dataset validation failed: {exc}")
        return 2

    # 2. Check dependencies
    dependencies = check_optional_dependencies()
    print("Dependency check:")
    for dep in dependencies.values():
        status = "OK" if dep.level == "ok" else "WARNING"
        print(f"  [{status}] {dep.message}")

    # 3. Check environment
    environment = check_environment(options, dependencies)
    blocking_errors = [d.message for d in environment if d.level == "error"]
    if blocking_errors:
        for message in blocking_errors:
            print(f"ERROR: {message}")
        return 2

    has_warnings = [d for d in environment if d.level == "warning"]
    if has_warnings:
        for d in has_warnings:
            print(f"WARNING: {d.message}")

    # 4. Generate config
    config = generate_training_config(options, dataset)

    # 5. Create output directories
    config.output_dir.mkdir(parents=True, exist_ok=True)
    if config.output_dir.exists() and not cast(bool, options.overwrite):
        contents = list(config.output_dir.iterdir())
        if contents:
            print(
                f"ERROR: Output directory exists and is non-empty: {config.output_dir}. "
                "Pass --overwrite to continue."
            )
            return 2

    # 6. Training
    try:
        run_training(config)
    except Exception as exc:
        print(f"ERROR: Training failed: {exc}")
        return 1

    # 7. Optional: merge adapter
    if cast(bool, options.merge):
        try:
            merge_adapter(config)
        except Exception as exc:
            print(f"ERROR: Adapter merge failed: {exc}")
            return 1

    # 8. Optional: GGUF export
    if cast(bool, options.export_gguf):
        llama_cpp_path = cast(Path | None, options.llama_cpp_path)
        if llama_cpp_path is None:
            print("ERROR: --llama-cpp-path is required for GGUF export.")
            return 2
        try:
            export_gguf(config, llama_cpp_path)
        except Exception as exc:
            print(f"ERROR: GGUF export failed: {exc}")
            return 1

    # 9. Generate Modelfile
    try:
        modelfile_path = run_modelfile_generation(
            config, overwrite=cast(bool, options.overwrite)
        )
        print(f"\n[Modelfile] Written to {modelfile_path}")
    except FileExistsError as exc:
        print(f"ERROR: {exc}")
        return 2

    # 10. Optional: Ollama create
    if cast(bool, options.run_ollama_create):
        try:
            ollama_create_model(config)
        except Exception as exc:
            print(f"ERROR: Ollama model creation failed: {exc}")
            return 1

    # 11. Optional: Update config
    if cast(bool, options.update_config):
        config_path = cast(Path | None, options.config_path) or Path("config.json")
        try:
            backup_and_update_config(
                config_path,
                config.ollama_model,
                backup=cast(bool, options.backup_config),
            )
            print(f"\n[Config] Updated {config_path} with model '{config.ollama_model}'.")
        except Exception as exc:
            print(f"ERROR: Config update failed: {exc}")
            return 1

    print("\n=== Fine-tuning pipeline completed successfully ===")
    return 0


def _require_required_inputs(options: Namespace) -> None:
    required_values: tuple[tuple[str, object | None], ...] = (
        ("--base-model", cast(object | None, getattr(options, "base_model"))),
        ("--dataset", cast(object | None, getattr(options, "dataset"))),
        ("--output-dir", cast(object | None, getattr(options, "output_dir"))),
        ("--ollama-model", cast(object | None, getattr(options, "ollama_model"))),
    )
    missing = [flag for flag, value in required_values if value is None]
    if missing:
        raise ValueError(f"Missing required arguments: {', '.join(missing)}")


def _print_diagnostics(title: str, diagnostics: Sequence[Diagnostic]) -> None:
    print(title)
    for diagnostic in diagnostics:
        print(f"  [{diagnostic.level.upper()}] {diagnostic.message}")


def _print_steps(steps: Sequence[PlannedStep]) -> None:
    for index, step in enumerate(steps, start=1):
        status = "skipped" if step.skipped else "planned"
        print(f"{index}. {step.stage} ({status})")
        print(f"   {step.description}")
        for command in step.commands:
            print(f"   command: {command}")


def run_dry_run(options: Namespace) -> int:
    _require_required_inputs(options)
    dataset = validate_dataset(cast(Path, options.dataset), cast(str, options.dataset_format))
    dependencies = check_optional_dependencies()
    environment = check_environment(options, dependencies)
    blocking_errors = [diagnostic.message for diagnostic in environment if diagnostic.level == "error"]
    if blocking_errors:
        for message in blocking_errors:
            print(f"ERROR: {message}")
        return 2

    config = generate_training_config(options, dataset)
    print("Source-only Ollama Transformers fine-tuning dry run")
    print("No training, Ollama, subprocess, GPU, network model download, or config mutation will run.")
    _print_diagnostics("Environment diagnostics:", list(dependencies.values()) + environment)
    print("Dataset validation:")
    print(
        f"  [OK] {dataset.path} contains {dataset.record_count} valid {dataset.dataset_format} record(s)."
    )
    steps = plan_training_commands(config) + plan_merge_export_commands(config, options)
    print("Staged plan:")
    _print_steps(steps)
    print("\nModelfile preview:")
    print(generate_modelfile_content(config))
    if cast(bool, options.update_config):
        config_path = cast(Path | None, options.config_path) or Path("config.json")
        print(f"\nConfig update: would append model entry to {config_path}")
        print(f"  Backup requested: {cast(bool, options.backup_config)}")
        print(f"  Model name: {config.ollama_model}")
        print("  Non-default entry, type=ollama")
    return 0


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        description=(
            "Source-only Ollama Transformers fine-tuning utility skeleton. "
            "This script is not packaged into the PyInstaller/exe build and "
            "must be run from a source checkout."
        )
    )
    _ = parser.add_argument(
        "--wizard",
        action="store_true",
        help="start an interactive setup wizard in a future implementation",
    )
    _ = parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show the planned source-only workflow without training or writing files",
    )
    _ = parser.add_argument(
        "--run",
        action="store_true",
        help="execute the full fine-tuning pipeline (training, merge, export, ollama create)",
    )
    _ = parser.add_argument(
        "--base-model",
        help="base Hugging Face or local Transformers model identifier",
    )
    _ = parser.add_argument(
        "--dataset",
        type=Path,
        help="path to the fine-tuning dataset for a future training run",
    )
    _ = parser.add_argument(
        "--dataset-format",
        choices=("messages", "prompt-completion", "auto"),
        default="auto",
        help="dataset schema to expect; default: auto",
    )
    _ = parser.add_argument(
        "--output-dir",
        type=Path,
        help="directory for future adapter, merge, and export artifacts",
    )
    _ = parser.add_argument(
        "--ollama-model",
        help="target Ollama model name for a future create step",
    )
    _ = parser.add_argument(
        "--backend",
        choices=("transformers", "unsloth"),
        default="transformers",
        help="fine-tuning backend to use later; default: transformers",
    )
    _ = parser.add_argument(
        "--method",
        choices=("lora", "qlora"),
        default="lora",
        help="adapter fine-tuning method to use later; default: lora",
    )
    _ = parser.add_argument(
        "--merge",
        action="store_true",
        help="request future adapter merge after fine-tuning",
    )
    _ = parser.add_argument(
        "--export-gguf",
        action="store_true",
        help="request future GGUF export for Ollama import",
    )
    _ = parser.add_argument(
        "--llama-cpp-path",
        type=Path,
        help="path to llama.cpp tooling for a future GGUF export",
    )
    _ = parser.add_argument(
        "--modelfile-path",
        type=Path,
        help="path for a future generated or supplied Ollama Modelfile",
    )
    _ = parser.add_argument(
        "--run-ollama-create",
        action="store_true",
        help="run `ollama create` in a future implementation; default: disabled",
    )
    _ = parser.add_argument(
        "--update-config",
        action="store_true",
        help="update app config in a future implementation; default: disabled",
    )
    _ = parser.add_argument(
        "--config-path",
        type=Path,
        help="config file path for a future optional config update",
    )
    _ = parser.add_argument(
        "--backup-config",
        action="store_true",
        help="create a config backup before a future optional config update",
    )
    _ = parser.add_argument(
        "--overwrite",
        action="store_true",
        help="allow future steps to replace existing generated artifacts",
    )
    _ = parser.add_argument(
        "--quantization",
        choices=("q4_k_m", "q8_0", "f16"),
        default="q4_k_m",
        help="future GGUF quantization target; default: q4_k_m",
    )
    _ = parser.add_argument(
        "--learning-rate",
        type=float,
        default=2e-4,
        help="learning rate for training; default: 2e-4",
    )
    _ = parser.add_argument(
        "--batch-size",
        type=int,
        default=2,
        help="per-device training batch size; default: 2",
    )
    _ = parser.add_argument(
        "--max-steps",
        type=int,
        default=1000,
        help="maximum training steps; default: 1000",
    )
    _ = parser.add_argument(
        "--gradient-accumulation-steps",
        type=int,
        default=4,
        help="gradient accumulation steps; default: 4",
    )
    _ = parser.add_argument(
        "--lora-r",
        type=int,
        default=16,
        help="LoRA rank; default: 16",
    )
    _ = parser.add_argument(
        "--lora-alpha",
        type=int,
        default=32,
        help="LoRA alpha; default: 32",
    )
    _ = parser.add_argument(
        "--lora-dropout",
        type=float,
        default=0.05,
        help="LoRA dropout; default: 0.05",
    )
    _ = parser.add_argument(
        "--max-seq-length",
        type=int,
        default=4096,
        help="maximum sequence length for tokenization; default: 4096",
    )
    return parser


def parse_options(argv: Sequence[str] | None = None) -> Namespace:
    return build_parser().parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    options = parse_options(argv)
    try:
        if cast(bool, options.dry_run):
            return run_dry_run(options)
        if cast(bool, options.run):
            return run_execution(options)
        if cast(bool, options.wizard):
            print("Interactive wizard is planned for a future implementation; no training was run.")
            return 1
        message = (
            "No action specified. "
            "Run with --dry-run to validate inputs and inspect the staged workflow, "
            "or --run to execute training."
        )
        print(message)
        return 1
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
