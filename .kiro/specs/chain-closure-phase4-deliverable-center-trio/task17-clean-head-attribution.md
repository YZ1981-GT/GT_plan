# Task 17 — clean HEAD 对照与冲突归因（交付证据）

> spec `chain-closure-phase4-deliverable-center-trio`，需求 7.7 / 8.1 / 8.4。
> 分支 `work/2026-10-01-i-cycle-classification-convergence`，基线 HEAD `19c65589d`。
> append-only。本任务为**调查 + 归因报告**，不新增生产代码、不提交（提交归 Task 18）。

## 一、任务定位与结论

本任务核验「已交付」是否真的「在库」，并用 clean HEAD 临时 worktree 做三桶归因。

**核心结论（🔴 本任务不得勾选 `[x]`，只能标 `[-]` 进行中）**：

> **phase4 三件套的全部核心产物当前完全不在 HEAD。** 生产模块、迁移、11 个 phase4 测试、
> 前端组件、以及对已有文件的 phase4 改动——**无一进入 commit `19c65589d`**，全部停留在未提交工作树。
> 本地 `pytest` 全绿（46 passed）**只因未跟踪模块本地存在**；clean HEAD 检出（CI / 新 clone /
> 容器）会在 **import 期**炸（`full_deliverables_executor.py` 顶层 import 未跟踪模块）或测试文件
> 根本不存在（pytest exit 4）。这正是 steering 铁律「已交付 ≠ 在库」要求必须拦截的形态。

任务判定三条红线逐条命中其一即不得勾选：

| 红线 | 现状 | 命中 |
|------|------|------|
| 冲突未清 | 无合并冲突 | 否 |
| **模块未跟踪** | **4 个生产模块 + 2 迁移 + 11 测试 + 前端 3 文件全未跟踪** | **是 🔴** |
| 只在工作树绿 | 主树 46 passed，clean HEAD import 炸 / 测试缺失 | **是 🔴** |

⇒ 本项标 `[-]`，交由 Task 18 决定提交策略（stage specific files，不 `git add -A`）。

## 二、git-tracked 覆盖核验（`git ls-files` / `git status`）

HEAD 核验：任务开始 `git rev-parse HEAD = 19c65589d02aa6f977548cd4f3be2f2bba6b0b89`，
全程及收尾复查**未移动**；并行存在 `D:/GT_plan_ip_wt`（detached 8c1a94e43，他人工作树，未触碰）。

### 2.1 phase4 新建产物 —— 全部 UNTRACKED（`git status` 标 `??`，`git ls-files` 返空）

| 类别 | 文件 | 跟踪状态 |
|------|------|---------|
| 生产·服务 | `backend/app/services/deliverable_readiness_service.py` | ❌ 未跟踪 |
| 生产·服务 | `backend/app/services/deliverable_trio_snapshot.py` | ❌ 未跟踪 |
| 生产·服务 | `backend/app/services/deliverable_file_fingerprint.py` | ❌ 未跟踪 |
| 生产·路由 | `backend/app/routers/deliverable_trio.py` | ❌ 未跟踪 |
| 迁移 | `backend/migrations/V180__deliverable_trio_attempt_and_snapshot.sql` | ❌ 未跟踪 |
| 迁移 | `backend/migrations/R180__rollback_deliverable_trio_attempt_and_snapshot.sql` | ❌ 未跟踪 |
| 前端 | `audit-platform/frontend/src/components/deliverable/TrioRetryPanel.vue` | ❌ 未跟踪 |
| 前端 | `.../deliverable/__tests__/TrioRetryPanel.spec.ts` | ❌ 未跟踪 |
| 前端 | `audit-platform/frontend/tsconfig._phase4-trio.json` | ❌ 未跟踪 |
| 测试 | `backend/tests/test_phase4_trio_baseline_red.py` | ❌ 未跟踪 |
| 测试 | `backend/tests/test_phase4_readiness_gates.py` | ❌ 未跟踪 |
| 测试 | `backend/tests/test_phase4_trio_snapshot_schema.py` | ❌ 未跟踪 |
| 测试 | `backend/tests/test_phase4_file_fingerprint_fail_closed.py` | ❌ 未跟踪 |
| 测试 | `backend/tests/test_phase4_trio_executor_order.py` | ❌ 未跟踪 |
| 测试 | `backend/tests/test_phase4_trio_savepoint_isolation.py` | ❌ 未跟踪 |
| 测试 | `backend/tests/test_phase4_trio_attempt_history.py` | ❌ 未跟踪 |
| 测试 | `backend/tests/test_phase4_trio_retry_reexecute.py` | ❌ 未跟踪 |
| 测试 | `backend/tests/test_phase4_trio_endpoints_authz.py` | ❌ 未跟踪 |
| 测试 | `backend/tests/test_phase4_trio_full_chain_integration.py` | ❌ 未跟踪 |
| 测试 | `backend/tests/test_phase4_trio_pg_transaction_rollback.py` | ❌ 未跟踪 |
| spec 文档 | `baseline-task1.md`、`task2..task13-*.md`、`tasks.meta.json` | ❌ 未跟踪 |

