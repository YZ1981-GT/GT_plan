# 设计文档：公式管理平台缺陷闭环（formula-manager-closure）

> 关联需求：#[[file:.kiro/specs/formula-manager-closure/requirements.md]]
> 唯一权威输入：`docs/proposals/formula-management-platform-audit-2026-10-17.md`（全面审计报告，HEAD `84def65b`，复核更正绑定 HEAD `e5ee550f`）。
> 类型：bugfix + 接线收敛 + 安全加固 + 可观测性闭合 + 诊断。**本 spec 本轮只产出三件套文档，不实施任何生产代码；本 design 不写生产代码补丁，只写设计决策与现状核实。**
> 本轮为第三次修订轮：第一轮已修复评审 MEDIUM-1/2/3 + NIT-1/2/3/4（落点见 §13）；第二轮修复 1 MEDIUM + 2 NIT（落点见 §13.1）；本轮对照 `.agents/tasks/GT_plan-spec-formula-manager-closure-2026-10-17/design-review.{json,md}`（1 MEDIUM + 2 NIT，核心为 `stable_sheet_key` 迁移编号 V163/R163 归属更正 + 稳定键单一真源引用）逐条修复，落点见 §13.2。

## 0. 锚点绑定声明（务必先读）

**本 spec 的所有「现状锚点 / 现状 grep 确认」均绑定 commit `4934142a1c221afb785cdfcddee8aaaba7fb7527`**（取自 `.agents/tasks/GT_plan-spec-formula-manager-closure-2026-10-17/head_sha.txt`，与工作树 `d:\GT_plan\.worktrees\fm-closure-spec` 实测 `git rev-parse HEAD` 一致）。§1 的每条实测结果都是在该 commit 的工作树上现场 grep/读码得出。

**铁律（坐标漂移不报错、只让人少做）**：行号会漂、符号可能被改名、文件可能被移动。本文全程用「文件路径 : 符号名 / 端点字面量 / 常量名」定位，**不写死行号**。**实施前（届时 HEAD 必然已前移）必须重做一次 §1 的每条现状 grep 确认**，把「确认成立 / 已变化 / 需调整」重新跑一遍，再据当时真实坐标动手。坐标漂移不会抛异常，只会静默把补丁打到错的地方——这是本仓反复踩过的坑。

**仓库布局提醒（实测）**：本仓前端在 `audit-platform/frontend/src/...`，而**后端在仓库根下的 `backend/...`（不在 `audit-platform/backend` 下）**。本文所有后端路径均以 `backend/app/...` 书写。

## 1. 现状 grep 确认（HEAD `4934142a` 工作树实测）

> 方法：在 `d:\GT_plan\.worktrees\fm-closure-spec` 工作树上用 PowerShell `Select-String` / `git grep` + 读码现场核实。读中文输出先 `chcp 65001`；校验文件内容时用工具读取而非信任 PowerShell 行数显示。下表「实测结论」是本 commit 的真实状态，不是照抄报告。

| # | 锚点（文件 : 符号/端点） | 报告声称 | 本 commit 实测结论 |
|---|---|---|---|
| 1 | `audit-platform/frontend/src/components/formula/FormulaManagerDialog.vue : matchSheetCode` | 模糊包含匹配致当前 sheet 串页 | **确认成立**。函数体正是 `if (!a||!b) return false; return a === b || a.includes(b) || b.includes(a)`（`a/b` 经 `normalizeSheetToken` 归一）。`includes` 子串匹配使 `E1-1` 命中 `E1-10/14/15`、`D2-1` 命中 `D2-10/12`。 |
| 2 | `FormulaManagerDialog.vue : onFormulaEditSave` 的「已有行——更新到后端」分支 | 工作底稿保存误入 report-config | **确认成立（按 e5ee550f 口径收窄）**。该分支为 `if (row.id) { await api.put(P_rc.detail(row.id), {...}) }`，**无 kind 校验**；`tb_detail` 节点在更早处 `persistTbDetailFormulas()` 分流；新增行仅 `activeReportType` 非空才走 `P_rc.list` POST。故缺陷精确表述为「**任何有 id 的非报表、非 tb_detail 行保存时无 kind 校验即发 report-config detail**」。*（报告 84def65b 原述「工作底稿保存统一写 report_config」，e5ee550f 已收窄为上述表述，本实测采 e5ee550f 口径。）* |
| 2b | 同上 `onFormulaEditSave` 写入字段 | 前端把契约字段 `category/description` 误读为 `formula_category/formula_description` | **确认成立**。`onFormulaEditSave` 把保存值写进 `row.formula_category = data.category` / `row.formula_description = data.description`，全组件（表格列 `prop="formula_description"`、分组、过滤）均用 `formula_category/formula_description`。与 surfaced 只读、kind 分派**正交**，须作独立整改点（见 §5 步骤 1）。 |
| 3 | `backend/app/routers/wp_formula.py : _build_surfaced_formulas` | surfaced/Tier B 逐条 `readonly:true` | **确认成立**。`E1-surfaced-tb-check` / `E1-surfaced-adj-{i}` / `E1-surfaced-{sheet}-{i}` / `E1-surfaced-leaf-{code}` / F2 `{base}-surfaced-{sheet}-{i}` 全部硬标 `"readonly": True`。后端语义已是只读；缺陷在**前端把只读投影渲染成可编辑**。 |
| 4 | `backend/app/routers/wp_formula.py : list_formulas / save_formula / delete_formula` | 鉴权仅 `get_current_user` | **确认成立（IDOR 静态高危）**。三端点均 `Depends(get_current_user)`，路径只有 `{wp_id}`，无项目级反查、无 `require_project_access`。写端点 `save_formula` 同样仅登录门控。 |
| 5 | `audit-platform/frontend/src/shell/formula/openFormulaManagerCommand.ts : createOpenFormulaManagerCommand` | 生产零调用（仅测试引用） | **确认成立**。全仓引用仅 `shell/formula/openFormulaManagerCommand.ts`（定义）、`shell/formula/index.ts`（re-export）、`shell/formula/__tests__/openFormulaManagerCommand.spec.ts` + `fShellConformance.spec.ts`（测试）。无任何生产组件 import。 |
| 6 | `FormulaManagerDialog.vue : loadAcnrTree / buildWpDomainTree / acnrDrivenTree` | 左栏调全局 ACNR 树，不调当前 sheet anchors | **确认成立**。左栏标题「数据源」，`loadAcnrTree()` 调 `useAcnr().listSheets()` 建 TB/report/note/wp/aux/合并/表间审核/数据质量**五域全局树**（`acnrDrivenTree`）；无任何对「当前 sheet 的 listCells/anchors」的调用。 |
| 7 | `backend/app/routers/report_config.py` CRUD | report_config 端点仅 `get_current_user`，全局模板无项目门控 | **确认成立**。`GET ""` / `GET /{config_id}` / `POST /clone` / `PUT /{config_id}` / `POST ""` / `DELETE /{config_id}` / `POST /drill-down` / `POST /execute-formula` / `POST /execute-formulas-batch` 全 `Depends(get_current_user)`；仅 `POST /fill-formulas` 为 `require_role(["admin"])`。 |
| 8 | `backend/app/routers/report_config.py : GET /{config_id}`（`config_id: UUID`） | `/api/report-config/types` 无真实路由，被 UUID 路由捕获为 422 | **确认成立**。无 `/types` 路由；`/types` 命中 `GET /{config_id}` 的 UUID 解析失败 → 422。 |
| 9 | `backend/app/routers/report_config.py : GET /tb-detail-formulas/{project_id} / PUT /tb-detail-formulas/{project_id}` | 读端 IDOR（仅 `get_current_user`）、写端仅角色门控 | **确认成立**。GET 为 `Depends(get_current_user)`（路径有 `{project_id}` 但未校验归属 → IDOR）；PUT 为 `require_role(["admin","partner","signing_partner","manager"])`（角色门控≠项目门控）。 |
| 10 | `backend/app/routers/formula.py : execute_formula / register_custom_function / unregister_custom_function` | `/api/formula/execute` 等仅 `get_current_user`；自定义函数注册无 admin | **确认成立**。`POST /execute`、`POST /batch-execute`、注册/注销自定义函数全 `Depends(get_current_user)`，无 admin 门控。 |
| 11 | `backend/app/routers/formula_scope_query.py : GET /{project_id}/formulas` | `formula-scope/{project_id}` 仅 `get_current_user`（IDOR） | **确认成立**。prefix `/api/formula-scope`，端点 `Depends(get_current_user)`，`{project_id}` 未校验归属。 |
| 12 | `backend/app/routers/disclosure_notes.py : apply_formulas / list_note_formulas / upsert_note_formulas` | 附注三端点均挂 `require_project_access`（健全，不列入整改） | **确认成立**。`apply_formulas`（`require_project_access("edit")`）、`list_note_formulas`（`readonly`）、`upsert_note_formulas`（`edit`）。附注鉴权健全，**本 spec 不动附注鉴权**。 |
| 13 | `backend/app/routers/formula_logic_check.py : run_report_cross_check` | `GET report-cross-check` 的 `year` 必填，前端未传恒 422 | **确认成立**。签名 `run_report_cross_check(project_id, year: int, ...)`——`year` 无默认值（必填）；端点挂 `require_project_access("readonly")`。前端 GET 不带 `year` → 422。 |
| 14 | `backend/app/services/note_formula_generator.py : execute_note_formulas` vs `disclosure_notes.py : upsert_note_formulas` | 附注双存储：apply 读 `_formulas/_check_presets`，upsert 写 `_user_formulas`，互不可见 | **确认成立**。`execute_note_formulas` 读 `td.get("_formulas")`（空时按 `_check_presets` 生成），`upsert_note_formulas` 整体替换 `_user_formulas`；两键不相交，`execute` 永不消费 `_user_formulas`。 |
| 15 | `FormulaManagerDialog.vue` 对 `_user_formulas / list_note_formulas` 的引用 | 中央弹窗不读用户附注公式 | **确认成立**。全文件对 `_user_formulas` / `list_note_formulas` / `note-formulas` / `noteFormulas` **零命中**——中央弹窗附注节点只读模板预设。 |
| 16 | `audit-platform/frontend/src/components/workpaper/GtE1MonetaryFund.vue`、`.../d4/other/D4TabOther*.vue` | E1/D4-33~36 子入口仅发 `nodeKey`（node-only 旁路） | **确认成立**。`GtE1MonetaryFund.vue` 与 `D4TabOtherCheck/Contract/Cutoff/Margin.vue` 均含 `openFormulaManager`/`nodeKey` 旁路入口。 |
| 17 | `audit-platform/frontend/src/composables/useEditorToolbar.ts : 同步公式` | Univer 主路径工具栏只有「同步公式」，无 FormulaManager 入口 | **确认成立**。`useEditorToolbar.ts` 命中「同步公式」；无 `formula-manager-open` 入口。 |
| 18 | 全仓 `data-testid="formula-manager-open"` | 门禁要求的统一 testid 尚不存在 | **确认成立（需新增）**。全仓对 `formula-manager-open` **零命中**——该 testid 是本 spec 新增的统一入口标记，门禁据它枚举。 |
| 19 | `backend/migrations/V163__wp_formula_stable_key.sql`（前向）/ `R163__wp_formula_stable_key.sql`（回滚）: `WpFormula.stable_sheet_key` | 精确匹配拟用的 `stable_sheet_key` 列可空 | **需调整（重要）**。`stable_sheet_key` 列由 **V163**（`V163__wp_formula_stable_key.sql`）**新增**（`ALTER TABLE wp_formula ADD COLUMN IF NOT EXISTS stable_sheet_key VARCHAR(255)` + 回填 + `CREATE UNIQUE INDEX … WHERE stable_sheet_key IS NOT NULL`），列可空（`nullable=True`，`workpaper_models.py:WpFormula.stable_sheet_key` 实测 `Mapped[str \| None]`）；**R163 是配对回滚脚本**（`DROP COLUMN IF EXISTS stable_sheet_key …`），**不**是新增该列的迁移。V163 回填逻辑注明「与 `app.services.formula_management.stable_key` 对齐」。故 §5 步骤 1 的精确等值匹配**必须 fail-closed**：缺结构化身份的行排除，不得退回 `includes`。*（第一/二轮设计曾把新增迁移错标为 R163、头部误列 V052，第三轮评审 MEDIUM-1 据 V163/R163 实测更正；实质结论——列可空、须 fail-closed——不受影响。）* |
| 20 | `backend/app/data/wp_code_overrides.json` | 10 个 classification 404 的归类须查该表 | **确认成立（表存在）**。`wp_code_overrides.json` 位于 `backend/app/data/`，是 wp_code→componentType 的精确映射真源，可据其有无映射判「数据漂移 / 口径外」（见 §5 步骤 2 的 404 归类）。 |

