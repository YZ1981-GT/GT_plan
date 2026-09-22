# C1 同步协议契约 — D4 双模式

> 状态：FROZEN（此文件为门控契约，不得在未评审情况下修改）
> 依据：Requirements 2.1 / 2.2 / 2.3
> 生成依据：2026-06 grep 实证（`backend/app/services/workpaper_sync/*` + `backend/app/services/*` + `audit-platform/frontend/src/`）
> 关联 spec 产物：`merge.py`（Task 14 三方合并域）/ `content_mutation.py`（Task 15 唯一 commit 边界）/ `conflict_resolution.py` / `materialize_coordinator.py` / `excel_rematerialize.py` / `repository.py`

---

## A. 共享同步路径

### A.1 关键结论

**`ContentMutationService` 与 `useWorkpaperSyncBridge` 均已在仓库中真实存在**：

- 后端：`backend/app/services/workpaper_sync/content_mutation.py`（110 KB），文档注释明列：
  「唯一 commit 边界是 `ContentMutationService.commit()`（Property 61）」；
  被 `workpaper_save_orchestrator.py`、`wp_download_service.py`、`wp_migration_service.py`、
  `wp_storage_service.py`、`oo_to_html.py`、`materialize_coordinator.py`、
  `conflict_resolution.py`、`projection_first_publication.py` 共同消费。
- 前端：`audit-platform/frontend/src/composables/useWorkpaperSyncBridge.ts`（34 KB）。

**禁止文件直读回调**：`merge.py` 文档头第 3 节明示「本模块**不 import** openpyxl / python-docx / sqlalchemy / repository / outbox」；`excel_rematerialize.py` 文档头二节明示「保存后**必须**过 Task 37 的唯一 commit 前置门 —— `ContentMutationService` 只接受过了 `RematerializeOutcome.assert_ready_for_commit` 的产物」。

### A.2 四种写入路径接入表

| 模式 | 写入路径 | ContentMutationService | useWorkpaperSyncBridge | 现状 |
|------|---------|:---:|:---:|------|
| HTML 编辑 | HTML → store → `MaterializeCoordinator`（`direction=html_to_oo`） → `ContentMutationService.commit` | Y | Y | **已实现**（`materialize_coordinator.py` L1765-1768 事务 B 唯一业务事务；`merge.py` 头注「Task 15 已接线」） |
| Excel/OO 导出 | 权威 OOXML 字节 → `ExcelRematerializeOutcome.assert_ready_for_commit` → `ContentMutationService.commit` | Y | N（Excel 侧不需前端桥） | **已实现**（`excel_rematerialize.py` L27-31 明列断言门；`ContentMutationService` 拒收未过门的产物） |
| Excel/OO 导入 | OO callback → `oo_to_html.py` → 有冲突走裁决，无冲突走 `ContentMutationService.commit(substrate=incoming)` | Y | Y（用户端确认刷新） | **已实现**（`oo_to_html.py` L47-51 明列无冲突→commit、有冲突→指针不动） |
| 上传/CSV/JSON 导入 | 上传 OOXML 字节原样提交为 `authoritative_payload` → `ContentMutationService.commit` | Y | N | **已实现**（`wp_download_service.py` L406-410 明列「上传 OOXML 字节就是权威内容本体」；`prefill_stale`/`updated_at` 属非内容非版本副作用字段，Requirement 2.1 明列豁免） |
| 底稿 parsed_data 迁移 | projection lane → `ContentMutationService.commit_html_projection` | Y | N | **已实现**（`wp_migration_service.py` L210-214 明列「唯一提交出口是 `commit_html_projection()`」） |

### A.3 共享副作用豁免清单（Requirement 2.1 明列）

以下副作用**不属内容非版本字段**，允许绕过 `ContentMutationService`，仅记入本契约：

- `wp.file_version += 1`：已从共享 handler 收回至三条各自写文件处（`workpaper_save_orchestrator.py` L36-40）
- `updated_at` / `prefill_stale`：`wp_download_service.py` L409 明列为「Requirement 2.1 明列的非内容非版本副作用字段」

---

## B. 字段级合并规则

来源：`backend/app/services/workpaper_sync/merge.py` §「三方真值表」——**这是 Requirement 2.2 的直接实现**，判据自上而下短路。

