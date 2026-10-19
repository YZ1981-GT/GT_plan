# Requirements Document

需求文档：合伙人与经理的编辑权限（partner-manager-edit-permission）

> 工作流：Requirements-First（feature）。验收标准用 EARS 句式（WHEN / WHILE / IF…THEN / WHERE + THE〈系统〉SHALL）。
> 现状基线：`origin/spec/disclosure-note-doc-upload-and-batch-fill` @ `c6f14d5eb`。主工作树 HEAD `d33acb9f1` 落后它 2 个提交（上一轮附注导出 / 交付件门禁的改动只在 origin），本文引用的现状一律按 origin 现读。
> 文中计数都是 2026-10-19 写作时的现算快照，只作对账参照，**禁止写死进判据**；实施时重算。

## Introduction

用户 2026-10-19 原话：「把这些接口逐个放开到复核级。在项目角色映射里把经理（以及合伙人）直接升为编辑级。」

上一轮已把附注编辑器「导出 Word」、交付件「刷新章节 / 批量刷新 / 回填到报告正文」改走交付中心同一判定 `deliverable._guard_action`（本项目成员 review 及以上 + 角色矩阵 + EQCR 只读）。附注编辑器的其余写操作（保存正文和表格、离线导入、校验、从底稿取数、公式、批量写入、内容模板、上年继承等）仍是 edit 级；`assignment_service.ROLE_MAP` 给合伙人 / 经理的项目级别是 review，所以他们在附注编辑器里只能看、不能改。

本 spec 同时落地两条指令：

1. 附注编辑器的写端点逐个改走统一的「附注编辑门禁」：本项目 review 及以上成员即可写，EQCR 只读。
2. `ROLE_MAP` 把合伙人（含签字合伙人）和经理升为 edit 级。这一条全平台生效：底稿编辑、调整分录等所有 edit 级操作都对他们放开；质控、EQCR 保持 review。

两条叠加后，经理 / 合伙人编辑附注靠第 2 条就已成立；第 1 条额外放开的只有 review 级的**质控**（EQCR 由门禁显式排除）。这个叠加口径列为待确认项 Q1、Q2。

### 现状核实（grep + 真库现查）

| # | 事实 | 出处 |
|---|------|------|
| F1 | `ROLE_MAP`：`signing_partner` / `partner` / `合伙人` →（partner, review）；`manager` / `项目经理` →（manager, review）；`qc` / `质控` →（qc, review）；`eqcr` / `独立复核合伙人` →（partner, review）；`auditor` / `审计员` / `assistant` / `助理` →（auditor, edit）；未登记角色 →（readonly, readonly） | `backend/app/services/assignment_service.py` |
| F2 | 第二份映射 `_ASSIGNMENT_ROLE_MAP`：级别与 F1 相同，但缺 `signing_partner`，未登记角色兜底为（auditor, edit），与 F1 的 readonly 不一致；在没有 project_users 行时被 `/api/role-context/project/{id}` 使用，前端 `roleContext.canEditInProject` 读它 | `backend/app/services/role_context_service.py` |
| F3 | `_sync_project_users`：新行按映射写；已有行只升不降（`PERM_ORDER`）⇒ 经理改派为 EQCR 后仍保留原级别；同步后不失效权限缓存。`invalidate_permission_cache` 生产代码零调用（仅 `tests/test_phase8.py`）；委派保存端点 commit 后只调 `invalidate_auto_cache` | `assignment_service.py`、`deps.py`、`routers/assignments.py` |
| F4 | 唯一索引：`project_assignments (project_id, staff_id) WHERE is_deleted=false`（一人一项目只有一条现行委派）；`project_users (project_id, user_id) WHERE is_deleted=false` | 真库 `pg_indexes` |
| F5 | 鉴权：`assert_project_permission` 级别 edit 3 > review 2 > readonly 1；admin 跳过成员校验；非 readonly 级先判归档（423）；Redis 缓存键 `perm:{user_id}:{project_id}`，`PERM_CACHE_TTL = 300` 秒 | `backend/app/deps.py` |
| F6 | 附注写门禁 `_assert_project_edit` = `require_project_access("edit")` → `require_operation("note:edit")` → `check_consol_lock`（403 先于 423） | `backend/app/routers/disclosure_notes.py` |
| F7 | 操作矩阵取并集：`ROLE_OPERATIONS[全局角色] ∪ PROJECT_ROLE_OPERATIONS[项目角色]`。EQCR 在 project_users 里是 partner，`PROJECT_ROLE_OPERATIONS["partner"]` 含 `note:edit` ⇒ 矩阵对 EQCR 放行，现在只靠 edit 级把它挡住；`ROLE_OPERATIONS["qc"]`、`["eqcr"]` 不含 `note:edit`；`PROJECT_ROLE_OPERATIONS` 没有 `qc` / `auditor` 键 | `backend/app/services/permission_matrix_service.py` |
| F8 | EQCR 判定 `EqcrWorkbenchService._is_user_eqcr_on` 只认委派角色 `eqcr`，漏掉 `ROLE_MAP` 接受的 `独立复核合伙人`；交付中心 `_guard_action` 用它 | `backend/app/services/eqcr_workbench_service.py`、`routers/deliverable.py` |
| F9 | 前端可写态：`DisclosureEditor.vue` 的 `isEqcrRole` 只看全局角色 `'eqcr'`；`canEdit`（`useAuditContext.ts`）= 未归档 且 `canDo('edit','workpaper')`，`canDo` 只按全局角色查 `permission-matrix.ts`，不看项目级别；`effectiveCanEdit` = `canEdit` 且未被多窗口锁强制只读。`roleContext.canEditInProject`（按项目级别）存在但编辑器没用；`/api/projects/{pid}/my-role` 只返回项目角色与全局角色 | `audit-platform/frontend/src/views/DisclosureEditor.vue`、`composables/useAuditContext.ts`、`stores/roleContext.ts`、`stores/project.ts` |
| F10 | 附注相关路由（文件名 `note*` / `*note*` / `disclosure*`）26 个文件、168 个端点；写方法端点 101 个 = 项目级门禁 59（edit 41、readonly 16、`_guard_action` 2）+ 仅校验登录 36 + 无任何鉴权依赖 6（AST 现算） | 仓库外一次性 AST 探针（已删除；口径由需求 1 的清册脚本固化） |
| F11 | 连续审计「复制团队」只复制 project_users（角色 + 级别），不复制 project_assignments ⇒ EQCR 在新项目里变成无委派的 partner + review，F8 判不出 | `backend/app/services/continuous_audit_service.py` |
| F12 | 全平台 edit 级门禁调用点：`require_project_access("edit")` 224 + `assert_project_permission(..., "edit")` 5 + `authorize_wp_edit` 8 + `require_wp_edit_permission` 4 + `_assert_project_edit` 5 = 246 处、100 个文件（AST 现算，不含 `attachments.py` / `office_preview.py` / `custom_query.py` 直接比较 `permission_level` 的位置） | 仓库外一次性 AST 探针（已删除；口径由需求 9.1 的影响清单固化） |
| F13 | 真库：现行委派 86 条，角色全是 `manager`——84 条在已软删的测试项目上（对应 project_users 为 auditor + readonly），2 条在现行项目（宜宾、和平）上，人是 admin（manager + review）；EQCR 委派 0 条；全局角色只有 admin / auditor | `audit_platform` 现查 |
| F14 | 迁移：已提交最高 V191；工作树另有并发会话未跟踪的 V192~V196 ⇒ 写作时新版本号不得早于 V197 | `git ls-tree` + `migration_status` |
| F15 | 钉住旧口径的测试：`test_phase8_endpoint_role_levels.py::test_premise_reviewer_roles_are_review_level`、`test_deliverable_generation_membership_auth.py::test_premise_reviewers_are_review_level`（断言合伙人 / 经理 / 质控 / EQCR 为 review）；`test_disclosure_notes_hardening.py`（`project_factory` 断言级别 == "edit"、调用序列 `project_edit`）；`test_disclosure_notes_project_gate_contract.py::BODY_GATES`；`test_project_endpoint_authorization_baseline.py` 的 `_PROJECT_LEVEL_TOKENS`、`_IDENTITY_ONLY_BASELINE = 214`、`_PREFIXED_IDENTITY_ONLY_BASELINE = 277` | `backend/tests/` |
| F16 | 🔴 委派端点 `GET` / `POST /api/projects/{project_id}/assignments` 只校验登录 ⇒ 任何登录用户能给自己委派任意项目的任意角色。这是既有缺口（现在委派成审计员就已拿到 edit），本 spec 把经理映射到 edit 后不增加新的提权路径，但影响面相同 | `backend/app/routers/assignments.py` |

### 附注写端点快照

**表 A：单体附注编辑器的 edit 级写端点（「逐个放开到复核级」的对象，现算 24 个）**

| # | 方法与路径 | 现门禁 | 文件 |
|---|-----------|--------|------|
| A1 | `POST /api/disclosure-notes/generate` | `_assert_project_edit` | `disclosure_notes.py` |
| A2 | `PUT /api/disclosure-notes/{note_id}` | `_assert_project_edit` | 同上 |
| A3 | `DELETE /api/disclosure-notes/{project_id}/{year}/sections/{note_section}` | `_assert_project_edit` | 同上 |
| A4 | `PATCH /api/disclosure-notes/{project_id}/{year}/sections/{note_section}` | `_assert_project_edit` | 同上 |
| A5 | `PATCH /api/disclosure-notes/{project_id}/{year}/restore/{note_id}` | `_assert_project_edit` | 同上 |
| A6 | `POST /api/disclosure-notes/{project_id}/{year}/pull-from-workpapers` | `require_project_access("edit")` | 同上 |
| A7 | `POST /api/disclosure-notes/{project_id}/{year}/validate` | `require_project_access("edit")` | 同上 |
| A8 | `PUT /api/disclosure-notes/findings/{validation_id}/confirm` | `_assert_validation_project_access(edit)` | 同上 |
| A9 | `POST /api/disclosure-notes/{project_id}/{year}/{note_section}/clear-formulas` | `require_project_access("edit")` | 同上 |
| A10 | `POST /api/disclosure-notes/{project_id}/{year}/{note_section}/restore-auto` | `require_project_access("edit")` | 同上 |
| A11 | `POST /api/disclosure-notes/{project_id}/{year}/{note_section}/apply-formulas` | `require_project_access("edit")` | 同上 |
| A12 | `PUT /api/disclosure-notes/{project_id}/{year}/{note_section}/formulas` | `require_project_access("edit")` | 同上 |
| A13 | `POST /api/disclosure-notes/{project_id}/{year}/offline-import/execute` | `require_project_access("edit")` | `note_offline.py` |
| A14 | `POST /api/projects/{project_id}/disclosure-note-import/parse-upload` | edit + `note:edit` + 合并锁 | `note_text_batch.py` |
| A15 | `POST /api/projects/{project_id}/disclosure-note-import/parse-knowledge` | 同上 | 同上 |
| A16 | `POST /api/projects/{project_id}/disclosure-note-text-batch/preview` | 同上 | 同上 |
| A17 | `POST /api/projects/{project_id}/disclosure-note-text-batch/apply` | 同上 | 同上 |
| A18 | `POST /api/projects/{project_id}/note-content-templates/snapshot-preview` | `require_project_access("edit")` | `note_content_templates.py` |
| A19 | `POST /api/projects/{project_id}/note-content-templates` | `require_project_access("edit")` | 同上 |
| A20 | `DELETE /api/projects/{project_id}/note-content-templates/{template_id}` | `require_project_access("edit")` | 同上 |
| A21 | `POST /api/projects/{project_id}/notes/import-prior-year` | `require_project_access("edit")` | `note_advanced.py` |
| A22 | `POST /api/projects/{project_id}/notes/inherit-prior-year` | `require_project_access("edit")` | 同上 |
| A23 | `POST /api/projects/{project_id}/notes/cross-references/update` | `require_project_access("edit")` | 同上 |
| A24 | `POST /api/disclosure-notes/{project_id}/{year}/{note_id}/toggle-mode` | `require_project_access("edit")` | `note_wp_mapping.py` |

其余 17 个 edit 级写端点：合并附注 14 个（`consol_notes.py` 5、`consol_note_sections.py` 4、`consol_note_detail_templates.py` 5，见 Q5）+ `account_note_mapping.py` 3 个（前端零调用点）。

**表 B：只校验登录、没有项目级门禁的单体附注写端点（现算 26 个，处置见 Q3）**

| 类别 | 端点 | 编辑器调用 |
|------|------|-----------|
| B1 写本项目附注内容 / 结构 | `POST /api/projects/{project_id}/note-template/save`（新增 / 删除自定义章节）、`POST .../note-template/restore`（结构版本回滚）、`POST /api/disclosure-notes/{project_id}/{year}/refresh-from-workpapers`（🔄 刷新、恢复自动提数、章节重算、就绪度面板修复表头）、`POST .../{note_section}/refresh-from-workpaper`（当前章节刷新）、`POST /api/projects/{project_id}/apply-group-baseline`（集团基线弹窗） | 已确认 |
| B2 待核对调用方 | `note_wp_mapping.py` 的 `PUT .../wp-mapping`、`POST .../refresh-all-bindings`；`note_trim.py` 2 个；`note_custom_section.py` 3 个；`note_conversion.py` 3 个；`group_note_baseline.py` 的 `POST /api/group-note-baselines` | design 阶段核对 |
| B3 非附注内容写入 | `note_section_lock.py` 4 个（章节锁）、`note_data_lock.py` 3 个（签字锁定 / 快照）、`note_group_template.py` 3 个（集团模板保存 / 下发 / 脱离） | design 阶段逐个定级 |

另有 `disclosure_notes.py` 的 `PUT .../formula-gray`（只按全局角色 `require_role`）和合并附注 9 个仅登录端点，不在本 spec 范围。

**表 C：前端在调、后端不存在的附注路径（死链，只登记）**：`PUT .../sections/{id}/move`（`useNoteTree` 拖拽）、`POST .../sections/{id}/fork`（`NoteVersionTreePanel`）、`POST .../template-conversion/preview|execute`（`NoteTemplateSwitch`，后端实际是 `/api/projects/{pid}/notes/conversion/*`）、`POST /api/disclosure-notes/{pid}/sections/{id}/force-lock`（`NoteSectionLockBadge`）、`POST .../preview-text` 与 `PUT .../text-template-vars`（`NoteParagraphVarsEditor`）、`POST .../ai/suggest-dynamic-rows` 与 `.../ai/check-consistency`（`NoteAiSuggestionPanel`）。

### 待用户确认的口径

下文需求按「默认」一栏写成。用户改选备选时，对应需求按备选重写。

| 编号 | 问题 | 默认（下文按此写） | 备选 |
|------|------|-------------------|------|
| Q1 | 质控能否编辑附注 | 能：本项目 review 级、非 EQCR 即放行；操作矩阵 `note:edit` 保持现状——全局角色为 `qc` 的用户仍被矩阵拒绝（真库全局角色只有 admin / auditor，按现有数据，凡委派为质控的成员都能编辑） | ① 矩阵同时给项目角色 qc 加 `note:edit`，全局 qc 也能编辑；② 质控不能编辑附注 |
| Q2 | EQCR 是否仍只读 | 只读：附注全部写端点 403。判定为「全局角色是 eqcr，或在本项目持有 EQCR 别名委派」，任一成立即是 EQCR；附注门禁与交付中心门禁共用同一判定 | 只看本项目委派，不看全局角色 |
| Q3 | 表 B 的仅登录写端点 | B1 纳入附注编辑门禁（顺带堵上跨项目写入：非成员、readonly 成员此后被拒）；B2 核对调用方后同规则处置；B3 逐个定级，不套用附注编辑门禁 | 只登记不改，另立 spec |
| Q4 | 委派同步遇到已有成员行 | 按本次委派角色精确写入，可升可降 | 保持只升不降，只在改派为 EQCR 时强制回落到 review |
| Q5 | 合并附注 14 个 edit 级写端点 | 不纳入「放开到复核级」：仍是 edit 级，经理 / 合伙人靠第 2 条已能用，质控不能用 | 一并改走附注编辑门禁 |
| Q6 | 连续审计复制团队时的 EQCR | 跳过上年项目里持有 EQCR 委派的成员，复制结果给中文提示「独立复核合伙人需在新项目重新委派」 | 连同 EQCR 委派一起复制 |
| Q7 | 🔴 F16 委派端点只校验登录 | 本 spec 不改（先要定「谁有权委派」），在 design 登记为高风险项 | 本 spec 一并补项目级鉴权（本项目经理 / 合伙人 / admin） |

## Glossary