**小结**：20 条锚点全部现场核实——18 条「确认成立」，1 条（#2）按 e5ee550f 口径收窄后成立并标注口径演进，1 条（#19）「需调整」（精确匹配须 fail-closed）。其中 #4/#7/#9/#10/#11 共同坐实 FM-P0-05 的「静态高危」判断；#12 坐实附注鉴权健全、不纳入整改。所有后端端点路径与前端布局已按实测仓库结构（后端在 `backend/`）校正。

## 2. 架构概览

「公式管理平台」在当前代码里不是一个单体服务，而是一组分层零件：

- **前端中央弹窗** `FormulaManagerDialog.vue`：左栏「数据源」（现为全局 ACNR 五域树）、右栏「当前页公式」（现为模糊 `includes` 聚合）、编辑保存（现按 `row.id` 直发 report-config detail）。入口分散——公共 toolbar 按钮、E1/D4 的 node-only 旁路、A1/Univer 无入口；已设计好的统一命令 `createOpenFormulaManagerCommand` 生产零调用。
- **前端执行入口** 工作底稿页内的函数按钮（NOTE/REPORT/ROW/AUX/PREV/ADJ 等）与 Univer「同步公式」。
- **后端公式源（四类权威边界）**：① `wp_formula`（用户自建/编辑的工作底稿正式公式，表 `WpFormula`，CRUD 在 `wp_formula.py`）；② surfaced 只读投影（`_build_surfaced_formulas` + `wp_surfaced_formulas.py` 家族聚合，逐条 `readonly:true`）；③ D/F extraction（Tier A/B，灰度）；④ 附注 `disclosure_notes.table_data`（`_formulas/_check_presets` 模板预设 + `_user_formulas` 用户集，双存储）；⑤ 报表 `report_config`（全局模板表，无 `project_id`，按 4 个 `applicable_standard` 区分）。
- **后端执行器**：`formula.py`（`/api/formula/execute` 通用求值）、`formula_runtime/adapters/*`（report/note 等执行适配，report 路径对 PREV/AUX 的支持受限）、`note_formula_generator.py:execute_note_formulas`（附注）、`report_config.py:execute-formulas-batch`（报表批量）、`formula_logic_check.py`（表间审核/逻辑校对）。
- **传播与可观测性**：ACNR 地址目录、stale 静态依赖图、`formula_runtime_outbox`、`formula_push_run/state`、`cross_check_results`、审计哈希链（`append_audit_log`）、合并链 `consol_report_values/consol_note_data/consol_push_run`。

**本 spec 的目标不是造新内核**，而是把这些零件收敛成一个可宣称「打通」的产品闭环：每页统一入口 → 当前页精确地址（左）+ 当前页权威公式（右）→ 可验证执行/校对 → 安全保存/传播，并补齐一道会随分母增长自动变红的全量门禁。对 count=0 的链路（附注运行、报表运行、合并三类）一律「先最小数据运行诊断，再决定是否改代码」，不预设断链。

## 3. 真实端到端数据流（现状 + 目标）

下表逐条列出「当前页公式管理」六要素在各模块的**现状**与**目标**；「本轮动作」列明确每条是「改代码 / 仅诊断 / 条件项不实施」。

| 要素 / 模块 | 现状（HEAD `4934142a` 实测） | 目标 | 本轮动作 |
|---|---|---|---|
| 统一入口 | 公共按钮 + E1/D4 node-only 旁路 + A1/Univer 无入口；`createOpenFormulaManagerCommand` 零调用 | 每页一个 `data-testid=formula-manager-open`，只提交 `CanonicalWorkpaperLocation` | 改代码（§5 步骤 2） |
| 右栏（当前页公式） | `matchSheetCode` 模糊 `includes` → 串页 | 按 `stable_sheet_key` 精确等值，缺身份 fail-closed 排除 | 改代码（§5 步骤 1、3） |
| 右栏字段读写 | 误读 `formula_category/formula_description` | 统一读写契约字段 `category/description` | 改代码（§5 步骤 1，独立改动点） |
| surfaced/extraction | 后端 `readonly:true`，前端渲染成可编辑 + 包装「自定义/健康度100%」 | 前端强制只读、去伪装 | 改代码（§5 步骤 1） |
| 工作底稿保存 | 有 id 的非报表行无 kind 校验即发 `P_rc.detail` | 按 kind 分派；wp 行走 `PUT /api/workpapers/{wp_id}/formulas`（`wpFormula.upsert`） | 改代码（§5 步骤 1） |
| 左栏（当前页地址） | 调 `useAcnr().listSheets()` 建全局五域树 | 调当前 sheet anchors（`GET addresses?project_id&wp_id&sheet_uid`），只显精确当前 sheet；另设显式「全局浏览」按钮 | 改代码（§5 步骤 3） |
| 附注公式 | `execute` 读 `_formulas`，`upsert` 写 `_user_formulas`，互不可见；中央弹窗不读用户集 | 二选一收敛（见 ADR-FMC-04）；中央弹窗附注节点读 `list_note_formulas` | 改代码（§5 步骤 4） |
| 附注鉴权 | 三端点已挂 `require_project_access` | 保持不变 | 不动（§1 #12） |
| 报表链 | `report_config`→执行→`financial_report`；6 项目各 82 行是同一模板 6 份克隆（6×82=492），非 6 份独立证据 | 口径按 distinct 模板/标准计（≈82），不按项目数夸大；写操作补项目+admin 门控 | 改代码（鉴权）+ 口径澄清（§5 步骤 4、5） |
| report 路径函数支持 | PREV/AUX 被置 0（静默）；UI 却提供这些按钮 | 维护按执行器的函数支持矩阵，不支持者 UI 显式禁用/标注，禁静默 0 | 改代码（§5 步骤 4） |
| 表间审核 | GET 缺 `year` 恒 422→退静态示例；按「规则列表」误解析执行结果；规则只改内存；树父/叶 key 与规则 map key 不一致 | 带 `year`；按执行结果解析；规则落库；空结果显式；树 key 与规则 map key 同源 | 改代码（§5 步骤 6） |
| report-config/types | `/types` 被 UUID 路由捕获 422 | 新增真实 `/types` 路由或前端改走正确端点 | 改代码（§5 步骤 6） |
| 鉴权（wp/report/execute/scope/tb-detail/custom-fn） | 仅 `get_current_user` 或仅角色门控（IDOR 静态高危） | 对象 id 先反查 project 再 `require_project_access`；body/query 的 project_id 同样校验；全局模板/自定义函数写限 admin；wp CRUD 写审计哈希链 | 先 TestClient 坐实，再改代码（§5 步骤 5） |
| 缓存 / 年份 / 单行 stale | `noteTreeLoaded/reportTypesLoaded/crossCheckLoaded` 不按项目隔离；保存用系统当前年；单行保存不触发统一 stale | 缓存按 project key；保存用 `props.year`；单行保存触发与「保存全部」相同的 stale 传播 | 改代码（§5 步骤 6） |
| tb_detail 传播 | `tb_detail_formulas` 键的项目数=0，无传播需求 | `FORMULA_CONFIG_CHANGED` 列为**条件项不实施**，仅诊断发现需要时开（见 NIT-3 响应） | 条件项不实施（§5 步骤 5） |
| 正式运行数据 | 29 条 wp_formula 全属已软删项目；活跃项目=0；push/cross-check/outbox/consol 运行表全 0 | 一次最小数据运行逐值对拍坐实 | 诊断（§6） |
| 合并三类 | 1 个 consolidated 项目，`consol_push_run=0`；count=0 双重可能 | 先最小数据运行诊断，再决定是否改代码 | 诊断后决策（§6、ADR-FMC-09） |

