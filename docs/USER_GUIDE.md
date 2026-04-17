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
- **Python**: `>=3.14,<3.15`（与 `pyproject.toml` 保持一致）

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
- Python `>=3.14,<3.15`
- Poetry（包管理器）

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
# 复制标准配置模板
cp config.example.json config.json

# 或者使用 PowerShell (Windows)
Copy-Item config.example.json config.json
```

如果你想使用 `prompt_modules/` 里的模块化提示词，也可以把 `config.example-prompt-modules.json` 复制为同一个运行时文件名 `config.json`。

#### 步骤 3: 安装 Python 依赖

**使用 Poetry（推荐，也是文档中的标准路径）：**

```bash
# 安装 Poetry
pip install poetry

# 安装依赖
poetry install

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
poetry run python __main__.py
```

运行时会继续从项目根目录下的 `config.json` 读取配置。

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
| `models` | array | 否 | `[]` | 模型配置数组；要真正发起对话，至少需要配置一个模型 |
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
| `api_key` | string | 否 | API 密钥（仅 online 类型需要）|
| `options` | object | 否 | 模型额外参数，如 `temperature`、`top_p` 等 |

### 3.4 记忆系统配置

记忆系统是 Live2oder 的重要功能，它会自动保存对话历史并进行智能压缩管理。配置位于 `memory` 对象下：

#### 基础配置选项

| 选项 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | boolean | `true` | 是否启用记忆功能 |
| `storage_type` | string | `json` | 存储类型：`json` 或 `sqlite` |
| `data_dir` | string | `./data/memory` | 记忆数据存储目录 |
| `max_messages` | integer | `20` | 工作内存中保留的最大消息数 |
| `max_tokens` | integer | `4096` | 工作内存中允许的最大 token 数，超过则触发压缩 |
| `compression_enabled` | boolean | `true` | 是否启用自动压缩 |
| `enable_long_term` | boolean | `true` | 是否启用长期记忆 |
| `use_mcp` | boolean | `false` | 是否启用 MCP（Model Context Protocol）三层上下文管理 |

#### MCP 高级配置

当启用 MCP 后，可以使用更精细的三层上下文管理：

| 选项 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `mcp_mode` | string | `local` | 运行模式：`local`、`hybrid`、`remote` |
| `compression_strategy` | string | `summary` | 压缩策略：`summary`（摘要）、`sliding`（滑动窗口）、`extraction`（关键信息提取） |
| `max_working_messages` | integer | `10` | 工作内存最大消息数 |
| `max_recent_tokens` | integer | `2048` | 近期记忆层最大 token 数 |

完整配置示例请参考项目根目录的 `config.example.json`。

---

## 4. 功能使用

### 4.1 启动与退出

**启动：**
```bash
poetry run python __main__.py
```

**退出：**
- 右键点击系统托盘图标，选择"退出"
- 或者点击悬浮输入框标题栏上的关闭按钮

### 4.2 系统托盘

程序启动后会最小化到系统托盘：

- **左键单击**托盘图标：切换悬浮输入框的显示/隐藏
- **右键单击**托盘图标：打开菜单，可选择显示/隐藏输入框或退出程序

### 4.3 AI 助手交互

在悬浮输入框中输入文字，按回车发送。支持以下快捷键：

- **Enter**：发送消息
- **Shift + Enter**：插入换行
- **Ctrl + Enter**：强制发送
- **Ctrl + L**：清空输入框
- **Ctrl + ↑/↓**：浏览历史消息
- **Esc**：隐藏输入框

### 4.4 Live2D 控制功能

AI 助手可以通过工具调用直接控制 Live2D 模型：

- **切换表情**：直接告诉 AI"换成开心的表情"，AI 会自动调用工具
- **触发动作**：说"做一个打招呼的动作"，AI 会触发对应动作
- **显示气泡**：AI 回复会自动显示在气泡中
- **切换模型**：可以在配置多个模型后通过指令切换

---

## 5. 提示词模块

### 5.1 模块化提示词系统

Live2oder 支持模块化提示词，你可以将系统提示词拆分为多个独立模块，按需组合，便于复用和维护。

在配置中使用模块化提示词的格式：

```json
"system_prompt": {
    "modules": ["core/base_rules", "personality/cute", "capabilities/file_ops"]
}
```

### 5.2 预定义模块

项目已经预定义了一些常用模块：

- **core/**：核心规则
  - `base_rules`：基础行为规则
  - `live2d_rules`：Live2D 操作规则
  - `tool_calling`：工具调用规范
- **capabilities/**：能力模块
  - `file_ops`：文件操作能力
  - `web_search`：网络搜索能力
  - `live2d_ctrl`：Live2D 控制能力
  - `office`：Office 文档处理能力
- **personality/**：个性模块
  - `friendly`：友好助手
  - `cute`：可爱少女风格
- **languages/**：语言模块
  - `chinese`：中文输出
  - `english`：英文输出
- **scenarios/**：场景模块
  - `daily_chat`：日常聊天
  - `assistant`：助手场景

### 5.3 自定义提示词

你可以在 `prompt_modules/` 目录下创建自己的模块文件，文件扩展名为 `.md`。每个文件就是一个独立的提示词模块，程序会在启动时自动加载所有模块。

---

## 6. 常见问题与故障排除

### 6.1 配置问题

**Q: 启动后提示找不到 `config.json`**  
A: 需要先复制配置模板：`cp config.example.json config.json`，然后编辑 `config.json` 填入你的配置。

**Q: JSON 解析错误**  
A: 检查 `config.json` 是否格式正确，特别注意逗号和括号的匹配，可以使用 JSON 校验工具检查。

### 6.2 连接问题

**Q: 无法连接到 Live2D WebSocket**  
A: 
1. 确认 Live2D WebSocket 服务已经启动
2. 检查 `live2dSocket` 地址是否正确，注意协议是 `ws://` 不是 `http://`
3. 检查防火墙是否阻止了连接

**Q: 连接断开后不会自动重连**  
A: Live2oder 默认会自动重连，如果一直连接失败，检查 Live2D 服务是否正常运行。

### 6.3 模型运行问题

**Q: Ollama 模型调用失败**  
A: 确认 Ollama 服务已经启动，并且模型已经拉取到本地。可以先用 `ollama run <model-name>` 测试模型是否正常。

**Q: Transformers 模型内存不足**  
A: 尝试启用 4bit 或 8bit 量化，在模型配置中添加 `"load_in_4bit": true`。

### 6.4 UI 显示问题

**Q: 悬浮输入框看不到了**  
A: 左键点击系统托盘图标可以重新显示，或者右键通过菜单显示。

**Q: 窗口位置记住了但我想重置**  
A: 删除程序保存的位置信息后重启，位置信息存在 QSettings 中。

### 6.5 性能优化建议

- **CPU 运行较慢**：使用较小的模型（1B-3B 参数）
- **内存占用太高**：开启压缩，减少 `max_messages` 配置
- **响应延迟大**：使用 4bit 量化加载 Transformers 模型，或者改用 Ollama 后端

---

*本文档最后更新于 2026年4月*
Error message: JSON Parse error: Unterminated string
