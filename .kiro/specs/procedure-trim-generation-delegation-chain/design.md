# 设计：程序裁剪 → 底稿生成 → 委派 → 可见性 链条闭环

## 1. 现状（2026-10-24 现扫，代码 + 真库）

| 环节 | 现状 | 断点 |
|---|---|---|
| 粗裁 | `procedure_instances.status`，「配置裁剪」页 canonical preview → apply | 智能裁剪「有无数据」读 `procedure_trim_account_map.json`（H3=1503/1504 等 16 处错码），只看期末；与金额两套来源，档 4 先于金额 |
| 细裁 | 控制台 `GtAProgramConsole` 只改组件内存随 `/save` 存；设计真源 `procedure_row_tasks.applicability_status` 前端无写入方；另有 `parsed_data.trimming_metadata`、`workpaper_procedures`（真库 0 行）两套 | 细裁结果到不了委派与可见性 |
| 生成 | `/generate` 只排除精确码；5xx 回退 `generate-from-codes` 不看裁剪；全链按前缀但查询失败放行；B60 / IPO / 模板复制 / 准则转换不看；先生成后裁剪不处理；`/generate` 两端点只校验登录 | 安徽 132 张已裁底稿仍在 |
| 委派 | `delegate_lead` 不查裁剪；5 条旁路直写 `working_paper.assigned_to`（batch-assign 不限项目）；`expand_scope` 前端从未传；级联取消按 `audit_cycle_snapshot` 匹配（物化兜底 'A'，I2/I3 漏 6 条） | 裁掉的照样能派；跨循环委派恒失败 |
| 可见性 | `VisibilityQueryService` 不看裁剪；scope 上界 `project_users.scope_cycles` 只在扩权时写；团队分配的 `assigned_cycles` 不进可见性；主管只认英文角色且要求唯一委派；`get_user_scope_cycles` 空 = 不限（与可见性相反） | 非 admin 成员一张都看不到；主管也被 scope 截断 |
| 行级 | gate 不传 sheet；`/save` 整页替换；field-overrides 零鉴权；前端拿不到 grants | 程序执行人能改整张表 |

真库：真实业务项目成员只有 admin；安徽 132 张待删底稿全是 draft、`content_revision=0`，`checklist_responses` 45 行全为公式推送值（`updated_by` 空），无人工内容。

## 2. 设计决策

- **ADR-1 科目口径复用四表单一来源。** 每个底稿主码的科目名称与兜底码取自 `four_table` 循环规格（`declared_codes` 背后的 `D/E1/F/G/H/I/J/K/L/M/N` specs），规格缺失时取 `wp_account_mapping.json` 的 `is_primary` 条目（由并发 spec formula-fetch-followup 维护，本 spec 只读）。定位用 `semantic_account_resolver.match_slot_in_chart`（客户科目表按名 → 平台标准科目表按名 → 兜底码须在本项目科目表存在），与四表取数同一判据；不读 `procedure_trim_account_map.json`（下线删除）。
- **ADR-2 有数据 = 余额或发生。** 标准层：试算表命中标准码（前缀）期末 / 期初非零，或 `tb_balance` 叶子按映射归集的本期借贷非零；客户层：名称命中的客户码在 `tb_balance` 叶子的期初 / 期末 / 借 / 贷非零（覆盖映射缺口）。阈值 0.005。
- **ADR-3 保留范围单一实现** `services/procedure_scope_retention.py`：粗裁码 + 区间展开 + 子表前缀；读取失败抛 `TrimScopeUnavailable`，生成入口 fail-closed。
- **ADR-4 生成后裁剪 = 移入回收站（两层软删），不是标记隐藏。** 理由：底稿列表 / 看板 / 可见性 / 委派候选全部已按 `wp_index.is_deleted` 过滤，软删一处生效全处；`uq_wp_index_project_code` 不含 `is_deleted` ⇒ 恢复只能复活原行，lineage 记在 `wp_index.cross_ref_codes["_recycle_lineage"]`，不改 `parsed_data`，不删文件与关联行。无迁移。
- **ADR-5 有效循环范围单一计算** `services/wp_visibility/effective_scope.py`：主管 = 全部循环（项目内 `wp_index.audit_cycle` 出现值 ∪ A~S），受限 = 全部有效委派的 `assigned_cycles` ∪ `project_users.scope_cycles`（扩权部分）。分类器、`get_user_scope_cycles`、`_enforce_scope` 都调它。主管仍用填满集合表达（`VisibilityContext` 不变，admin 不变）。
- **ADR-6 细裁真源 = 程序行任务；按 (wp_id, 程序表码, 程序号) 定位**，后端按需导入定义、物化任务、绑定底稿，再走 `ProcedureTrimService.set_row_not_applicable / restore_row_execute`。不翻 `PROCEDURE_ROW_TASKS_ENABLED`（会改整套控制台 UI 与生成绑定，影响面大）；render-config 增加一个总开的「适用性投影」，让展示状态跟随任务。
- **ADR-7 行级编辑在服务端合并，不信客户端行归属。** `/save` 对受限用户按服务端任务归属合并：本人行取白名单字段，其余保留服务端已存内容；前端只读只是体验。
- **ADR-8 跨循环委派走「拒绝 + 带理由扩权重试」**，保留原 spec 的显式扩权与留痕；前端统一用一个组合函数处理 `out_of_scope`。