`git ls-files` 对上述 8 个核心（4 服务/路由 + 2 迁移 + 2 前端）**全部返回空字符串**，坐实未入库。

### 2.2 phase4 改动的已有文件 —— TRACKED，但改动只在工作树（`M`），HEAD 版本无 phase4 引用

| 文件 | `git ls-files` | HEAD 版本是否含 phase4 引用 |
|------|---------------|---------------------------|
| `backend/app/router_registry/report.py` | ✅ 跟踪 | **否**（`git show HEAD:` grep `deliverable_trio` 空） |
| `backend/app/services/full_deliverables_executor.py` | ✅ 跟踪 | **否**（grep `deliverable_trio_snapshot` 空） |
| `backend/app/services/deliverable_service.py` | ✅ 跟踪 | **否**（grep `deliverable_file_fingerprint` 空） |
| `backend/app/services/export_job_service.py` | ✅ 跟踪 | 改动在工作树 `M` |
| `backend/app/models/phase13_models.py` / `phase13_schemas.py` | ✅ 跟踪 | 改动在工作树 `M` |
| `backend/app/routers/word_export.py` | ✅ 跟踪 | 改动在工作树 `M` |
| 前端 `deliverableApi.ts` / `apiPaths/report.ts` / `DeliverableCenter.vue` / `components.d.ts` / `auto-imports.d.ts` | ✅ 跟踪 | 改动在工作树 `M` |

🔴 **断链证据**：工作树的 `full_deliverables_executor.py:32` 为**模块顶层** import
`from app.services.deliverable_trio_snapshot import (TRIO_STEP_KEYS, DeliverableTrioSnapshot, build_digest)`，
而 `deliverable_trio_snapshot.py` 未跟踪；`router_registry/report.py:48` import `deliverable_trio`（未跟踪）；
`deliverable_service.py` 惰性 import `deliverable_file_fingerprint`（未跟踪）。
⇒ 一旦 Task 18 只提交「改动的已有文件」而漏掉这 4 个未跟踪模块，clean HEAD 立即 import 崩。

### 2.3 跟踪方被未跟踪模块 import 的清单（steering 要求显式报告）

- `router_registry/report.py`（tracked, 工作树改动）→ import `app.routers.deliverable_trio`（untracked）
- `full_deliverables_executor.py`（tracked, 工作树改动，**顶层** import）→ `app.services.deliverable_trio_snapshot`（untracked）
- `deliverable_service.py`（tracked, 工作树改动，惰性 import）→ `app.services.deliverable_file_fingerprint`（untracked）
- `deliverable_trio.py`（untracked）→ `deliverable_readiness_service` / `export_job_service` / `full_deliverables_executor` / `deliverable_file_fingerprint`
- `deliverable_readiness_service.py`（untracked）→ `deliverable_file_fingerprint` / `deliverable_trio_snapshot`（均 untracked）

### 2.4 同名干扰项排除

`backend/tests/test_phase4_pbt.py` **是跟踪的**（commit `03f295427`「C~S循环底稿全量…」），
但它是 RLS 隔离性 + YoY 边界的既有 PBT，**与本 phase4 三件套无关**，仅共享 `phase4` 名前缀。
不计入本链产物。

