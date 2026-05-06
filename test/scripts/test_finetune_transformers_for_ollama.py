import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.finetune_transformers_for_ollama as finetune
from scripts.finetune_transformers_for_ollama import (
    check_environment,
    check_optional_dependencies,
    main,
    parse_options,
    validate_dataset,
)


FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "finetune"


def test_parse_options_preserves_task_one_defaults():
    options = parse_options([])

    assert getattr(options, "backend") == "transformers"
    assert getattr(options, "method") == "lora"
    assert getattr(options, "dataset_format") == "auto"
    assert getattr(options, "quantization") == "q4_k_m"
    assert getattr(options, "run_ollama_create") is False
    assert getattr(options, "update_config") is False


@pytest.mark.parametrize(
    ("argument", "bad_value"),
    [
        ("--backend", "bad-backend"),
        ("--method", "full"),
        ("--dataset-format", "chatml"),
        ("--quantization", "q2"),
    ],
)
def test_parse_options_rejects_required_choices(argument: str, bad_value: str):
    with pytest.raises(SystemExit):
        _ = parse_options([argument, bad_value])


def test_validate_dataset_accepts_messages_fixture():
    result = validate_dataset(FIXTURES_DIR / "messages.jsonl", "messages")

    assert result.dataset_format == "messages"
    assert result.record_count == 2


def test_validate_dataset_accepts_prompt_completion_fixture():
    result = validate_dataset(
        FIXTURES_DIR / "prompt_completion.jsonl",
        "prompt-completion",
    )

    assert result.dataset_format == "prompt-completion"
    assert result.record_count == 2


def test_validate_dataset_auto_detects_messages_fixture():
    result = validate_dataset(FIXTURES_DIR / "messages.jsonl")

    assert result.dataset_format == "messages"
    assert result.record_count == 2


def test_validate_dataset_auto_detects_prompt_completion_fixture():
    result = validate_dataset(FIXTURES_DIR / "prompt_completion.jsonl")

    assert result.dataset_format == "prompt-completion"
    assert result.record_count == 2


def test_validate_dataset_rejects_invalid_json_with_line_number():
    with pytest.raises(ValueError, match="line 1: invalid JSON"):
        _ = validate_dataset(FIXTURES_DIR / "invalid_json.jsonl")


def test_validate_dataset_rejects_missing_fields_without_raw_record_content():
    with pytest.raises(
        ValueError,
        match=r"line 1: messages\[0\]\.content must be a string",
    ) as exc_info:
        _ = validate_dataset(FIXTURES_DIR / "missing_fields.jsonl", "messages")

    assert "Missing completion" not in str(exc_info.value)


def test_validate_dataset_rejects_empty_file():
    with pytest.raises(ValueError, match="Dataset contains no valid records"):
        _ = validate_dataset(FIXTURES_DIR / "empty.jsonl")


def test_validate_dataset_rejects_blank_only_file(tmp_path: Path):
    dataset_path = tmp_path / "blank.jsonl"
    _ = dataset_path.write_text("\n  \n\t\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Dataset contains no valid records"):
        _ = validate_dataset(dataset_path)