## 4. 关键决策（ADR 风格）

### ADR-FMC-01 · 右栏匹配从模糊 `includes` 改为结构化精确等值 + fail-closed
- **背景**：`matchSheetCode` 用 `a.includes(b)||b.includes(a)`，`E1-1` 串入 `E1-10/14/15`、`D2-1` 串入 `D2-10/12`（§1 #1 实测）。
- **选项**：(A) 收紧为等值 `a===b`；(B) 用结构化 `stable_sheet_key` 精确等值；(C) 正则边界匹配。
- **裁定**：选 **B**。`WpFormula.stable_sheet_key` 列已存在（由 **V163** 新增、`R163` 为其回滚，§1 #19），是唯一不随 sheet 改名漂移的结构化身份；右栏聚合改用它做精确等值。因该列**可空**，匹配必须 **fail-closed**：缺可解析结构化身份的行直接排除，**不得**退回 `includes`（否则精确化形同虚设）。不选 A（纯字符串等值仍受 sheet 名别名/大小写影响）、不选 C（正则边界仍是字符串启发式，不如结构键稳）。
- **稳定键单一真源（NIT-1 响应）**：V163 回填、`wp_formula_service` 写入、PBT 三处共用仓库既有单一真源 `backend/app/services/formula_management/stable_key.py`（`derive_stable_key` / `normalize_sheet_key`，该模块 docstring 明确「供 service 写入、迁移回填、PBT 三处共用，不各写一份」）。本改动的任何 sheet 名归一（含 §5 步骤 1 的历史行回填、以及前端若需本地归一）**一律复用该真源**，**禁另写一套规范化**；前端本地归一须与该真源口径对齐并由单测钉死，否则「同一 sheet 在前端归一后与库里 `stable_sheet_key` 对不上」会让精确匹配更隐蔽地串/漏。
- **后果**：右栏不再串页；代价是「无 `stable_sheet_key` 的历史行」会在精确化后从右栏消失——这是**可接受的 fail-closed**，并由 §5 步骤 1 的「优先一次性回填脚本（复用 stable_key 真源）补齐、回填后仍无结构身份的 `needs_review` 行才 fail-closed 排除」补偿、门禁断言⑤守护。

### ADR-FMC-02 · surfaced/extraction 前端强制只读 + 工作底稿保存按 kind 分派；字段名修正为独立改动点
- **背景**：后端 surfaced/Tier B 已 `readonly:true`（§1 #3），但前端把它渲染成可编辑并包装「自定义/健康度100%」；且任何有 id 的非报表行保存无 kind 校验即发 `P_rc.detail`（§1 #2）。另外前端读写用 `formula_category/formula_description` 而非契约字段 `category/description`（§1 #2b）。
- **选项**：(A) 后端再加校验拒收 surfaced 保存；(B) 前端按 `readonly` 标志禁编辑 + 保存前按 kind 分派目标端点。
- **裁定**：选 **B 为主、A 为兜底**。前端据后端 `readonly` 标志渲染只读（去「编辑」按钮、去「自定义/健康度」伪装）；保存链先判行的 kind（wp / report / tb_detail / surfaced-只读），wp 行走 `PUT /api/workpapers/{wp_id}/formulas`，surfaced/extraction 不可保存，report 行才走 report-config。后端 `save_formula` 保留对非 wp kind 的拒收作为纵深防御。
- **后果**：说明元数据不再被当权威公式编辑/误写报表模板。**字段名修正（`formula_category/formula_description` → `category/description`）与 surfaced 只读、kind 分派正交，列为独立改动点**（见 §5 步骤 1 改动点 ③，MEDIUM-3 响应）：即便 kind 分派正确，字段名读错仍会使 category/description 显示与保存错位。

### ADR-FMC-03 · 统一入口：生产真正调用 `createOpenFormulaManagerCommand`，按钮只提交 `CanonicalWorkpaperLocation`
- **背景**：命令已设计好但零生产调用（§1 #5）；E1/D4 node-only 旁路丢实例/项目/sheet（§1 #16）；A1/Univer 无入口（§1 #17）；统一 testid 不存在（§1 #18）。
- **选项**：(A) 保留各入口各自组装 payload；(B) 全部入口收敛到 `createOpenFormulaManagerCommand`，只提交一个 `CanonicalWorkpaperLocation`。
- **裁定**：选 **B**。每个可渲染页恰有一个 `data-testid=formula-manager-open` 的 primary outlet，点击调用统一命令提交完整 location（projectId/wpId/wpCode/sheetUid…）。删除 E1 页内第二按钮与 D4-33~36 的 node-only 旁路（或改为提交完整 location）；A1（`a1-dashboard`）与 Univer 主路径补同一 outlet；`redirect-materiality`（B15）登记带 owner/reason/expires_at 的正式豁免。
- **后果**：任意入口打开的都是本页公式管理，scope 标签与面包屑一致；不再出现底稿入口落 `report` scope、`/report-config/types` 或缺 year 的 422。门禁断言①②③守护。

### ADR-FMC-04 · 附注公式权威源二选一：选「apply 消费 `_user_formulas`」
- **背景**：双存储 `_formulas`（模板预设）与 `_user_formulas`（用户集）互不可见，`execute_note_formulas` 永不消费用户集（§1 #14），中央弹窗不读用户集（§1 #15），真库三键全 0。
- **选项**：(A) `execute_note_formulas` 同时消费 `_user_formulas`（用户公式真执行）；(B) 取消 `_user_formulas` 可编辑，统一回「模板预设 + 项目级覆盖」。
- **裁定**：选 **A**。附注本就提供「用户自定义公式编辑」入口（`upsert_note_formulas`），取消它（方案 B）是削功能、与用户诉求「保存的公式真的会执行」相悖。故让 `execute_note_formulas` 合并消费 `_formulas` ∪ `_user_formulas`（合并口径见下「后果」默认口径），并让中央弹窗附注节点改调 `list_note_formulas`（含用户集）。附注三端点鉴权健全，**不动**（ADR-FMC-07）。
- **后果**：用户保存的附注公式可被 apply 执行并回填；弹窗能看到自己的公式。代价是执行器需处理用户集与模板集的合并与拓扑排序——由 §5 步骤 4 覆盖、§6 最小数据运行坐实。**合并默认口径（NIT-1 响应，供 tasks 立断言）**：同一目标单元格键冲突时**用户集优先**（用户公式覆盖同键模板预设）；拓扑排序对合并去重后的集合**统一重算**（不是两套各自排序后拼接），避免用户公式与模板公式对同一单元格产生两次回填或排序抖动。该口径由 §9 可测项「键冲突样本：用户公式覆盖同键模板公式」守护；若 §6.2 最小数据运行对拍出更合理的口径，可据运行结果在 tasks 阶段调整并记录。