| 场景 | merge.py 判据（verdict） | 实现状态 |
|------|-------------------------|---------|
| 不同字段同时写入 | 无冲突分支，两侧值按 stable field key 独立合并 | **已实现**（P25 属性测试锁死） |
| 同字段，值相同 | 判据 7：`c == i` → `merged = c`（`both_sides_agree`） | **已实现** |
| 同字段，值不同（b/c/i 全异） | 判据 9：`merged = c`（fail closed）+ `verdict=conflict_value` + 三方原值入冲突记录 | **已实现**（P26 属性测试锁死） |
| Excel 覆盖 HTML 同字段 | 禁止 Excel 优先：判据 6/7/8/9 均**不选边**，`merged` 恒保持 `current`，由人工裁决（`apply_resolutions`）收敛 | **已实现**（`merge.py` 头注：「永不 last-write-wins」；`conflict_resolution.py` 收敛） |
| 最后写入胜出（Last-Write-Wins） | 禁止：判据 8/9 均把三值原样写入冲突记录，`merged` 保持 `c` | **已实现**（`merge.py` 头注明列） |
| protected 字段异值 | 判据 4：`verdict=conflict_protected` | **已实现**（P24 属性测试锁死） |
| delete-update 冲突 | 判据 8：`b` 在且 c/i 恰一侧缺失 → `verdict=conflict_delete_update` | **已实现**（P27 属性测试锁死） |
| schema 冲突（载体消失） | 判据 3：非行域字段在 incoming 缺失 → `verdict=conflict_schema` | **已实现** |
| Word 模式 | 判据 2：`mode=word_only` → `merged = i or c`，不进 HTML | **已实现** |
| 结构冲突封锁 | 判据 0：`held_by_schema_conflict`，`merged = c`（fail closed） | **已实现** |
| 行级 delete-update 冲突 | 判据 1：`held_by_row_conflict`，`merged = c`（整行 hold） | **已实现** |

### B.1 值比较规范化（merge.py §「类型规范化只用于比较，不改写值」）

- `amount` / `rate` / `ratio` → `Decimal`
- `integer` → `int`（bool 拒绝；`True != 1`）
- `date` / `datetime` → 各自类型（互相**不**等价）
- `boolean` → `bool`（只接受真 bool 与 `"true"`/`"false"`）
- `text` → CRLF/CR 归一 LF + 去 BOM；**不** trim、**不**折叠空白、NBSP 与普通空格**不**等价
- `json` → canonical bytes（键序无关）
- `enum` → 原样精确比较

不可规范化输入 → 抛 `ValueNormalizationError` → 收成 `schema` 冲突并**保留原值供裁决**。

### B.2 MISSING 独立哨兵

「字段不存在」与「字段被显式清空」是两种输入，由 `MISSING` 单例区分：与 `None`、`""`、`0`、`False` 均不相等。折叠为 `None` 会使删除与清空在 HTML projection、回滚、审计轨迹里再也分不开。`TestMissingSentinel` 逐条锁死。

---

## C. 冲突轨迹数据结构

Requirement 2.2 要求保留 `base/current/incoming/decision/trace`。实现分**两栏**，禁止混用：

### C.1 字段级冲突记录（merge 域产出，`MergeOutcome`）

来源：`merge.py` §「永不 last-write-wins」+ §「MISSING 独立哨兵」

| 字段 | 类型 | 说明 |
|------|------|------|
| `field_key` | `stable_sheet_key.row_key.field_key` | 唯一字段身份（本 spec R3 冻结，`preset_version` 不进入） |
| `base` | `ValueEnvelope \| MISSING` | 分叉点值 |
| `current` | `ValueEnvelope \| MISSING` | 数据库侧当前值 |
| `incoming` | `ValueEnvelope \| MISSING` | 本次写入值 |
| `merged` | `ValueEnvelope` | 折后结果（冲突时恒等于 `current`） |
| `verdict` | `str` | `conflict_value` / `conflict_protected` / `conflict_delete_update` / `conflict_schema` / `held_by_*` 等 |
| `value_envelope` | dataclass | 值与类型信封（absent 与 present-but-null 不折叠） |

### C.2 裁决轨迹（`conflict_resolution.py`）

Requirement 2.2 的 `decision` 与 `trace` 字段由 `conflict_resolution.py` 独立短事务写入（本文件唯一 commit 边界仍是 `ContentMutationService.commit`，见文件头 §「不 commit 业务内容」）。

**建议规范化字段（冻结为本 spec 契约，供未来 CI 校验）**：