- **角色映射（Role_Map）**：`assignment_service.ROLE_MAP`，委派角色 →（项目角色 ProjectUserRole，项目级别 PermissionLevel）的单一真源。
- **合伙人 / 经理别名集合**：`signing_partner`、`partner`、`合伙人`、`manager`、`项目经理`。
- **质控别名集合**：`qc`、`质控`。
- **EQCR 别名集合**：`eqcr`、`独立复核合伙人`，由角色映射推导。
- **审计员别名集合**：`auditor`、`审计员`、`assistant`、`助理`。
- **项目级别**：`project_users.permission_level`，edit > review > readonly。
- **现行委派**：`project_assignments` 中 `is_deleted = false` 的行，经 `staff_members.user_id`（`is_deleted = false`）关联到用户。
- **委派同步（Assignment_Sync）**：`AssignmentService._sync_project_users`，保存委派时 upsert project_users。
- **委派保存端点（Assignment_Save_Endpoint）**：`POST /api/projects/{project_id}/assignments`。
- **角色上下文服务（Role_Context_Service）**：`RoleContextService`，供 `/api/role-context/*` 使用。
- **级别回填迁移（Level_Backfill_Migration）**：本 spec 新增的运行时迁移（`backend/migrations/V*.sql` 与配对 `R*.sql`），把已有委派对应的 project_users 行改到新映射。
- **项目级鉴权（Project_Access_Check）**：`deps.assert_project_permission` 及其依赖工厂 `require_project_access`。
- **权限缓存（Permission_Cache）**：Redis 键 `perm:{user_id}:{project_id}`，TTL 为 `PERM_CACHE_TTL`（300 秒）。
- **EQCR 判定（Eqcr_Resolver）**：判断某用户在某项目是否为 EQCR 的单一函数（本 spec 收口）。
- **交付中心门禁（Deliverable_Guard）**：`routers/deliverable.py::_guard_action`。
- **附注编辑门禁（Note_Edit_Gate）**：本 spec 新设的附注写端点统一判定，替代 `_assert_project_edit` 与附注写端点上的 `require_project_access("edit")`。
- **操作矩阵（Operation_Matrix）**：`permission_matrix_service` 的 `ROLE_OPERATIONS` / `PROJECT_ROLE_OPERATIONS`，经 `deps.require_operation` 生效。
- **附注写端点清册（Note_Write_Inventory）**：本 spec 产出的附注相关写端点清单，逐个记录现门禁与目标门禁。
- **附注编辑器（Disclosure_Editor）**：`DisclosureEditor.vue` 及其子组件、composable。
- **连续审计复制（Continuous_Audit_Copy）**：`continuous_audit_service` 的「复制团队」步骤。
- **端点级测试**：用 TestClient 真发请求、让真实 `assert_project_permission` 判定的测试；只替换下层取数点（当前用户、权限缓存、归档守卫、RLS、委派查询、业务 service），不 override `require_project_access` 或附注编辑门禁本身。
- **磁盘变异证明**：把生产代码改坏后写回磁盘、跑测试确认按预期打红、再逐字节恢复。
- **鉴权基线守卫**：`backend/tests/test_project_endpoint_authorization_baseline.py`。
- **附注门禁契约守卫**：`backend/tests/test_disclosure_notes_project_gate_contract.py`。

## Requirements

### 需求 1：附注写端点清册

**用户故事：** 作为平台维护者，我希望附注相关写端点有一份逐个列出「现门禁 → 目标门禁」的清册，以便「逐个放开」可核对、不漏不多。

#### 验收标准

1. THE 附注写端点清册 SHALL 由清册生成脚本以 AST 扫描 `backend/app/routers/` 直接子文件中、文件名匹配 `note*`、`*note*`、`disclosure*` 的 `.py` 路由现算生成。扫描不递归子目录：子目录里的 EQCR 复核笔记、应收 / 应付票据等同名文件不属附注。同时匹配多个模式的文件只计一次。对每个 POST / PUT / PATCH / DELETE 端点，清册记录：所在文件与函数名、方法、完整路径、现门禁形态与级别（按第 8 条识别）、目标门禁（按第 9 条确定）。其中：
   - 完整路径 = 路由注册时追加的前缀 + 路由器前缀 + 装饰器路径，路径参数名保持原样。
   - 所在路由器未被注册挂载的端点，标注「未注册」。
   - 一个函数声明多条路由或多个方法时，每个（方法，完整路径）各记一条。
   - 清册内容只由仓库现状决定：行按文件名、完整路径、方法排序，不含生成时间、机器名、绝对路径等随运行变化的内容；同一仓库状态下重复生成，结果逐字节相同。
2. THE 附注写端点清册 SHALL 把每个写端点按 S → C → G → E → R → X → I 的顺序，归入第一个定义被满足的类别，且只归入这一类：
   - S（桩端点）：函数体只抛出「已废弃」或「未实现」错误，且签名不声明数据库会话、上传文件或后台任务依赖。
   - C（合并附注）：所在文件名以 `consol_` 开头。
   - G：已走交付中心门禁。
   - E（edit 级，改走附注编辑门禁）：已走附注编辑门禁，或项目级判定的最高级别为 edit；最高级别为 review 的也归此类。
   - R（readonly 级预览类）：项目级判定的最高级别为 readonly。
   - X（只按全局角色判定的全局配置）：有全局角色判定，没有项目级判定。
   - I：只校验登录，或没有任何鉴权依赖。
3. THE 附注写端点清册 SHALL 对 E、I 两类逐个列出附注编辑器范围内的全部前端调用点（文件与调用形态）。没有调用点的端点标明「编辑器内无调用点」，并注明附注编辑器范围外的前端源码里有没有调用点（有则列出文件）。判定口径：
   - 附注编辑器范围 = `DisclosureEditor.vue` 及其 import 传递闭包（含动态 import，不含测试文件）。
   - 调用形态分三种：路径字面量、路径常量、封装函数（注明函数名）。
   - 经封装函数发起的请求，以范围内调用该函数的位置为调用点；范围内没有调用者的封装函数不产生调用点。
   - 调用与端点的匹配条件是方法相同、路径逐段对应：插值段可对应任一段，查询串不计。
   - 一个调用同时匹配多个端点时，取字面段对应最多的那个；仍并列的全部列出，并标注「歧义」。
4. THE 附注写端点清册 SHALL 把附注编辑器范围内、指向本平台后端、按第 3 条规则没有命中任何扫描端点的写方法调用分三项单列，三项都不计入任何门禁类别。绝对地址和发往其他服务的请求不算在内。三项是：
   - 表 C：与后端全部已注册路由比对后找不到同路径路由；或路径存在但方法不符（这种情况注明后端现有的方法）。
   - 表 D：命中扫描范围之外的已注册端点，记录该端点所在文件、现门禁形态与级别。
   - 未解析：无法静态确定方法或路径的调用，逐个列出位置。
5. WHEN 清册生成脚本完成扫描与归类、尚未写出清册，THE 清册生成脚本 SHALL 校验以下四项全部成立：
   - 各类计数之和等于扫描到的写端点总数。
   - 每个（方法，完整路径）在清册中恰好出现一次。
   - 附注编辑器范围内的写方法调用数，等于「命中扫描端点」「表 C」「表 D」「未解析」四项之和。
   - 每条与类别默认值不同的目标门禁声明，都对应一个现存的写端点。
6. WHEN 清册生成脚本开始一次生成或检查，THE 清册生成脚本 SHALL 先用内置合成样例自检。样例与期望结果至少包括：
   - 无任何鉴权依赖 → I
   - 只依赖登录 → I
   - 只在 docstring 与注释里写有 `require_project_access("edit")`、签名与函数体都没有挂载 → I
   - 签名依赖 `require_project_access("edit")` → E
   - 函数体经同文件辅助函数以 edit 级判定 → E
   - 调用附注编辑门禁 → E
   - 签名依赖 `require_project_access("readonly")` → R
   - 函数体只抛出「未实现」错误 → S
   - 挂载未登记的依赖 → 按第 7 条报未识别

   任一样例判错时，脚本以非零退出码失败，用中文列出样例名、期望结果与实际结果，且不写出清册。
7. IF 出现以下任一情况，THEN THE 清册生成脚本 SHALL 以非零退出码失败，用中文逐项输出原因（列出文件、函数名、未识别的名称或不成立的校验项），不把相关端点归入 I 类或任何兜底类别，不写出清册，已提交的清册保持不变：
   - 扫描到的文件数或写端点数为 0。
   - 任一匹配文件无法解析。
   - 某写端点挂载了脚本未登记的依赖。
   - 某个项目级判定的级别无法静态确定。
   - 路由或依赖用了脚本不支持的写法声明。
   - 某写端点按第 2 条无法归入任何一类。
   - 第 5 条任一校验不成立。
8. THE 清册生成脚本 SHALL 只按实际生效的依赖与调用识别现门禁：
   - 识别来源有四处：签名参数默认值里的依赖（不论参数名，包括 `_` 这类占位名）；装饰器与路由器声明的依赖；路由注册时附加的依赖；函数体内对门禁函数的调用（包括经同文件辅助函数的间接调用）。
   - 函数体内的门禁调用如果位于条件分支或异常处理之内，标注「条件执行」。
   - 级别取自这些调用里可以静态确定的级别值（字面量或同文件常量）。
   - 注释、docstring 和其他字符串里出现的门禁名称一律不计。
   - 同一端点有多个项目级判定时，按最高级别记录，并逐项列出操作矩阵权限点、合并锁、全局角色与仅登录判定。
9. THE 附注写端点清册 SHALL 为每个写端点记录目标门禁：
   - 默认值：E 类为附注编辑门禁；G、R、S、C、X 类为保持现门禁；I 类没有默认值，逐个声明为附注编辑门禁、design 定级的门禁与级别，或「待 design 核对」。
   - 与类别默认值不同的声明，逐个附上理由（需求编号、Q 编号或「范围外」条目）。
   - 每个端点标注现门禁是否已经等于目标门禁。
   - E、I 两类中目标门禁为附注编辑门禁的端点，就是需求 6.1、8.1、12.2 所指的附注编辑门禁覆盖集合。
10. WHEN 清册生成脚本以检查模式运行，THE 清册生成脚本 SHALL 不写任何文件，只把现算结果与已提交的清册逐条比对。比对项为：方法、完整路径、文件与函数名、现门禁形态与级别、类别、目标门禁、调用点，以及表 C、表 D、未解析各项。两者不一致，或已提交的清册不存在时，以非零退出码失败，并用中文逐条列出新增、消失与变化的条目；完全一致时以零退出码结束。

### 需求 2：角色映射升级与单一真源

**用户故事：** 作为业务合伙人或项目经理，我希望被委派到项目后直接拥有编辑级，以便能编辑底稿、调整分录和附注。

#### 验收标准

1. THE 角色映射 SHALL 把 `signing_partner`、`partner`、`合伙人` 映射为（partner, edit），把 `manager`、`项目经理` 映射为（manager, edit）。
2. THE 角色映射 SHALL 保持其余取值不变：`qc`、`质控` →（qc, review）；`eqcr`、`独立复核合伙人` →（partner, review）；`auditor`、`审计员`、`assistant`、`助理` →（auditor, edit）；不属于合伙人 / 经理、质控、EQCR、审计员四个别名集合的委派角色字符串 →（readonly, readonly）。查找按字符串精确匹配：空串、大小写不同或带首尾空白的别名变体（如 `Manager`、首尾带空格的 `manager`）一律按未登记处理。
3. THE 角色上下文服务 SHALL 在两处委派兜底（①单项目角色查询：用户在该项目没有未删除的项目成员行时；②全局角色上下文中仅由委派补充的项目条目）直接读取角色映射得到项目角色与级别，并以字符串取值返回（与来自项目成员行的返回口径相同，如 `manager`、`edit`）；未登记委派角色随之兜底为（readonly, readonly），不再是现状的（auditor, edit）。
4. FOR ALL 委派角色字符串 r，对在未删除项目上「没有未删除的项目成员行、只有一条角色为 r 的现行委派」的用户，角色上下文服务在第 3 条两处兜底返回的（项目角色，项目级别）SHALL 与角色映射对 r 给出值（r 未登记时为（readonly, readonly））的字符串取值逐项相等（模型对拍性质）。用例由三部分组成：角色映射的每个键逐个断言；固定样例（空串、`Manager`、首尾带空格的 `manager`、`readonly`、`观察员`）逐个断言；hypothesis 另生成长度 0~30 个字符的任意字符串（`max_examples=5`）。
5. THE 两处前提测试（写作时名为 `test_phase8_endpoint_role_levels.py::test_premise_reviewer_roles_are_review_level`、`test_deliverable_generation_membership_auth.py::test_premise_reviewers_are_review_level`，可随新口径改名）SHALL 按期望表逐键断言角色映射的项目角色与级别（现状只断言级别、只覆盖英文键）。期望表为第 1、2 条四个别名集合的全部键（含中文别名）及其取值，另加实现时登记、取值为（readonly, readonly）的键；角色映射的键集合与取值须与期望表完全相等，增删任一键或改动任一取值即打红。测试还须断言取值为（partner, review）的键恰好是 EQCR 别名集合（需求 7.2 的推导前提）。
6. THE 以「合伙人 / 经理在项目里是 review 级」作定级理由的文字 SHALL 改写：改写后不再称合伙人 / 经理为 review 级，所述理由与该端点现行判定一致（例如保留 review 门禁是为了放行 review 级的质控 / EQCR，或注明本 spec 未改该端点级别）。范围为后端生产代码与测试的注释、docstring、断言失败信息，前端源码注释，以及 steering 记忆的现行规则条目；历史档案（dev-history 与已归档 spec）按 append-only 不改。写作时已知位置：`review_workflow.py`、`wp_procedures.py`、`wp_cross_check.py` 的模块注释；`deliverable._guard_action`、`disclosure_notes.export_word` 的 docstring；第 5 条两处前提测试所在文件的模块 docstring 与断言失败信息（如「review 级成员（合伙人/经理/质控/EQCR）」「edit 级成员（审计员/助理）」）；`.kiro/steering/memory.md` 的项目级鉴权定级条。
7. THE 角色映射 SHALL 是后端生产代码与前端源码（均不含测试文件）中唯一一份「委派角色 → 项目角色与级别」映射。计数口径：以四个别名集合中 2 个及以上委派角色为键、且取值给出项目级别（单独的级别，或项目角色与级别的组合）的映射各计一份；委派通知与页面显示用的中文显示名映射不计（写作时现算 2 份：角色映射与角色上下文服务内的 `_ASSIGNMENT_ROLE_MAP`）。该约束由一条扫描测试钉住，并配磁盘变异证明：在角色上下文服务里写回一份等价映射后，该测试红在「映射不唯一」的断言上。
8. WHEN 一个全局角色为 auditor、只参与一个项目的用户在该项目没有未删除的项目成员行、只有一条委派角色为 `signing_partner` 的现行委派，THE 系统 SHALL 按角色映射判定该用户：角色上下文服务的两处兜底都返回（partner, edit）；全局角色上下文的最高角色为 partner；审计日志哈希链校验对该用户在该项目放行（现状：缺该键时兜底为（auditor, edit），哈希链校验拒绝；写作时真库 0 例）。
9. WHEN 第 6 条改写完成，THE 验收 SHALL 在第 6 条范围内检索同一注释块、docstring、断言失败信息或记忆条目里同时出现「合伙人」或「经理」与「review」的文字，逐条判读后，仍称合伙人 / 经理为 review 级的命中为 0；检索口径与命中清单（含判读结论）记入验收记录。

### 需求 3：委派同步写入级别

**用户故事：** 作为项目经理，我希望保存团队委派后，成员的项目级别立即与其委派角色一致，以便改派（包括改派为 EQCR）不留下旧权限。

#### 验收标准

1. WHEN 委派保存处理批次内某用户、且该用户在该项目没有未删除的成员行（含只有已删除成员行的情形），THE 委派同步 SHALL 为其新建一条成员行，项目角色与项目级别取角色映射对本次委派角色给出的值（未登记角色取（readonly, readonly）），已删除的成员行保持删除状态与各项原值（只有已删除成员行的情形以真 PG 验证：测试库建出的成员唯一索引不带删除条件，会误拒新建）。
2. WHEN 委派保存处理批次内某用户、且该用户在该项目已有一条未删除的成员行，THE 委派同步 SHALL 在该行上把项目角色与项目级别改写为角色映射对本次委派角色给出的值，级别可升可降（Q4 默认）：本次委派角色未登记时改写为（readonly, readonly），原为 edit 或 review 同样降级；全局角色不影响本条（admin 同样改写）；该行的循环范围、科目范围与有效期保持改写前的值。
3. IF 本次委派角色属于 EQCR 别名集合，THEN THE 委派同步 SHALL 把该用户在该项目的成员行写为（partner, review），不论改写前该行为 edit、review、readonly 级还是尚不存在。
4. THE 委派同步 SHALL 保持以下成员行的项目角色、项目级别与删除状态为保存前的值：批次外用户（批次中没有任何人员关联到的登录用户，含本次保存中被移出团队的用户）在该项目的成员行、任何用户在其他项目的成员行、已删除的成员行。
5. FOR ALL 委派批次（0~6 条委派；委派角色取自角色映射的全部已登记别名与随机未登记字符串；批次内每个用户改写前的成员行取「无 / readonly / review / edit」之一；可含未关联登录用户的人员、经两份人员库记录出现两次的用户；另置 1~2 名批次外成员，并在另一项目为批次内用户各置一条成员行），委派同步完成后 SHALL 同时成立：批次内每个用户在该项目恰有一条未删除的成员行，其（项目角色，项目级别）等于按第 1~3、8、9 条由角色映射算出的值；批次外成员行与另一项目的成员行与同步前逐值相同；打乱批次内委派顺序后结果不变（hypothesis，`max_examples=5`；另以固定样例必测三种情形：edit 改派为 EQCR、edit 改派为未登记角色、同一用户 manager 与 eqcr 各一条）。
6. WHEN 委派保存提交成功，THE 委派保存端点 SHALL 在提交之后、返回成功响应之前删除每个受影响（用户，项目）的权限缓存条目；受影响指本次委派同步为该用户新建了成员行，或该用户在该项目的项目角色或项目级别与保存前不同（失效步骤失败按需求 5.4 处理，降级后的并发回写按需求 5.2 处理）。
7. IF 委派保存未能提交（EQCR 独立性校验拒绝、写库报错或提交报错），THEN THE 委派保存端点 SHALL 返回表示保存失败的响应，不删除也不写入任何权限缓存条目，该项目的委派与全部成员行保持保存前的值。
8. IF 批次中两份及以上人员库记录关联到同一登录用户（`staff_members.user_id` 无唯一约束，F4 只保证同一人员库记录在同一项目只有一条现行委派），THEN THE 委派同步 SHALL 为该用户在该项目只写一组与委派先后顺序无关的（项目角色，项目级别）：其中任一委派角色属于 EQCR 别名集合时写（partner, review）；否则取角色映射对这些委派角色给出的最高级别，项目角色在该级别的候选中按 partner、manager、qc、auditor、readonly 的先后取第一个（细化时补的默认口径，备选为整批拒绝保存）。
9. IF 批次中某人员的人员库记录未关联登录用户，THEN THE 委派同步 SHALL 跳过该人员，不新建也不改写任何成员行，该人员的委派照常保存，委派保存不因此失败。

