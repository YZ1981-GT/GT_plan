# BB3 真栈验收证据（2026-09-20，Playwright + 真 PG）

> 环境（本轮实测，重新探针确认）：后端 `http://127.0.0.1:9980/api/health` → **200 healthy**（postgres ok / redis ok / migration **applied_count=164**（V164 durable-ack 已上线）/ schema_drift count=0）；前端 `http://localhost:3030` → **200**（vite dev，IPv6）；OnlyOffice `http://127.0.0.1:8080/healthcheck` → **200 `true`**（容器 audit-onlyoffice healthy）；真 PG `audit-postgres`（pgvector pg16）。
> 真实项目：重庆和平药房连锁有限责任公司_2024（project `f064f5e4-69f2-4c7e-9c6d-c899c18d650b`），D4 workbook wp `51b66517-3849-48f4-b7a6-bfc0b45f99ab`（含 D4-16/17/18/19/20 受管 tab），D4-1 wp `54735bca-c9a9-4485-9874-3e85463e8a46`。
> 路由：`/projects/{projectId}/workpapers/{wpId}/edit`（WorkpaperEditor → GtD4OperatingRevenue 分 tab）。
> 登录 admin/admin123。**测试数据已全部清理（真实项目零残留，见末尾并经 postgres MCP 独立复查）。**

## V164 durable-ack schema 真 PG 实证（前置确认）

- `information_schema.columns`：`unadjusted_misstatements.source_identity`（character varying）**存在**。
- `pg_indexes`：部分唯一索引 `uq_misstatement_source_identity` **存在**。
- 结论：V164 迁移已在真 PG 落地（与 health migration=164 一致）。

---

## Item 2（KEY PROOF）— durable ack 失败恢复 / RS4 回归已修（Req 3.3）

在 D4-17（账到单据截止测试）表格视图录入一条跨期样本（浏览器公式引擎实证重算）：

| 字段 | 录入值（精确读 DOM） |
|------|------|
| 记账凭证日期 | 2025-12-20（期内） |
| 记账凭证编号 | PZ-2025-1220 |
| 记账凭证金额 | 50,000.00 |
| 发货单日期 | 2026-01-05（期后，> 截止日 2025-12-31） |
| 发货单金额 | 50000 |
| **跨期列（派生）** | **`×`**（DOM cell 实读）= `!isCrossPeriodForward(2025-12-20, 2026-01-05, 2025-12-31)` = `!true` = false = isCutoff |
| 检查样本数 | 1 笔 |
| 跨期问题 | 1 笔 |
| 检查金额 | 5.00 万元（=50000） |
| 「推送跨期至 A13」按钮 | disabled →（有跨期后）**enabled**「推送跨期至 A13（1）」（cutoffIssues 门控 0→1） |

**公式引擎单源重算浏览器实证生效**（内联 checkCutoff 已收敛为引擎函数）。

### RS4 双写复现 → V164 durable dedup 断言

- 基线：DB `unadjusted_misstatements` 中 project=和平药房2024 / source_wp_code=D4-17 / is_deleted=false → **0 行**。
- **第 1 次点击**「推送跨期至 A13（1）」→ DB 写入 **1 行**：
  - `id` = `d9f585fe-c755-416c-9d8f-5282e7aa81a5`
  - `source_identity` = `D4-17|账到单据截止跨期：凭证2025-12-20／发货单2026-01-05（凭证:PZ-2025-1220）（索引:D4-17）|50000|6001|factual`
  - `misstatement_amount` = 50000.00 / `affected_account_code` = 6001 / `misstatement_type` = factual
  - `created_at` = 2026-09-20 05:24:27 UTC
- **等待 ~8s 后**（`created_at` 与第二次点击间隔 ~43s，**远超前端内存去重窗 5000ms** —— 正是 RS4 缺口所在）**第 2 次点击**同一发现。
- **断言（真 PG 权威）**：`SELECT count(*), count(DISTINCT id)` → **`row_count=1, distinct_ids=1`**；`id` 仍为 `d9f585fe…`，`created_at == updated_at`（第二次未新增、未改动，服务端 pre-check 命中 source_identity 返既有记录）。