### ADR-FMC-05 · 左栏改为当前页地址 + 显式「全局浏览」按钮，缺身份 fail-closed
- **背景**：左栏调全局 ACNR 五域树，不调当前 sheet anchors（§1 #6）。
- **裁定**：左栏默认调当前 sheet 的 anchors（`GET addresses?project_id&wp_id&sheet_uid` 或等价 listCells），只显属于精确当前 sheet 的 `addr_id`；「全局浏览」作为独立显式按钮，**不**作为缺上下文时的默认回退。当前页 location identity 缺失时 fail-closed（显式告警 + 空集），不退全局树。左右栏每行带同一 location identity（projectId/wpId/sheetUid）。
- **后果**：左右栏始终对应同一当前页。门禁断言④守护「左侧 addr_id 全属精确当前 sheet」。

### ADR-FMC-06 · FM-P0-05 定级为「静态高危·待 TestClient 坐实」，先坐实再加固
- **背景**：wp_formula/report_config/execute/formula-scope/tb_detail 等仅 `get_current_user` 或仅角色门控（§1 #4/#7/#9/#10/#11 实测），平台有 `t_accounts`/`formula_audit_log` 同型 IDOR 先例；但本轮**未执行任何跨项目越权探测**。
- **裁定**：P0 定级是**静态读码 + 先例的高置信推断，非已复现事故**。整改前**先跑一条 TestClient 跨项目越权用例**坐实：以项目 A 凭据对项目 B 的 wp_formula 读/写、report_config 更新、`/api/formula/execute`、`formula-scope/{project_id}`、`tb_detail` 读/写发请求，断言全部 403 且 0 副作用。坐实后再据结果加固（对象 id 先反查 project 再 `require_project_access`；body/query 的 project_id 同样校验；全局模板/自定义函数写限 admin；wp CRUD 写 `append_audit_log`）。若坐实用例意外显示某端点已安全，则据运行时结果更新定级，不继续按「已越权」处置。
- **后果**：避免把推断当事故；加固范围由坐实结果界定。门禁断言⑦依赖本整改落地（见 ADR-FMC-08 的 pending 处理）。

### ADR-FMC-07 · 附注鉴权不纳入整改
- **背景**：复核发现（e5ee550f）附注三端点均挂 `require_project_access`（§1 #12 坐实）。
- **裁定**：附注层项目隔离与 `stamp_section_edit` 留痕健全，**不在**本 spec 鉴权整改范围内；§5 步骤 5 的鉴权加固不触及附注端点；门禁/测试不把附注端点当待修鉴权项。
- **后果**：避免误改健全代码、避免回归。

### ADR-FMC-08 · 全量门禁 `formula-manager-all-accessible-pages.spec.ts`：运行时权威分母 + 幂等输出 + 四变异
- **背景**：现有 toolbar E2E 允许 `triggerCount>=0`、只数关闭态 dialog≤1，从未点按钮核左右栏；报告要求幂等输出防永红（memory 铁律㉗）。
- **裁定**：门禁先通过项目 API 枚举全部可访问 `working_paper`，逐张 GET render-config 展开「每真实 sheet + whole_workbook + redirect」形成运行时权威分母（每项记 `project_id/wp_id/wp_code/sheet_uid/sheet_code/host/componentType`）；每非 redirect 项跑 8 条断言；redirect/不可渲染项用带 owner/reason/expires_at 可伪证豁免登记；输出幂等（分母 JSON 内容不变不改时间戳、排序稳定、无机器名/绝对路径、`--check` 不用 `--write`+diff、子进程 `PYTHONIOENCODING=utf-8`+`errors='replace'`+断言 stdout 内容）；四变异（注入 `E1-10`、删按钮、去 `wp_id`、save 改回 report_config）各命中对应断言。**断言⑦（权限分层）在 ADR-FMC-06 鉴权整改合入前标 skip/pending、不计入分母红**（与幂等防永红一致，见 NIT-2 响应）。
- **后果**：分母任何新增或任一契约回退自动变红，且门禁本身不会恒红。详见 §7。

### ADR-FMC-09 · 合并三类（report/note/wp）先最小数据运行诊断，再决定是否改代码
- **背景**：1 个 consolidated 项目，`consol_push_run=0`、`consol_note_formula=0`、`consol_note_data=2`；count=0 有「已接线未使用（成本低）」与「已断裂（成本高）」双重可能。
- **裁定**：**不预设坏链、不重写合并链**。在未删除的 consolidated 项目造一套隔离合并公式 + 触发推送/重算，逐值对拍 `consol_report_values`/`consol_note_data`、观察 `consol_push_run` 是否落库；**据这次运行结果再决定**：落库且对拍一致 → 判「已打通（仅数据阻塞）」不改代码；不落库或不一致 → 判「已断裂」，据失败点定位最小改动，不预设需重写整条链。
- **后果**：需求 17/18/19 的 Out-of-Scope「禁写重写合并链」得到设计层保证；诊断结果是是否改代码的前置分支。详见 §6。

## 5. 整改顺序（按报告第十节七步组织）

> 七步严格按报告第十节的最小闭环顺序。每步列「目标 / 现状锚点 / 覆盖需求」。本节只写设计与改动点定位，不写代码补丁。

### 步骤 1 · P0 止错（串页 / surfaced 伪装 / 错保存域 / 字段误读）

覆盖需求 1、2、13（wp 收敛）。三个并列改动点 + 一个独立改动点：

- **改动点 ①（串页，ADR-FMC-01）**：`FormulaManagerDialog.vue : matchSheetCode` 及其右栏聚合调用处，改为用 `stable_sheet_key`/`sheet_uid` 结构化精确等值；缺身份 fail-closed 排除，禁退回 `includes`。配套：后端 `wp_formula.py` 的公式投影须带 `stable_sheet_key`（由 **V163** 新增的列，`R163` 为其回滚；§1 #19）。
  - **历史缺值行的处置顺序（明确取舍，NIT-2 响应）**：**优先**由一次性回填脚本补齐 `stable_sheet_key`——回填与任何 sheet 名归一**一律复用单一真源** `backend/app/services/formula_management/stable_key.py` 的 `derive_stable_key` / `normalize_sheet_key`（V163 回填 / 服务写入同源），**禁另写一套规范化**；回填后仍无法解析 A1 / sheet 结构身份的 `needs_review` 行，**才** fail-closed 排除，并在右栏明确标注「无结构身份已排除 N 行」。即「回填为主、标注为过渡」，与 ADR-FMC-01「后果」口径一致，**不**是「回填 或 标注」二选一。
  - **前端本地归一约束**：若前端需本地归一 sheet 名，须与 `stable_key` 真源口径对齐，并由 §9 单测「前端归一结果与 stable_key 真源对同一 sheet 名产出一致」钉死。
- **改动点 ②（surfaced 只读 + kind 分派，ADR-FMC-02）**：前端据后端 `readonly` 标志把 surfaced/extraction 渲染为只读（去「编辑」按钮、去「自定义/健康度100%」伪装）；`onFormulaEditSave` 保存链先按行 kind 分派——wp 行走 `wpFormula.upsert`（`PUT /api/workpapers/{wp_id}/formulas`），surfaced/extraction 不可保存，仅 report 行走 `P_rc.detail`；后端 `save_formula` 对非 wp kind 拒收作纵深防御。
- **改动点 ③（字段名修正，独立，ADR-FMC-02 后果，MEDIUM-3 响应）**：`FormulaManagerDialog.vue` 读/写工作底稿公式行的字段统一为后端契约字段 `category/description`，消除 `formula_category/formula_description` 误读。此点**独立于 ②**：即便 kind 分派正确，字段名读错仍致 category/description 显示与保存错位。门禁/单测须断言「保存请求体字段 = 契约字段 `category/description`」「右栏渲染读的是契约字段」。
- **锚点**：`matchSheetCode`、`onFormulaEditSave`、`_build_surfaced_formulas`、`WpFormula.stable_sheet_key`（§1 #1/#2/#2b/#3/#19）。

### 步骤 2 · 统一入口（ADR-FMC-03） + 10 个 classification 404 一次性归类（MEDIUM-1 响应）

覆盖需求 3、9。

- **统一入口**：生产真正调用 `createOpenFormulaManagerCommand`；每个可渲染页恰一个 `data-testid=formula-manager-open`，只提交 `CanonicalWorkpaperLocation`；删除 E1 页内第二按钮与 D4-33~36 node-only 旁路（或改为提交完整 location）；A1（`a1-dashboard`）与 Univer 主路径补同一 outlet；`redirect-materiality`（B15）登记带 owner/reason/expires_at 的正式豁免。枚举 220 个声明 componentType，每项恰有「当前页入口覆盖」或「带期限正式豁免」，无未知未覆盖项。
- **10 个 classification 404 归类（独立子任务，需求 9.2~9.4）**：对医疗器械真实项目运行时 classification API 返 404 的 10 个 `wp_code`，**逐个查 `backend/app/data/wp_code_overrides.json`**：
  - **命中映射** → 判「**数据漂移**」，记录应补的 override 条目或 classification 行（修复动作落 override / 补 classification 行），该 wp_code 仍计入按钮覆盖分母。
  - **未命中映射** → 判「**口径外**（本就无映射的未建模底稿）」，从 §7.1 门禁按钮覆盖分母中**显式剔除**并登记理由。
  - 归类结果并入 §7.3 门禁分母豁免登记（带 owner/reason/expires_at）；归类完成后报告第四节「无法判定」子类解除，每个 404 wp_code 有明确归属。
  - **实施期重算（第四轮评审 NIT-2 响应）**：10 个 classification 404 的 `wp_code` 清单及其 `wp_code_overrides.json` 命中与否，**会随 HEAD 前移与真实项目数据变化**，须在实施期对**当时真实项目**重跑 classification API + 重查 `wp_code_overrides.json` 现算得出，**不沿用本设计撰写期快照**（与 §0/§11 漂移纪律一致）；据此得出的分母剔除项每条带可被实际情况验证的理由字段，禁写死清单。
