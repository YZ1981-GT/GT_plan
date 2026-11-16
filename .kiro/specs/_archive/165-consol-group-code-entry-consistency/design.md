# 三码入口一致与改上级并发保护 — 设计

需求见 `requirements.md`（R1~R6）。本文写现状落点、取舍、接口与测试，不复述需求。

## 1. 现状确认（HEAD `39777a020` 现读）

### 1.1 写入口校验链

| 入口 | 规范化 | 校验 | 入库 | 位置 |
| --- | --- | --- | --- | --- |
| 单建：上级 / 控制方 | `strip().upper()` | 规范化值校验 | 交给 `prepare_group_fields`，按原值再校验一次，小写在这里被拒 | `project_creation_coordinator.py:30-38` → `group_links.py:65-96` |
| 单建：企业代码 | `strip()` | 去空白后校验 | 写原值 | `project_wizard_service.py:255-264`、`:104` |
| 向导保存基本信息 | 无 | 上级 / 控制方经 `prepare_group_fields`；企业代码**不校验 USCC、不判唯一** | 写原值 | `project_wizard_service.py:430-455` |
| 向导 pydantic | `company_code = Field(min_length=18, max_length=18)` | 带空格 → 长度错误 | — | `audit_platform_schemas.py:95`；报错只列英文字段名 `:436-441` |
| 批量导入 | `_cell` 只 `str(value).strip()` | 按原值校验 | — | `batch_project_workbook.py:216-219`、`:284-293` |
| 拖拽改上级 | 路由 inline `strip()` | `reparent_project` 锁内校验 | 写原值 | `routers/project_wizard.py:425`、`group_links.py:399-436` |
| 建项授权 | `normalize_company_code` = `strip().upper()` | — | — | `project_creation_grant_service.py:36` |
| 纳入下级 | 读库内父项目值 | 不校验 | 复制父项目已存值 | `project_subsidiary_attachment_service.py:88-118`，无前端调用方 |

前端 `BasicInfoStep.vue:497-526`：企业代码校验不去空白，上级 / 控制方去空白不转大写；`utils/uscc_validator.ts` 与后端同规则，二者共用 `backend/tests/fixtures/uscc_test_vectors.json`（前端经 `@fixtures` 别名读取）。

### 1.2 报错口径

单建与 `normalize_group_fields` 为 `"{字段}：{原因}"`；批量为 `"{字段}格式错误：{原因}"`（`batch_project_workbook.py:292`）；企业代码三处都不带字段名（`:285`、`project_wizard_service.py:263`）。既有测试只钉住 `test_group_links.py:106` 的 `"{字段}：…"` 与两处 `startswith("基本信息字段缺失或格式错误：")`，统一后不破坏。

### 1.3 Excel 模板与基线 hash

- 代码列未设 `number_format`；工作表保护默认禁止设置单元格格式（`_style_data_sheet :379-401`）；示例企业代码 `911100002000000005` 是纯数字（`:87-88`）。
- 读取 `load_workbook(read_only=True, data_only=True)`（`:177`）。数字类型的代码经 `str()` 变成 `'9.11100002e+17'`（报「必须为 18 位」）或后三位为 0 的整数（报校验码错误，约 1/31 概率碰巧通过）；公式单元格缓存为空时读到 None，按「未填」处理，上级 / 控制方静默丢失。
- 两套 hash：`entity_group_fields_hash`（`:491-508`）供预校验与执行比较（`batch_project_plan.py:411`、`batch_project_execution.py:624`）；`group_fields_hash`（`:511-516`）只被 `batch_project_export._project_export_row` 在 `action=="update"` 且未传基线时使用（`:38-39`），算法不同、永远比对失败。现有两个调用方都显式传了基线，该分支是陷阱而非活路径。

### 1.4 共享库现查（只读，2026-11-11）

20 个未删除项目，三码共 0 个小写、0 个首尾空白、0 个 USCC 字符集外字符；纯数字企业代码 5 个；`parent_company_code = ''` 2 个（读取方按空处理，R1 不回填）。⇒ 存储端改为写规范化值对存量零影响，不需要数据迁移。