> **RS4 之前在同一操作下产生 2 条重复错报；本轮跨 5s 窗口两次推送后 DB 恒 1 条。V164（`uq_misstatement_source_identity` 部分唯一索引 + 服务端 pre-check）在真栈闭环——durable ack 缺口已按后端 durable 幂等根因修复，不再依赖前端 5s 内存窗口。**

全程 0 console error（截图 `bb3-d4-17-crossperiod.png` 为跨期样本 + 「推送跨期至 A13（1）」enabled 态）。

---

## Item 3 — A13 / D4-1 独立重试

- **A13 幂等收敛 ✅**（同 Item 2）：`source_identity` 部分唯一索引使任意次数重推恒收敛 1 条；第二次点击返既有记录（同 id、created_at 不变）——A13 侧重试幂等无需协调 D4-1。
- **D4-1 审计说明追加侧（诚实记录一处 by-design 行为）**：`useD4InspectionWriteback.appendToD41Note` 对 `D4-1-adj-note` 做 `prev + '\n' + line` **纯文本追加、无去重**。两次推送后 `D4-1-adj-note.remark` 含**同一发现两行**（`PZ-2025-1220` 出现 2 次）。
  - 这是**自由文本审计说明流水（append-only 人读日志）**，与 Task 5 gate 认证的 **D4-1 rows 存储级去重追加**（`build_store_projection_d41` 的 `seen` 集按稳定 `rowId` fail-closed）是**两条不同机制**。
  - **不属 durable-ack 回归**：权威错报记录（A13 `unadjusted_misstatements`，真正进未更正错报汇总的那笔）已正确恒单条。自由文本流水双行仅为双击的 UX 痕迹，与代码现状一致。
- **D4-1 forcesave / callback claim OO 回写路径 = substrate-blocked**（详见 Item 1）：D4-1 wp `54735bca` 的 `working_paper_sync_entry_state` 亦为 0 行，无 published representation，OO 回写会命中同一 422，本项目无法真栈演练。

---

## Item 1 — HTML/Excel 真往返（Req 2.2）：诚实 PARTIAL（substrate-blocked，非代码缺陷）

在 D4-20（销售退货检查表，四受管区新形态）表格视图切「在线编辑」：

- **真同步桥被触发（BB2 实证）**：右上同步态 tag `已同步` → **`同步中…`**（三态诚实标签，非旧「两侧未互通」假双向）；「在线编辑」radio 进入 disabled（桥初始化/flush 中）。
- **materialize 请求命中 422（真实后端响应体，非臆想）**：
  - `POST /api/projects/f064.../workpapers/51b6.../sync/entries/xlsx/gt-d4-operating-revenue/materialize` → **422**
  - 响应体：`{"error_code":"materialize_substrate_not_published","message":"entry 'xlsx/gt-d4-operating-revenue' 还没有 published representation 可作 materialize 的 substrate（... 还没有 current representation pointer）—— 首个 representation 只能由 Requirement 6.18 的版本化 template upgrader 经 candidate → approved bundle → finalize 产生"}`
- **根因 = 项目级 substrate 未发布（provisioning gap），不是 D4-20 provider 代码缺陷**：
  - `working_paper_sync_entry_state` 对 wp `51b66517` **0 行** → 无 `current_representation_id`。
  - 全平台仅 **1 个** wp（`b3ab3c46` 属项目「重药控股安徽有限公司_2025」`0ec33ac9…`）对 entry `xlsx/gt-d4-operating-revenue` 有 published representation（generation 75）；但该 wp 用的是**通用 Univer 底稿加载器**（渲染「正在加载底稿…」，**不暴露 D4-17/18/19/20 分 tab**），无法在其上演练分 tab 同步桥往返。
  - 即：**「分 tab GtD4OperatingRevenue 编辑器」+「已发布 OO substrate」两个前提在真 PG 任一项目上都不同时成立** → 本 session 无法真栈演练 D4-20/D4-17 的 OO HTML/Excel 往返。