### 需求 4：已有委派的级别回填

**用户故事：** 作为平台管理员，我希望已经委派的合伙人和经理在升级后不必重新保存委派就拿到编辑级，同时 EQCR 不被误升。

#### 验收标准

1. THE 级别回填迁移 SHALL 以运行时迁移交付：`backend/migrations/V{n}__*.sql` 配对同号的 `R{n}__*.sql`；`n` 取实施时 `migration_status` 现扫的最高版本 + 1，现扫范围是主工作树磁盘（含未跟踪文件）与目标分支最新提交的并集（写作时不得早于 V197，见 F14）；提交前再核一次 `n` 没有被并发会话占用（同号会让启动时整轮迁移扫描报错，所有待执行迁移都不执行）；两个脚本在同一数据库上重复执行都不报错；配对回滚脚本在没有回填记录时（包括正向迁移从未执行）执行成功，且不改动任何成员行。
2. WHEN 级别回填迁移执行，THE 级别回填迁移 SHALL 把同时满足以下条件的项目成员行级别改为 edit，项目角色改为角色映射对该委派角色给出的项目角色（partner 或 manager）：①成员行未删除；②该用户在该项目至少有一条现行委派，角色属于合伙人 / 经理别名集合；③该用户在该项目没有 EQCR 别名的现行委派。判定口径：委派角色与别名按精确字符串比对，与角色映射查表一致（大小写和首尾空白都不归一，例如 `Manager` 按未登记角色处理）；项目是否已软删不影响判定（写作时有 84 行在已软删测试项目上）；全局角色不参与判定（与委派同步口径一致）；同一用户在该项目同时持有映射为 partner 和映射为 manager 的现行委派时，项目角色取 partner；项目角色与级别已经等于目标值的行不改写，也不计为被改动行。
3. WHEN 级别回填迁移执行，THE 级别回填迁移 SHALL 把在该项目至少持有一条 EQCR 别名现行委派的用户的未删除成员行级别置为 review，不论该用户是否还持有其他角色的现行委派；原级别为 edit 或 readonly 的行都改为 review，项目角色保持迁移前的值；原级别已经是 review 的行不计为被改动行；判定口径同第 2 条（写作时真库 0 行）。
4. THE 级别回填迁移 SHALL 只改动第 2、3 条所述行的项目角色与级别；其余成员行（没有现行委派的、只持有质控 / 审计员 / 未登记角色现行委派的、已软删的）的项目角色与级别保持迁移前的值；迁移不新增、不删除、不恢复成员行（有现行委派但没有成员行的用户不补建），也不改动委派、人员、用户和项目数据。
5. WHEN 级别回填迁移改动成员行，THE 级别回填迁移 SHALL 在与改动相同的事务内，为每个被改动行在数据库中留存一条回填记录，至少包含该成员行的唯一标识及其迁移前的项目角色与级别；未被改动的行不产生记录；该行已有回填记录时保留原记录，不用新值覆盖。
6. FOR ALL 迁移前数据集，在期间没有其他写入的前提下，先执行级别回填迁移（一次或连续两次）、再执行配对回滚脚本 SHALL 使数据库回到迁移前状态：全部成员行的项目角色与级别等于迁移前的值，且不残留回填记录（往返性质）。数据集至少覆盖：成员行未删除 / 已软删；委派现行 / 已软删，角色取自合伙人 / 经理、EQCR、质控、审计员别名集合，以及未登记字符串和已登记别名的大小写、首尾空白变体；人员记录未删除 / 已软删 / 未关联用户；同一用户经多条人员记录在同一项目持有多条现行委派；项目现行 / 已软删。
7. FOR ALL 迁移前数据集（维度同第 6 条），级别回填迁移执行两次后的成员行与回填记录 SHALL 与执行一次后相同：第二次执行不改动任何成员行，不新增回填记录，也不覆盖第一次记录的迁移前值（幂等）。
8. WHEN 级别回填迁移在本地真库执行完毕，THE 验收记录 SHALL 包含：①重启前现查的迁移前快照（同 F13 口径）；②全量重启 `start-dev.bat` 之后（热重载不跑迁移）现查到版本 `n` 已登记为已应用，且没有该版本的迁移失败记录；③被改动行数，与回填记录数核对相等，并按「第 2 条 / 第 3 条」和「现行项目 / 已软删项目」分组；④与迁移前快照逐行对账，再与 F13 对账（写作时的期望：现行项目 2 行 admin 由 manager + review 改为 manager + edit；已软删测试项目 84 行由 auditor + readonly 改为 manager + edit；第 3 条 0 行），差异逐条说明原因。本地真库只执行正向迁移，不执行配对回滚脚本；往返与幂等只在测试库或不提交的事务内验证。
9. WHEN 配对回滚脚本执行，THE 级别回填迁移的配对回滚脚本 SHALL 只把「有回填记录、且项目角色与级别仍等于第 2、3 条目标值」的成员行恢复为记录中的迁移前值；没有回填记录的行，以及迁移后已被其他途径（如委派同步）改成其他值的行，保持现值；执行完成后不保留任何回填记录（包括未恢复的行）。
10. IF 级别回填迁移或其配对回滚脚本中任一改写或记录步骤出错，THEN THE 级别回填迁移 SHALL 让该脚本整体失败，不在脚本内吞掉错误继续执行：该脚本本次对成员行与回填记录的改动全部不生效；正向迁移出错时，版本 `n` 不登记为已应用，失败记入迁移失败记录，下次全量启动时重试；回滚脚本出错时，版本 `n` 保持已应用。
11. FOR ALL 迁移前数据集（维度同第 6 条），级别回填迁移执行一次后，每个成员行的项目角色与级别 SHALL 等于按第 2、3、4 条由迁移前数据逐行推导出的期望值，且被改动行的集合 SHALL 等于回填记录覆盖的成员行集合（模型对拍）。

### 需求 5：权限缓存与生效时效

**用户故事：** 作为合伙人或经理，我希望级别变化后尽快生效；作为质量管理负责人，我希望降级（尤其改派为 EQCR）立即生效，以便独立性不因缓存出现空窗。

#### 验收标准

1. WHEN 级别回填迁移或委派同步提高了某（用户，项目）的项目级别（含新建成员行），THE 项目级鉴权及其他读取权限缓存、按其中级别作判定的位置（以下合称「级别判定点」；写作时现读另有 `authorize_wp_edit`、`authorize_wp_read` 2 处，实施时现算；高级查询 `OwnershipGuard` 只看缓存条目是否存在、不看级别，不属此列）SHALL 满足以下时限。判定的「开始」「结束」指进入、离开该判定（级别判定点或 EQCR 判定的一次调用）的时刻，因后端进程退出而中止的判定算作结束：
   - 记 T 为「变更已提交，且变更提交前已开始的判定均已结束」的时刻。晚于 T + 300 秒（即现行 `PERM_CACHE_TTL`）开始的每一次判定，结论与直接按变更后成员行判定的结论相同；该（用户，项目）在此期间持续有请求，也不延长这一时限。
   - T 至 T + 300 秒之间开始的判定，按变更后或变更前的级别得出结论都符合本条。
   - 委派同步造成的提高，在缓存失效成功、且没有提交前已开始的判定在提交之后写回旧级别时，委派保存端点返回成功响应之后开始的判定即按新级别得出结论。
   - 该（用户，项目）此后又有级别或委派变更提交的，按最近一次变更适用第 1、2 条。
2. IF 级别回填迁移或委派同步降低了某（用户，项目）的项目级别（edit → review、edit → readonly、review → readonly），或委派同步使该用户在该项目新被 EQCR 判定为 EQCR，THEN THE 级别判定点与 EQCR 判定 SHALL 对该变更提交成功之后开始、且早于该（用户，项目）下一次级别或委派变更提交的每一次判定，得出与直接按变更后的成员行与现行委派判定相同的结论（变更提交前已开始的判定不受本条约束）。本条覆盖以下情形：
   - 并发回写：提交前已在途的判定，在提交之后才把旧级别写回缓存。
   - 跨重启残留：后端重启前写入、级别回填迁移执行并重启后仍在有效期内的缓存条目（Redis 条目跨后端重启保留，迁移脚本触达不了 Redis）。
   - 缓存失效步骤失败（第 4 条）。
   - 迁移执行方式：级别回填迁移不论经后端启动流程执行（迁移完成前后端不接收请求），还是在后端运行期间以命令行等方式执行，本条都适用（细化时补的默认口径，备选为只约束经后端启动流程执行的迁移：运行期间另行执行的须随后全量重启后端，验收记录写明执行方式）。
3. IF Redis 不可用（客户端未初始化、连接失败、命令报错，或单次缓存读写在 1 秒内未完成），THEN THE 级别判定点 SHALL 降级为直接按该（用户，项目）未删除成员行的现值判定：结论与缓存未命中时相同；调用方请求不因 Redis 不可用得到服务器错误响应；单次判定因等待缓存而增加的耗时合计不超过 1 秒（1 秒为细化时补的默认口径，备选为 0.3 秒，与审计日志、高级查询缓存等模块探活 Redis 的上限一致）。
4. IF 委派保存提交成功后缓存失效步骤失败（任一受影响（用户，项目）的条目删除报错、因 Redis 不可用未能执行，或自失效步骤开始 1 秒内未得到删除确认；条目本不存在算删除成功），THEN THE 委派保存端点 SHALL 按以下处理（1 秒与「含降级的批次同样返回成功」均为细化时补的默认口径，备选分别为 0.3 秒、在成功响应中附中文提示「成员权限刷新失败」）：
   - 照常返回成功响应，委派与成员行保持已提交的值，不回滚。
   - 为每个未得到删除确认的（用户，项目）各记录一条告警及以上级别的日志，含用户标识与项目标识。
   - 不含降级的批次（受影响项全是新建成员行、级别提高或级别不变的角色变更）：旧级别至多按第 1 条的时限继续生效。
   - 含降级的批次（至少一个受影响（用户，项目）的级别降低，或其新被 EQCR 判定为 EQCR）：同样返回成功响应，且仍须满足第 2 条。
5. WHEN 委派保存端点执行缓存失效，THE 委派保存端点 SHALL 只删除需求 3.6 所定义受影响（用户，项目）的权限缓存条目；对批次内未受影响用户在该项目的条目、批次外用户在该项目的条目、任何用户在其他项目的条目，不删除、不改写，也不重置或延长其剩余有效期（hypothesis 性质测试，`max_examples=5`：随机生成委派批次与预置缓存条目，覆盖上述三类与受影响条目，断言执行后被删除的条目集合恰为「受影响（用户，项目）」与「预置条目」的交集）。
6. FOR ALL 由以下步骤任意交错构成的时序（一次降级变更的提交：委派同步的 edit → review、edit → readonly、review → readonly 或改派为 EQCR，或级别回填迁移的 edit → review；变更来自委派同步时，其后的缓存失效，成功或按第 4 条失败；0~3 个在降级提交前开始的判定，其「读取成员行」「写回缓存」两步可落在提交与失效之前或之后；1~3 个在降级提交成功之后开始的判定），THE 级别判定点与 EQCR 判定 SHALL 使每个降级提交成功之后开始的判定，结论与直接按降级后的成员行与现行委派判定的结论相同（hypothesis，`max_examples=5`）。另以固定样例必测：
   - ① 在途判定读到 edit 后暂停，改派为 EQCR（edit → review）提交且缓存失效完成后它才写回 edit，随后开始的 edit 级判定须被拒绝（403）。
   - ② 后端重启前为一名持有 EQCR 委派、成员行为 edit 的用户写入 edit 级缓存条目，级别回填迁移在启动流程中把其降为 review，重启后首个 edit 级判定须被拒绝。
   - ③ 含降级的批次缓存失效失败，提交成功之后开始的 edit 级判定须被拒绝。
   - ④ 质控（review）改派为 EQCR、级别不变，提交成功之后开始的附注编辑写请求须被附注编辑门禁按 EQCR 只读拒绝。
7. WHERE 级别判定点保留权限缓存，THE 验收 SHALL 让第 1、2、4、5、6 条的用例经过生产代码中的缓存读写函数本身运行（可替换缓存存储，替身须按生产 Redis 客户端的取值形态返回所存的值），并在每组用例前先跑一条对照用例：预置一条与成员行不同的级别、不做任何失效直接判定，结论须按预置级别得出，以证明用例确实命中缓存。（现状现读：生产 Redis 客户端以 `decode_responses=True` 创建、按字符串取回值，`_get_cached_permission` 再对取回值调用 `.decode()`，抛出的异常被吞掉、返回未命中 ⇒ 读路径恒按未命中处理，每次判定都查库，第 1、2 条的陈旧窗口现状下不出现，修复读路径后即会出现；`test_phase8.py` 的 `test_set_and_get_cache` 断言「None 或 edit」，两种结果都算通过，没能发现这一点。以上是读代码得出的推断，写作时未实测；若实测属实，对照用例在现状下必然失败，design 须先裁定修复读路径还是移除权限缓存。）

### 需求 6：附注编辑门禁（放开到复核级）

**用户故事：** 作为业务合伙人、项目经理或质控，我希望在附注编辑器里保存正文和表格、离线导入、校验、从底稿取数等操作对我放行，以便直接改附注。

#### 验收标准

1. THE 附注编辑门禁 SHALL 是覆盖集合内每个端点对目标项目唯一的项目级判定入口。覆盖集合按需求 1.9 确定，即清册 E、I 两类中目标门禁为附注编辑门禁的端点（写作时为表 A 的 24 个、需求 8.1 的 B1 5 个，以及需求 8.2 核对后标注纳入的 B2 端点）。判定顺序固定为：确定目标项目（取路径上的 project_id；路径上没有时按第 8 条）→ 归档（第 7 条）→ 项目成员 review 及以上（第 4 条，admin 跳过）→ EQCR 排除（第 5 条）→ 操作矩阵 `note:edit`（第 12 条，对覆盖集合内全部端点判定）→ 合并锁（第 6 条，只对合并锁适用集合）→ 放行（第 2、3 条）；各步都针对同一个目标项目。实施后以下三项同时成立：
   - 后端全部路由中挂载附注编辑门禁的写端点集合等于覆盖集合；清册检查模式对覆盖集合内每个端点都标注「现门禁已等于目标门禁」。
   - 按需求 1.8 的识别口径，覆盖集合内端点对目标项目不再有其他项目级判定（如 `require_project_access(...)`、`assert_project_permission`、`_assert_project_edit`、按对象反查的鉴权辅助函数）；操作矩阵与合并锁判定也只由附注编辑门禁执行，端点不另挂。端点对目标项目以外资源（知识库文档、内容模板、集团基线等）的可见性与操作权限判定保持现状，不在本条约束内。
   - 附注编辑门禁的调用不处于条件分支或异常处理之内，且先于该端点的一切业务调用；门禁之前至多执行一条第 8 条所述的最小投影查询。
