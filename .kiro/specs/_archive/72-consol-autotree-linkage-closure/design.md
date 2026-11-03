# 设计：合并模块自动建树、左树联动与四维表收口

## 1. 现状确认（2026-10-26 实测 / grep）

| 项 | 现状 | 证据 |
|---|---|---|
| 计算门 | `load_calc_basis` 调 `require_confirmed_scope`，未确认即 409；树一变又 409 | `consol_scope_confirmation_service.py`；真库【测试】公式同步集团推送失败 `SCOPE_CONFIRMATION_REQUIRED` |
| 树版本 | V183 两表；`confirmed_by NOT NULL` 引用 users | `V183__consol_scope_confirmation.sql` |
| 命名 | `_ROLE_SUFFIX`：（合并）（合并差额）（母公司）（本部）（母分差额），汇总「（汇总）」 | `consol_group_tree.py`（813 行，超 800 且未入白名单） |
| 拖拽改上级 | `PATCH /api/projects/{id}/parent-code` 只写上级代码与关系，不写上级名称；只要求登录 | `routers/project_wizard.py`（794 行） |
| 基本信息表 | 默认 5 个空行手录三码，`consol_scope`（0 行）可覆盖企业列 | `SubsidiaryInfoSheet.vue` / `ConsolWorksheetTabs.loadConsolScope` |
| 草稿 | 下游只认已审批，无任何预览 | `load_tree_entries(approved_only=True)` |
| 数据节点 | 右侧显示合并模板口径（乙的应收账款只有合计 70） | 浏览器实测 |
| 三棵树 | 布局中栏 `ConsolMiddleNav` + 页内常驻侧栏 + 集团架构页，互不同步 | `DefaultLayout.vue` / `ConsolidationIndex.vue` |
| 上期 | `load_view_context(本项目, year-1)` 年度不符被吞 ⇒ 恒空 | `routers/consol_report.py` |
| 右键合并明细 | 传行次、后端按科目码查持久化表 ⇒ 恒空 | `consol_report_breakdown_service.py` |
| 一致性校验 | 未 await ⇒ 500；判据按正负号 | `routers/consol_trial.py` |
| 手改试算 | `PUT /consolidation/trial/{id}` commit 未 await，假成功 | 同上 |
| 分录汇总表 | 另走 SQL、只按类型、键 `other_adjustment` 对不上枚举 `other`，导航里进不去 | `consol_entry_summary_service.py` / `ConsolWorksheetTabs.vue` |
| 四栏切换 | 布局收到 `four-col-switch` 带 tab 时 150 ms 后重发同一事件 ⇒ 自循环 | `ThreeColumnLayout.vue onSwitchFourCol` |

## 2. 决策

- **ADR-CAL-001 树版本自动记录、只在写路径记录**：读路径（报表 / 试算 / 差额表）按当前树读时计算，不写库；推送（写路径，逐步提交）在第一步前记录树版本。理由：读请求不提交事务，写了也会回滚；推送是「合并数落库」的时点，版本跟着落库结果走。
- **ADR-CAL-002 结构差异判定与指纹分开**：指纹（含展示名）用于判断「是否需要记新版本」；提示只看结构差异（节点增删、上级、类型、与上级关系）。本次改名只改展示名 ⇒ 现有版本指纹变化、但不弹结构变化提示，下次推送自动记新版。
- **ADR-CAL-003 版本表复用 V183**：V206 放开 `confirmed_by` 可空、加 `confirmation_mode`（user / auto）；手动「记录为新版本」沿用原 CAS 确认接口（mode=user）。
- **ADR-CAL-004 命名常量拆出**：命名与角色常量移到 `consol_node_naming.py`，`consol_group_tree` 再导出，顺带让后者回到 800 行以内。
- **ADR-CAL-005 拖拽改上级下沉到服务**：`group_links.reparent_project` 负责两口径同写（代码、名称、关系、控制方补齐、向导数据），路由只做鉴权与审计日志。
- **ADR-CAL-006 单棵树**：保留布局中栏 `ConsolMiddleNav`（加搜索），删除页内常驻侧栏；页面经事件 `consol-current-node` 同步中栏高亮。
- **ADR-CAL-007 数据节点走单体接口**：新组件读单体项目已有接口（报表 `GET /api/reports/{pid}/{year}/{type}`、附注 `GET /api/disclosure-notes/{pid}/{year}[/{section}]`），只读呈现，权限由单体接口自身判定；不在合并接口里拼单体数。
- **ADR-CAL-008 汇总表同源**：分录汇总表金额全部取自 `CalcBasis.elim_totals`（与试算、差额表同一份），笔数与方向提示取自同一批已归属分录。

## 3. 后端

### 3.1 树版本（R1）

