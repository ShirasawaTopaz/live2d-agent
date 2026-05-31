# Productivity Platform Design

**Date:** 2026-05-31
**Status:** Design

## Overview

Add three productivity subsystems to Live2oder, transforming it from a reactive chat app into a proactive desktop AI platform:

1. **Multi-Session Auto-Routing** — model-driven topic detection and automatic session switching
2. **Background Scheduler** — cron tasks, event-triggered tasks, and polling tasks
3. **External Integrations** — clipboard processing, browser control, global hotkeys

All three built incrementally within the existing layered architecture. They share the Agent as the unified execution engine and require minimal changes to existing code.

---

## Architecture

### New Module Layout

```
internal/session/          ← 新增
├── session_manager.py     # 会话生命周期
├── topic_classifier.py    # 话题检测
├── session_store.py       # 持久化
└── router.py              # 路由决策

internal/scheduler/        ← 新增
├── engine.py              # 调度核心 (asyncio)
├── triggers.py            # 触发器 (Cron / Watch / Polling)
├── store.py               # 任务持久化
└── notification.py        # 结果推送

internal/integration/      ← 新增
├── clipboard.py           # 剪贴板监听 + mini 操作栏
├── browser.py             # 浏览器控制工具
└── hotkey.py              # 全局快捷键
```

### Dependency Graph

```
integration ──→ Agent ──→ Memory
                    ↑
scheduler ─────────┘
     ↑
session ──→ Memory
```

### Changes to Existing Code

| File | Change | Why |
|------|--------|-----|
| `internal/memory/_manager.py` | Add `switch_session(session_id)` method | Serves session router |
| `internal/ui/input_box.py` | Register global hotkeys, clipboard hook signal | Enables quick summon and clipboard trigger |
| `internal/app/live2d_agent_app.py` | Initialize three new modules on startup | Bootstrap new subsystems |
| `internal/config/config.py` | Add config sections for hotkeys, scheduler, clipboard | User configurability |
| `config.example.json` | Add example config entries | Documentation |

---

## 1. Multi-Session Auto-Routing

### Design Principle

The user chats normally without managing sessions manually. The model detects topic shifts and automatically creates/switches sessions. Old sessions are summarized and archived, not lost.

### Components

#### 1.1 TopicClassifier (`topic_classifier.py`)

Two-layer classification, no extra LLM calls:

- **Layer 1 (fast):** Keyword/regex matching. Built-in rules map common phrases to topics (e.g., "写代码" → `coding`, "翻译" → `translation`). Users can configure custom keyword→topic mappings.
- **Layer 2 (fallback):** Embedding similarity. Uses the existing `internal/rag/embeddings.py` module to compute cosine similarity between the current message embedding and each session's summary embedding. Selects the best match above threshold; creates a new session if none qualify.

```python
class TopicClassifier:
    def classify(self, text: str, sessions: list[Session]) -> ClassificationResult:
        """Returns {topic, confidence, suggested_session_id | None}"""
```

#### 1.2 Router (`router.py`)

Decision logic based on classifier output:

```
confidence > 0.8 + match existing session → switch, inject old session summary
confidence > 0.8 + new topic              → create session, inherit key context variables
confidence <= 0.8                        → stay in current session
```

When switching, the router injects a 200-character summary of the previous session into the new session's context, so the model knows what was discussed before without carrying the full conversation.

#### 1.3 SessionManager (`session_manager.py`)

```python
class SessionManager:
    async def get_or_create_session(self, text: str, current_id: str) -> Session:
        """Classify text and return the appropriate session."""

    async def activate(self, session_id: str) -> None:
        """Save current session state, load target session into Agent."""

    async def list_sessions(self) -> list[Session]: ...
    async def delete_session(self, session_id: str) -> None: ...
    async def rename_session(self, session_id: str, name: str) -> None: ...
```

#### 1.4 Session Data Structure

```python
@dataclass
class Session:
    session_id: str
    topic: str              # Auto-identified topic label
    display_name: str       # User-editable name (defaults to topic)
    summary: str            # 200-char summary (reuses existing _summary module)
    created_at: float
    last_active_at: float
    message_count: int
    context_snapshot: dict  # Key context variables (user preferences, current project, etc.)
```

#### 1.5 SessionStore (`session_store.py`)

Follows the existing pattern in `internal/memory/storage/` — abstract base with JSON and SQLite implementations. Stores session metadata and summaries. Full message history stays in Memory layer.

#### 1.6 Memory Integration

`MemoryManager` gains one method:

```python
async def switch_session(self, session_id: str) -> list[Message]:
    """Archive current session state, load target session context."""
```