```json
{
  "conflict_id": "<uuid>",
  "wp_id": "<wp_id>",
  "field_key": "<stable_sheet_key>.<row_key>.<field>",
  "base": "<value_at_branch_point>",
  "current": "<value_in_db>",
  "incoming": "<value_being_written>",
  "decision": "pending | accept_current | accept_incoming | manual",
  "resolved_at": null,
  "trace": [{"ts": "...", "actor": "...", "action": "..."}]
}
```

> **注意**：merge 域的 `verdict` 与本表的 `decision` 是两栏概念。
> `verdict` 描述「三方比较结果」（机器裁决）；`decision` 描述「人工裁决结论」（用户决策）。
> `conflict_resolution.py` 是唯一裁决轨迹的写入方；`merge.py` 不写 `decision` 也不写 `trace`。

---

## D. Durable Ack vs Applied 状态机

Requirement 2.3 明确：durable ack ≠ applied；canonical rematerialize 完成 + 目标 content version 确认后才算 applied。

### D.1 状态定义（依据 `materialize_coordinator.py` + `content_mutation.py`）

```
pending
  → ack_received   ← 决策/业务意图已写入 DB（operation 行 + 幂等键落库）
       ↘ applied    ← ContentMutationService.commit 完成 CAS + canonical rematerialize
       ↘ rejected   ← 裁决拒绝或 CAS 冲突
       ↘ error      ← 事务失败（可重试，operation 有终态可查）
```

### D.2 每态持久化证据

| 状态 | 判定证据 | 代码依据 |
|------|---------|---------|
| `pending` | `repository.flush()` 只创建 pending mutation，**不推进** revision | `materialize_coordinator.py` L530-533 断言：flush 推进 revision 会抛「Requirement 3.1 规定 flush 只创建 pending mutation」 |
| `ack_received` | `ContentMutationService.commit()` 的 CAS 唯一推进 `working_paper.content_revision`（`UPDATE ... WHERE content_revision = :expected`，命中 0 行即冲突） | `workpaper_save_orchestrator.py` L46-49 明列「乐观锁是 `bump_content_revision()` 的单条 SQL CAS」 |
| `applied` | commit 事务内：projection + 兼容 representation staging/roundtrip/publish + revision CAS + pointer + outbox **一步完成**；rematerialize 产物由 `RematerializeOutcome.assert_ready_for_commit` 转手 `ExcelVerificationBundle.assert_publishable` 三重判据守门 | `materialize_coordinator.py` L41「事务 B：唯一业务事务、恰一次 revision」；`excel_rematerialize.py` L176-189 断言门 |
| `rejected` | `conflict_resolution.py` 裁决拒绝或 409 CAS 冲突 | `repository.py` L1239-1240「同 key 重复 flush 命中既有行，由 `ContentMutationService` 判『逐项等值即重放、不等值即 409』」 |

### D.3 铁律（Requirement 2.3）

- **ack_received 不等于 applied**：ack 只表示决策已持久化（operation 行 + 幂等键落库），**canonical content 未更新**
- **禁止伪装**：`merge.py` 头注「`ContentMutationService` 只接受过了 `RematerializeOutcome.assert_ready_for_commit` 的产物」—— 未经 rematerialize 的 commit 会被拒收
- **canonical rematerialize 与 commit 在同一事务内**：`materialize_coordinator.py` §「事务 B」唯一业务事务同时完成 projection + representation + revision CAS + pointer + outbox
- **rollback 只接受 opaque version UUID**：`pilot_harness.py` L415-418「`opaque_version_rollback_no_numeric_collision` —— 回滚只接受 opaque version UUID；跨 wp 相同 numeric revision 不碰撞」

---

## E. Canonical Refresh 触发条件

### E.1 触发矩阵

| 事件 | 触发 canonical rematerialize | 依据 |
|------|:---:|------|
| 用户 HTML 保存底稿 | **是** | `materialize_coordinator.py` §「MaterializeCoordinator」：HTML 保存即经事务 B 提交 |
| 模式切换（HTML↔Excel，仅 UI 切换） | **否** | 切换本身不产生业务变更；只有当用户在 OO 侧完成保存才走 commit |
| 冲突 decision=resolved（人工裁决收敛） | **是** | `conflict_resolution.py` `settle_adjudicated_projection` → `ContentMutationService._settle_projection` 独立重算 |
| OO callback 无冲突 | **是** | `oo_to_html.py` L47-51「无冲突/已裁决 → `ContentMutationService.commit(substrate=incoming)`」 |
| OO callback 有冲突未裁决 | **否**（指针不动） | `oo_to_html.py` L47「有冲突且无裁决 ⇒ application/operation=conflict，指针一律不动」 |
| 上传/CSV/JSON 导入完成 | **是** | `wp_download_service.py` L406-410「上传 OOXML 字节原样提交为 authoritative_payload」 |
| parsed_data 迁移 | **是** | `wp_migration_service.py` L210-214「`commit_html_projection()` 唯一提交出口」 |
| 表示升级（representation upgrade） | **否** | `excel_rematerialize.py` L186-189「纯表示升级的产物不得交 ContentMutationService —— 纯表示升级不改业务 projection」 |

