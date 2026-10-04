# Task 2 readiness 基线与硬/软闸门（交付证据）

> spec: `chain-closure-phase4-deliverable-center-trio` / 任务 2。append-only。
> 基线：HEAD `19c65589d`，分支 `work/2026-10-01-i-cycle-classification-convergence`，最高迁移 V179。

## 一、交付物

- 生产：`backend/app/services/deliverable_readiness_service.py`（新增，纯只读判定服务）。
- 测试：`backend/tests/test_phase4_readiness_gates.py`（新增，SQLite 真 ORM，16 用例）。

## 二、`DeliverableReadinessService.check` 真读取的来源（需求 1.1/1.4）

只读项目**审计年度**（显式 `year` 入参）下：

| 来源 | 真字段判据（非「有行就算完成」） |
|---|---|
| 试算表 TB | 行数 > 0 **且** 无 `audited_amount IS NULL`（审定数由发布门单一写入方维护） |
| 公式推送 | 最近一次 `FormulaPushRun.status`：`failed`→硬阻断，`partial`→软 warning，`succeeded`→过 |
| 调整确认 | 无 `review_status IN (draft, pending_review)` 的未删除分录 |
| 报表 | `FinancialReport` 行数 > 0 **且** 无 `is_stale=True` |
| 附注交接 | `DeliverableSectionState` 章节数 > 0 **且** 无 `is_stale=True` |
| 快照一致性 | 复用 `DeliverableSnapshotService.check_trio_consistency`（三件套绑定同一 tb_hash） |
| 项目身份 | `template_type` + `accounting_standard_id` + 年度（`audit_year`/`audit_period_end`）可唯一确定 |
| 既有文件 | 三件套最新版本 `file_path`：存在/是文件/大小>0/`file_hash` 匹配（`include_file_checks=True`） |

## 三、硬闸门（blocker）/ 软闸门（warning）分离（需求 1.2/1.3）

- 硬 code：`upstream_not_ready` / `stale_source` / `snapshot_inconsistent` /
  `missing_template_or_standard` / `missing_file` / `unreadable_file` / `file_hash_mismatch`。
  按稳定 code **去重**（同 code 仅首条，其余并入 `evidence.duplicates`）。
- 软 code：`formula_push_partial`（部分成功提醒）。
- 每条闸门都带：稳定 `code` + 中文 `message` + `evidence`（不含本机绝对路径）。
- 状态聚合：有硬闸门 → `blocked`；无硬闸门但有 warning → `ready_with_warnings`；全无 → `ready`。
  软 warning **不改变** `blocked`/`ready` 以外的成功判定，也不被 blocker 覆盖。

## 四、phase3 未在 HEAD 的能力 fail-closed（需求 1.2 第 1 项 / design §一）

`_REQUIRED_PHASE3_MODULES` 探测 `app.services.formula_push.engine`（公式推送引擎）与
`app.services.deliverable_section_state_service`（附注章节交接）。任一 `find_spec` 失败 →
`upstream_not_ready` 硬阻断，而非默默放行。**当前 HEAD 两模块均可导入**（真实状态），
故能力探测不产生 blocker；后续能力若回退则自动阻断。

## 五、快照摘要（需求 1.5 / design §3.4）

`_build_snapshot` 对规范化 JSON（项目/年度/准则/模板/report_scope/tb_hash/推送状态/报表/
附注/调整摘要）取 sha256 作 `id`=`digest`。**不含生成时间与本机绝对路径** ⇒ 同一输入两次
digest 相同（`test_snapshot_digest_excludes_time_and_abs_path` 守护）。

## 六、测试结果与变异证明

命令：`..\.venv\Scripts\python.exe -m pytest tests/test_phase4_readiness_gates.py -q`
（cwd=backend）。结果：**16 passed**。

- 基准绿：完全就绪项目 → `ready`，字段齐全（hard_blockers/warnings/trio_status/snapshot_id/sources）。
- 硬闸门变异证明（数据级）：每个闸门先造触发条件断言 blocker 出现，再复位断言 blocker 消失
  （证明闸门依条件判定，不是恒亮）：审定数缺失 / 推送 failed / 未复核调整 / 报表 stale /
  附注 stale / 准则模板缺失 / 快照不一致。
- 硬闸门变异证明（代码级，已验证并回退）：把 `stale_source` 报表闸门改成 `if stale > 0 and False`
  后，`test_stale_report_blocks` 与 `test_warning_coexists_with_blocker_without_masking`
  **双双变红**（`assert 'stale_source' in set()` / `'ready_with_warnings' == 'blocked'`），
  证明「删掉任一硬闸门必须红」。改回后恢复 16 passed。
- 软 warning 反向样本（必须绿）：`test_partial_formula_push_is_warning_not_blocker` —
  推送 partial 时 `status=ready_with_warnings`、`hard_blockers=[]`，软 warning 不阻断。
- 空项目：多来源都触发 `upstream_not_ready` 但去重为一条，其余入 `duplicates` 证据。

## 七、与基线红的关系

`backend/tests/test_phase4_trio_baseline_red.py` 的 5 条仍为**预期红**（Task 4/5/7 目标：
`render_and_store` fail-closed、`ExportJobAttempt` 模型、`TRIO_STEPS` 常量），本任务未触碰，
与 `baseline-task1.md` 一致。

## 八、范围说明

- 任务文本的「TestClient」部分依赖 readiness HTTP 端点，端点与 `router_registry` 登记在
  **Task 9**（design §4.4）；本任务交付纯判定 service + SQLite 真 ORM 全闸门覆盖与变异证明。
- 服务只读，不 flush/commit；无 PG-only SQL（SQLite/PG 同款查询）。