## 3. 组件设计

### 3.1 需求 1：科目有无数据

新模块 `backend/app/services/trim_subject_scope.py`：
- `subject_specs() -> dict[str, SemanticAccountSpec]`（lru_cache）：遍历四表 specs（K 循环由 `KCycleSpec.account_name / fallback_standard / fallback_provision / extra_standard_codes` 组装单槽 + 备抵槽），再补 `wp_account_mapping.json` 中 D~N 且无规格的 `is_primary` 条目（`account_name` → 名称槽，`account_codes` → 兜底码）。`has_account=False` 或无名无码 ⇒ 不进表（结果为 unknown）。
- `evaluate_subjects(db, project_id, year) -> SubjectAvailability`：一次取科目表、映射、试算表、`tb_balance` 叶子；逐规格逐槽定位（不走报表公式层，避免多槽误分配），按 ADR-2 判定；每个主码给 `state ∈ with_data / no_data / unknown` 与证据 `{slots: [{key, codes, standard_codes, source}], closing, opening, debit, credit, client_unmapped}`。

`procedure_trim_scope.resolve_subject_data_availability` 改为调用它，返回结构向后兼容并新增 `subject_unknown`、`evidence`；删除 `_load_wp_account_map / _package_has_data / _load_account_mapping` 与 `procedure_trim_account_map.json`。`cycles_with_data` 同口径补期初。

前端 `procedureTrimDecision.ts` 档 4：`accountAmount` 可比且 |x| ≥ 0.005 时不走 `no_data`（落到后续档位），证据记 `noDataContradicted`。

### 3.2 需求 2：保留范围与生成入口

`procedure_scope_retention.py`：
```python
@dataclass(frozen=True)
class TrimmedScope:
    codes: frozenset[str]            # 粗裁码 ∪ 区间展开
    def is_trimmed(self, wp_code) -> bool   # 精确命中或以「码-」开头
    def split(self, codes) -> tuple[list[str], list[str]]  # (保留, 裁掉)
async def load_trimmed_scope(db, project_id) -> TrimmedScope   # 失败抛 TrimScopeUnavailable
async def recycled_codes(db, project_id, codes) -> set[str]    # 已软删的同码
```
实施修订（批 2）：判定改为「**最近一级有程序行的编码决定**」—— 从编码往上逐级找母码（断点 = `-` 之前，以及数字后紧跟非数字之前：`M4A`→`M4`、`B5附件`→`B5`；`G10` 不是 `G1` 的子表），每级先看普通行再看区间行，同级冲突「执行」优先；子码自带「执行」行时保留（`A1` 被裁、`A1-11` 执行 ⇒ 保留，与页面每行显示一致）。安徽实际受影响 138 张（132 + 程序表 M3A/M4A/M7A/M9A/M10A/N3A）。另加 `plan_generation`（新建 / 已裁 / 在回收站 / 已存在四分流）供各入口共用；`ProcedureService._expand_range_wp_code` 改调同一展开函数。
接入点（各自回执增加 `skipped_trimmed_codes`、`in_recycle_codes`）：`template_engine.generate_project_workpapers_detailed`、`wp_template.generate_from_codes`（两端点改 `require_project_access("edit")`）、`chain_orchestrator._step_generate_workpapers`（含第 8 步补建子底稿）、`b60_plan_service.ensure_workpapers_for_codes`、`wp_template_init_service` IPO 加载、`wp_template_copy_router._persist_copy_result`、`wp_conversion/_generate` 生成循环。`wp_template_list` 给每个模板加 `trimmed`，裁剪弹窗不预选并标「已裁剪」；前端 `summarizeWorkpaperGenerateResult` 提示跳过与回收站编码。

### 3.3 需求 3：回收站联动

新模块 `backend/app/services/workpaper_recycle_service.py`：
- `plan_recycle(db, project_id, scope_codes) -> list[RecycleTarget]`：范围内未删 wp_index（主码与「码-」子表）+ 名下 working_paper，附 `substantive_reasons`（working_paper 状态非 draft、复核状态非 not_submitted、`content_revision>0`、`file_version>1`、有人工填写的 `checklist_responses`（`updated_by` 非空）、有附件关联、有复核意见）。
- `move_to_recycle_bin(db, project_id, targets, *, kind, reason, actor)`：两层 `is_deleted=True`，lineage 追加 `{action:"recycled", kind, reason, actor, at, trim_codes}`，`bump_policy_epoch`。
- `restore_from_recycle_bin(db, project_id, *, wp_index_ids=None, trim_codes=None, actor)`：两层复活（`trim_codes` 只复活 lineage 末条为 `kind="trim"` 的），lineage 追加 `restored`，`bump_policy_epoch`。