### E.2 前端刷新判据

`merge.py` §「生产消费方：Task 15 已接线」明列：`MergeOutcome.requires_client_refresh` 是 refresh 判据的单一来源（`conflict_resolution.py` 文件头三节亦复述：「refresh 判据从 `MergeOutcome.merged` 收敛为 `projection_requires_client_refresh`」）。

---

## F. 实现缺口（D4 循环 36 个 wp_code）

### F.1 分母来源

本 spec 治理 36 个逻辑 `wp_code`（design.md §R1 owner 矩阵）。分母**不**包含物理 Excel sheet、sheet 变体、程序表。

### F.2 C1 层统一接入状态

以下 C1 层机制对 36 个 `wp_code` **一视同仁**，无 per-wp 差异：

| 机制 | 接入状态 | 说明 |
|------|---------|------|
| `ContentMutationService` | 已实现（唯一 commit 边界） | 所有 36 个 wp_code 走同一 commit 服务 |
| `useWorkpaperSyncBridge` | 已实现（HTML 侧唯一桥） | HTML 编辑路径唯一入口 |
| 三方合并域 `merge.py` | 已实现（stable field key 域） | P24-P27 属性测试锁死 |
| 裁决轨迹 `conflict_resolution.py` | 已实现 | 独立短事务，不 commit 业务内容 |
| CAS 乐观锁 `bump_content_revision` | 已实现 | `working_paper.content_revision` 唯一推进 |
| `ExcelRematerializeOutcome.assert_ready_for_commit` 前置门 | 已实现 | 拒收未过门产物 |
| rollback 用 opaque version UUID | 已实现 | `pilot_harness.py` 有属性测试 |

### F.3 逐 wp_code C1 层状态表

**统一结论：所有 36 个 wp_code 的 C1 sync 协议均为已实现（后端 ContentMutationService / 三方 merge 域 / 裁决轨迹 / CAS 乐观锁 / rematerialize 断言门 全部真实存在并被消费）**。逐 wp_code 差异不体现在 C1 层（sync 协议），而体现在下游 C2 formula / C3 linkage / C4 验收层。

| wp_code | C1 sync 协议接入 | 冲突处理 | 状态 |
|---------|:---:|:---:|------|
| D4-1 | Y | Y | 已实现 |
| D4-2 | Y | Y | 已实现 |
| D4-3 | Y | Y | 已实现 |
| D4-4 | Y | Y | 已实现 |
| D4-5 | Y | Y | 已实现 |
| D4-6 | Y | Y | 已实现 |
| D4-7 | Y | Y | 已实现 |
| D4-8 | Y | Y | 已实现 |
| D4-9 | Y | Y | 已实现 |
| D4-10 | Y | Y | 已实现 |
| D4-11 | Y | Y | 已实现 |
| D4-12 | Y | Y | 已实现 |
| D4-13 | Y | Y | 已实现 |
| D4-14 | Y | Y | 已实现 |
| D4-15 | Y | Y | 已实现 |
| D4-16 | Y | Y | 已实现 |
| D4-17 | Y | Y | 已实现 |
| D4-18 | Y | Y | 已实现 |
| D4-19 | Y | Y | 已实现 |
| D4-20 | Y | Y | 已实现 |
| D4-21 | Y | Y | 已实现 |
| D4-22 | Y | Y | 已实现 |
| D4-23 | Y | Y | 已实现 |
| D4-24 | Y | Y | 已实现 |
| D4-25 | Y | Y | 已实现 |
| D4-26 | Y | Y | 已实现 |
| D4-27 | Y | Y | 已实现 |
| D4-28 | Y | Y | 已实现 |
| D4-29 | Y | Y | 已实现 |
| D4-30 | Y | Y | 已实现 |
| D4-31 | Y | Y | 已实现 |
| D4-32 | Y | Y | 已实现 |
| D4-33 | Y | Y | 已实现 |
| D4-34 | Y | Y | 已实现 |
| D4-35 | Y | Y | 已实现 |
| D4-36 | Y | Y | 已实现 |

