# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Live2oder is a Python-based desktop AI Agent application with a PySide6 Qt UI. It connects to Live2D models via WebSocket and supports multiple AI model backends (Ollama, Transformers, Online APIs).

## Development Commands

### Running the Application
```bash
# First time setup: copy config template
cp config.example.json config.json
# Edit config.json with your settings

# Run the application
python __main__.py
```

### Building for Distribution
```bash
# Build executable using PyInstaller
python build.py
```

### Configuration
- `config.json` - User configuration (gitignored, contains API keys)
- `config.example.json` - Template showing configuration format
- `prompt_modules/` - Modular prompt components that can be referenced in config

## Architecture Overview

### Core Layers

1. **Agent Layer** (`internal/agent/`)
   - `agent.py` - Main Agent class, orchestrates chat, tool calls, memory
   - `agent_support/` - Model implementations: Ollama, Transformers, Online API
   - `tool/` - Tool implementations: file operations, Live2D controls, web search
   - `register.py` - Tool registry

2. **Memory System** (`internal/memory/`)
   - `_manager.py` - `MemoryManager` - main interface
   - `_session.py` - Session management
   - `_context.py` - Context window management and compression triggers
   - `_summary.py` - Conversation summarization for compression
   - `_long_term.py` - Long-term memory with keyword search
   - `_archive.py` - Archive compression for old sessions
   - `storage/` - Storage backends (JSON, SQLite)

3. **UI Layer** (`internal/ui/`)
   - `input_box.py` - Floating input widget (`FloatingInputBox`)
   - `bubble_widget.py` - Qt-based speech bubble widget (`BubbleWidget`)
   - `styles.py` - UI styles and themes

4. **WebSocket Client** (`internal/websocket/`)
   - `client.py` - WebSocket connection to Live2D, message types

5. **Configuration** (`internal/config/`)
   - `config.py` - Config loading, `AIModelConfig`, `Config` classes

 6. **Prompt Manager** (`internal/prompt_manager/`)
    - `prompt_manager.py` - Loads and composes modular prompts from `prompt_modules/`

 7. **MCP Layer** (`internal/mcp/`) **(Model Context Protocol - NEW)**
    - `protocol.py` - MCP protocol definitions: messages, chunks, request/response
    - `config.py` - MCP configuration (local/hybrid/remote modes, compression strategies)
    - `manager.py` - `MCPContextManager` - core three-layer context management
    - `compression.py` - Pluggable compression strategies: summary/sliding/extraction
    - `backend.py` - Local storage backends: JSON/SQLite
    - `remote.py` - Remote MCP service HTTP client
    - Features: three-layer storage (Working → Recent → Long-Term), multi-scope isolation, remote service integration

### Key Classes and Interfaces

- **ModelTrait** (`internal/agent/agent_support/trait.py`) - Abstract base for model implementations
- **Tool** (`internal/agent/tool/base.py`) - Abstract base for tools
- **MemoryManager** - Main interface for memory operations
- **Message** type - `{