`procedure_trim_service.apply_scheme`：每个 scope 计划 —— 目标 skip / not_applicable ⇒ `plan_recycle` + 有实质内容且未确认则 409（`substantive_recycle_unconfirmed`，列出编码）+ `move_to_recycle_bin`；目标 execute ⇒ `restore_from_recycle_bin(trim_codes=...)` 并对级联取消的任务 `reopen`。级联任务改按 `wp_index_id ∈ 范围` ∪ `wp_code == 码` 匹配（去掉 `audit_cycle_snapshot` 条件）。preview 增加 `recycle_preview: {to_recycle, substantive, to_restore}`；apply 请求增加 `confirm_substantive_recycle`。前端 `saveTrim` 有待移入时弹确认框（列编码与有内容标记）。

`routers/recycle_bin.py`：`working_paper` 类型改按 wp_index 列出（名称 = 编码 + 底稿名，id = wp_index.id），恢复调 `restore_from_recycle_bin`，彻底删除 / 批量删除 / 清空对底稿返回 409；列表按用户可访问项目过滤（admin 全部），恢复 / 删除按行的 `project_id` 调 `assert_project_permission(..., "edit")`，无项目归属的行只给 admin；清空只给 admin。

### 3.4 需求 4：委派

- `delegation_transaction.delegate_lead / delegate_row`：非清空时 `TrimmedScope.is_trimmed(wp_code)` ⇒ `DelegationError(trimmed)`；`delegate_row` 另查任务 `applicability_status == execute` 且未取消。`_enforce_scope` 改用有效范围，被委派人为主管时跳过；扩权只把新增循环写入 `project_users.scope_cycles`。lead 委派同步写 `wp_index.assigned_to`（展示镜像）。
- `procedure_delegation_service`：`_trimmed_scopes` 改为保留范围判定（按码，不按循环快照）；preview 返回 `scope_gaps`（被委派人缺的循环），apply 缺循环且未带 `expand_scope + scope_reason` ⇒ 400 `out_of_scope`，带了则扩权并 `bump_policy_epoch`。
- 旁路：`wp_batch_router.batch_assign` 限定 `WorkingPaper.project_id`，主编改走 `delegate_lead`（入参可为 staff_id 或 user_id，统一解析为本项目唯一 active staff），复核人保留直写但校验项目成员；`batch_assign_enhanced` 同样改走 `delegate_lead`、鉴权改 `ensure_project_delegator`；`working_paper_service.assign_workpaper` 主编走 `delegate_lead`；`handover_service` 按 staff→user 正确换算后走 `delegate_lead`；`wp_mapping.assign/{wp_code}` 返回 410。四个入口都接受 `expand_scope / scope_reason`，错误体统一 `{error:"lead_delegation_rejected", reason, cycles}`。
- 前端 `composables/useScopeExpansionRetry.ts`：识别 `out_of_scope`，`ElMessageBox.prompt` 要理由后带参重试；接入主编下拉（`assignProcedures`）、程序委派向导与控制台行委派（`applyProcedureDelegation`）、`BatchAssignDialog`。

### 3.5 需求 5：可见范围

`wp_visibility/effective_scope.py`：
```python
SUPERVISOR_ROLES = 归一后的 {partner, signing_partner, manager, qc, eqcr} ∪ ROLE_MAP 中文别名
@dataclass(frozen=True)
class MemberScope: is_supervisor: bool; cycles: frozenset[str]; assigned: frozenset[str]; expanded: frozenset[str]
async def resolve_member_scope(db, project_id, user_id) -> MemberScope
```
- 分类器 `_is_supervisor`：唯一 active staff + 唯一 active ProjectUser 不变，委派记录改为「任一有效委派角色 ∈ SUPERVISOR_ROLES」；`_resolve_scope_cycles` 返回 `MemberScope.cycles`。
- `deps.get_user_scope_cycles`：系统 admin / 系统 partner / 项目主管 ⇒ `None`；受限 ⇒ 列表（可为空）。`disclosure_notes` 两处过滤由 `if allowed_sections:` 改为 `scope is not None` 即过滤（空范围不再全放行）。

### 3.6 需求 6：细裁