### 1.5 拖拽改上级

前端 `ConsolidationHub.vue:499-503` 只发 `{parent_company_code, parent_company_name}`；森林节点带 `parentCompanyCode`（`group_forest.py:80,126`）。服务端 `reparent_project` 先 `lock_topology_years` 再 `db.refresh(project)`（`group_links.py:419-424`），然后只做 USCC 与成环检查，后写覆盖前写。调用方：前端 1 处；后端测试 `test_group_links_reparent.py`、`test_group_links_sync.py`、`test_parent_code_update.py` 共约 12 处直接 PATCH。

### 1.6 差额表端点

AST 现算全部路由：函数有 `project_id` 参数且读其他参数 `.project_id` 的共 4 个，其中 3 个没有比较（全在 `consol_worksheet.py`）：

| 端点 | 鉴权 | 执行用 | 后果 |
| --- | --- | --- | --- |
| `POST /recalc` `:251-262` | query，edit | `body.project_id` | 可对无权项目全量重算差额表 |
| `POST /pivot` `:328-341` | query，readonly | `body.project_id` | 可读无权项目的合并数 |
| `POST /pivot/templates` `:374-388` | query，edit | `body.project_id` | 可往无权项目写查询模板 |

`consol_report.py:63` 是正例（不一致即拒）。前端 `consolidationApi.ts:1393/1417/1436` 三个包装函数只发请求体、不带 query，全仓无调用方。

### 1.7 建项授权与改企业代码

- 授权入口：`authorize_creation_codes`（`project_creation_grant_service.py:103-148`，admin / partner 直通 `:18`，manager 查有效授权，其他角色 403 `COMPANY_CREATION_NOT_AUTHORIZED`）与年度锁后的 `lock_and_revalidate_creation_codes`（`:193-245`）。单建（`project_creation_coordinator.py:41-56,76-92`）、批量、连续审计三处已接；向导保存没有接。
- AST 现算全后端给 `Project.company_code` 赋值只有 `_sync_basic_info_to_project`（`project_wizard_service.py:104`）一处（`group_links.py:259` 的 `setattr` 只写集团五字段），即向导保存是唯一能改企业代码的路径。

### 1.8 企业代码被引用的位置（共享库 information_schema 现查）

| 表 | 列 | 性质 |
| --- | --- | --- |
| `projects` | `parent_company_code`、`ultimate_company_code`；同代码另一口径项目 | 关系输入 |
| `consol_note_data` | `node_key`（`代码:角色`），3267 行 / 15 个节点 | 合并附注节点数据 |
| `consol_note_mapping_binding` | `entity_node_key`（无年度列，按所属合并项目年度） | 明细映射绑定 |
| `consol_worksheet` | `node_company_code` | 差额表 |
| `share_change_event` | `node_key` | 股权变动输入 |
| `consol_scope_confirmation_nodes` | `company_code` / `node_key` | 树版本快照（历史） |
| `consol_artifact`、`report_generation_run` | `node_key` | 产物与运行记录（历史） |

`tb_balance` / `trial_balance` 的 `company_code` 是四表内部编码，与项目 USCC 现查 0 行相同，不受影响。

### 1.9 企业树诊断的现有展示

`build_entity_graph` 对重复记录择一进树并出 `duplicate_project`（`consol_group_tree.py:301-312`），`_make_entity` 对两口径不一致出 `relation_conflict`（`:227-240`），`Diagnostic` 只带 `company_code` / `node_key`（`:133-150`）。前端只在合并工作台顶部放一条可关闭的横幅（`ConsolidationIndex.vue:33-54`），关闭后本次不再显示；三个手工推送入口（`ConsolidationIndex.vue:857`、`ConsolPushPanel.vue:141`、`ConsolTrialBalanceTab.vue:337`）推送前都不看诊断。批量预校验已把这两类列为阻断（`batch_project_plan.py:536-541`）。共享库现查两类均 0 条（唯一索引 `uq_project_company_year_scope` 防同码同年同口径；现存唯一一对两口径项目关系一致）。`consol_group_tree.py` 791 行，离上限 800 只剩 9 行。

