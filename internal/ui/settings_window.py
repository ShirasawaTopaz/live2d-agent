from __future__ import annotations

import copy
import json
import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from internal.config.config import AIModelType, Config
from internal.config.editor import (
    RuntimeApplyDecision,
    ValidationError,
    decide_runtime_apply,
    load_with_raw,
    merge_known_fields,
    normalize_models_default,
    save_config_atomic,
    validate_config_dict,
)
from internal.mcp import CompressionStrategyType, MCPMode

logger = logging.getLogger(__name__)


class SettingsWindow(QWidget):
    config_saved = Signal(object, object)

    def __init__(
        self,
        *,
        config_path: str,
        on_saved: Callable[[Config, RuntimeApplyDecision], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config_path = config_path
        self._on_saved = on_saved
        self._raw_config: dict[str, Any] = {}
        self._config: Config = Config()
        self._models_raw: list[dict[str, Any]] = []
        self._current_model_index: int | None = None
        self._last_default_index: int | None = None
        self._syncing_model_editor = False

        self.setWindowTitle("Live2oder Settings")
        self.setMinimumSize(1000, 760)
        self.resize(1140, 840)
        self._build_ui()
        self._load_from_disk()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.path_label = QLabel(f"Config: {self._config_path}")
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)

        self.status_label = QLabel("")
        self.status_label.setObjectName("settingsStatus")
        layout.addWidget(self.status_label)

        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs, stretch=1)

        self._build_general_tab()
        self._build_models_tab()
        self._build_memory_tab()
        self._build_sandbox_tab()
        self._build_planning_tab()
        self._build_rag_tab()

        button_row = QHBoxLayout()
        button_row.addStretch()

        self.reload_btn = QPushButton("Reload", self)
        self.reload_btn.clicked.connect(self._load_from_disk)
        button_row.addWidget(self.reload_btn)

        self.save_btn = QPushButton("Save", self)
        self.save_btn.clicked.connect(self._on_save_clicked)
        button_row.addWidget(self.save_btn)

        self.close_btn = QPushButton("Close", self)
        self.close_btn.clicked.connect(self.close)
        button_row.addWidget(self.close_btn)
        layout.addLayout(button_row)

    def _build_general_tab(self) -> None:
        tab = QWidget(self)
        form = QFormLayout(tab)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(10)

        self.live2d_socket_edit = QLineEdit(tab)
        self.live2d_socket_edit.setPlaceholderText("ws://127.0.0.1:10086/api")
        form.addRow("live2dSocket", self.live2d_socket_edit)

        self.tabs.addTab(tab, "General")

    def _build_models_tab(self) -> None:
        tab = QWidget(self)
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        left_col = QVBoxLayout()
        self.model_list = QListWidget(tab)
        self.model_list.currentRowChanged.connect(self._on_model_selected)
        left_col.addWidget(self.model_list, stretch=1)

        btn_row_1 = QHBoxLayout()
        self.model_add_btn = QPushButton("Add", tab)
        self.model_add_btn.clicked.connect(self._on_add_model)
        btn_row_1.addWidget(self.model_add_btn)

        self.model_clone_btn = QPushButton("Copy", tab)
        self.model_clone_btn.clicked.connect(self._on_copy_model)
        btn_row_1.addWidget(self.model_clone_btn)
        left_col.addLayout(btn_row_1)

        btn_row_2 = QHBoxLayout()
        self.model_delete_btn = QPushButton("Delete", tab)
        self.model_delete_btn.clicked.connect(self._on_delete_model)
        btn_row_2.addWidget(self.model_delete_btn)

        self.model_up_btn = QPushButton("Up", tab)
        self.model_up_btn.clicked.connect(self._on_move_model_up)
        btn_row_2.addWidget(self.model_up_btn)

        self.model_down_btn = QPushButton("Down", tab)
        self.model_down_btn.clicked.connect(self._on_move_model_down)
        btn_row_2.addWidget(self.model_down_btn)
        left_col.addLayout(btn_row_2)

        layout.addLayout(left_col, stretch=2)

        scroll = QScrollArea(tab)
        scroll.setWidgetResizable(True)
        editor_host = QWidget(scroll)
        form = QFormLayout(editor_host)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(8)

        self.model_name_edit = QLineEdit(editor_host)
        form.addRow("name", self.model_name_edit)

        self.model_model_edit = QLineEdit(editor_host)
        form.addRow("model", self.model_model_edit)

        self.model_type_combo = QComboBox(editor_host)
        for model_type in AIModelType:
            self.model_type_combo.addItem(model_type.value, model_type.value)
        form.addRow("type", self.model_type_combo)

        self.model_default_check = QCheckBox("Use as default model", editor_host)
        form.addRow("default", self.model_default_check)

        self.model_streaming_check = QCheckBox("Enable streaming responses", editor_host)
        form.addRow("streaming", self.model_streaming_check)

        self.model_api_key_edit = QLineEdit(editor_host)
        self.model_api_key_edit.setPlaceholderText("Only for online model")
        form.addRow("api_key", self.model_api_key_edit)

        self.model_temperature_spin = QDoubleSpinBox(editor_host)
        self.model_temperature_spin.setDecimals(3)
        self.model_temperature_spin.setSingleStep(0.05)
        self.model_temperature_spin.setRange(0.0, 2.0)
        form.addRow("temperature", self.model_temperature_spin)

        self.model_top_p_edit = QLineEdit(editor_host)
        self.model_top_p_edit.setPlaceholderText("optional float (0-1)")
        form.addRow("top_p", self.model_top_p_edit)

        self.model_repeat_penalty_edit = QLineEdit(editor_host)
        self.model_repeat_penalty_edit.setPlaceholderText("optional float")
        form.addRow("repeat_penalty", self.model_repeat_penalty_edit)

        self.model_max_new_tokens_edit = QLineEdit(editor_host)
        self.model_max_new_tokens_edit.setPlaceholderText("optional integer")
        form.addRow("max_new_tokens", self.model_max_new_tokens_edit)

        self.model_max_tool_retries_edit = QLineEdit(editor_host)
        self.model_max_tool_retries_edit.setPlaceholderText("optional integer >= 0")
        form.addRow("max_tool_call_retries", self.model_max_tool_retries_edit)

        self.model_load_4bit_combo = self._create_nullable_bool_combo(editor_host)
        form.addRow("load_in_4bit", self.model_load_4bit_combo)

        self.model_load_8bit_combo = self._create_nullable_bool_combo(editor_host)
        form.addRow("load_in_8bit", self.model_load_8bit_combo)

        self.model_kv_quant_combo = self._create_nullable_bool_combo(editor_host)
        form.addRow("kv_cache_quantization", self.model_kv_quant_combo)

        self.model_enable_cot_combo = self._create_nullable_bool_combo(editor_host)
        form.addRow("enable_cot", self.model_enable_cot_combo)

        self.model_system_prompt_edit = QPlainTextEdit(editor_host)
        self.model_system_prompt_edit.setPlaceholderText(
            "string or JSON object. JSON will be parsed automatically."
        )
        self.model_system_prompt_edit.setMinimumHeight(120)
        form.addRow("system_prompt", self.model_system_prompt_edit)

        self.model_options_edit = QPlainTextEdit(editor_host)
        self.model_options_edit.setPlaceholderText("JSON object")
        self.model_options_edit.setMinimumHeight(120)
        form.addRow("options", self.model_options_edit)

        scroll.setWidget(editor_host)
        layout.addWidget(scroll, stretch=4)

        self.tabs.addTab(tab, "Models")

    def _build_memory_tab(self) -> None:
        tab = QWidget(self)
        scroll = QScrollArea(tab)
        scroll.setWidgetResizable(True)

        host = QWidget(scroll)
        form = QFormLayout(host)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(8)

        self.memory_enabled_check = QCheckBox(host)
        form.addRow("enabled", self.memory_enabled_check)

        self.memory_storage_combo = QComboBox(host)
        self.memory_storage_combo.addItems(["json", "sqlite"])
        form.addRow("storage_type", self.memory_storage_combo)

        self.memory_data_dir_edit = QLineEdit(host)
        form.addRow("data_dir", self.memory_data_dir_edit)

        self.memory_max_messages_spin = self._create_int_spinbox(host, 1, 10000)
        form.addRow("max_messages", self.memory_max_messages_spin)

        self.memory_max_tokens_spin = self._create_int_spinbox(host, 1, 2000000)
        form.addRow("max_tokens", self.memory_max_tokens_spin)

        self.memory_compression_enabled_check = QCheckBox(host)
        form.addRow("compression_enabled", self.memory_compression_enabled_check)

        self.memory_compression_model_edit = QLineEdit(host)
        form.addRow("compression_model", self.memory_compression_model_edit)

        self.memory_threshold_spin = self._create_int_spinbox(host, 1, 10000)
        form.addRow("compression_threshold_messages", self.memory_threshold_spin)

        self.memory_long_term_compression_check = QCheckBox(host)
        form.addRow("long_term_compression_enabled", self.memory_long_term_compression_check)

        self.memory_cutoff_days_spin = self._create_int_spinbox(host, 1, 3650)
        form.addRow("compression_cutoff_days", self.memory_cutoff_days_spin)

        self.memory_min_messages_spin = self._create_int_spinbox(host, 1, 10000)
        form.addRow("compression_min_messages", self.memory_min_messages_spin)

        self.memory_compress_on_start_check = QCheckBox(host)
        form.addRow("compress_on_startup", self.memory_compress_on_start_check)

        self.memory_enable_long_term_check = QCheckBox(host)
        form.addRow("enable_long_term", self.memory_enable_long_term_check)

        self.memory_long_term_storage_combo = QComboBox(host)
        self.memory_long_term_storage_combo.addItems(["json", "sqlite"])
        form.addRow("long_term_storage", self.memory_long_term_storage_combo)

        self.memory_auto_cleanup_check = QCheckBox(host)
        form.addRow("auto_cleanup", self.memory_auto_cleanup_check)

        self.memory_max_sessions_spin = self._create_int_spinbox(host, 1, 100000)
        form.addRow("max_sessions", self.memory_max_sessions_spin)

        self.memory_use_mcp_check = QCheckBox(host)
        form.addRow("use_mcp", self.memory_use_mcp_check)

        mcp_box = QGroupBox("MCP", host)
        mcp_form = QFormLayout(mcp_box)
        mcp_form.setSpacing(8)

        self.memory_mcp_mode_combo = QComboBox(mcp_box)
        for mode in MCPMode:
            self.memory_mcp_mode_combo.addItem(mode.value, mode.value)
        mcp_form.addRow("mcp_mode", self.memory_mcp_mode_combo)

        self.memory_compression_strategy_combo = QComboBox(mcp_box)
        for strategy in CompressionStrategyType:
            self.memory_compression_strategy_combo.addItem(strategy.value, strategy.value)
        mcp_form.addRow("compression_strategy", self.memory_compression_strategy_combo)

        self.memory_max_working_messages_spin = self._create_int_spinbox(host, 1, 100000)
        mcp_form.addRow("max_working_messages", self.memory_max_working_messages_spin)

        self.memory_max_recent_tokens_spin = self._create_int_spinbox(host, 1, 10_000_000)
        mcp_form.addRow("max_recent_tokens", self.memory_max_recent_tokens_spin)

        self.memory_max_total_tokens_spin = self._create_int_spinbox(host, 1, 10_000_000)
        mcp_form.addRow("max_total_tokens", self.memory_max_total_tokens_spin)

        self.memory_remote_enabled_check = QCheckBox(mcp_box)
        mcp_form.addRow("remote.enabled", self.memory_remote_enabled_check)

        self.memory_remote_endpoint_edit = QLineEdit(mcp_box)
        mcp_form.addRow("remote.endpoint", self.memory_remote_endpoint_edit)

        self.memory_remote_api_key_edit = QLineEdit(mcp_box)
        mcp_form.addRow("remote.api_key", self.memory_remote_api_key_edit)

        self.memory_remote_timeout_spin = self._create_int_spinbox(host, 1, 36000)
        mcp_form.addRow("remote.timeout", self.memory_remote_timeout_spin)

        self.memory_remote_verify_ssl_check = QCheckBox(mcp_box)
        mcp_form.addRow("remote.verify_ssl", self.memory_remote_verify_ssl_check)

        form.addRow(mcp_box)

        scroll.setWidget(host)
        wrapper = QVBoxLayout(tab)
        wrapper.addWidget(scroll)
        self.tabs.addTab(tab, "Memory")

    def _build_sandbox_tab(self) -> None:
        tab = QWidget(self)
        scroll = QScrollArea(tab)
        scroll.setWidgetResizable(True)
        host = QWidget(scroll)
        root = QVBoxLayout(host)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        self.sandbox_enabled_check = QCheckBox("enabled", host)
        root.addWidget(self.sandbox_enabled_check)

        file_box = QGroupBox("File", host)
        file_form = QFormLayout(file_box)
        file_form.setSpacing(8)

        self.sandbox_file_enabled_check = QCheckBox(file_box)
        file_form.addRow("enabled", self.sandbox_file_enabled_check)

        self.sandbox_file_policy_combo = QComboBox(file_box)
        self.sandbox_file_policy_combo.addItems(["deny", "allow"])
        file_form.addRow("default_policy", self.sandbox_file_policy_combo)

        self.sandbox_allowed_dirs_edit = QPlainTextEdit(file_box)
        self.sandbox_allowed_dirs_edit.setPlaceholderText("one directory per line")
        self.sandbox_allowed_dirs_edit.setMaximumHeight(90)
        file_form.addRow("allowed_directories", self.sandbox_allowed_dirs_edit)

        self.sandbox_blocked_dirs_edit = QPlainTextEdit(file_box)
        self.sandbox_blocked_dirs_edit.setPlaceholderText("one directory per line")
        self.sandbox_blocked_dirs_edit.setMaximumHeight(90)
        file_form.addRow("blocked_directories", self.sandbox_blocked_dirs_edit)

        self.sandbox_blocked_ext_edit = QPlainTextEdit(file_box)
        self.sandbox_blocked_ext_edit.setPlaceholderText("one extension per line")
        self.sandbox_blocked_ext_edit.setMaximumHeight(90)
        file_form.addRow("blocked_extensions", self.sandbox_blocked_ext_edit)

        self.sandbox_blocked_files_edit = QPlainTextEdit(file_box)
        self.sandbox_blocked_files_edit.setPlaceholderText("one file pattern per line")
        self.sandbox_blocked_files_edit.setMaximumHeight(90)
        file_form.addRow("blocked_files", self.sandbox_blocked_files_edit)

        self.sandbox_max_file_size_spin = self._create_int_spinbox(file_box, 1, 1_000_000_000)
        file_form.addRow("max_file_size", self.sandbox_max_file_size_spin)

        self.sandbox_allow_write_check = QCheckBox(file_box)
        file_form.addRow("allow_write", self.sandbox_allow_write_check)

        self.sandbox_approval_write_check = QCheckBox(file_box)
        file_form.addRow("require_approval_for_write", self.sandbox_approval_write_check)

        self.sandbox_approval_read_check = QCheckBox(file_box)
        file_form.addRow(
            "require_approval_for_read_outside_allowed",
            self.sandbox_approval_read_check,
        )
        root.addWidget(file_box)

        network_box = QGroupBox("Network", host)
        network_form = QFormLayout(network_box)
        network_form.setSpacing(8)

        self.sandbox_network_enabled_check = QCheckBox(network_box)
        network_form.addRow("enabled", self.sandbox_network_enabled_check)

        self.sandbox_block_private_ip_check = QCheckBox(network_box)
        network_form.addRow("block_private_ips", self.sandbox_block_private_ip_check)

        self.sandbox_allowed_domains_edit = QPlainTextEdit(network_box)
        self.sandbox_allowed_domains_edit.setPlaceholderText("one domain pattern per line")
        self.sandbox_allowed_domains_edit.setMaximumHeight(100)
        network_form.addRow("allowed_domains", self.sandbox_allowed_domains_edit)

        self.sandbox_blocked_ports_edit = QPlainTextEdit(network_box)
        self.sandbox_blocked_ports_edit.setPlaceholderText("one port per line")
        self.sandbox_blocked_ports_edit.setMaximumHeight(100)
        network_form.addRow("blocked_ports", self.sandbox_blocked_ports_edit)
        root.addWidget(network_box)

        approval_box = QGroupBox("Approval", host)
        approval_form = QFormLayout(approval_box)
        approval_form.setSpacing(8)

        self.sandbox_approval_enabled_check = QCheckBox(approval_box)
        approval_form.addRow("enabled", self.sandbox_approval_enabled_check)

        self.sandbox_approval_timeout_spin = self._create_int_spinbox(approval_box, 1, 36000)
        approval_form.addRow("timeout_seconds", self.sandbox_approval_timeout_spin)

        self.sandbox_approval_remember_check = QCheckBox(approval_box)
        approval_form.addRow("remember_choice", self.sandbox_approval_remember_check)
        root.addWidget(approval_box)

        root.addStretch()
        scroll.setWidget(host)
        wrapper = QVBoxLayout(tab)
        wrapper.addWidget(scroll)
        self.tabs.addTab(tab, "Sandbox")

    def _build_planning_tab(self) -> None:
        tab = QWidget(self)
        form = QFormLayout(tab)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(8)

        self.planning_enabled_check = QCheckBox(tab)
        form.addRow("enabled", self.planning_enabled_check)

        self.planning_storage_combo = QComboBox(tab)
        self.planning_storage_combo.addItems(["json", "sqlite"])
        form.addRow("storage_type", self.planning_storage_combo)

        self.planning_storage_path_edit = QLineEdit(tab)
        form.addRow("storage_path", self.planning_storage_path_edit)

        self.planning_max_concurrency_spin = self._create_int_spinbox(tab, 1, 1024)
        form.addRow("max_concurrency", self.planning_max_concurrency_spin)

        self.planning_max_depth_spin = self._create_int_spinbox(tab, 1, 1000)
        form.addRow("max_plan_depth", self.planning_max_depth_spin)

        self.planning_auto_save_check = QCheckBox(tab)
        form.addRow("auto_save", self.planning_auto_save_check)

        self.tabs.addTab(tab, "Planning")

    def _build_rag_tab(self) -> None:
        tab = QWidget(self)
        form = QFormLayout(tab)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(8)

        self.rag_enabled_check = QCheckBox(tab)
        form.addRow("enabled", self.rag_enabled_check)

        self.rag_document_dir_edit = QLineEdit(tab)
        form.addRow("document_dir", self.rag_document_dir_edit)

        self.rag_chunk_size_spin = self._create_int_spinbox(tab, 1, 1000000)
        form.addRow("chunk_size", self.rag_chunk_size_spin)

        self.rag_chunk_overlap_spin = self._create_int_spinbox(tab, 0, 1000000)
        form.addRow("chunk_overlap", self.rag_chunk_overlap_spin)

        self.rag_top_k_spin = self._create_int_spinbox(tab, 0, 10000)
        form.addRow("top_k", self.rag_top_k_spin)

        self.tabs.addTab(tab, "RAG")

    def _load_from_disk(self) -> None:
        try:
            self._raw_config, self._config = load_with_raw(self._config_path)
        except ValueError as exc:
            self._set_status(str(exc), is_error=True)
            QMessageBox.critical(self, "Config Error", str(exc))
            return

        self._syncing_model_editor = True
        try:
            self._clear_error_styles()
            self.live2d_socket_edit.setText(self._config.live2dSocket)
            self._load_models_to_ui()
            self._load_memory_to_ui()
            self._load_sandbox_to_ui()
            self._load_planning_to_ui()
            self._load_rag_to_ui()
        finally:
            self._syncing_model_editor = False
        self._set_status("Configuration loaded.", is_error=False)

    def _load_models_to_ui(self) -> None:
        raw_models = self._raw_config.get("models")
        if isinstance(raw_models, list):
            self._models_raw = [copy.deepcopy(item) for item in raw_models if isinstance(item, dict)]
        else:
            self._models_raw = [model.to_dict() for model in self._config.models]

        self.model_list.clear()
        for idx, model in enumerate(self._models_raw):
            name = str(model.get("name") or f"model-{idx + 1}")
            item = QListWidgetItem(name)
            self.model_list.addItem(item)

        if self._models_raw:
            self.model_list.setCurrentRow(0)
        else:
            self._current_model_index = None
            self._clear_model_editor()

    def _load_memory_to_ui(self) -> None:
        memory = self._config.memory
        self.memory_enabled_check.setChecked(bool(memory.enabled))
        self.memory_storage_combo.setCurrentText(str(memory.storage_type))
        self.memory_data_dir_edit.setText(str(memory.data_dir))
        self.memory_max_messages_spin.setValue(int(memory.max_messages))
        self.memory_max_tokens_spin.setValue(int(memory.max_tokens))
        self.memory_compression_enabled_check.setChecked(bool(memory.compression_enabled))
        self.memory_compression_model_edit.setText(str(memory.compression_model))
        self.memory_threshold_spin.setValue(int(memory.compression_threshold_messages))
        self.memory_long_term_compression_check.setChecked(bool(memory.long_term_compression_enabled))
        self.memory_cutoff_days_spin.setValue(int(memory.compression_cutoff_days))
        self.memory_min_messages_spin.setValue(int(memory.compression_min_messages))
        self.memory_compress_on_start_check.setChecked(bool(memory.compress_on_startup))
        self.memory_enable_long_term_check.setChecked(bool(memory.enable_long_term))
        self.memory_long_term_storage_combo.setCurrentText(str(memory.long_term_storage))
        self.memory_auto_cleanup_check.setChecked(bool(memory.auto_cleanup))
        self.memory_max_sessions_spin.setValue(int(memory.max_sessions))
        self.memory_use_mcp_check.setChecked(bool(memory.use_mcp))
        self.memory_mcp_mode_combo.setCurrentText(str(memory.mcp_mode))
        self.memory_compression_strategy_combo.setCurrentText(str(memory.compression_strategy))
        self.memory_max_working_messages_spin.setValue(int(memory.max_working_messages))
        self.memory_max_recent_tokens_spin.setValue(int(memory.max_recent_tokens))
        self.memory_max_total_tokens_spin.setValue(int(memory.max_total_tokens))

        remote_cfg = memory.remote if isinstance(memory.remote, dict) else {}
        self.memory_remote_enabled_check.setChecked(bool(remote_cfg.get("enabled", False)))
        self.memory_remote_endpoint_edit.setText(str(remote_cfg.get("endpoint", "")))
        self.memory_remote_api_key_edit.setText(str(remote_cfg.get("api_key") or ""))
        self.memory_remote_timeout_spin.setValue(int(remote_cfg.get("timeout", 30)))
        self.memory_remote_verify_ssl_check.setChecked(bool(remote_cfg.get("verify_ssl", True)))

    def _load_sandbox_to_ui(self) -> None:
        sandbox = self._config.sandbox
        self.sandbox_enabled_check.setChecked(bool(sandbox.enabled))

        file_cfg = sandbox.file
        self.sandbox_file_enabled_check.setChecked(bool(file_cfg.enabled))
        self.sandbox_file_policy_combo.setCurrentText(str(file_cfg.default_policy))
        self.sandbox_allowed_dirs_edit.setPlainText("\n".join(file_cfg.allowed_directories))
        self.sandbox_blocked_dirs_edit.setPlainText("\n".join(file_cfg.blocked_directories))
        self.sandbox_blocked_ext_edit.setPlainText("\n".join(file_cfg.blocked_extensions))
        self.sandbox_blocked_files_edit.setPlainText("\n".join(file_cfg.blocked_files))
        self.sandbox_max_file_size_spin.setValue(int(file_cfg.max_file_size))
        self.sandbox_allow_write_check.setChecked(bool(file_cfg.allow_write))
        self.sandbox_approval_write_check.setChecked(bool(file_cfg.require_approval_for_write))
        self.sandbox_approval_read_check.setChecked(
            bool(file_cfg.require_approval_for_read_outside_allowed)
        )

        network_cfg = sandbox.network
        self.sandbox_network_enabled_check.setChecked(bool(network_cfg.enabled))
        self.sandbox_block_private_ip_check.setChecked(bool(network_cfg.block_private_ips))
        self.sandbox_allowed_domains_edit.setPlainText("\n".join(network_cfg.allowed_domains))
        self.sandbox_blocked_ports_edit.setPlainText("\n".join(str(port) for port in network_cfg.blocked_ports))

        approval_cfg = sandbox.approval
        self.sandbox_approval_enabled_check.setChecked(bool(approval_cfg.enabled))
        self.sandbox_approval_timeout_spin.setValue(int(approval_cfg.timeout_seconds))
        self.sandbox_approval_remember_check.setChecked(bool(approval_cfg.remember_choice))

    def _load_planning_to_ui(self) -> None:
        planning = self._config.planning
        self.planning_enabled_check.setChecked(bool(planning.enabled))
        self.planning_storage_combo.setCurrentText(str(planning.storage_type))
        self.planning_storage_path_edit.setText(str(planning.storage_path))
        self.planning_max_concurrency_spin.setValue(int(planning.max_concurrency))
        self.planning_max_depth_spin.setValue(int(planning.max_plan_depth))
        self.planning_auto_save_check.setChecked(bool(planning.auto_save))

    def _load_rag_to_ui(self) -> None:
        rag = self._config.rag
        self.rag_enabled_check.setChecked(bool(rag.enabled))
        self.rag_document_dir_edit.setText(str(rag.document_dir))
        self.rag_chunk_size_spin.setValue(int(rag.chunk_size))
        self.rag_chunk_overlap_spin.setValue(int(rag.chunk_overlap))
        self.rag_top_k_spin.setValue(int(rag.top_k))

    def _on_model_selected(self, row: int) -> None:
        if self._syncing_model_editor:
            return

        if self._current_model_index is not None:
            self._store_model_editor(self._current_model_index)

        if row < 0 or row >= len(self._models_raw):
            self._current_model_index = None
            self._clear_model_editor()
            return

        self._current_model_index = row
        model = self._models_raw[row]
        self._syncing_model_editor = True
        try:
            self.model_name_edit.setText(str(model.get("name", "") or ""))
            self.model_model_edit.setText(str(model.get("model", "") or ""))
            self.model_type_combo.setCurrentText(
                str(model.get("type", AIModelType.OllamaModel.value) or AIModelType.OllamaModel.value)
            )
            self.model_default_check.setChecked(bool(model.get("default", False)))
            self.model_streaming_check.setChecked(bool(model.get("streaming", True)))
            self.model_api_key_edit.setText(
                str(self._model_field_value(model, "api_key", "") or "")
            )
            self.model_temperature_spin.setValue(
                float(self._model_field_value(model, "temperature", 0.7))
            )
            self.model_top_p_edit.setText(self._optional_to_text(self._model_field_value(model, "top_p")))
            self.model_repeat_penalty_edit.setText(
                self._optional_to_text(self._model_field_value(model, "repeat_penalty"))
            )
            self.model_max_new_tokens_edit.setText(
                self._optional_to_text(self._model_field_value(model, "max_new_tokens"))
            )
            self.model_max_tool_retries_edit.setText(
                self._optional_to_text(self._model_field_value(model, "max_tool_call_retries"))
            )
            self._set_nullable_bool_combo(
                self.model_load_4bit_combo, self._model_field_value(model, "load_in_4bit")
            )
            self._set_nullable_bool_combo(
                self.model_load_8bit_combo, self._model_field_value(model, "load_in_8bit")
            )
            self._set_nullable_bool_combo(
                self.model_kv_quant_combo,
                self._model_field_value(model, "kv_cache_quantization"),
            )
            self._set_nullable_bool_combo(
                self.model_enable_cot_combo, self._model_field_value(model, "enable_cot")
            )
            self.model_system_prompt_edit.setPlainText(
                self._json_dump_or_text(model.get("system_prompt", ""))
            )
            self.model_options_edit.setPlainText(self._json_dump_or_text(model.get("options", {})))
        finally:
            self._syncing_model_editor = False

    def _store_model_editor(self, index: int) -> None:
        if self._syncing_model_editor:
            return
        if index < 0 or index >= len(self._models_raw):
            return

        model = self._models_raw[index]
        model["name"] = self.model_name_edit.text().strip()
        model["model"] = self.model_model_edit.text().strip()
        model["type"] = self.model_type_combo.currentText().strip()
        model["default"] = self.model_default_check.isChecked()
        model["streaming"] = self.model_streaming_check.isChecked()

        api_key = self.model_api_key_edit.text().strip()
        model["api_key"] = api_key if api_key else None

        model["temperature"] = float(self.model_temperature_spin.value())
        model["top_p"] = self._parse_optional_number(self.model_top_p_edit.text(), allow_int=True)
        model["repeat_penalty"] = self._parse_optional_number(
            self.model_repeat_penalty_edit.text(), allow_int=True
        )
        model["max_new_tokens"] = self._parse_optional_int(self.model_max_new_tokens_edit.text())
        model["max_tool_call_retries"] = self._parse_optional_int(
            self.model_max_tool_retries_edit.text()
        )
        model["load_in_4bit"] = self._get_nullable_bool_combo(self.model_load_4bit_combo)
        model["load_in_8bit"] = self._get_nullable_bool_combo(self.model_load_8bit_combo)
        model["kv_cache_quantization"] = self._get_nullable_bool_combo(self.model_kv_quant_combo)
        model["enable_cot"] = self._get_nullable_bool_combo(self.model_enable_cot_combo)
        model["system_prompt"] = self._parse_json_or_string(
            self.model_system_prompt_edit.toPlainText()
        )
        model["options"] = self._parse_json_or_original(self.model_options_edit.toPlainText())

        self._rename_model_item(index, model.get("name"))
        if model.get("default"):
            self._last_default_index = index

    def _clear_model_editor(self) -> None:
        self.model_name_edit.clear()
        self.model_model_edit.clear()
        self.model_type_combo.setCurrentText(AIModelType.OllamaModel.value)
        self.model_default_check.setChecked(False)
        self.model_streaming_check.setChecked(True)
        self.model_api_key_edit.clear()
        self.model_temperature_spin.setValue(0.7)
        self.model_top_p_edit.clear()
        self.model_repeat_penalty_edit.clear()
        self.model_max_new_tokens_edit.clear()
        self.model_max_tool_retries_edit.clear()
        self._set_nullable_bool_combo(self.model_load_4bit_combo, None)
        self._set_nullable_bool_combo(self.model_load_8bit_combo, None)
        self._set_nullable_bool_combo(self.model_kv_quant_combo, None)
        self._set_nullable_bool_combo(self.model_enable_cot_combo, None)
        self.model_system_prompt_edit.clear()
        self.model_options_edit.clear()

    def _rename_model_item(self, index: int, name: Any) -> None:
        if index < 0 or index >= self.model_list.count():
            return
        item = self.model_list.item(index)
        if item is None:
            return
        title = str(name).strip() or f"model-{index + 1}"
        item.setText(title)

    def _on_add_model(self) -> None:
        if self._current_model_index is not None:
            self._store_model_editor(self._current_model_index)
        new_model = {
            "name": f"model-{len(self._models_raw) + 1}",
            "model": "",
            "type": AIModelType.OllamaModel.value,
            "system_prompt": "",
            "default": False,
            "options": {},
            "temperature": 0.7,
            "api_key": None,
            "streaming": True,
            "load_in_4bit": None,
            "load_in_8bit": None,
            "kv_cache_quantization": None,
            "top_p": None,
            "repeat_penalty": None,
            "max_new_tokens": None,
            "enable_cot": None,
            "max_tool_call_retries": None,
        }
        self._models_raw.append(new_model)
        self.model_list.addItem(QListWidgetItem(str(new_model["name"])))
        self.model_list.setCurrentRow(len(self._models_raw) - 1)

    def _on_copy_model(self) -> None:
        if self._current_model_index is None:
            return
        self._store_model_editor(self._current_model_index)
        model = copy.deepcopy(self._models_raw[self._current_model_index])
        model_name = str(model.get("name") or "model")
        model["name"] = f"{model_name}-copy"
        model["default"] = False
        self._models_raw.insert(self._current_model_index + 1, model)
        self.model_list.insertItem(self._current_model_index + 1, QListWidgetItem(str(model["name"])))
        self.model_list.setCurrentRow(self._current_model_index + 1)

    def _on_delete_model(self) -> None:
        row = self.model_list.currentRow()
        if row < 0 or row >= len(self._models_raw):
            return
        self.model_list.takeItem(row)
        self._models_raw.pop(row)
        if not self._models_raw:
            self._current_model_index = None
            self._clear_model_editor()
            return
        next_row = min(row, len(self._models_raw) - 1)
        self.model_list.setCurrentRow(next_row)

    def _on_move_model_up(self) -> None:
        row = self.model_list.currentRow()
        if row <= 0:
            return
        self._store_model_editor(row)
        self._models_raw[row - 1], self._models_raw[row] = self._models_raw[row], self._models_raw[row - 1]
        item = self.model_list.takeItem(row)
        self.model_list.insertItem(row - 1, item)
        self.model_list.setCurrentRow(row - 1)

    def _on_move_model_down(self) -> None:
        row = self.model_list.currentRow()
        if row < 0 or row >= len(self._models_raw) - 1:
            return
        self._store_model_editor(row)
        self._models_raw[row], self._models_raw[row + 1] = self._models_raw[row + 1], self._models_raw[row]
        item = self.model_list.takeItem(row)
        self.model_list.insertItem(row + 1, item)
        self.model_list.setCurrentRow(row + 1)

    def _on_save_clicked(self) -> None:
        if self._current_model_index is not None:
            self._store_model_editor(self._current_model_index)

        edited_dict = self._build_edited_config_dict()
        models, auto_fixed = normalize_models_default(
            edited_dict.get("models", []),
            self._last_default_index,
        )
        edited_dict["models"] = models

        merged = merge_known_fields(self._raw_config, edited_dict)
        errors = validate_config_dict(merged)
        if errors:
            self._show_validation_errors(errors)
            return

        old_config = self._config
        try:
            save_config_atomic(self._config_path, merged)
            self._raw_config, self._config = load_with_raw(self._config_path)
        except Exception as exc:
            logger.error("Failed to save config: %s", exc, exc_info=True)
            self._set_status(f"Failed to save config: {exc}", is_error=True)
            QMessageBox.critical(self, "Save Failed", str(exc))
            return

        self._load_models_to_ui()
        decision = decide_runtime_apply(old_config, self._config)
        self._set_status("Configuration saved.", is_error=False)

        if auto_fixed:
            QMessageBox.information(
                self,
                "Default Model Updated",
                "Multiple default models were selected. The latest selected model was kept as default.",
            )

        if self._on_saved is not None:
            self._on_saved(self._config, decision)
        self.config_saved.emit(self._config, decision)

    def _show_validation_errors(self, errors: list[ValidationError]) -> None:
        self._clear_error_styles()
        for error in errors:
            self._mark_field_error(error.field)

        message = "\n".join(f"- {err.field}: {err.message}" for err in errors)
        self._set_status("Validation failed. Please review the highlighted fields.", is_error=True)
        QMessageBox.warning(self, "Validation Error", message)
        first = errors[0].field
        self._focus_tab_for_field(first)

    def _focus_tab_for_field(self, field: str) -> None:
        field_lower = field.lower()
        if field_lower.startswith("live2dsocket"):
            self.tabs.setCurrentIndex(0)
        elif field_lower.startswith("models"):
            self.tabs.setCurrentIndex(1)
        elif field_lower.startswith("memory"):
            self.tabs.setCurrentIndex(2)
        elif field_lower.startswith("sandbox"):
            self.tabs.setCurrentIndex(3)
        elif field_lower.startswith("planning"):
            self.tabs.setCurrentIndex(4)
        elif field_lower.startswith("rag"):
            self.tabs.setCurrentIndex(5)

    def _clear_error_styles(self) -> None:
        widgets = [
            self.live2d_socket_edit,
            self.model_name_edit,
            self.model_model_edit,
            self.model_type_combo,
            self.model_system_prompt_edit,
            self.model_options_edit,
            self.model_temperature_spin,
            self.model_top_p_edit,
            self.model_repeat_penalty_edit,
            self.model_max_new_tokens_edit,
            self.model_max_tool_retries_edit,
            self.memory_data_dir_edit,
            self.memory_max_messages_spin,
            self.memory_max_tokens_spin,
            self.memory_threshold_spin,
            self.memory_cutoff_days_spin,
            self.memory_min_messages_spin,
            self.memory_max_sessions_spin,
            self.memory_mcp_mode_combo,
            self.memory_compression_strategy_combo,
            self.memory_max_working_messages_spin,
            self.memory_max_recent_tokens_spin,
            self.memory_max_total_tokens_spin,
            self.memory_remote_enabled_check,
            self.memory_remote_endpoint_edit,
            self.memory_remote_api_key_edit,
            self.memory_remote_timeout_spin,
            self.memory_remote_verify_ssl_check,
            self.sandbox_file_policy_combo,
            self.sandbox_max_file_size_spin,
            self.sandbox_blocked_ports_edit,
            self.sandbox_approval_timeout_spin,
            self.planning_storage_combo,
            self.planning_max_concurrency_spin,
            self.planning_max_depth_spin,
            self.rag_chunk_size_spin,
            self.rag_chunk_overlap_spin,
            self.rag_top_k_spin,
        ]
        for widget in widgets:
            widget.setStyleSheet("")

    def _mark_field_error(self, field: str) -> None:
        field_lower = field.lower()
        if field_lower == "live2dsocket":
            self.live2d_socket_edit.setStyleSheet("border: 1px solid #c62828;")
            return

        if field_lower.startswith("models["):
            model_index = self._extract_model_index(field_lower)
            if model_index is not None and 0 <= model_index < len(self._models_raw):
                self.model_list.setCurrentRow(model_index)
            if ".name" in field_lower:
                self.model_name_edit.setStyleSheet("border: 1px solid #c62828;")
            elif ".model" in field_lower:
                self.model_model_edit.setStyleSheet("border: 1px solid #c62828;")
            elif ".type" in field_lower:
                self.model_type_combo.setStyleSheet("border: 1px solid #c62828;")
            elif ".system_prompt" in field_lower:
                self.model_system_prompt_edit.setStyleSheet("border: 1px solid #c62828;")
            elif ".options" in field_lower:
                self.model_options_edit.setStyleSheet("border: 1px solid #c62828;")
            elif ".temperature" in field_lower:
                self.model_temperature_spin.setStyleSheet("border: 1px solid #c62828;")
            elif ".top_p" in field_lower:
                self.model_top_p_edit.setStyleSheet("border: 1px solid #c62828;")
            elif ".repeat_penalty" in field_lower:
                self.model_repeat_penalty_edit.setStyleSheet("border: 1px solid #c62828;")
            elif ".max_new_tokens" in field_lower:
                self.model_max_new_tokens_edit.setStyleSheet("border: 1px solid #c62828;")
            elif ".max_tool_call_retries" in field_lower:
                self.model_max_tool_retries_edit.setStyleSheet("border: 1px solid #c62828;")
            return

        if field_lower.startswith("live2dexpressions"):
            self.tabs.setCurrentIndex(0)
            return

        memory_field_map = {
            "memory.max_messages": self.memory_max_messages_spin,
            "memory.max_tokens": self.memory_max_tokens_spin,
            "memory.compression_threshold_messages": self.memory_threshold_spin,
            "memory.compression_cutoff_days": self.memory_cutoff_days_spin,
            "memory.compression_min_messages": self.memory_min_messages_spin,
            "memory.max_sessions": self.memory_max_sessions_spin,
            "memory.max_working_messages": self.memory_max_working_messages_spin,
            "memory.max_recent_tokens": self.memory_max_recent_tokens_spin,
            "memory.max_total_tokens": self.memory_max_total_tokens_spin,
            "memory.mcp_mode": self.memory_mcp_mode_combo,
            "memory.compression_strategy": self.memory_compression_strategy_combo,
            "memory.remote.enabled": self.memory_remote_enabled_check,
            "memory.remote.endpoint": self.memory_remote_endpoint_edit,
            "memory.remote.api_key": self.memory_remote_api_key_edit,
            "memory.remote.timeout": self.memory_remote_timeout_spin,
            "memory.remote.verify_ssl": self.memory_remote_verify_ssl_check,
        }
        if field_lower in memory_field_map:
            memory_field_map[field_lower].setStyleSheet("border: 1px solid #c62828;")
            return

        if field_lower == "sandbox.file.default_policy":
            self.sandbox_file_policy_combo.setStyleSheet("border: 1px solid #c62828;")
            return
        if field_lower == "sandbox.file.max_file_size":
            self.sandbox_max_file_size_spin.setStyleSheet("border: 1px solid #c62828;")
            return
        if field_lower.startswith("sandbox.network.blocked_ports"):
            self.sandbox_blocked_ports_edit.setStyleSheet("border: 1px solid #c62828;")
            return
        if field_lower == "sandbox.approval.timeout_seconds":
            self.sandbox_approval_timeout_spin.setStyleSheet("border: 1px solid #c62828;")
            return

        planning_field_map = {
            "planning.storage_type": self.planning_storage_combo,
            "planning.max_concurrency": self.planning_max_concurrency_spin,
            "planning.max_plan_depth": self.planning_max_depth_spin,
        }
        if field_lower in planning_field_map:
            planning_field_map[field_lower].setStyleSheet("border: 1px solid #c62828;")
            return

        rag_field_map = {
            "rag.chunk_size": self.rag_chunk_size_spin,
            "rag.chunk_overlap": self.rag_chunk_overlap_spin,
            "rag.top_k": self.rag_top_k_spin,
        }
        if field_lower in rag_field_map:
            rag_field_map[field_lower].setStyleSheet("border: 1px solid #c62828;")

    @staticmethod
    def _extract_model_index(field: str) -> int | None:
        if not field.startswith("models["):
            return None
        end = field.find("]")
        if end <= len("models["):
            return None
        index_text = field[len("models["):end]
        try:
            return int(index_text)
        except ValueError:
            return None

    def _build_edited_config_dict(self) -> dict[str, Any]:
        memory = {
            "enabled": self.memory_enabled_check.isChecked(),
            "storage_type": self.memory_storage_combo.currentText(),
            "data_dir": self.memory_data_dir_edit.text().strip(),
            "max_messages": int(self.memory_max_messages_spin.value()),
            "max_tokens": int(self.memory_max_tokens_spin.value()),
            "compression_enabled": self.memory_compression_enabled_check.isChecked(),
            "compression_model": self.memory_compression_model_edit.text().strip(),
            "compression_threshold_messages": int(self.memory_threshold_spin.value()),
            "long_term_compression_enabled": self.memory_long_term_compression_check.isChecked(),
            "compression_cutoff_days": int(self.memory_cutoff_days_spin.value()),
            "compression_min_messages": int(self.memory_min_messages_spin.value()),
            "compress_on_startup": self.memory_compress_on_start_check.isChecked(),
            "enable_long_term": self.memory_enable_long_term_check.isChecked(),
            "long_term_storage": self.memory_long_term_storage_combo.currentText(),
            "auto_cleanup": self.memory_auto_cleanup_check.isChecked(),
            "max_sessions": int(self.memory_max_sessions_spin.value()),
            "use_mcp": self.memory_use_mcp_check.isChecked(),
            "mcp_mode": self.memory_mcp_mode_combo.currentText(),
            "compression_strategy": self.memory_compression_strategy_combo.currentText(),
            "max_working_messages": int(self.memory_max_working_messages_spin.value()),
            "max_recent_tokens": int(self.memory_max_recent_tokens_spin.value()),
            "max_total_tokens": int(self.memory_max_total_tokens_spin.value()),
            "remote": {
                "enabled": self.memory_remote_enabled_check.isChecked(),
                "endpoint": self.memory_remote_endpoint_edit.text().strip(),
                "api_key": self.memory_remote_api_key_edit.text().strip() or None,
                "timeout": int(self.memory_remote_timeout_spin.value()),
                "verify_ssl": self.memory_remote_verify_ssl_check.isChecked(),
            },
        }

        sandbox = {
            "enabled": self.sandbox_enabled_check.isChecked(),
            "file": {
                "enabled": self.sandbox_file_enabled_check.isChecked(),
                "default_policy": self.sandbox_file_policy_combo.currentText(),
                "allowed_directories": self._parse_lines(self.sandbox_allowed_dirs_edit),
                "blocked_directories": self._parse_lines(self.sandbox_blocked_dirs_edit),
                "blocked_extensions": self._parse_lines(self.sandbox_blocked_ext_edit),
                "blocked_files": self._parse_lines(self.sandbox_blocked_files_edit),
                "max_file_size": int(self.sandbox_max_file_size_spin.value()),
                "allow_write": self.sandbox_allow_write_check.isChecked(),
                "require_approval_for_write": self.sandbox_approval_write_check.isChecked(),
                "require_approval_for_read_outside_allowed": self.sandbox_approval_read_check.isChecked(),
            },
            "network": {
                "enabled": self.sandbox_network_enabled_check.isChecked(),
                "block_private_ips": self.sandbox_block_private_ip_check.isChecked(),
                "allowed_domains": self._parse_lines(self.sandbox_allowed_domains_edit),
                "blocked_ports": self._parse_lines_as_ints(self.sandbox_blocked_ports_edit),
            },
            "approval": {
                "enabled": self.sandbox_approval_enabled_check.isChecked(),
                "timeout_seconds": int(self.sandbox_approval_timeout_spin.value()),
                "remember_choice": self.sandbox_approval_remember_check.isChecked(),
            },
        }

        planning = {
            "enabled": self.planning_enabled_check.isChecked(),
            "storage_type": self.planning_storage_combo.currentText(),
            "storage_path": self.planning_storage_path_edit.text().strip(),
            "max_concurrency": int(self.planning_max_concurrency_spin.value()),
            "max_plan_depth": int(self.planning_max_depth_spin.value()),
            "auto_save": self.planning_auto_save_check.isChecked(),
        }

        rag = {
            "enabled": self.rag_enabled_check.isChecked(),
            "document_dir": self.rag_document_dir_edit.text().strip(),
            "chunk_size": int(self.rag_chunk_size_spin.value()),
            "chunk_overlap": int(self.rag_chunk_overlap_spin.value()),
            "top_k": int(self.rag_top_k_spin.value()),
        }

        return {
            "live2dSocket": self.live2d_socket_edit.text().strip(),
            "models": [copy.deepcopy(model) for model in self._models_raw],
            "memory": memory,
            "sandbox": sandbox,
            "planning": planning,
            "rag": rag,
        }

    def _set_status(self, message: str, *, is_error: bool) -> None:
        color = "#b22222" if is_error else "#2d7d46"
        self.status_label.setStyleSheet(f"color: {color};")
        self.status_label.setText(message)

    @staticmethod
    def _parse_lines(text_edit: QPlainTextEdit) -> list[str]:
        return [line.strip() for line in text_edit.toPlainText().splitlines() if line.strip()]

    @staticmethod
    def _parse_lines_as_ints(text_edit: QPlainTextEdit) -> list[Any]:
        values: list[Any] = []
        for line in text_edit.toPlainText().splitlines():
            item = line.strip()
            if not item:
                continue
            try:
                values.append(int(item))
            except ValueError:
                values.append(item)
        return values

    @staticmethod
    def _create_nullable_bool_combo(parent: QWidget) -> QComboBox:
        combo = QComboBox(parent)
        combo.addItem("null", None)
        combo.addItem("true", True)
        combo.addItem("false", False)
        return combo

    @staticmethod
    def _set_nullable_bool_combo(combo: QComboBox, value: Any) -> None:
        if value is True:
            combo.setCurrentIndex(1)
        elif value is False:
            combo.setCurrentIndex(2)
        else:
            combo.setCurrentIndex(0)

    @staticmethod
    def _get_nullable_bool_combo(combo: QComboBox) -> bool | None:
        return combo.currentData()

    @staticmethod
    def _create_int_spinbox(parent: QWidget, minimum: int, maximum: int) -> QSpinBox:
        spin = QSpinBox(parent)
        spin.setRange(minimum, maximum)
        return spin

    @staticmethod
    def _optional_to_text(value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _model_field_value(model: dict[str, Any], field: str, default: Any = None) -> Any:
        value = model.get(field, None)
        if value is not None:
            return value

        options = model.get("options")
        if isinstance(options, dict):
            option_value = options.get(field, None)
            if option_value is not None:
                return option_value

        return default

    @staticmethod
    def _parse_optional_number(raw_value: str, *, allow_int: bool = True) -> Any:
        value = raw_value.strip()
        if not value:
            return None
        try:
            parsed = float(value)
            if allow_int and parsed.is_integer():
                return int(parsed)
            return parsed
        except ValueError:
            return value

    @staticmethod
    def _parse_optional_int(raw_value: str) -> Any:
        value = raw_value.strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return value

    @staticmethod
    def _parse_json_or_string(raw: str) -> Any:
        text = raw.strip()
        if not text:
            return ""
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        return raw

    @staticmethod
    def _parse_json_or_original(raw: str) -> Any:
        text = raw.strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except Exception:
            return raw

    @staticmethod
    def _json_dump_or_text(value: Any) -> str:
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            return str(value)