新模块 `backend/app/services/procedure_row_trim_service.py`：`resolve_row_task(db, project_id, wp_id, sheet_name, program_no)` —— 取底稿与 wp_index（项目校验）→ `resolve_program_template_code(sheet_name, wp_code)` 得程序表码 → 按 (template_code, program_no) 找定义，缺则从 `procedure_table_templates.json` 经 `ProcedureDefinitionImporter.build_from_json_template + import_definitions` 导入 → 找 active 任务，缺则 `materialize + bind_working_paper` → 返回任务；自加行或模板无此行 ⇒ 422。`trim_row / restore_row` 调 `ProcedureTrimService`。
端点（`routers/procedure_trim.py`）：`POST /api/projects/{pid}/procedure-trim/workpapers/{wp_id}/program-rows/not-applicable|restore`，体 `{sheet_name, program_no, reason, request_id}`，`require_project_delegator_pid`，router commit。
展示投影：`wp_render_strategies/_a_program.py` 两条路径（持久化 programs / 重新生成）都调 `project_row_applicability`：按 (wp_index, 表码, program_no) 取任务，任务不适用 ⇒ 行 `status=not_applicable`、`trim_reason` = 最近一次裁剪历史理由；任务已恢复而行仍为不适用 ⇒ 置 `pending`。只读，失败不阻塞渲染。
前端 `composables/useProgramRowTrim.ts`：控制台单条 / 批量裁剪、从裁剪恢复先调端点，成功后改本地状态并保存，失败回滚提示。`useWpCompletionRate.calcACompletion` 排除不适用。

### 3.7 需求 7：行级编辑

新模块 `backend/app/services/wp_visibility/program_row_guard.py`：
- `resolve_row_access(db, user, wp, sheet_name) -> RowAccess(full_power, can_trim, own_program_nos, assignee_names)`：分类 + `grants_for_wp_index`；`full_power` = 有 admin / supervisor_scope / lead grant；`own_program_nos` = 该底稿该程序表码下适用且未取消、执行人映射到当前用户的任务程序号；`can_trim` = 项目委派人。
- `merge_program_sheet(old, new, access) -> (merged, ignored_program_nos)`：受限用户只接受本人行的 `status`（不含 not_applicable）、`execution_summary`；新增 / 删除行、`trim_decisions`、`signatures` 保留旧值。
接入：`wp_html_save.save_html_data` 在写入前对含 `programs` 的 sheet 调用，响应增加 `ignored_program_nos`；`wp_field_overrides` 写入补 `assert_project_permission(..., "edit")`，`procedure_table:*` 作用域对受限用户校验本人行。新端点 `GET /api/workpapers/{wp_id}/program-row-access?sheet_name=`（新路由文件，注册到 workpaper 组，自动挂可见性门）。
前端 `composables/useProgramRowAccess.ts` + 控制台：非本人行状态下拉与执行说明只读并显示执行人；多选、批量裁剪、新增、委派只对 `full_power`（裁剪另需 `can_trim`）显示。

### 3.8 需求 8：安徽处置工具

正式工具 `backend/scripts/fix/recycle_trimmed_workpapers.py --project-id ... [--dry-run|--apply] [--restore-misjudged]`：① 用新判定复核粗裁码，有数据的经 `ProcedureTaskTransitionService.set_scope_status` 恢复执行（理由「系统误判更正：…」）；② 其余经 `workpaper_recycle_service` 移入回收站，清单写 `backend/backups/recycle_trimmed_{pid}_{时间}.json`；③ 经 `chain_orchestrator` 生成步骤重跑生成；④ 打印对账。可重跑（第二次 0 动作）。

## 4. 接口变化汇总

| 接口 | 变化 |
|---|---|
| `GET /procedure-scope/data-availability` | 新增 `subject_unknown`、`evidence` |
| `POST /procedure-trim/preview` / `apply` | preview 增 `recycle_preview`；apply 增 `confirm_substantive_recycle`，未确认 409 |
| `POST /procedure-trim/workpapers/{wp_id}/program-rows/not-applicable|restore` | 新增 |
| `GET /workpapers/{wp_id}/program-row-access` | 新增 |
| `POST /workpapers/{wp_id}/save` | 响应增 `ignored_program_nos` |
| `/working-papers/generate`、`/generate-from-codes` | 改 edit 鉴权；回执增 `skipped_trimmed_codes`、`in_recycle_codes` |
| `PUT /workpaper-leads`、`/procedure-delegations/*`、`/working-papers/batch-assign`、`/workpapers/batch-assign-enhanced` | 接受 `expand_scope`、`scope_reason`；拒绝体带 `reason`、`cycles` |
| `/recycle-bin/*` | 底稿两层恢复、禁止彻底删除、项目鉴权 |
| `POST /assign/{wp_code}`（wp_mapping） | 410 |

## 5. 测试与变异