2. WHEN 调用者在未归档的目标项目上有一条未删除的 review 级或 edit 级成员行、未被 EQCR 判定为本项目 EQCR、操作矩阵对其放行 `note:edit`，且该端点不属于合并锁适用集合或目标项目未被合并锁定，THE 附注编辑门禁 SHALL 放行：端点照常执行业务处理；同一用户在其余条件相同时，级别为 review 与为 edit 对同一请求得到相同的业务处理与响应；「最近一次编辑」等操作人信息记为调用者本人（Q1 默认：委派为质控的 review 级成员只要操作矩阵放行即按本条放行；操作矩阵内容保持现状，矩阵拒绝的情形见第 12 条）。
3. WHEN 全局角色为 admin、未被 EQCR 判定为本项目 EQCR 的调用者在未归档的目标项目上调用覆盖集合内的端点，且该端点不属于合并锁适用集合或目标项目未被合并锁定，THE 附注编辑门禁 SHALL 放行：不要求其是本项目成员，不看其成员行级别，操作矩阵对 admin 恒放行（admin 被判为 EQCR 时按第 5 条处理，与交付中心门禁一致）。
4. IF 调用者不是 admin，且在未归档的目标项目上没有未删除的成员行（含只有已删除成员行的情形）或其成员行级别为 readonly（级别按项目级鉴权的现行口径取得，含权限缓存，级别变更的生效时效见需求 5），THEN THE 附注编辑门禁 SHALL 返回 403「权限不足」（沿用项目级鉴权的现有固定文案），不再进行 EQCR、操作矩阵与合并锁判定，业务效果按第 11 条为零。
5. IF 调用者在未归档的目标项目上通过了第 4 条的判定（admin，或 review 级及以上成员），且被 EQCR 判定（需求 7.1）为本项目 EQCR，THEN THE 附注编辑门禁 SHALL 返回 403，信息为固定中文文本并写明「独立复核合伙人（EQCR）在本项目只读」，不再进行操作矩阵与合并锁判定，业务效果按第 11 条为零。操作矩阵对项目角色 partner 放行 `note:edit`（F7），EQCR 只靠本条拦截；EQCR 判定查询出错时按需求 7.6 拒绝；readonly 成员或非成员即使是 EQCR，也按第 4 条返回「权限不足」。
6. IF 调用者已通过第 4、5、12 条的判定，该端点属于合并锁适用集合，且目标项目处于合并锁定（项目的合并锁定标记为真，沿用 `check_consol_lock` 的判定），THEN THE 附注编辑门禁 SHALL 返回 423，信息沿用现有的中文合并锁定提示（含「合并锁定」字样，前端据此刷新锁定态），业务效果按第 11 条为零。口径：
   - 合并锁适用集合 = 按需求 1 对附注编辑门禁改造前的代码现算的清册中，现门禁列有合并锁判定的覆盖集合端点（写作时 13 个：A1~A5、A9~A12、A14~A17）；改造后清册中列有合并锁判定的覆盖集合端点须与之逐个相等。
   - 按 Q3 纳入、改造前未判合并锁的端点（如 B1）不新增合并锁判定（细化时补的默认口径，备选为：其中写本项目附注内容的端点一并判合并锁）。
   - 被第 4、5、12 条拒绝的调用者在合并锁定项目上得到对应的 403，不得到本条的 423（403 先于 423）；本条的 423 与第 7 条先于成员判定的归档 423 不是同一判定。
7. WHILE 目标项目已归档（项目状态为 archived），THE 附注编辑门禁 SHALL 对任何调用者（含 admin、非成员、readonly 成员与 EQCR）返回 423「项目已归档，无法编辑」（沿用现有归档提示），业务效果按第 11 条为零；归档判定先于成员、EQCR、操作矩阵与合并锁判定（沿用 `_check_project_not_archived` 的现顺序），第 4、5、6、12 条只适用于未归档项目；对象 id 端点的对象不存在时，先按第 8 条返回 404。
8. WHERE 端点路径上没有 project_id，THE 附注编辑门禁 SHALL 按以下方式确定目标项目，再对该项目执行全部判定：
   - project_id 在请求体里：以请求体中的 project_id 为目标项目。
   - 只能从对象 id 反查：先以一条只取对象所属项目这一列的最小投影查询取得目标项目，该查询之前不执行任何其他读写；对象不存在时返回 404 与中文提示（沿用现有文案，如「附注章节不存在」「校验结果不存在」），不进入后续判定（沿用 `_assert_object_project_access` 的反查语义）。
   - 调用方在查询参数或请求体中另附的项目标识不改变对象 id 端点的目标项目：对象属于调用者无权的项目时，即使另附一个调用者有权的项目标识，也按对象所属项目判定并拒绝。
9. THE 清册 G 类端点（写作时为两个导出 Word 端点）SHALL 继续只经交付中心门禁判定，不调用附注编辑门禁；其判定结论除需求 7 对 EQCR 判定的收口（如委派角色为 `独立复核合伙人` 的成员由放行变为拒绝）外，保持本 spec 实施前的现状。
10. THE 附注门禁契约守卫与鉴权基线守卫 SHALL 把附注编辑门禁登记为项目级门禁（无论以依赖还是函数体调用的形态挂载，两处守卫都能识别），并各配一条可伪证断言。断言按语法树判定（注释、docstring 与其他字符串里出现的名称不计）附注编辑门禁的函数体同时满足：①在条件分支与异常处理之外调用 `assert_project_permission`，级别为 review（字面量或同文件常量）；②调用 EQCR 判定。级别改成其他值、该调用移入条件分支、或删去 EQCR 判定调用，断言即打红；需求 12.5 的前两处磁盘变异下，这两条断言同样红在该断言上。契约守卫现有的四项判据（project_id 不在路径上的端点不靠路径依赖取项目、门禁先于一切业务调用、门禁之前至多一次最小投影读、反查先于鉴权）改为针对附注编辑门禁后继续成立，判据强度不降。
11. IF 附注编辑门禁拒绝请求（第 4、5、6、7、12 条的 403 / 423，或第 8 条的对象不存在），或门禁任一步骤的查询出错（Redis 不可用时按需求 5.3 降级查库，不算出错），THEN THE 附注编辑门禁 SHALL 不放行，并使该请求不产生任何业务效果：
   - 业务处理（含上传文件的解析与保存）一次也不执行；目标项目与其他项目的业务数据与请求前逐值相同；不发布业务事件（如附注章节保存事件）。
   - 不读取也不写入该请求所带幂等键的记录：被拒绝的调用者即使带上他人用过的幂等键，也只得到拒绝响应，拿不到已存的响应。
   - 拒绝响应带固定的中文原因，不含附注正文、表格数据等业务内容。
12. IF 调用者在未归档的目标项目上通过了第 4、5 条的判定，但操作矩阵按「全局角色的操作权限 ∪ 其成员行项目角色的操作权限」不含 `note:edit`（Q1 默认，矩阵内容不改。例如全局角色为 `qc` 或 `readonly`、项目角色为 `qc` 或 `auditor` 的成员；项目角色为 partner 或 manager 时并集含 `note:edit`，矩阵放行），THEN THE 附注编辑门禁 SHALL 返回 403，原因为中文并写明其角色没有编辑附注的操作权限，可与第 4 条「权限不足」、第 5 条 EQCR 提示区分；不再进行合并锁判定，业务效果按第 11 条为零。本条同样适用于改造前未判操作矩阵的覆盖集合端点（写作时如 A6~A13、A18~A24 与 B1）：这些端点上此类成员由放行变为拒绝（按 F13，写作时真库全局角色只有 admin / auditor，受影响 0 人）。
13. FOR ALL 判定输入组合，THE 附注编辑门禁的结论 SHALL 等于按第 7、4、5、12、6 条的先后取第一个成立的拒绝（归档 423、「权限不足」403、EQCR 403、操作矩阵 403、合并锁 423），都不成立时放行；其中 admin 跳过第 4 条，操作矩阵对 admin 恒放行，「被判为 EQCR」按需求 7.1 取「全局角色为 eqcr，或持有本项目 EQCR 别名现行委派」。
   - 输入维度：目标项目是否归档；是否合并锁定；端点是否属于合并锁适用集合；调用者全局角色（全局角色枚举的全部取值）；调用者在目标项目的成员行（无 / 已删除 / 未删除；未删除时级别取 readonly、review、edit，项目角色取角色映射可写出的 partner、manager、qc、auditor、readonly）；是否持有本项目 EQCR 别名现行委派。
   - 用 hypothesis 模型对拍（`max_examples=5`）：用例请求都通过请求格式校验；端点取自覆盖集合，至少覆盖路径、请求体、对象 id 三种项目确定方式，以及属于 / 不属于合并锁适用集合两种情形。
   - 另以固定样例必测（未写明的维度取：未归档、未合并锁定、无 EQCR 委派、全局角色 auditor）：
     - admin 在已归档项目 → 归档 423
     - 非成员在合并锁定项目 → 403「权限不足」
     - 项目角色 partner、review 级、持有本项目 EQCR 委派的成员在合并锁定项目 → EQCR 403
     - admin 持有本项目 EQCR 委派 → EQCR 403
     - 全局角色 qc、项目角色 qc 的 review 级成员 → 操作矩阵 403
     - 项目角色 qc 的 review 级成员 → 放行
     - 项目角色 qc 的 review 级成员在合并锁定项目上调用不属于合并锁适用集合的端点 → 放行

### 需求 7：EQCR 判定以项目委派为准

**用户故事：** 作为质量管理负责人，我希望 EQCR 的独立性不因其全局角色、或委派时用了中文别名而失效。

#### 验收标准

1. THE EQCR 判定 SHALL 在以下任一条件成立时把（用户，项目）判为本项目 EQCR，两条都不成立时判为非 EQCR（Q2 默认）：
   - 用户的全局角色为 `eqcr`；
   - 该用户在该项目至少有一条现行委派（术语表口径），其委派角色按字符串精确匹配属于 EQCR 别名集合。与需求 2.2、4.2 同口径：大小写不同或带首尾空白的变体（如 `EQCR`、首尾带空格的 `eqcr`）不算。

   判定细则：
   - 同一用户经多条人员库记录在该项目持有多条现行委派时，任一条属于 EQCR 别名集合即判为 EQCR，其余委派是什么角色都不影响（与需求 3.8、4.3 一致）。
   - 全局角色为 admin 不豁免（与需求 6.3 一致）。
   - 只看本项目：在其他项目持有的 EQCR 委派不影响本项目的结论。
   - 已删除的委派、已删除的人员库记录不计入：被移出团队的原 EQCR 不再判为 EQCR（其成员行仍保留的后果见范围外「委派被移除后 project_users 行不撤销」）。
   - 项目是否已软删（与需求 4.2 一致）、人员状态（在职 / 休假 / 离职）、成员行的项目级别，都不影响结论。
   - 成员行的项目角色不参与判定：项目角色枚举含 `eqcr`，但成员行项目角色为 `eqcr`、没有 EQCR 别名现行委派的用户判为非 EQCR（细化时补的默认口径，备选为成员行项目角色为 `eqcr` 也判为 EQCR）。
2. THE EQCR 别名集合 SHALL 由角色映射推导：取角色映射中取值为（partner, review）的全部委派角色键。推导以需求 2.1、2.2 的取值为前提，由需求 2.5 的前提测试钉住；写作时推导结果为 `eqcr`、`独立复核合伙人`。EQCR 判定所用的别名集合只有这一处来源，按 AST 扫描（注释与 docstring 不计）的口径为：
   - 后端生产代码（不含测试）中，以 EQCR 别名集合全部成员为元素或键的字面量集合、列表、元组、映射，只有角色映射一处；
   - 字面量 `独立复核合伙人` 作为委派角色取值（集合元素、映射键、比较操作数）只出现在角色映射中；显示名映射的取值与用户可见文案不计。

   前端的 EQCR 判定按需求 10 处理，不在本条扫描范围。该约束由一条扫描测试钉住，并配两项磁盘变异证明：①在 EQCR 判定所在模块写回一份 EQCR 别名字面量集合后，扫描测试红在「别名集合来源不唯一」的断言上；②把角色映射中 `独立复核合伙人` 的取值改为（partner, edit）后，第 4 条的 `独立复核合伙人` 用例红在「应拒绝」的断言上（证明判定跟随角色映射，没有另存的别名副本）。
3. THE 交付中心门禁与附注编辑门禁 SHALL 调用同一个 EQCR 判定得出「是否本项目 EQCR」（需求 10.1 的判定查询同样经此判定）。门禁内不另行判断：不另查委派角色，也不另比较全局角色是否为 `eqcr`。对同一（用户，项目），两门禁得出的 EQCR 结论相同。
   - 交付中心门禁配一条与需求 6.10 同口径的可伪证断言（按 AST 判定）：其函数体调用 EQCR 判定，且不含与字面量 `eqcr` 的比较。
   - 在相同的成员行与委派数据下，全局角色不是 `eqcr`、且在本项目没有 `独立复核合伙人` 现行委派的用户，交付中心门禁各操作的结论与改动前相同（以 `eqcr` 委派的用户改动前已是只读）。
4. WHEN 在项目 P 持有角色为 `独立复核合伙人` 的现行委派的用户发起写操作（项目未归档、未合并锁定；全局角色取 partner、auditor、admin 各测一次；成员行按需求 3.3 为（partner, review）），THE 交付中心门禁与附注编辑门禁 SHALL 拒绝该写操作，业务写入一次也不执行（现状 `_is_user_eqcr_on` 只认 `eqcr`，该别名会漏判）：
   - 附注编辑门禁：附注编辑门禁覆盖集合（需求 1.9）中的每个端点都返回 403，信息按需求 6.5；
   - 交付中心门禁：读操作（列表、预览、下载）以外的全部操作返回 403，包括附注导出 Word（清册 G 类）与交付件的刷新章节、批量刷新、回填到报告正文，拒绝信息沿用交付中心门禁现状；读操作照常放行。

   同一组用例改用 `eqcr` 委派重跑，逐端点结论与 `独立复核合伙人` 相同。配磁盘变异证明：把 EQCR 判定的委派条件改回只认 `eqcr` 后，`独立复核合伙人` 用例红在「应拒绝」的断言上。
5. FOR ALL 按下列维度生成的数据，THE EQCR 判定对（被测用户，项目 P）给出的结论 SHALL 等于模型「全局角色为 `eqcr`，或存在一条 P 上的现行委派，其人员库记录关联到被测用户、委派角色属于 EQCR 别名集合」（hypothesis 模型对拍，`max_examples=5`；模型里的别名集合取需求 2.5 期望表中取值为（partner, review）的键，不读生产代码）：
   - 全局角色：系统角色的全部取值（admin、partner、manager、auditor、qc、eqcr、readonly）；
   - 被测用户的委派：经 1~2 条人员库记录持有 0~4 条委派。每条的项目取 P 或另一项目；委派与人员库记录各自取未删除或已删除；委派角色取角色映射的全部键、这些键的大小写与首尾空白变体、长度 0~30 个字符的任意字符串。生成数据遵守 F4（同一人员库记录在同一项目至多一条现行委派）；
   - 干扰数据：其他用户在 P 的 EQCR 委派；未关联用户的人员库记录在 P 的 EQCR 委派；被测用户在 P 的成员行（项目角色可取 `eqcr`，级别任取）。

   另以固定样例逐个断言：
   - ① 全局 auditor，P 上委派 `独立复核合伙人` → 是
   - ② 全局 admin，P 上委派 `eqcr` → 是
   - ③ 全局 eqcr，无任何委派 → 是
   - ④ 全局 partner，P 上委派 `manager` → 否
   - ⑤ 全局 auditor，P 上委派 `EQCR` → 否
   - ⑥ 全局 auditor，P 上的 `eqcr` 委派已删除 → 否
   - ⑦ 全局 auditor，P 上 `eqcr` 委派的人员库记录已删除 → 否
   - ⑧ 全局 auditor，另一项目委派 `eqcr`、P 上委派 `manager` → 否
   - ⑨ 全局 manager，经人员库记录甲在 P 上委派 `manager`、经人员库记录乙在 P 上委派 `eqcr` → 是
   - ⑩ 全局 auditor，P 上成员行项目角色为 `eqcr`、无委派 → 否
6. IF EQCR 判定执行中出错（包括委派查询报错、数据库连接中断），THEN THE 附注编辑门禁与交付中心门禁 SHALL 拒绝本次请求，不按「非 EQCR」放行：返回失败响应（不返回成功响应），业务写入一次也不执行，本请求已做的数据库改动全部不生效。交付中心门禁现在遇到查询报错时请求就会失败，本条把这一行为钉住。验证时在 EQCR 判定的下层查询注入异常，两门禁各至少测一个写操作，断言响应不是成功响应、业务 service 调用 0 次。
7. THE EQCR 本人正向授权（只允许本项目 EQCR 本人执行或查看的操作，即第 8 条清单中用途为「EQCR 本人正向授权」的全部位置）SHALL 保持现行判定：只认本项目委派角色 `eqcr`，EQCR 结构化判断提交对 admin 的现有放行照旧；本 spec 对 EQCR 判定的改动不改变它们的任何结论。写作时这些位置包括：EQCR 审批、意见解锁、备忘录定稿、备忘录版本历史、工时开始与结束、EQCR 结构化判断提交、A25 复核表、项目权限接口的 EQCR 专属权限，以及本人 EQCR 项目列表和项目总览中的「本人已确认为 EQCR」。
   - 全局角色为 `eqcr`、在该项目没有 `eqcr` 现行委派的用户：上述操作仍被拒绝，本人 EQCR 项目列表不含该项目，「本人已确认为 EQCR」仍为否。EQCR 判定的全局角色分支只用于只读排除；用在正向授权上就是越权（全局 eqcr 用户能审批自己没被委派的项目）。
   - 以 `独立复核合伙人` 委派的用户：在这些位置的结论保持现状，不被识别为 EQCR（细化时补的默认口径，备选为这些位置改用 EQCR 判定的委派条件，一并识别 EQCR 别名集合）。