- **锚点**：`createOpenFormulaManagerCommand`（§1 #5）、E1/D4 旁路（§1 #16）、Univer `同步公式`（§1 #17）、`formula-manager-open`（§1 #18）、`wp_code_overrides.json`（§1 #20）。

### 步骤 3 · 左右栏契约收敛（ADR-FMC-01、ADR-FMC-05）

覆盖需求 6。后端收敛 `GET formulas?project_id&wp_id&sheet_uid`（右栏，服务端精确过滤）与 `GET addresses?project_id&wp_id&sheet_uid`（左栏 anchors，服务端精确过滤）；左栏只显精确当前 sheet 的 anchors，另设显式「全局浏览」按钮；左右栏每行带同一 location identity；缺 identity fail-closed（空集 + 告警），不退全局树。锚点：`loadAcnrTree/buildWpDomainTree/acnrDrivenTree`（§1 #6）。

### 步骤 4 · 收敛权威源与执行语义

覆盖需求 4、8、14（note 收敛）、15（报表口径）。

- **wp 正式公式 = `wp_formula`**；surfaced/extraction = 只读投影/文档化目录（步骤 1 已定）。
- **附注二选一（ADR-FMC-04）**：`execute_note_formulas` 合并消费 `_formulas` ∪ `_user_formulas`；中央弹窗附注节点改调 `list_note_formulas`（含用户集）。锚点：`execute_note_formulas`/`upsert_note_formulas`（§1 #14）、弹窗零引用（§1 #15）。
- **report = `report_config`**；`formula_push` 明确文档化为**自动物化层**（不是权威定义源）。报表链「生产实证」口径按 distinct 模板/标准计（≈82 条模板公式），**不按项目数（6）夸大**为 6 倍（6×82=492 是同一模板 6 份克隆）。
- **函数支持矩阵（需求 8，禁静默 0）**：为每个公式函数 NOTE/REPORT/ROW/AUX/PREV/ADJ 维护一张「函数 × 执行器 → 支持/不支持」矩阵（覆盖 wp evaluator 真支持 TB/SUM_TB/WP、report 路径当前强制 PREV/AUX=0、note 执行器、中央 batch 的 ADJ 实时数据注入）。不支持者 UI 显式禁用/标注，**禁止点击后静默返回 0**；支持者运行须产生真实结果，不以空 ctx 回退为 0。

### 步骤 5 · 项目鉴权与原子性（ADR-FMC-06、ADR-FMC-07）

覆盖需求 5、15（报表鉴权）、16（tb-detail 鉴权）。

- **先坐实**：跑一条 TestClient 跨项目越权用例（见 §6），断言读/写/执行全 403 且 0 副作用。
- **再加固**：对象型端点（路径只有 `{wp_id}` 等对象 id）先最小反查 `project_id` 再 `require_project_access("edit"/"readonly")`；body/query 的 `project_id` 同样校验；全局模板（`report_config` list/get/clone/update/create/delete/execute-batch）与全局自定义函数（`formula.py` 注册/注销）写操作限 admin；`tb_detail` 读端补 `require_project_access`、写端在 `require_role` 之外叠加项目归属校验；批量保存单事务 + CAS；直接 `wp_formula` CRUD 写 `append_audit_log` 哈希审计链。
- **不动附注**（ADR-FMC-07）：附注三端点已合规，不列入。
- **tb_detail 传播条件项（NIT-3 响应）**：`FORMULA_CONFIG_CHANGED` 本轮 tb_detail 真库=0、无传播需求，**列为条件项不实施**，仅诊断发现需要时开。
- **锚点**：`list_formulas/save_formula/delete_formula`（§1 #4）、report_config CRUD（§1 #7）、`execute_formula`/自定义函数注册（§1 #10）、`formula-scope`（§1 #11）、`tb-detail-formulas` 读/写（§1 #9）。

### 步骤 6 · 执行/传播可观测性

覆盖需求 7（表间审核）、10（缓存/年份/单行 stale）、9（report-config/types）。

- **report-config/types**：`/types` 被 UUID 路由捕获 422（§1 #8）——新增真实 `/types` 路由或前端改走正确端点。
- **report-cross-check year（§1 #13）**：前端 GET 带 `year`，不再恒 422；前端按「执行结果」解析响应（非「规则列表」）；新增/编辑规则落库持久化（关闭再打开仍可见）；空结果显式呈现「无结果」（不以静态示例冒充）；**表间审核树的父/叶节点 key 与规则 map 的 key 用同一 key 生成，不一致视为契约缺陷**（需求 7.4，MEDIUM-2 响应）。
- **缓存/年份/单行 stale（需求 10）**：`report/note/cross-check` 缓存按 project key 隔离，切项目失效旧缓存；「保存全部」与单行保存用 `props.year`（项目年）；单行保存触发与「保存全部」相同的统一 stale 传播；ACNR GET abort 后重发不污染跨项目上下文。每次执行写 run/issue/hint/outbox/audit 且可查询；去掉「执行 0 条仍成功」。

### 步骤 7 · 真实 UAT（最小数据运行）

覆盖需求 11、17、18、19。见 §6。standalone 一套 + consolidated 一套最小数据运行，逐值对拍权威表并观察 run/state/outbox 落库——这是把所有「DB count=0」从「未证明」推进到「已打通（仅阻塞）/已断裂」的唯一手段。

### 步骤 8 · P2 治理收敛（第四轮评审 MEDIUM-1 响应）

覆盖需求 20（P2 治理组，报告第九节 P2-1~3；报告第十节七步不含 P2，故本步骤为七步之外的治理收尾，tasks 对应 Phase 可用 `*` 标记为治理项）。四条 AC 逐条给落点：

- **20.1 · ≥7 套 local formula dialog/drawer 收敛或明确分工**：枚举报告指出的至少 7 套局部公式弹窗/抽屉（E1/D4 等 node-only 旁路入口已在步骤 2 删除/改造；其余如确认汇总、D4 披露等局部规则说明），逐个登记「组件路径 + 当前权威源 + 去留决策（收敛进中央弹窗 / 保留但标注分工边界 / 废弃）」。收敛后与步骤 2 的统一入口口径一致：凡能收敛的走 `createOpenFormulaManagerCommand`，保留的须在登记表写明为何不收敛（权威源不同 / UX 专用）。**不预设全部收敛**——有正当分工的局部弹窗保留，但禁「按钮同名、能力/权威源不同」的隐性碎片化。
- **20.2 · 两条历史假红/脆化前端测试修正**：`FormulaManagerPageWiring`（一次性 reject 被新增 bindings GET 抢先消费，错误态已脆化）与 `formulaStatusPanelDisplay`（仍断言「HTML 面板不可达」这一已修复的旧缺口，变成历史假红）。各写修正方向=让测试反映**当前真实行为**（不是放宽断言蒙绿，也不是删测试）：前者稳定化竞态（按序消费或显式等待对应请求），后者更新期望为「HTML 面板已有入口按钮」。修正须配变异反证（注入对应真实缺陷仍能打红），避免改成恒绿。
- **20.3 · formula_push 套件 1164 warnings 收敛**：定位 `Connection._cancel was never awaited` 根因（异步连接取消未 await），给处置方向（在测试 fixture / 连接管理处补 await 或改用同步关闭）。验收=套件 warnings 显著下降且无新增失败；不以 `-W ignore` 掩盖。
- **20.4 · RTK 吞失败退出码修正**：RTK 外层包装在子命令失败时仍返回 exit 0，使「只看退出码」的门禁假绿。复用 §7.4③ 口径——门禁子进程断言 stdout/stderr 含预期内容（非仅看 returncode），并对 RTK 包装的命令显式校验内层退出码或输出标志。

> **P2 边界声明**：本步骤是治理收尾、非功能闭环主线；若某条 AC 在实施期评估 ROI 不足或须另立 spec（如 20.1 的大规模弹窗重构），按 tasks 的 `*` 可选项处置并在该任务显式记录「本轮仅登记 / 条件实施」的决策边界（与 ADR-FMC-09 的「先诊断后决策」同构，不默默丢弃正式需求）。

## 6. 诊断：坐实用例与最小数据运行（先诊断后决策）

本 spec 有两类必须先运行、再据结果决策的诊断，均**不预设结论**。

### 6.1 FM-P0-05 跨项目越权坐实（TestClient，ADR-FMC-06）

一条 TestClient 用例：取两个未删除项目 A、B；以属于 A 的凭据对 B 的下列资源分别发请求——`wp_formula` 读（`GET /api/workpapers/{B_wp_id}/formulas`）/写（`PUT .../formulas`、`POST .../formulas`）、`report_config` 更新（`PUT /api/report-config/{config_id}`）、`/api/formula/execute`、`formula-scope`（`GET /api/formula-scope/{B_project_id}/formulas`）、`tb_detail` 读（`GET /api/report-config/tb-detail-formulas/{B_project_id}`）/写（`PUT .../{B_project_id}`）。