`consol_scope_confirmation_service.py`：
- 删 `_is_legacy_boundary` 与 `require_confirmed_scope`；新增 `require_calc_year(db, project_id, year)`：项目审计年度与 `year` 不一致 ⇒ `HTTPException(409, {error_code: "SCOPE_YEAR_MISMATCH", message: "请求年度…与合并项目审计年度…不一致"})`。
- `record_scope_version(db, project_id, *, recorded_by, mode="auto") -> dict`：项目行 `FOR UPDATE`；锁定 ⇒ `{"recorded": False, "skipped": "locked"}`；当前指纹 == active ⇒ 不新建；否则旧 active 置 superseded、写新修订与节点快照。只 flush。返回 `{revision, created, mode, fingerprint}`。
- `structural_diff(old_nodes, new_nodes) -> dict`：按 `node_key` 比较 `added / removed / moved(parent_node_key) / changed(kind, relation) / renamed(company_name)`；`structural = added or removed or moved or changed`。
- `scope_version_info(db, project_id, result) -> dict | None`：`{revision, mode, recorded_at, matches, structural_change, diff}`，无版本时 `revision=0`。
- `_load_state` 去掉 legacy 字段；`confirm_scope` 写 `confirmation_mode="user"`。

`consol_calc_basis.load_calc_basis`：去掉 `allow_legacy_read`，调用 `require_calc_year`。

`consol_push_service._push_one(..., user_id)`：worksheet 步骤先 `record_scope_version(recorded_by=user_id)`，明细前缀「树版本第 N 版（本次记录）」。

`consol_tree_service.build_tree_view`：合并根时附 `scope_version`（失败只记日志、返回 None，不影响取树）。

迁移 V206 / R206（号在落盘前现取）：
```sql
ALTER TABLE consol_scope_confirmations ALTER COLUMN confirmed_by DROP NOT NULL;
ALTER TABLE consol_scope_confirmations ADD COLUMN IF NOT EXISTS confirmation_mode VARCHAR(10) NOT NULL DEFAULT 'user';
-- CHECK (confirmation_mode IN ('user','auto'))，DO 块按约束名判存在
```
R206：删约束与列、删 `confirmed_by IS NULL` 的版本、恢复 NOT NULL。

### 3.2 命名（R2）

`consol_node_naming.py`：`ROLE_* / KIND_* / MODE_* / MODE_LABELS / node_key / display_name`。`display_name(name, role, kind)`：

| 角色 | kind | 后缀 |
|---|---|---|
| consol | aggregate | （合并户） |
| consol_elim | elim | （差额户） |
| parent | data / aggregate | （单体母公司户） / （母公司户） |
| hq | data | （本部单体户） |
| branch_elim | elim | （母分差额户） |
| subsidiary / branch | aggregate | （汇总户） |
| subsidiary / branch | data | 原名 |

诊断文案里的「X（合并）」同步改「X（合并户）」。

### 3.3 拖拽改上级（R3）

`group_links.reparent_project(db, project, new_code, *, name_hint) -> dict`：同企业同年度两口径逐个 `apply_group_values`（`parent_company_code / parent_company_name / relation_to_parent`，控制方为空时按新上级补齐）；名称取新上级本年度项目（单体优先），取不到用 `name_hint`；返回 `{synced: [{id, name, report_scope}], parent_company_name, notices}`。路由改 `require_project_access("edit")`，请求体加可选 `parent_company_name`。

### 3.4 读时视图（R5 / R8.5 / R10）

- `load_view_context(..., include_drafts=False)`：`include_drafts` ⇒ `ViewContext.draft_basis`（分录状态 ∈ {draft, pending_review, approved}，同一树与试算表）。
- `trial_view(..., draft_basis=None)`：响应加 `node_kind / node_role`；有 `draft_basis` 时每行加 `consolidated_with_drafts`，列加 `{key: "consolidated_with_drafts", label: "含草稿预览"}`；加 `balance = {debit_total, credit_total, difference, balanced}`（节点合并数按科目自然方向分借贷性质求和）。
- `entry_drill_rows` 行加 `entry_type_label / description`；`individual_drill_rows` 行加 `parent_label`。

### 3.5 合并上期与右键明细（R8.1 / R8.2）

- `consol_report_view_service.prior_node_values(db, project_id, year, node_key, report_type) -> (values | None, reason)`：`prior_year_context.find_prior_project`（同企业代码、年度 − 1、同为合并口径）→ 上年项目 `load_view_context` → 同 `node_key` 合并数求值；取不到返回原因。`GET /consolidation/reports/{pid}/{year}` 用它，并在行上带 `prior_blank_reason`。
- `get_report_consol_breakdown`：路径参数是报表行次 ⇒ `child_contributions`（根节点）映射为原契约（`by_company` 每行带 `node_key / kind / source / pct / source_project_id`，`consolidated` = 后端合计，`elimination` = 差额子节点之和，`basis = "read_time"`）；否则沿用科目码持久化路径。

### 3.6 试算接口（R8.3 / R8.4）

`check_trial_consistency`：按 `account_sign` 归借贷性质；路由 `await`。删除 `PUT /consolidation/trial/{id}` 与 `ConsolTrialUpdate` 的路由引用。

### 3.7 分录汇总表（R9）