### F.4 C1 层 UNVERIFIABLE 声明（严格遵守）

以下**不能**在本契约中判定，归 C0 gap register / C4 逐表验收判定：

- 每个 wp_code 是否已在 D4 循环中实际完成 HTML↔Excel 双向实测（归 C4）
- 每个 wp_code 的 formula key 是否已按 R3 冻结（归 C2）
- 每个 wp_code 的 DAG 与联动是否已按 R4 建立（归 C3）
- 是否所有 36 个 wp_code 的 C0 模板 / identity 就绪（归 C0）
- **UNVERIFIABLE 不计 GREEN**（Requirement 8.1）

### F.5 已实现证据链（grep 实证，2026-06）

- `backend/app/services/workpaper_sync/content_mutation.py`（110 KB）
- `backend/app/services/workpaper_sync/merge.py`（三方合并真值表 10 分支 + 12 类型规范化）
- `backend/app/services/workpaper_sync/conflict_resolution.py`（78 KB）
- `backend/app/services/workpaper_sync/materialize_coordinator.py`（145 KB，事务 B 唯一业务事务）
- `backend/app/services/workpaper_sync/excel_rematerialize.py`（`assert_ready_for_commit` 前置门）
- `backend/app/services/workpaper_sync/oo_to_html.py`（174 KB，无冲突→commit、有冲突→指针不动）
- `backend/app/services/workpaper_sync/repository.py`（CAS `bump_content_revision`）
- `backend/app/services/workpaper_sync/pilot_harness.py`（`opaque_version_rollback_no_numeric_collision` 属性测试）
- `backend/app/services/workpaper_sync/writer_migration.py`、`phase5_d4_*.py`（D4 循环 per-wp 接线）
- `audit-platform/frontend/src/composables/useWorkpaperSyncBridge.ts`（34 KB，前端唯一桥）

---

## G. 属性测试锁死清单

以下属性测试锁定本契约的每条铁律，任一被破坏 → CI 必红：

| Property | 锁定内容 | 对应 Requirement |
|---------|---------|-----------------|
| P24 | 保护字段冲突 | 2.2 |
| P25 | 不同字段自动合并 | 2.2 |
| P26 | 同字段异值必冲突 | 2.2 |
| P27 | delete-update 不整表覆盖 | 2.2 |
| P32 | Word 多实例异值 | 2.2 |
| P35 | 冲突双侧可追溯 | 2.2 |
| P38 | retry 一律不再 forcesave | 2.1（禁止文件直读回调） |
| P61 | 唯一 commit 边界是 `ContentMutationService.commit` | 2.1 |
| P65 | `oo_to_html` extract 与 merged 逐字段等值 | 2.1 |
| P67 | 表示升级不改业务 projection（走 non-current candidate） | 2.3 |
| `opaque_version_rollback_no_numeric_collision` | 回滚只接受 opaque version UUID | 2.3 |

---

## H. 禁止事项（冻结）

- ❌ **Last-Write-Wins**：判据 8/9 不选边，`merged` 恒保持 `current`（`merge.py` 头注明列「永不 last-write-wins」）
- ❌ **Excel 优先**：Excel 覆盖 HTML 同字段必须走冲突轨迹（本 spec R2 明列）
- ❌ **文件直读回调**：`merge.py` 不 import openpyxl / python-docx / sqlalchemy / repository / outbox
- ❌ **`ack_received` 伪装 `applied`**：commit 前置门 `RematerializeOutcome.assert_ready_for_commit` + `assert_publishable` 三重判据守门
- ❌ **绕过 `ContentMutationService`**：全平台唯一业务内容 commit 边界，无第二路径
- ❌ **repository 自行 commit**：`repository.py` 文件头明列「若仓储自己 commit，任一后续步骤失败就会留下『pointer 指向缺失 artifact』的半成功态（Requirement 5.9 明令禁止）」
- ❌ **表示升级混入业务 commit**：`excel_rematerialize.py` L186-189「纯表示升级的产物不得交 ContentMutationService」

---

## I. 变更控制

- 本契约为 FROZEN。任何修改必须：
  1. 在 requirements.md 增补对应 Requirement
  2. 在 tasks.md 增补对应任务
  3. 通过 code review（≥ 1 位非本 spec owner）
  4. 更新所有引用本契约的测试
- 未评审修改视为破坏 C1 门控，C4 验收不得进入
