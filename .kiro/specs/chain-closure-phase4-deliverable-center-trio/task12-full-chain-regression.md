# Task 12 — SQLite 真 ORM/文件故障全链回归（证据）

spec: `chain-closure-phase4-deliverable-center-trio`
需求：2.1–2.6, 3.1–3.6, 4.1–4.6, 5.1–5.6, 7.1–7.3
HEAD: `19c65589d`，分支 `work/2026-10-01-i-cycle-classification-convergence`

## 交付物

新增 `backend/tests/test_phase4_trio_full_chain_integration.py`（7 用例），**未改动任何生产代码**。
全链用**真实** `FullDeliverablesExecutor` / `ExportJobService` / `DeliverableService.render_and_store`
/ `DeliverableTrioSnapshot` / `DeliverableReadinessService` + 真实 ORM 行（SQLite 内存库）。
唯一替身是三件套渲染步骤的**导出器层**产确定性字节（真实 `ReportExcelExporter` /
`NoteWordExporter` 需完整项目报表/附注数据，属 Task 14/16 真项目/真浏览器范围）；替身之下的
`render_and_store → 落盘 → compute_file_fingerprint → create_version` 全是生产实现，
故障注入也注在导出器下一层（文件系统 / 指纹模块），不替换 `render_and_store` 本身
（`_assert_production_render_and_store` 守卫）。

## 用例清单

| 用例 | 覆盖 | 结论 |
|---|---|---|
| `test_full_chain_item_by_item` | 2.1–2.6/3.1–3.6/4.x/5.x | readiness(ready)→生成(第2步失败)→retry→三项成功，逐阶段比对 snapshot/文件/指纹 |
| `test_f1_write_failure_fail_closed` | 7.3 ①写失败 | fail-closed，无版本 |
| `test_f2_deleted_before_verify_fail_closed` | 7.3 ②删除 | fail-closed，无版本 |
| `test_f3_truncated_to_zero_fail_closed` | 7.3 ③截断 | fail-closed，无版本 |
| `test_f4_hash_mismatch_fail_closed` | 7.3 ④哈希不一致 | 统一 verify 抛 `file_hash_mismatch` |
| `test_f5_version_before_verify_fail_closed` | 7.3 ⑤版本先写 | 校验失败时 `create_version` 零调用 |
| `test_retry_without_recovery_still_fails` | 5.2/4.4 变异证明 | 故障未恢复 retry 后 job 不得 succeeded，trio_succeeded 仍=1 |

## 全链逐阶段对账（主用例）

- **阶段 0 readiness**：真实 `DeliverableReadinessService.check` 判定 `ready`，`hard_blockers==[]`，
  产出确定性 `snapshot.id`，`trio_status` 固定顺序 `financial_report→disclosure_notes→audit_report`。
- **阶段 1 生成（第 2 步失败）**：financial_report=succeeded（真落盘 1 版本，磁盘重算 sha256/size
  与版本记录逐一对账）；disclosure_notes=failed（无版本行，`render_and_store` 从未被调用，fail-closed）；
  audit_report=`blocked_by_dependency`；`trio_succeeded==1`；三项 item 绑定**同一** job snapshot_id
  （`verify_trio_shares_snapshot==True`）；失败 attempt append-only（trigger=initial，
  error_type=ValueError，diagnostic_detail.step=disclosure_notes）；job=partial_failed。
- **阶段 2 retry（恢复后）**：financial_report 复用不重跑（导出器调用次数不增、不新增版本行，需求 5.3）；
  disclosure_notes retry 真落盘（指纹对账）；audit_report 前置恢复后重跑成功；attempt=[1(initial,failed),
  2(retry,succeeded)]，原始失败原因未被洗（需求 5.4）。
- **阶段 3 完成**：job=succeeded，trio_succeeded==3；三项仍共享同一 snapshot（retry 未跨快照混用，
  需求 2.4/5.5）；三项文件各自存在、指纹与各自版本记录一致；三项 sha256 两两不同（三个独立交付物）。

### readiness 与 executor 快照 digest 不逐字节相等 — 已核实为设计意图，非 bug

