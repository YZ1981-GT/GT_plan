# workpaper-fill-service-split — workpaper_fill_service.py 拆分（1587→拆 4）

> 起草日期：2026-05-28
> 触发：底稿模块复盘（V3 spec gaps.md §B/G + memory.md 超级 SFC 风险铁律）
> 工时：2 工作日
> 优先级：**P1**

## 触发问题

`backend/app/services/workpaper_fill_service.py` = **1587 行**，是 backend 51 个 wp 服务里最大的文件，涵盖：

- 6 个 prefill 函数 dispatcher（`=TB / =AUX / =PRIOR / =ROW / =SUM / =CELL`）
- DSL 公式解析（tokenize → AST → 评估）
- cell writeback（含 manual_override + audit log）
- snapshot diff（与上次预填充对比）
- 跨循环依赖（如 H1-12 折旧 → K11 减值汇总）

风险：任何 prefill 函数加新公式 = 改 1587 行的文件 = 风险高。

## 拆分方案

| 新文件 | 职责 | 估行 |
|---|---|---|
| `wp_prefill_engine.py` | 6 函数纯 dispatcher（`=TB/=AUX/=PRIOR/=ROW/=SUM/=CELL`） | ≤ 500 |
| `wp_formula_parser.py` | DSL 解析 + AST + 评估（无副作用） | ≤ 400 |
| `wp_cell_writeback.py` | cell 写回 + manual_override + audit log | ≤ 350 |
| `wp_snapshot_diff.py` | snapshot 对比 + stale 计算 | ≤ 350 |

合计 ≤ 1600 行，**单文件 ≤ 500**。`workpaper_fill_service.py` 退化为 ≤ 50 行 facade（向后兼容入口）。

## 不在范围

- 修改 prefill 业务逻辑（仅做 service 拆分）
- 改 DB schema / migration
- 改前端调用入口

## 验收

- 4 个新 service 单测覆盖率 ≥ 95%
- pytest backend/tests/services/test_workpaper_fill* 全绿
- 现有调用方（`router_registry/prefill.py` / `audit_chain_orchestrator.py` / `wp_cross_check_service.py`）零改动通过
- 性能基准：YG2101 65 万行场景 prefill 耗时 ≤ baseline + 10%（防拆分引入间接调用 overhead）

## Sprint 划分（2 天）

| Sprint | 工时 | 内容 |
|---|---|---|
| 0. 准备 | 0.3 天 | 静态依赖图 + 找 import 调用方 + 现有 pytest 基线 |
| 1. wp_formula_parser 拆出 | 0.5 天 | 纯函数最容易，先做 |
| 2. wp_cell_writeback 拆出 | 0.5 天 | manual_override 守卫 + audit log |
| 3. wp_snapshot_diff 拆出 | 0.4 天 | snapshot 对比 |
| 4. wp_prefill_engine + facade | 0.3 天 | 主 dispatcher + 旧 fill_service 退化为 facade |

下一步：触发时起完整 requirements + design + tasks 三件套。