- 后端：`test_trim_subject_scope.py`（两种科目表方言、H3 回归、期初 / 发生口径、客户未映射、unknown）、重写 `test_procedure_trim_scope.py`、`test_procedure_scope_retention.py`、各生成入口过滤与回执、`test_workpaper_recycle_service.py`（PG 真库事务回滚：唯一索引下的复活）、apply_scheme 联动与级联修复、委派拦截与旁路收口、有效范围与分类器、细裁端点（PG：物化）、行级合并与 field-overrides 鉴权、回收站路由鉴权。
- 前端：决策内核档 4 矛盾守卫、`useScopeExpansionRetry`、`useProgramRowTrim`、`useProgramRowAccess`、完成率口径。
- 变异（逐个注入、确认红在预期断言上、逐字节恢复）：保留范围去前缀；生成入口去过滤；apply 去回收站联动；级联恢复快照条件；主管全循环去掉；行级合并直接放行；field-overrides 去鉴权；档 4 去矛盾守卫。
- 浏览器：admin 粗裁 → 预览确认 → 生成 → 委派给审计员（跨循环扩权）→ 审计员登录只见本人底稿、程序表整表可见只能改本人行。

## 6. 行数门与文件归属

`ProcedureTrimming.vue`（4012）、`GtAProgramConsole.vue`（1889）、`procedure_trim_service.py`（1086）HEAD 已超限且未登记白名单 ⇒ 新逻辑放伴生模块，三文件按改前真实行数登记白名单（只许 +5%）。`commonApi.ts`、`wp_html_save.py`、`wp_template.py`、`chain_orchestrator.py` 已在册，控制在 +5% 内。其余新文件各自 ≤ 800 / 1500。`wp_account_mapping.json` 属并发 spec formula-fetch-followup，本 spec 只读。

## 7. 风险与范围外

- 受限用户空范围后，试算表 / 调整 / 附注对其为空（按用户裁决的口径；真实项目当前只有 admin 成员，无存量影响）。
- 程序表之外的 sheet 仍按整稿授权（程序执行人可编辑同底稿其他 sheet），需另行裁决是否也按页隔离。
- 粗裁本身不记操作人（`procedure_instances` 无列，preview 凭证有 actor）——未改，登记。
- 回收站其余类型的彻底删除仍会撞外键（与本 spec 无关），只对底稿拦截。
- 方案二（生成前按模板细裁、先委派后生成）另立项。

## 8. 实施记录

**批 2（任务 5~7）** 范围补充（同类入口一并收口）：自定义底稿单条 / 批量也走保留范围（已裁 409 / skipped，原因写明），单条与批量改 edit、批量预览改 readonly；准则切换预览 / 执行原只校验登录，改 readonly / edit，读不到裁剪结果 503 且不做任何改动；鉴权棘轮 `_IDENTITY_ONLY_BASELINE` 200→193。顺带修复的既有缺陷：跨项目模板复制在 commit 后调 dataclass 没有的 `model_dump`（复制落库、接口 500）、`working_paper.source_type` 未赋值（NOT NULL 插入失败）、目标已有同码且 overwrite 时撞唯一索引 —— 改为跳过并说明；IPO 加载与 B60 附件单条失败原为整会话 rollback / 无保存点，改为单条保存点。
范围外登记：`gt_coding.generate_project_index`（编码体系索引，`code_range` 是 `D0-D12` 这类分组码，非底稿编码，且仅空项目可跑）未接入；全链第 7 步单条失败仍整会话 `db.rollback()`（会丢同批已建底稿）；跨项目模板复制不校验来源项目读权限；自定义批量预览不标已裁（创建时跳过并写原因）；准则转换复活软删行只复活 wp_index、再插新 working_paper 会撞 `uq_working_paper_project_index`（批 3 改走回收站恢复）。