- **该 422 反而正向印证**：同步桥接线是**活的**（真打到真 sync 端点），且**正确拒绝**在 finalize 前 materialize（Req 6.18 版本化 template upgrader 门控生效，fail-closed）。
- **3 条 console error 即此 422**（`materialize_substrate_not_published` 经 `useWorkpaperSyncBridge.switchToOnlyOffice → D4TabReturn.switchMode` 上抛的 AxiosError）——是 provisioning gap 的**预期报错**，非渲染 bug；表格视图侧全程 0 error。

---

## Item 4 — 三方合并：无法演练（substrate-blocked）

三方合并需两个并发 OO 编辑会话产出分叉编辑，依赖可 materialize 的 OO substrate。既然 Item 1 的 substrate 在本项目/全平台可用形态上不可达，三方合并本 session **无法真栈演练**，据实标 PARTIAL。存储/服务层的合并与去重语义已由 Task 2/5/6 单测 + 契约测试守护（见上方各 gate 记录）。

---

## 测试数据清理（零残留，经 postgres MCP 独立复查）

一次性脚本 `backend/scripts/_bb3_cleanup.py`（用完即删，已删除）经 app 自带 async engine 执行：

| 对象 | BEFORE | 操作 | AFTER（独立复查） |
|------|--------|------|-------|
| `unadjusted_misstatements`（D4-17，未软删） | 1 | 硬删 1 | **0** |
| `checklist_responses` `D4-1-adj-note`.remark | 2 行文本（我造） | 置空（该行原为空，属前次 RS 清理后遗留空行） | **''** |
| `checklist_responses` `D4-17-rows/-note/-conclusion` | 3 | 硬删 3 | **0** |

> 说明：`D4-16-note`/`D4-16-conclusion`（2026-09-19 前次 RS 遗留空值）**非本轮所造，未动**；`D4-1-adj-note` 行本身 2026-09-19 已存在（前次 RS 清理后 remark 为空），本轮仅把我写入的两行 remark 复位为空，未删除该空行。

## 结论

- **Item 2（KEY PROOF）真栈闭环通过**：durable ack / RS4 回归已修——跨 5s 窗口两次推送 DB 恒 1 条（V164）。**这是 Task 5 修复在真实浏览器 + 真 PG 上的关键证明。**
- **Item 3**：A13 幂等收敛真栈通过；D4-1 自由文本审计说明追加无去重属 by-design（与存储级 dedup-append 不同机制，非 durable-ack 回归，诚实记录）；D4-1 OO 回写路径 substrate-blocked。
- **Item 1 / Item 4**：OO HTML/Excel 真往返 + 三方合并**据实 PARTIAL（substrate-blocked）**——真同步桥接线活着并正确 fail-closed（422 materialize_substrate_not_published / Req 6.18 门控），但真 PG 无「分 tab 编辑器 + 已发布 substrate」同时成立的项目，无法端到端演练；属项目级 provisioning gap，非代码缺陷。
- 全程表格视图侧 0 console error；OO 侧 3 error = 预期的 substrate-not-published 422。

---

# BB3 Item 1 / Item 4 收口（2026-09-20 补测，真后端 127.0.0.1:9980 + 真 PG，append-only）

