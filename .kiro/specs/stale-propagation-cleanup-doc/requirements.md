# Stale 传播死代码清理 + 分层文档 — Requirements

## 背景

codegraph 复核（2026-06-23）发现联动 stale 传播侧有两个治理点：

1. **死代码**：`backend/app/services/stale_incremental_propagation.py`（86 行，含 `propagate_stale_by_account`/`propagate_stale_by_wp_code`/`propagate_stale_by_adjustment` 三个函数）**零引用**——codegraph callers=0，grep `import stale_incremental_propagation` / `propagate_stale_by` 调用点=0（仅定义处）。该文件名字最像"stale 入口"，极易误导后人改联动逻辑时改错地方。

2. **分层不清**：stale 传播实际有多个入口并存且为**分层协作**（非重复），但缺权威说明：
   - `StalePropagationEngine.on_change`（`stale_propagation_engine.py`，336 行）：事件订阅的统一对外入口（被 `event_handlers` 订阅）。
   - `wp_formula_dependency.mark_stale_downstream`：仅被 `incremental_refresh` 调用（公式依赖层）。
   - `prefill_engine.mark_stale`：预填层。
   - 静态 `unified_dependency_graph.json` + 运行时图。

   新人改 stale 逻辑容易改错层。

> 注：写入路径收口（4 路径 → `WorkpaperSaveOrchestrator.after_save`）与孤立 EventBus 删除**已在 6-23 完成**（`single-source-cleanup`/`workpaper-save-orchestrator`），不在本 spec 范围。

## 目标

删除确认无引用的死代码模块，并产出一份 stale 传播分层说明，明确"唯一对外入口 + 各内部层职责 + 调用关系"，降低后续维护改错层的风险。

## 需求

### 需求 1：安全删除死代码

**用户故事**：作为维护者，我不希望仓库里存在零引用、名字却像核心入口的误导性模块。

#### 验收准则
1. WHEN 删除前 THEN SHALL 用 codegraph callers + grep（`import stale_incremental_propagation`、`propagate_stale_by_account|wp_code|adjustment`、动态 `getattr`/字符串分发）**三重确认零引用**。
2. IF 三重确认全部为零引用 THEN `stale_incremental_propagation.py` SHALL 被删除。
3. IF 发现任何动态/字符串引用 THEN SHALL 停止删除并在文档记录引用点，改为标注 `@deprecated` 而非删除。
4. WHEN 删除后 THEN 后端测试套件 SHALL 全绿（无 import 错误、无 collection 错误）。

### 需求 2：stale 传播分层文档

**用户故事**：作为新加入的开发，我需要一页文档就能知道"改 stale 逻辑该改哪个文件、入口是哪个"。

#### 验收准则
1. THE 一份文档（`backend/docs/STALE-PROPAGATION-LAYERS.md`）SHALL 说明：
   - 唯一对外入口 = `StalePropagationEngine.on_change`（谁订阅、何时触发）。
   - 各内部层职责：公式依赖层（`wp_formula_dependency`）、预填层（`prefill_engine`）、静态图（`unified_dependency_graph.json`）与运行时图的关系。
   - 一张调用关系图（文字/mermaid）。
   - "改 stale 行为应改哪一层"的决策指引。
2. THE 文档 SHALL 标注本次已删除的死代码，避免后人再创建同类。

### 需求 3：代码注释指引

#### 验收准则
1. THE `stale_propagation_engine.py` 顶部 SHALL 补注释，声明它是 stale 唯一对外入口，并指向分层文档。
2. THE `wp_formula_dependency.py` / `prefill_engine.py` 的 stale 相关函数 SHALL 补一行注释说明其为内部层、由谁调用。

## 非目标
- 不重构 stale 传播逻辑本身（仅删死代码 + 文档 + 注释）。
- 不动 `WorkpaperSaveOrchestrator`（已收口）。
- 不改 SSE/事件机制。