## 三、clean HEAD 临时 worktree 对照

`git worktree add --detach D:/GT_plan_phase4_cleanhead 19c65589d…`（HEAD 快照，非破坏性）。

### 3.1 产物在 clean HEAD 的存在性 —— 全部缺失

clean HEAD worktree 下 `Get-ChildItem` 四服务/路由模块、11 测试、V180/R180 迁移 —— **全部不存在**（空输出）。

### 3.2 相同定向命令运行结果

| 命令（在 clean HEAD worktree） | 结果 | 归因 |
|------|------|------|
| `pytest tests/test_phase4_trio_full_chain_integration.py tests/test_phase4_readiness_gates.py` | **ERROR: file or directory not found** + `collected 0 items` + **exit 4** | 测试文件不在 HEAD |
| `python -c "import app.services.full_deliverables_executor; import app.router_registry.report; import app.services.deliverable_service"` | **三者 import OK, exit 0** | HEAD 版本不含 phase4 改动，故不触发断链 |

### 3.3 主工作树对照（证明「只在工作树绿」）

| 命令（主工作树 `d:\GT_plan\backend`） | 结果 |
|------|------|
| `python -c "import app.services.full_deliverables_executor; import app.routers.deliverable_trio"` | **OK, exit 0**（未跟踪模块本地存在故不炸） |
| `pytest readiness_gates + executor_order + file_fingerprint + endpoints_authz` | **46 passed**（代码正确，问题纯粹是未入库） |

## 四、三桶归因（需求 7.7）

| 桶 | 定义 | 本次结果 |
|----|------|---------|
| **HEAD 预存红** | commit `19c65589d` 自身在 clean worktree 跑定向命令就红 | **0**。HEAD 版三模块 import 全绿；phase4 测试在 HEAD 不存在（exit 4 属「文件缺失」非「预存失败」）。 |
| **并行未提交红** | 他人未提交工作（如 `GT_plan_ip_wt`）造成的红 | **0 可归因**。本任务只跑 phase4 定向命令，未触碰并行工作树；未发现并行改动污染 phase4 定向集。 |
| **本阶段引入红** | phase4 本阶段改动在 clean HEAD 的表现 | **全部**。根因**不是代码错误**（主树 46 passed），而是**未入库**：核心模块/测试/迁移/前端全未跟踪 ⇒ clean HEAD import 期崩 + 测试缺失。 |

**一句话归因**：本阶段 0 预存红、0 并行红；clean HEAD 的全部红来自「phase4 产物未进入 HEAD」这一**跟踪缺口**，而非逻辑缺陷。修复动作是「把 4 个未跟踪生产模块 + 2 迁移 + 11 测试 + 前端 3 文件 + 已改已有文件一并、按 specific-file 方式提交」（Task 18）。

## 五、安全与收尾

- HEAD SHA 开始/结束均为 `19c65589d02aa6f977548cd4f3be2f2bba6b0b89`，**无并发移动**。
- **未执行任何 `git add` / commit**（本任务是归因报告；提交策略归 Task 18，须 stage specific files，禁 `git add -A`，不覆盖他人暂存）。
- 临时 worktree 已 `git worktree remove --force` 清理；`git worktree list` 复查仅剩主树 + 他人 `GT_plan_ip_wt`（未触碰）。
- 未修改 git config，未 force push / reset --hard。

## 六、给 Task 18 的交接要点

1. 提交必须包含 §2.1 全部 untracked 产物（否则 clean HEAD 仍断链）——尤其 `deliverable_trio_snapshot.py`（被顶层 import）、`deliverable_file_fingerprint.py`、`deliverable_readiness_service.py`、`deliverable_trio.py`。
2. 同批提交 §2.2 已改已有文件（它们引用上述模块）。
3. 提交前再核 HEAD 未并发移动；用 specific-file staging，不 `git add -A`（工作树另有 `.agents/tasks/checksum-drift-8/*` 等他项产物）。
4. 提交后应在 clean HEAD worktree 复跑 phase4 定向集确认转绿（本任务已备好方法）。
5. 本任务 tasks.md 维持 `[-]`，提交入库并 clean HEAD 复跑转绿后方可由 Task 18 流程勾 `[x]`。