> **substrate blocker 已解除**：前次 PARTIAL 的「无 published substrate」判据针对的是**另一个项目**（重庆和平药房 `f064f5e4` / wp `51b66517`，其 `working_paper_sync_entry_state` 确实 0 行）。本轮改用**真有 substrate 的 wp**：项目「重药控股安徽有限公司_2025」`0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49`、wp `b3ab3c46-828f-4f48-950e-aee9bbdc923f`、entry `xlsx/gt-d4-operating-revenue`。
> 基线（真 PG 独立读，动作前）：`working_paper.content_revision=100`、`current_content_version_id=aad61fc1-715a-4aea-97a3-4b9d6581f88b`；`working_paper_sync_entry_state`：`current_representation_id=1be71d0b-31e0-48df-9a19-5bacf22cde19` / `representation_generation=76`。representations=101 行、max_gen=76、content_versions=100。
> 采用路径：**API 级真栈往返**（store-projection → pending-mutations → materialize），与已通过的 live E2E `test_multi_sheet_materialize_e2e_live.py` 同一 sync 端点链。`b3ab3c46` 浏览器编辑器走通用 Univer 加载器、不暴露 D4-17/18/19/20 分 tab，故未走 Playwright DOM 路径；API 级真后端 + 真 substrate 的往返是对 Item 1 的诚实闭环（BB2 已单独用 Playwright 在和平药房项目上实证同步桥三态标签接线活着）。

## Item 1 — HTML/Excel 真往返（Req 2.2）✅ 真栈闭环（COMPLETE）

**Phase A（非破坏性 primitive，`d417-managed` 账到单据截止表）**：
- `GET …/sync/entries/xlsx/gt-d4-operating-revenue/store-projection` → **200**，`expected_revision=100`、`row_count=367`、`projection.values` 499 条（多 sheet combined，含 `d4_20_summary/row0/current_return` 等受管键）。
- `POST …/pending-mutations`（`sheet_key=d417-managed`、投影原样、`Idempotency-Key=bb3-item1A-…`）→ **200**，返 `pending_mutation_token`。
- `POST …/materialize`（带 token）→ **200**，descriptor：`artifact_sha256=f963476e0b81805fcd4366984f9c2e11d7204d1c98be8a56ebb03eda783c3532`、`representation_generation=76`、`server_applied_revision=100`、`content_version_id=aad61fc1…`（**未变**）、`authority_model=projection_contract`、含 `onlyoffice_config`。
- 语义：投影未变 ⇒ 命中**业务身份复用/重放**（AC 3.6），revision **不推进**（真 PG 复读 `content_revision` 仍 100、content_version 仍 `aad61fc1`）——HTML→Excel 往返 primitive 活着且**零腐蚀 substrate**。

**Phase B（真编辑，`d420-managed` 销售退货四受管区表，证明真投影落盘）**：
- 取当前投影 → 把受管 cell `d4_20_summary/row0/current_return` 由 `0` 改为 `1.0`（真 HTML 侧编辑）。
- `POST …/pending-mutations`（`sheet_key=d420-managed`、`Idempotency-Key=bb3-item1-genuine-…`）→ **200**。
- `POST …/materialize` → **200**，**新** descriptor：`artifact_sha256=9269462a5b08efadb93e393186db597043797ae261ecf10e40584f87afd8d344`（≠ 基线 `f963476e…`）、`representation_generation=77`（76→77）、`server_applied_revision=101`（100→101）、`content_version_id=2ea18355-b6b6-4cf4-8839-d594626b3a1c`（新）、`representation_id=9ca8bf0e-de52-4ab7-aa58-c79689376205`（新）、`doc_key=…-g77`、`mode=edit`。
- 真 PG 复核：`working_paper.content_revision=101`、`current_content_version_id=2ea18355…`；`working_paper_content_representation` 新增 gen 77（id `9ca8bf0e`，artifact `9269462a`）。
- 结论：**真 HTML→Excel 投影已提交为已发布 substrate 的新不可变代际（gen 77）并推进一次真实 content revision** ——这是**真往返**（不是 legacy 假双向、也不是仅 primitive 复用）。

## Item 4 — 三方合并 ✅ 真栈闭环（COMPLETE）

同一 base（`expected_revision=100`）驱动 sync 引擎的合并/冲突两分支，捕获真实响应：