8. THE EQCR 消费方清单 SHALL 现算列出后端生产代码（不含测试）中按委派角色判断某人是否为 EQCR 的全部位置。检索口径有三种：委派角色值与字面量 `eqcr` 作相等、不等或成员判断；把 `eqcr` 列入委派角色名单；以委派角色为键取 EQCR 专属权限。每个位置记录：所在文件与函数；用途（EQCR 只读排除 / EQCR 本人正向授权 / 独立性控制 / 含 EQCR 的宽权限名单 / 统计）；是否识别 `独立复核合伙人`；本 spec 的处置与理由。处置口径：
   - EQCR 只读排除：写作时只有交付中心门禁（经 `_is_user_eqcr_on`），改用 EQCR 判定（第 3 条）。
   - EQCR 本人正向授权：按第 7 条保持现状。理由：不识别中文别名只会多拒绝、不会多放行；前端团队委派下拉（项目向导、项目设置）对 EQCR 只提交 `eqcr`；真库 EQCR 委派 0 条（F13）。
   - 独立性控制、含 EQCR 的宽权限名单、统计：保持现状，登记范围外（细化时补的默认口径，备选为本 spec 一并改为识别 EQCR 别名集合）。理由：这些位置的角色口径各自另有缺口，要另行确认业务口径。例如轮换检查不含 `partner` / `合伙人`；EQCR 兼任校验遇到 `独立复核合伙人` 直接放行（按需求 9.5 保持）。

   写作时已知位置（实施时按检索口径重算，与本快照的差异逐条说明）：EQCR 工作台服务的 `_is_user_eqcr_on` 及其调用方、本人 EQCR 项目列表；EQCR 结构化判断提交；EQCR 问题单可见性；EQCR 指标仪表盘；`EqcrIndependenceRule` 与批内预检；轮换检查；独立性签署的复核人查询；门禁规则的独立性声明必需角色；独立性声明的核心角色项目列表；A25 复核表角色；项目权限接口的角色权限表；底稿可见性的主管角色；底稿签字回退角色。
9. WHEN 委派写入提交成功，使某用户在项目 P 开始或不再持有 EQCR 别名现行委派，THE 附注编辑门禁与交付中心门禁 SHALL 对提交之后开始的请求按提交后的委派给出 EQCR 结论。不沿用提交前得出的结论，也不受权限缓存（`PERM_CACHE_TTL` 300 秒）及其失效成败的影响。验证：
   - 全局角色为 auditor、在 P 委派为 `manager`（edit 级）的用户改派为 `eqcr` 并保存成功后，下一次附注写请求返回 403（信息按需求 6.5），下一次交付中心写操作也返回 403。测试中把权限缓存的读取固定为改派前的 edit 级，以证明 EQCR 结论不依赖权限缓存；
   - 该用户再改派回 `manager` 并保存成功后，下一次附注写请求不再因 EQCR 被拒。

### 需求 8：只校验登录的附注写端点纳入门禁（Q3 默认）

**用户故事：** 作为项目合伙人，我希望不是本项目成员的人改不了本项目附注，以便附注数据不被跨项目写入。

#### 验收标准

1. THE 附注编辑门禁 SHALL 覆盖表 B 的 B1 类端点（写作时 5 个：`note-template/save`、`note-template/restore`、`refresh-from-workpapers`、`{note_section}/refresh-from-workpaper`、`apply-group-baseline`），清册把它们的目标门禁声明为附注编辑门禁。其中：
   - 判定针对路径中的项目。集团基线应用只判被写入的路径中项目，不判基线所属的母公司项目（细化时补的默认口径，备选为同时要求调用者对基线所属项目有 readonly 及以上权限）。
   - 门禁判定先于业务层的「版本不存在」「基线不存在」处理：被拒的调用者只得到门禁结论，得不到对象是否存在的信息。
   - 不新增合并锁判定（这些端点现在都不判合并锁，与需求 6.1 一致）。
   - 被拒时，该项目的附注章节、自定义附注模板（当前版本与全部历史版本）与附注校验结果都保持请求前状态。
   - 附注编辑器里调用这些端点的按钮类入口，属于需求 10.3~10.5 所称的写入口（写作时：新增 / 删除自定义章节、结构版本回滚、全部刷新、当前章节刷新、同步失败后的重试、试算表重算、章节重算、恢复自动提数、就绪度面板修复表头、集团基线应用）。
   - 本 spec 完成时，清册对 B1 端点都标注「现门禁已等于目标门禁」。
2. WHEN design 阶段按需求 1.3 的口径核对完 B2 类端点的前端调用点（写作时 11 个：取数映射保存 `PUT .../wp-mapping`、全量取数刷新 `POST .../refresh-all-bindings`、裁剪保存与自动裁剪、自定义章节的新建 / 另存为模板 / 应用模板、国企版与上市版互转的预览 / 执行 / 撤销、保存集团基线 `POST /api/group-note-baselines`），THE 附注写端点清册 SHALL 为每个 B2 端点写明处置、判定所针对的项目（取自路径、查询参数、请求体字段，或由对象 id 反查）与理由，此后不再有 B2 端点标为「待 design 核对」。处置规则：
   - 「附注数据」指某项目的附注章节（正文、表格、章节结构与排序、裁剪状态、单元格取数模式）、附注与底稿的取数映射，以及该项目的自定义附注模板。成功调用会新增、修改或删除附注数据的 B2 端点，标注「纳入附注编辑门禁」。
   - 上一项中同时写入附注以外数据（如项目的报表模板类型、报表行次、公式）的端点，可改为声明更严格的门禁并写明理由；改后仍须拒绝非本项目成员、本项目 readonly 成员与本项目 EQCR。
   - 其余 B2 端点声明 design 定级的项目级门禁与级别。
   - 前端没有调用点，不构成保持只校验登录的理由（细化时补的默认口径，备选为无调用点的 B2 端点只登记，改造另立 spec）。
   - 本 spec 完成时，清册对全部 B2 端点标注「现门禁已等于目标门禁」。
3. THE 附注写端点清册 SHALL 对 B3 类端点（写作时 10 个：章节锁的获取 / 释放 / 强制释放 / 心跳，数据锁定的锁定 / 解锁 / 快照，集团模板的保存 / 下发 / 脱离）逐个声明目标门禁与级别、判定所针对的项目（集团模板下发须含每个目标项目，见第 5 条）、是否放行本项目 EQCR，以及理由。不以「待 design 核对」代替，也不默认套用附注编辑门禁。其中：
   - 目标门禁都须含项目级判定，不得保持只校验登录。
   - 端点的说明文字（函数说明或前端文案）自述了角色限制的（写作时：强制释放写明「项目经理 / 管理员」，解锁写明「管理员」），目标门禁须落实该限制，或在理由里写明不落实的依据。
   - 本 spec 完成时，清册对全部 B3 端点标注「现门禁已等于目标门禁」（细化时补的默认口径，备选为 B3 只在清册登记目标门禁，改造另立 spec）。
4. WHEN 本 spec 把端点由「只校验登录」改为项目级门禁，THE 鉴权基线守卫 SHALL 同时满足以下各项。「两维」指守卫的两个「仅登录不校项目」维度：按装饰器路径识别的一维，上限为 `_IDENTITY_ONLY_BASELINE`；按路由前缀识别的一维，上限为 `_PREFIXED_IDENTITY_ONLY_BASELINE`。
   - 在将要提交的那棵树上现算两维清单，两个常量分别改为与现算值相等；不能因为差距仍在「基线 − 现算值 ≤ 20」的容差内就不下调（棘轮只许向下）。
   - 表 B 写端点既不出现在任一维的仅登录清单中，也不出现在无鉴权清单（两维中未引用任何鉴权标识的端点）中。
   - 对比只差本 spec 改动的改动前、改动后两棵树：被移出两维仅登录清单的条目都是本 spec 改造的端点；没有端点新进入仅登录清单或无鉴权清单，包括按需求 6 改走附注编辑门禁的表 A 端点。
   - 表 B 端点所在路由文件里的读方法端点，档位保持改造前的值（细化时补的默认口径，备选为同文件读方法端点一并补 readonly 级项目门禁）。
5. IF 表 B 写端点的一次请求要写入路径中项目以外的项目，或要读取这类项目的附注数据（第 2 条定义），或路径中没有项目 id（项目 id 来自请求体、查询参数或对象 id 反查；写作时如集团模板下发的目标项目、按章节 id 另存章节模板时章节所属的项目、保存集团基线时的来源项目），THEN 该端点的门禁 SHALL 对请求涉及的每个项目逐一判定，各项目适用的级别以清册声明为准：
   - 任一项目判定不通过时整个请求被拒，任何项目的数据都不写入（细化时补的默认口径，备选为逐个项目判定，未通过的计入失败清单，其余项目照常写入）。有项目判为权限不足（含 EQCR 排除）时返回 403；否则沿用该项目单独判定时的结论（如已归档返回 423）。中文错误信息列出未通过判定的项目 id。
   - 集团基线、集团模板、章节模板库这类多项目共用的模板不属于附注数据，读取它们不触发对来源项目的判定（与第 1 条的默认口径一致）。
6. FOR ALL 清册中目标门禁为 design 定级门禁的表 B 写端点（走附注编辑门禁的端点由需求 12.2、12.3 覆盖，不在此列），THE 端点级测试 SHALL 满足以下各项：
   - 逐个断言：对该端点判定的任一项目（第 5 条）不是成员的调用者（admin 除外）返回 403，业务写入一次也不执行，所有项目的数据保持请求前状态。
   - 端点会写入某项目附注数据（第 2 条定义）的，另断言该项目的 readonly 成员与该项目的 EQCR 同样返回 403。
   - 各判定项目的 EQCR 得到的结论与清册声明一致。
   - 按清册目标门禁应放行的身份中，至少一种实际放行：业务处理执行一次且响应成功。
   - 参数化的端点集合等于清册中这类端点的集合，包括两维守卫看不见的端点（项目 id 在查询参数或请求体中）。
   - 逐个端点做磁盘变异证明：把该端点的项目级判定换回只校验登录，确认红在该端点的 403 断言上，再逐字节恢复。
7. WHEN 附注编辑器收到本项目的底稿保存事件，THE 附注编辑器 SHALL 只在需求 10.1 的判定为可编辑时调用 B1 的刷新端点：
   - 判定为不可编辑时（含按需求 10.6 以只读呈现），不调用该端点，也不显示底稿同步失败提示（细化时补的默认口径，备选为照常调用，被拒时静默不提示）。
   - 调用被 403 拒绝时，按需求 10.7 显示后端返回的中文原因，同样不显示底稿同步失败提示。

### 需求 9：全平台 edit 级操作的影响与不变量

**用户故事：** 作为平台维护者，我希望经理 / 合伙人升 edit 的全平台影响有清单、有守卫，以便不会顺带放开不该放开的人。

#### 验收标准

1. THE 影响清单 SHALL 由影响清单生成脚本以 AST 扫描后端生产代码（`backend/app/` 下全部 `.py`，递归含子目录，不含测试）现算生成，逐条列出全部 edit 级判定点。edit 级判定点分两类：
   - 门禁调用点：级别为 edit 的 `require_project_access(...)` 与 `assert_project_permission(...)`，以及固定为 edit 级的 `authorize_wp_edit`、`require_wp_edit_permission`、`_assert_project_edit`。每一处调用或依赖挂载计一处，门禁自身的定义不计。级别取实参中可静态确定的值（字面量或同文件常量，位置参数与关键字参数都认）；级别经同文件辅助函数的参数传入的，按该辅助函数在同文件内各调用方传入的值逐个记录。门禁函数自身实现内的调用：级别取自门禁自身参数的不计（写作时如 `require_project_access` 内部对 `assert_project_permission` 的调用）；级别固定的计入，记为「门禁内部」（写作时如 `require_wp_edit_permission` 内部对 `authorize_wp_edit` 的调用）。
   - 直接比较位置：读取成员行项目级别、并以比较结果决定是否拒绝请求的代码（写作时：`attachments.py`、`office_preview.py` 的本地鉴权辅助函数，`custom_query.py` 的回写准入辅助函数与单元格回写端点）。属性访问与以字面量属性名调用 `getattr` 两种读法都认。每处记录实际比较的级别；级别经参数传入的，按调用方逐个记录；只有 edit 级的计入 edit 级合计（写作时 `office_preview.py` 只以 readonly 调用）。
   - 不计入的读取：门禁函数（含 `authorize_wp_read`）自身实现内的读取与比较；读取成员行级别只用于展示、同步写入或复制的位置（写作时：角色上下文服务、委派同步、连续审计复制）。后者在清单附录逐个列出位置与用途。
   - 识别口径同需求 1.8：签名参数默认值、装饰器与路由器声明的依赖、路由注册时附加的依赖、函数体调用（含经同文件辅助函数的间接调用，注明辅助函数名）；注释、docstring 与其他字符串一律不计。位于条件分支、循环或异常处理之内的，另标注「条件执行」。
   - 每条记录：所在文件与函数；门禁形态；级别；条件执行标注；所门禁的端点；业务域；叠加判定（对全局角色免查项目级别的名单、按全局角色判定的能力、操作矩阵权限点、合并锁）；所门禁的端点是否属于附注编辑门禁覆盖集合（需求 1.9）。所门禁的端点按方法与完整路径记录（完整路径口径同需求 1.1）：路由器声明或注册时附加的依赖，记该路由器的全部端点；同文件辅助函数内的判定点，记其全部调用方端点；「门禁内部」的调用注明经哪个门禁生效。
   - 业务域取端点所在路由模块被注册进的路由注册分组（写作时 5 组：底稿、报表与附注、协作、系统、循环引擎）；未注册的路由与「门禁内部」各单列一组。清单按业务域给出门禁调用点数、直接比较位置数、端点数（按方法与完整路径去重）与文件数的小计与合计（写作时门禁调用点 246 处 / 100 个文件，见 F12，只作对账参照）。
   - 清单内容只由仓库现状决定：按文件、函数、门禁形态排序，同一函数内形态与级别都相同的多处按出现先后编号；不含生成时间、机器名、绝对路径与行号；同一仓库状态下重复生成，结果逐字节相同。
   - 生成脚本另有检查模式，行为同需求 1.10（比对项换为本条所列各字段与附录）；每次生成与检查之前先按第 8 条自检。检查模式由一条随后端测试一起运行的守卫测试调用，该测试同时断言退出码与输出内容（只断言退出码不算）。
2. WHEN 一条委派角色属于合伙人 / 经理别名集合的委派经委派保存端点保存成功，且该用户在该项目没有 EQCR 别名的现行委派，THE edit 级判定点 SHALL 对该用户在该项目（未归档、未合并锁定）上、委派保存端点返回成功响应之后开始的判定放行：业务处理执行一次，响应成功。缓存失效失败或有在途判定写回旧级别时，按需求 5.1 的时限生效。全局角色不具备判定点所要求的全局能力的，按第 6 条处理，不属本条的放行范围。口径：
   - 端到端：委派保存、委派同步与鉴权三步都走生产代码。被判定读取的成员行由本次委派同步写入数据库，不预置成员行。可替换的只有当前用户、权限缓存存储、RLS 上下文设置与目标端点的业务 service；委派查询与委派同步不替换。
   - 代表端点至少两个：一个经 `require_project_access("edit")` 判定的调整分录写端点（如修改或删除调整分录），一个经 `authorize_wp_edit` 判定的底稿保存端点。五个别名（`signing_partner`、`partner`、`合伙人`、`manager`、`项目经理`）各至少经一个代表端点测一次；全局角色取 auditor、manager 各测一次。附注编辑门禁覆盖集合内的端点按需求 6 另测，不在此列。
   - 全局角色不参与成员行级别的确定（与需求 3.2、4.2 一致）：全局角色为 qc 或 eqcr、委派为合伙人 / 经理别名的用户，成员行同样为 edit 级，经 `require_project_access`、`assert_project_permission` 与直接比较位置判定的 edit 级判定点同样放行；`authorize_wp_edit` 按第 6 条仍以全局角色拒绝；附注编辑门禁与交付中心门禁按需求 6、7 判定（全局角色为 eqcr 的被判为 EQCR，写操作被拒）。此为细化时补的默认口径（由需求 3.2、4.2 推出），备选为委派同步对全局角色为 qc 或 eqcr 的用户不升 edit 级（须同时改写需求 3.2、4.2）；写作时真库全局角色只有 admin / auditor（F13），受影响 0 人。
3. WHEN 一条委派角色属于质控别名集合、EQCR 别名集合或未登记的委派经委派保存端点保存成功（含该用户改派前成员行为 edit 级，即原为合伙人 / 经理 / 审计员的人改派，Q4 默认；质控与未登记角色另要求该用户在该项目没有经其他人员库记录持有的合伙人 / 经理 / 审计员别名现行委派，见需求 3.8），THE edit 级判定点 SHALL 对该用户在该项目（未归档、未合并锁定）上、委派保存提交成功之后开始的每一次判定拒绝：返回该判定点现有的 403 拒绝响应（沿用现有文案，如 `require_project_access` / `assert_project_permission` 的「权限不足」、`authorize_wp_edit` 的「无底稿编辑权限」），业务处理一次也不执行。口径：
   - 权限缓存中改派前的 edit 级条目不改变结论（生效时效按需求 5.2）。
   - 不受本条约束的只有两种：全局角色为 admin 的用户；在对全局角色免查项目级别的判定点（第 6 条）上，全局角色在其免查名单内的用户（写作时：全局角色为 partner 的 EQCR 在 `authorize_wp_edit` 与 `custom_query.py` 两处回写准入上放行）。
   - 端到端口径与代表端点同第 2 条。委派角色取 `qc`、`质控`、`eqcr`、`独立复核合伙人` 与一个未登记字符串（如 `观察员`）各测一次；另以改派前成员行为（manager, edit）的用户改派为 `eqcr`、`质控`、未登记角色各测一次。
