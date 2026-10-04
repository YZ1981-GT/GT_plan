# Task 18 — 收尾与追溯（交付证据）

> spec `chain-closure-phase4-deliverable-center-trio`，需求 7.7 / 8.1–8.4。
> 分支 `work/2026-10-01-i-cycle-classification-convergence`。
> append-only。本任务为**入库提交 + clean HEAD 复验 + 追溯登记**，承接 Task 17 归因报告。

## 一、HEAD 并发核验

- 提交前 `git rev-parse HEAD = 19c65589d02aa6f977548cd4f3be2f2bba6b0b89`，与 Task 17 基线一致，**未并发移动**。
- 全程未改 git config、未 force push / reset --hard、未 `--no-verify`、未 `git add -A`。
- 并行工作树 `D:/GT_plan_ip_wt`（detached `8c1a94e43`，他人）全程未触碰。

## 二、提交策略与内容（specific-file staging）

**提交 1：`e3ea78a9bdcc8b73765a6bb67a20ba8e9e58259e`（52 文件，10915 insertions / 171 deletions）**

按 specific-file 方式逐组 `git add`，**未用 `git add -A`**。暂存前对新建生产模块/迁移/前端做了 secret 扫描（password/secret/token/private key/AKIA/BEGIN —— 均无命中）。

| 类别 | 文件 |
|------|------|
| 生产·服务（新建·曾未跟踪） | `deliverable_readiness_service.py` / `deliverable_trio_snapshot.py` / `deliverable_file_fingerprint.py` |
| 生产·路由（新建·曾未跟踪） | `routers/deliverable_trio.py` |
| 迁移（新建·曾未跟踪） | `V180__deliverable_trio_attempt_and_snapshot.sql` / `R180__...sql` |
| 生产·已改（fail-closed 消费方 + 编排 + 模型 + 注册） | `full_deliverables_executor.py` / `export_job_service.py` / `deliverable_service.py` / `routers/word_export.py` / `routers/deliverable.py` / `router_registry/report.py` / `models/phase13_models.py` / `models/phase13_schemas.py` / `deliverable_center_integration.py` / `deliverable_refresh_service.py` / `onlyoffice_callback_service.py` / `template_fill_service.py` |
| 前端（新建 + 已改） | `TrioRetryPanel.vue` + `__tests__/TrioRetryPanel.spec.ts` / `tsconfig._phase4-trio.json` / `deliverableApi.ts` / `apiPaths/report.ts` / `DeliverableCenter.vue` / `components.d.ts` |
| 测试（11 个 phase4 + 2 个既有回归） | `test_phase4_trio_baseline_red` / `_readiness_gates` / `_trio_snapshot_schema` / `_file_fingerprint_fail_closed` / `_trio_executor_order` / `_trio_savepoint_isolation` / `_trio_attempt_history` / `_trio_retry_reexecute` / `_trio_endpoints_authz` / `_trio_full_chain_integration` / `_trio_pg_transaction_rollback` + `test_deliverable_center_p0.py` / `test_full_deliverables_executor.py` |
| spec 文档 | `baseline-task1.md` / `task2..task9` / `task11..task13` / `task17-clean-head-attribution.md` / `tasks.meta.json` |

**刻意排除（未暂存）**：

- `.agents/tasks/checksum-drift-8/*`（并行任务产物，与 phase4 无关）。
- `audit-platform/frontend/src/auto-imports.d.ts`（`git diff --numstat` 无内容差异，仅行尾归一化 warning，无实义改动）。
- `tasks.md`（进入提交 2，待 clean HEAD 复验通过后再翻 17/18 状态）。

🔴 **比 Task 17 清册多出的 5 处 fail-closed 消费方**：`routers/deliverable.py`、`deliverable_center_integration.py`、`deliverable_refresh_service.py`、`onlyoffice_callback_service.py`、`template_fill_service.py`。它们都是需求 3.1 的 `render_and_store` 返回 `version=None`（落盘/校验失败）后的判空消费方——漏提交任一处，则「文件未落盘」仍会按成功返回版本号/下载链接或伪造 EvidenceRef（即"平台持久化失败仍伪成功"）。已随本提交一并入库。

## 三、clean HEAD 复验（这是 Task 17 得以勾选的依据）

`git worktree add --detach D:/GT_plan_phase4_verify e3ea78a9b…`（在**新提交**上建全新检出）。