## 2. 取舍

### 2.1 规范化：入口友好转换，不一律拒绝小写

| 方案 | 结论 | 理由 |
| --- | --- | --- |
| A 各入口统一拒绝小写 / 空格 | 否 | 授权服务已在转大写，拒绝会让「授权能通过、建项被拒」；全角输入在中文输入法下常见 |
| B NFKC + strip + upper 后校验、按规范值入库 | **采用** | 与授权同口径；共享库零冲突（§1.4）；中间空格与非法字符仍拒，不猜测修复 |

规范化函数放在 `uscc_validator.py`（`normalize_uscc_input`），校验函数签名不变；授权服务的 `normalize_company_code` 改为委托它（空值行为保持：授权侧空串仍按原逻辑处理，见任务 1）。读取侧 6 处 `strip()` 不动（R1.6）。

### 2.2 报错保留字符串 detail

改成 dict 会破坏 `handleApiError` 与批量错误表的现有读取；只统一文案格式。授权类 409 已是 dict，保持。

### 2.3 改上级 CAS：比较上级代码，不用 entity hash

entity hash 输入是同企业同年度全部项目的 id / 口径 / 上级 / 控制方 / 关系（§1.3）。森林只给上级代码，客户端算不出；改森林接口去暴露这些字段只为了算 hash，代价大于收益。拖拽只改上级一个维度，比较「改前上级」已覆盖丢失更新；控制方与关系由服务端按新上级推导（`infer_ultimate_from_parent` / `resolve_relation`），不属于用户在本次拖拽里看到并决定的内容。

缺字段严格 428（与 `consol-note-save-integrity-closure` §2.2 同理）：前端调用方只有 1 处，后端测试一并改，放行缺字段只会留一条不受保护的旁路。

### 2.4 Excel：拒绝数字单元格，不尝试还原

18 位整数超出 Excel 15 位有效数字，读到的值已丢精度，不可逆；按原值猜测会造成碰巧通过的错误代码。公式单元格只在缓存为空时拒绝，靠第二次以 `data_only=False` 只读加载、只扫三列判定是否为公式（批量上限 `MAX_IMPORT_ROWS`，额外开销可接受；不改其他列的读法）。

### 2.5 改企业代码只对新代码授权

建项授权管的是「谁能在哪个企业代码下有项目」。改企业代码等于把项目挪到新代码下，须对新代码授权；旧代码已有项目，不再要求。上级 / 控制方代码变化不授权：批量「更新集团关系」（`required_creation_codes` 只取 `action == "create"`）与拖拽改上级都不要求，向导保持同口径，避免同一改动在三个入口授权要求不同。

### 2.6 有引用就拒绝，不做「确认后照改」

| 方案 | 结论 | 理由 |
| --- | --- | --- |
| A 弹窗确认后照改 | 否 | 下级的上级代码仍是旧码 ⇒ 全部脱挂；合并附注、映射绑定、差额表挂在旧 `node_key` 上 ⇒ 静默变成孤儿数据，且无工具找回 |
| B 确认后级联改写引用 | 否（本 spec） | 要区分「代码更正」与「主体变更」（review §3.5）、改写 6 张表并留 `old → new` 映射，属节点身份迁移，规模与风险超出入口一致 |
| C 有引用即 409 并列出影响，无引用照常改 | **采用** | 新建后发现录错、尚无下游数据的场景（最常见的更正）不受影响；有下游数据时用户看得到原因 |

判据只看同一审计年度：历年数据按当年身份保留（review §3.5「历史年度默认继续使用当时的节点身份」）。历史留痕类表（树版本快照、产物、运行记录）不算引用。表清单由 R6.5 守卫钉住，新加节点身份列须当场归类。

### 2.7 冲突提示：弹窗，不阻断

