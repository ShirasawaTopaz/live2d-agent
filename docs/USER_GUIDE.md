# Live2oder 使用手册

**版本：v0.1.0**  
**最后更新：2026年4月**

---

## 目录

- [1. 简介](#1-简介)
  - [1.1 什么是 Live2oder](#11-什么是-live2oder)
  - [1.2 主要功能](#12-主要功能)
  - [1.3 系统架构](#13-系统架构)
- [2. 快速开始](#2-快速开始)
  - [2.1 系统要求](#21-系统要求)
  - [2.2 安装步骤](#22-安装步骤)
  - [2.3 首次运行](#23-首次运行)
- [3. 配置详解](#3-配置详解)
  - [3.1 配置文件结构](#31-配置文件结构)
  - [3.2 Live2D 连接配置](#32-live2d-连接配置)
  - [3.3 模型配置](#33-模型配置)
  - [3.4 记忆系统配置](#34-记忆系统配置)
- [4. 功能使用](#4-功能使用)
  - [4.1 启动与退出](#41-启动与退出)
  - [4.2 系统托盘](#42-系统托盘)
  - [4.3 AI 助手交互](#43-ai-助手交互)
  - [4.4 Live2D 控制功能](#44-live2d-控制功能)
- [5. 提示词模块](#5-提示词模块)
  - [5.1 模块化提示词系统](#51-模块化提示词系统)
  - [5.2 预定义模块](#52-预定义模块)
  - [5.3 自定义提示词](#53-自定义提示词)
- [6. 常见问题与故障排除](#6-常见问题与故障排除)
  - [6.1 配置问题](#61-配置问题)
  - [6.2 连接问题](#62-连接问题)
  - [6.3 模型运行问题](#63-模型运行问题)
  - [6.4 UI 显示问题](#64-ui-显示问题)
  - [6.5 性能优化建议](#65-性能优化建议)

---

## 1. 简介

### 1.1 什么是 Live2oder

**Live2oder** 是一款基于 Python 开发的桌面 AI 虚拟助手应用程序，它结合了 PySide6 Qt 框架构建的现代化用户界面，通过 WebSocket 与 Live2D 模型进行实时交互，支持多种 AI 模型后端，为用户提供沉浸式的虚拟助手体验。

项目名称 "Live2oder" 源自 "Live2D" 与 "Order" 的组合，寓意通过这个软件你可以像下达指令一样与你的 Live2D 虚拟角色进行互动。

### 1.2 主要功能

#### Live2D 集成
- 通过 WebSocket 与 Live2DViewerEX 实时通信
- 控制模型表情、动作、位置
- 显示对话气泡文本
- 切换背景、播放音效

#### 多模型支持
- **Ollama**：本地运行的开源模型（如 gemma3、llama3 等）
- **Transformers**：使用 Hugging Face 加载本地模型
- **在线 API**：支持 OpenAI 兼容 API（如火山引擎方舟平台）

#### 丰富工具集
- **文件操作**：读取、写入、搜索文件
- **Office 处理**：支持 Word、Excel、PowerPoint、PDF
- **网络搜索**：搜索网络信息
- **Live2D 控制**：完整的模型控制功能

#### 智能记忆系统
- 对话历史持久化存储（支持 JSON 和 SQLite）
- 自动上下文压缩，避免 token 溢出
- 长期记忆存储，支持关键词搜索
- 多会话管理

#### 现代化 UI
- 悬浮输入框，随时可召唤
- 语音气泡窗口，自然显示对话
- 系统托盘图标，常驻后台
- 位置记忆，记住上次窗口位置

#### 模块化提示词
- 预定义多种场景提示词模块
- 支持自定义提示词组合
- 能力模块、规则模块、语言模块、个性模块

#### 技能系统
- 动态加载外部技能
- 模块化工具和提示词组合
- 依赖管理

### 1.3 系统架构

Live2oder 采用分层架构设计，各层职责清晰，便于维护和扩展。

**架构层次说明：**

1. **UI 层**：使用 PySide6 构建，提供悬浮输入框、气泡窗口、系统托盘
2. **Agent 层**：核心控制层，协调模型、工具、记忆的交互
3. **模型支持层**：三种模型实现（Ollama、Transformers、在线 API）
4. **工具层**：10+ 种工具，覆盖文件、Office、搜索、Live2D 控制
5. **记忆系统**：完整的记忆管理，包括会话、上下文、摘要、长期记忆
6. **通信层**：WebSocket 客户端，与 Live2DViewerEX 实时通信

---

## 2. 快速开始

### 2.1 系统要求

#### 操作系统
- **Windows**: Windows 10/11 (64位)
- **Linux**: Ubuntu 20.04+, CentOS 8+ 等主流发行版
- **macOS**: macOS 12+ (Intel/Apple Silicon)

#### Python 版本
- **Python**: 3.14+（必须），建议使用 Python 3.14.x

#### 硬件要求

**最低配置：**
- CPU: 4 核以上
- 内存: 8 GB RAM
- 磁盘空间: 2 GB（不含模型文件）

**推荐配置：**
- CPU: 8 核以上
- 内存: 16 GB RAM
- 显卡: NVIDIA GPU（CUDA 支持，可选但推荐）
- 磁盘空间: 20 GB+（含模型文件）

#### 依赖软件

**必需：**
- Python 3.14+
- pip 或 Poetry（包管理器）

**推荐：**
- Ollama（用于运行本地模型）
- Live2DViewerEX（用于显示 Live2D 模型）
- Git（用于克隆仓库）

### 2.2 安装步骤

#### 步骤 1: 克隆或下载项目

```bash
# 使用 Git 克隆
git clone https://github.com/your-username/live2oder.git
cd live2oder

# 或者直接下载 ZIP 解压
# 解压后进入 live2oder 目录
```

#### 步骤 2: 创建配置文件

```bash
# 复制配置模板
cp config.example.json config.json

# 或者使用 PowerShell (Windows)
Copy-Item config.example.json config.json
```

#### 步骤 3: 安装 Python 依赖

**使用 Poetry（推荐）：**

```bash
# 安装 Poetry
pip install poetry

# 安装依赖
poetry install

# 激活虚拟环境
poetry shell
```

**使用 pip：**

```bash
# 创建虚拟环境（推荐）
python -m venv .venv

# 激活虚拟环境
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
# 或者直接从 pyproject.toml
pip install poetry && poetry install
```

#### 步骤 4: 配置模型

编辑 `config.json` 文件，配置你想使用的 AI 模型。

**示例配置（Ollama）：**

```json
{
    "live2dSocket": "ws://127.0.0.1:10086/api",
    "models": [
        {
            "name": "ollama-gemma",
            "model": "gemma3:1b",
            "type": "ollama",
            "system_prompt": "你是一个可爱的Live2D虚拟助手...",
            "default": true,
            "streaming": true,
            "options": {
                "temperature": 0.3,
                "top_p": 0.9
            }
        }
    ],
    "memory": {
        "enabled": true,
        "storage_type": "json",
        "data_dir": "./data/memory",
        "max_messages": 20,
        "max_tokens": 4096
    }
}
```

**安装 Ollama 和模型（如选择 Ollama）：**

```bash
# 安装 Ollama（访问 https://ollama.com 下载安装程序）

# 拉取模型
ollama pull gemma3:1b

# 测试模型
ollama run gemma3:1b
```

### 2.3 首次运行

#### 步骤 1: 启动 Live2DViewerEX（可选但推荐）

如果你希望在桌面上显示 Live2D 角色：

1. 安装并启动 **Live2DViewerEX**
2. 确保其 WebSocket 服务器在 `ws://127.0.0.1:10086/api` 运行
3. 加载你喜欢的 Live2D 模型

#### 步骤 2: 启动 Live2oder

```bash
# 使用 Poetry
poetry run python __main__.py

# 或者在虚拟环境中
python __main__.py

# Windows 双击运行（如果配置了）
# 或者使用 PowerShell
python __main__.py
```

#### 步骤 3: 验证启动成功

启动成功后，你会看到：

1. **系统托盘图标**：屏幕右下角出现蓝色 "L" 图标
2. **悬浮输入框**：在屏幕右下角出现输入框窗口
3. **气泡通知**：托盘显示 "程序已在系统托盘运行" 的提示

#### 步骤 4: 测试基本功能

在输入框中输入：

```
你好，请介绍一下自己
```

按回车或点击发送按钮，你应该看到：

1. **气泡窗口**：显示 AI 助手的回复
2. **Live2D 模型**：如果连接了 Live2D，模型会同步显示气泡

如果一切正常，恭喜你！Live2oder 已经成功运行。

---

## 3. 配置详解

### 3.1 配置文件结构

Live2oder 的配置文件 `config.json` 采用 JSON 格式，包含以下主要部分：

```json
{
    "live2dSocket": "ws://127.0.0.1:10086/api",
    "models": [...],
    "memory": {...}
}
```

#### 配置项概览

| 配置项 | 类型 | 必需 | 默认值 | 说明 |
|--------|------|------|--------|------|
| `live2dSocket` | string | 否 | `ws://127.0.0.1:10086/api` | Live2D WebSocket 地址 |
| `models` | array | 是 | - | 模型配置数组 |
| `memory` | object | 否 | 默认配置 | 记忆系统配置 |

### 3.2 Live2D 连接配置

#### `live2dSocket` 配置项

```json
{
    "live2dSocket": "ws://127.0.0.1:10086/api"
}
```

**配置说明：**

- **协议**：支持 `ws://`（WebSocket）和 `wss://`（安全 WebSocket）
- **地址**：Live2DViewerEX 的 WebSocket 服务器地址
- **端口**：默认为 10086，可在 Live2DViewerEX 中修改
- **路径**：默认为 `/api`

**常见配置示例：**

```json
// 本地默认配置
"live2dSocket": "ws://127.0.0.1:10086/api"

// 局域网内其他设备
"live2dSocket": "ws://192.168.1.100:10086/api"

// 使用域名
"live2dSocket": "ws://your-domain.com:10086/api"
```

**提示**：如果不需要 Live2D 功能，可以暂时不配置此项，或者设置为一个无效的地址，程序会跳过 Live2D 连接。

### 3.3 模型配置

`models` 是一个数组，可以配置多个模型，每个模型是一个对象。

#### 基本模型配置结构

```json
{
    "models": [
        {
            "name": "模型名称",
            "model": "模型标识符或路径",
            "type": "ollama|transformers|online",
            "system_prompt": "系统提示词",
            "default": true|false,
            "streaming": true|false,
            "api_key": "API密钥（仅online类型）",
            "options": {
                "temperature": 0.3,
                "top_p": 0.9,
                ...
            }
        }
    ]
}
```

#### 模型配置字段详解

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 模型名称，用于识别和切换 |
| `model` | string | 是 | 模型标识符或本地路径 |
| `type` | string | 是 | 模型类型：`ollama`、`transformers`、`online` |
| `system_prompt` | string/object | 是 | 系统提示词，可以是字符串或模块引用对象 |
| `default` | boolean | 否 | 是否为默认模型，只能有一个为 true |
| `streaming` | boolean | 否 | 是否启用流式响应，默认 true |
| `api_key` | string | 否 | API .
Error message: JSON Parse error: Unterminated string