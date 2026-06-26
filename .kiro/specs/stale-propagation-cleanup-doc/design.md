# Stale 传播死代码清理 + 分层文档 — Design

## 设计原则

ponytail 第 1 步「需要存在吗」：死代码不需要存在 → 删；分层文档是低成本高收益的可维护性投资。本 spec 不改任何运行逻辑。

## 删除流程（需求 1，安全第一）

```
1. codegraph callers 三函数 → 确认 0
2. grep 全仓库：
   - import stale_incremental_propagation
   - from .* import propagate_stale_by_account|wp_code|adjustment
   - propagate_stale_by_  (调用点，排除定义文件本身)
   - getattr.*propagate_stale / "propagate_stale_by  (动态/字符串分发)
3. 全部为 0 → 删除文件
   任一非 0 → 不删，记录引用点，改 @deprecated
4. 删除后跑后端测试：pytest --co（collection 不报错）+ 受影响域测试
```

## stale 传播分层（文档化对象）

实际架构（基于 codegraph callers 实证）：

```
事件 (WORKPAPER_SAVED 等)
        │
        ▼
event_handlers.py  ──subscribe──►  StalePropagationEngine.on_change   ◄── 唯一对外入口
                                          │ _mark_stale_by_uri
                                          │ _fallback_mark_stale
                          ┌───────────────┼────────────────┐
                          ▼               ▼                ▼
                  公式依赖层          预填层           静态/运行时图
            wp_formula_dependency   prefill_engine   unified_dependency_graph.json
            .mark_stale_downstream  .mark_stale      （build 时加载）
            （由 incremental_refresh 调用）
```

文档 `backend/docs/STALE-PROPAGATION-LAYERS.md` 内容大纲：
1. **一句话**：改 stale 行为，先看本图定位层，唯一对外入口是 `StalePropagationEngine.on_change`。
2. **各层职责表**（入口/被谁调用/负责什么）。
3. **mermaid 调用图**（同上）。
4. **决策指引**：
   - 改"某事件该不该触发 stale" → event_handlers 订阅处。
   - 改"地址 URI → 哪些行变 stale" → StalePropagationEngine。
   - 改"公式上下游依赖" → wp_formula_dependency。
   - 改"预填字段 stale" → prefill_engine。
5. **已删除死代码记录**：`stale_incremental_propagation.py`（86 行，零引用，2026-06-23 删），勿重建。

## 注释指引（需求 3）

- `stale_propagation_engine.py` 顶部 docstring：声明"stale 唯一对外入口，详见 backend/docs/STALE-PROPAGATION-LAYERS.md"。
- `wp_formula_dependency.mark_stale_downstream` / `prefill_engine.mark_stale`：补一行"内部层，由 X 调用，勿作为对外入口"。

## 测试策略

- 删除后：`pytest backend/tests --co -q` 无 collection error；跑 stale/linkage 相关测试全绿（`test_stale_*`、`test_detect_stale_*`、`test_report_stale_*`、`test_cycle_linkage_*`）。
- 无新增测试逻辑（纯删除 + 文档），但需确认现有 stale 测试覆盖未因删除受影响。
- 文档为人读，不需测试；mermaid 语法可本地预览确认。

## 风险与缓解
- **风险**：存在动态字符串分发未被 grep 命中 → 缓解：grep 覆盖 `getattr`/字符串字面量两种动态模式；删后跑全量 collection + stale 域测试兜底。
- **风险**：删错文件 → 缓解：仅删确认零引用的 `stale_incremental_propagation.py` 单文件，不碰 `stale_propagation_engine.py`（336 行，真入口）。