保留 2026-10-27 裁决（计算门只校年度）。横幅可关闭、推送时看不到，是这两类诊断「用户没注意到」的原因；弹窗解决可见性，不改变计算行为。弹窗只针对这两类（会让企业树取值与用户以为的不同），其余诊断（脱挂、关系未填等）仍走横幅，避免弹窗泛滥。推送前现取诊断而不读页面缓存：推送面板与试算表不一定在合并工作台里打开。

## 3. 接口变化

### 3.1 `PATCH /api/projects/{project_id}/parent-code`

```json
{ "parent_company_code": "91110000…", "parent_company_name": "…", "expected_parent_company_code": "91110000…" | null }
```

- 请求模型 `UpdateParentCodeRequest` 增加字段；按 `model_fields_set` 判断是否提供（null 是合法期望值）。未提供 → 428。
- `reparent_project(db, project, new_code, *, name_hint=None, expected_parent_code=_UNCHECKED)`：在 `db.refresh(project)` 之后比较 `normalize_uscc_input(project.parent_company_code)` 与 `normalize_uscc_input(expected)`，不一致抛 409（dict detail，见 R4.2）。服务层默认不检查，供既有服务层调用方保持语义；路由层强制传入。
- 路由 inline `strip()` 改为 `normalize_uscc_input`。

### 3.2 差额表三端点

函数开头 `if body.project_id != project_id: raise HTTPException(422, "请求体项目与校验项目不一致")`，之后统一用 `project_id`。

### 3.3 向导保存基本信息

`update_step(basic_info)`：`BasicInfoSchema` 三码字段加 `field_validator(mode="before")` 调规范化（企业代码规范化后再判长度）；校验失败的 detail 用中文字段名表（`_BASIC_INFO_FIELD_LABELS`，放在 `project_wizard_service.py`）。企业代码 / 审计年度 / 报表口径任一与库内不同时，先 `validate_uscc`，再 `lock_topology_years` + `uniqueness_checker.check_uniqueness(…, exclude_project_id=project.id)`。该函数现无排除参数（`uniqueness_checker.py:12-32`），任务 2 增加仅限关键字参数、默认 None，`create_project` 与 `continuous_audit_service.py:153` 两个既有调用方不变。

### 3.4 向导改企业代码

`update_step(basic_info)` 入口已对新旧年度加拓扑锁并 `refresh`（`project_wizard_service.py:378-391`）。解析出 `BasicInfoSchema` 后，规范化的新企业代码与 `project.company_code` 不同时，在 `prepare_group_fields`（会读同企业另一口径等库存）之前依次执行：`authorize_creation_codes(db, actor, [新代码], entrypoint="wizard_company_code")` → `lock_and_revalidate_creation_codes(..., expected_snapshots=上一步快照)`（年度锁已持有）→ 唯一性（§3.3）→ 影响检查（新模块 `company_code_change_guard.py` 的 `code_change_impacts(db, project, old_code, year)`）。403 包装成 R2.5 文案；授权快照变化沿用单建的 409 `PROJECT_CREATION_GRANT_STALE`。服务层新增仅限关键字参数 `actor=None`；`actor is None` 且企业代码有变化时拒绝（fail-closed），避免内部调用绕开授权。

**顺带修复的越权**：`PUT /api/projects/{project_id}/wizard/{step}`（`routers/project_wizard.py:603-615`）与 `POST …/wizard/confirm`（`:636`）只依赖 `get_current_user`，服务层也只做存在性检查（`_get_project_or_404 :182-192`）⇒ 任何登录用户可改任意项目的基本信息与三码并确认。改为 `require_project_access("edit")`，路由把 `current_user` 传给服务层作 `actor`。新建项目流程不受影响：创建时创建者已写入成员行（`project_creation_coordinator.py:127-150`），admin 直通。同文件其余只依赖登录的端点（列表、详情、模板推荐、向导读取与校验等 9 个）只读或已在服务内鉴权，登记不改；鉴权基线 `_IDENTITY_ONLY_BASELINE` 按棘轮下调。

### 3.5 企业树诊断与前端弹窗

