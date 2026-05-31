# ADR-CONSOL-201: 重建统一编排者 cascade_refresh（填补被删的 orchestrator）

## 状态
已接受 (2026-05-30)

## 背景

合并"建树→worksheet→trial→report→notes"全链路无统一入口，散在各 router；`consolidation_orchestrator` 源码被删剩 stale pyc（C2）→ 编排层被抽空导致步骤散落、依赖顺序无保证（notes 依赖 report 依赖 trial 依赖 worksheet）。用户"一键刷新"诉求本质就是要这个编排者。

## 决策

新建 `consol_cascade_refresh_service.refresh_all(db, parent_project_id, year, progress_cb=None)` 作唯一编排入口：

- DAG 自底向上顺序恒定：`tree → worksheet → trial → reconcile → report → notes`（属性 S1）。
- 复用既有 service（build_tree / recalc_full / recalculate_trial / reconcile_worksheet_vs_trial / generate_consol_reports_sync / generate_full_consol_notes），**只编排不重写**。
- 失败隔离（属性 S2 / EH1）：每步 try/except 记 `errors[{step,node,error}]`；关键步（worksheet/trial）失败中断、下游步（reconcile/report/notes）失败记录后继续标部分成功。
- trial 步后统一 `await db.commit()` 一次（recalculate_trial 只 flush），确保 individual_sum/抵销落库供 report/notes 读取。
- `progress_cb(step, current, total, current_node, status)` 每步上报，worker 经 SSE 推进度。
- 既有单步 recalc 端点保留作细粒度入口（组合 vs 细粒度分工，R3）。

## 后果

- 正向：依赖顺序有保证 + 一键刷新有载体 + 重建 C2 被删编排层；幂等（S6，依赖 recalc_full/recalculate_trial 全量覆盖式重算）。
- 代价：与单步端点并存（R3，组合 vs 细粒度分工明确）。
- 守门：S1/S2/S6 由 `test_consol_phase2_cascade_pbt.py`（8 测试，mock 全部底层 service）验证编排器自身的顺序/隔离/确定性。