4. THE review 级端点（Phase 8 的复核保存、关联复核对话、取消关联复核对话、发起独立性签署、程序裁剪、执行跨表校验六个端点，以及交付中心生成类操作，即经交付中心门禁判定、列表 / 预览 / 下载以外的操作）SHALL 保持 review 级判定：不出现在影响清单中，也不改走附注编辑门禁。在未归档、未合并锁定的项目上，对成员行取角色映射对委派角色给出值的成员，结论如下（端点级测试逐端点、逐身份断言）：
   - 合伙人 / 经理别名（edit 级）：Phase 8 六个端点放行（业务处理执行一次、响应成功）。交付中心生成类操作的结论与本 spec 实施前相同：角色矩阵按其全局角色放行、且其未被判为本项目 EQCR 的操作放行，其余拒绝（写作时现读：全局角色为 auditor 时，签字、审批、归档被角色矩阵拒绝）。
   - 质控别名与 EQCR 别名（review 级）：Phase 8 六个端点放行，与实施前相同；交付中心生成类操作对 EQCR 按需求 7.4 拒绝。
   - 未登记角色（readonly 级）与非成员：Phase 8 六个端点返回 403「权限不足」，与实施前相同。
5. THE 底稿职责分离判定（`SoDGuardService.check` 的编制人 / 复核人 / 合伙人审批互斥）与 EQCR 兼任校验（`EqcrIndependenceRule` 的单条与批量两种模式，及批内预检 `validate_eqcr_sod_in_batch`）SHALL 保持现行为：
   - 输入相同时，结论（是否允许、冲突描述、策略码）与本 spec 实施前相同。输入指：职责分离判定为底稿的编制人、复核人、合伙人审批人，操作人与目标角色；兼任校验为本次委派角色与同项目已有或同批的委派角色。
   - 结论不随操作人在项目里的成员行（项目角色与级别）变化。
   - 互斥矩阵、`CONFLICT_ROLES`（`signing_partner`、`manager`、`auditor`）与批内预检的冲突角色（`CONFLICT_ROLES` 加 `qc`）内容不变；既不是 `eqcr`、也不在这些集合里的委派角色（含 `独立复核合伙人`、`partner`、`合伙人`、`项目经理`、`审计员`、`assistant`、`助理`、`质控`）照旧直接放行（需求 7.8 以此为前提）。
   - 委派保存被兼任校验拒绝时，委派保存端点照旧返回兼任冲突的拒绝响应，委派、全部成员行与权限缓存保持保存前的值（与需求 3.7 一致）。
   - 验证：以固定样例表逐项断言，表中期望由本 spec 改动前的代码实测得出后写入测试，至少覆盖互斥矩阵每个键、`eqcr` 与每个冲突角色的双向组合、`独立复核合伙人` 与 `manager` 同批（兼任校验放行）、`eqcr` 与 `qc` 同批（批内预检拒绝，单条与批量模式放行）；另以 hypothesis（`max_examples=5`）对任意成员行级别与项目角色断言职责分离判定的结论不变。
6. THE 影响清单中对全局角色免查项目级别、或按全局角色判定能力的 edit 级判定点 SHALL 保持现行为（登记于范围外，本 spec 不收紧也不放宽），并在影响清单的叠加判定中逐个标注免查名单与能力判定：
   - `authorize_wp_edit`（含经它判定的 `require_wp_edit_permission`）：全局角色 admin / partner 在底稿存在时直接放行，不看是否本项目成员与成员行级别；全局角色不具底稿写能力的（写作时为 qc、eqcr、readonly），成员行为 edit 级也拒绝。
   - `custom_query.py` 两处回写准入：全局角色 admin / partner 免查成员行级别（写作时现读）。
   - 端点级测试以固定样例钉住现行为：全局角色 partner、在目标项目没有成员行的用户，经 `authorize_wp_edit` 判定的端点放行；全局角色 qc、成员行为（manager, edit）的用户，经 `authorize_wp_edit` 判定的端点返回「无底稿编辑权限」。
7. WHEN 本 spec 的后端改动完成，THE 验收 SHALL 在只差本 spec 改动的改动前、改动后两棵树上各生成一次影响清单，逐条对比并满足以下各项，逐条差异与归因记入验收记录：
   - 消失的、或门禁形态与级别改变的 edit 级判定点，只能是附注编辑门禁覆盖集合内端点上被附注编辑门禁替换的判定点。
   - 新增的 edit 级判定点，只能是按需求 8.2、8.3 在附注写端点清册中声明、目标门禁为 edit 级的门禁。
   - 其余判定点的各记录字段逐条相同。所门禁的端点也在比对之列：本 spec 新增的端点（如需求 10.1 的判定查询）不落入已有 edit 级判定点的门禁范围。
   - 在将要提交的那棵树上，检查模式运行通过。
   - 配磁盘变异证明，每次变异后逐字节恢复：在一个不属于上述两类的端点上把 edit 级门禁改为 review 级，检查模式以非零退出码失败，并把该判定点列为消失条目；在一个读端点上新挂 edit 级门禁，检查模式把它列为新增条目。
8. IF 影响清单生成脚本在一次生成或检查中遇到以下任一情况，THEN THE 影响清单生成脚本 SHALL 以非零退出码失败，用中文逐项列出原因（文件、函数、未识别的写法，或判错样例的名称、期望结果与实际结果），不写出清单，已提交的清单保持不变：
   - 内置合成样例自检任一判错。样例与期望结果至少包括：
     - 签名参数默认值依赖 `require_project_access("edit")`（参数名为 `_`）→ 计入一处门禁调用点
     - 函数体内 `assert_project_permission` 以位置参数、关键字参数各给出 edit → 各计入一处
     - 级别为值是 edit 的同文件常量 → 计入
     - 位于 if 分支内的 `assert_project_permission(..., "edit")` → 计入，并标注「条件执行」
     - 路由器声明依赖 `require_project_access("edit")` → 计入一处，所门禁的端点为该路由器全部端点
     - `require_project_access("review")` → 不计
     - 只在注释、docstring 与其他字符串里写有 `require_project_access("edit")` → 不计
     - 同文件辅助函数以属性访问、`getattr` 字面量属性名两种写法读取成员行级别，与 edit 比较不成立即拒绝，在同文件以 edit、readonly 各调用一次 → 记直接比较位置，edit 那次计入合计，readonly 那次不计入
     - 读取成员行级别只用于返回展示 → 列入附录，不计
     - 级别为函数参数、同文件没有调用方 → 报「级别无法静态确定」
   - 扫描到的文件数或门禁调用点数为 0。
   - 任一文件无法解析。
   - 某个门禁调用或直接比较位置的级别无法静态确定（第 1 条所述不计的门禁内部调用除外）。
   - 某处读取成员行项目级别的代码，既不能判定为直接比较位置，也不能判定为附录所列的非鉴权读取。
9. FOR ALL 影响清单中出现的 edit 级门禁形态（另加 review、readonly 两级的 `require_project_access`）与下列身份的组合，THE 端点级测试 SHALL 对每种形态至少一个代表端点断言结论等于模型：
   - 门禁形态：`require_project_access`、`assert_project_permission`、`authorize_wp_edit`、`require_wp_edit_permission`、`_assert_project_edit` 各算一种（清单中出现才测），每个直接比较位置各算一种。附注编辑门禁不在影响清单中，由需求 6.13、12.2 覆盖。
   - 代表端点：除该形态外不叠加其他鉴权或可见性判定的端点；没有这样的端点时，替换叠加判定的下层取数点使其放行，并在测试中注明。目标项目未归档、未合并锁定；权限缓存不预置条目；业务 service 打桩并计数。
   - 身份维度：全局角色取系统角色全部取值（admin、partner、manager、auditor、qc、eqcr、readonly）；在目标项目的成员行取「无」「已删除」，或未删除且级别取 edit、review、readonly，项目角色取项目角色枚举任一值。
   - 模型（按先后取第一个成立的）：全局角色为 admin → 放行；该形态对全局角色免查项目级别、且全局角色在免查名单内（第 6 条）→ 放行；该形态按全局角色判定能力、且全局角色不具该能力（第 6 条）→ 拒绝；成员行未删除、且级别不低于该端点要求的级别 → 放行；其余 → 拒绝。项目角色不影响结论。
   - 放行：业务处理执行一次，响应成功。拒绝：返回该形态现有的拒绝响应，业务处理 0 次。
   - hypothesis 生成组合（`max_examples=5`）。另以固定样例对每种 edit 级形态逐个必测（全局角色均为 auditor，成员行取角色映射对委派角色给出的值）：质控别名（qc, review）、EQCR 别名（partner, review）、未登记角色（readonly, readonly）、无成员行 → 拒绝；合伙人别名（partner, edit）、经理别名（manager, edit）、审计员别名（auditor, edit）→ 放行。
   - 参数化的 edit 级门禁形态集合等于影响清单中出现的门禁形态集合：清单出现新形态而测试未覆盖，即打红。
   - 对每个独立实现级别比较的位置（`assert_project_permission`、`authorize_wp_edit` 与各直接比较位置）各做一次磁盘变异证明：把其中对 edit 的比较改为 review，确认红在质控固定样例「应拒绝」的断言上，再逐字节恢复。

### 需求 10：附注编辑器的可写态与后端一致

**用户故事：** 作为合伙人、经理或质控，我希望附注编辑器的按钮状态与后端是否放行一致；作为 EQCR，我希望看到的就是只读副本。

#### 验收标准

1. THE 附注编辑门禁 SHALL 提供一个只读判定查询，对「当前登录用户 × 请求指定的目标项目」返回三项：能否编辑附注、不能时的中文原因、是否被判定为本项目 EQCR。口径：
   - 「能否编辑」：在成员行、委派与项目状态不变时，等于附注编辑门禁对同一调用者、同一目标项目、覆盖集合（需求 1.9）中不属于合并锁适用集合的端点给出的结论，即按需求 6.13 依次判归档、成员级别、EQCR、操作矩阵；合并锁不参与（细化时补的默认口径，备选为查询另返回目标项目是否合并锁定，编辑器据此只禁用目标属于合并锁适用集合的写入口）。
   - 「中文原因」：结论为不能编辑时，与附注编辑门禁对同一调用者、同一项目拒绝写请求时返回的原因文本逐字相同（归档、「权限不足」、EQCR 只读、操作矩阵不放行四种之一）；能编辑时为空。
   - 「是否 EQCR」：取需求 7.1 的 EQCR 判定（需求 7.3），对通过查询自身鉴权的调用者一律给出，不因项目已归档、级别为 readonly 或操作矩阵不放行而省略。
   - 查询自身要求调用者在目标项目有未删除的成员行（readonly 及以上）或全局角色为 admin；不满足时返回 403「权限不足」，需求 12.4 对拍时视同「不能编辑」。项目已归档时照常返回结论（不能编辑，原因为归档提示），不返回 423。
   - 任一判定步骤出错（含按需求 7.6 处理的 EQCR 判定出错）时返回失败响应，不返回「能编辑」；查询不改变任何业务数据。
   - 「走同一判定函数」配一条与需求 6.10 同口径的可伪证断言（按语法树判定，注释、docstring 与其他字符串不计）：查询端点的函数体调用附注编辑门禁的判定函数与 EQCR 判定；除查询自身的 readonly 级鉴权外，不另调用 `assert_project_permission`，不另查委派角色，不与字面量 `eqcr` 比较。删去判定函数调用、或改为直接判 edit 级，断言即打红。
2. THE 附注编辑器 SHALL 只以第 1 条的查询结论决定可写态（再叠加项目已归档与多窗口锁强制只读），不再以全局角色、前端操作矩阵或其他前端角色数据自行推断：
   - 附注编辑器挂载时、目标项目变化时，对当前目标项目发起判定查询。
   - 尚未得到结论期间按不可编辑呈现：写入口禁用，悬停提示写明正在确认编辑权限；不显示「📋 只读副本」标识，不显示失败提示。
   - 只采用针对当前目标项目、且是对该项目最近一次发起的查询结论；目标项目变化后，先前项目查询晚到的结论不改变当前可写态（用例：挂起项目 A 的响应 → 切换到项目 B 并得到结论 → 再放行 A 的响应，可写态仍按 B）。
   - 项目状态显示已归档时，即使查询结论为能编辑，也按不可编辑呈现，原因为项目已归档。
   - 写请求被拒后按第 7 条重新查询。
3. WHILE 判定查询结论为能编辑（即按需求 6.2、6.3 放行的调用者：本项目 review 级或 edit 级、未被判定为 EQCR 且操作矩阵放行的成员，或未被判定为 EQCR 的 admin）且项目未归档，THE 附注编辑器 SHALL 启用全部写入口。各入口自身的业务前置条件（如未选章节、没有可删除的行、有未保存修改、请求进行中）照常生效，不算权限禁用；被多窗口锁强制只读时，只禁用受该锁约束的写入口，范围保持现状（写作时：编辑、两处保存、一键清除公式、正文批量写入三个入口；细化时补的默认口径，备选为多窗口锁约束全部写入口）。口径：
   - 写入口：附注编辑器范围（需求 1.3 口径）内，经用户操作或自动触发后会发出写方法请求、且请求目标为附注编辑门禁覆盖集合（需求 1.9）端点的入口；另含进入编辑模式的「编辑」按钮、章节树拖拽排序，以及会把本地内容标记为未保存的输入区（正文富文本编辑区、表格单元格、表格结构工具栏、导出表格勾选等；输入区纳入为细化时补的默认口径，备选为输入区保持可输入、只禁用保存）。形态含按钮、下拉菜单项、开关、树节点操作图标、右键菜单项、快捷键与自动触发；先打开弹窗、弹窗内另有只读功能的，以弹窗内发出请求的元素为入口。写作时至少含原列举的编辑、保存、离线导入、校验、从底稿刷新、公式清除 / 应用、批量写入、内容模板、新增章节，以及需求 8.1 所列 B1 入口。
   - 写入口清单逐项记录入口、触发方式与对应调用点，并与需求 1.3 清册的调用点对账：清册中附注编辑器范围内、目标为覆盖集合端点的每个调用点都至少归属一个写入口，否则测试打红。
   - 合并锁定时的呈现保持现状：合并锁定横幅照常显示，正文批量写入三个入口照常隐藏，其余写入口被 423 拒绝时按第 7 条处理。
   - 目标不在覆盖集合内的写方法入口（如导出 Word、AI 预览类、清册表 D 端点、表 C 死链（章节树拖拽排序除外））不受第 3~5 条约束，呈现保持现状；其中按 EQCR 显隐的入口按第 8 条改用查询结论。
4. WHILE 判定查询结论为本项目 EQCR（包括全局角色不是 eqcr、只在本项目以 EQCR 别名委派的人，以及全局角色为 eqcr 的人），THE 附注编辑器 SHALL 隐藏或禁用全部写入口，并显示「📋 只读副本」标识：
   - 每个写入口要么不渲染，要么处于禁用态且操作后不发出请求；禁用的写入口悬停提示写明判定查询返回的原因。
   - 未被判定为 EQCR 时不显示该标识。
   - 只看本项目（固定样例必测）：同一用户打开其持有 EQCR 委派的项目 P，显示标识、写入口均不可操作；切换到其以 `manager` 委派、判定为能编辑的项目 Q 后，不显示标识，写入口按第 3 条启用。
5. WHILE 判定查询结论为不能编辑、且未被判定为 EQCR（写作时含：本项目 readonly 成员；操作矩阵不放行 `note:edit` 的 review 级及以上成员，如全局角色与项目角色均为 qc 的成员；项目已归档），THE 附注编辑器 SHALL 禁用全部写入口：可编辑用户在同一页面状态下能看到的写入口保持可见、处于禁用态、操作后不发出请求，悬停提示为中文并写明判定查询返回的原因（readonly 成员为「权限不足」）；不显示「📋 只读副本」标识。
6. IF 判定查询失败（返回 403 或其他失败响应；网络错误；成功响应缺少「能否编辑」或「是否 EQCR」，或结论为不能编辑却没有原因；发起后 15 秒内仍未得到结论。15 秒为细化时补的默认口径，备选为沿用平台默认请求超时），THEN THE 附注编辑器 SHALL 以只读呈现：
   - 写入口按第 5 条禁用，悬停提示写明无法确认编辑权限（403 时为后端返回的原因）；不显示「📋 只读副本」标识。
   - 每次失败恰好显示一条中文提示，写明无法确认编辑权限、已按只读打开（403 时含后端返回的原因），不另弹全局通用错误提示。
   - 查询被取消（前端同请求去重、组件卸载或目标项目变化所致）不算失败：不提示，不进入本条只读，仍按第 2 条取结论。
   - 此后的查询（目标项目变化、重新进入页面、第 7 条的重新查询）得到结论时，按该结论呈现。