⚠️ 复验须用**主仓绝对 venv 路径** `D:\GT_plan\.venv\Scripts\python.exe`——worktree 内相对 `..\.venv` 不存在。

| 命令（clean worktree `backend/`） | 结果 |
|------|------|
| `python -c "import full_deliverables_executor; router_registry.report; deliverable_service; routers.deliverable_trio; deliverable_trio_snapshot; deliverable_file_fingerprint; deliverable_readiness_service"` | **ALL IMPORTS OK**（曾在 clean HEAD 顶层 import 断链，现解除） |
| `pytest` 10 个 SQLite phase4 测试（显式枚举，避免无关 collection error） | **90 passed**（195.98s） |
| `pytest test_phase4_trio_pg_transaction_rollback.py` | **6 passed**（4.22s，真 PG） |

合计 **96 passed**（90 SQLite + 6 PG）**在全新 clean 检出上**，证明「代码正确且已入库」，不再是「只在工作树绿」。worktree 已 `git worktree remove --force` 清理，`git worktree list` 复查仅剩主树 + 他人 `GT_plan_ip_wt`。

## 四、一次性探针清理（步骤 4）

现扫确认 **phase4 本阶段无一次性探针残留**：`git status` 无 `_*.py` / `_*.txt` 未跟踪产物（`.venv` 内第三方 `_trio*` 命中不计）。`backend/scripts/analyze/_hr_*` 四个探针属**并行任务**（时间戳 2026-10-03，J/人力循环），**未触碰**。

## 五、追溯登记（步骤 5/6）

- **INDEX.md**：`chain-closure-phase4-deliverable-center-trio` 进度 `0/18 未实施` → **`16/18`（实施完成；余 14/15/16 `[ ]*` 外部依赖未做）**，描述补 Task17 归因 + 提交号 + clean HEAD 复验 + 交付分级。编辑经 `read_bytes().decode()`，复查**纯 CRLF 不变**（1031 CRLF / 0 bare LF）、该行恰 4 个未转义 pipe。phase2(`17/18`)、phase3(`0/19`) 条目**未改动，仍如实未完成**。
- **memory.md**：追加 `chain-closure-phase4` 小节（交付分级 + Task17 归因教训），文件 **199 行 ≤ 200**。

## 六、交付文案分级（需求 8.1–8.4，不得混用）

| 等级 | 覆盖范围 | 本阶段对应 |
|------|---------|-----------|
| **已通过 SQLite/PG** | 真 ORM + TestClient / 真 PG 临时 schema 跑绿 | T2–T13 全部（readiness/snapshot/fingerprint/executor/savepoint/attempt/retry/端点鉴权/前端/全链回归/PG 回滚） |
| **已通过 clean HEAD** | 产物已入库，全新检出 import + 定向测试转绿 | 提交 `e3ea78a9b` + 本任务复验 96 passed |
| **代码已改但未实测** | （本阶段无此类——所有已勾项都有 SQLite/PG + clean HEAD 证据） | 无 |
| **已获授权真浏览器出具** | 用户明确授权后真实写库 / Playwright 真浏览器 | **T14 / T15 / T16 均未达此级 ⇒ 保持 `[ ]*`** |

🔴 **T14（真实项目事务 dry-run）/ T15（Playwright 真浏览器）/ T16（授权真实出具写库）= 外部依赖未做**，依赖「可连接真实项目环境 + 用户明确授权真实写库」，**不以 SQLite 通过或 HTTP 200 冒充生产交付**。

## 七、Task 17 可勾选结论

Task 17 的唯一阻断条件是「模块未跟踪 / 只在工作树绿」。本任务提交 `e3ea78a9b` 把 §2.1 全部曾未跟踪产物 + 已改消费方一并入库，并在**全新 clean worktree** 复跑 96 passed 转绿 ⇒ **阻断条件已解除**。据此 Task 17 由 `[-]` 翻 `[x]`，Task 18 同步翻 `[x]`。

## 八、安全与收尾复查

- HEAD 提交后 = `e3ea78a9b`；仅创建 1 个代码提交 + 1 个收尾提交（tasks.md/INDEX/memory/本文档），**未 push**（未被要求）。
- 无 secret 入库（暂存前已扫）。未改 git config，未 force push / reset。
- 临时 worktree 已清理。