`consol_entry_summary_service.entry_summary(db, project_id, year)` 重写：`load_view_context(include_drafts=True)` → 对树内每个差额节点（树序）× 科目 × 类型取 `elim_totals[...].by_type` 的原始借贷，净额 = `sign × (借 − 贷)`；笔数来自 `basis.attributed` 的分录；`draft_net` 取 `draft_basis`。输出：

```text
{year, rows:[{node_key,node_label,hosted_here,account_code,account_name,entry_type,type_label,measure,debit,credit,net,draft_net,entry_count}],
 by_type:[...], totals:{debit,credit,balanced}, reconcile:{matched, mismatches:[...], persisted_stale},
 orphans:[{entry_no, reason}], warnings:[...]}
```
对账：逐科目 Σ 调整 / Σ 抵销 vs `trial_amounts(basis)`；`persisted_stale` = 持久化 `consol_trial` 与读时不一致。方向提示：`internal_ar_ap / internal_trade` 分录所有明细行 `sign × (借 − 贷) > 0`。

## 4. 前端

| 文件 | 改动 |
|---|---|
| `consolTreeView.ts` | 角色标签按 kind；`nearestAggregateAncestor`、`standaloneEntityOf`、`treeOptionsWithDepth` |
| `consolSubsidiaryInfo.ts`（新） | `treeMemberInfos(root)`、`alignInfoRows(saved, members, mkEmpty)` |
| `ConsolMiddleNav.vue` | 搜索；树版本标签 + 结构变化提示 + 「重新推送」；监听 `consol-current-node` 高亮；差额户右键「📝 差额分录」 |
| `ConsolScopeConfigDialog.vue` | 改「企业树版本」：版本、差异、成员、诊断；「记录为新版本」可选；`mode="created"` 用于向导 |
| `ConsolidationIndex.vue` | 删页内侧栏；当前节点上下文条；差额户不自动弹抽屉 + 「📝 差额分录」；数据节点切 `ConsolEntityStandalonePanel`；就绪门；进附注页切四栏；`consol-current-node` 广播；子组件 `node-change` 回写 |
| `ConsolEntityStandalonePanel.vue`（新） | 单体报表表格 / 附注目录 + `NoteTablesReadonly`；无项目、403、未生成三种说明；进入项目 |
| `NoteTablesReadonly.vue`（新） | `table_data` 只读渲染：`_tables` / 单表、`headers` + `_column_groups` 两级、`multi_header` 多级（rowspan / colspan）、合计行加粗、表后文字 |
| `ConsolTrialBalanceTab.vue` | 全部节点下拉 + `node-change`；口径说明；含草稿预览列高亮；平衡提示；穿透补全 |
| `ConsolReportBreakdownView.vue` | 非汇总节点 ⇒ 上级汇总节点 + 高亮列；`node-change` |
| `ConsolBreakdownDialog.vue` | 新契约：下级节点 / 来源 / 金额 / 占比，合并数取后端 |
| `EntrySummarySheet.vue`（新） | 分录汇总表（从 `ConsolWorksheetTabs` 抽出），进「合并抵消」分组 |
| `SubsidiaryInfoSheet.vue` | `treeLocked`：三码只读、去新增、只能删「已不在企业树中」、按代码导入 |
| `ConsolWorksheetTabs.vue` | 企业列只认企业树；基本信息表对齐；接 `EntrySummarySheet` |
| `ThreeColumnLayout.vue` / `eventBus.ts` | `four-col-switch` 只转发一次（`_relayed`） |
| `ConsolidationHub.vue` | 拖拽成功提示同步了哪些项目 |
| `BasicInfoStep.vue` / `ConsolElimNodePanel.vue` | 文案按新命名 |

## 5. 验证

- 后端 pytest：范围确认（改写为自动版本）、命名、改上级同步与鉴权、上期、右键明细、一致性校验、PUT 已删、草稿预览列与平衡、分录汇总表同源 / 对账 / 方向提示、推送记录版本；既有合并套件回归（失败集合与改前逐条对比）。
- 前端 vitest：上述组件与纯函数；单区域 vue-tsc + 变异证明。
- 变异：每条判据在生产代码注入反例（磁盘变异逐字节恢复）须打红。
- 浏览器（chrome-devtools，只读为主）：某测试集团_2098 点各类节点、`?tab=report` 直接进入、附注页四栏、试算页草稿列与口径说明、分录汇总表、右键明细；【测试】公式同步集团推送在回滚事务探针里验证（不落库，避免干扰并发会话）。

## 6. 风险

- `ConsolidationIndex.vue`（白名单 2368，门 2486）与 `ConsolWorksheetTabs.vue`（1649，门 1731）有体量门：删侧栏、抽 `EntrySummarySheet` 抵消新增。
- `ConsolidationIndex.vue`、`consolidationApi.ts`、`ConsolNoteTab.vue`、`ConsolCatalog.vue` 有并发会话未提交改动：只做定点替换；提交时只暂存本 spec 的改动块。
- 展示名进指纹：上线后现有版本一次性「不一致」，按 ADR-CAL-002 不弹结构提示。
