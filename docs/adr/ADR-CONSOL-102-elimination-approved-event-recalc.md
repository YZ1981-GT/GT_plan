# ADR-CONSOL-102: 抵销消费统一为 APPROVED + 事件驱动重算

## 状态
已接受 (2026-05-31)

## 背景

衔接2 口径不一致：`consol_worksheet_engine` 的 `_get_elimination_map` / `_batch_load_eliminations` 消费**全部** `EliminationEntry`（仅 `is_deleted` 过滤），而 `consol_trial_service.recalculate_trial` 只消费 `review_status == approved`。两条计算路径口径不同，是 Phase 0 B2 对账 diff 的根因之一。

实证发现潜伏 bug：`ReviewStatusEnum` 仅定义小写成员（`draft/pending_review/approved/rejected`），但 `elimination_service.py`（6 处）+ `consol_trial_service.py`（1 处）误用大写 `.APPROVED/.DRAFT/...` → 运行时 `AttributeError`（因 0 PG consolidated 项目链路从未端到端跑而未暴露）。

## 决策

1. **统一只认 `review_status == approved`**：`consol_worksheet_engine._get_elimination_map` + `_batch_load_eliminations` 加 `review_status == ReviewStatusEnum.approved` 过滤，与 trial 对齐（draft 不进合并数）。
2. **修复大小写潜伏 bug**：全仓 `ReviewStatusEnum.{APPROVED,DRAFT,PENDING_REVIEW,REJECTED}` → 小写成员（触类旁通一次修完 7 处）。
3. **事件驱动重算**：`EventType` 新增 `ELIMINATION_APPROVED`；抵销审批端点（`POST /api/consolidation/eliminations/{id}/review`，action=approve）审批落库 + 留痕后发 `ELIMINATION_APPROVED` 事件（含 project_id/year）。
4. **handler**：新增 `consol_elimination_recalc_handler`，订阅 `ELIMINATION_APPROVED` → 触发 `recalc_full(worksheet)` + `recalculate_trial`（幂等：全量重算覆盖写）。

## 后果

- worksheet 与 trial 消费的抵销集合相同（均 approved），Phase 0 B2 对账 diff 收窄（Q3）。
- 审批后自动重算，无需手动触发（Q4 幂等）。
- **重算与审批解耦**：审批同步落库（含审计留痕），重算为下游派生；重算失败记 error 不阻断审批（EH3）。
- 口径变更（draft 不再进合并数）属预期修正，需通知用户（R3）。