7. IF 附注编辑器发往覆盖集合端点的写请求被拒（403，或归档 / 合并锁定的 423），THEN THE 附注编辑器 SHALL：
   - 403：恰好显示一条中文提示，文本包含后端返回的原因（如「权限不足」、EQCR 只读、操作矩阵不放行），不另弹全局通用权限提示。423：沿用现有提示（合并锁定提示并刷新锁定态；归档提示）。
   - 不自动重发该请求（含定时自动保存的失败重试）；同一次操作中尚未发出的后续写请求不再发出（如批量删除、批量恢复、导出设置的逐章请求；细化时补的默认口径，备选为继续发出其余请求并汇总被拒数）。
   - 不显示成功提示，也不在本地把该操作呈现为已生效（例如「一键清除公式」被拒时，不把单元格改成本地手动模式）。
   - 保留本地未保存的编辑内容：当前章节正文、表格单元格与表格结构的修改保持显示，编辑模式与未保存标记保持，离开页面仍按未保存拦截确认；不从服务端重载当前章节；发出该请求的弹窗保持打开，已填内容保留。
   - 重新发起一次判定查询，按结论更新可写态（细化时补的默认口径，备选为保持当前可写态直至重新进入页面）；结论为不能编辑时，写入口按第 4~6 条不可操作，已保留的编辑内容仍可选中复制。
8. THE 附注编辑器 SHALL 由第 2 条得出唯一一份可写态与唯一一份「是否 EQCR」，替换按全局角色判 EQCR 的 `isEqcrRole` 与 `useAuditContext` 的 `canEdit`：全部写入口的启用判定，以及传给子组件与 composable 的写开关和 EQCR 开关，都取自这两份值（写作时：章节树的可拖拽属性与 `useNoteTree` 的 EQCR 选项、`DisclosureNoteContentTools` 的 `can-write`、`NoteMappingDialog` 的 `can-edit`、按 EQCR 隐藏的 AI 填充 / 参照文档填充 / 批量预填充入口）。查询尚未得到结论或失败时，按 EQCR 隐藏的入口按 EQCR 处理（细化时补的默认口径，备选为按非 EQCR 显示）。验收：
   - 扫描测试（按语法树，注释与字符串不计）：`DisclosureEditor.vue`，以及附注编辑器范围内不被该范围以外页面引用的组件与 composable，不再把全局角色与 `eqcr` 比较，不再读取 `useAuditContext` 的 `canEdit`，不再引用前端操作矩阵的判定函数（`canDo`、`can`）。写作时 `DisclosureNoteContentTools` 以 `can('note:edit')` 判定入口，须改为取编辑器传入的值。
   - 对需求 12.2 的五种身份，以及「尚未得到结论」「查询失败」两种状态，逐一断言上述开关的取值与编辑器的两份值一致。
   - 磁盘变异证明：把其中一处开关改回按全局角色判定后，扫描测试红在该处，受影响身份的取值断言红在该开关上；每次变异后逐字节恢复。
   - 与附注编辑器以外页面共用的子组件，在其他页面的行为保持不变（新增的开关缺省时沿用原行为）。
9. THE 附注编辑器新增或改动的用户可见文案 SHALL 全部为中文（技术术语 SQL / PDF / LLM / API / UUID / EQCR / Word 保留英文），包括禁用悬停提示，以及正在确认权限、查询失败、写请求被拒的提示；后端返回的中文原因原样显示；提示中不出现英文原始错误信息（如请求库给出的状态码描述）。验收：本 spec 改动的前端文件在既有静态检查 `gt-audit/no-english-ui-text` 下零新增告警，新增文案逐条列入验收记录。
10. WHILE 附注编辑器处于不可编辑态（第 2 条尚未得到结论期间，以及第 4、5、6 条所述状态），THE 附注编辑器 SHALL 不发出任何目标为覆盖集合端点的写方法请求，也不发出章节拖拽排序请求。这包括自动触发：定时自动保存、快捷键保存、加载或切换年度后发现没有附注章节时的自动生成、切换附注模板触发的重新生成、底稿保存事件触发的刷新（需求 8.7）；也包括以程序方式触发已隐藏或禁用的入口（如直接派发点击）。可编辑时这些自动触发保持现行为；加载时没有附注章节的，在判定为能编辑之后才自动生成。验证：对需求 12.2 五种身份与「尚未得到结论」「查询失败」两种状态，拦截网络请求，逐个操作写入口清单中的入口并触发上述自动触发：不可编辑态下此类请求为 0 个；可编辑身份下，每个有对应调用点的入口在满足业务前置条件并完成确认后，都发出其调用点的请求。
11. FOR ALL 由以下输入构成的组合，THE 附注编辑器的呈现 SHALL 等于下述模型（fast-check，`numRuns: 5`；另以第 4 条的 P / Q 样例、需求 12.2 五种身份、尚未得到结论、查询失败、项目已归档、多窗口锁强制只读为固定样例逐个断言）：
   - 输入：判定查询状态（尚未得到结论 / 失败 / 成功；成功时附能否编辑、原因、是否 EQCR，只生成第 1 条可能出现的组合，即判为 EQCR 时能否编辑必为否）；项目状态是否已归档；是否被多窗口锁强制只读；写入口取自写入口清单（区分是否受多窗口锁约束）。
   - 模型：写入口可操作 ⇔ 查询成功 ∧ 能编辑 ∧ 未归档 ∧（不受多窗口锁约束 ∨ 未被强制只读）。不可操作时：查询成功且判为 EQCR，则隐藏或禁用；否则可见且禁用（限可编辑用户在同一页面状态下可见的入口），悬停提示写明一项当前成立的原因、不写不成立的原因。「📋 只读副本」显示 ⇔ 查询成功 ∧ 判为 EQCR。按 EQCR 隐藏的入口显示 ⇔ 查询成功 ∧ 未判为 EQCR。
   - 磁盘变异证明：把任一写入口改为忽略可写态后，性质测试红在该入口上；逐字节恢复。

### 需求 11：连续审计复制团队时保持 EQCR 独立性（Q6 默认）

**用户故事：** 作为质量管理负责人，我希望连续审计复制团队后，上年的 EQCR 不会在新项目里变成能编辑的普通成员。

#### 验收标准

1. WHERE 创建下年项目时开启「复制团队」（含不带请求体、按默认开启的调用；写作时项目详情面板 `DetailProjectPanel.vue` 的「创建下年」就是这样调用的），WHEN 连续审计复制上年项目的成员行，THE 连续审计复制 SHALL 跳过在上年项目持有 EQCR 别名现行委派的用户，不在新项目为其新建成员行。判定口径：
   - 与需求 7.1 第二项（委派条件）逐项相同：只看上年项目的现行委派（术语表口径，已删除的委派与已删除的人员库记录不计）；委派角色按字符串精确匹配属于 EQCR 别名集合，大小写变体与首尾空白变体不算；同一用户经多条人员库记录持有多条现行委派时，任一条属于 EQCR 别名集合即跳过；在其他项目持有的 EQCR 委派不影响结论。
   - EQCR 别名集合按需求 7.2 由角色映射推导，本步不另存别名副本。
   - 全局角色为 admin 不豁免。成员行的项目角色与级别、人员状态都不影响结论。以执行复制时上年项目的数据为准。
   - 全局角色为 `eqcr`、但在上年项目没有 EQCR 别名现行委派的成员照常复制（细化时补的默认口径，备选为按需求 7.1 两项一并判定，这类成员同样跳过）。理由有两点：需求 7.1 的全局角色分支在新项目同样成立，附注编辑门禁在新项目照样拒绝其写入（需求 6.4 或 6.5）；这类成员也没有需要「重新委派」的 EQCR 委派。
   - 被跳过的非 admin 用户因此不是新项目成员，附注编辑门禁按需求 6.4 拒绝其写入，直到在新项目重新委派。重新委派为 EQCR 别名后，按需求 3.3 成为（partner, review），附注编辑门禁按需求 6.5 拒绝其写入。
   - 按 F13，写作时真库 EQCR 委派 0 条，全局角色只有 admin / auditor，按现有数据不会跳过任何人（快照，不作判据）。
2. WHEN 创建下年项目成功，THE 连续审计复制 SHALL 在成功响应中返回团队复制结果：
   - 开启「复制团队」时，同时返回复制人数与跳过人数。跳过人数 = 上年项目未删除成员行中因第 1 条未复制的行数（F4 下即人数），无人跳过时为 0。持有 EQCR 别名现行委派、但在上年项目没有未删除成员行的用户本来就不在复制范围内，不计入。复制人数只计新项目实际新建的成员行，不含被跳过的成员。
   - 跳过人数 ≥ 1 时，另附中文提示，内容包含「独立复核合伙人需在新项目重新委派」；跳过人数为 0 时不附该提示。
   - 跳过不使创建失败：照常返回成功响应，其余复制步骤照常执行。
   - 关闭「复制团队」时，不执行第 1 条判定，响应不含跳过人数与该提示（现状关闭时也不含复制人数）。

   写作时现读：成功响应只含新项目标识、上年项目标识、新年度与各项复制数；前端展示见第 4 条。
3. WHERE 开启「复制团队」，WHEN 连续审计复制上年项目的成员行，THE 连续审计复制 SHALL 对未被第 1 条跳过的每条上年未删除成员行保持现行复制行为：
   - 在新项目新建一条成员行，项目角色、项目级别、循环范围、科目范围与上年该行逐值相同，不按角色映射重算；有效期不复制。
   - 已删除的成员行不复制，既不计入复制人数，也不计入跳过人数。
   - 不为新项目新建委派。
   - 上年项目的成员行、委派与人员库记录保持复制前的值。

   本需求不改变创建下年项目接口的鉴权（写作时现读：该接口只校验登录，与 F16 同类）。
4. WHEN 项目详情面板的「创建下年」收到跳过人数 ≥ 1 的成功响应，THE 项目详情面板 SHALL 显示一条中文提示，内容包含跳过人数与「独立复核合伙人需在新项目重新委派」：
   - 跳转到新项目的项目向导后，该提示仍保持显示，直到用户手动关闭（细化时补的默认口径，备选为与现有成功提示一样，数秒后自动消失）。
   - 跳过人数为 0，或响应不含跳过人数时，不显示该提示。
   - 现有的「已创建下年项目」成功提示与跳转保持现状。

   写作时现读：「创建下年」只提示新项目 ID 前 8 位，随即跳转项目向导，不展示任何复制数。
5. IF 复制团队时判定上年项目 EQCR 的查询出错（含委派查询或人员库记录查询报错、数据库连接中断），THEN THE 连续审计复制 SHALL 使本次创建下年项目整体失败：不按「无人持有 EQCR 委派」照常复制，也不吞掉错误后继续执行后续步骤（细化时补的默认口径，备选为本次不复制任何成员、项目照常创建，并在成功响应中附中文提示说明团队未复制）。
   - 返回失败响应，不返回成功响应。
   - 新项目及本次已写入的全部数据（项目、科目映射、成员行等）都不生效，上年项目的数据保持请求前的值。调用方随后重试时，不会因下年项目已存在而被拒。
   - 验证时在该判定的下层查询注入异常（不替换判定本身），同时断言两点：响应不是成功响应；数据库中不存在新项目及其成员行。
6. FOR ALL 按下列维度生成的上年项目数据，连续审计复制在开启「复制团队」时完成后 SHALL 同时满足以下各项（hypothesis 模型对拍，`max_examples=5`；模型里的 EQCR 别名集合取需求 2.5 期望表中取值为（partner, review）的键，不读生产代码）：
   - 新项目成员行的用户集合 = 上年未删除成员行的用户集合 − 按第 1 条口径在上年项目持有 EQCR 别名现行委派的用户集合。
   - 新项目每条成员行的项目角色、项目级别、循环范围、科目范围与上年对应行逐值相同，有效期为空；本次复制没有为新项目新建委派。
   - 复制人数等于新项目成员行数，复制人数 + 跳过人数 = 上年未删除成员行数；响应含第 2 条的提示，当且仅当跳过人数 ≥ 1。
   - 上年项目与另一项目的成员行、委派、人员库记录都与复制前逐值相同。

   生成维度：
   - 上年项目：0~6 名有未删除成员行的用户（成员行的项目角色、级别、循环范围、科目范围与有效期任取），另有 0~2 名只有已删除成员行的用户；另一项目为其中部分用户各置一条成员行。
   - 每名用户的全局角色取系统角色的全部取值（admin、partner、manager、auditor、qc、eqcr、readonly）。
   - 每名用户经 1~2 条人员库记录持有 0~3 条委派：项目取上年项目或另一项目；委派与人员库记录各自取未删除或已删除；委派角色取角色映射的全部键、这些键的大小写与首尾空白变体，以及长度 0~30 个字符的任意字符串；生成数据遵守 F4。
   - 干扰数据：持有上年项目 EQCR 委派、却没有成员行的用户；未关联用户的人员库记录在上年项目的 EQCR 委派。

   另以固定样例逐个断言（未写明的维度取：全局角色 auditor、上年成员行为（partner, review）、无其他委派）：
   - ① 上年委派 `eqcr` → 跳过，跳过人数 1，响应含提示
   - ② 上年委派 `独立复核合伙人` → 跳过
   - ③ 经人员库记录甲委派 `manager`、经人员库记录乙委派 `eqcr` → 跳过
   - ④ 上年委派 `EQCR` → 复制
   - ⑤ 上年的 `eqcr` 委派已删除 → 复制
   - ⑥ 全局角色 eqcr、上年委派 `manager`、成员行为（manager, edit）→ 复制，仍为（manager, edit）
   - ⑦ 全局角色 admin、上年委派 `eqcr` → 跳过
   - ⑧ 在另一项目委派 `eqcr`、上年委派 `manager` → 复制
   - ⑨ 上年委派 `manager` → 复制，跳过人数 0，响应不含提示
   - ⑩ 端到端：用①的数据经创建下年项目接口真发请求，再以该用户对新项目调用附注编辑门禁覆盖集合（需求 1.9）中任选的一个端点，得到需求 6.4 的 403「权限不足」

   配两项磁盘变异证明（每次写磁盘后逐字节恢复）：①删去第 1 条的跳过判定后，样例①红在「新项目不应有该用户的成员行」的断言上；②把判定的委派条件改为只认 `eqcr` 后，样例②红在同一断言上。

### 需求 12：测试与验收

**用户故事：** 作为质控复核人，我希望本 spec 的每个结论都有端点级测试和变异证明，以便「已完成」不是假绿。

#### 验收标准

1. THE 端点级测试 SHALL 用 TestClient 真发请求，由真实的 `assert_project_permission`、附注编辑门禁、EQCR 判定与交付中心门禁作出判定（不论门禁以依赖还是函数体调用挂载），替换范围限于其下层取数点：
   - 可替换的只有：当前用户（替换门禁内层所用的当前用户依赖）、权限缓存的存储（替身按生产 Redis 客户端的取值形态返回所存的值，缓存读写函数本身不替换，同需求 5.7）、归档守卫、RLS 上下文设置、委派查询、端点的业务 service（打桩并计数）。
   - 某条用例观测的判定（归档、成员级别、EQCR、操作矩阵、合并锁、权限缓存）在该用例中不替换，其输入以数据库中的项目、成员行、人员库记录与委派给出。例如观测归档结论的用例不替换归档守卫，观测 EQCR 结论的用例不替换委派查询。
   - 不以 `dependency_overrides` 或 monkeypatch 替换 `require_project_access`（依赖工厂每次返回新函数对象，按它 override 会静默失效）、`assert_project_permission`、附注编辑门禁、EQCR 判定与交付中心门禁本身。故障注入只注在被测判定的下一层（如需求 7.6、11.5 的下层查询）。本项由第 13 条的扫描测试钉住。
   - 每个端点级测试文件至少含一条放行用例（业务 service 调用恰 1 次且响应成功）；只有拒绝用例的文件不计为端点级测试。
   - 级别判定点保留权限缓存时，需求 5.7 所指的缓存用例组在同一次运行中先通过命中对照用例；对照用例失败时该组判为失败，不判为跳过或通过。

2. FOR ALL 附注编辑门禁覆盖集合（需求 1.9；写作时即表 A 与按 Q3 纳入的端点）中的端点，THE 端点级测试 SHALL 逐个端点断言以下五种身份的结论（编号与定义供需求 10.8、10.10、10.11 引用）。五种身份的全局角色均为 auditor；目标项目未归档、未合并锁定；不预置权限缓存条目；除身份⑤外没有任何 EQCR 别名委派：
   - ① edit 级成员：成员行（manager, edit）→ 放行。
   - ② review 级非 EQCR 成员：成员行（qc, review）→ 放行（Q1 默认）。
   - ③ readonly 成员：成员行（readonly, readonly）→ 403「权限不足」。
   - ④ 非成员：在目标项目没有成员行，在另一项目有一条（manager, edit）成员行 → 403「权限不足」。
   - ⑤ 本项目 EQCR：成员行（partner, review），在目标项目持有一条 `eqcr` 现行委派 → 403，信息含需求 6.5 的「独立复核合伙人（EQCR）在本项目只读」。
   - 放行指端点的业务 service（打桩并计数）调用恰 1 次，且响应成功。拒绝指业务 service 调用 0 次，响应状态与原因符合上表。原因逐字比较，用来区分「权限不足」、EQCR 只读与操作矩阵不放行；只断言状态码不算。
   - 五种身份各在独立的初始数据上，对同一端点发出同一请求：路径参数与请求体相同，幂等键等一次性字段各取新值，对象 id 端点的对象存在且属于目标项目。该请求在身份①下放行，以证明其余身份的拒绝来自门禁，而不是 404 或请求格式校验。
   - 对象 id 端点另测一次：身份④在查询参数或请求体中另附其有权的另一项目的标识，结论仍为 403「权限不足」（需求 6.8）。
   - 另对每个端点断言：未登录请求返回 401，业务 service 调用 0 次（不计入五种身份）。

