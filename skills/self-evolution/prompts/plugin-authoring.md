# 自进化插件编写规范

你可以用 `plugin_*` 工具集在**运行时**创建或改写 cordis 插件。这适用于：需要新增能力、
需要替换 Agent 对话循环（最小循环）、需要替换滚动字/气泡输出模块、需要接线新的服务。

## 何时铸造插件

- 某个能力应该是**可插拔替换**的（例：另一个最小循环实现、另一种输出节奏）。
- 需要把跨会话稳定的逻辑固化为服务，而不是每次对话重新推导。
- 需要在不重启应用的情况下生效（热重载）。

不需要铸造插件的场景：一次性计算、纯文本回答、已有工具能覆盖的操作。

## 标准流程

1. `plugin_scaffold(name, kind, description)` —— 得到骨架源码，先审阅。
2. 按需修改 `code`（必须保留 `def apply(ctx, config=None)`）。
3. `plugin_install(name, code, kind, config)` —— 校验 → 版本快照 → 写盘 → 挂载。
4. `plugin_status(entry_id)` / `plugin_diagnose()` —— 确认 fiber 为 `active`。
5. 出问题时：`plugin_reload(entry_id)`，仍失败则 `plugin_rollback(name)`。

## 插件形态与约束

- 源码必须导出 `apply(ctx, config=None)`（或 `plugin_name` + 一个 `Service` 子类）。
- 依赖别的能力请声明 `inject = ["服务名"]`：服务缺失时 fiber 停在 `pending` 而不是崩溃。
- 一切注册都是 **effect**：`ctx.service(...)`、`ctx.on(...)`、`ctx.effect(disposer)`、
  `tools.register(tool, owner=ctx)` 都会在插件卸载时自动撤销。不要留下裸监听器或裸工具。
- 需要后台任务用 `ctx.spawn(coro)`；它随插件卸载自动取消。
- 允许导入：`internal.cordis`、`internal.plugins`、asyncio/typing/dataclasses/json/logging/
  pathlib/time/re/math/collections 等标准库。
- 禁止：`exec`/`eval`/`compile`/`__import__`、`subprocess`、`ctypes`、socket、dunder 逃逸。

## 两个核心槽位

- **最小循环**：注册服务名 `agent/loop`，实现 `attach_agent(agent)` 与
  `async run(message, ws) -> ChatResult`（`internal.plugins.agent.loop.ChatResult`）。
  参考 `internal.plugins.agent.loop_minimal`。
- **滚动字输出**：注册服务名 `outputs/bubble`，实现
  `attach(widget=None, timing=None)`、`async begin(chunk)`、`async stream(chunk)`、
  `async finish(text, duration_ms)`。`chunk` 是
  `internal.plugins.outputs.typewriter.BubbleChunk`；`stream` 会经过
  `bubble/stream` waterfall，其他插件可改写或否决。

替换槽位后，旧插件仍可 `plugin_toggle` 恢复，因此不要删除旧实现。

## 替换一个槽位的完整流程

以「换成自己的最小循环」为例（输出槽位同理，服务名换成 `outputs/bubble`）：

1. `plugin_scaffold(name="my_loop", kind="loop")` 取骨架。
2. 改代码：确保注册的服务名是 `agent/loop`，并实现 `attach_agent` 与 `async run(message, ws)`。
   新插件只会在**旧实现卸载之后**才可挂载（服务名冲突时注册的是后挂载者）。
3. `plugin_toggle(entry_id="loop", enabled=false)` —— 卸载内置循环。
4. `plugin_install(name="my_loop", code=..., kind="loop")` —— 挂载新循环。
5. `plugin_status()` 确认只有一个 `agent/loop` 提供者，且状态为 `active`。
6. 不满意：`plugin_toggle(entry_id="loop", enabled=true)` 恢复内置实现，再
   `plugin_toggle(entry_id="user:my_loop", enabled=false)` 停用自己的。

注意：`entry_id` 以 `user:` 前缀的是自进化安装的插件，其余是内置条目（见 `plugin_status().entries`）。
两个实现同时启用会互相覆盖服务注册，务必先禁用旧的。

## 安全与回滚

- 默认只允许写入用户插件目录（`%APPDATA%/Live2Oder/plugins/sources`）。
- 写入仓库内 `internal/plugins/**` 需要 `allow_core_writes: true` 且会请求用户审批。
- 每次 `plugin_install` 都会留下版本快照；`plugin_rollback` 可回到任意历史版本。
- 每次动作都会写入审计日志，用 `plugin_audit` 查看。

## 失败诊断

- `pending`：缺少 `inject` 声明的服务。用 `plugin_diagnose` 看 `missing` 字段。
- `failed`：`apply()` 抛异常。看应用日志，或先 `plugin_rollback` 恢复上一个可用版本。
- 没有反应：确认条目 id 出现在 `plugin_status().entries` 中，且没有 `disabled: true`。