- `Diagnostic` 增 `project_ids: tuple[str, ...] = ()`，`to_dict` 输出列表；`duplicate_project` 填被丢弃与被选中两条记录的 id，`relation_conflict` 填合并与单户两条的 id。前端类型 `ConsolTreeDiagnostic` 增可选 `project_ids`。
- 新 `components/consolidation/composables/consolTreeConflicts.ts`：`treeConflicts(diags)` 只取两类；`conflictSignature(conflicts)`（排序后的 code + message 拼接，供会话内去重）；`confirmPushDespiteConflicts(projectId)`：`getWorksheetTree` 现取诊断，有冲突时 `ElMessageBox.confirm`（消息用 `h()` 生成列表，样式内联，不依赖 scoped 样式），取数失败返回 `true` 并 `ElMessage.warning('未能检查企业树冲突，已继续推送')`。
- 新 `components/consolidation/ConsolTreeConflictDialog.vue`：列表 + 每个 `project_ids` 一个「去修改」（`/projects/new?projectId=…`，与项目列表打开基本信息同一路由）+「我知道了」。合并工作台在 `loadGroupTree` 成功后判定是否弹出，已确认签名存 `sessionStorage`（键 `gt:consol-tree-conflicts:{projectId}:{year}`）。
- 三个手工推送入口在调用 `pushConsolidation` 前 `if (!(await confirmPushDespiteConflicts(id))) return`。

## 4. 落点

| 文件 | 改动 |
| --- | --- |
| `services/uscc_validator.py` | 新增 `normalize_uscc_input`、`format_code_error(label, reason)` |
| `models/audit_platform_schemas.py` | `BasicInfoSchema` 三码前置规范化 |
| `services/project_creation_coordinator.py` / `project_wizard_service.py` / `group_links.py` | 入口改用规范化函数；企业代码报错带字段名；update_step 唯一性 |
| `services/project_creation_grant_service.py` | `normalize_company_code` 委托 |
| `services/batch_project_workbook.py` | `_code_cell` 读三码（类型判断 + 规范化）、公式无缓存扫描、文本格式、示例文本、错误回显原值；删 `group_fields_hash` |
| `services/batch_project_export.py` | 删回退分支 |
| `routers/project_wizard.py` | `expected_parent_company_code`；向导保存与确认改 `require_project_access("edit")` 并传 `actor` |
| `services/company_code_change_guard.py`（新） | `code_change_impacts`：§1.8 表中「关系输入 / 合并数据」五类按旧代码、同年度计数 |
| `services/consol_group_tree.py` | `Diagnostic.project_ids`，两类诊断填 id（791 行，超 800 时把 `Diagnostic` 与 `sort_diagnostics` 移到新文件并保留导入） |
| `routers/consol_worksheet.py` | 三端点一致性检查 |
| 前端 `utils/uscc_validator.ts`、`components/wizard/BasicInfoStep.vue`、`views/ConsolidationHub.vue`、`components/consolidation/composables/consolReparent.ts` | 规范化、失焦写回、拖拽带期望值、409 提示 |
| 前端 `stores/wizard.ts`、`views/ProjectWizard.vue` | `saveStep` 增可选 `onForbidden` / `onConflict`（请求级处理，避免全局拦截器先弹「权限不足」或把 dict 显示成 `[object Object]`）；基本信息保存遇 `COMPANY_CODE_IN_USE` 用 `ElMessageBox.alert` 列出影响项，遇授权 403 显示授权原因 |
| 前端 `composables/consolTreeConflicts.ts`、`ConsolTreeConflictDialog.vue`（均新）、`ConsolidationIndex.vue`、`ConsolPushPanel.vue`、`ConsolTrialBalanceTab.vue` | 冲突弹窗与推送前确认（§3.5） |

## 5. 测试与变异

