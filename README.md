# Live2D Agent

> A Python-based desktop AI Agent application with PySide6 Qt UI that connects to Live2D models via WebSocket.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[English](#english) | [中文](#中文)

---

## English

### 🤖 What is Live2D Agent

Live2D Agent is a desktop AI Agent that brings your virtual characters to life. Connect to any Live2D model via WebSocket, chat with multiple AI backends including local Ollama/Transformers and online APIs, and extend functionality through an extensible skill system.

### ✨ Key Features

- **Multiple AI Backends** - Supports Ollama, Transformers, and online API providers
- **Live2D WebSocket Integration** - Seamless connection to Live2D models for real-time interaction
- **Extensible Skill System** - Hot-reloadable skills and tools for custom functionality
- **Multi-layer Memory** - Compressed conversation memory with long-term storage and keyword search
- **Security Sandbox** - Isolated environment for safe file and network operations
- **Modern PySide6 UI** - Clean Qt-based interface with floating input and speech bubbles
- **System Tray Support** - Runs in background with quick access from system tray

### 🚀 Quick Start

1. Clone the repository and install dependencies
```bash
git clone https://github.com/yourusername/live2d-agent.git
cd live2d-agent
poetry install
```

Live2D Agent currently follows the Python version declared in `pyproject.toml`: **Python >=3.14,<3.15**.

2. Copy and configure your settings
```bash
cp config.example.json config.json
# Edit config.json with your AI model settings
```

If you want the modular prompt setup, copy `config.example-prompt-modules.json` to `config.json` instead.

3. Start your Live2D WebSocket service

4. Run the application
```bash
poetry run python __main__.py
```

### 📋 Prerequisites

- Python >=3.14,<3.15
- A running Live2D WebSocket service (separate)
- Optional: GPU for local Transformers inference

### 📸 Screenshots

*Screenshots will be added here showing the UI in action*

### 📖 Documentation

- [USAGE.md](./USAGE.md) - Detailed usage guide
- [DEVELOPMENT.md](./DEVELOPMENT.md) - Development setup and contribution guidelines
- [ARCHITECTURE.md](./ARCHITECTURE.md) - Project architecture overview
- [CONTRIBUTING.md](./CONTRIBUTING.md) - Contribution guidelines
- [SECURITY.md](./SECURITY.md) - Security policy
- [CLAUDE.md](./CLAUDE.md) - Development notes for AI coding assistants

### 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

### 🙏 Acknowledgments

- Thanks to the PySide6 team for the excellent Qt bindings
- Live2D Inc. for Live2D technology
- The Ollama project for local AI inference
- All contributors who help improve this project

---

## 中文

### 🤖 Live2D Agent 是什么

Live2D Agent 是一个桌面 AI 智能体应用，让你的虚拟角色活起来。通过 WebSocket 连接任意 Live2D 模型，支持多种 AI 后端（本地 Ollama/Transformers 和在线 API），可通过可扩展技能系统扩展功能。

### ✨ 主要特性

- **多种 AI 后端** - 支持 Ollama、Transformers 和在线 API 提供商
- **Live2D WebSocket 集成** - 与 Live2D 模型无缝连接，实现实时交互
- **可扩展技能系统** - 支持热重载技能和工具，方便自定义功能
- **多层记忆系统** - 压缩对话记忆，支持长期存储和关键词搜索
- **安全沙箱** - 隔离环境确保文件和网络操作安全
- **现代 PySide6 UI** - 简洁的 Qt 界面，支持浮动输入和语音气泡
- **系统托盘支持** - 后台运行，可从系统托盘快速访问

### 🚀 快速开始

1. 克隆仓库并安装依赖
```bash
git clone https://github.com/yourusername/live2d-agent.git
cd live2d-agent
poetry install
```

2. 复制并配置设置
```bash
cp config.example.json config.json
# 编辑 config.json 填入你的 AI 模型设置
```

如果你想使用模块化提示词，也可以把 `config.example-prompt-modules.json` 复制为 `config.json`。

3. 启动你的 Live2D WebSocket 服务

4. 运行应用
```bash
poetry run python __main__.py
```

### 📋 环境要求

- Python >=3.14,<3.15
- 运行中的 Live2D WebSocket 服务（独立部署）
- 可选：GPU 加速本地 Transformers 推理

### 📸 截图

*截图将在此处展示 UI 效果*

### 📖 文档

- [USAGE.md](./USAGE.md) - 详细使用指南
- [DEVELOPMENT.md](./DEVELOPMENT.md) - 开发设置和贡献指南
- [ARCHITECTURE.md](./ARCHITECTURE.md) - 项目架构概览
- [CONTRIBUTING.md](./CONTRIBUTING.md) - 贡献指南
- [SECURITY.md](./SECURITY.md) - 安全政策
- [CLAUDE.md](./CLAUDE.md) - 给 AI 编码助手的开发说明

### 🙏 致谢

- 感谢 PySide6 团队提供优秀的 Qt 绑定
- Live2D Inc. 提供 Live2D 技术
- Ollama 项目提供本地 AI 推理
- 所有帮助改进本项目的贡献者

### ⚙️ 配置说明

项目提供了两个真实存在的配置模板：

- `config.example.json`：内联 `system_prompt` 的完整示例
- `config.example-prompt-modules.json`：引用 `prompt_modules/` 中模块化提示词的示例

请任选一个复制为运行时使用的 `config.json`，并按以下步骤配置：

1. 复制配置模板：
```bash
cp config.example.json config.json
```

2. 编辑 `config.json`，填入你的配置信息：

- **live2dSocket**: Live2D WebSocket 服务地址
- **models**: 模型配置数组，可以配置多个模型
  - `name`: 模型名称
  - `model`: 模型标识符或本地路径
  - `type`: 模型类型 (`ollama` | `transformers` | `online`)
  - `api_key`: API 密钥（仅 `online` 类型需要）
  - `system_prompt`: 系统提示词
  - `default`: 是否为默认模型
  - `options`: 模型参数配置

> **安全提示**: `config.json` 包含敏感信息（如 API Key），已添加到 `.gitignore`，不会被提交到版本控制系统。

### 支持的模型类型

1. **ollama**: 本地 Ollama 服务运行的模型
2. **transformers**: 使用 Hugging Face Transformers 加载的本地模型
3. **online**: 在线 API 模型（如火山引擎方舟平台）

## 更新日志

26/3/23 删除所有残留的golang代码
26/3/29 使用PyInstaller打包