- **预期（高置信推断）**：加固前多数返回 200（坐实 IDOR）；加固后全部 403 且 0 副作用。
- **若意外某端点加固前已 403**：据运行时结果更新该端点定级，不继续按「已越权」处置（需求 5.8）。
- 用例须用 `dependency_overrides` 内层 `get_current_user/get_db`（而非直接覆盖 `require_project_access` 工厂——工厂每次返回新函数对象，覆盖静默失效，memory 教训㉕①）；鉴权口径须穷举（避免漏判 `require_project_delegator`/`require_wp_edit_permission` 等别名）。

### 6.2 最小数据运行（standalone + consolidated，ADR-FMC-09）

**standalone 一套**（坐实需求 11、13 的运行/传播）：在未删除的 standalone 项目造一套隔离公式并保存 → 重开右栏与保存一致 → 执行使目标值改变、`last_computed_at` 更新 → `stale`/`formula_runtime_outbox`/audit 均带同一 `run_id`。以逐值对拍权威表为准，不看组件/mock。

**consolidated 一套（合并三类，先诊断后决策）**：在**未删除的 consolidated 项目**造一套隔离合并公式 + 触发推送/重算，一次运行覆盖 12.5/12.6/12.7：

| 子节 | 诊断动作 | 对拍表 | 观察落库 | 结果分支 |
|---|---|---|---|---|
| 12.5 合并报表 | 造合并报表公式 + 触发推送 | `consol_report_values` | `consol_push_run` | 落库且对拍一致→判「已打通（仅阻塞）」**不改代码**；不落库/不一致→判「已断裂」据失败点定位最小改动，**不预设重写** |
| 12.6 合并附注 | 造合并附注公式 + 执行 | `consol_note_data` | `consol_push_run` | 同上 |
| 12.7 合并底稿 | 合并底稿「公式」体现在差额表引擎中间节点，随 12.5/12.6 同一运行观察 | `consol_report_values`/`consol_note_data` | `consol_push_run` | 同上 |

**纪律**：三子节需求措辞禁写「重写/重建合并链」；诊断结果是是否改代码的前置分支；造数用幂等脚本、名称带可识别前缀、用完经项目回收站删除；诊断数据不污染真实项目。

## 7. 全量门禁 `formula-manager-all-accessible-pages.spec.ts`（ADR-FMC-08）

### 7.1 运行时权威分母

先通过项目 API 枚举全部可访问 `working_paper`，逐张 GET render-config，展开「每个真实 sheet + whole_workbook + redirect」，形成运行时权威分母；每项记录 `project_id/wp_id/wp_code/sheet_uid/sheet_code/host/componentType`。10 个 classification 404 中判「口径外」者从本分母显式剔除并登记理由（§5 步骤 2）。

### 7.2 八条断言（每个非 redirect 项）

- **① 唯一入口**：恰好一个 `[data-testid=formula-manager-open]`。
- **② 单弹窗**：点击只出现一个中心弹窗。
- **③ 完整 location**：抓包断言打开请求带完整 `CanonicalWorkpaperLocation`（projectId/wpId/wpCode/sheetUid）。
- **④ 左栏精确**：左侧返回的 `addr_id` 全属精确当前 sheet。
- **⑤ 右栏精确 + surfaced 只读 + 契约字段**（拆为三个可独立计红的子断言，第四轮评审 NIT-1 响应；§7.5 变异逐一映射到具体子项，避免整体绿掩盖某子项未真正断言，铁律㉖）：
  - **⑤a · 右栏精确**：右侧每条 `stable_sheet_key` 精确相等（反例 `E1-1` 不得混入 `E1-10/14/15`）。
  - **⑤b · surfaced 只读去伪装**：surfaced/extraction 行渲染为只读、无「编辑」按钮、无「自定义/健康度」伪装。
  - **⑤c · 保存契约字段 + 目标端点**：保存请求体字段为契约字段 `category/description`（需求 2.4），且目标端点按 kind 分派正确（wp 行发 `PUT /api/workpapers/{wp_id}/formulas`，非 report-config detail）。
- **⑥ 切换隔离**：切 sheet/项目后集合变化，且旧响应不能覆盖新项目结果。
- **⑦ 权限分层（pending 处理，NIT-2 响应）**：admin/auditor/readonly 分别验证 view/edit 权限。**本断言依赖 ADR-FMC-06 鉴权整改落地；在鉴权整改合入前标 skip/pending、不计入分母红**（与 §7.4 防永红一致）。**⑦转硬断言的前置 = ADR-FMC-06 列出的全部对象型端点（`wp_formula` 读/写、`report_config` CRUD、`/api/formula/execute`、`formula-scope`、以及 §16 的 `tb_detail` 读/写）均已加固并通过 §6.1 TestClient 坐实；任一端点未合入则整条⑦保持 pending、不做部分硬化**（避免在部分加固态下半绿半 skip、口径含糊）。
- **⑧ 零错误**：0 console error、0 当前请求 abort、0 4xx。

### 7.3 豁免登记

redirect / 不可渲染项（含 B15 `redirect-materiality`、判「口径外」的 404 wp_code）用带 `owner/reason/expires_at` 的可伪证豁免登记（不是只存理由文本的后门，须含可被实际情况验证的字段 + 「判据抽不到值」防空转断言）。

### 7.4 幂等输出（防永红，memory 铁律㉗）

- **①** 分母 JSON 内容不变则不改时间戳、排序稳定、不含机器名/绝对路径。
- **②** 沿用仓库既有 `--check` 约定（漂移 exit 2 并点名新增项），**不用 `--write` 后 `git diff`**（后者因时间戳每次必 diff → 门禁恒红 → 被忽略）。
- **③** 子进程捕获输出设 `PYTHONIOENCODING=utf-8` + `errors='replace'` 且**断言 stdout 含预期内容**（只看 returncode 的守卫在 Windows gbk 下必假绿；memory 教训㉗⑦）。

### 7.5 四变异必须命中

| 变异 | 应命中断言（精确到⑤子项，NIT-1 响应） |
|---|---|
| 注入 `E1-10`（串页） | **⑤a** 右栏精确（`stable_sheet_key` 不等） |
| 删除 `formula-manager-open` 按钮 | ① 唯一入口（数到 0） |
| 去掉 `wp_id`（丢 location） | ③ 完整 location |
| 把 save 改回写 `report_config` | **⑤c** 保存目标端点（应发 wp formulas 端点而非 report-config detail） |
| （补）surfaced 行加回「编辑」按钮 / 把 readonly 渲染成可编辑 | **⑤b** surfaced 只读去伪装 |

> ⑤ 拆分后三个子变异各命中 ⑤a/⑤b/⑤c 的不同子项，每个子项都有至少一个变异单独验证（含对应反向断言：未注入时不命中），不再出现「两个变异都映射⑤、整体绿掩盖某子项未断言」的风险。

每变异须配反向断言（未注入时不命中），避免单向变异把干净态判成缺陷（memory 铁律㉒）。

## 8. 错误处理与外部输入校验

| 操作 / 输入 | 失败条件 | 可恢复? | 调用方收到 | 日志层级 |
|---|---|---|---|---|
| 右栏精确匹配 | 行缺 `stable_sheet_key`（§1 #19） | 可恢复（fail-closed 排除） | 该行不出现在右栏；可选「无结构身份已排除 N 行」提示 | 前端 warn |
| 工作底稿保存 | 行 kind 非 wp 却走保存 | 可恢复 | 按 kind 分派到正确端点；surfaced/extraction 拒绝保存并提示只读 | 前端 warn |
| 跨项目越权（加固后） | project A 凭据访问 project B 对象 | 不可恢复（拒绝） | 403，0 副作用 | 后端 warn（审计链记一次拒绝） |
| 全局模板/自定义函数写 | 非 admin | 不可恢复 | 403 | 后端 warn |
| `report-cross-check` | 缺 `year`（§1 #13） | 可恢复（前端补 year 后重试） | 加固后前端必带 year；若仍缺 → 422（后端契约不变） | 前端 error |
| `report-config/types` | 旧前端请求 `/types`（§1 #8） | 可恢复 | 新增真实 `/types` 路由或前端改走正确端点；旧路径不再被 UUID 捕获为 422 | — |
| 执行 | 函数在当前执行器不支持 | 可恢复 | UI 显式禁用/标注「此处不支持」；禁静默返回 0 | 前端 info |
| 执行 | 0 条可执行 | 可恢复 | 显式「无结果」；去掉「执行 0 条仍成功」 | 前端 info |
| wp_id / project_id / config_id | 格式非法 / 对象不存在 / 非本项目 | 不可恢复 | 400（格式）/ 404（不存在）/ 403（越权）；对象 id 先最小反查 project 再鉴权 | 后端 warn |
| 门禁子进程 | 解码失败 | 可恢复 | `errors='replace'` + 断言 stdout 内容（否则 returncode=0 假绿，教训㉗⑦） | CI error |