| 层 | 内容 | 文件 |
| --- | --- | --- |
| 向量 | `uscc_test_vectors.json` 增 `normalization` 组（全角、首尾空格、小写、中间空格、非法字符、空白→None），前后端各跑一遍 | `test_uscc_validator.py`、`uscc_validator.spec.ts` |
| 入口一致性 | 同一组输入（小写 / 全角 / 首尾空格 / 非法）分别走单建、向导保存、批量预校验、拖拽，断言通过与否一致、入库值相同、文案为 `"{字段}：…"` | 新 `test_group_code_entry_consistency.py` |
| 唯一性 | 向导把企业代码改成同年度同口径已有代码 → 409 | 同上 |
| Excel | 用 openpyxl 构造：代码写成 int / float、公式无缓存、公式有缓存、文本；断言错误文案与错误明细回显；导出 update 行 hash 与 `entity_group_fields_hash` 相等；无基线抛错 | `test_batch_project_import_closure.py` 增例 |
| 模板 | 下载模板三列数据区 `number_format == "@"`，示例行是 str | 同上 |
| CAS | 两次拖拽：第二次带过期期望值 → 409 且库值不变；缺字段 428；null 期望值对无上级项目通过 | `test_group_links_reparent.py` |
| 越权 | 三端点 body 与 query 不一致 → 422 且服务函数未被调用 | 新 `test_consol_worksheet_project_scope.py` |
| 守卫 | AST：有 `project_id` 参数又读 `X.project_id` 的路由必须含二者比较；基线 0 | 新 `test_route_body_project_id_consistency.py` |
| 前端 | 失焦写回规范化值；拖拽请求带 `expected_parent_company_code`；409 提示并 reload、不重试 | `BasicInfoStep` 相关 spec、`ConsolidationHub.reparent.spec.ts` |
| 改代码授权 | 走真实依赖链：manager 无新代码授权 → 403 且库值不变；有授权 → 通过；授权在年度锁后被撤销 → 409 `PROJECT_CREATION_GRANT_STALE`；partner / admin 直通；auditor 改代码 → 403；代码未变（只差大小写 / 空格）不触发授权；上级代码变化不触发授权 | 新 `test_wizard_company_code_change.py` |
| 改代码影响 | 五类引用各一例 → 409 列出该类计数；跨年度引用不算；无引用 → 保存成功 | 同上 |
| 节点身份列登记 | ORM 元数据中 `node_key` / `entity_node_key` / `node_company_code` 列须在影响清单或豁免表；内置变异：临时模型加一列须打红 | 同上 |
| 向导越权 | 非成员 PUT 基本信息 / POST 确认 → 403；edit 成员通过；鉴权基线下调 | `test_project_wizard_router.py` 增例、`test_project_endpoint_authorization_baseline.py` |
| 诊断 id | 两类诊断带 `project_ids` 且为真实项目 id | `test_consol_group_tree.py` 增例 |
| 冲突弹窗 | 有两类诊断时弹窗；确认后同签名不再弹、签名变化再弹；「去修改」路由；三个推送入口有冲突时取消即不推送、确认后推送、取诊断失败照推并提示；只有其他诊断时不弹 | 新 `consolTreeConflicts.spec.ts`、`ConsolTreeConflictDialog.spec.ts`、`ConsolPushPanel.spec.ts` / `ConsolTrialBalanceTab.spec.ts` 增例 |
| 向导弹窗 | `saveStep` 遇 `COMPANY_CODE_IN_USE` 弹出影响清单、遇授权 403 显示原因，表单保留 | `ProjectWizard` 相关 spec |

变异（每条确认红在预期断言上）：规范化去掉 NFKC / 去掉 upper；某一入口改回不规范化；入库改回原值；批量文案改回「格式错误：」；数字单元格改回 `str()`；公式无缓存改回当空；导出恢复旧 hash 回退；CAS 比较删除 / 改为锁前比较；路由缺字段改放行；三端点任一删比较；守卫把比较判据改成恒真；向导改代码删授权调用 / 授权挪到库存查询之后 / `actor is None` 改放行；影响检查任一类删除 / 不按年度过滤；向导路由改回只校登录；推送入口删确认；弹窗去重签名改成恒等。

