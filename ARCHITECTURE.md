# Live2oder Architecture

## Overview

Live2oder is a desktop AI Agent application that connects AI language models to Live2D virtual characters via WebSocket. It provides a PySide6-based Qt user interface, supports multiple AI backends (local and online), and features an extensible tool and skill system for custom functionality.

The application follows a modular layered architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│  User Input / System Tray                                    │
├─────────────────────────────────────────────────────────────┤
│  UI Layer                  (internal/ui/)                    │
│  FloatingInputBox, BubbleWidget, Styles                      │
├─────────────────────────────────────────────────────────────┤
│  Agent Layer                (internal/agent/)                │
│  Agent orchestration, response processing, tool dispatch     │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐│
│  │ Model Support│ │ Tool System │ │  Memory System          ││
│  │(agent_support)│ │  (tool/)   │ │  (memory/)              ││
│  │ Ollama      │ │ Live2D tools│ │ Multi-layer compression  ││
│  │ Transformers│ │ File ops   │ │ Long-term searchable storage│
│  │ Online API  │ │ Web search  │ │                          ││
│  └─────────────┘ └─────────────┘ └─────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│  Skill System               (internal/skill/)               │
│  Extensible skills with dynamic hot-reload                  │
├─────────────────────────────────────────────────────────────┤
│  Prompt Manager            (internal/prompt_manager/)       │
│  Modular prompt composition                                    │
├─────────────────────────────────────────────────────────────┤
│  Configuration            (internal/config/)                │
│  JSON config loading and validation                          │
├─────────────────────────────────────────────────────────────┤
│  MCP Layer (Optional)      (internal/mcp/)                  │
│  Model Context Protocol - advanced context management        │
├─────────────────────────────────────────────────────────────┤
│  WebSocket Layer         (internal/websocket/)              │
│  Live2D connection with automatic reconnection               │
├─────────────────────────────────────────────────────────────┤
│  Live2D WebSocket Service (external process)                │
└─────────────────────────────────────────────────────────────┘
```

## Core Layers

### UI Layer (`internal/ui/`)

The UI layer provides all user interface components built with PySide6:

- **`input_box.py`** - Floating input widget for user text input
- **`bubble_widget.py`** - Speech bubble widget that displays AI responses
- **`title_bar.py`** - Custom title bar for the frameless window
- **`styles.py`** - UI styling and theme definitions
- **`history_manager.py`** - UI history management

The UI runs on the main Qt thread, with all heavy AI operations offloaded to background threads to keep the interface responsive. System tray integration allows the application to run in the background with quick access.

### Agent Layer (`internal/agent/`)

The core orchestration layer that manages the entire conversation flow:

- **`agent.py`** - Main `Agent` class that coordinates chat processing, tool calling, and response delivery
- **`register.py`** - Tool registry that maintains available tools
- **`response.py`** - Response parsing and post-processing
- **`api.py`** - API exposed to the UI layer
- **`sandbox/`** - Security sandbox middleware for safe tool execution

The agent is responsible for:
1. Receiving user input from the UI
2. Composing the full prompt with memory and system prompts
3. Calling the AI model backend
4. Parsing and executing tool calls
5. Sending the final response back to UI and Live2D
6. Storing the interaction in memory

### Model Support (`internal/agent/agent_support/`)

Abstract trait-based system for supporting multiple AI backends:

- **`trait.py`** - `ModelTrait` abstract base class that defines the interface all model backends must implement
- **`ollama.py`** - Ollama backend for local models running via Ollama service
- **`transformers.py`** - Hugging Face Transformers backend for local model inference
- **`online.py`** - Online API backend for remote model services (like Volcengine Ark)

The trait abstraction makes it easy to add new model backends without changing the rest of the codebase. Multiple models can be configured and switched at runtime.

### Tool System (`internal/agent/tool/`)

Extensible tool system that allows the AI to interact with the external world:

- **`base.py`** - `Tool` abstract base class
- **`live2d/`** - Live2D-specific tools for controlling the model:
  - `set_expression.py` - Change model expression
  - `trigger_motion.py` - Trigger character motion
  - `display_bubble_text.py` - Display speech bubble text
  - `clear_expression.py` - Reset to default expression
  - `next_expression.py` - Cycle to next expression
  - `play_sound.py` - Play audio through Live2D
  - `set_background.py` - Change background image
  - `set_model.py` - Switch Live2D model
- **`file.py`** - File read/write operations
- **`web_search.py`** - Web search capability
- **`office.py`** - Office document processing
- **`dynamic/`** - Dynamic tool generation system with security auditing and versioning
- **`meta/`** - Meta-tools for tool management (generate, delete, list, rollback)

All tool operations go through a security sandbox that enforces access controls and user approval policies.

### Memory System (`internal/memory/`)

Multi-layer conversational memory with automatic compression to maintain context within model window limits:

- **`_manager.py`** - `MemoryManager` main interface used by the agent
- **`_session.py`** - Session management - each conversation is a session
- **`_context.py`** - Context window management with compression triggers
- **`_summary.py`** - Conversation summarization for compressing older messages
- **`_long_term.py`** - Long-term memory storage with keyword search
- **`_archive.py`** - Archive compression for very old sessions
- **`storage/`** - Storage backends:
  - `_json.py` - JSON file storage
  - `_sqlite.py` - SQLite storage (recommended for larger deployments)

Memory hierarchy:
1. **Working Memory** - Active conversation context that fits in the model's context window
2. **Recent Memory** - Compressed summaries of older messages
3. **Long-term Memory** - Archived memory with searchable embeddings/keywords

When the context window fills up, the memory system automatically compresses older messages by summarizing them and moving them to deeper storage layers.

### Skill System (`internal/skill/`)

Extensible skill system that supports dynamic loading and hot-reload:

- **`base.py`** - `Skill` base class
- **`manager.py`** - Skill manager that handles loading and lifecycle
- **`dynamic_loader.py`** - Dynamic module loader for hot-reloading
- **`registry.py`** - Skill registry
- **`integration.py`** - Integration with agent and tools
- **`external.py`** - External skill loading from `skills/` directory
- **`builtin/`** - Built-in skills

Skills are stored as separate directories in the `skills/` folder at the project root. Each skill can provide its own prompts and tools. The system supports hot-reloading so skills can be added/modified without restarting the application.

### Prompt Manager (`internal/prompt_manager/`)

Modular prompt composition system:

- **`prompt_manager.py`** - Loads and composes modular prompts from `prompt_modules/` directory

Prompts are split into reusable modules (base rules, capabilities, personality, scenarios) that can be combined based on configuration. This makes it easy to customize the AI behavior without editing large monolithic prompt files.

### WebSocket Layer (`internal/websocket/`)

Manages the WebSocket connection to the external Live2D service:

- **`client.py`** - WebSocket client implementation
- **`reconnect.py`** - Automatic reconnection logic with exponential backoff

The layer handles:
- Connection establishment and maintenance
- Automatic reconnection on disconnect
- Message serialization/deserialization
- Sending expression/motion commands to Live2D
- Receiving events from Live2D

The external Live2D service runs as a separate process and communicates via JSON messages over WebSocket.

### Configuration (`internal/config/`)

- **`config.py`** - Configuration loading, validation, and access

Loads configuration from `config.json`, provides typed configuration objects (`Config`, `AIModelConfig`). The `config.example.json` template is provided for users to copy.

### MCP Layer (`internal/mcp/`) *Optional*

Model Context Protocol implementation for advanced three-layer context management:

- **`protocol.py`** - MCP message and chunk protocol definitions
- **`config.py`** - MCP configuration (local/hybrid/remote modes)
- **`manager.py`** - `MCPContextManager` core context management
- **`compression.py`** - Pluggable compression strategies (summary, sliding window, extraction)
- **`backend.py`** - Local storage backends (JSON, SQLite)
- **`remote.py`** - Remote MCP service HTTP client

This is an optional advanced feature that provides more sophisticated context management than the built-in memory system. It supports:
- Three-layer storage (Working → Recent → Long-Term)
- Multi-scope context isolation
- Remote context service integration
- Pluggable compression strategies

## Data Flow

A typical interaction follows this flow:

1. **User Input** → User types message in `FloatingInputBox` (UI Layer)
2. **Agent receives message** → `Agent.on_user_message()` (Agent Layer)
3. **Memory retrieval** → `MemoryManager.get_working_context()` retrieves relevant context (Memory System)
4. **Prompt composition** → `PromptManager.compose()` builds the full prompt from modules (Prompt Manager)
5. **Model inference** → AI backend (`ModelTrait`) generates response (Model Support)
6. **Tool call detection** → Agent parses response and checks if tool calls are requested
7. **(Optional) Tool execution** → Tool is invoked via registry, potentially through sandbox middleware (Tool System)
   - If the tool controls Live2D → Command sent via WebSocket Layer to Live2D service
8. **Response generation** → Final response is prepared after tool execution
9. **Memory storage** → New interaction is stored in `MemoryManager` (Memory System)
10. **UI update** → Response displayed in `BubbleWidget` (UI Layer)
11. **Live2D output** → Response text and expressions sent via WebSocket to Live2D model (WebSocket Layer)

## Key Architectural Design Decisions

### Async I/O Throughout

All blocking operations (model inference, network requests, tool execution) use async/await to avoid blocking the UI thread. This keeps the application responsive even when running large local models.

### Multiple AI Backend Support via Trait Abstraction

The `ModelTrait` abstract base class defines a minimal interface that all backends must implement. This makes it trivial to add new model backends without changing any other code in the system. The current implementation supports local (Ollama, Transformers) and online (API) models.

### Extensible Tool and Skill System

Tools and skills are designed to be added without modifying the core codebase. External skills can be loaded from the `skills/` directory dynamically with hot-reload. Dynamic tool generation allows the AI to create new tools at runtime when needed.

### Security Sandbox for Safe Operations

All file operations and dynamic code execution run in an approval-based sandbox. User consent is required for certain operations, and access can be restricted to specific directories. This prevents accidental data loss or malicious activity.

### Auto-Reconnection for WebSocket Reliability

The WebSocket layer automatically attempts to reconnect if the connection to the Live2D service drops. Exponential backoff is used to avoid overwhelming the service. All pending messages are queued during reconnection.

### Modular Prompt Composition

Prompts are split into small reusable modules in the `prompt_modules/` directory. Users can mix and match modules (core rules, capabilities, personality, scenarios) in their configuration to customize AI behavior.

### Multi-Layer Memory with Compression

To handle long conversations within model context limits, the memory system automatically compresses older messages. The three-layer approach (working → recent → long-term) keeps relevant context available while respecting token limits. Long-term memory supports keyword search to retrieve old information when needed.

## Technology Stack

- **UI Framework**: PySide6 (Qt6)
- **AI Backends**: Ollama, Hugging Face Transformers, OpenAI-compatible online APIs
- **Memory Storage**: JSON or SQLite
- **WebSocket**: asyncio WebSocket client
- **Concurrency**: Python async/await

## Extension Points

Live2oder can be extended in several ways:

1. **Add a new AI backend** - Implement the `ModelTrait` interface in `internal/agent/agent_support/`
2. **Add a new tool** - Create a new tool class in `internal/agent/tool/` or use dynamic generation
3. **Add a new skill** - Create a new directory in `skills/` with your skill definition
4. **Add prompt modules** - Create new modules in `prompt_modules/` and reference them in config
5. **Add a new memory storage backend** - Implement the storage interface in `internal/memory/storage/`