外部输入校验要点：`year` 为必填 int（后端契约不变，前端必传）；`project_id/wp_id/config_id` 为 UUID，格式非法 → 400；body/query 的 `project_id` 与路径对象反查出的 project 不一致 → 403；批量保存请求体行数限额 + 单事务 CAS。

## 9. 可测试性

- **单元可测**：`matchSheetCode` 结构化精确等值（含 `E1-1` vs `E1-10/14/15`、`D2-1` vs `D2-10/12` 反例逐一判不串页 + 缺身份 fail-closed 排除）；保存 kind 分派（wp→upsert、surfaced→拒绝、report→detail）；字段名映射（保存体与渲染读 `category/description`）；函数支持矩阵查表（支持/不支持 → 允许/禁用）；**前端归一与 stable_key 真源一致：对同一组 sheet 名（含带排序前缀如「五、1 审定表D2-1」、全角空格、大小写敏感 wp_code），断言前端本地归一结果与 `app.services.formula_management.stable_key.normalize_sheet_key` 产出一致（第三轮评审 NIT-1 响应，防前端另写一套规范化致与库里 `stable_sheet_key` 对不上）**；**附注合并键冲突：构造一条用户公式与一条模板预设指向同一目标单元格键，断言合并后用户集覆盖模板预设、且拓扑排序对合并集统一重算（第二轮评审 NIT-1 响应）**；**表间审核树 key ↔ 规则 map key 一致性（构造不一致样本应判失败，MEDIUM-2 响应）**；门禁幂等（同输入两次运行 JSON 字节一致）。
- **集成/脚本可测**：**10 个 classification 404 各一次 `wp_code_overrides.json` 查表，分母剔除项有理由字段（MEDIUM-1 响应）**；**历史行回填复用单一真源：断言 §5 步骤 1 的回填逻辑与 `app.services.formula_management.stable_key.derive_stable_key` 对同一 `(sheet_name, target_cell)` 产出一致（含 `needs_review` 行的标记与排除），禁另写一套（第三轮评审 NIT-1 响应）**；缓存按 project key 隔离（切项目旧缓存失效）；保存用 `props.year`。
- **TestClient 可测**：§6.1 跨项目越权（读/写/执行全 403、0 副作用）；加固端点鉴权（对象反查 + require_project_access + body/query project_id 校验 + admin 门控）；wp CRUD 审计哈希链写入。
- **E2E/门禁可测**：§7 的 8 断言 + 4 变异（含反向断言）。
- **最小数据运行可测**：§6.2 逐值对拍 standalone + consolidated（run/state/outbox 落库、`run_id` 贯穿）。
- **难测点**：合并链真实对拍依赖「未删除 consolidated 项目 + 造数」，是集成级而非单元级，须先诊断再决策。

## 10. 实施前必做：重做 §1 现状 grep 确认（强制）

实施时 HEAD 必然已前移，§1 的行号/符号/路径可能漂移。**动代码前必须重跑 §1 全部 20 条 grep**，逐条标「确认成立 / 已变化 / 需调整」；任一条「已变化」须先更新本设计对应锚点再动手。重点复核：前端布局是否仍 `audit-platform/frontend/`、后端是否仍在仓库根 `backend/`；`matchSheetCode`、`onFormulaEditSave` 的 `row.id` 分支、`_build_surfaced_formulas` 的 `readonly:True`、各端点鉴权依赖、`createOpenFormulaManagerCommand` 是否仍零生产调用、`stable_sheet_key` 是否仍可空、`wp_code_overrides.json` 路径。**特别复核迁移归属（第三轮评审 MEDIUM-1 教训）**：`stable_sheet_key` 列由 `V163__wp_formula_stable_key.sql`（前向 `ADD COLUMN` + 回填 + 唯一索引）新增、`R163__wp_formula_stable_key.sql`（`DROP COLUMN`）为回滚——实施者按本节重做 grep 时，若去读 R163 会看到它在 DROP 该列，须认准前向迁移是 V163；并确认回填逻辑仍与 `app.services.formula_management.stable_key` 对齐。坐标漂移不报错、只会把补丁打错位置——这是本仓铁律。

## 11. 关键快照（撰写时实测值，交付/实施时须重扫，不写死进判据）

以下为撰写时在 HEAD `4934142a` 的实测观察，**仅作参考快照**；计数随并行会话漂移，**交付/实施时须重扫，禁写死进任何判据**（与 §0/§10 漂移纪律一致）：`createOpenFormulaManagerCommand` 生产引用数 = 0（仅 4 处测试/定义）；`formula-manager-open` testid 全仓 = 0；附注 `_user_formulas`/`list_note_formulas` 在 `FormulaManagerDialog.vue` 引用 = 0；报表 6 项目各 82 行克隆（6×82=492）；29 条 wp_formula 全属已软删项目。门禁的 `_IDENTITY_ONLY_BASELINE` 之类基线**不写死数字**，统一用「现算 + 禁写死」（与 §0/§10 漂移纪律一致）。报告第七节给出的 `_IDENTITY_ONLY_BASELINE=224` 仅表示「不再增加」、非「现状安全」，故本设计不把该值固化进任何判据；报告中出现的 `227` 是 `disclosure_notes.is_stale` 计数（第十一节附录 + 第十二节）、与鉴权基线无关，二者**不是矛盾值**、无须「规避」（铁律㉖「口径不同 ≠ 有偏差」）。

## 12. 七类模块深化（12.1~12.7）落点索引

- **12.1 底稿 wp**：串页（步骤 1①）、surfaced 只读 + kind 分派 + 字段名（步骤 1②③）、鉴权 + 审计（步骤 5）、函数矩阵（步骤 4）、运行坐实（§6.2 standalone）。
- **12.2 附注 note**：权威源二选一（步骤 4 / ADR-FMC-04）；鉴权不动（ADR-FMC-07）。
- **12.3 报表 report**：口径按 distinct 模板计（步骤 4）、鉴权 + admin（步骤 5）、运行坐实（§6.2 standalone）。
- **12.4 试算表 tb**：tb_detail 读/写鉴权（步骤 5）、`FORMULA_CONFIG_CHANGED` 条件项不实施（步骤 5）、tb_summary 随报表鉴权（步骤 5）。
- **12.5/12.6/12.7 合并三类**：§6.2 consolidated 最小数据运行先诊断后决策（ADR-FMC-09），禁写重写合并链。

## 13. 评审 findings 响应（对照 design-review.json / design-review.md）

| finding | 级别 | 处置 | 落点 |
|---|---|---|---|
| MEDIUM-1 · 10 个 classification 404 一次性归类无落点 | MEDIUM | **已修复** | §5 步骤 2 新增独立子任务（逐个查 `wp_code_overrides.json`；命中→数据漂移记补 override/classification 行，未命中→口径外剔出 §7.1 分母 + 登记理由；归类并入 §7.3 豁免登记）；§9 集成/脚本可测项「10 个 404 各一次查表、剔除项有理由字段」 |
| MEDIUM-2 · 表间审核树父/叶 key 与规则 map key 一致（需求 7.4）无落点 | MEDIUM | **已修复** | §5 步骤 6「report-cross-check year」行补「树父/叶节点 key 与规则 map key 用同一 key 生成、不一致视为契约缺陷」；§9 单元可测项「树 key↔规则 map key 一致性（不一致样本应判失败）」 |
| MEDIUM-3 · 字段误读 `formula_category/formula_description`（需求 2.4）无独立整改点 | MEDIUM | **已修复** | ADR-FMC-02「后果」显式列为独立改动点；§5 步骤 1 改动点 ③（独立于 kind 分派）；§3 数据流表「右栏字段读写」行；§7.2 断言⑤ + §9 单元可测项「保存体与渲染读契约字段」 |
| NIT-1 · §1 #2「报告声称」列未标 84def65b→e5ee550f 口径演进 | NIT | **已修复** | §1 #2 实测列补注「报告 84def65b 原述『统一写 report_config』，e5ee550f 已收窄，本实测采 e5ee550f 口径」 |
| NIT-2 · 门禁断言⑦坐实前 pending 未说明 | NIT | **已修复** | ADR-FMC-08 与 §7.2 断言⑦明确「鉴权整改合入前标 skip/pending、不计入分母红，合入后转硬断言」 |
| NIT-3 · tb_detail 进传播（需求 16.3）条件项未定本轮是否纳入 | NIT | **已修复** | §3 数据流表「tb_detail 传播」行 + §5 步骤 5 明确「本轮真库=0、无传播需求，`FORMULA_CONFIG_CHANGED` 条件项不实施，仅诊断发现需要时开」 |
| NIT-4 · §11 快照「撰写时 = 现扫一致项」易误读为保证一致 | NIT | **已修复** | §11 标题与正文改为「撰写时实测值，交付/实施时须重扫，不写死进判据」，并重申与 §0/§10 漂移纪律一致 |

全部 3 MEDIUM + 4 NIT 已处置，无 backlog、无 ignore。

### 13.1 第二轮评审 findings 响应（design-review.{json,md}，1 MEDIUM + 2 NIT）

> 第二轮评审在第一轮修订基础上重新独立核验，裁决 CHANGES_REQUESTED（0 HIGH / 1 MEDIUM / 2 NIT）。逐条处置如下。

