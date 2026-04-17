# Live2oder Usage Guide

This guide covers everything you need to know to install, configure, and use Live2oder.

## Table of Contents

- [Installation & Setup](#installation--setup)
- [Live2D WebSocket Setup](#live2d-websocket-setup)
- [User Interface Guide](#user-interface-guide)
- [AI Backends Guide](#ai-backends-guide)
- [Skill System](#skill-system)
- [Conversation Memory & MCP (Model Context Protocol)](#conversation-memory--mcp-model-context-protocol)
- [Security Sandbox](#security-sandbox)
- [Building a Standalone Executable](#building-a-standalone-executable)
- [Troubleshooting](#troubleshooting)

## Installation & Setup

This guide walks you through installing and setting up Live2oder step by step.

### Prerequisites

Before you begin, make sure you have the following software installed on your system:

- **Git** - For cloning the repository. Download from [git-scm.com](https://git-scm.com/).
- **Python >=3.14,<3.15** - Live2oder follows the interpreter range declared in `pyproject.toml`. Download a compatible version from [python.org](https://www.python.org/).
- **Poetry** - Dependency manager for Python. Install following the [official guide](https://python-poetry.org/docs/#installation).
- **Live2D WebSocket service** - A separate running Live2D service that exposes a WebSocket endpoint. Live2oder connects to this to interact with your Live2D model.

#### Checking Your Prerequisites

You can verify these are installed correctly by running these commands in your terminal:

```bash
# Check Git
git --version

# Check Python
python --version
# OR on some systems:
python3 --version

# Check Poetry
poetry --version
```

If all commands output version numbers, you're good to go.

### Step 1: Clone the Repository

Clone the Live2oder source code from GitHub to your local machine:

```bash
git clone https://github.com/yourusername/live2oder.git
cd live2oder
```

Replace `yourusername` with the actual repository path if you're cloning from a different location.

### Step 2: Install Dependencies

Use Poetry to install all required Python dependencies:

```bash
poetry install
```

Poetry will automatically create a virtual environment and install all dependencies listed in `pyproject.toml`. This may take a few minutes depending on your internet connection.

> **Note**: The project configuration includes a PyPI mirror from Peking University to speed up downloads in mainland China. If you encounter issues, you can remove or modify this mirror in `pyproject.toml`.

### Step 3: First-Time Configuration

Live2oder uses a JSON configuration file to store your settings. The repository includes two templates you can copy to the runtime filename `config.json`:

- `config.example.json` - standard inline `system_prompt` example
- `config.example-prompt-modules.json` - example that references prompt modules from `prompt_modules/`

#### Copy a Configuration Template

```bash
# On macOS/Linux
cp config.example.json config.json

# On Windows (Command Prompt)
copy config.example.json config.json

# On Windows (PowerShell)
Copy-Item config.example.json config.json
```

If you want the modular prompt setup instead, replace `config.example.json` with `config.example-prompt-modules.json` in the same commands.

#### What's in the Configuration?

Open `config.json` in your favorite text editor to customize the settings:

- **`live2dSocket`** - The WebSocket URL of your running Live2D service. Default is `ws://127.0.0.1:10086/api`.
- **`models`** - An array of AI model configurations. You can configure multiple models and switch between them:
  - `name`: A friendly name for your model
  - `model`: Model identifier or file path
  - `type`: Model type - `ollama`, `transformers`, or `online`
  - `api_key`: API key (only required for `online` type models)
  - `system_prompt`: System prompt that defines the character's personality and behavior
  - `default`: Whether this should be the default model on startup
  - `streaming`: Enable streaming responses
  - `options`: Model-specific parameters like temperature, top_p, etc.
- **`memory`** - Conversation memory settings. Controls how chat history is stored and compressed.
- **`sandbox`** - Security sandbox settings for file and network operations.

> **Security Note**: `config.json` contains sensitive information like API keys. The file is already listed in `.gitignore`, so it will never be committed to the Git repository.

### Step 4: Verify Installation

After installing dependencies and configuring your settings, verify everything is set up correctly:

```bash
# Activate the poetry virtual environment
poetry shell

# Check that Python and key packages can be imported
python -c "import PySide6; import ollama; import transformers; print('All packages installed successfully!')"
```

If you don't see any error messages, your installation is good.

### Step 5: Run the Application

1. Make sure your Live2D WebSocket service is running and accessible at the URL you configured in `config.json`.

2. Run Live2oder:

```bash
# Recommended: run through Poetry so the managed environment is used
poetry run python __main__.py
```

The PySide6 UI should open and you'll see the floating input box. Live2oder will automatically connect to your Live2D model via WebSocket.



## Live2D WebSocket Setup

### Overview

Live2oder connects to an existing Live2D WebSocket service to control your Live2D model. The application itself does not include Live2D model rendering - you need to have a separate Live2D viewer or service running that exposes a WebSocket API for Live2oder to connect to.

### What the WebSocket Does

The WebSocket connection allows Live2oder to:
- Send chat messages that appear as speech bubbles above your Live2D model
- Trigger character motions and expressions based on conversation context
- Control model movement and breathing
- Send emotion data to sync the model's mood with the conversation

### Configuration

To set up the connection, add your WebSocket endpoint to `config.json`:

```json
{
  "live2dSocket": "ws://localhost:8080/ws"
}
```

Replace the URL with your actual Live2D WebSocket service endpoint.

### Expected Message Format

Live2oder sends JSON messages over the WebSocket with the following structure:

```json
{
  "type": "chat",
  "content": "Hello world!",
  "emotion": "happy"
}
```

Common message types:
- `chat` - Contains speech bubble text and emotion data
- `motion` - Requests a specific motion trigger
- `expression` - Sets a specific facial expression

### Running a Live2D WebSocket Service

#### If you already have a Live2D project

If you have an existing Live2D project or viewer running in a browser or desktop, you can expose a WebSocket API by adding a simple WebSocket server that listens for incoming connections and handles the messages Live2oder sends.

Your server needs to:
1. Accept incoming WebSocket connections on the configured port
2. Parse incoming JSON messages
3. Update your Live2D model based on the message content
4. Display speech bubbles when chat messages arrive

#### If you don't have a Live2D project

You will need a separate Live2D viewer application that supports WebSocket control. Look for or create a Live2D viewer that exposes a WebSocket API for external control. Live2oder only handles the AI conversation side - it cannot render the Live2D model on its own.

### Connection Features

Live2oder automatically handles connection issues:
- Automatic reconnection with exponential backoff
- Infinite retries until the connection succeeds
- Graceful degradation when disconnected - conversations continue locally and sync once reconnected

### Troubleshooting Connection Problems

If you cannot connect:

1. **Wrong URL** - Double-check the `live2dSocket` URL in `config.json` matches what your service is listening on. Make sure you use `ws://` not `http://` for WebSocket connections.

2. **Service not running** - Verify your Live2D WebSocket service is actually running and listening on the correct port.

3. **Firewall blocking** - Check your local firewall settings. It may be blocking incoming connections on the WebSocket port.

4. **CORS issues** - If your Live2D service runs in a browser from a different origin, you may need to configure CORS headers on your WebSocket server to allow connections from Live2oder.

 5. **SSL/HTTPS issues** - If you're using `wss://` (secure WebSocket), make sure your SSL certificates are properly configured. Self-signed certificates may cause connection failures.

---

## User Interface Guide

Live2oder uses a lightweight, non-intrusive PySide6 Qt desktop interface with three main components: **System Tray**, **Floating Input Box**, and **Speech Bubble Widget**. All components stay on top of other windows so they don't block your Live2D model but are always accessible when you need them.

### System Tray

Live2oder runs in the background and is primarily accessed through the system tray icon. This keeps it out of the way and doesn't take up taskbar space.

**Features and Usage:**
- The tray icon appears in your system tray area. **Left-click** the icon to toggle the input box visibility (show when hidden, hide when shown)
- **Right-click** the icon opens the context menu with:
  - **Show Input Box** - Displays the floating input box
  - **Hide Input Box** - Hides the floating input box
  - **Settings** - *(Placeholder for future implementation)* Open settings dialog
  - **Quit** - Exit the application completely
- On startup, the app shows a tray notification telling you to click the icon to show/hide the input box
- If system tray is not available on your system, the input box will always remain visible and you can exit via the title bar close button

**Tray Icon Behavior:**
- Clicking toggles visibility (show becomes hide, hide becomes show)
- All window positions and settings are automatically saved before the application closes

### Floating Input Box

The floating input box is your main interface for chatting with the AI. It's a borderless, draggable tool window that always stays on top.

**Default Position:**
- On first startup, it appears in the bottom-right corner of your screen
- Position is automatically saved and restored on next startup

**Moving and Resizing:**
- Drag the title bar to move the input box anywhere on the screen
- There's a resize handle in the bottom-right corner to adjust the window size
- Size and expanded/collapsed state are automatically saved

**Sending Messages:**
- Type your message in the text box (supports multi-line input)
- **Enter** - Send message (for 1-2 lines of text)
- **Shift + Enter** - Insert newline
- **Ctrl + Enter** - Force send message regardless of line count
- **Ctrl + L** - Clear input box
- **Ctrl + ↑/↓** - Navigate through message history
- **Esc** - Hide input box

**UI Features:**
- **Clear** - One-click clear all input content
- **History** - Browse previously sent messages (also available via Ctrl+↑/↓)
- **New Context** - Start a fresh conversation context
- **Plan Mode** - Enable planning mode, messages automatically get `[Plan Mode]` prefix, button turns green when enabled
- **Orchestrate Mode** - Enable orchestration mode, messages automatically get `[Orchestrate Mode]` prefix, button turns blue when enabled
- **Character Counter** - Real-time display of current input length, maximum 2000 characters
- **Send** - Click to send message, input is automatically cleared after sending

**Appearance:**
- Borderless design with rounded corners
- Title bar for dragging and collapsing/expanding
- Collapsed state only shows title bar to save screen space
- Always stays on top of other windows
- Doesn't show an icon in the taskbar

### Speech Bubble Widget

The speech bubble widget displays AI responses with beautiful gradient text and typewriter animation.

**Features:**
- Displays AI response text
- Supports typewriter effect that outputs text character by character
- Long text automatically scrolls horizontally so you can read the entire content
- Automatically fades out after a delay (base 13 seconds, adds 1 second per 10 characters, maximum 30 seconds)
- Completely transparent background, only shows gradient text with outline glow
- Fully draggable to reposition, position is automatically saved
- Always stays on top of other windows

**Default Position:**
- On first startup, appears centered at the bottom of the screen
- After dragging, position is automatically saved and restored on next startup

**Theme Support:**
- **Dark Theme** (default): Blue to purple gradient text, light text on dark semi-transparent background
- **Light Theme**: Slightly darker blue gradient, dark text on light semi-transparent background
- Text has 8-direction outline glow to ensure readability on any background

**Usage:**
- AI responses automatically appear here - no manual interaction needed
- You can drag the bubble anywhere on the screen by holding any point of the bubble
- New messages interrupt the fade-out animation, redisplay and reset the timer
- Native emoji display with correct color rendering is supported

### Theme Support

Live2oder supports both dark and light themes, with dark theme enabled by default:

- **Dark Theme**: Dark gray background, blue border, white text - good for nighttime use
- **Light Theme**: White background, light gray border, dark text - good for daytime use

**Theme Synchronization:**
- Both the floating input box and speech bubble automatically synchronize theme settings
- Theme change takes effect immediately - no application restart required
- Current theme selection is automatically saved to settings

### Window Position Memory

Live2oder remembers all your window positions:
- Floating input box position and size
- Speech bubble position
- Input box expanded/collapsed state
- Current theme selection

All settings are persisted via QSettings and automatically restored on next application startup.

### Basic Workflow

The complete interaction flow with AI and Live2D model:

1. **Input Message** - Type your message in the floating input box
2. **Send Message** - Press Enter or click the Send button
3. **AI Processing** - Input box becomes temporarily disabled and shows a loading indicator
4. **Response Display** - AI response appears in the speech bubble with typewriter effect
5. **Control Live2D** - AI automatically calls tools to control Live2D model motions and expressions
6. **Auto-hide** - Speech bubble automatically fades out after display duration completes

### Common Operations

**Show/Hide Input Box:**
- Left-click system tray icon to toggle show/hide
- Press Esc key to hide input box
- Use tray menu to explicitly select show or hide

**Move Windows:**
- Input box: Drag by the title bar
- Speech bubble: Drag anywhere on the bubble
- New position is automatically saved when you release the mouse

**Exit Application:**
- Right-click system tray icon, select "Quit"
- Or click the close button on the input box title bar

---

## AI Backends Guide

Live2oder supports three types of AI model backends. You can configure multiple models simultaneously and switch between them at any time. Choose the backend that best fits your needs based on privacy requirements, hardware capabilities, and cost.

### Overview

| Backend Type | Location | Description | Best For |
|---------------|----------|-------------|----------|
| Ollama | Local | Runs models through Ollama local service | Users who want privacy with easy setup |
| Transformers | Local | Directly loads Hugging Face models with PyTorch | Users with powerful GPUs who want full control |
| Online API | Remote | Connects to cloud-hosted models via API | Users who want high quality without powerful hardware |

---

## Common Configuration Options

All AI models share these common configuration fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Human-readable identifier for the model |
| `model` | string | Yes | Model identifier (Ollama tag, local path, or API model ID) |
| `type` | string | Yes | Must be one of: `ollama`, `transformers`, `online` |
| `api_key` | string | No | API key (only required for online backends) |
| `system_prompt` | string | Yes | System instructions that define the assistant's behavior |
| `default` | boolean | Yes | Set to `true` to use this as the default model |
| `streaming` | boolean | Yes | Enable streaming responses (currently always `true`) |
| `options` | object | No | Additional model parameters like temperature, top_p |

---

## 1. Ollama Backend

### What it is

Ollama runs large language models locally on your computer through the Ollama service. This is the easiest way to get started with local AI. Everything runs on your machine for complete privacy.

### Prerequisites

- Install [Ollama](https://ollama.com/) on your system
- Have Ollama running in the background (usually starts automatically after installation)
- Pull the model you want to use using `ollama pull <model-name>`

### Complete Configuration Example

```json
{
    "name": "ollama-agent",
    "model": "gemma3:1b",
    "type": "ollama",
    "system_prompt": "你是一个可爱的Live2D虚拟助手。\n\n## 可用工具\n\n### display_bubble_text - 显示气泡文本\n用于向用户显示消息气泡。\n- text(必需): 显示文本内容\n- choices(可选): 选项数组\n- textFrameColor(可选): 边框颜色，默认0\n- textColor(可选): 文字颜色，默认16777215\n- duration(可选): 显示时长毫秒，默认13000\n\n### file - 文件操作工具\n用于读取、写入、搜索文件和目录。\n- action(必需): 操作类型 - read/write/search_files/search_dirs\n- path(必需): 文件或目录路径\n- content(可选): 写入内容（write时需要）\n- pattern(可选): 搜索模式（search_files时使用）\n\n请用自然友好的语气回应用户。当需要读取文件时，请使用file工具的read操作。",
    "default": false,
    "streaming": true,
    "options": {
        "temperature": 0.3,
        "top_p": 0.9
    }
}
```

### How to Get Models

1. Visit [Ollama.com](https://ollama.com/library) to browse available models
2. Pull the model to your local machine:
```bash
ollama pull gemma3:1b
ollama pull llama3.2
ollama pull mistral
```
3. Use the exact model name in your configuration (e.g., `gemma3:1b`)

### Resource Requirements

- **1B-3B models**: Works on any modern CPU (4GB+ RAM)
- **7B models**: 8GB+ RAM recommended (16GB if using CPU only)
- **10B+ models**: 16GB+ RAM required, GPU strongly recommended
- Ollama automatically uses GPU acceleration when available on macOS, Windows, and Linux

---

## 2. Transformers Backend

### What it is

Transformers backend loads any Hugging Face PyTorch model directly. This gives you full control over model loading and execution, enabling the use of custom models that aren't available through Ollama. All inference happens locally on your machine.

### Prerequisites

- PyTorch installed with your hardware configuration (CPU or GPU)
- Sufficient RAM/VRAM to fit the model
- The model downloaded locally from Hugging Face

### Complete Configuration Example

```json
{
    "name": "local-transformers",
    "model": "/path/to/your/local/model",
    "type": "transformers",
    "system_prompt": "你是Live2D虚拟助手。\n\n## 核心规则\n1. 当需要显示内容给用户时，必须使用工具\n2. 禁止输出任何解释、思考或无关文本\n\n## 可用工具\n\n### display_bubble_text - 显示气泡文本\n参数：\n- text(必需): 显示文本内容\n- choices(可选): 选项数组\n- textFrameColor(可选): 边框颜色，默认0\n- textColor(可选): 文字颜色，默认16777215\n- duration(可选): 显示时长毫秒，默认13000\n\n### file - 文件操作工具\n参数：\n- action(必需): 操作类型 - read/write/search_files/search_dirs\n- path(必需): 文件或目录路径\n- content(可选): 写入内容\n- pattern(可选): 搜索模式\n\n## 规则\n- 每次只能调用一个工具\n- 系统返回结果后，可继续调用其他工具\n- 最多调用5次工具",
    "default": false,
    "streaming": true,
    "options": {
        "temperature": 0.3,
        "top_p": 0.9
    }
}
```

### How to Get Models

1. Find a model on [Hugging Face Hub](https://huggingface.co/models)
2. Clone or download the model to your local disk:
```bash
git lfs install
git clone https://huggingface.co/google/gemma-3-1b-it
```
3. Set the `model` field to the absolute or relative path of your model directory

### Resource Requirements

- **1B models**: 4GB+ VRAM (with quantization) or 8GB+ RAM (CPU)
- **7B models**: 8GB+ VRAM (4-bit quantization) or 16GB+ RAM (CPU)
- **12B+ models**: 16GB+ VRAM required
- GPU acceleration is strongly recommended. Without a GPU, response times will be very slow for models larger than 3B parameters.

---

## 3. Online API Backend

### What it is

Online API backend connects to cloud-hosted AI models through a standardized OpenAI-compatible API endpoint. This lets you use powerful state-of-the-art models without needing powerful local hardware. You pay for what you use based on tokens.

### Prerequisites

- API key from your chosen provider
- Network access to connect to the API endpoint
- An account with sufficient credits on the platform

### Complete Configuration Example

```json
{
    "name": "online-kimi",
    "model": "your-model-endpoint",
    "type": "online",
    "api_key": "your-api-key-here",
    "system_prompt": "你是花里实乃理。\n\n## 核心规则\n1. 当需要显示内容给用户时，必须使用工具\n2. 禁止输出任何解释、思考或无关文本\n\n## 可用工具\n\n### display_bubble_text - 显示气泡文本\n参数：\n- text(必需): 显示文本内容\n- choices(可选): 选项数组\n- textFrameColor(可选): 边框颜色，默认0\n- textColor(可选): 文字颜色，默认16777215\n- duration(可选): 显示时长毫秒，默认13000\n\n### file - 文件操作工具\n参数：\n- action(必需): 操作类型 - read/write/search_files/search_dirs\n- path(必需): 文件或目录路径\n- content(可选): 写入内容\n- pattern(可选): 搜索模式\n\n## 规则\n- 每次只能调用一个工具\n- 系统返回结果后，可继续调用其他工具\n- 最多调用5次工具",
    "default": true,
    "streaming": true,
    "options": {
        "api": "https://ark.cn-beijing.volces.com/api/v3",
        "max_tokens": 1024,
        "temperature": 0.3,
        "top_p": 0.9
    }
}
```

### How to Get Model and API Key

Many providers work with this backend. Common options:

**Volcengine Ark (ByteDance)**:
1. Sign up for [Volcengine](https://www.volcengine.com/)
2. Create an API key in the console
3. Find the endpoint URL and model ID for your deployed model
4. Fill in the `api` endpoint in `options`, `model` with your model ID, and `api_key` with your key

**OpenAI**:
1. Sign up at [OpenAI](https://platform.openai.com/)
2. Create an API key from your account settings
3. Configure with:
   - `model`: `gpt-4o-mini` or `gpt-4o`
   - `api_key`: `your-openai-api-key`
   - `options.api`: `https://api.openai.com/v1`

**Any OpenAI-compatible API**:
The online backend works with any service that follows the OpenAI API specification. Just set the correct `api` endpoint, `model` ID, and `api_key`.

### Resource Requirements

No local hardware requirements beyond what's needed to run the Live2oder application. All computation happens in the cloud. You only need a stable internet connection. Costs depend on your provider and usage.

---

## Selecting the Default Model

You can configure multiple AI models in the same `config.json` file. This lets you quickly switch between different backends or models without editing your configuration.

To select which model is used by default when the application starts, set `"default": true` on exactly one model entry. If multiple models have `default: true`, the first one in the list will be used.

Example with multiple models:

```json
"models": [
    {
        "name": "ollama-gemma3-1b",
        "model": "gemma3:1b",
        "type": "ollama",
        "default": false,
        ...
    },
    {
        "name": "online-gpt-4o",
        "model": "gpt-4o",
        "type": "online",
        "api_key": "sk-xxx",
        "default": true,
        ...
    }
]
```

In this example, the online GPT-4o model will be used by default at startup.

---

## Skill System

The Skill System lets you extend Live2oder with custom capabilities. Skills are modular bundles of related tools, prompts, and configuration that you can add without modifying the core application.

### What is a Skill

A Skill is a self-contained capability bundle that can:
- Provide custom **tools** the AI can use to perform actions
- Add **prompt modules** that guide AI behavior for specific tasks
- Declare **dependencies** on other skills, Python packages, or system commands
- Store its own **configuration** settings

Skills are completely optional. The core application works fine without any custom skills.

### How Skills Work

Live2oder has two types of skills:

**Built-in Skills** are included with the application and provide core functionality like file operations. They are packaged with the application and cannot be modified by users.

**External Skills** are created by users or third-party developers. They are stored as YAML files on your filesystem and can be added, modified, or removed at any time.

The skill system supports **hot-reload**, meaning you can add, remove, or modify skills while the application is running. No restart required.

### Configuration Options

To configure skills, add these options to your `config.json`:

```json
{
  "skill_directories": ["./skills", "./custom_skills"],
  "enabled_skills": ["file_ops", "web_search", "my_custom_skill"],
  "skill_config": {
    "hot_reload": {
      "enabled": true,
      "use_polling": false,
      "poll_interval": 2.0,
      "auto_enable_new_skills": true
    }
  }
}
```

**Configuration fields:**

| Field | Description | Default |
|-------|-------------|---------|
| `skill_directories` | List of directories to search for external skills | `["./skills"]` |
| `enabled_skills` | List of skill names to enable on startup | `[]` (all found skills auto-enabled) |
| `skill_config.hot_reload.enabled` | Enable automatic hot-reload detection | `true` |
| `skill_config.hot_reload.use_polling` | Use polling instead of filesystem events (helps with network drives or certain filesystems) | `false` |
| `skill_config.hot_reload.poll_interval` | How often to check for changes (in seconds) | `2.0` |
| `skill_config.hot_reload.auto_enable_new_skills` | Automatically enable newly detected skills | `true` |

### Skill Directory Structure

External skills follow a simple directory structure:

```
skills/
└── my_skill/
    ├── skill.yaml      # Skill definition (required)
    ├── prompts/        # Prompt modules (optional)
    │   └── *.md        # Individual prompt files
    ├── tools.py        # Custom tool implementations (optional)
    └── data/           # Any additional data files (optional)
        └── ...
```

- `skill.yaml` - Required. Contains all metadata, prompt definitions, tool declarations, and dependencies.
- `prompts/` - Optional directory containing separate prompt markdown files.
- `tools.py` - Optional. Contains Python code for custom tools if your skill needs them.
- `data/` - Optional. Any additional data your skill needs.

### Creating a Custom Skill - Step by Step

Follow these steps to create your own custom skill:

#### Step 1: Create the Directory Structure

Create a new directory for your skill inside one of your configured skill directories:

```bash
# Create skill directory and prompts subdirectory
mkdir -p skills/my_skill/prompts
```

#### Step 2: Create the skill.yaml Definition

Create `skills/my_skill/skill.yaml` with your skill definition:

```yaml
name: my_skill
version: 1.0.0
description: My custom skill does something useful
author: Your Name
category: utility
tags: [custom, utility]

dependencies:
  python_packages: ["requests>=2.28.0"]
  system_commands: ["git"]
  skills: ["other_skill"]

prompts:
  - name: guidelines
    description: Usage guidelines for this skill
    required: true
    file: prompts/guidelines.md

tools:
  - name: my_custom_tool
    description: Does something useful
    parameters:
      type: object
      properties:
        query:
          type: string
          description: What to search for
        max_results:
          type: integer
          description: Maximum number of results
          default: 5
      required: [query]
```

#### Step 3: Add Your Prompt Modules

Create the prompt file referenced in your `skill.yaml`:

```markdown
## My Skill Guidelines

This skill provides custom functionality for doing useful things.

### When to Use This Skill

Use this tool when the user asks questions about specific topics that require this capability.

### How to Use

1. Check that you have all the required parameters
2. Call the tool with the correct arguments
3. Present the results clearly to the user
```

#### Step 4: (Optional) Add Custom Tools

If your skill needs custom tool logic, add it to `tools.py`:

```python
import requests

def my_custom_tool(query: str, max_results: int = 5):
    """My custom tool implementation."""
    try:
        # Your custom logic here
        results = perform_search(query, max_results)
        return {
            "success": True,
            "result": results
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
```

The function name must match the tool name defined in `skill.yaml`.

#### Step 5: Enable Your Skill

If `auto_enable_new_skills` is `true`, Live2oder will automatically detect and enable your skill. If not, add it to your `config.json`:

```json
{
  "enabled_skills": ["my_skill"]
}
```

### Complete Working Example

Here's a complete example of a working skill that does web search:

**File structure:**
```
skills/web_search/
├── skill.yaml
├── prompts/
│   └── guidelines.md
└── tools.py
```

**`skill.yaml`:**
```yaml
name: web_search
version: 1.0.0
description: Search the web for information
author: Jane Doe
category: utility
tags: [search, web, utility]

dependencies:
  python_packages: ["requests>=2.28.0"]

prompts:
  - name: guidelines
    description: Web search usage guidelines
    required: true
    file: prompts/guidelines.md

tools:
  - name: web_search
    description: Search the web and get results
    parameters:
      type: object
      properties:
        query:
          type: string
          description: The search query
      required: [query]
```

**`prompts/guidelines.md`:**
```markdown
## Web Search Guidelines

Use the web_search tool when:
- The user asks about current events or recent information
- You need up-to-date data that your training data doesn't have
- The user specifically asks to search for something online

Always cite your sources after getting search results.
```

**`tools.py`:**
```python
import requests

def web_search(query: str):
    """Search the web for the given query."""
    try:
        # Example using a hypothetical search API
        response = requests.get(
            "https://api.example.com/search",
            params={"q": query},
            timeout=10
        )
        response.raise_for_status()
        results = response.json()
        return {
            "success": True,
            "results": results
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Search failed: {str(e)}"
        }
```

This skill is ready to use!

### Hot-Add, Remove, and Reload Skills

Live2oder supports three methods for managing skills without restarting:

#### Method 1: Auto-Detect (Recommended)

Just add, modify, or delete the skill directory in one of your configured skill directories. Live2oder automatically detects changes:

- **Add**: Copy the skill directory to your skills folder. Live2oder detects it, loads it, and enables it automatically. You'll see a console message: `[Skill] 检测到新SKill: my_custom_skill`
- **Modify**: Save changes to any file in the skill directory. Live2oder automatically reloads it: `[Skill] 检测到SKill变化: my_custom_skill`
- **Remove**: Delete the skill directory. Live2oder automatically unregisters it.

This works as long as `hot_reload.enabled` is `true` in your configuration.

#### Method 2: Configuration File

You can also add new skill directories by editing `config.json`:

```json
{
  "skill_directories": [
    "./skills",
    "C:/Users/YourName/Documents/Live2Oder/my_custom_skills"
  ]
}
```

This requires an application restart to take effect. All skills found in the new directory will be loaded.

#### Method 3: Programmatic

If you're developing a plugin system or integrating from code, you can add skills dynamically:

```python
from internal.skill import SkillManager, DynamicSkillLoader

# Create a dynamic loader
loader = DynamicSkillLoader(skill_manager)

# Start watching a directory for new skills
loader.watch(["C:/path/to/custom_skills"])
```

The loader will automatically detect and load new skills added to the directory.

### Best Practices

Follow these guidelines to create high-quality, maintainable skills:

#### 1. Version Your Skills

Always include a version number in `skill.yaml`:

```yaml
version: 1.0.0
```

Use semantic versioning (major.minor.patch) so users can track updates.

#### 2. Handle Errors Gracefully

Add proper error handling in your tool implementations:

```python
def my_tool(param: str):
    try:
        # Do the work
        return {"success": True, "result": "..."}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

Always return a clear error message the AI can communicate to the user.

#### 3. Document Your Skill

Provide a clear description and documentation:

```yaml
description: |
  Search for recipes online.

  Features:
  - Search by ingredient
  - Filter by cooking time
  - Get step-by-step instructions

  Use when the user asks for cooking recipes.
```

Good documentation helps users understand what your skill does and when to use it.

#### 4. Declare Dependencies

List all required Python packages and system commands:

```yaml
dependencies:
  python_packages: ["requests>=2.28.0", "beautifulsoup4>=4.11.0"]
  system_commands: ["ffmpeg"]
  skills: ["base_image_processing"]
```

This helps users install everything your skill needs before using it.

#### 5. Keep Skills Focused

Each skill should do one thing well. If your functionality is too broad, split it into multiple smaller skills. This makes it easier for users to enable only what they need.

### Troubleshooting Common Issues

#### Problem: Skill won't load

**Symptoms**: Console shows "Failed to load skill 'name-of-skill'".

**Solutions**:
1. Check that `skill.yaml` has valid YAML syntax. Use a YAML validator if you're unsure.
2. Verify the `name` field is present, not empty, and unique (no other skill has the same name).
3. Make sure all files are saved with UTF-8 encoding. Some editors use other encodings which can cause parsing errors.
4. Check that all referenced files (like prompt modules) actually exist at the correct paths.

#### Problem: Hot-reload not working

**Symptoms**: Modified files don't reload automatically.

**Solutions**:
1. Verify you're modifying files in the correct directory (the one Live2oder is watching).
2. If you're on a network filesystem or certain types of external storage, enable polling mode:
   ```json
   "skill_config": {
     "hot_reload": {
       "use_polling": true
     }
   }
   ```
3. Check the console for error messages. There may be a syntax error in your modified files that prevents loading.
4. Confirm hot-reload is enabled in your configuration: `"enabled": true` under `skill_config.hot_reload`.

#### Problem: Skill loads but tool not found

**Symptoms**: Skill loads successfully, but the AI says the tool doesn't exist.

**Solutions**:
1. Confirm the skill is enabled. Check the console logs for "enabled" messages. If auto-enable is off, you must add it to `enabled_skills` in `config.json`.
2. Check that the tool name in `skill.yaml` matches the function name in `tools.py` exactly. Names are case-sensitive.
3. Look at the tool definition syntax in `skill.yaml`. Make sure all required fields are present and correctly formatted.
4. If you have a `tools.py` file, check for Python syntax errors. The console will show error messages if the code can't be imported.

#### Problem: Dependencies won't install

**Symptoms**: Skill loads, but tools fail because of missing dependencies.

**Solutions**:
1. Install the required Python packages using pip: `pip install package-name`.
2. For system commands, verify the command is installed and available in the system PATH.
3. Check that the dependency versions match what your skill requires.

---

## Conversation Memory & MCP (Model Context Protocol)

Live2oder includes a sophisticated conversation memory system that retains your chat history across sessions, automatically compresses old content to fit within model context limits, and provides long-term storage with keyword search.

### Overview

The memory system is designed to:

- Keep track of your conversation history across multiple sessions
- Automatically compress older messages to stay within token limits
- Provide long-term storage for past conversations that you can search later
- Support both simple single-layer memory and advanced three-layer MCP context management
- Work with both JSON files and SQLite for storage

### Memory Layers Concept

Live2oder uses a layered approach to conversation memory:

**Working Memory → Recent Memory → Long-Term Storage**

1. **Working Memory** - The active conversation that gets sent to the AI model with every message. Contains the most recent messages. Limited by message count or token count to fit within the model's context window.

2. **Recent Memory** - Messages that are too old for working memory but still relatively recent. These are compressed (either summarized or truncated) to keep the most important information.

3. **Long-Term Storage** - Archives of older conversations that are compressed and stored on disk. You can search these archives when you need to reference old information.

### Basic Memory Configuration

All memory settings are under the `memory` object in `config.json`. Here are all available options for the original memory system:

| Option | Type | Description | Default |
|--------|------|-------------|---------|
| `enabled` | boolean | Enable or disable conversation memory. When disabled, the chat doesn't retain history between messages. | `true` |
| `storage_type` | string | Storage backend for active sessions: `json` or `sqlite`. JSON is simpler for small usage, SQLite handles more concurrent sessions better. | `json` |
| `data_dir` | string | Directory where memory data is stored. | `./data/memory` |
| `max_messages` | integer | Maximum number of messages to keep in working memory. | `20` |
| `max_tokens` | integer | Maximum number of tokens allowed in working memory. When exceeded, compression triggers. | `4096` |
| `compression_enabled` | boolean | Enable automatic compression when limits are reached. | `true` |
| `compression_model` | string | Which model to use for compression. `default` uses the current active model. | `default` |
| `compression_threshold_messages` | integer | Start compression when message count exceeds this number. | `15` |
| `long_term_compression_enabled` | boolean | Enable compression of old sessions that haven't been accessed recently. | `true` |
| `compression_cutoff_days` | integer | Compress sessions that haven't been accessed in this many days. | `7` |
| `compression_min_messages` | integer | Minimum number of messages a session must have before compression applies. | `10` |
| `compress_on_startup` | boolean | Run compression automatically when application starts. | `true` |
| `enable_long_term` | boolean | Enable long-term memory storage. | `true` |
| `long_term_storage` | string | Storage backend for long-term memory: `json` or `sqlite`. | `sqlite` |
| `auto_cleanup` | boolean | Automatically clean up old sessions when maximum is reached. | `true` |
| `max_sessions` | integer | Maximum number of recent sessions to keep. Older sessions are archived. | `10` |

Example basic memory configuration:

```json
"memory": {
    "enabled": true,
    "storage_type": "json",
    "data_dir": "./data/memory",
    "max_messages": 20,
    "max_tokens": 4096,
    "compression_enabled": true,
    "compression_threshold_messages": 15,
    "long_term_compression_enabled": true,
    "compression_cutoff_days": 7,
    "compression_min_messages": 10,
    "compress_on_startup": true,
    "enable_long_term": true,
    "long_term_storage": "sqlite",
    "auto_cleanup": true,
    "max_sessions": 10,
    "use_mcp": false
}
```

### MCP (Model Context Protocol) - Advanced Three-Layer Management

MCP is an advanced context management system that provides more fine-grained control over how conversation history is handled across three layers. It's designed for users who want more control over context window management and have larger conversation volumes.

#### What MCP Does

- Enforces strict separation between Working, Recent, and Long-Term layers
- Supports multiple compression strategies to suit different use cases
- Can offload storage and compression to a remote MCP service (for multi-device setups)
- Provides better context organization for long-running conversations

#### MCP Configuration Options

To enable MCP, set `"use_mcp": true` in your memory configuration:

| Option | Type | Description | Default |
|--------|------|-------------|---------|
| `use_mcp` | boolean | Enable MCP context management. When enabled, the original memory system is replaced with the three-layer MCP system. | `false` |
| `mcp_mode` | string | Operating mode: `local`, `hybrid`, or `remote`. See explanations below. | `local` |
| `compression_strategy` | string | How to compress content when moving between layers: `summary`, `sliding`, or `extraction`. | `summary` |
| `max_working_messages` | integer | Maximum number of messages in working memory (active context sent to model). | `10` |
| `max_recent_tokens` | integer | Maximum number of tokens in recent memory layer. | `2048` |
| `remote.enabled` | boolean | Enable remote MCP service. | `false` |
| `remote.endpoint` | string | Endpoint URL of the remote MCP service. | `http://localhost:8080/v1` |
| `remote.api_key` | string | API key for remote service authentication. | `null` |
| `remote.timeout` | integer | Request timeout in seconds. | `30` |
| `remote.verify_ssl` | boolean | Verify SSL certificates when connecting to remote service. | `true` |

#### MCP Modes

- **`local`** - All storage and compression happens locally on your machine. All layers are stored in your local data directory. Best for personal single-device use.

- **`hybrid`** - Working memory stays local, recent and long-term storage are handled by a remote service. Good for accessing your conversation history across multiple devices while keeping current interactions responsive.

- **`remote`** - All layers are stored on the remote MCP service. Your local device only caches the current session. Best for low-power devices or when you want full synchronization across multiple devices.

#### Compression Strategies

- **`summary`** - When moving messages to the next layer, the AI creates a concise summary of the conversation content. This preserves the most important information while dramatically reducing token count. Best for most use cases.

- **`sliding`** - Keeps the most recent N messages and discards older ones. No summarization is done. This is simpler but means older context is completely lost. Best when you only care about the most recent conversation.

- **`extraction`** - Extracts only the key facts, decisions, and important information from older messages. Creates a structured knowledge base instead of a narrative summary. Good for productivity and note-taking use cases where you need to retain factual information.

Complete MCP configuration example:

```json
"memory": {
    "enabled": true,
    "storage_type": "json",
    "data_dir": "./data/memory",
    "max_messages": 20,
    "max_tokens": 4096,
    "compression_enabled": true,
    "compression_model": "default",
    "compression_threshold_messages": 15,
    "long_term_compression_enabled": true,
    "compression_cutoff_days": 7,
    "compression_min_messages": 10,
    "compress_on_startup": true,
    "enable_long_term": true,
    "long_term_storage": "sqlite",
    "auto_cleanup": true,
    "max_sessions": 10,
    "use_mcp": true,
    "mcp_mode": "local",
    "compression_strategy": "summary",
    "max_working_messages": 10,
    "max_recent_tokens": 2048,
    "remote": {
        "enabled": false,
        "endpoint": "http://localhost:8080/v1",
        "api_key": null,
        "timeout": 30,
        "verify_ssl": true
    }
}
```

### How to Choose the Right Configuration

The best settings depend on how you use Live2oder and what kind of hardware you have.

#### For Casual Chat (Short Conversations)

If you mainly have short conversations and don't need to remember many things:

```json
{
    "enabled": true,
    "max_messages": 10,
    "max_tokens": 2048,
    "compression_enabled": false,
    "enable_long_term": false,
    "use_mcp": false
}
```

No compression needed, just keep the last 10 messages in memory.

#### For Daily Assistant Use

If you use Live2oder daily as a personal assistant and want to retain context across days:

- **Memory system**: Original (non-MCP) is fine for most users
- **Enabled**: `true`
- **max_messages**: `20-30`
- **compression_enabled**: `true`
- **compression_threshold_messages**: `15`
- **enable_long_term**: `true`
- **auto_cleanup**: `true`
- **max_sessions**: `10`

This automatically keeps your current session manageable while still archiving old conversations.

#### For Long Conversations with Context Retention

If you have long-running conversations that span many hours or days:

- **Enable MCP**: `"use_mcp": true`
- **MCP mode**: `local` (unless you need multi-device)
- **Compression strategy**: `summary`
- **max_working_messages**: `10-15`
- **max_recent_tokens**: `2048-4096`
- **enable_long_term**: `true`

This gives you the three-layer system that automatically manages context. The summary approach keeps important information without blowing out your context window.

#### For Note-Taking and Knowledge Capture

If you use Live2oder to take notes and capture information you want to search later:

- **Enable MCP**: `"use_mcp": true`
- **Compression strategy**: `extraction`
- **long_term_storage**: `sqlite` (better search capabilities than JSON)

The extraction strategy pulls out key facts that are easier to search later.

#### For Multi-Device Usage

If you use Live2oder on multiple devices and want your conversation history available everywhere:

- **Enable MCP**: `"use_mcp": true`
- **MCP mode**: `hybrid` or `remote`
- Set up a remote MCP service (see MCP documentation for setup)
- Configure the remote endpoint and API key

### Data Storage Location

By default, all memory data is stored in the `data/memory` directory relative to where you run the application:

```
data/
└── memory/
    ├── sessions/          # Active session storage (when using json)
    ├── long_term/        # Long-term archives
    ├── memory.db         # SQLite database (when using sqlite storage)
    └── ...
```

You can change the storage location by modifying the `data_dir` setting in your configuration.

Both JSON and SQLite storage keep all data on your local machine when using local MCP mode. Your conversation history never leaves your computer unless you use a remote MCP service.

---

## Building a Standalone Executable

### Overview

Live2oder can be built into a standalone executable that can be distributed and run without requiring users to install Python or any dependencies. The project uses PyInstaller for this purpose, and includes a pre-configured build script that drives the checked-in `live2oder.spec` manifest.

This is ideal if you want to:
- Distribute Live2oder to users who aren't comfortable with Python development
- Create a single self-contained package that works out of the box
- Deploy the application to multiple machines without repeating the setup process

### Prerequisites

Before building, you must already have:
1. Cloned the Live2oder repository to your build machine
2. Installed all project dependencies (follow the Installation & Setup section earlier in this guide)
3. Installed PyInstaller in the active environment (for example with `poetry add --group dev pyinstaller`)
4. Verified that the application runs correctly with `poetry run python __main__.py`
5. Configured any custom settings or skills you want to include in the build

### Build Process

Building is as simple as running a single command:

```bash
poetry run python build.py
```

The script handles everything automatically:
1. Fails fast with a clear message if PyInstaller is missing from the active environment
2. Runs PyInstaller using `live2oder.spec` as the single packaging manifest
3. Materializes the packaged artifact inventory into a versioned output directory
4. Verifies that the expected executable, asset directories, config templates, and docs are present

If you have a `skills` directory with custom skills, or prompt modules under `prompt_modules/`, the script will include them in the packaged output.

### What the Build Script Does

The build process:
- Uses **PyInstaller** to bundle Python and all dependencies into a single executable
- Creates a **one-file output** that includes everything needed to run the application
- Reads hidden imports and packaged data from `live2oder.spec`
- Excludes development-only packages to reduce output size
- Copies the verified distribution inventory (configuration templates, skills, prompt modules, documentation, etc.) to the output directory

### Build Output

After the build completes successfully, you can find the output in:

```
dist/live2oder-<version>/
```

Inside this directory you'll find:
- `live2oder.exe` (on Windows) or `live2oder` (on macOS/Linux) - the main executable
- `skills/` - packaged skill definitions distributed alongside the executable
- `prompt_modules/` - packaged prompt module files for modular prompt configs
- `config.example.json` - configuration template for end users
- `config.example-prompt-modules.json` - modular-prompt configuration template for end users
- `README.md` - project readme
- `USER_GUIDE.md` - user guide (if present)
- `配置说明.txt` - quick start configuration instructions for Chinese users

The entire directory contains everything your users need to run Live2oder. They just need to copy `config.example.json` to `config.json`, edit the configuration, and run the executable.

### Common Build Issues and Solutions

#### Out of Memory During Build

PyInstaller can use a lot of memory when bundling large applications like Live2oder. If you get out-of-memory errors:

- **Solution 1**: Close other running applications to free up RAM. You need at least 4GB of free RAM for successful builds.
- **Solution 2**: Use `--exclude-module` to exclude more unnecessary packages that aren't needed at runtime. The build script already excludes common development packages, but you can add more if needed.
- **Solution 3**: Upgrade to a 64-bit Python if you're still using 32-bit Python. 32-bit Python is limited to 4GB of address space.

#### Missing Modules

Sometimes PyInstaller misses modules that are dynamically imported at runtime. If your built executable crashes with "No module named" errors:

- Update `live2oder.spec`, because it is the single source of truth for PyInstaller hidden imports and packaged data.
- If you add new runtime assets such as prompt modules or config templates, add them to `live2oder.spec` so the build inventory and verification step pick them up automatically.
- After adding missing modules, run the build again.

#### Antivirus False Positives

Some antivirus programs incorrectly flag PyInstaller-generated executables as malware. This is a common issue with PyInstaller:

- **Solution 1**: Add an exception for your build directory in your antivirus software.
- **Solution 2**: Sign the executable with a code signing certificate (see notes below). Signed executables are much less likely to be flagged.
- **Solution 3**: Tell users downloading the executable that it's safe and the warning is a false positive.

#### PySide6 Deployment Issues

PySide6 is the Qt binding used for the UI. Sometimes PyInstaller can have issues bundling Qt dependencies:

- **Problem**: The executable starts but immediately crashes without an error message.
- **Solution 1**: Make sure you're using the same architecture (32-bit vs 64-bit) for both Python and PySide6.
- **Solution 2**: On Windows, ensure that the Visual C++ Redistributable is installed on the build machine.
- **Solution 3**: The project already includes the necessary Qt plugins through PySide6's PyInstaller hooks. If you're still having issues, you may need to manually include Qt plugins using `--add-data` in your PyInstaller command.

### Distribution

To distribute the built executable to users:

1. After the build completes, go to the output directory: `dist/live2oder-<version>/`
2. Compress the entire directory into a ZIP archive
3. Distribute the ZIP file through your preferred method (website, GitHub releases, etc.)
4. Instruct users to:
   - Extract the ZIP file to a location on their computer
   - Copy `config.example.json` to `config.json`
   - Edit `config.json` to add their Live2D WebSocket URL and AI model configuration
   - Run `live2oder.exe` (Windows) or `live2oder` (macOS/Linux) to start the application

No installation is required - users can run the executable directly from the directory.

### Note About Code Signing

Code signing is optional for personal use, but **strongly recommended** if you're distributing the executable to other people.

What code signing does:
- Prevents "Unknown publisher" warnings on Windows when users run the executable
- Reduces false positive detections from antivirus software
- Lets users know the executable hasn't been modified since you built it
- Builds trust with users downloading your software

You can purchase a code signing certificate from a trusted certificate authority. On Windows, you sign the executable after building with:

```bash
signtool sign /f your-certificate.pfx /p your-password /d Live2oder /fd SHA256 dist\live2oder-version\live2oder.exe
```

On macOS, you can sign with your Apple Developer certificate through Xcode.

For personal or internal use, you don't need to code sign. The executable will still work fine.

---

## Troubleshooting

This section covers common problems you might encounter when running Live2oder, organized by category. If you don't find your issue here, check the Getting Help section at the end of this guide.

### Connection Issues

#### 1. WebSocket won't connect to Live2D service

**Symptom**: Live2oder starts but shows "Connection failed" errors, can't connect to your Live2D service at all.

**Solution**:
1. Verify your Live2D WebSocket service is actually running on the host and accepting connections.
2. Double-check the live2dSocket URL in config.json. Make sure it matches exactly the address and port your service is listening on.
3. Ensure you used the correct protocol prefix: Use ws:// not http:// for plain WebSocket connections, or wss:// for secure connections.
4. Check that no other process is already using the port you configured.
5. Verify your firewall isn't blocking incoming connections on the WebSocket port.
6. If connecting to another machine, ensure the service isn't bound to 127.0.0.1 when you need connections from another interface.

#### 2. Live2D doesn't respond after connection is established

**Symptom**: WebSocket connects successfully, but nothing happens when you send messages. Your model doesn't move, change expressions, or show speech bubbles.

**Solution**:
1. Check that your Live2D service is correctly parsing the message format Live2oder sends. See the Live2D WebSocket Setup section earlier for the expected format.
2. Verify your service handles the message types Live2oder sends (chat, motion, expression).
3. Enable debug logging (see Debugging Tips at the end) to see what messages are actually being sent.
4. Check if your service requires authentication or additional headers that Live2oder isn't sending.
5. Try connecting from a simple WebSocket client tool to verify the service works independently of Live2oder.

#### 3. Model won't load or display

**Symptom**: Connection succeeds, but your Live2D model won't load in your viewer/service when Live2oder tries to control it.

**Solution**:
1. Verify the model files are correctly accessible to your Live2D service. Check file paths are absolute or relative correctly.
2. Check that your Live2D service supports the model format (.model3.json for Live2D Cubism 4/5).
3. Ensure all texture files are in the correct directory structure relative to the model file.
4. Check your service's console output for texture loading errors.
5. Try loading the model in your Live2D viewer independently of Live2oder to confirm the model itself works.

### AI Model Issues

#### 4. Out of memory error with Transformers backend

**Symptom**: Application crashes or displays "CUDA out of memory" or "RAM exceeded" errors when loading a Transformers model.

**Solution**:
1. Use a smaller model with fewer parameters. 1B-3B models work best on consumer hardware.
 2. Enable quantization in your model configuration options. Add "load_in_4bit" or "load_in_8bit" options to reduce memory usage:
```json
"options": {
  "load_in_4bit": true
}
```
3. Close other applications to free up RAM/VRAM before starting Live2oder.
4. If you don't have a GPU, use the Ollama backend instead - it manages memory more efficiently for CPU inference.
5. Offload layers to CPU if you have partial VRAM space: add "device_map": "auto" in your model options.

#### 5. AI model doesn't respond or generates empty output

**Symptom**: You send a message, but nothing appears in the speech bubble and nothing happens.

**Solution**:
1. Check your system prompt follows the correct format. Make sure it includes tool usage instructions if you want your agent to display output with the display_bubble_text tool.
2. Verify your API key is correct and hasn't expired for online models.
3. Check that you have sufficient credits/quota with your online provider.
4. Enable debug logging to see what the actual response from the model is (see Debugging Tips below).
5. For Ollama, verify the model was pulled completely with ollama pull <model-name> and ollama list shows it exists.
6. Check that your system prompt doesn't exceed the model's context window size.

### UI Issues

#### 6. Floating input box doesn't appear

**Symptom**: Application starts, you can see it in the system tray, but the floating input box doesn't show up on screen.

**Solution**:
1. Click the "Show Input" option in the system tray menu - it may have been hidden previously.
2. Check if it's on a different monitor if you use multiple displays. Try moving your mouse around the edges of your screens to find it.
3. Restart the application - the position is saved in local storage, and sometimes ends up off-screen after display resolution changes.
4. On Linux, check that your window manager isn't hiding it due to its always-on-top setting.
5. Verify PySide6 installed correctly by running python -c "import PySide6.QtWidgets; print(PySide6.__version__)" - if this errors, reinstall PySide6.

#### 7. Speech bubble is not showing

**Symptom**: AI responds, but no speech bubble appears above your Live2D model.

**Solution**:
1. Verify your Live2D service handles the chat message from Live2oder. The speech bubble rendering is handled by your Live2D service, not Live2oder.
2. Check that the AI actually called the display_bubble_text tool. Enable debug logging to see the tool call was sent correctly.
 3. Verify the text color isn't the same as your background. The default text color is white, change the `textColor` parameter if needed.
4. Check that your Live2D service doesn't have speech bubble disabled in its configuration.
5. Try specifying a positive duration - most services require a positive duration (default is 13000ms).

### Skill Issues

#### 8. Skill won't load or hot-reload doesn't work

**Symptom**: You added a new skill or modified an existing skill, but it doesn't show up or the changes aren't applied.

**Solution**:
1. Check that the skill file is in the correct directory structure. Skills must follow the naming convention and entry point format expected by the skill loader.
2. Verify there are no syntax errors in your skill code. Run python -m py_compile path/to/skill.py to check for syntax errors.
3. Trigger hot-reload from the system tray menu instead of just saving changes.
4. Check that the skill exports all required entry points (skill registration, tool registrations) are correctly defined.
5. Restart Live2oder completely to load the skill from scratch - sometimes hot-reload fails if there are dependency errors when importing.
6. Verify all dependencies the skill needs are installed in your environment.

### Security/Sandbox Issues

#### 9. AI tries to access files and gets access denied

**Symptom**: The AI wants to read or write a file, but gets "Access denied" error from the sandbox.

**Solution**:
1. Check the sandbox configuration in config.json. The sandbox blocks access to sensitive directories by default for security.
 2. Add the directory the AI needs to access to the `allowedPaths` list in the sandbox configuration:
```json
"sandbox": {
  "allowedPaths": ["/home/user/projects", "D:/Documents"]
}
```
3. Verify the file path doesn't contain sensitive system directories that are blocked by default (like /etc, C:\Windows, ~). The sandbox always blocks these for safety.
4. Check that the file has correct file system permissions - the user running Live2oder has read/write access to the directory.
5. If you fully trust the AI model, you can disable the sandbox entirely (not recommended for untrusted models).

### Build & Startup Issues

#### 10. Build fails with PyInstaller

**Symptom**: Running python build.py fails before completing the build.

**Solution**:
1. Verify PyInstaller is up to date. Update with pip install -U pyinstaller.
2. Check that you're building from the project root directory. PyInstaller needs the correct working directory to find all files.
3. Verify all dependencies are installed in your active environment. Run `poetry install` before building.
4. On Windows, check that your antivirus isn't interfering with PyInstaller - it sometimes flags PyInstaller as malicious. Add an exception for the build directory.
5. Check the build log for missing module errors - some PySide6 components may need to be explicitly included in the PyInstaller spec file.
 6. If you get "maximum recursion depth exceeded", increase the recursion limit at the top of `build.py`.

#### 11. Application won't start after building

**Symptom**: Build completes, but double-clicking the executable doesn't open anything.

**Solution**:
1. Try running the executable from the command line to see the error output. Double-clicking won't show console errors on Windows.
2. Verify config.json exists in the same directory as the executable. Copy it from the project root if it's missing.
3. Check that your antivirus didn't quarantine the executable. PyInstaller-generated executables are sometimes falsely flagged.
4. Verify all data files (styles, prompts) are included in the build output directory. The build script copies them automatically, but if it fails, copy them manually.
5. Check that you're not running the executable from a path with non-ASCII characters (Chinese, Japanese, Korean characters in username folder). Move it to a simple ASCII path.

## Debugging Tips

### Enable Debug Logging

To get more detailed output about what's happening:

 1. Create or edit config.json and add the debug option:
```json
"debug": true
```

2. Run the application from the command line to see debug output in the console.

### Where to Find Logs

- When running from source, all logs go to the console output.
- For built applications, check logs/app.log in the application directory.
- Debug logging includes detailed information about:
  - WebSocket connection attempts and message content
  - AI model requests and responses
  - Tool call execution
  - Memory compression events
  - Skill loading errors

## Getting Help

If you can't find your problem here, you can open an issue on GitHub. When opening an issue, please include:

1. Your operating system and version (Windows 11, macOS 14, Ubuntu 22.04, etc.)
2. Your Python version and how you installed it
3. Your config.json content (remove API keys and secrets first!)
4. The full error traceback from the console or log
5. What you've already tried to fix the problem
6. Steps to reproduce the issue

Open new issues at: https://github.com/yourusername/live2oder/issues