浏览器实测（【测试】项目，写入后复原）：向导输入小写 / 带空格代码保存后显示规范值；下载模板用 Excel 输入纯数字代码导入看到针对性提示；两个标签页同时拖拽同一节点，后者提示并刷新；用无该代码授权的【测试】经理账号改企业代码看到授权提示；对有下级的【测试】企业改代码看到影响清单弹窗；用 `initScript` 拦截树接口注入两类诊断，看到进入弹窗与推送前确认。

## 6. 范围外与待拍板

| 项 | 处置 |
| --- | --- |
| 回执 `tree_kind` | 不做：森林与合并树的键格式不同（`code@year` / `code:role`），合并类接口都在服务端自建树，无误用路径 |
| 树指纹加规则版本号 | 不做：指纹由树的输出算出（`consol_scope_confirmation_service.py:45-120`），规则变化导致输出变化即被识别 |
| 纳入下级接口 | 不改：复制的是库内已规范化的父项目值；无前端调用方 |
| 批量「与上级关系」认英文 | 不做：模板该列有下拉校验 |
| 前端差额表三个包装函数 | 不改：无调用方；如需启用须改为带 query `project_id` |
| 向导改企业代码是否要求建项授权 | **已定（用户 2026-11-11）**：要求，见 R2.5 / §2.5 / §3.4 |
| 重复项目与关系冲突是否阻断 | **已定（用户 2026-11-11）**：不阻断，弹窗提示，见 R7 / §2.7 |
| `AMBIGUOUS_SELF_REFERENCE` | **已定（按建议）**：不加。现网三码相同一律判 `SELF_ULTIMATE` 且有中文提示（`group_relation.py:105-126`），没有出现「无法判断」的业务场景；加第三态需要所有入口处理一个从不产生的值 |
| 树版本记录失败是否阻断推送 | **已定（按建议）**：不阻断。版本「不是计算前提」（`_record_tree_version` docstring），失败已随推送运行记录 warnings 落库可查（review §0.5 第 3 条） |
| 企业代码更正 / 主体变更的节点身份迁移 | **已定（按建议）**：本 spec 只做「有引用即拒绝」（§2.6）；`old → new` 映射、级联改写下级与合并数据、更正与主体变更的区分另立 spec，待有真实更正需求时启动 |
| 同文件其余只校登录的向导端点 | 登记：列表 / 详情 / 模板推荐 / 向导读取与校验 / 可选下级列表 / 新建 / 批量删除（后者服务内已鉴权）；只读类是否收紧另立 spec |
| 读取侧 `strip()` 收敛 | 不做：存储值已规范化，收敛只增加改动面 |

## 7. 行数预算

| 文件 | 现值 | 预计 | 上限 |
| --- | --- | --- | --- |
| `audit_platform_schemas.py` | 1125 | +8 | 1142（白名单 1088 +5%），只放一行 validator 调用 |
| `batch_project_workbook.py` | 558 | +40 | 800 |
| `group_links.py` | 582 | +12 | 800 |
| `project_wizard_service.py` | 623 | +25 | 800 |
| `routers/project_wizard.py` | 741 | +8 | 800 |
| `routers/consol_worksheet.py` | 420 | +9 | 800 |
| `uscc_validator.py` | 51 | +20 | 800 |
| `ConsolidationHub.vue` | 835 | +12 | 1500 |
| `BasicInfoStep.vue` | 748 | +10 | 1500 |
| `consol_group_tree.py` | 791 | +5 | 800（超出即按 §4 拆文件） |
| `company_code_change_guard.py`（新） | — | ~90 | 800 |
| `ConsolidationIndex.vue` | HEAD 2513（工作区 2545，含他会话未提交改动） | +10 | 2638；与 `consol-status-semantics-closure` 合计复核，实施时在候选树上改 |
| `ConsolPushPanel.vue` / `ConsolTrialBalanceTab.vue` | 173 / 481 | +3 / +3 | 1500 |
| `stores/wizard.ts` / `ProjectWizard.vue` | 359 / 252 | +12 / +15 | 1500 |
| `ConsolTreeConflictDialog.vue` / `consolTreeConflicts.ts`（新） | — | ~80 / ~60 | 1500 |