The Memory layer's existing compression/summarization pipeline handles per-session context window management.

---

## 2. Background Scheduler

### Design Principle

The scheduler uses asyncio primitives (no external scheduler library) for maximum portability. The Agent is the execution engine for all task types — the scheduler only decides when to fire.

### Components

#### 2.1 SchedulerEngine (`engine.py`)

```python
class SchedulerEngine:
    async def add(self, task: Task) -> str: ...
    async def remove(self, task_id: str) -> bool: ...
    async def list_tasks(self) -> list[Task]: ...
    async def pause(task_id: str) / resume(task_id: str): ...

    # Internal: one asyncio.Task per scheduled item
    # CronTask: loop with asyncio.sleep(next_fire - now)
    # WatchTask: await trigger.wait()
    # PollingTask: loop with asyncio.sleep(interval)
```

#### 2.2 Trigger System (`triggers.py`)

Extensible trigger architecture:

```python
class TriggerSource(ABC):
    """Pluggable event source."""
    async def start(self, callback: Callable[[Event], None]) -> None: ...
    async def stop(self) -> None: ...

# Built-in implementations
class CronTrigger(TriggerSource):      # Cron expression or one-shot timestamp
class FileWatcher(TriggerSource):      # watchdog-based directory monitoring
class ProcessWatcher(TriggerSource):   # Process start/exit events
class PollingTrigger(TriggerSource):   # Fixed-interval polling

# Extension points (not implemented now, architected for)
class NetworkWatcher(TriggerSource):   # Port/connection state changes
class WebhookListener(TriggerSource):  # HTTP webhook endpoint
class ClipboardChangeTrigger(TriggerSource):  # Clipboard content change
class WindowFocusTrigger(TriggerSource):     # Active window change
```

#### 2.3 Task Types

```python
@dataclass
class Task:
    task_id: str
    prompt: str            # The prompt to send to Agent when triggered
    created_by: str        # "user" or "agent"
    enabled: bool
    created_at: float
    last_fired_at: float | None

class CronTask(Task):
    cron_expr: str | None  # "*/30 * * * *"
    run_at: float | None   # One-shot timestamp (alternative to cron)

class WatchTask(Task):
    trigger: TriggerSource
    filter: EventFilter | None  # Optional: only fire on *.pdf, etc.

class PollingTask(Task):
    interval: float        # Seconds between polls
    stop_condition: str | None  # "when result contains 'closed'"
```

#### 2.4 Task Creation Flow

```
User: "每天早上9点帮我汇总今天的待办事项"
  ↓
Agent parses intent, generates:
  CronTask(
    prompt="汇总用户今天的待办事项，列出优先级",
    cron_expr="0 9 * * *"
  )
  ↓
SchedulerEngine.add(task)
  ↓
Store persists task → survives restart
```

Natural language → Task is done by the Agent itself. The scheduler only stores structured `Task` objects.

#### 2.5 Task Session Context

When a scheduled task fires, it runs in its own isolated session:

- **Each task gets a dedicated session** — task output doesn't pollute the user's active conversation
- The session label is the task's description (e.g., "每日待办汇总")
- Notification includes a one-click action to open that session's history
- If the task was created during a user session, it inherits relevant context variables (user preferences, language, etc.) from that session at creation time

#### 2.6 Notification (`notification.py`)

When a task completes:

```
Agent response
  ↓
Notification.push(task, result)
  ↓
├── QSystemTrayIcon.showMessage()  ← desktop toast
├── Live2D bubble shows summary    ← existing bubble pipeline
└── Stored in task history         ← audit trail
```

#### 2.6 Persistence (`store.py`)

Follows existing storage pattern (`internal/memory/storage/`). Tasks stored as JSON/SQLite. On startup, the scheduler reloads all enabled tasks and restarts their triggers.

---

## 3. External Integrations

### 3a. Clipboard Integration (`clipboard.py`)

#### Flow

```
User copies text anywhere (Ctrl+C)
  ↓
ClipboardMonitor detects change
  ↓
Shows mini action bar near mouse cursor:
  [📝 总结] [🌐 翻译] [🔄 改写] [💻 代码] [✕]
  ↓ User clicks action
  ↓
Agent processes text with the chosen action
  ↓
Result written back to clipboard + balloon notification
```

#### Design Constraints

- **Only active when app is visible** (not monitoring in background, for security)
- Mini action bar is a small frameless `QWidget` with ~2-second auto-dismiss
- Action buttons are configurable in settings
- Uses `QClipboard.dataChanged` signal