初版曾断言 `result.snapshot_id == readiness.snapshot.id`，实测不等（`f075…` vs `20b7…`）。
核对两处生产实现：`DeliverableReadinessService._build_snapshot` 的 content 绑定
`tb_hash/formula_push_status/reports/notes/adjustments`；`FullDeliverablesExecutor._build_snapshot_input`
的 content 绑定 `template_type/report_scope/snapshot_refs`——**两个不同的内容构造函数**，二者
均用同一 `build_digest` 单一真源算法，但输入内容不同故 digest 不同。设计 §3.4/§4.2 与需求 1.5/2.4
的权威约束是「**三件套三项**引用同一 job 快照」+ 各自确定性，并未要求 readiness 预览摘要与 job
快照逐字节相等。故修正断言为：readiness 快照 digest 确定（同输入两次相同）+ 三项 item 绑定同一
job snapshot。**结论：无生产 bug，是测试初版过度断言，已改为验证规格真实要求的不变量。**

## 变异证明（非恒绿）

- `test_retry_without_recovery_still_fails`：故障**未恢复**就 retry ⇒ disclosure_notes 仍 failed、
  audit_report 仍 blocked、job 绝不被标 succeeded、trio_succeeded 仍=1；两次失败 attempt
  （initial+retry）均保留。证明「完成判据」依赖真实步骤成功，而非 retry 调用即变绿。
- 五类文件故障用例各自：故障被拦 ⇒ `platform_persist_failed=True` / 无版本行 / 下游 verify 抛明确
  code；F5 额外 spy `create_version` 断言零调用（版本先写后校验=fail-open 会打破此断言）。
- 既有 per-task 文件的 M1 变异（去掉 savepoint 泄漏半成品、只复位状态不建 attempt）继续守护底层不变量。

## 回归运行结果（本阶段引入 vs 预存红）

全部命令：Windows `python`，`;` 分隔，backend cwd=`..\.venv\Scripts\python.exe`，`-p no:cacheprovider`。

| 批次 | 命令范围 | 结果 | 归因 |
|---|---|---|---|
| 新全链文件 | `test_phase4_trio_full_chain_integration.py` | **7 passed** | 本阶段引入，全绿 |
| phase4 全量（含新文件） | 10 个 phase4 文件 | **90 passed**（83 旧+7 新） | 无跨文件干扰 |
| phase2 定向 | formula_push_engine/e1_binding + adj_formula_function/resolution | **144 passed** | 预存绿，未受影响 |
| phase3 定向 | audit_determination_writeback_integration/publish_to_tb_writeback_rows/full_deliverables_executor/deliverable_center_p0/deliverable_section_state_persist | **93 passed, 3 skipped** | 3 skip 为需 PG 环境（预期）|

### HEAD 预存红（与本阶段无关，不归因于 Task 12）

- `tests/test_deliverable_onlyoffice.py::test_property_54_onlyoffice_unavailable_degradation`：
  1 failed（ONLYOFFICE 环境 secret 缺失致降级断言失败）。属 HEAD 预存，与 phase4 全链无交集
  （我的新文件不触碰 onlyoffice 路径）。
- 全量 `pytest -k phase4` 收集阶段 7 个 collection error：`e2e/test_sign_convention_e2e.py` 与
  `playwright/test_wp_html_rendering_sample.py`（缺 `playwright.sync_api`）、
  `services/test_bulk_export_password_fail_closed.py`（缺 `pyzipper`）、
  `test_guidance_canonical_migration.py`/`test_guidance_render_identity.py`/
  `test_render_config_sheet_context.py`/`test_task_event_bus_idempotency_auth.py`（已知 import 漂移）。
  均为缺依赖 / 已知 import 漂移的 HEAD 预存环境红，与本阶段无关；故 Task 12 回归一律**按文件逐一指定**
  规避被破坏的全量 collection。
- 任务上下文列出的 `test_onlyoffice_disabled_without_secret` / `test_onlyoffice_word_template_callback`
  / `test_service_call_wiring_integrity`（wp_guidance_chat）亦为 HEAD 预存红，Task 12 不涉及。

## 边界说明

- SQLite 真 ORM 层已通过；真 PG 临时 schema（Task 13）与真实项目 dry-run（Task 14）、Playwright
  （Task 15）、真实出具写库（Task 16）仍按 `[ ]*` / `[~]` 保留，需 PG/浏览器环境与用户授权。
- 本任务**未改动生产代码**（全链未暴露真实集成 bug，只修正了测试初版的过度断言）。