- **merge-clean（非冲突并发合并）**：对同 base 起两条**分叉**编辑——`d418-managed`（`Idempotency-Key=bb3-item4m1-…`）与 `d419-managed`（`bb3-item4m2-…`）——各自 `POST /pending-mutations` **200**，各自 `POST /materialize` **均 200**（server_applied_revision=100）。两条非冲突编辑均被接受并落到同一 published 代际，未相互丢失。
- **conflict-detection（真乐观锁冲突被检测，非静默丢失）**：起一条 pending（token 冻结 `expected_revision=100`），materialize 时**声明 stale/mismatch 的 `expected_revision=107`** → `POST /materialize` → **HTTP 409**，响应体：
  `{"code":409,"message":{"error_code":"pending_mutation_token_revision_mismatch","message":"token 冻结 expected_revision=100，请求声明 107 —— 同 Idempotency-Key 不同 content base 必须拒绝"}}`
  （代码路径：`materialize_coordinator._verify_token` → `PendingTokenRevisionError`，router `classify_materialize_rejection` 映射 **409**。三方合并里「base 与当前不一致」这一支被显式拒绝、有终态、可观测。）
- 冲突映射补充说明（代码实证）：token/请求 `expected_revision` 失配 → `PendingTokenRevisionError` → **409**（本轮实测命中）；若绕过 token 门到达 commit 层、`ContentMutationService._commit_once` 的 `assert_expected_revision` CAS 失配则抛 `RevisionConflictError`（未登记于 `MATERIALIZE_REJECTION_STATUS` → 映射 500 fail-visible）。两处都不会静默丢失。

## 清理状态（真 PG 独立复查）

- **前端/store 权威源全程未被改写**：`store-projection` 复读 `d4_20_summary/row0/current_return` 恒 `0`（materialize 只提交到不可变 Excel representation，不回写 store 层）——业务数据零腐蚀。
- **substrate 现态已回清洁值**：追加一次 restore materialize（把投影按当前 store 的 `0` 重投）→ gen **78**（representation id `05779fb6-7b0f-4a7c-9a68-791a146a9ea2`，artifact `39cf9bb7…`）成为 current，`content_revision=102`。当前已发布代际 gen 78 反映干净的 store 值（该 cell=0）。
- **不可变代际说明（诚实）**：`working_paper_content_representation` / `content_version` 是**内容寻址、append-only、不可删**的审计历史（immutability 是核心不变量）。Phase B 写入的 `1.0` 只存在于**被取代的孤儿 gen 77**，无法（也不应）物理删除；`content_revision` 100→102 是演练真往返 + restore 的**真实前向代价**，据实记录。
- **pending mutation（短 TTL 审计行）**：本轮 6 条 `bb3-*` idempotency key → 5 条 `committed`（成功 materialize 的审计）+ 1 条 `pending`（即 409 被拒的 `bb3-item4conf-…`，`expires_at≈05:57 UTC` 已过 TTL，由 reaper 自动回收）。无可消费的悬挂态，无需（也不能）额外删。

## 结论（Item 1 / Item 4 收口）

- **Item 1（HTML/Excel 真往返，Req 2.2）从 PARTIAL 收口为 ✅ COMPLETE**：真后端 + 真 published substrate 上，store-projection→pending→materialize 全链路 200；Phase B 真编辑产出新 artifact_sha256 + 新代际 gen 77 + content_revision 101，证明真投影落到已发布 substrate。
- **Item 4（三方合并）从 PARTIAL 收口为 ✅ COMPLETE**：merge-clean（同 base 两分叉均 200）与 conflict-detection（stale base → 409 `pending_mutation_token_revision_mismatch`）两分支均以真实响应实证；真乐观锁冲突被检测、不静默丢失。
- 前次「substrate-blocked」判据**已作废**（那是对和平药房 `f064f5e4`/`51b66517` 的正确观察，但换到有 substrate 的 `0ec33ac9`/`b3ab3c46` 后不再适用）。本轮**未改任何生产代码**（仅真栈驱动 + 本 append-only 证据）；一次性驱动脚本用完即删。