```python
class ClipboardMonitor:
    def start(self) -> None:
        """Begin listening to QClipboard.dataChanged signal."""
    def stop(self) -> None:
        """Stop listening."""
    def set_actions(self, actions: list[ClipAction]) -> None:
        """Configure available quick actions."""

@dataclass
class ClipAction:
    id: str            # "summarize", "translate", etc.
    label: str         # Display text on button
    prompt_template: str  # "{text}" placeholder
```

### 3b. Browser Integration (`browser.py`)

Reuses the existing Playwright MCP infrastructure. Exposes browser operations as Agent Tools.

#### Tools Registered

| Tool Name | Parameters | Description |
|-----------|------------|-------------|
| `browser_open` | `url: str` | Navigate to URL, return page text |
| `browser_extract` | `selector: str` | Extract content from page element |
| `browser_click` | `selector: str` | Click a page element |
| `browser_type` | `selector: str, text: str` | Type text into input field |
| `browser_search` | `query: str` | Search engine query, return top results |
| `browser_screenshot` | `selector: str?` | Take page/element screenshot (for vision models) |
| `browser_scroll` | `direction: str` | Scroll page up/down |

#### Implementation

```python
class BrowserController:
    """High-level wrapper over Playwright MCP for Agent Tool consumption."""
    
    def __init__(self, playwright_session):
        self._ps = playwright_session
    
    async def navigate(self, url: str) -> PageContent: ...
    async def extract(self, selector: str) -> str: ...
    async def click(self, selector: str) -> None: ...
    async def type_text(self, selector: str, text: str) -> None: ...
    async def search(self, query: str) -> list[SearchResult]: ...
```

#### Example Agent Interaction

```
User: "帮我在淘宝搜机械键盘，比较前三名的价格"
  ↓
Agent calls: browser_search("淘宝 机械键盘")
  ↓
Agent calls: browser_extract(".product-item:nth-child(1) .price")
Agent calls: browser_extract(".product-item:nth-child(2) .price")
Agent calls: browser_extract(".product-item:nth-child(3) .price")
  ↓
Agent compares and responds with structured comparison
```

### 3c. Global Hotkeys (`hotkey.py`)

#### Default Bindings

| Shortcut | Action |
|----------|--------|
| `Ctrl+Shift+Space` | Toggle input box visibility |
| `Ctrl+Shift+C` | Clipboard quick-process (process selected text) |

#### Design

- Stored in `config.json` under `hotkeys` section
- Uses platform-appropriate mechanism (pynput on Windows/Linux, or Qt native)
- Conflicts with system/other app shortcuts → ignored gracefully
- User-configurable in Settings window

```python
class HotkeyManager:
    def register(self, shortcut: str, callback: Callable) -> bool: ...
    def unregister(self, shortcut: str) -> None: ...
    def register_all(self, bindings: dict[str, Callable]) -> None: ...
```

---

## Error Handling Strategy

| Component | Error Scenario | Handling |
|-----------|---------------|----------|
| TopicClassifier | Embedding not available | Fall back to keyword-only, log warning |
| SessionManager | Session load failure | Create fresh session, don't block user |
| Scheduler | Task execution fails | Retry once after 60s, then disable task and notify user |
| FileWatcher | Path doesn't exist | Notify user, pause trigger, don't crash |
| Clipboard | Non-text content | Skip silently (image/file clipboard not processed yet) |
| Browser | Page load timeout | Return partial content + timeout error to Agent |
| Hotkey | Registration conflict | Log warning, hotkey silently unavailable |

---

## Testing Strategy

### Session Module
- Unit: `TopicClassifier` classification accuracy with known inputs
- Unit: `Router` decision logic with boundary confidence values
- Integration: `SessionManager` + `MemoryManager.switch_session()` round-trip

### Scheduler Module
- Unit: `CronTrigger` next-fire calculation
- Unit: `FileWatcher` event filtering
- Integration: Full `add → fire → Agent.execute → notification` pipeline with mock Agent
- Integration: Persistence round-trip (save tasks, restart engine, verify reload)

### Integration Module
- Unit: `ClipboardMonitor` signal handling with mock QClipboard
- Unit: `HotkeyManager` registration/unregistration
- Integration: `BrowserController` tool registration and execution (with headless Playwright)

### Manual Verification
- Global hotkey summon on Windows
- Clipboard mini-bar positioning near mouse
- Browser search → extract → compare flow end-to-end

---

## Implementation Order

1. **Session Manager** — foundational, touches Memory layer which other modules may depend on
2. **Scheduler** — independent of UI changes, can be built in parallel after Session
3. **Integration (clipboard + hotkey)** — requires UI changes, most user-visible
4. **Integration (browser)** — depends on Playwright MCP already being stable