3. THE 端点级测试 SHALL 断言「第 2 条参数化的端点集合 = 附注写端点清册中目标门禁为附注编辑门禁的端点集合（需求 1.9 的覆盖集合）」，新增附注写端点未进测试即打红：
   - 两个集合按（方法，完整路径）双向比较：清册有而测试没有、测试有而清册没有，都打红并逐个列出端点。
   - 清册以已提交的清册为准；同一次测试运行中第 12 条的清册检查模式守卫也通过，本断言才计为通过。
   - 集合非空，每个端点的五种身份用例都被收集并执行（未被跳过）。
   - 配磁盘变异证明：在一个附注路由文件中新增一个挂附注编辑门禁的写端点并重新生成清册，本断言红在「集合不等」上并点名该端点；之后路由文件与清册都逐字节恢复。

4. FOR ALL 第 2 条的五种身份与以下三种补充情形，THE 端点级测试 SHALL 断言需求 10.1 判定查询的结论与覆盖集合每个端点的写请求结论一致。补充情形让需求 10.1 的四种原因和 admin 放行都出现：⑥ 身份①的成员在已归档项目上；⑦ 全局角色与项目角色均为 qc 的 review 级成员；⑧ 全局角色为 admin、不是本项目成员。
   - 前提：目标项目未合并锁定；查询先于写请求发出，两者之间成员行、委派与项目状态不变。
   - 「能否编辑」为是 ⇔ 写请求放行；为否 ⇔ 写请求被拒。查询本身返回 403（身份④）视同「不能编辑」。
   - 不能编辑时，查询给出的原因（查询返回 403 时取其信息）与写请求拒绝响应中的原因逐字相同。
   - 「是否 EQCR」对身份⑤为是，对其余返回了结论的情形为否。
   - 查询前后业务数据不变。

5. THE 磁盘变异证明 SHALL 至少覆盖以下四处（编号与含义固定，需求 6.10 所称「前两处」即①②），每处的应红、应绿断言如下：
   - ① 附注编辑门禁中 `assert_project_permission` 的级别由 review 改回 edit。应红：第 2 条身份②在每个端点上的「应放行」断言；身份⑤的原因断言（拒绝原因变为「权限不足」）；需求 6.10 断言①。应绿：身份①③④；第 4 条的对拍（判定查询与写端点走同一判定函数，结论同步变化）。
   - ② 删去附注编辑门禁对 EQCR 判定的调用。应红：身份⑤在每个端点上的「应拒绝」断言；需求 6.10 断言②。应绿：身份①~④。
   - ③ 角色映射中 `manager`、`项目经理` 的取值改回（manager, review）。应红：需求 2.5 前提测试对这两个键的逐键断言；第 7 条「回填与角色映射对账」中这两个别名的用例；需求 9.2 以这两个别名委派的端到端用例。应绿：上述测试中其余别名的用例；第 2 条五种身份（成员行为预置值，不经角色映射）。
   - ④ 删去委派保存端点提交后的权限缓存失效。本处只在级别判定点保留权限缓存时适用（同需求 5.7 的 WHERE 条件），不适用时在验收记录写明 design 的裁定。应红：固定样例「保存前预置一名受影响用户的缓存条目，成功响应返回时该条目已不存在」；需求 5.1 第三项的固定样例「成员行与缓存条目均为 readonly 级的用户经委派升为 `manager`，成功响应之后开始的 edit 级判定放行」。应绿：需求 5.6 的降级固定样例。需求 5.2 要求缓存失效失败时降级照样即时生效；这些样例若在本变异下变红，说明降级的即时生效依赖缓存失效，须先按需求 5.2 修实现，再重做本变异。行为类断言只在同一次运行中需求 5.7 的命中对照用例通过时才计为有效。
   - 以下规则同样适用于需求 2.7、7.2、7.4、8.6、9.7、9.9、10.8、10.11、11.6 与本需求第 3、8、12、13 条的变异证明：
     - 应红的断言是确定性用例（固定样例，或性质测试显式附带的样例），不依赖 `max_examples=5` / `numRuns: 5` 的随机生成碰巧命中。
     - 失败须落在指定断言上，失败信息能辨认出是该断言；收集错误、导入错误、语法错误、夹具错误、超时与其他未预期异常都不算变红。
     - 应绿的断言保持通过。
     - 变异前记录被改文件的哈希；运行后逐字节恢复，恢复后的哈希与变异前相同，复跑同一组用例全部通过。
     - 变异在临时 worktree 中进行，不在运行着开发服务的主工作树上改生产代码（细化时补的默认口径，备选为在主工作树进行，但先停开发服务、浏览器离开附注编辑器）。
     - 需求 7.3、10.1 所列的可伪证断言，各以一次磁盘变异实测打红（需求 6.10 的两条由①②实测）。
     - 每次变异的记录写入验收记录（第 14 条）。

6. THE 性质测试 SHALL 覆盖需求 2.4、3.5、4.6、4.7、4.11、5.5、5.6、6.13、7.5、9.5、9.9、11.6（hypothesis，每个测试显式声明 `max_examples=5`，不多不少）与需求 10.11（fast-check，`numRuns: 5`）：
   - 每个性质测试同时带上所属需求列出的固定样例。所属需求未列固定样例的（写作时如需求 4.6、4.7、4.11、5.5），至少附一个使性质非平凡成立的固定样例：如需求 5.5 中受影响（用户，项目）与预置条目的交集非空；需求 4.6、4.7、4.11 中含被需求 4.2、4.3 改动的行。
   - 模型的期望值按需求原文与需求 2.5 的期望表计算，不调用被测的生产判定函数。需求 2.4、3.5 明文以角色映射为对拍对象，属例外（角色映射本身由需求 2.5 钉住）。
   - 运行中发现的反例先固化为固定样例，再修实现（细化时补的默认口径，备选为只记入验收记录）。
   - 需真 PG 的性质测试（需求 4.6、4.7、4.11）带 `pg_only` 标记，并按第 9 条在验收运行中实际执行。

7. THE 级别回填迁移测试 SHALL 在真 PG 上（`pg_only` 标记）执行一次正向迁移与配对回滚并逐行对账，且在验收运行中实际执行（跳过或未被收集都计为未完成）：
   - 正向迁移经运行时迁移执行器执行（与启动流程同一路径）。测试在测试库或不提交的事务内进行，不在本地开发库上执行回滚（同需求 4.8）。
   - 正向迁移后，每个成员行等于需求 4.11 的期望值，被改动行集合等于回填记录覆盖的行集合。回滚后，全部成员行等于迁移前的值，不残留回填记录（需求 4.6）。
   - 回填与角色映射对账：对合伙人 / 经理别名集合与 EQCR 别名集合的每个别名（取自需求 2.5 期望表，不读生产代码），在「只持有该别名一条现行委派、迁移前为（auditor, readonly）」的成员行上执行正向迁移，所得项目级别等于角色映射（生产代码）对该别名给出的级别；合伙人 / 经理别名的项目角色也须相等。迁移脚本引用不了角色映射，本断言是两者之间的一致性约束（第 5 条③靠它打红）。

8. THE 既有测试中钉住旧口径的（F15 所列）、需求 5.7 所指的宽松断言（`test_phase8.py::test_set_and_get_cache` 接受「None 或 edit」），以及第 9 条运行中因本 spec 口径变化而失败、需要改写的其他既有测试 SHALL 按新口径改写，断言强度不低于改写前：
   - 改写前后逐个测试函数对照，记入验收记录：原有每条断言都有对应的新断言；改名或拆分的写明新旧名对照。不删除测试函数；因口径消失而不再成立的，写明理由与接替它的测试。
   - 新断言逐值比较（相等或集合相等）。不写同时容纳新旧两种取值的断言（如「review 或 edit」「None 或 edit」），也不退化为「调用不抛即通过」或只断言状态码。
   - 不新增 `skip`、`xfail`，不放宽既有的 `xfail(strict=True)`。
   - 调用序列类断言（如 `test_disclosure_notes_hardening.py` 的门禁调用序列）改为逐项断言附注编辑门禁按需求 6.1 的判定顺序执行。鉴权基线守卫与附注门禁契约守卫按需求 6.10、8.4 改写。
   - `test_set_and_get_cache`：保留权限缓存时，改为断言取回的值等于写入的级别；design 裁定移除权限缓存时，随之删除，并在验收记录写明。改写后的该测试要在本 spec 改动前的读路径上运行一次：需求 5.7 的推断属实时，须红在取回值的断言上；不属实时，在验收记录写明实测结论。

9. WHEN 后端与前端改动完成、提交之前，THE 验收 SHALL 在临时 worktree 中干净检出「将要提交的那棵树」（本次提交的全部文件，含新增的模块、迁移、清册与测试，不含工作树里其他会话的未提交改动），并：
   - 后端跑全量测试，不在首个失败处中止；前端跑 vitest 全量（细化时补的默认口径，备选为只跑本 spec 新增与改写的测试、引用本 spec 改动模块的既有测试和全仓守卫类测试）。
   - 依赖 PG 专有行为的判据在真 PG 上执行，包括：迁移；带删除条件的唯一索引（如需求 3.1 只有已删除成员行的情形）；含原生 SQL、按 uuid 绑定参数的查询。本 spec 新增的 `pg_only` 用例跳过数为 0。
   - 前端另以网络审计模式运行本 spec 新增与改动的测试文件：不出现真实网络连接，不向网络泄漏清单新增条目。
   - 前端类型检查：全量 vue-tsc 在本仓库会内存耗尽，改以单区域配置只检查本 spec 改动的前端文件。检查前先在其中一个文件注入一处类型错误，确认检查报错，恢复后确认通过；输出含内存耗尽等崩溃信息时不算通过。
   - 预存失败归因：同一批测试在目标分支最新提交的干净检出上运行。一条失败只有在基线树上以同一测试标识、同类失败（同一异常类型、同一断言位置）复现时才算预存，逐条登记测试标识、失败摘要与基线提交；其余失败都算本 spec 引入，修复后重跑。
   - 结束后按项目约定清理临时 worktree（解锁、删目录、修剪登记）。

10. WHEN 前端改动完成，THE 验收 SHALL 用 chrome-devtools 浏览器实测五种身份：edit 级经理、edit 级合伙人、review 级质控、review 级 EQCR、readonly 成员：
   - 前置：后端已全量重启（迁移与新路由不随热重载生效）；开发服务所跑代码在本 spec 改动的文件上与将要提交的那棵树逐字节相同。
   - 身份：在一个名称带「【测试】」、未归档、未合并锁定的项目上，新建五个全局角色为 auditor 的临时账号（真库全局角色只有 admin / auditor，F13）。经委派保存端点把它们分别委派为 `manager`、`partner`、`qc`、`eqcr` 与一个未登记角色，成员行由委派同步写出（细化时补的默认口径，备选为直接写入成员行与委派）。
   - 可写态：经理、合伙人、质控的写入口可操作，不显示「📋 只读副本」。EQCR 的写入口不可操作，显示该标识。readonly 成员的写入口可见且禁用，悬停原因为「权限不足」，不显示该标识。页面不出现英文报错文案。
   - 真实保存：经理、合伙人、质控各在编辑器内修改一处正文并保存，刷新后内容保持，「最近一次编辑」为本人。EQCR 与 readonly 成员各用浏览器内脚本发出与保存按钮相同的请求：返回 403，原因分别与需求 6.5、6.4 一致，附注内容与请求前相同。
   - 每种身份的页面快照、请求与响应摘要记入验收记录。实测期间不改动附注编辑器及其子组件的源码（热更新重挂载会触发自动保存的真实写入）。
   - 清理：结束后按写过的表逐项恢复到实测前状态并核对行数（临时账号、人员库记录、委派、成员行、附注改动、权限缓存条目）。审计日志等只追加的留痕不删除，在验收记录登记（细化时补的默认口径，备选为一并删除并重新校验审计日志哈希链）。

11. THE tasks.md 中的任务 SHALL 只在同时满足以下条件时标记完成（`[x]`）：
   - 勾选所在提交的树中已包含对应代码与测试（不在代码入库之前勾选）。
   - 对应测试在第 9 条的干净检出运行中通过（`pg_only` 用例实际执行）。
   - 任务涉及磁盘变异证明的，变异记录已写入验收记录。
   - 完成证据（测试标识、验收记录条目）写在该任务下。

   依赖外部环境、本轮未能实测的任务标 `[ ]*`，写明「代码已改但未实测」与所缺环境。不使用 `[~]` 等其他标记（gt-plan 的任务统计不识别，会误报完成）。

12. WHEN 后端测试套件运行，THE 附注写端点清册（需求 1.10）与影响清单（需求 9.1）的检查模式守卫测试 SHALL 以子进程调用两个生成脚本的检查模式，并同时断言退出码与输出内容：
   - 子进程以 UTF-8 输出（Windows 下传 `PYTHONIOENCODING=utf-8`），守卫断言输出含检查模式的中文结论。输出为空、读取失败或含解码替换字符时判失败；只断言退出码不算。
   - 在将要提交的那棵树上，两个检查模式都以零退出码通过。两个脚本以生成模式输出到临时位置（不覆盖已提交文件）连续两次，两次结果与已提交文件逐字节相同。
   - 附注写端点清册配一项磁盘变异证明（影响清单的同类证明见需求 9.7）：把一个覆盖集合端点的附注编辑门禁换回 `require_project_access("edit")`，检查模式以非零退出码失败，并把该端点列为变化条目。
   - 两个脚本另各配一项磁盘变异证明：使识别逻辑判错一个合成样例（如不再识别签名参数默认值里的依赖），生成与检查模式都以非零退出码失败、列出该样例名称、不写出文件，已提交的文件保持不变。
   - 该守卫测试另在「未处理的线程异常告警视为失败」的设置下复跑一次并通过（排除子进程输出解码异常被吞），结果记入验收记录。

13. THE 防假绿扫描测试 SHALL 按语法树（注释与字符串不计）扫描本 spec 新增的测试文件，以及既有测试文件中本 spec 新增或改动的测试函数（扫描清单须与改动前、改动后两棵树之间的差异逐个相等）。以下写法命中即打红，并列出文件与位置：
   - 以 `dependency_overrides` 或 monkeypatch 替换第 1 条列为不可替换的判定，或替换权限缓存读写函数。
   - `pytest.raises` 块内多于一条语句，或其后未断言异常信息。
   - 子进程调用后只断言退出码、未断言输出内容。
   - 断言条件是同一表达式与两个及以上不同取值的相等比较的「或」组合，或是对含两个及以上元素的字面量元组、列表、集合的成员判断（如「None 或 edit」）。
   - hypothesis 性质测试未显式声明 `max_examples=5` 或声明了其他值；fast-check 性质测试未声明 `numRuns: 5` 或声明了其他值。
   - 新增 `skip`、`skipif`、`xfail`（`pg_only` 标记与需求明文要求的 `xfail(strict=True)` 除外）。

   配磁盘变异证明：在一个被扫描的测试文件中写入一处 override 附注编辑门禁的语句，扫描测试红在该条上；之后逐字节恢复。

14. WHEN 准备把 tasks.md 的最后一项未完成任务标记完成，THE 验收 SHALL 先用一条检查核对验收记录是否闭合，未闭合就不得标记：
   - 判据引用闭合：需求 1~12 的每条验收标准都至少对应一个测试标识或一项验收记录条目，对应关系逐条列出。由脚本核对，不靠人工清点。
   - 变异证明汇总：第 5 条所列全部变异逐项登记：被改文件与改动描述、运行命令、变红的测试标识与断言信息、应绿用例保持通过的证据、恢复前后的文件哈希、恢复后的复跑结果。
   - 性质测试汇总：第 6 条每个性质测试的测试标识、声明的样例数与附带的固定样例名。
   - 现算计数对账：清册、影响清单、鉴权基线常量等在将要提交的那棵树上的现算值，与需求正文的写作时快照（如 F10、F12、F15、需求 6.6 的合并锁适用集合）逐项对照，差异逐条写明原因（快照只作对账参照，不作判据）。
   - 第 8 条的改写对照、第 9 条的预存失败登记、第 10 条的浏览器实测记录与清理对账，都已记入验收记录。

## 范围外（登记，不在本 spec 修改）

- 委派被移除后，project_users 行不撤销：被移出团队的人仍保留项目权限。
- `EqcrIndependenceRule.CONFLICT_ROLES` 只含 `signing_partner` / `manager` / `auditor`，不含中文别名与 `partner`；受 F4 唯一索引约束，同一人在同一项目只有一条现行委派，实际影响有限。
- 合并附注写端点（Q5 默认）；`account_note_mapping.py` 3 个 edit 级端点（前端零调用点）。
- 平台其余只校验登录的端点：由鉴权基线守卫的棘轮冻结。
- `note_templates.py` 5 个全局附注模板写端点没有任何鉴权依赖（是否另有全局中间件兜底，design 阶段核实后登记）。
- 表 C 的前端死链。
- 有现行委派、却没有 project_users 行的用户：后端一律 403，角色上下文兜底却按委派显示级别（真库 0 例）。
- `authorize_wp_edit` 对全局角色 partner 跨项目放行。
- F16 委派端点只校验登录（Q7 默认，🔴 高风险，建议另立 spec 先定委派权限）。