| finding | 级别 | 处置 | 落点 |
|---|---|---|---|
| MEDIUM-1 · §11 把「报告 224 与 227 自相矛盾」当作规避基线的理由，但该矛盾不存在（事实错误） | MEDIUM | **已修复**。核验报告源文坐实：`_IDENTITY_ONLY_BASELINE` 全文唯一值为 224（第七节），`227` 是 `disclosure_notes.is_stale=true` 的 stale 计数（第十一节附录 + 第十二节），两者是不同指标、报告无自相矛盾。删除伪矛盾表述。 | §11：改为「基线不写死数字、统一现算+禁写死；224 仅表示『不再增加』非『现状安全』、不固化进判据；227 是 is_stale 计数、与鉴权基线无关、二者非矛盾值（铁律㉖）」 |
| NIT-1 · ADR-FMC-04 附注合并键冲突的优先级/去重语义仅标「实施时定」，缺可验收口径 | NIT | **已修复**。补默认口径：同键用户集优先覆盖模板预设、合并去重后统一重算拓扑；并给留调整余地（§6.2 对拍出更合理口径可在 tasks 调整并记录）。 | ADR-FMC-04「后果」新增默认口径段；§9 单元可测新增「附注合并键冲突：用户公式覆盖同键模板公式 + 拓扑统一重算」 |
| NIT-2 · §7.2 断言⑦转硬断言的前置未点明须 ADR-FMC-06 全部对象型端点（含 §16 tb_detail 读写）都已加固 | NIT | **已修复**。补前置条件：⑦转硬断言的前置 = wp_formula/report_config/execute/scope/tb_detail 读写全部加固并通过 §6.1 坐实；任一未合入则整条⑦保持 pending、不做部分硬化。 | §7.2 断言⑦ 补前置条件句 |

本轮经现状 grep 核实的锚点：报告第七节 `_IDENTITY_ONLY_BASELINE=224`、第十一节附录 + 第十二节 `disclosure_notes.is_stale=227`、附注端点 `require_project_access`（第九/十二节复核）——三处确认 MEDIUM-1 的事实更正成立。1 MEDIUM + 2 NIT 全部处置，无 backlog、无 ignore。

### 13.2 第三轮评审 findings 响应（design-review.{json,md}，1 MEDIUM + 2 NIT）

> 第三轮评审裁决 CHANGES_REQUESTED（0 HIGH / 1 MEDIUM / 2 NIT）；评审肯定「§1 的 20 条现状 grep 为真核实、锚点全用符号名/端点字面量/HEAD 绑定、合并三类严格先诊断后决策、FM-P0-05 静态高危待坐实、附注三端点明确排除」，唯一阻断项是 §1 把前向迁移编号写反的已核实事实错误。逐条处置如下（已在本工作树 HEAD `4934142a` 对 `V163`/`R163`/`stable_key.py` 现读复核，结论全部成立）。

| finding | 级别 | 现读复核 | 处置 | 落点 |
|---|---|---|---|---|
| MEDIUM-1 · §1 #19 / ADR-FMC-01 / §5 步骤 1 把「新增 `stable_sheet_key` 列的迁移」错标为 R163（实为 V163；R163 是 DROP 该列的回滚脚本） | MEDIUM | **成立**。`V163__wp_formula_stable_key.sql` 为前向迁移（`ALTER TABLE wp_formula ADD COLUMN IF NOT EXISTS stable_sheet_key VARCHAR(255)` + `UPDATE` 回填 + `CREATE UNIQUE INDEX … WHERE stable_sheet_key IS NOT NULL`）；`R163__wp_formula_stable_key.sql` 为回滚（`DROP COLUMN IF EXISTS stable_sheet_key …`）。实质结论（列可空、须 fail-closed）不受影响，仅编号归属错。 | **已修复** | §1 #19 标题/正文、ADR-FMC-01 裁定、§5 步骤 1 改动点①、§10 重做 grep 提醒：统一改为「列由 **V163** 新增（`ADD COLUMN … VARCHAR(255)`，可空，唯一索引带 `WHERE stable_sheet_key IS NOT NULL`）；`R163` 为配对回滚（DROP）」 |
| NIT-1 · 右栏精确匹配与历史行回填未引用既有「稳定键单一真源」`app.services.formula_management.stable_key` | NIT | **成立**。`backend/app/services/formula_management/stable_key.py` 存在 `derive_stable_key`/`normalize_sheet_key`，docstring 明确「供 service 写入、迁移回填、PBT 三处共用，不各写一份」；V163 回填 SQL 注明「与该模块逻辑对齐」。原设计未点明，存在前端/回填另写一套规范化致与库里键分叉的风险。 | **已修复** | ADR-FMC-01 新增「稳定键单一真源」段 + §5 步骤 1 改动点①「回填与任何 sheet 名归一一律复用 `stable_key` 真源、禁另写」；§9 单元可测「前端归一结果与 `stable_key` 真源对同一 sheet 名产出一致」+ 集成可测「回填逻辑与 `derive_stable_key` 产出一致」 |
| NIT-2 · §5 步骤 1 改动点①「回填脚本补 **或** 右栏标注已排除」二选一未定本轮取舍（两者是不同用户可见行为） | NIT | **成立**。原文「或」与 ADR-FMC-01「后果」偏向「回填为主」的口径不一致，tasks 阶段难落为单一可验收任务。 | **已修复** | §5 步骤 1 改动点① 改为明确顺序：「**优先**一次性回填脚本（复用 `stable_key` 真源）补齐；回填后仍无法解析身份的 `needs_review` 行**才** fail-closed 排除并标注『无结构身份已排除 N 行』」，与 ADR-FMC-01「后果」口径统一；ADR-FMC-01「后果」同步改写 |

本轮经现状 grep 核实的锚点（HEAD `4934142a` 工作树实读）：`backend/migrations/V163__wp_formula_stable_key.sql`（前向 ADD COLUMN + 回填 + 唯一索引）、`backend/migrations/R163__wp_formula_stable_key.sql`（回滚 DROP COLUMN）、`backend/app/services/formula_management/stable_key.py`（`derive_stable_key`/`normalize_sheet_key` 单一真源，docstring 自述三处共用）——三处确认本轮三条 finding 全部成立并已修复。1 MEDIUM + 2 NIT 全部处置，无 backlog、无 ignore。

### 13.3 第四轮评审 findings 响应（design-review.{json,md}，1 MEDIUM + 2 NIT；由 orchestrator 在 design 循环 abort 后补齐）

> 第四轮评审裁决 CHANGES_REQUESTED（0 HIGH / 1 MEDIUM / 2 NIT）；design 循环在此轮达到 maxIterations 而 abort。评审肯定「§1 现状 grep 为真核实、关键锚点逐字吻合、FM-P0-05 静态高危待坐实、附注端点正确排除、合并三类先诊断后决策、V163/R163 已修正」，唯一阻断项是需求 20（P2 治理组）在 design 零落点。由 orchestrator 对照 design-review.json 逐条补齐（设计本身已三轮收敛、仅差此一节，无须重跑整个循环）。

| finding | 级别 | 处置 | 落点 |
|---|---|---|---|
| MEDIUM-1 · 需求 20（P2 治理组：≥7 套 local dialog 收敛、2 条历史假红测试、1164 warnings、RTK 吞退出码）在 design 零落点，4 条 AC 无法派生任务 | MEDIUM | **已修复**。§5 新增「步骤 8 · P2 治理收敛」逐条给 20.1~20.4 落点（local dialog 登记去留 / 两测试修为反映真实行为 + 变异反证 / 1164 warnings 定位 `Connection._cancel` 根因 / RTK 断言 stdout 复用 §7.4③）；并声明 P2 为治理收尾、ROI 不足可 `*` 条件项处置但须显式记录边界（不默默丢正式需求）。 | §5 步骤 8（新增）；§7.4③ 复用 |
| NIT-1 · §7.2 断言⑤三义合一、§7.5 两变异都映射⑤致子项计红含糊 | NIT | **已修复**。断言⑤拆为可独立计红的 ⑤a（右栏精确）/⑤b（surfaced 只读去伪装）/⑤c（保存契约字段 + 目标端点）；§7.5 变异表「注入 E1-10」→⑤a、「save 改回 report_config」→⑤c，并补一条「surfaced 加回编辑按钮」→⑤b 变异，每子项各有独立变异 + 反向断言。 | §7.2 断言⑤；§7.5 变异表 |
| NIT-2 · 10 个 classification 404 归类清单与分母剔除须点明实施期重算 | NIT | **已修复**。§5 步骤 2 404 归类补「清单及 override 命中随 HEAD/项目漂移，须实施期对当时真实项目重跑 classification API + 重查 overrides 现算得出，不沿用撰写期快照，剔除项带可验证理由字段、禁写死」。 | §5 步骤 2 404 归类子任务 |

本轮响应由 orchestrator 直接补齐（design 循环 abort 于 maxIterations，非设计质量问题）；所有落点均在既有 §1 现状 grep（HEAD `4934142a`）基础上书写，不新增未核实锚点。1 MEDIUM + 2 NIT 全部处置，无 backlog、无 ignore。至此 design 四轮评审的全部 findings 均已闭合。