**批 3（任务 8~13）** 与 §3.3 / §3.4 的差异：
- 回收站：只回收由本次应用条目决定的底稿（覆盖判定沿用批 2）；粗裁恢复执行只恢复去向记录末条 `kind=trim` 的，级联只 reopen `scheme_scope_cascade` 取消的任务；有实质内容未确认在任何写入前 409。回收站路由按行的项目 edit 鉴权，仍被粗裁的底稿不能直接恢复（409），底稿彻底删除 409，清空限 admin。
- 委派：拦截与扩权写在 `wp_visibility/delegation_guard.py`、`procedure_delegation_scope.py`（mixin，两个服务文件否则超 800 行），旁路共用 `wp_visibility/lead_delegation_entry.py`。admin 视同主管；被委派人不是项目成员 ⇒ `not_project_member`（不能扩权，不自动建成员）；成员行 ≠ 1 ⇒ `mapping_invalid`；批量主编委派收齐全部缺口一次报出、路由整体回滚；行委派循环选择器按 `wp_index.audit_cycle`（物化快照兜底 'A' 会漏）；preview 对已裁 / 回收站底稿不物化；状态机端点 assign / reassign 改走协调器。拒绝体 `{error, reason, message, cycles[, scope_gaps]}`：已裁 / 回收站 409，读不到裁剪结果 503，其余 400。
- 旁路：批量分配与复核页指派改要求项目委派人（原 review 级，质控可改主编）；复核人仍直写但须是项目成员；人员交接先转团队分配，再按 staff→user 换算经委派（`expand_scope` + 交接理由，跳过已裁），接收人没有用户账号报错；`wp_mapping` 指派 410（登记 `_STUB_ENDPOINTS`）。
- 前端：首次请求静默，同一凭证 / 请求号 / 载荷带理由重试；主编下拉取消或被拒恢复为上次保存值（不重新加载，免丢未保存的裁剪）。
- 准则切换（批 2 遗留）：源独有底稿经回收站服务两层移入（`kind=standard_conversion`），切回时只恢复因准则切换移入的（原行原数据），别的原因在回收站的进回执 `in_recycle_codes`；`_generate_one_workpaper` 不再复活软删行（原写法必撞 `uq_working_paper_project_index`，保存点回滚后静默跳过）。真库现无此类归档行。
- 夹具与守卫：被委派人默认角色由经理改审计员（主管免检，用户裁决）—— `test_delegation_transaction*`、`test_task15_integration_explain`；`test_task23_zero_regression` 登记新增字段 `scope_gaps`、`summary.trimmed_excluded`、apply `scope_expanded / trimmed_excluded`，HEAD 侧判据改为「HEAD 有的不少 + 多出的已登记」；架构债务基线刷新 `GtAProgramConsole` 指纹（债务形态未变）；附注联动模块的注释改动撤回（零回归守卫要求与 HEAD 一致）。
- 验收：变异 35 个（B01~B29、F01~F06）全部红在预期断言上；ESLint 0 错误、44 条告警与 HEAD 相同；单区域 vue-tsc 13 条报错与 HEAD 相同（全在未改动行），注入的类型错误能报出。HEAD 同样红、与本 spec 无关：`test_task9_core_route_gate::test_checklist_put_allow_admin`（MissingGreenlet）、`test_wp_large_file_size_guard`（`wp_render_config.py` HEAD 已 1128 行）、两条真库现况判据（出现项目级报表配置 / 没有未设准则的项目）、`test_lazy_import_resolvability` 2 条（并发会话的新模块）。
- 真库污染（既有测试，本次回归跑到）：`tests/procedure_delegation` 里 backfill_runner / performance / reconcile / review_service / transition_service 提交真库、清理不开维护开关（`app.procedure_history_maintenance`）而失败，materialization 会把别的测试留下的定义物化到真实底稿上。本次留下 1 万条任务与定义（挂在第一个用户 testuser2 的临时人员名下，task_query 用例因此误红）、给真实用户的 4 条通知、凭证、复核会话 —— 已按维护开关清理，备份 `backend/backups/procedure_test_junk_*.json`；此后回归不跑这些文件。8 月以来留下的 T13 / 委派测试人员（testuser2 名下 111 份、yangzhi 29 份人员记录，两人因此人员映射不唯一）与和平药房 155 条旧任务未动，待用户决定。本 spec 的 `_cleanup_committed` 改为维护开关硬删、失败退回软删。本 spec 两个真库只读用例改为自建引擎（全局连接池跨事件循环复用，整套跑时报 `'NoneType' object has no attribute 'send'`）。
- 范围外登记：工时批量审批路由按旧表 `WorkHour` 做项目校验而服务审批 `WorkHourEntry` ⇒ 真实 id 不做项目校验（跨项目审批）；`HandoverRecord` 两个人员外键指向 users 但存 staff id（库里无外键、0 行）；`WorkpaperList.vue` 的 `batchAssign / delegate` 分支是死代码；走 `app.main` 的 SQLite 用例经审计中间件把日志写进真库 `logs`；`test_committed_code_imports_only_committed_modules` 在新模块入库前会红；附注就绪度 `summary` 仍按全部章节统计（只过滤了 `sections`）。

**批 4（任务 14）**：分类器改为一次调用 `resolve_member_scope`（主管判定与范围同一来源，查询异常受限空集）；`SUPERVISOR_ASSIGNMENT_ROLES` 改指向同一角色集合（含中文别名）。`get_user_scope_cycles` 对主管返回 `None`、受限返回列表（可为空）。附注目录树与就绪度去掉「对不上章节就不过滤」；调整分录列表原先整段 `try/except: pass`（取循环科目失败 = 全部放行），改为失败按空集过滤。委派通知「负责循环」：主管没勾选写「全部」，受限成员写「未勾选」。
- 与需求 5.3 的偏差：`idx_assignment_project_staff` 部分唯一索引使一份人员记录在一个项目只有一条有效委派；「同一人多条委派」只会经多份人员记录出现，与委派的人员映射校验一致按受限（各份勾选的循环合并）。
- 按裁决改写的既有用例都写明了裁决（主管看全部循环）：主管跨循环由「拒绝」改「放行」（task6 / task17 角色矩阵、DSH 宿主上界）；MCP 跨循环拒绝用例的样本换成受限审计员（经理不再是越界样本）。
- 范围外登记：DSH `test_denied_host_emits_no_sensitive_sql` 把 `wp_index` 的 id 当底稿 id 传给宿主授权，拒绝来自「找不到」而不是跨项目 / 跨循环判定，用例对这两类边界是空转的；`test_note_standalone_consolidated_only_scope` 两条、`test_task9_core_route_gate` 一条 HEAD 同样红。

