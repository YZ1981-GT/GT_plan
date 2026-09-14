# Stale 传播死代码清理 + 分层文档 — Tasks

- [x] 1. 三重确认 `stale_incremental_propagation.py` 零引用：codegraph callers + grep（import / 调用点 / 动态分发 getattr+字符串）
  - 需求 1
  - 产物：确认结果记入 design 或 PR 描述

- [x] 2. 确认零引用后删除 `backend/app/services/stale_incremental_propagation.py`（若发现引用则改 @deprecated 并记录）
  - 文件：`backend/app/services/stale_incremental_propagation.py`
  - 需求 1

- [x] 3. 删除后跑 `pytest backend/tests --co -q` 无 collection error + stale/linkage 域测试全绿
  - 需求 1
  - 命令：`rtk python -m pytest backend/tests -k "stale or linkage" -q`（cwd 视项目根）

- [x] 4. 编写 `backend/docs/STALE-PROPAGATION-LAYERS.md`：唯一入口 + 各层职责表 + mermaid 调用图 + 决策指引 + 已删死代码记录
  - 文件：`backend/docs/STALE-PROPAGATION-LAYERS.md`
  - 需求 2

- [x] 5. 补注释：`stale_propagation_engine.py` 顶部声明唯一入口指向文档；`wp_formula_dependency.mark_stale_downstream` + `prefill_engine.mark_stale` 标注内部层
  - 需求 3

- [x]* 6. 更新 `docs/平台全局体验与一致性建议.md` §3.5 与 §7.2 标记死代码已删、分层已文档化