def test_validate_dataset_rejects_mixed_formats_in_auto_mode(tmp_path: Path):
    dataset_path = tmp_path / "mixed.jsonl"
    _ = dataset_path.write_text(
        "\n".join(
            [
                '{"messages":[{"role":"user","content":"hello"}]}',
                '{"prompt":"hello","completion":"hi"}',
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="line 2: mixed dataset format; expected messages"):
        _ = validate_dataset(dataset_path)


def test_validate_dataset_caps_reported_errors(tmp_path: Path):
    dataset_path = tmp_path / "many_errors.jsonl"
    _ = dataset_path.write_text("\n".join("{}" for _ in range(7)), encoding="utf-8")

    with pytest.raises(ValueError, match="and 2 more validation error") as exc_info:
        _ = validate_dataset(dataset_path, "messages")

    assert str(exc_info.value).count("line ") == 5


def test_validate_dataset_rejects_unknown_format():
    with pytest.raises(ValueError, match="Unsupported dataset format 'chatml'"):
        _ = validate_dataset(FIXTURES_DIR / "messages.jsonl", "chatml")


def _dry_run_args(tmp_path: Path) -> list[str]:
    return [
        "--base-model",
        "Qwen/Qwen2.5-0.5B-Instruct",
        "--dataset",
        str(FIXTURES_DIR / "messages.jsonl"),
        "--output-dir",
        str(tmp_path / "finetune-output"),
        "--ollama-model",
        "live2oder-test-model",
        "--dry-run",
    ]


def test_check_optional_dependencies_distinguishes_installed_and_missing(monkeypatch: pytest.MonkeyPatch):
    def fake_find_spec(package: str):
        return object() if package == "torch" else None

    monkeypatch.setattr(finetune, "_find_spec", fake_find_spec)

    diagnostics = check_optional_dependencies(("torch", "unsloth"))

    assert diagnostics["torch"].level == "ok"
    assert "installed" in diagnostics["torch"].message
    assert diagnostics["unsloth"].level == "warning"
    assert "not installed" in diagnostics["unsloth"].message


def test_check_environment_reports_ollama_and_llama_cpp_states(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    options = parse_options(
        _dry_run_args(tmp_path)
        + ["--run-ollama-create", "--export-gguf", "--llama-cpp-path", str(tmp_path / "missing-llama-cpp")]
    )
    dependencies = {
        package: finetune.Diagnostic(key=f"package:{package}", level="ok", message=f"{package} ok")
        for package in finetune.OPTIONAL_PACKAGES
    }
    def fake_missing_command(_command: str) -> None:
        return None

    monkeypatch.setattr(finetune, "_which", fake_missing_command)
    monkeypatch.setattr(
        finetune,
        "_check_ollama_server",
        lambda: finetune.Diagnostic(key="ollama_server", level="warning", message="Ollama server unreachable"),
    )

    diagnostics = check_environment(options, dependencies)

    by_key = {diagnostic.key: diagnostic for diagnostic in diagnostics}
    assert by_key["ollama_cli"].level == "warning"
    assert "missing" in by_key["ollama_cli"].message.lower()
    assert by_key["ollama_server"].level == "warning"
    assert "unreachable" in by_key["ollama_server"].message
    assert by_key["llama_cpp_path"].level == "warning"
    assert "missing" in by_key["llama_cpp_path"].message


def test_dry_run_prints_truthful_staged_plan(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    dependencies = {
        package: finetune.Diagnostic(key=f"package:{package}", level="ok", message=f"{package} installed")
        for package in finetune.OPTIONAL_PACKAGES
    }
    monkeypatch.setattr(finetune, "check_optional_dependencies", lambda: dependencies)
    monkeypatch.setattr(
        finetune,
        "_check_ollama_server",
        lambda: finetune.Diagnostic(key="ollama_server", level="warning", message="not called unless requested"),
    )

    exit_code = main(_dry_run_args(tmp_path))

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Environment diagnostics" in output
    assert "Dataset validation" in output
    assert "LoRA adapter training" in output
    assert "Merge/export" in output
    assert "GGUF/Modelfile" in output
    assert "Ollama create" in output
    assert "Config update skipped" in output
    assert "No training, Ollama, subprocess" in output


def test_dry_run_requires_non_interactive_inputs(capsys: pytest.CaptureFixture[str]):
    exit_code = main(["--dry-run"])

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "Missing required arguments" in output
    assert "--base-model" in output
    assert "--dataset" in output
    assert "--output-dir" in output
    assert "--ollama-model" in output


def test_dry_run_does_not_execute_subprocess_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    def fake_dependencies() -> dict[str, finetune.Diagnostic]:
        return {}

    def fake_environment(
        _options: finetune.Namespace,
        _dependencies: dict[str, finetune.Diagnostic] | None = None,
    ) -> list[finetune.Diagnostic]:
        return []

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("dry-run must not execute subprocesses")

    monkeypatch.setattr(finetune, "check_optional_dependencies", fake_dependencies)
    monkeypatch.setattr(finetune, "check_environment", fake_environment)
    monkeypatch.setattr("subprocess.run", fail_if_called)

    assert main(_dry_run_args(tmp_path)) == 0


def test_existing_non_empty_output_dir_requires_overwrite(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    output_dir = tmp_path / "existing-output"
    output_dir.mkdir()
    marker = output_dir / "file.txt"
    _ = marker.write_text("x", encoding="utf-8")
    args = _dry_run_args(tmp_path)
    args[args.index(str(tmp_path / "finetune-output"))] = str(output_dir)

    exit_code = main(args)

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "Pass --overwrite" in output
    assert marker.read_text(encoding="utf-8") == "x"


def test_existing_non_empty_output_dir_allowed_with_overwrite(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    output_dir = tmp_path / "existing-output"
    output_dir.mkdir()
    marker = output_dir / "file.txt"
    _ = marker.write_text("x", encoding="utf-8")
    args = _dry_run_args(tmp_path)
    args[args.index(str(tmp_path / "finetune-output"))] = str(output_dir)

    exit_code = main(args + ["--overwrite"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Output directory exists and is non-empty" in output
    assert marker.read_text(encoding="utf-8") == "x"


def test_unsloth_backend_is_gated_by_dependency_check(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    dependencies = {
        package: finetune.Diagnostic(key=f"package:{package}", level="ok", message=f"{package} installed")
        for package in finetune.OPTIONAL_PACKAGES
    }
    dependencies["unsloth"] = finetune.Diagnostic(
        key="package:unsloth",
        level="warning",
        message="Optional package 'unsloth' is not installed.",
    )
    monkeypatch.setattr(finetune, "check_optional_dependencies", lambda: dependencies)
    args = _dry_run_args(tmp_path) + ["--backend", "unsloth"]

    exit_code = main(args)

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "Backend 'unsloth' is unavailable" in output
    assert "unsloth" in output


# ── Task 5: Modelfile generation ────────────────────────────────────────────

def test_generate_modelfile_content_is_deterministic(tmp_path: Path):
    from scripts.finetune_transformers_for_ollama import TrainingConfig, generate_modelfile_content

    config = TrainingConfig(
        base_model="Qwen/Qwen2.5-0.5B-Instruct",
        backend="transformers",
        method="lora",
        dataset_path=tmp_path / "data.jsonl",
        dataset_format="messages",
        output_dir=tmp_path / "output",
        adapter_dir=tmp_path / "output" / "adapter",
        merged_dir=tmp_path / "output" / "merged",
        gguf_path=tmp_path / "output" / "model-Q4_K_M.gguf",
        modelfile_path=tmp_path / "output" / "Modelfile",
        ollama_model="live2oder-test",
        quantization="q4_k_m",
    )

    content1 = generate_modelfile_content(config)
    content2 = generate_modelfile_content(config)

    assert content1 == content2
    assert "FROM ./model-Q4_K_M.gguf" in content1
    assert "PARAMETER temperature 0.7" in content1
    assert "PARAMETER num_ctx 4096" in content1
    assert "SYSTEM" in content1
    assert "Live2oder assistant" in content1


def test_generate_modelfile_respects_custom_system_prompt(tmp_path: Path):
    from scripts.finetune_transformers_for_ollama import TrainingConfig, generate_modelfile_content

    config = TrainingConfig(
        base_model="Qwen/Qwen2.5-0.5B-Instruct",
        backend="transformers",
        method="lora",
        dataset_path=tmp_path / "data.jsonl",
        dataset_format="messages",
        output_dir=tmp_path / "output",
        adapter_dir=tmp_path / "output" / "adapter",
        merged_dir=tmp_path / "output" / "merged",
        gguf_path=tmp_path / "output" / "model-Q4_K_M.gguf",
        modelfile_path=tmp_path / "output" / "Modelfile",
        ollama_model="live2oder-test",
        quantization="q4_k_m",
    )

    content = generate_modelfile_content(config, system_prompt="Custom prompt here.")

    assert 'SYSTEM """Custom prompt here."""' in content


# ── Task 5: Config update safety ────────────────────────────────────────────

def test_backup_and_update_config_appends_non_default_entry(tmp_path: Path):
    from scripts.finetune_transformers_for_ollama import backup_and_update_config

    config_path = tmp_path / "config.json"
    original = {"live2dSocket": "ws://127.0.0.1:10086/api", "models": []}
    config_path.write_text(json.dumps(original), encoding="utf-8")

    result = backup_and_update_config(config_path, "my-finetuned-model", backup=True, model_name="my-model")

    assert result == config_path
    updated = json.loads(config_path.read_text(encoding="utf-8"))
    assert len(updated["models"]) == 1
    entry = updated["models"][0]
    assert entry["name"] == "my-model"
    assert entry["model"] == "my-finetuned-model"
    assert entry["type"] == "ollama"
    assert entry["default"] is False
    # Backup was created
    backups = list(tmp_path.glob("config.json.bak.*"))
    assert len(backups) == 1


def test_backup_and_update_config_preserves_existing_models(tmp_path: Path):
    from scripts.finetune_transformers_for_ollama import backup_and_update_config

    config_path = tmp_path / "config.json"
    existing_model = {
        "name": "existing-ollama",
        "model": "gemma3:1b",
        "type": "ollama",
        "default": True,
        "system_prompt": "hello",
        "streaming": True,
        "options": {"temperature": 0.3},
    }
    original = {"live2dSocket": "ws://127.0.0.1:10086/api", "models": [existing_model]}
    config_path.write_text(json.dumps(original), encoding="utf-8")

    backup_and_update_config(config_path, "my-finetuned-model", backup=False)

    updated = json.loads(config_path.read_text(encoding="utf-8"))
    assert len(updated["models"]) == 2
    assert updated["models"][0]["name"] == "existing-ollama"
    assert updated["models"][1]["name"] == "my-finetuned-model"
    # No backup when backup=False
    backups = list(tmp_path.glob("config.json.bak.*"))
    assert len(backups) == 0


def test_backup_and_update_config_raises_if_config_missing(tmp_path: Path):
    from scripts.finetune_transformers_for_ollama import backup_and_update_config

    with pytest.raises(FileNotFoundError, match="Config file not found"):
        backup_and_update_config(tmp_path / "nonexistent.json", "model-name")


def test_dry_run_does_not_modify_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    config_path = tmp_path / "config.json"
    original = {"live2dSocket": "ws://127.0.0.1:10086/api", "models": []}
    config_path.write_text(json.dumps(original), encoding="utf-8")

    dependencies = {
        package: finetune.Diagnostic(key=f"package:{package}", level="ok", message=f"{package} installed")
        for package in finetune.OPTIONAL_PACKAGES
    }
    monkeypatch.setattr(finetune, "check_optional_dependencies", lambda: dependencies)
    args = _dry_run_args(tmp_path) + ["--config-path", str(config_path)]

    exit_code = main(args)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Config update skipped" in output
    # config must be untouched
    current = json.loads(config_path.read_text(encoding="utf-8"))
    assert current == original


def test_config_update_with_dry_run_shows_preview(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    config_path = tmp_path / "config.json"
    original = {"live2dSocket": "ws://127.0.0.1:10086/api", "models": []}
    config_path.write_text(json.dumps(original), encoding="utf-8")

    dependencies = {
        package: finetune.Diagnostic(key=f"package:{package}", level="ok", message=f"{package} installed")
        for package in finetune.OPTIONAL_PACKAGES
    }
    monkeypatch.setattr(finetune, "check_optional_dependencies", lambda: dependencies)
    args = _dry_run_args(tmp_path) + ["--update-config", "--backup-config", "--config-path", str(config_path)]

    exit_code = main(args)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Config update: would append model entry" in output
    assert "Backup requested: True" in output
    # config must be untouched (dry-run)
    current = json.loads(config_path.read_text(encoding="utf-8"))
    assert current == original


# ── Task 5: Packaging exclusion ─────────────────────────────────────────────

def test_finetune_script_not_referenced_in_spec_file():
    spec_path = Path(__file__).resolve().parents[2] / "live2d-agent.spec"
    spec_text = spec_path.read_text(encoding="utf-8")

    assert "finetune_transformers_for_ollama" not in spec_text
    assert "finetune_transformers_for_ollama.py" not in spec_text


# ── Task 5: Modelfile write ─────────────────────────────────────────────────

def test_run_modelfile_generation_writes_file(tmp_path: Path):
    from scripts.finetune_transformers_for_ollama import (
        TrainingConfig,
        run_modelfile_generation,
    )

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    config = TrainingConfig(
        base_model="Qwen/Qwen2.5-0.5B-Instruct",
        backend="transformers",
        method="lora",
        dataset_path=tmp_path / "data.jsonl",
        dataset_format="messages",
        output_dir=output_dir,
        adapter_dir=output_dir / "adapter",
        merged_dir=output_dir / "merged",
        gguf_path=output_dir / "model-Q4_K_M.gguf",
        modelfile_path=output_dir / "Modelfile",
        ollama_model="live2oder-test",
        quantization="q4_k_m",
    )

    path = run_modelfile_generation(config)

    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "FROM ./model-Q4_K_M.gguf" in content
    assert "PARAMETER temperature 0.7" in content


def test_run_modelfile_generation_refuses_overwrite_without_flag(tmp_path: Path):
    from scripts.finetune_transformers_for_ollama import (
        TrainingConfig,
        run_modelfile_generation,
    )

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    modelfile_path = output_dir / "Modelfile"
    modelfile_path.write_text("existing", encoding="utf-8")

    config = TrainingConfig(
        base_model="Qwen/Qwen2.5-0.5B-Instruct",
        backend="transformers",
        method="lora",
        dataset_path=tmp_path / "data.jsonl",
        dataset_format="messages",
        output_dir=output_dir,
        adapter_dir=output_dir / "adapter",
        merged_dir=output_dir / "merged",
        gguf_path=output_dir / "model-Q4_K_M.gguf",
        modelfile_path=modelfile_path,
        ollama_model="live2oder-test",
        quantization="q4_k_m",
    )

    with pytest.raises(FileExistsError, match="Pass --overwrite"):
        run_modelfile_generation(config)

    assert modelfile_path.read_text(encoding="utf-8") == "existing"


def test_run_modelfile_generation_overwrites_with_flag(tmp_path: Path):
    from scripts.finetune_transformers_for_ollama import (
        TrainingConfig,
        run_modelfile_generation,
    )

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    modelfile_path = output_dir / "Modelfile"
    modelfile_path.write_text("old", encoding="utf-8")

    config = TrainingConfig(
        base_model="Qwen/Qwen2.5-0.5B-Instruct",
        backend="transformers",
        method="lora",
        dataset_path=tmp_path / "data.jsonl",
        dataset_format="messages",
        output_dir=output_dir,
        adapter_dir=output_dir / "adapter",
        merged_dir=output_dir / "merged",
        gguf_path=output_dir / "model-Q4_K_M.gguf",
        modelfile_path=modelfile_path,
        ollama_model="live2oder-test",
        quantization="q4_k_m",
    )

    path = run_modelfile_generation(config, overwrite=True)

    assert path.read_text(encoding="utf-8") != "old"
    assert "FROM ./model-Q4_K_M.gguf" in path.read_text(encoding="utf-8")


# ── Task 6: parse_options for new flags ──────────────────────────────────────


def test_parse_options_preserves_new_hyperparameter_defaults():
    options = parse_options([])

    assert getattr(options, "run") is False
    assert getattr(options, "learning_rate") == 2e-4
    assert getattr(options, "batch_size") == 2
    assert getattr(options, "max_steps") == 1000
    assert getattr(options, "gradient_accumulation_steps") == 4
    assert getattr(options, "lora_r") == 16
    assert getattr(options, "lora_alpha") == 32
    assert getattr(options, "lora_dropout") == 0.05
    assert getattr(options, "max_seq_length") == 4096


def test_parse_options_accepts_run_flag():
    options = parse_options(["--run"])
    assert getattr(options, "run") is True


# ── Task 6: _run_subprocess ──────────────────────────────────────────────────


def test_run_subprocess_success(monkeypatch: pytest.MonkeyPatch):
    fake_result = subprocess.CompletedProcess(
        args=["echo", "hello"], returncode=0, stdout="hello\n", stderr=""
    )

    def fake_run(*args, **kwargs):
        return fake_result

    monkeypatch.setattr(finetune, "_subprocess_run", fake_run)

    result = finetune._run_subprocess(["echo", "hello"])
    assert result.returncode == 0
    assert result.stdout == "hello\n"


def test_run_subprocess_timeout(monkeypatch: pytest.MonkeyPatch):
    import subprocess as sp

    def fake_run(*args, **kwargs):
        raise sp.TimeoutExpired(cmd=["sleep"], timeout=1)

    monkeypatch.setattr(finetune, "_subprocess_run", fake_run)

    with pytest.raises(RuntimeError, match="timed out"):
        finetune._run_subprocess(["sleep", "10"], timeout=1)


def test_run_subprocess_command_not_found(monkeypatch: pytest.MonkeyPatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("no such command")

    monkeypatch.setattr(finetune, "_subprocess_run", fake_run)

    with pytest.raises(RuntimeError, match="Command not found"):
        finetune._run_subprocess(["nonexistent"])


# ── Task 6: _format_record ───────────────────────────────────────────────────


def test_format_record_messages():
    tokenizer = _FakeTokenizer()
    record = {
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
    }
    result = finetune._format_record(record, "messages", tokenizer)
    assert "Hello" in result
    assert "Hi" in result
    assert tokenizer.apply_chat_template_called


def test_format_record_prompt_completion():
    tokenizer = _FakeTokenizer()
    record = {"prompt": "Question: ", "completion": "Answer."}
    result = finetune._format_record(record, "prompt-completion", tokenizer)
    assert result == "Question: Answer."


# ── Task 6: prepare_dataset ──────────────────────────────────────────────────


def _mock_datasets_in_sys_modules(monkeypatch: pytest.MonkeyPatch):
    """Inject a mock datasets module so ``from datasets import Dataset`` works."""
    import types

    mock_datasets = types.ModuleType("datasets")
    mock_datasets.Dataset = _FakeDataset
    monkeypatch.setitem(sys.modules, "datasets", mock_datasets)


def test_prepare_dataset_with_messages(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    dataset_path = tmp_path / "data.jsonl"
    dataset_path.write_text(
        json.dumps(
            {
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi"},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _mock_datasets_in_sys_modules(monkeypatch)
    config = _make_training_config(tmp_path, dataset_path=dataset_path, dataset_format="messages")
    tokenizer = _FakeTokenizer()
    ds = finetune.prepare_dataset(config, tokenizer)

    assert len(ds) == 1
    assert "text" in ds.column_names
    assert "Hello" in ds[0]["text"]


def test_prepare_dataset_with_prompt_completion(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    dataset_path = tmp_path / "data.jsonl"
    dataset_path.write_text(
        json.dumps({"prompt": "Q: ", "completion": "A."}) + "\n",
        encoding="utf-8",
    )

    _mock_datasets_in_sys_modules(monkeypatch)
    config = _make_training_config(
        tmp_path, dataset_path=dataset_path, dataset_format="prompt-completion"
    )
    ds = finetune.prepare_dataset(config, _FakeTokenizer())

    assert len(ds) == 1
    assert ds[0]["text"] == "Q: A."


# ── Task 6: run_training (mocked) ────────────────────────────────────────────


def _mock_ml_packages_for_run_training(monkeypatch: pytest.MonkeyPatch, trainer_cls=None):
    """Inject mock torch, transformers, trl modules so run_training imports work."""
    import types

    mock_torch = types.ModuleType("torch")
    mock_torch.cuda = types.ModuleType("torch.cuda")
    mock_torch.cuda.is_available = lambda: False
    monkeypatch.setitem(sys.modules, "torch", mock_torch)
    monkeypatch.setitem(sys.modules, "torch.cuda", mock_torch.cuda)

    mock_transformers = types.ModuleType("transformers")
    mock_transformers.TrainingArguments = lambda **kw: kw
    monkeypatch.setitem(sys.modules, "transformers", mock_transformers)

    mock_trl = types.ModuleType("trl")
    if trainer_cls is not None:
        mock_trl.SFTTrainer = trainer_cls
    monkeypatch.setitem(sys.modules, "trl", mock_trl)


def test_run_training_calls_sft_trainer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    config = _make_training_config(tmp_path)
    config.adapter_dir.mkdir(parents=True)

    fake_trainer = _FakeTrainer()

    _mock_ml_packages_for_run_training(monkeypatch, trainer_cls=lambda *a, **kw: fake_trainer)
    monkeypatch.setattr(finetune, "_load_base_model", _fake_load_base_model)
    monkeypatch.setattr(finetune, "prepare_dataset", lambda c, t: _FakeDataset())

    result = finetune.run_training(config)

    assert result == config.adapter_dir
    assert fake_trainer.train_called
    assert fake_trainer.save_model_called


def test_run_training_creates_adapter_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    config = _make_training_config(tmp_path)
    assert not config.adapter_dir.exists()

    _mock_ml_packages_for_run_training(monkeypatch, trainer_cls=_FakeTrainer)
    monkeypatch.setattr(finetune, "_load_base_model", _fake_load_base_model)
    monkeypatch.setattr(finetune, "prepare_dataset", lambda c, t: _FakeDataset())

    finetune.run_training(config)
    assert config.adapter_dir.exists()


# ── Task 6: merge_adapter (mocked) ───────────────────────────────────────────


def _mock_ml_packages_for_merge_adapter(monkeypatch: pytest.MonkeyPatch, fake_model):
    """Inject mock torch, transformers, peft modules for merge_adapter."""
    import types

    mock_torch = types.ModuleType("torch")
    mock_torch.cuda = types.ModuleType("torch.cuda")
    mock_torch.cuda.is_available = lambda: False
    mock_torch.bfloat16 = None
    mock_torch.float32 = None
    monkeypatch.setitem(sys.modules, "torch", mock_torch)
    monkeypatch.setitem(sys.modules, "torch.cuda", mock_torch.cuda)

    _FakeAutoModel = _make_fake_auto_model_cls(fake_model)
    _FakeAutoTokenizer = _make_fake_auto_tokenizer_cls()
    _FakePeftModelCls = _make_fake_peft_model_cls(fake_model)

    mock_transformers = types.ModuleType("transformers")
    mock_transformers.AutoModelForCausalLM = _FakeAutoModel
    mock_transformers.AutoTokenizer = _FakeAutoTokenizer
    monkeypatch.setitem(sys.modules, "transformers", mock_transformers)

    mock_peft = types.ModuleType("peft")
    mock_peft.PeftModel = _FakePeftModelCls
    monkeypatch.setitem(sys.modules, "peft", mock_peft)


def test_merge_adapter_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    config = _make_training_config(tmp_path)
    config.adapter_dir.mkdir(parents=True)

    fake_model = _FakeModel()
    _mock_ml_packages_for_merge_adapter(monkeypatch, fake_model)

    result = finetune.merge_adapter(config)
    assert result == config.merged_dir
    assert fake_model.save_pretrained_called


def test_merge_adapter_missing_adapter_dir(tmp_path: Path):
    config = _make_training_config(tmp_path)

    with pytest.raises(FileNotFoundError, match="Adapter directory not found"):
        finetune.merge_adapter(config)


# ── Task 6: export_gguf ──────────────────────────────────────────────────────


def test_export_gguf_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    config = _make_training_config(tmp_path)
    config.merged_dir.mkdir(parents=True)
    config.gguf_path.parent.mkdir(parents=True, exist_ok=True)

    llama_cpp_dir = tmp_path / "llama.cpp"
    llama_cpp_dir.mkdir()
    convert_script = llama_cpp_dir / "convert_hf_to_gguf.py"
    convert_script.write_text("", encoding="utf-8")

    fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
    monkeypatch.setattr(finetune, "_run_subprocess", lambda *a, **kw: fake_result)

    result = finetune.export_gguf(config, llama_cpp_dir)
    assert result == config.gguf_path


def test_export_gguf_missing_script(tmp_path: Path):
    config = _make_training_config(tmp_path)
    config.merged_dir.mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match="llama.cpp conversion script not found"):
        finetune.export_gguf(config, tmp_path / "nonexistent")


def test_export_gguf_subprocess_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    config = _make_training_config(tmp_path)
    config.merged_dir.mkdir(parents=True)
    config.gguf_path.parent.mkdir(parents=True, exist_ok=True)

    llama_cpp_dir = tmp_path / "llama.cpp"
    llama_cpp_dir.mkdir()
    (llama_cpp_dir / "convert_hf_to_gguf.py").write_text("", encoding="utf-8")

    fake_result = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="conversion error"
    )
    monkeypatch.setattr(finetune, "_run_subprocess", lambda *a, **kw: fake_result)

    with pytest.raises(RuntimeError, match="GGUF conversion failed"):
        finetune.export_gguf(config, llama_cpp_dir)


# ── Task 6: ollama_create_model ──────────────────────────────────────────────


def test_ollama_create_model_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    config = _make_training_config(tmp_path)
    config.modelfile_path.parent.mkdir(parents=True, exist_ok=True)
    config.modelfile_path.write_text("FROM ./model.gguf\n", encoding="utf-8")

    fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
    monkeypatch.setattr(finetune, "_run_subprocess", lambda *a, **kw: fake_result)

    result = finetune.ollama_create_model(config)
    assert result == config.ollama_model


def test_ollama_create_model_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    config = _make_training_config(tmp_path)
    config.modelfile_path.parent.mkdir(parents=True, exist_ok=True)
    config.modelfile_path.write_text("FROM ./model.gguf\n", encoding="utf-8")

    fake_result = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="ollama error"
    )
    monkeypatch.setattr(finetune, "_run_subprocess", lambda *a, **kw: fake_result)

    with pytest.raises(RuntimeError, match="ollama create failed"):
        finetune.ollama_create_model(config)


# ── Task 6: run_execution integration ────────────────────────────────────────


def _run_args(tmp_path: Path) -> list[str]:
    return [
        "--base-model",
        "Qwen/Qwen2.5-0.5B-Instruct",
        "--dataset",
        str(FIXTURES_DIR / "messages.jsonl"),
        "--output-dir",
        str(tmp_path / "finetune-output"),
        "--ollama-model",
        "live2oder-test-model",
        "--run",
    ]


def test_run_execution_training_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    """Training only, no merge/export/ollama."""
    dependencies = {
        p: finetune.Diagnostic(key=f"package:{p}", level="ok", message=f"{p} installed")
        for p in finetune.OPTIONAL_PACKAGES
    }
    monkeypatch.setattr(finetune, "check_optional_dependencies", lambda: dependencies)
    monkeypatch.setattr(finetune, "run_training", lambda c: c.adapter_dir)
    monkeypatch.setattr(
        finetune,
        "run_modelfile_generation",
        lambda c, overwrite: c.modelfile_path,
    )

    exit_code = finetune.run_execution(
        parse_options(_run_args(tmp_path) + ["--overwrite"])
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "completed successfully" in output


def test_run_execution_full_pipeline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """All steps enabled."""
    dependencies = {
        p: finetune.Diagnostic(key=f"package:{p}", level="ok", message=f"{p} installed")
        for p in finetune.OPTIONAL_PACKAGES
    }
    monkeypatch.setattr(finetune, "check_optional_dependencies", lambda: dependencies)
    monkeypatch.setattr(finetune, "run_training", lambda c: c.adapter_dir)
    monkeypatch.setattr(finetune, "merge_adapter", lambda c: c.merged_dir)
    monkeypatch.setattr(finetune, "export_gguf", lambda c, p: c.gguf_path)
    monkeypatch.setattr(finetune, "ollama_create_model", lambda c: c.ollama_model)
    monkeypatch.setattr(
        finetune,
        "run_modelfile_generation",
        lambda c, overwrite: c.modelfile_path,
    )
    monkeypatch.setattr(
        finetune,
        "backup_and_update_config",
        lambda config_path, ollama_model, **kw: config_path,
    )

    llama_cpp_dir = tmp_path / "llama.cpp"
    llama_cpp_dir.mkdir()

    exit_code = finetune.run_execution(
        parse_options(
            _run_args(tmp_path)
            + [
                "--overwrite",
                "--merge",
                "--export-gguf",
                "--llama-cpp-path", str(llama_cpp_dir),
                "--run-ollama-create",
                "--update-config",
            ]
        )
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "completed successfully" in output


def test_run_execution_halts_on_environment_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """Blocking environment errors return 2."""
    dependencies = {
        p: finetune.Diagnostic(key=f"package:{p}", level="ok", message=f"{p} installed")
        for p in finetune.OPTIONAL_PACKAGES
    }
    monkeypatch.setattr(finetune, "check_optional_dependencies", lambda: dependencies)

    def fake_env(options, deps):
        return [
            finetune.Diagnostic(
                key="output_dir", level="error", message="blocking error"
            )
        ]

    monkeypatch.setattr(finetune, "check_environment", fake_env)

    exit_code = finetune.run_execution(parse_options(_run_args(tmp_path)))

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "blocking error" in output


def test_run_execution_training_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """Training failure returns 1."""
    dependencies = {
        p: finetune.Diagnostic(key=f"package:{p}", level="ok", message=f"{p} installed")
        for p in finetune.OPTIONAL_PACKAGES
    }
    monkeypatch.setattr(finetune, "check_optional_dependencies", lambda: dependencies)

    def fail_training(config):
        raise RuntimeError("CUDA out of memory")

    monkeypatch.setattr(finetune, "run_training", fail_training)

    exit_code = finetune.run_execution(
        parse_options(_run_args(tmp_path) + ["--overwrite"])
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "Training failed" in output


def test_run_execution_output_dir_exists_without_overwrite(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """Existing non-empty output dir without --overwrite returns 2."""
    output_dir = tmp_path / "existing"
    output_dir.mkdir()
    (output_dir / "old_file.txt").write_text("x", encoding="utf-8")

    dependencies = {
        p: finetune.Diagnostic(key=f"package:{p}", level="ok", message=f"{p} installed")
        for p in finetune.OPTIONAL_PACKAGES
    }
    monkeypatch.setattr(finetune, "check_optional_dependencies", lambda: dependencies)

    args = _run_args(tmp_path)
    args[args.index(str(tmp_path / "finetune-output"))] = str(output_dir)

    exit_code = finetune.run_execution(parse_options(args))

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "exists and is non-empty" in output


def test_run_execution_gguf_requires_llama_cpp_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """GGUF export without --llama-cpp-path returns 2."""
    dependencies = {
        p: finetune.Diagnostic(key=f"package:{p}", level="ok", message=f"{p} installed")
        for p in finetune.OPTIONAL_PACKAGES
    }
    monkeypatch.setattr(finetune, "check_optional_dependencies", lambda: dependencies)
    monkeypatch.setattr(finetune, "run_training", lambda c: c.adapter_dir)
    monkeypatch.setattr(finetune, "merge_adapter", lambda c: c.merged_dir)
    monkeypatch.setattr(
        finetune,
        "run_modelfile_generation",
        lambda c, overwrite: c.modelfile_path,
    )

    exit_code = finetune.run_execution(
        parse_options(
            _run_args(tmp_path)
            + ["--overwrite", "--merge", "--export-gguf"]
        )
    )

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "--llama-cpp-path is required" in output


# ── Task 6: main() --run dispatch ────────────────────────────────────────────


def test_main_run_flag_dispatches_to_run_execution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    run_exec_called = []

    def fake_run_execution(options):
        run_exec_called.append(True)
        return 0

    monkeypatch.setattr(finetune, "run_execution", fake_run_execution)

    exit_code = finetune.main(_run_args(tmp_path) + ["--overwrite"])
    assert exit_code == 0
    assert len(run_exec_called) == 1


def test_main_dry_run_takes_precedence_over_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    run_exec_called = []
    dry_run_called = []

    monkeypatch.setattr(finetune, "run_execution", lambda o: run_exec_called.append(True) or 0)
    monkeypatch.setattr(finetune, "run_dry_run", lambda o: dry_run_called.append(True) or 0)

    finetune.main(_run_args(tmp_path) + ["--dry-run", "--overwrite"])

    assert len(dry_run_called) == 1
    assert len(run_exec_called) == 0


# ── Test helpers ─────────────────────────────────────────────────────────────


class _FakeTokenizer:
    def __init__(self):
        self.apply_chat_template_called = False
        self.pad_token = None
        self.eos_token = "[EOS]"

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=False):
        self.apply_chat_template_called = True
        return " ".join(m["content"] for m in messages)

    def save_pretrained(self, path):
        pass

    @classmethod
    def from_pretrained(cls, model_name):
        return cls()


class _FakeModel:
    def __init__(self):
        self.save_pretrained_called = False

    def save_pretrained(self, path):
        self.save_pretrained_called = True

    def merge_and_unload(self):
        return self

    def save_model(self, path):
        pass


class _FakeTrainer:
    def __init__(self, *args, **kwargs):
        self.train_called = False
        self.save_model_called = False

    def train(self):
        self.train_called = True

    def save_model(self, path):
        self.save_model_called = True


class _FakeDataset:
    def __init__(self, texts=None):
        self._texts = texts or ["sample text"]

    def __len__(self):
        return len(self._texts)

    def __getitem__(self, idx):
        return {"text": self._texts[idx]}

    @property
    def column_names(self):
        return ["text"]

    @classmethod
    def from_dict(cls, data):
        return cls(data.get("text", []))


class _FakePeftModel:
    def __init__(self, fake_model):
        self._fake_model = fake_model

    def merge_and_unload(self):
        return self._fake_model

    @classmethod
    def from_pretrained(cls, model, adapter_path):
        return cls(model)


def _fake_load_base_model(config):
    return _FakeModel(), _FakeTokenizer()


def _make_fake_auto_model_cls(fake_model):
    class _FakeAutoModel:
        @classmethod
        def from_pretrained(cls, model_name, **kwargs):
            return fake_model
    return _FakeAutoModel


def _make_fake_auto_tokenizer_cls():
    class _FakeAutoTokenizer:
        @classmethod
        def from_pretrained(cls, model_name):
            return _FakeTokenizer()
    return _FakeAutoTokenizer


def _make_fake_peft_model_cls(fake_model):
    class _FakePeftModelCls:
        @classmethod
        def from_pretrained(cls, model, adapter_path):
            return _FakePeftModel(fake_model)
    return _FakePeftModelCls


def _make_training_config(
    tmp_path: Path,
    dataset_path: Path | None = None,
    dataset_format: str = "messages",
) -> finetune.TrainingConfig:
    output_dir = tmp_path / "output"
    return finetune.TrainingConfig(
        base_model="Qwen/Qwen2.5-0.5B-Instruct",
        backend="transformers",
        method="lora",
        dataset_path=dataset_path or (tmp_path / "data.jsonl"),
        dataset_format=dataset_format,  # type: ignore[arg-type]
        output_dir=output_dir,
        adapter_dir=output_dir / "adapter",
        merged_dir=output_dir / "merged",
        gguf_path=output_dir / "model-Q4_K_M.gguf",
        modelfile_path=output_dir / "Modelfile",
        ollama_model="test-model",
        quantization="q4_k_m",
    )