**批 5（任务 15~18）** 与 §3.6 / §3.7 的差异：
- 细裁定位：按（底稿，程序表码，程序号）取这一行的全部有效任务 —— 模板改版后同一行可有新旧定义的任务，一起裁、一起恢复。裁剪时一条都没有，才按 JSON 模板算出这一行的定义、只建这一条任务（定义与任务都 ON CONFLICT，插入即绑定本底稿）；不整表物化（库里同模板码还有别的来源的定义，真库现有定义全是测试残留）。已有任务的行（含 xlsx 来源）不看模板；没有任务又不在模板里（自加行、无模板的表）422 `row_trim_unsupported`，控制台只在页面上标记。恢复只动不适用的任务、不建任务，用户另行取消的（仍适用）不动。
- 投影：两条渲染路径都调 `project_row_applicability`，只在最近一次行级决定（控制台细裁 / 裁剪方案的行条目）是恢复时把页面上的「不适用」改回待执行；粗裁级联与粗裁恢复执行不算（整张底稿的决定，粗裁期间底稿在回收站、页面没被改过 —— 算进去会把旧的页面裁剪、模板默认的不适用翻成待执行）；没有行级决定的行不动；已存数据深拷贝后投影，不就地改写；同一任务的事件按任务版本排序（创建时间是事务开始时间，并发时先后不可靠）。
- 行级编辑：裁剪 / 恢复只归项目委派人（同 `require_project_delegator_pid`）；主编、质控、EQCR 可改全部行，但「不适用」的进出、裁剪理由与裁剪决定保持服务端；受限用户本人行只收执行状态与说明；读不到归属 503、不落盘。行归属端点只靠路由级可见性门（与其余 `/{wp_id}/...` 端点同口径），去掉了函数体内的成员复核（过了门的主编可能没有成员行，复核会让控制台退回放开态）。
- 前端：两个组合函数合并为 `useProgramRowControl`；裁剪 / 恢复先落任务，成功才改页面，批量逐行、只改成功的；读不到行归属按原行为放开（服务端合并兜底）；宿主没传程序表页名（A10~A17、B2 / B13 / B19 汇总包内嵌的控制台）定位不到任务，与改前一样只在页面上标记；`/save` 回执的 `ignored_program_nos` 由编辑器提示。循环 *A 程序表（D~N）经 `CycleProgramConsoleTab` 以表码为页名、不发 `/save`，状态与说明走字段覆盖（`procedure_table:{表码}`），本人行校验同样生效。
- 字段覆盖：GET 原只校验登录（可读任意项目）补项目成员，POST 补 edit 与本人行；请求体带项目维的鉴权棘轮 87→84（含批 1 的模板清单），三个端点登记回归钉子（含源码变异）。
- 残余风险：服务端还没存过这张程序表时，分不清模板默认的「不适用」与本次改的 —— 受限用户非本人行只收模板原样状态（待执行 / 不适用），主编首存照收。
- 范围外登记：非循环程序表的字段覆盖前端写 `procedure_table:{页名}`、渲染读 `procedure_table:{表码}`（既有口径不一致）；`ensure_project_delegator` 只认英文角色码，中文别名的经理是主管（看全部、改全部）但不能裁剪 / 委派（批 3 起同样）；`WorkpaperEditor.vue` 单区域类型检查会拉进整张导入图而内存溢出，其改动只有一个导入与 `.then(warnIgnoredPrograms)`，由 ESLint 与浏览器实测覆盖。
- 验收：变异 34 个（B36~B58、F07~F17）全部红在预期断言上（B50 由同程序号用例打红：新建任务插入即绑定）；后端相关 20 个文件 317 passed；前端 12 个文件 106 passed；ESLint 0 错误、告警与 HEAD 相同（新增的两处状态字面量改用 `PROCEDURE_EXECUTION_STATUS`）；单区域 vue-tsc 21 条与 HEAD 逐条相同、注入的类型错误能报出；新用例文件审计模式不连网，两个在泄漏清单内的既有用例补了行归属 mock、不新增泄漏。HEAD（988c6809b，并发会话新提交）干净检出同样红、与本 spec 无关：`test_workpaper_writer_inventory` 4 条（清单裁决了源码里已不存在的写入方）、`test_lazy_import_resolvability` 2 条。

