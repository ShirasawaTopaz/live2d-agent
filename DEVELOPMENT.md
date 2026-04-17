# Development Guide

This guide contains everything you need to know to set up your development environment and understand the Live2oder codebase.

## Table of Contents

- [Environment Setup](#environment-setup)
- [Directory Structure Overview](#directory-structure-overview)
- [Testing Guide](#testing-guide)
- [Component Deep Dive](#component-deep-dive)
  - [Agent Layer](#agent-layer-internalagentagentpy)
  - [Model Support](#model-support-internalagentagent_support)
  - [Tool System](#tool-system-internalagenttool)
  - [Memory System](#memory-system-internalmemory)
  - [Skill System](#skill-system-internalskill)
  - [MCP Layer](#mcp-layer-internalmcp)
  - [UI Layer](#ui-layer-internalui)
  - [WebSocket Layer](#websocket-layer-internalwebsocket)
  - [Configuration](#configuration-internalconfigconfigpy)
  - [Prompt Manager](#prompt-manager-internalprompt_manager)
- [Component Interactions and Dependencies](#component-interactions-and-dependencies)
- [Extension Points for Contributors](#extension-points-for-contributors)

## Environment Setup

This section covers how to set up your development environment for Live2oder.

### Prerequisites

Before you begin, ensure you have the following installed:

- **Git** - For version control
- **Python >=3.14,<3.15** - Match the interpreter range declared in `pyproject.toml`
- **Poetry** - For dependency management
- **IDE** - Visual Studio Code is recommended, but any Python IDE works

### Getting the Code

1. Fork the repository on GitHub
2. Clone your forked repository locally:

```bash
git clone https://github.com/your-username/live2oder.git
cd live2oder
```

### Installing Dependencies

Use Poetry to install all project dependencies:

```bash
poetry install
```

The project uses a custom PyPI mirror (Peking University) configured in `pyproject.toml` for faster downloads in mainland China.

### Pre-commit Hooks

Pre-commit hooks are configured for this project. Install them locally with:

```bash
poetry run pre-commit install
```

### IDE Configuration Recommendations

#### Visual Studio Code

We recommend the following setup:

1. Install the **Python extension for VS Code** (provided by Microsoft)
2. Enable **Pylance** for type checking and IntelliSense
3. Enable **mypy** for static type checking in settings
4. Install the **Ruff** extension for linting

Your VS Code `settings.json` should include something like this:

```json
{
  "python.linting.ruffEnabled": true,
  "python.linting.enabled": true,
  "python.analysis.typeCheckingMode": "basic"
}
```

### Verify Your Setup

After completing the steps above, verify your development setup by running the application in development mode:

1. Copy one of the configuration templates to the runtime filename `config.json`:

```bash
cp config.example.json config.json
```

   Or copy `config.example-prompt-modules.json` to `config.json` if you want prompt module references instead of an inline `system_prompt`.

2. Edit `config.json` with your AI model settings and Live2D WebSocket endpoint

3. Run the application:

```bash
poetry run python __main__.py
```

If the application starts without errors, your development environment is ready.

## Directory Structure Overview

Live2oder follows a modular architecture organized into these top-level directories:

```
live2oder/
├── .claude/              # Claude AI settings
├── .pytest_cache/        # pytest cache directory
├── .ruff_cache/          # Ruff linter cache
├── .sisyphus/            # Project planning and notes
├── .trae/                # Trae IDE documents
├── .venv/                # Python virtual environment (not committed)
├── build/                # Build artifacts from PyInstaller
├── data/                 # Data files and persistent storage
├── dist/                 # PyInstaller distribution output
├── docs/                 # Documentation files
├── examples/             # Example configurations and usage examples
├── internal/             # Core application source code
│   ├── agent/            # Agent layer: main agent, model implementations, tool system
│   │   ├── agent_support/  # Model backends (Ollama, Transformers, Online API)
│   │   └── tool/          # Tool implementations for agent capabilities
│   ├── config/           # Configuration loading and validation
│   ├── mcp/              # Model Context Protocol implementation (new feature)
│   ├── memory/           # Multi-layer conversation memory management system
│   ├── prompt_manager/   # Modular prompt loading and composition
│   ├── skill/            # Dynamic skill system for hot-loading
│   ├── ui/               # PySide6 UI components (floating input, speech bubbles)
│   └── websocket/        # Live2D WebSocket client with auto-reconnect
├── prompt_modules/       # Modular prompt components (loaded at runtime)
├── resources/            # Static resources (icons, images)
├── skills/               # User-added skills (dynamically loaded)
└── tests/                # Test files
```

### Key Files

- `__main__.py` - Main application entry point, creates `Live2oderApp` and runs the application
- `pyproject.toml` - Poetry project configuration, dependencies, and mirror configuration
- `poetry.lock` - Poetry dependency lock file (pinned versions)
- `config.example.json` - Main configuration template
- `config.example-prompt-modules.json` - Prompt module configuration template
- `build.py` - PyInstaller build script for creating distributable executables
- `live2oder.spec` - PyInstaller specification file
- `CLAUDE.md` - Development guidance for AI coding assistants
- `README.md` - Project overview and quick start guide

## Testing Guide

### Current State

Live2oder already has a growing pytest-based test suite plus scoped local quality gates. This section documents the current commands contributors should run and the conventions to follow when adding coverage.

### Current Testing and Quality Commands

The main local commands are:

 - `poetry run pytest --collect-only`
 - `poetry run pytest tests -q`
 - `poetry run ruff check __main__.py build.py internal/ internal/agent internal/config internal/memory internal/mcp internal/prompt_manager internal/skill internal/ui internal/websocket tests`
 - `poetry run mypy __main__.py build.py internal/agent internal/config internal/memory internal/mcp internal/prompt_manager internal/websocket`
 - `poetry run pre-commit run --all-files`

### How to Run Tests

Run tests with commands like:

```bash
# Run all tests with verbose output
poetry run pytest -v

# Run a specific test file
poetry run pytest tests/test_config.py -v

```

### Code Quality Checks

Use these tools locally as part of the current contributor workflow:

#### Ruff Linting

Ruff is a fast Python linter that enforces code style and catches common errors.

```bash
# Run the scoped lint check used by the repository quality gates
poetry run ruff check __main__.py build.py internal/ internal/agent internal/config internal/memory internal/mcp internal/prompt_manager internal/skill internal/ui internal/websocket tests

# Fix fixable issues automatically in the same scoped paths
poetry run ruff check --fix __main__.py build.py internal/ internal/agent internal/config internal/memory internal/mcp internal/prompt_manager internal/skill internal/ui internal/websocket tests
```

#### mypy Type Checking

mypy provides static type checking to catch type-related errors before runtime.

```bash
# Run the scoped type check used by the repository quality gates
poetry run mypy __main__.py build.py internal/agent internal/config internal/memory internal/mcp internal/prompt_manager internal/websocket
```

### Writing Tests

When adding new code to Live2oder, please follow these guidelines:

1. **Add tests for new features** - Every new feature should come with appropriate test coverage
2. **Follow existing patterns** - Match the test file structure and naming conventions used in existing tests
3. **Test edge cases** - Don't just test the happy path; include tests for error conditions and edge cases
4. **Keep tests fast** - Unit tests should run quickly; avoid heavy network or I/O operations in unit tests
5. **Mock external dependencies** - Mock out AI model APIs and WebSocket connections to keep tests self-contained
6. **One assertion per test** - Focus each test on testing one specific behavior for easier debugging

Test files should be placed in the `tests/` directory with the naming pattern `test_<module_name>.py`.

### CI/CD with GitHub Actions

The repository includes a GitHub Actions workflow that mirrors the scoped local gates. The CI checks:

- All tests pass with pytest
- Ruff linting passes with no errors
- mypy type checking passes with no errors

The CI configuration lives at `.github/workflows/ci.yml`.

### Pre-commit Hooks

Pre-commit hooks are configured for the repository. Set them up locally with:

```bash
# Install pre-commit hooks
poetry run pre-commit install

# Run pre-commit hooks manually on all files
poetry run pre-commit run --all-files
```

The pre-commit configuration includes:

- Ruff linting
- Trailing whitespace removal
- End-of-file fixing
- mypy type checking (optional)

For more information about contributing to Live2oder, see the roadmap in `TODO.md`.

## Component Deep Dive

### Introduction

Live2oder is organized into a clean layered architecture with clear separation of concerns between components. Each major component has a single responsibility and communicates through well-defined interfaces.

The architecture layers from highest to lowest are:

1. **UI Layer** - User interface components (PySide6)
2. **Agent Layer** - Core agent orchestration, chat processing, and tool calling
3. **Skill System** - Dynamic skill loading and lifecycle management
4. **Memory/MCP Layer** - Conversation context management and long-term storage
5. **Infrastructure Layer** - Configuration, WebSocket connection, prompt management

This modular design enables easy testing, extension, and maintenance. You can add new capabilities without changing core code by implementing new tools or skills.

---

### Agent Layer (`internal/agent/agent.py`)

The **Agent** class is the main orchestrator that coordinates chat processing, memory, and tool execution. It's the heart of the application.

**Key Responsibilities:**
- Maintains the model instance and tool registry
- Processes chat messages from user input
- Manages the multi-turn tool calling loop
- Handles both streaming and non-streaming responses
- Integrates with memory system for context management
- Coordinates speech bubble display to Live2D through WebSocket
- Manages automatic context compression in the background

**Chat Processing Flow:**

1. **Message Entry**: User sends message through `FloatingInputBox` → `Agent.chat()`
2. **Memory Integration**: If memory is enabled, message is added to memory context
3. **Flow Decision**:
   - If no tools defined or model doesn't support tools **and** streaming enabled → go to streaming mode
   - Otherwise → non-streaming mode with potential tool calling
4. **Streaming Mode**:
   - Async generator yields content chunks from model
   - Chunks are sent incrementally to either Qt `BubbleWidget` or Live2D WebSocket
   - Content accumulates and the bubble updates in place
   - After completion, final content is saved to memory
5. **Non-Streaming with Tool Calling**:
   - Get complete response from model
   - Parse tool calls from response (OpenAI format or custom `<tool_call>` tags)
   - Execute each tool with proper error handling
   - Add tool results to conversation history
   - Repeat up to `max_tool_calls` (default 5) until model stops calling tools
   - Send final text response as speech bubble
6. **Memory Persistence**: Save current session to storage and check if compression is needed
7. **Background Compression**: If context threshold reached, compress older messages in background

**Tool Calling Orchestration:**
- Agent gets tool definitions from `ToolRegistry` in OpenAI format
- Supports parallel tool calling (multiple tools in one response)
- Falls back to parsing `<tool_call>` tags from content if model doesn't support native tool calling
- Passes `ws` (WebSocket) and `bubble_widget` to tools that need them
- All errors during tool execution are caught and returned to the model as error messages

The Agent class holds references to all major subsystems but delegates actual work to specialized components.

Additional components in the agent layer:
- **Planning subsystem** (`internal/agent/planning/`) - Task planning with persistent storage (JSON/SQLite), enables the agent to break down complex tasks into executable steps
- **Sandbox security system** (`internal/agent/sandbox/`) - Comprehensive security middleware for file and network operations

---

### Model Support (`internal/agent/agent_support/`)

All model implementations implement the **ModelTrait** abstract base class, which defines the minimal interface required by the Agent.

**ModelTrait** (`trait.py`):
- `config: AIModelConfig` - Model configuration holder
- `history: list[dict]` - Conversation history
- `_tools_supported: bool` - Whether the model natively supports tool calling
- `_prompt_manager: Optional[PromptManager]` - Lazy-loaded prompt manager
- `chat(message, tools) -> dict` - Synchronous chat completion
- `stream_chat(message, tools) -> AsyncIterator[dict]` - Streaming response

**Available Backends:**

1. **Ollama** (`ollama.py`) - Connects to local Ollama service running on localhost. Supports both streaming and non-streaming, native tool calling. Works with any model available in your local Ollama.

2. **Transformers** (`transformers.py`) - Loads models locally through Hugging Face Transformers. Supports GPU acceleration if available. Works with causal language models. Can be configured for different quantization levels to fit in memory.

3. **Online API** (`online.py`) - Connects to remote API endpoints compatible with OpenAI format (including火山引擎方舟, OpenAI itself, and others). Handles API key authentication, request formatting, and response parsing.

**Prompt Composition:**
All backends integrate with the `PromptManager` to resolve system prompts. System prompts can be either a raw string or a composition of multiple modular prompt modules loaded from the `prompt_modules/` directory.

---

### Tool System (`internal/agent/tool/`)

The tool system enables the AI agent to interact with the external world and extend its capabilities. Tools follow a simple abstract base class pattern.

**Tool Base Class** (`base.py`):
- `name()` - Unique tool identifier used by AI to call the tool
- `description()` - Human-readable description sent to the model
- `parameters()` - JSON Schema definition of tool parameters
- `execute(**kwargs)` - Execute the tool and return result

**Tool Registry** (`register.py`):
- Maintains a map of tool names to tool instances
- Provides tool definitions in OpenAI format to the model
- Supports dynamic runtime registration and unregistration
- Handles loading persisted dynamic tools from storage on startup

**Current Tools Included:**

**Live2D Control Tools** (`tool/live2d/`):
- `DisplayBubbleTextTool` - Display text in a speech bubble
- `TriggerMotionTool` - Trigger a model motion/animation
- `SetExpression` - Set a specific facial expression
- `NextExpression` - Cycle to next expression
- `ClearExpression` - Clear current expression
- `SetBackground` - Change background image/color
- `SetModel` - Switch to a different Live2D model
- `PlaySoundTool` - Play audio effects

**File System Tools:**
- `FileTool` - Read, write, and manipulate files with sandbox security restrictions

**Office Tools:**
- `OfficeTool` - Read and process PDF, Word, and other office documents

**Web Search:**
- `WebSearchTool` - Search the web for current information

**Meta Tools (Dynamic Tool Management)** (`tool/meta/`):
- `GenerateToolTool` - AI generates new tool code from natural language description
- `ListToolsTool` - List all currently registered tools
- `DeleteToolTool` - Delete a dynamically created tool
- `RollbackTool` - Rollback to previous tool version after deletion

**Dynamic Tool System** (`tool/dynamic/`):
The system supports on-the-fly tool generation. The AI can create new tools using the meta-tools, which are then persisted to storage and automatically loaded on next startup. All generated tools go through security validation before execution to prevent unsafe operations. Features:
- Security validation for dangerous operations
- Version control for rollback
- Audit logging
- Code templates for consistent structure

**Security:**
File operations are protected by a **SandboxMiddleware** (`internal/agent/sandbox/`) that restricts file access to allowed directories and blocks dangerous operations. The sandbox also provides network access control.

---

### Memory System (`internal/memory/`)

The memory system manages conversation history across multiple sessions with automatic compression to keep context within model token limits. It supports both legacy mode and integration with the newer MCP layer.

**Main Components:**

- **MemoryManager** (`_manager.py`) - Main coordinator that ties all sub-components together
  - Initializes storage backend based on configuration
  - Routes operations to appropriate components
  - Supports MCP (Model Context Protocol) integration when enabled
  - Provides unified API for Agent to use

- **SessionManager** (`_session.py`) - Manages multiple conversation sessions
  - Each session is an independent conversation
  - Supports switching between sessions
  - Handles session creation and deletion
  - Automatically persists sessions to storage

- **ContextManager** (`_context.py`) - Manages context window limits
  - Tracks total token count
  - Triggers compression when thresholds are hit
  - Enforces maximum message limits

- **Summarizer** (`_summary.py`) - Generates summaries for compression
  - Uses the configured AI model to create conversation summaries
  - Compresses multiple turns into a single summary message
  - Reduces token usage while preserving conversation context

- **LongTermMemory** (`_long_term.py`) - Keyword-based search across past conversations
  - Indexes previous messages for keyword search
  - Can inject relevant context based on current query
  - Enables the AI to recall relevant information from the past

- **ArchiveCompressor** (`_archive.py`) - Compresses inactive sessions in bulk
  - Runs on startup to clean up old sessions
  - Compresses sessions that haven't been active for a while
  - Saves storage space and keeps context management efficient

**Storage Backends:**
- **JSONStorage** - Each session stored as a JSON file (good for version control, simple)
- **SQLiteStorage** - All sessions in a single SQLite database (better for many sessions)

**Memory Configuration:**
- `enabled` - Toggle memory system on/off
- `storage_type` - json or sqlite
- `max_messages` - Maximum messages in context
- `max_tokens` - Maximum tokens allowed
- `compression_threshold_messages` - Trigger compression when this many messages reached
- `compression_enabled` - Whether automatic compression is enabled
- `enable_long_term` - Enable keyword search long-term memory
- `long_term_compression_enabled` - Enable archive compression of inactive sessions
- `compress_on_startup` - Automatically compress on application startup
- `use_mcp` - Use MCP (Model Context Protocol) instead of legacy memory

When MCP is enabled, MemoryManager delegates all context management to the MCPContextManager.

---

### Skill System (`internal/skill/`)

The skill system provides a way to package related tools and prompts as reusable modules that can be dynamically loaded at runtime. This is the recommended way to extend Live2oder with new functionality.

**Skill Base Class** (`base.py`):
- `SkillMetadata` - Dataclass for skill metadata (name, version, description, author, category, tags)
- `SkillPrompt` - Prompt module provided by the skill
- `SkillTool` - Tool definition provided by the skill
- `_load_metadata()` - Return skill metadata
- `_load()` - Load prompts and tools into the skill instance
- `initialize()` - Initialize resources when skill is enabled (async)
- `shutdown()` - Clean up resources when skill is disabled (async)
- `get_tool_instances()` - Get concrete Tool instances to register with Agent

**SkillManager** (`manager.py`) - Lifecycle manager:
- Discovers skills in multiple directories (user skills, embedded skills, builtin skills)
- Loads skill definitions from `skill.yaml` in each skill directory
- Initializes skill instances and registers tools/prompts when enabled
- Handles shutdown and unregistration when disabled
- Supports hot-reloading of new skills added to user directory without recompiling

**Skill Registry** (`registry.py`) - Stores loaded skill instances for lookup:
- Supports registration and lookup by name
- Keeps metadata for skill discovery

**Dynamic Loader** (`dynamic_loader.py`) - Loads external skill modules dynamically from filesystem:
- Handles importing Python code from skill directories
- Supports hot-reloading when skills are added or modified

**Built-in Skills:**
- `file_ops` - File operation tools
- `web_search` - Web search capability
- `live2d_ctrl` - Live2D model control tools
- `office` - Office document processing

**Loading Flow:**
1. SkillManager scans configured skill directories on startup
2. Looks for `skill.yaml` in each directory
3. Creates skill instance (builtin or external)
4. Registers in SkillRegistry
5. When enabled, initializes and registers tools with Agent's ToolRegistry

Users can add new skills by creating a new directory with `skill.yaml` and restarting the application. No code changes to core are required.

---

### MCP Layer (`internal/mcp/`)

**Model Context Protocol** is a newer three-layer context management system that provides more sophisticated context handling than the legacy memory system. It's designed for scalability with long conversations.

**Three-Layer Architecture:**

1. **Working Memory** - Current active conversation (in-memory)
   - Holds the most recent N messages (configurable)
   - Direct access for the model, no lookup needed
   - Automatically compresses when threshold is hit

2. **Recent Context** - Recent conversation chunks still uncompressed (in-memory)
   - Keeps last N compressed chunks
   - Older chunks are moved to long-term storage
   - Provides fast access to recent context

3. **Long-Term Storage** - All compressed chunks persisted to storage
   - Full-text search support
   - Only loaded when relevant to current query
   - Minimal memory footprint

**Key Components:**

**protocol.py** - Defines all core data structures:
- `MCPMessage` - Single message with role, content, token count, metadata
- `MCPContextChunk` - Compressed chunk of multiple messages with summary
- `MCPGetContextRequest` - Request for assembled context
- `MCPGetContextResponse` - Response with assembled messages
- `MCPParticipant` - Role enum (SYSTEM, USER, ASSISTANT, TOOL)
- `MCPMode` - LOCAL, HYBRID, REMOTE operation modes

**config.py** - Configuration options:
- `enabled` - Whether MCP is enabled
- `mode` - Local (all storage local), Hybrid (some remote), Remote (all remote)
- `max_working_messages` - Maximum messages in working memory
- `max_recent_tokens` - Maximum tokens in recent context
- `max_total_tokens` - Maximum total tokens for context window
- `compression_threshold_messages` - Compress when working memory exceeds this
- `compression_strategy` - summary, sliding_window, or extraction
- `enable_long_term` - Enable long-term storage
- `storage_type` - json or sqlite
- `remote` - Configuration for remote MCP service

**manager.py** - `MCPContextManager` - Core coordinator:
- `add_message()` - Add message to working memory
- `get_context()` - Assemble context from all three layers
- `switch_scope()` - Switch to different conversation scope (multi-tenant)
- `compress_pending()` - Compress working memory to recent chunk
- `clear_scope()` - Clear all context for a scope
- Three-layer assembly: long-term relevant + recent + working

**compression.py** - Pluggable compression strategies:
- `SummaryCompression` - Compress messages into AI-generated summary (default)
- `SlidingWindowCompression` - Keep last N messages, drop older
- `ExtractionCompression` - Extract key points only, keep important information
- All strategies implement the `CompressionStrategy` interface for easy extension

**backend.py** - Storage backend interface:
- `JSONFileBackend` - Each chunk stored as separate JSON file
- `SQLiteBackend` - All chunks stored in SQLite database
- Both support searching chunks by keyword

**remote.py** - Remote MCP service client:
- Connects to remote MCP HTTP service
- Forwards context operations to remote service
- Enables sharing context across multiple clients
- Good for team collaboration or syncing across devices

**Scopes:**
MCP supports multiple isolated scopes (think of them as workspaces). You can switch between different conversations or projects without mixing context. Each scope has its own working memory, recent chunks, and long-term storage.

---

### UI Layer (`internal/ui/`)

The UI is built with **PySide6** (Qt bindings for Python) and consists of two main floating widgets that stay on top of other windows. This gives you a chat overlay that works alongside your Live2D model without taking over the entire screen.

**FloatingInputBox** (`input_box.py`) - Always-on-top floating chat input:
- Frameless, resizable window that stays always on top
- Draggable anywhere on the screen
- Position and size persist between sessions via QSettings
- Supports dark/light themes with configurable opacity
- Chat history navigation with up/down arrows
- Sizing grip for resizing the window
- Custom title bar with drag handle and buttons
- Signals: `message_sent`, `visibility_changed`, `close_requested`, `new_context_requested`

**BubbleWidget** (`bubble_widget.py`) - Speech bubble for AI responses:
- Single-line floating text bubble with auto-scrolling for long text
- Typewriter effect for streaming output (gradual character-by-character display)
- Pause longer on Chinese punctuation for natural reading rhythm
- Auto-hides after configurable duration based on text length
- Smooth fade-out animation
- Draggable, position persists between sessions
- Supports theme-aware gradient text coloring
- Subtle outline for better readability against any background
- Maximum height constraint prevents it from covering too much screen space

**Other UI Components:**

- **TitleBar** (`title_bar.py`) - Custom draggable title bar for floating windows
- **HistoryManager** (`history_manager.py`) - Manages chat history persistence
- **Styles** (`styles.py`) - Theme definitions for dark/light modes, provides style sheets

**Qt Integration:**
The application runs the Qt event loop in the main thread. Agent chat processing runs as async tasks to keep the UI responsive. The Agent holds a reference to the BubbleWidget, and tools can directly update the UI when needed.

**Key Features:**
- Both widgets are frameless and borderless for a clean, minimal look
- All user positions are persisted automatically
- Always-on-top flag keeps the overlay visible above other applications
- Transparent background support allows the widgets to blend with your desktop
- Theme switching supported without restart

---

### WebSocket Layer (`internal/websocket/`)

The WebSocket layer handles communication with the Live2D application (typically Live2DViewerEX) running locally. It provides automatic reconnection with exponential backoff.

**ReconnectingWebSocket** (`reconnect.py`) - The main client class:
- Maintains connection state
- Supports automatic reconnection on disconnect
- Uses **ExponentialBackoff** strategy for retries
- Initial delay 1s, doubles each attempt with jitter (randomness) up to 60s max
- Can configure maximum retry attempts (0 = unlimited retries)
- Supports `on_connect` and `on_disconnect` callbacks
- Starts background receive loop that automatically resumes after reconnection

**ExponentialBackoff**:
- Implements the exponential backoff algorithm with jitter
- Random jitter prevents thundering herd
- Configurable initial delay, max delay, and multiplier
- Resets after successful connection

**Client** (`client.py`) - Base client with message types:
- Defines all message type constants for Live2D protocol (DisplayBubbleText, TriggerMotion, SetBackground, SetExpression, etc.)
- `Client` wrapper around aiohttp ClientWebSocketResponse
- `new_client()` creates new connection with proper URL normalization
- Provides message sending with error handling
- Defines structured dataclasses for each message type

The combination of `ReconnectingWebSocket` with exponential backoff ensures that the application automatically recovers from temporary network issues or Live2D service restarts without manual user intervention.

---

### Configuration (`internal/config/config.py`)

Configuration is loaded asynchronously from `config.json` on startup. The main `Config` class contains all top-level configuration:

- `live2dSocket: str` - Live2D WebSocket endpoint URL
- `models: list[AIModelConfig]` - List of configured AI models
- `memory: MemoryConfig` - Memory system configuration
- `sandbox: SandboxConfig` - Security sandbox configuration
- `planning: PlanningConfig` - Task planning system configuration

**AIModelConfig** dataclass:
- `name` - Unique identifier for the model
- `model` - Model identifier or path
- `system_prompt` - System prompt - can be string or modular prompt composition dict
- `type` - Model type enum: OllamaModel, TransformersModel, Online
- `default` - Whether this is the default model to use
- `config` - Additional model-specific options
- `temperature` - Sampling temperature
- `api_key` - Optional API key for online models
- `streaming` - Whether to enable streaming responses (default: True)

**Loading Flow:**
1. `Config.load()` async method reads and parses `config.json`
2. Populates typed dataclasses from JSON
3. Provides helper methods to get the default model or get by name
4. If `config.json` doesn't exist, returns default empty configuration

Configuration is gitignored because it may contain sensitive API keys. A template `config.example.json` is provided in the repository.

---

### Prompt Manager (`internal/prompt_manager/`)

The Prompt Manager enables modular prompt composition, allowing you to split large system prompts into reusable, maintainable modules instead of having one long hard-coded string.

**Key Features:**
- Singleton pattern - one instance shared across all model backends
- Recursive loading from `prompt_modules/` directory
- Supports nested directories with categorization
- Three composition modes for system prompts: raw string, module list only, or prefix + modules + suffix
- Template variable rendering with `{{variable}}` syntax

**Composition Examples:**
1. **Simple string**: `"You are a helpful assistant"` - used directly
2. **Modules only**: `{"modules": ["personality/waifu", "behavior/charming", "tools/default"]}` - composes multiple modules
3. **Full composition**: `{"prefix": "You are...", "modules": [...], "suffix": "..."}` - complete customization

**API:**
- `load(modules_dir)` - Load all prompt modules recursively
- `compose_system_prompt(prompt_config)` - Compose according to configuration format
- `render_module(module_path, context)` - Render module with template variables
- `list_modules_by_category()` - Group modules by directory category

This system makes it easy to reuse prompt components across different character configurations and keep your prompts organized.

---

## Component Interactions and Dependencies

### High-Level Interaction Flow

```
User Input → FloatingInputBox → Agent.chat() → [Memory/MCP → get_context()] → Model.chat() → [ToolRegistry → execute tools] → (repeat tool loop) → Response → BubbleWidget or WebSocket → Memory save → Background compression
```

### Key Dependency Graph

- **`__main__.py`** → Creates everything, depends on all
- **Agent** → Depends on: ModelTrait, ToolRegistry, MemoryManager, SkillManager, WebSocket Client
- **ModelTrait implementations** → Depend on: PromptManager, Config
- **ToolRegistry** → Depends on: Tool implementations, SandboxMiddleware
- **MemoryManager** → Depends on: SessionManager, ContextManager, StorageBackend, optionally MCPContextManager
- **MCPContextManager** → Depends on: CompressionStrategy, StorageBackend, optionally RemoteBackend
- **SkillManager** → Depends on: SkillRegistry, DynamicLoader, integrates with ToolRegistry and PromptManager
- **UI Components** → Don't depend on business logic, use signals for communication
- **ReconnectingWebSocket** → Independent, just handles connection and reconnection

### Design Principles

1. **Dependency Injection** - Agent receives model, memory config, etc. instead of creating them directly
2. **Abstract Base Classes** - All pluggable components use ABCs for easy extension
3. **Single Responsibility** - Each component does one thing well
4. **Dependency Inversion** - Depends on abstractions, not concretions
5. **Async First** - All I/O operations are async to keep UI responsive

### Communication Patterns

- **Signal/Slot** - Qt UI components use Qt signals for communication with main app
- **Async/Await** - All API calls that do I/O use async/await
- **Direct Method Calls** - Most component-to-component communication is direct method calls
- **Event Loops** - Qt event loop runs in main thread, async tasks scheduled onto it

---

## Extension Points for Contributors

Live2oder is designed to be easily extended. Here are the common extension points where you can add new functionality without changing core code:

### Add a New AI Model Backend

1. Create a new file in `internal/agent/agent_support/`
2. Subclass `ModelTrait` abstract base class
3. Implement:
   - `__init__` that takes `AIModelConfig`
   - `async def chat(message, tools) -> dict`
   - `def stream_chat(message, tools) -> AsyncIterator[dict]`
4. Add your model type to `AIModelType` enum in `config.py`
5. Update `create_agent` factory in `agent.py` to create your backend

**What you get for free:**
- Integration with Agent chat processing flow
- Tool calling support
- Memory/MCP context management
- Streaming response display
- Prompt composition with PromptManager

### Add a New Tool

**Two ways to add tools:**

1. **Static tool** (built into the code):
   - Create new file in `internal/agent/tool/` or appropriate subdirectory
   - Subclass `Tool` ABC, implement all abstract methods
   - Register it in `Agent._register_default_tools()` in `agent.py`

2. **Dynamic tool** (created at runtime by AI):
   - AI can create tools using `GenerateToolTool` meta-tool
   - Tools are automatically persisted and loaded on next startup
   - No code changes needed - AI handles everything

**What you get for free:**
- Automatic registration with ToolRegistry
- Schema generation for AI model
- Security sandbox for file/network operations
- Error handling and logging
- Pass-through of WebSocket and BubbleWidget references

### Add a New Skill

Skills are the cleanest way to package and distribute functionality:

1. Create a new directory in `skills/your-skill-name/`
2. Create `skill.yaml` with metadata:
   ```yaml
   name: your-skill-name
   version: 1.0.0
   description: What your skill does
   author: Your name
   category: your-category
   ```
3. Implement the skill class in Python
4. Package your tools and prompts with the skill
5. Restart the application - SkillManager auto-discovers it

**What you get for free:**
- Dynamic loading without changing core code
- Hot-reload support
- Automatic tool registration when enabled
- Configuration management
- Lifecycle hooks (initialize/shutdown)

### Add a New Compression Strategy for MCP

1. Create new strategy class in `internal/mcp/compression.py`
2. Implement the `CompressionStrategy` ABC
3. Add your strategy to the `create_compression_strategy` factory function
4. Users can select it in configuration with `compression_strategy: your-strategy`

### Add a New Storage Backend

For either legacy Memory or MCP:
- **Memory storage**: Subclass `BaseStorage` in `internal/memory/storage/_base.py`
- **MCP storage**: Subclass `MCPStorageBackend` in `internal/mcp/backend.py`
- Implement all required storage operations
- Update the factory functions to create your backend

### Add UI Themes

Add new theme colors to `internal/ui/styles.py` - the system automatically supports theme switching without restart.

### Add New Live2D Message Types

1. Add the message type constant to `internal/websocket/client.py`
2. Create a dataclass for the message parameters
3. Add a convenience sending function
4. Create a tool that uses the new message type
5. Now AI can control the new Live2D capability

---

## Summary

The modular architecture makes Live2oder easy to extend and maintain. By following the established patterns and using the existing abstract base classes, you can add new capabilities without disrupting the core system. The main extension points are:

- **New model backends** - Support for new AI providers
- **New tools** - New capabilities for the AI agent
- **New skills** - Reusable packages of tools and prompts
- **New compression strategies** - Different approaches to context management
- **New storage backends** - Different storage options

Contributors are encouraged to follow the existing patterns and submit pull requests with new capabilities!