**批 6（任务 19）** 与 §3.8 的差异：
- 处置路径：不直接调 `set_scope_status` + 回收站服务，而是把项目现有的裁剪行原样（状态、理由不变）经 `preview_scheme` / `apply_scheme` 重放一遍 —— 移入回收站、按归属级联取消任务、纪元递增与联动全走同一条编排，不另写一份。
- 误裁复核：只恢复「系统按无数据自动裁剪」（`suggestion_state.reason_code=no_data` 且理由以「自动裁剪」开头）而新判定有数据的；用户手工裁剪的即使有数据也只报告（`data_but_manual`），不替用户改决定。更正理由经 `reject_suggestions` 记在建议状态上（恢复执行会清空 `skip_reason`，写在那里留不住）。
- 重新生成：按项目上次生成用的模板集（与已有底稿编码重合最多的那套，并列即报错）走模板集生成，不走全链生成步骤 —— 后者按试算表匹配底稿，会生成用户从没生成过的编码。
- 不变式在 `apply_cleanup` 内校验（仍在用的已裁底稿为空、回收站底稿下没有未关闭任务），不成立抛错、调用方整体回滚。
- 重药安徽执行结果：误裁 1 个（H3：期末 10,763,907.81、期初 0、本期借方 7,689,744.44、贷方 3,074,163.37，7 张底稿保留）；131 张底稿两层移入回收站；级联取消 17 条任务（I2 3、I2-1 11、I3 3，原按循环快照没被取消）；按「标准年审」模板集（1025 个编码）重新生成新建 0；任务状态 已分配 / 进行中 / 已复核 / 未分配 / 不适用 71 / 10 / 14 / 19 / 32 → 58 / 9 / 14 / 16 / 49。第二次 dry-run 0 动作。附带写入：17 条 `procedure_task.scheme_scope_cascade` 任务事件（未消费，可能给 testuser2 名下的临时人员发通知）、1 条预览凭证、17 条历史、1 条失效外发，可见性纪元到 47。

**批 7（任务 22 浏览器实测）** 实测发现并修复：
- 项目详情「人员委派」弹窗关闭只是隐藏，勾选的角色 / 循环从未落库（审计员能看哪些循环全靠这里）⇒ `TeamAssignmentStep.save()`：有改动才提交（保存会重写全部分配并逐人发通知，循环顺序不同不算改动）、成员列表没加载成功不提交、不带入向导 store 里别的项目的团队、失败返回 false；面板底部「关闭」与 × / ESC（before-close）都先保存，失败不关，保存中再点不重复提交。不在面板调 `validate()`（会把 store 里残留的别的项目写进向导状态），也不逐次即存（每次都重发通知）。
- 「参照项目」把路径字符串当函数调（`P_proj.list()`），抛错被吞 ⇒ 项目列表恒空，复制委派这条路一直走不通（HEAD 单区域类型检查的 TS2349 就是它）。
- 回收站恢复 / 删除 / 清空不带 `_silent`，全局拦截器先弹一次、页面 `handleApiError` 再弹一次 ⇒ 三个请求改静默（调用方只有回收站页，都自行提示）。
- 粗裁保存后不重取程序列表：行上 `wp_id` 决定「程序裁剪 ›」还是「未生成」，移入回收站的底稿仍可点进去、恢复的显示未生成 ⇒ 回执有移入 / 恢复时重取（其余三个保存入口原本就重取）。
- 控制台超出大组件行数守卫（≤1900，本 spec 加到 1916；任务 21 的前端选集只按 import 找用例，守卫读源码而漏选）⇒ 程序行委派对话框原样抽到 `composables/useProgramRowDelegate.ts`（1822 行），补组合函数用例与「委派成功后重拉 overlay」接线断言；选集加上读源码的用例。
- 环境所限：`PROCEDURE_ROW_TASKS_ENABLED=False` 控制台没有行委派按钮（行任务改用程序委派向导委派）；`ProcedureBackfillRunner` 无调用方，新项目在界面上导不进程序行定义，行任务只能经细裁端点产生。
- 范围外登记（未改）：程序表字段覆盖按「地址的 year 或今年」写、按项目审计年度读 ⇒ 从底稿列表打开（地址不带 year）时执行人填的状态 / 说明刷新后看不到（真库：审计员两项存在 2026 下，控制台显示待执行、说明为空），属 `audit-year-calendar-fallback-ratchet` 已登记的 `GtAProgramConsole.vue` 2 处；`GET /api/users/` 不校验登录（未登录可列全部用户名 / 邮箱 / 角色）且不返回 `is_active`（用户管理页全部显示「禁用」）、`PUT /api/users/{id}` 不存在（编辑用户保存必失败）；平台没有停用 / 删除用户的入口，`/api/security/lock-account` 引用未定义的 `db` / `HTTPException`（调用即 500）且不校验管理员；回收站「删除人」列恒空；底稿列表「编制人」恒「—」（列表接口无 `assignee_name`）；生成的 D2 / E1 `file_path` 为空。
