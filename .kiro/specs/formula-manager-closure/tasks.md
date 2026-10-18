# 实施任务：公式管理平台缺陷闭环（formula-manager-closure）

> 关联需求：#[[file:.kiro/specs/formula-manager-closure/requirements.md]]（20 条需求，EARS 风格）
> 关联设计：#[[file:.kiro/specs/formula-manager-closure/design.md]]（九条 ADR、§5 八步整改、§6 诊断、§7 全量门禁）
> 唯一权威输入：`docs/proposals/formula-management-platform-audit-2026-10-17.md`（审计报告，第九/十/十二/十三节）。

## 锚点绑定与实施前强制提醒（动代码前必读）

- **锚点绑定（design §0）**：本 spec 所有「现状 grep / 行号锚点 / 计数快照」均绑定 HEAD `4934142a1c221afb785cdfcddee8aaaba7fb7527`。坐标漂移不报错、只会把补丁静默打到错位置——这是本仓反复踩过的坑。
- **实施前强制（design §10）**：动任何生产代码前，**必须先完成 Task 1.1**（重做 design §1 全部 20 条现状 grep 确认），逐条标「确认成立 / 已变化 / 需调整」；任一条「已变化」须先更新 design 对应锚点再动手。Task 1.1 是所有后续 Phase 的硬前置。
- **证据纪律（requirements 引言）**：严格区分「已坐实缺陷（改代码）」与「count=0 未证明（先诊断后决策）」；**禁把 count=0 写成「重写 / 重建链路」**（合并三类 Phase 7 / ADR-FMC-09 的硬约束）。
- **仓库布局（design §0 实测）**：前端在 `audit-platform/frontend/src/...`；**后端在仓库根 `backend/...`**（不在 `audit-platform/backend`）。
- **计数禁写死**：220 componentType、≈82 报表模板公式、10 个 classification 404、29 条 wp_formula、`_IDENTITY_ONLY_BASELINE` 等**均为撰写期快照**（design §11），实施期须对当时真实项目/HEAD 现算，禁写进任何判据（design §0/§10/§11 漂移纪律）。
- **Phase 结构声明**：8 个 Phase 严格对齐 design §5 八步，顺序不可改。Phase 8（P2 治理）内任务带 `*` 者为可选/条件项（design §5 步骤 8 的 P2 边界声明），须在该任务显式记录「本轮仅登记 / 条件实施」的决策边界。
- **验收纪律**：每个任务的「验收」须是可跑测试 / 门禁 / 对拍（取自 design §9 可测性 + §7 门禁 + 报告第十三节待办表「验收门禁」列），**不以 grep 命中作验收**；守卫须配变异反证（memory 铁律㉒㉖：单向变异会把干净态判成缺陷，故每条变异配反向断言）。
- **稳定键单一真源（ADR-FMC-01 / NIT-1）**：所有 sheet 名归一（右栏匹配、历史行回填、前端本地归一）**一律复用** `backend/app/services/formula_management/stable_key.py` 的 `derive_stable_key` / `normalize_sheet_key`，**禁另写一套规范化**。
- **编排原子性（memory 操作铁律）**：跨 service 编排的 router 端点各 service 只 `flush`，router 统一 `commit` 保原子。

每个任务统一四项标注：**【需求】** requirements 编号；**【design 锚点】** ADR-FMC-0x / §5 步骤 x / §1 #n / §7；**【验收判据】** 可跑测试 / 门禁 / 对拍；**【待办 ID】** 报告第十三节待办表缺陷 ID。

---

## Phase 1 · 步骤 1 P0 止错（串页 / surfaced 伪装 / 错保存域 / 字段误读）

> design §5 步骤 1（改动点 ①②③）、ADR-FMC-01 / ADR-FMC-02；覆盖需求 1、2、13（wp 收敛）。

- [x] 1.1（前置·强制）实施前重做 design §1 全部 20 条现状 grep 确认
  - 在当时真实 HEAD 的工作树上重跑 §1 全部 20 条 grep / 读码，产出一张「20 条锚点 × {确认成立 / 已变化 / 需调整}」核实表（随当时真实 HEAD，不照抄本设计撰写期结论）。
  - 重点复核：前端是否仍 `audit-platform/frontend/`、后端是否仍在仓库根 `backend/`；`matchSheetCode`（#1）、`onFormulaEditSave` 的 `row.id` 分支（#2）与字段 `formula_category/formula_description`（#2b）、`_build_surfaced_formulas` 的 `readonly:True`（#3）、各端点鉴权依赖（#4/#7/#9/#10/#11）、`createOpenFormulaManagerCommand` 是否仍零生产调用（#5）、左栏 `loadAcnrTree/buildWpDomainTree/acnrDrivenTree`（#6）、`report-config` `/types` 被 UUID 路由捕获（#8）、附注 `require_project_access`（#12）、`run_report_cross_check` 的 `year` 必填（#13）、`execute_note_formulas` vs `upsert_note_formulas` 双存储（#14/#15）、E1/D4 node-only 旁路（#16）、Univer「同步公式」（#17）、`formula-manager-open` 全仓零命中（#18）、`stable_sheet_key` 列由 **V163** 新增（`R163` 为回滚 DROP）且 `nullable=True`（#19）、`wp_code_overrides.json` 路径（#20）、`stable_key.py` 单一真源仍在。
  - 任一「已变化」必须**先更新 design 对应锚点再继续**后续任何任务。
  - 【需求】贯穿（design §10 强制前置）
  - 【design 锚点】§0 锚点绑定、§1 #1~#20、§10、§11
  - 【验收判据】产出 20 条核实表（文档化，随当时真实 HEAD）；若有「已变化」项，附对应 design 锚点更新 diff。本任务不改生产代码。
  - 【待办 ID】全部（前置动作，不单独对应某 ID）

- [x] 1.2 右栏串页修复：`matchSheetCode` 改结构化精确等值 + fail-closed（改动点①）
  - `FormulaManagerDialog.vue : matchSheetCode` 及右栏聚合调用处，改为按 `stable_sheet_key` / `sheet_uid` 结构化**精确等值**（`a===b` 结构键），删除 `a.includes(b) || b.includes(a)` 子串匹配；缺可解析结构身份的行 fail-closed 排除，**禁退回 `includes`**。
  - 后端 `backend/app/routers/wp_formula.py` 公式投影须带 `stable_sheet_key`，供前端做结构化等值。
  - 前端若需本地归一 sheet 名，须复用 `stable_key` 真源口径（见 Task 1.3）。
  - 【需求】需求 1.1、1.2、1.3、1.4；需求 13.1
  - 【design 锚点】ADR-FMC-01、§5 步骤 1 改动点①、§1 #1 / #19；稳定键单一真源 `backend/app/services/formula_management/stable_key.py`
  - 【验收判据】单测逐一构造报告反例（`E1-1` vs `E1-10/14/15`、`D2-1` vs `D2-10/12`）断言不串页；缺结构身份行断言被 fail-closed 排除（不退 `includes`）。变异反证：注入 `includes` 旧逻辑 / 注入 `E1-10` 串页行，对应反例用例应打红；未注入时不命中（反向断言）。门禁断言⑤a 守护（Task 8.1）。
  - 【待办 ID】FM-P0-01

- [x] 1.3 历史缺值行 `stable_sheet_key` 回填（改动点①附属，复用单一真源）
  - **优先**写一次性回填脚本补齐历史行 `stable_sheet_key`，回填与任何 sheet 名归一**一律复用** `stable_key.derive_stable_key` / `normalize_sheet_key`（禁另写规范化）；回填后仍无法解析 A1 / sheet 结构身份的 `needs_review` 行**才** fail-closed 排除，右栏明确标注「无结构身份已排除 N 行」。即「回填为主、标注为过渡」，非二选一。
  - 脚本幂等、名称带可识别前缀、探针放仓库外；仅处理历史数据，不改范式。
  - 【需求】需求 1.4
  - 【design 锚点】ADR-FMC-01「后果」、§5 步骤 1 改动点①「回填为主、标注为过渡」、§9 集成可测
  - 【验收判据】集成测试断言回填逻辑与 `derive_stable_key` 对同一 `(sheet_name, target_cell)` 产出一致（含 `needs_review` 行的标记与排除）；若前端本地归一，单测断言其结果与 `normalize_sheet_key` 对同一组 sheet 名（含带排序前缀「五、1 审定表D2-1」、全角空格、大小写敏感 wp_code）产出一致。变异反证：篡改回填归一逻辑应使一致性断言打红。
  - 【待办 ID】FM-P0-01

- [x] 1.4 surfaced/extraction 前端强制只读 + 保存按 kind 分派（改动点②）
  - `FormulaManagerDialog.vue`：据后端 `readonly` 标志把 surfaced/extraction 渲染为只读（去「编辑」按钮、去「自定义」「健康度100%」伪装标签）。
  - `onFormulaEditSave` 保存链先按行 kind 分派：wp 行走 `wpFormula.upsert`（`PUT /api/workpapers/{wp_id}/formulas`）、surfaced/extraction 拒绝保存并提示只读、仅 report 行走 `P_rc.detail`；`tb_detail` 节点保持既有 `persistTbDetailFormulas()` 分流。
  - 后端 `backend/app/routers/wp_formula.py : save_formula` 对非 wp kind 拒收作纵深防御。
  - 【需求】需求 2.1、2.2、2.3、2.5；需求 13.1
  - 【design 锚点】ADR-FMC-02、§5 步骤 1 改动点②、§1 #2 / #3
  - 【验收判据】单测：据 `readonly` 渲染只读（无编辑按钮、无伪装标签）；保存链按 kind 分派（wp→upsert、surfaced/extraction→拒绝、report→detail）；后端 `save_formula` 拒收非 wp kind。门禁变异「把 save 改回写 report_config」应被断言⑤c 捕获（Task 8.1、§7.5）；变异「surfaced 加回编辑按钮 / 渲染成可编辑」应被断言⑤b 捕获；各配反向断言。
  - 【待办 ID】FM-P0-02

- [x] 1.5 字段名修正 `formula_category/formula_description` → `category/description`（改动点③，独立）
  - `FormulaManagerDialog.vue` 读 / 写工作底稿公式行的字段统一为后端契约字段 `category` / `description`（含表格列 `prop`、分组、过滤、`onFormulaEditSave` 写入）。此点**独立于 kind 分派**：即便分派正确，字段名读错仍致 category/description 显示与保存错位。
  - 【需求】需求 2.4
  - 【design 锚点】ADR-FMC-02「后果」独立改动点、§5 步骤 1 改动点③、§1 #2b、§7.2 断言⑤c、§9 单元可测（MEDIUM-3 响应）
  - 【验收判据】单测断言：保存请求体字段 = 契约字段 `category/description`；右栏渲染读的是契约字段。门禁断言⑤c 同守护。变异：把字段改回 `formula_category/formula_description` 应打红；反向断言未改时不命中。
  - 【待办 ID】FM-P0-02

---

## Phase 2 · 步骤 2 统一入口（ADR-FMC-03）+ 10 个 classification 404 一次性归类

> design §5 步骤 2；覆盖需求 3、9。

- [x] 2.1 生产真正调用 `createOpenFormulaManagerCommand` + 统一 testid + 删 node-only 旁路
  - 生产代码真正调用 `audit-platform/frontend/src/shell/formula/openFormulaManagerCommand.ts : createOpenFormulaManagerCommand`；每个可渲染页恰一个 `data-testid=formula-manager-open` 的 primary outlet，点击提交完整 `CanonicalWorkpaperLocation`（projectId/wpId/wpCode/sheetUid…）。
  - 删除 E1 页内第二按钮与 D4-33~36 的 node-only 旁路（`GtE1MonetaryFund.vue`、`D4TabOther{Check,Contract,Cutoff,Margin}.vue`），或改为提交完整 location；WHEN 从这些入口打开则 scope 标签与面包屑一致（底稿入口不落 `report` scope），且不产生 `/report-config/types` 或缺 year 的 422。
  - A1（`a1-dashboard`）自管工具栏与 Univer 主路径（`useEditorToolbar.ts`）补同一 primary outlet 入口。
  - 【需求】需求 3.1、3.2、3.3、3.5；需求 9.1
  - 【design 锚点】ADR-FMC-03、§5 步骤 2、§1 #5 / #16 / #17 / #18
  - 【验收判据】门禁断言①（恰一个 testid）、②（单弹窗）、③（完整 location）守护（Task 8.1）；变异「删按钮」命中①、「去 wp_id」命中③，各配反向断言。单测断言 E1/D4 入口提交完整 location（非仅 nodeKey）。
  - 【待办 ID】FM-P0-03、P1-A1/Univer 无入口

- [x] 2.2 B15 `redirect-materiality` 正式豁免登记
  - `redirect-materiality`（B15）登记为带 `owner/reason/expires_at` 的可伪证豁免（含「判据抽不到值」防空转断言），并入 §7.3 门禁分母豁免登记。
  - 【需求】需求 3.4
  - 【design 锚点】ADR-FMC-03、§5 步骤 2、§7.3
  - 【验收判据】门禁读取豁免登记，`redirect-materiality` 从非 redirect 分母剔除且登记三字段齐全；变异：删掉豁免条目应使该项计入分母并触发相应断言红。
  - 【待办 ID】FM-P0-03

- [x] 2.3 componentType 覆盖闭合 + 10 个 classification 404 一次性归类（实施期现算）
  - 枚举全部声明 componentType（撰写期快照 ≈220，**实施期现算**），每项恰有「当前页入口覆盖」或「带期限正式豁免」，无未知未覆盖项。
  - 对**实施期当时真实项目**重跑 classification API 得出的 404 `wp_code`（撰写期快照 10 个，**禁写死、须现算**），逐个查 `backend/app/data/wp_code_overrides.json`：命中映射→判「数据漂移」（记应补的 override / classification 行，仍计入按钮分母）；未命中→判「口径外」（从 §7.1 分母**显式剔除** + 登记带可验证理由字段的豁免）。归类并入 §7.3 豁免登记；归类后报告第四节「无法判定」子类解除。
  - 【需求】需求 3.5；需求 9.2、9.3、9.4
  - 【design 锚点】§5 步骤 2 404 归类子任务、ADR-FMC-03、§1 #20、§7.1 / §7.3、§9 集成可测（MEDIUM-1 / NIT-2 响应）
  - 【验收判据】集成/脚本测试：10 个 404（现算）各一次 `wp_code_overrides.json` 查表，剔除项有可验证理由字段；门禁分母枚举无未知未覆盖项。清单禁写死，变异：伪造一个新 404 wp_code 应被门禁识别为未归类而要求归类。
  - 【待办 ID】FM-P0-03、P1-A1/Univer 无入口（含报告第四节 404 子类）

---

## Phase 3 · 步骤 3 左右栏契约收敛（ADR-FMC-01、ADR-FMC-05）

> design §5 步骤 3；覆盖需求 6。

- [x] 3.1 右栏服务端精确过滤 `GET formulas?project_id&wp_id&sheet_uid`
  - 后端 `GET formulas` 按 `project_id&wp_id&sheet_uid` 服务端精确过滤；右栏每行带同一 location identity（projectId/wpId/sheetUid）。与 Task 1.2 的前端结构化等值配套（服务端口径）。
  - 【需求】需求 6.2；需求 1.1（服务端口径）
  - 【design 锚点】ADR-FMC-01、§5 步骤 3
  - 【验收判据】集成测试断言服务端按三键精确过滤、返回行均属精确当前 sheet；门禁断言⑤a 守护（右栏 `stable_sheet_key` 精确相等）。变异：放宽服务端过滤为前缀匹配应打红。
  - 【待办 ID】FM-P0-01、P1-左栏非当前页地址

- [x] 3.2 左栏改为当前页 anchors + 显式全局浏览按钮 + 缺 identity fail-closed（ADR-FMC-05）
  - `FormulaManagerDialog.vue` 左栏默认调 `GET addresses?project_id&wp_id&sheet_uid`（或等价 listCells），只显精确当前 sheet 的 `addr_id`，替换现有 `loadAcnrTree/buildWpDomainTree/acnrDrivenTree` 全局五域树默认行为。
  - 「全局浏览」作独立显式按钮、**不**作缺上下文默认回退；缺 location identity 时 fail-closed（显式告警 + 空集），不退全局树。左右栏每行带同一 location identity。
  - 【需求】需求 6.1、6.2、6.3、6.4
  - 【design 锚点】ADR-FMC-05、§5 步骤 3、§1 #6
  - 【验收判据】单测/集成：左栏默认只返精确当前 sheet 的 `addr_id`；缺 identity 时返空集 + 告警（非全局树）；「全局浏览」为独立按钮。门禁断言④守护（左侧 addr_id 全属精确当前 sheet）。变异：把缺 identity 回退改成全局树应打红。
  - 【待办 ID】P1-左栏非当前页地址

---

## Phase 4 · 步骤 4 收敛权威源与执行语义

> design §5 步骤 4、ADR-FMC-04；覆盖需求 4、8、14（note 收敛）、15（报表口径）。

- [x] 4.1 附注权威源收敛：`execute_note_formulas` 合并消费 `_formulas` ∪ `_user_formulas`（ADR-FMC-04）
  - `backend/app/services/note_formula_generator.py : execute_note_formulas` 合并消费 `_formulas`（模板预设）与 `_user_formulas`（用户集）两键；合并默认口径：同一目标单元格键冲突时**用户集优先**覆盖模板预设，对合并去重后的集合**统一重算拓扑排序**（不是两套各自排序后拼接）。
  - 中央 `FormulaManagerDialog.vue` 附注节点改调 `list_note_formulas`（含用户集），替换现仅读模板预设。
  - 附注三端点鉴权保持不变（ADR-FMC-07，本任务不动 `apply/list/upsert` 的 `require_project_access`）。若 §6.2 最小数据运行对拍出更合理口径，可在实施期调整并记录。
  - 【需求】需求 4.1、4.2、4.3、4.4；需求 14.1、14.2
  - 【design 锚点】ADR-FMC-04、ADR-FMC-07、§5 步骤 4、§1 #14 / #15、§9 单元可测
  - 【验收判据】单测构造「用户公式与模板预设指向同一目标单元格键」样本，断言合并后用户集覆盖模板预设、拓扑对合并集统一重算（不产生两次回填/排序抖动）；单测断言弹窗附注节点调 `list_note_formulas`；断言附注三端点鉴权未被改动。变异：去掉用户集合并应使覆盖样本打红。
  - 【待办 ID】FM-P0-04

- [x] 4.2 函数支持矩阵禁静默 0（需求 8）
  - 维护一张「函数 × 执行器 → 支持 / 不支持」矩阵，覆盖 wp evaluator（真支持 TB/SUM_TB/WP）、report 路径（当前强制 PREV/AUX=0）、note 执行器、中央 batch（ADJ 实时注入）。
  - 不支持者 UI 显式禁用 / 标注「此处不支持」，**禁点击后静默返回 0**；支持者运行产生真实结果，不以空 ctx 回退 0。
  - 【需求】需求 8.1、8.2、8.3、8.4；需求 13.2
  - 【design 锚点】§5 步骤 4「函数支持矩阵」、§1（报告第三/五/九节）、§9 单元可测
  - 【验收判据】单测查表：不支持者 UI 禁用/标注、禁静默 0；支持者运行产生真实结果。变异：把某不支持函数改成静默返 0 而 UI 仍可点，应被断言打红；反向断言支持函数不误判为禁用。
  - 【待办 ID】P1-函数按钮/运行不一致

- [x] 4.3 报表链口径澄清（按 distinct 模板计，不按项目克隆夸大）
  - 文档化口径：报表链「生产实证」按 distinct 模板/标准计（撰写期量级 ≈82 条模板公式），**不按项目数（6）夸大**为 6 倍（6×82=492 是同一模板 6 份克隆，非 6 份独立证据）；`formula_push` 明确文档化为**自动物化层、非权威定义源**。本任务以口径澄清 + 测试断言口径为主，不改模板范式。
  - 【需求】需求 15.1
  - 【design 锚点】§5 步骤 4「report=report_config」、§3 数据流表「报表链」、深化 12.3
  - 【验收判据】脚本/测试断言 distinct 口径（去重 `(row_code+formula_used)`）与项目克隆口径的区分，断言不以项目数夸大；量级随实施期现算、禁写死。
  - 【待办 ID】FM-P0-05（报表侧）

---

## Phase 5 · 步骤 5 项目鉴权与原子性（ADR-FMC-06、ADR-FMC-07）

> design §5 步骤 5、§6.1；覆盖需求 5、15（鉴权）、16（tb-detail 鉴权）。FM-P0-05 必须「先 §6.1 TestClient 坐实再加固」。

- [x] 5.1（前置·先坐实）FM-P0-05 跨项目越权 TestClient 坐实（§6.1，ADR-FMC-06）
  - 写一条 TestClient 用例：以项目 A 凭据，对项目 B 的 `wp_formula` 读/写（`GET/PUT/POST /api/workpapers/{B_wp_id}/formulas`）、`report_config` 更新（`PUT /api/report-config/{config_id}`）、`/api/formula/execute`、`formula-scope`（`GET /api/formula-scope/{B_project_id}/formulas`）、`tb_detail` 读/写（`GET/PUT /api/report-config/tb-detail-formulas/{B_project_id}`）分别发请求。
  - **加固前先记录实际响应**（预期多数 200 坐实 IDOR）；加固后断言全部 403 且 0 副作用（目标项目数据无变更）。
  - 用例须 `dependency_overrides` 内层 `get_current_user` / `get_db`（**禁直接覆盖 `require_project_access` 工厂**——每次返回新函数对象，覆盖静默失效，memory 教训㉕①）；鉴权口径穷举（避免漏判 `require_project_delegator` / `require_wp_edit_permission` 等别名）。
  - 若某端点加固前已 403，据运行时结果更新定级（需求 5.8），不继续按「已越权」处置。
  - 【需求】需求 5.1、5.2、5.8
  - 【design 锚点】ADR-FMC-06、§6.1、§1 #4 / #7 / #9 / #10 / #11
  - 【验收判据】TestClient 用例可跑：加固前记录响应（坐实/推翻 IDOR），加固后全部 403 + 0 副作用。本任务是 Phase 5 全部加固任务与门禁断言⑦的硬前置。
  - 【待办 ID】FM-P0-05

- [x] 5.2 对象型端点加固（对象 id 反查 project + require_project_access + body/query project_id 校验）
  - `wp_formula`（list/save/delete）、`formula-scope/{project_id}`、`tb_detail` 读端补 `require_project_access("readonly")`、写端在 `require_role` 外叠加项目归属校验；路径只有 `{wp_id}` 的对象型端点先最小反查 `project_id` 再 `require_project_access`；body/query 的 `project_id` 与路径对象反查出的 project 不一致 → 403。附注端点不动（ADR-FMC-07）。
  - 【需求】需求 5.3、5.5；需求 16.1、16.2
  - 【design 锚点】ADR-FMC-06、ADR-FMC-07、§5 步骤 5、§1 #4 / #9 / #11
  - 【验收判据】TestClient：对象型端点读/写补项目级鉴权，body/query project_id 不一致返 403；附注端点断言未被改动。变异：摘掉某端点鉴权依赖应使越权用例打红（逐处变异，memory 铁律㉖）。
  - 【待办 ID】FM-P0-05、P1-缓存未隔离/传播（tb-detail 侧归 FM-P0-05）

- [x] 5.3 全局模板 / 全局自定义函数写限 admin（report_config CRUD + formula.py 注册/注销）
  - `backend/app/routers/report_config.py` 的 list/get/clone/update/create/delete/execute-batch 补 `require_project_access`（body/query project_id 同样校验）+ 全局模板写操作限 admin；`backend/app/routers/formula.py` 自定义函数注册/注销限 admin。非 admin 写/注册返回 403。
  - 【需求】需求 5.4；需求 15.2
  - 【design 锚点】ADR-FMC-06、§5 步骤 5、§1 #7 / #10
  - 【验收判据】TestClient：report_config 写端 + 自定义函数注册/注销非 admin 返 403，admin 通过。变异：移除 admin 门控应使非 admin 写用例打红。
  - 【待办 ID】FM-P0-05（报表侧）

- [x] 5.4 批量单事务 + CAS + wp CRUD 写审计哈希链
  - 批量保存请求体行数限额 + 单事务 + CAS；直接 `wp_formula` CRUD 写 `append_audit_log` 哈希审计链。service 只 flush、router 统一 commit（memory 操作铁律）。
  - 【需求】需求 5.6；需求 13.4
  - 【design 锚点】§5 步骤 5、§8 错误处理（批量行数限额 + 单事务 CAS）
  - 【验收判据】TestClient 断言：批量超限额被拒、单事务回滚一致、CAS 冲突被拒；wp CRUD 后审计链有新条目。变异：去掉 CAS 应使并发冲突样本打红。
  - 【待办 ID】FM-P0-05

- [x] 5.5* tb_detail 传播 `FORMULA_CONFIG_CHANGED`（条件项·本轮不实施）
  - 本轮 tb_detail 真库=0、无传播需求，`FORMULA_CONFIG_CHANGED` 列为**条件项不实施**，仅诊断（Phase 7）发现需要时开。
  - **决策边界（本轮仅登记）**：本轮不实施；触发条件 = 诊断发现 tb_detail 有真实公式且需进统一 stale 传播时才开。
  - 【需求】需求 16.3
  - 【design 锚点】§5 步骤 5「tb_detail 传播条件项」、§3 数据流表、NIT-3 响应
  - 【验收判据】文档化「本轮不实施 + 触发条件」边界；无需跑测试（条件项）。若实施期诊断触发条件成立，再在后续轮次补 `FORMULA_CONFIG_CHANGED` 发事件 + stale 传播测试。
  - 【待办 ID】FM-P0-05（tb-detail，复核发现）

---

## Phase 6 · 步骤 6 执行/传播可观测性

> design §5 步骤 6；覆盖需求 7（表间审核）、10（缓存/年份/单行 stale）、9（report-config/types）。

- [x] 6.1 report-config/types 路由修复（§1 #8）
  - 新增真实 `GET /types` 路由或前端改走正确端点，使 `/types` 不再被 `GET /{config_id}` 的 UUID 路由捕获为 422。
  - 【需求】需求 9（report-config/types 侧）
  - 【design 锚点】§5 步骤 6、§1 #8、§8 错误处理表
  - 【验收判据】TestClient 断言 `/types` 返 200 正确响应、不再 422。变异：移除 `/types` 路由应使该断言打红。
  - 【待办 ID】P1-表间审核契约错（关联 report-config/types）

- [x] 6.2 report-cross-check year 必填 + 按执行结果解析 + 规则落库 + 树 key↔规则 map key 一致
  - 前端 GET 带 `year`（项目年）不再恒 422；前端按「执行结果」解析响应（非「规则列表」）；新增/编辑规则落库持久化（关闭再打开仍可见）；空结果显式「无结果」（不以静态示例冒充）；表间审核树父/叶节点 key 与规则 map key 用**同一 key** 生成。
  - 【需求】需求 7.1、7.2、7.3、7.4、7.5
  - 【design 锚点】§5 步骤 6、§1 #13、§9 单元可测（MEDIUM-2 响应）
  - 【验收判据】集成：GET 带 year 返 200；按执行结果解析；规则落库（重开可见）；空结果显式「无结果」。单元：构造树 key 与规则 map key **不一致**样本应判失败（MEDIUM-2）；反向断言一致样本通过。
  - 【待办 ID】P1-表间审核契约错

- [x] 6.3 缓存按 project key 隔离 + 单行保存触发统一 stale + 保存用项目年（需求 10）
  - `report/note/cross-check` 缓存（`noteTreeLoaded/reportTypesLoaded/crossCheckLoaded`）按 project key 隔离，切项目失效旧缓存、旧响应不覆盖新项目结果；「保存全部」与单行保存用 `props.year`（项目年，非系统当前年）；单行保存触发与「保存全部」相同的统一 stale 传播；ACNR GET abort 后重发不污染跨项目上下文。
  - 【需求】需求 10.1、10.2、10.3、10.4；需求 13.3
  - 【design 锚点】§5 步骤 6、§9 集成可测（缓存按 project key 隔离、保存用 props.year）
  - 【验收判据】单测/集成断言：切项目旧缓存失效、旧响应不覆盖；保存用 `props.year`；单行保存触发统一 stale。变异：把缓存 key 去掉 project 维度应使跨项目串样本打红。
  - 【待办 ID】P1-缓存未隔离/传播

- [x] 6.4 每次执行写 run/issue/hint/outbox/audit 同 run_id + 去掉「执行 0 条仍成功」
  - 每次执行写 run/issue/hint/outbox/audit 且可查询、贯穿同一 `run_id`；去掉「执行 0 条仍成功」，0 条可执行时显式「无结果」。（落库逐值由 Phase 7 最小数据运行坐实。）
  - 【需求】需求 10（传播侧）；需求 11.4（run_id 贯穿，运行坐实在 Phase 7）
  - 【design 锚点】§5 步骤 6、§8 错误处理表（执行 0 条显式「无结果」）
  - 【验收判据】集成断言：执行写五表且 `run_id` 贯穿；0 条执行返「无结果」而非「成功」。变异：把 0 条执行改回「成功」应打红。
  - 【待办 ID】P1-缓存未隔离/传播

---

## Phase 7 · 步骤 7 + §6.2 最小数据运行（先诊断后决策）

> design §5 步骤 7、§6.2、ADR-FMC-09；覆盖需求 11、17、18、19。合并三类严格两段式，**禁写「重写/重建合并链」**（requirements Out-of-Scope + ADR-FMC-09 硬约束）。

- [x] 7.1 standalone 一套最小数据运行坐实（需求 11）
  - 在未删除的 standalone 项目造一套隔离公式并保存 → 重开右栏与保存一致 → 执行使目标值改变、`last_computed_at` 更新 → `stale` / `formula_runtime_outbox` / audit 均带同一 `run_id`。以逐值对拍权威表为准，不看组件/mock。
  - 造数用幂等脚本、名称带可识别前缀、用完经项目回收站删除、探针放仓库外。
  - 【需求】需求 11.1、11.2、11.3、11.4、11.5
  - 【design 锚点】§6.2 standalone、§5 步骤 7、§9 最小数据运行可测
  - 【验收判据】逐值对拍：保存↔重开一致、执行后目标值改变 + `last_computed_at` 更新、五处带同一 `run_id`；以权威表为准（不看 mock）。产出运行记录。
  - 【待办 ID】P1-正式运行数据为空

- [x] 7.2（两段式·先诊断）consolidated 合并三类最小数据运行诊断（§6.2，ADR-FMC-09）
  - 在未删除的 consolidated 项目造一套隔离合并公式 + 触发推送/重算，**一次运行覆盖**：12.5（对拍 `consol_report_values`）、12.6（对拍 `consol_note_data`）、12.7（合并底稿「公式」在差额表引擎中间节点，随 12.5/12.6 同一运行观察 `consol_report_values`/`consol_note_data`）；三子节均观察 `consol_push_run` 是否落库。
  - 造数幂等、名称带前缀、用完经回收站删除、探针放仓库外、不污染真实项目。**本任务只诊断、产出诊断报告（落库/对拍结果），禁改代码、禁写「重写合并链」。**
  - 【需求】需求 17.1、18.1、19.1
  - 【design 锚点】§6.2 consolidated（12.5/12.6/12.7 表）、ADR-FMC-09
  - 【验收判据】产出诊断报告：逐值对拍 `consol_report_values`/`consol_note_data` + `consol_push_run` 落库观察结果；明确每子节「落库且对拍一致 / 不落库或不一致」。本任务不改代码。
  - 【待办 ID】三 consol 子节统一（12.5/12.6/12.7）

- [x] 7.3（两段式·后决策）合并三类据诊断结果决策
  - 据 Task 7.2 结果二分决策：落库且对拍一致 → 判「已打通（仅数据阻塞）」**不改代码**，记录结论；不落库/不一致 → 判「已断裂」，据失败点定位**最小改动**（禁预设重写整条链）并实施 + 复测。
  - 【需求】需求 17.2、17.3、17.4；需求 18.2、18.3；需求 19.2、19.3
  - 【design 锚点】ADR-FMC-09「结果分支」、§6.2 纪律
  - 【验收判据】据诊断二分记录结论：判「已打通」则记录结论无代码改动；判「已断裂」则给最小改动 + 复测对拍一致。措辞禁「重写/重建合并链」。
  - 【待办 ID】三 consol 子节统一（12.5/12.6/12.7）

---

## Phase 8 · 步骤 8 P2 治理收敛 + 全量门禁

> design §5 步骤 8、§7 全量门禁；覆盖需求 20、12。P2 项带 `*` 为可选/条件项，须记录决策边界。

- [x] 8.1 全量门禁 `formula-manager-all-accessible-pages.spec.ts`（需求 12，§7）
  - 项目 API 枚举全部可访问 `working_paper` → 逐张 GET render-config 展开「每真实 sheet + whole_workbook + redirect」形成运行时权威分母（每项记 `project_id/wp_id/wp_code/sheet_uid/sheet_code/host/componentType`）。
  - 每非 redirect 项跑 8 条断言：①唯一入口（恰一个 testid）②单弹窗 ③完整 location ④左栏精确（addr_id 全属当前 sheet）⑤a 右栏精确（`stable_sheet_key` 精确相等）⑤b surfaced 只读去伪装 ⑤c 保存契约字段 `category/description` + 目标端点按 kind 分派 ⑥切换隔离（旧响应不覆盖新项目）⑦权限分层（**已转硬断言**：Phase 5 全部对象型端点加固 + Task 5.1 §6.1 坐实完成，门禁以 4 个 Phase 5 TestClient 守卫 existsSync + 坐实文件断言 403/端点维度作运行时锚点，缺任一则⑦红、不 pending）⑧零错误（0 console error / 0 abort / 0 4xx）。
  - **实施产出（3 新文件，不动其他任务未提交改动）**：①门禁 spec `audit-platform/frontend/src/components/formula/__tests__/formula-manager-all-accessible-pages.spec.ts`（vitest，40 用例全绿）②运行时分母枚举器 `backend/scripts/check/check_formula_manager_all_pages_denominator.py`（真连 PG 枚举 working_paper→render-config，`--write`/`--check`/`--json`，退出码 OK=0/DRIFT=2/DB_UNAVAILABLE=3）③幂等分母产物 `backend/app/data/formula_manager_all_pages_denominator.json`（真连实测 740 底稿展开 7182 项、render_config_resolved=7182/7182、redirect=4 B15、exempted=8）。
  - **8 断言复用 Phase 1~7 单一真源**：①③→`openFormulaManagerFromLocation`（Task 2.1）、④→`leftPanelAnchors`（3.2）、⑤a→`sheetIdentityMatch`（1.2）、⑤b→`formulaRowKind`+Dialog 编辑列模板结构（1.4）、⑤c→`wpFormulaFields`+`resolveSaveDispatch`（1.4/1.5）、⑥→`projectCacheKey`（6.3）、⑦→Phase 5 守卫、⑧→fail-closed。
  - **分母真连 §7.1（如实）**：枚举器真连 PG 成功（render-config 实现在进程内展开，一 wp 一 session 隔离真库 `wp_file_status` 枚举漂移致的事务 aborted）；门禁 spec 的 `beforeAll` 经 `spawnSync` 调枚举器 `--check` 真跑（约 230s）。真库不可达时枚举器 exit 3，门禁对「需真库的分母级断言」如实 `.runIf(dbAvailable)` 跳过（非假绿），8 契约断言 + 变异 + 幂等仍全跑（复用生产单一真源，不依赖活 HTTP）。
  - redirect / 口径外 404 用带 `owner/reason/expires_at` 可伪证豁免登记（含「判据抽不到值」防空转断言）。
  - 幂等输出（§7.4）：①内容不变不改时间戳、排序稳定、无机器名/绝对路径 ②沿用 `--check` 约定（漂移 exit 2 点名），**不用 `--write`+`git diff`** ③子进程 `PYTHONIOENCODING=utf-8` + `errors='replace'` 且**断言 stdout 含预期内容**（只看 returncode 在 Windows gbk 下必假绿，教训㉗⑦）。
  - 四变异 + surfaced 变异（§7.5）各命中对应子断言：注入 `E1-10`→⑤a、删按钮→①、去 `wp_id`→③、save 改回 report_config→⑤c、surfaced 加回编辑按钮/渲染成可编辑→⑤b；每变异配反向断言（未注入时不命中）。
  - **断言⑦ pending→硬断言（NIT-2，前置已满足）**：⑦依赖 ADR-FMC-06 鉴权整改落地；Phase 5 全部对象型端点（`wp_formula` 读写、`report_config` CRUD、`/api/formula/execute`、`formula-scope`、`tb_detail` 读写）均已加固并通过 Task 5.1 §6.1 坐实 ⇒ **本任务⑦已从 pending 转硬断言**，运行时锚点 = 4 个 Phase 5 TestClient 守卫（`test_fm_p0_05_cross_project_idor.py` / `test_wp_formula_sheet_uid_server_filter.py` / `test_task_5_3_global_write_admin.py` / `test_task_5_4_batch_cas_audit.py`）`existsSync` + 坐实文件断言 `403` 与端点维度覆盖，缺任一则⑦红、不 pending。
  - **变异验证（逐一真红 + 反向绿，各单独注入→跑→字节还原，无残留）**：①删 testid(A1)→hit 2<3 红；③去 `wp_id`→location 非 null 红；④缺 sheetUid→`current-sheet`≠`fail-closed` 红；⑤a 注入 `E1-10` includes→命中 `E1-1` 红；⑤b 编辑列 `v-if` 守卫失效→结构缺失红；⑤c wp→report 红；⑥去 `projectId` 维度→keyA===keyB 红。7 处生产文件变异全部 `str_replace` 还原，git 确认无 `MUTATION-TEST` 残留 + 锚点字节一致。
  - 【需求】需求 12.1、12.2、12.3、12.4、12.5、12.6
  - 【design 锚点】ADR-FMC-08、§7.1 / §7.2 / §7.3 / §7.4 / §7.5
  - 【验收判据】✅ 门禁可跑（真连 PG，vitest 40/40 全绿）：运行时分母（7182 项）+ 8 断言（⑦ 已转硬断言）+ 豁免登记（复用 `gate_exemptions.exempted_keys()`）+ 幂等三条（子进程 `PYTHONIOENCODING=utf-8` + 断言 stdout 标记、分母 JSON 无绝对路径/机器名、`--check` 漂移 exit 2 不用 `--write`+diff）+ 四变异 + surfaced 变异各命中对应子断言且配反向断言。门禁本身幂等（枚举器两次 `--write` 字节一致、`generated_at` 指纹不变则沿用）、不恒红（三态退出码正交）。
  - 【待办 ID】P2-spec 归档 100%≠可靠（配套门禁）

- [x] 8.2* ≥7 套 local formula dialog/drawer 收敛或明确分工登记（需求 20.1）
  - 枚举 ≥7 套局部公式弹窗/抽屉，逐个登记「组件路径 + 当前权威源 + 去留决策（收敛进中央弹窗 / 保留但标注分工边界 / 废弃）」；能收敛者走 `createOpenFormulaManagerCommand`，保留者写明不收敛理由（权威源不同 / UX 专用）。禁「按钮同名、能力/权威源不同」的隐性碎片化。
  - **决策边界**：ROI 不足或须大规模重构者，本轮仅登记 + 标注分工边界，大重构另立 spec（`*` 条件处置，不默默丢正式需求）。
  - 【需求】需求 20.1
  - 【design 锚点】§5 步骤 8 · 20.1
  - 【验收判据】产出 ≥7 套登记表（路径 + 权威源 + 去留决策）；收敛项走统一命令、保留项有理由。文档化为主。
  - 【待办 ID】P2-局部 dialog 碎片化

- [x] 8.3 两条历史假红/脆化前端测试修为反映真实行为 + 变异反证（需求 20.2）
  - `FormulaManagerPageWiring`（竞态脆化：改为按序消费或显式等待对应请求）与 `formulaStatusPanelDisplay`（历史假红：更新期望为「HTML 面板已有入口按钮」）各修为反映当前真实行为（**非放宽断言蒙绿、非删测试**），各配变异反证（注入对应真实缺陷仍能打红），避免恒绿。
  - 【需求】需求 20.2
  - 【design 锚点】§5 步骤 8 · 20.2
  - 【验收判据】两测试修为反映真实行为并通过；各配变异（注入对应真实缺陷打红）+ 反向断言（真实态通过）。
  - 【待办 ID】P2-spec 归档 100%≠可靠

- [x] 8.4* formula_push 套件 warnings 收敛（定位 `Connection._cancel` 根因）（需求 20.3）——**本轮：定位完成 + 条件处置（`*` 边界，仅登记真实根因与处置方向，禁掩盖）**
  - 定位 `Connection._cancel was never awaited` 根因（异步连接取消未 await），在测试 fixture / 连接管理处补 await 或改同步关闭；验收 = 套件 warnings 显著下降且无新增失败；**不以 `-W ignore` 掩盖**。
  - **决策边界**：若环境受限或根因须另立 spec，本轮仅定位 + 登记根因与处置方向（`*` 条件处置）。
  - 【需求】需求 20.3
  - 【design 锚点】§5 步骤 8 · 20.3
  - 【验收判据】定位根因 + 处置后 warnings 显著下降、无新增失败；不以 `-W ignore` 掩盖。
  - 【待办 ID】P2-门禁告警噪声

  **实施记录（2026-10-18，现算，禁写死；HEAD `67c3bcc5a`，PG 可达 postgresql+asyncpg）：**
  - **现算基线（before，干净 HEAD 全量 `test_formula_push*.py` 44 文件一次跑完，`-p no:cacheprovider`）**：**3464 warnings** / 20 failed / 1212 passed。撰写期「1164」快照已过期（随 batch 系列后续新增测试，噪声基数上升；本轮一律按现算值，不引用 1164）。
  - 🔴 **关键定位：任务前提被证伪——`Connection._cancel` 不是 warnings 主因。** 用 pytest 原生 `pytest_warning_recorded` hook 做类别直方图（一次性探针，已删），3464 条按类别拆分：
    - `DeprecationWarning: The default datetime adapter is deprecated as of Python 3.12` = **3454（99.7%）**
    - `RuntimeWarning: coroutine 'Connection._cancel' was never awaited` = **7**
    - `PydanticDeprecatedSince20`（class-based config）= 2 · `jsonschema RefResolutionError` = 1
  - **`Connection._cancel`（7 次）真实根因**：`test_formula_push_{engine_pg, k1_d4_canary_pg, k2_canary_pg}.py` 三个真 PG 场景用全局生产引擎 `from app.core.database import engine`（asyncpg `pool_size=20/overflow=80` 池）在**每用例各自的 `asyncio.run()` 事件循环**内 `engine.begin()/connect()` 检出池连接，**结束不 `engine.dispose()`**。循环关闭后池连接残留在已关闭循环上，GC 调度其 `Connection._cancel` 协程却无法 await ⇒ RuntimeWarning。同目录 `schema_pg / note_skip_pg / triggers / schema_contract` 已 `await engine.dispose()`（正确口径对照）。
  - **「3454 datetime adapter」真实根因（真正的噪声主体）**：Python 3.12 `sqlite3` 废弃内置 datetime 适配器；`tests/conftest.py` 与 `_formula_push_env.make_env` 的内存 SQLite 未注册 `sqlite3.register_adapter(datetime, ...)`，ORM 时间列（`FormulaPushRun.started_at` / `DisclosureNote`/`Project` 时间戳等）每绑定一个 `datetime` 值即触发一次。**与异步连接取消无关，补 await 无法减少一条。**
  - **试过的处置 + 为何回退（诚实暴露，非绕开）**：给三个 pg 文件 `finally` 补 `await engine.dispose()`（对齐同目录正确口径）后全量复测 = **3462 warnings / 19 failed**。①总量仅降 2（3464→3462），**达不到「显著下降」**（因主体是 datetime adapter，与此无关）；②**引入新失败**：`test_formula_push_schema_pg::test_v169_on_real_postgres` 转 `AttributeError: 'NoneType' object has no attribute 'send'`（Windows ProactorEventLoop 传输层在 `asyncio.run` 跨循环复用**共享全局池** dispose 后的拆除竞态）——违反「无新增失败」。三个 pg 真库用例（`k1_d4_canary` / `note_skip_pg` / `schema_pg`）本就随 dispose 时序**互相换位 flaky**，是「跨多个 `asyncio.run` 循环共享全局池」这一架构脆弱性的两面（`_cancel` warning 与 `.send` 失败同源）。⇒ **已 `git checkout` 回退这三处编辑**，不留净负改动；**未动任何其他任务的未提交改动**，未删任何测试，未加 `-W ignore`。
  - **条件处置结论（`*` 边界，依 design §5 步骤 8 P2 声明）**：本轮**仅定位 + 登记**，不实施。理由：①「显著下降」要求命中 datetime-adapter（99.7%），其修复 = 在 `conftest.py` 全局 `sqlite3.register_adapter`/`register_converter`，**影响面是整个 backend SQLite 测试基座**，远超 formula_push，须另立 spec（带全量回归 + 变异反证：注入一个写 datetime 的 SQLite 用例应仍 0 该告警）；②`Connection._cancel` 的「补 dispose」在 Windows 共享全局池下引入新失败，正确处置是**让这三个 pg 场景各自用独立 `create_async_engine` + 末尾 dispose**（不共享生产全局池），属测试脚手架改造，同样建议并入上述 spec 一并做。两条均不以 `-W ignore` 掩盖。
  - **后续 spec 处置方向（供另立 spec 承接，待办 P2-门禁告警噪声）**：
    1. `conftest.py` 注册 Py3.12 兼容的 `sqlite3` datetime 适配器/转换器（消除 ~3454 条，warnings 预计降至个位数～两位数）。
    2. 三个 pg 场景（`engine_pg`/`k1_d4_canary_pg`/`k2_canary_pg`）改用**独立引擎**（`create_async_engine(DATABASE_URL)` 局部实例，末尾 `await engine.dispose()`），不复用 `app.core.database.engine` 全局池 ⇒ 消除 `Connection._cancel` 且解除三 pg 用例跨循环 flaky。
    3. 变异反证：注入一个绑定 `datetime` 的 SQLite 用例 + 一个共享全局池的 pg 用例，分别断言「0 datetime-adapter 告警」「0 `_cancel` 告警」，防恒绿。
  - **验收如实**：本轮**未**达成「warnings 显著下降」（主因在 formula_push 范围外、且 `_cancel` 补丁引入新失败），按 `*` 条件项**仅完成定位 + 根因登记 + 处置方向**；工作树已复原（三处编辑回退、探针全删），无新增失败、无掩盖。

- [x] 8.5 RTK 吞失败退出码修正（复用 §7.4③ 口径）（需求 20.4）
  - 门禁子进程断言 stdout/stderr 含预期内容（非仅看 returncode），对 RTK 包装命令显式校验内层退出码或输出标志。
  - 【需求】需求 20.4
  - 【design 锚点】§5 步骤 8 · 20.4、§7.4③
  - 【验收判据】变异：内层命令失败而 RTK 返 exit 0 时门禁应打红；反向断言内层成功时通过。断言 stdout 内容（非仅 returncode）。
  - 【待办 ID】P2-门禁告警噪声

---

## 覆盖自检

### 20 条需求 → 任务承接
| 需求 | 承接任务 |
|---|---|
| 需求 1 串页精确匹配 | 1.2、1.3、3.1、8.1(⑤a) |
| 需求 2 surfaced 只读+upsert+字段名 | 1.4、1.5、8.1(⑤b/⑤c) |
| 需求 3 统一入口/删 node-only/补 A1·Univer | 2.1、2.2、2.3、8.1(①②③) |
| 需求 4 附注用户公式可执行 | 4.1 |
| 需求 5 坐实并整改项目隔离 | 5.1、5.2、5.3、5.4、5.5* |
| 需求 6 左栏当前页地址 | 3.1、3.2、8.1(④) |
| 需求 7 表间审核契约 | 6.1、6.2 |
| 需求 8 函数支持矩阵禁静默 0 | 4.2 |
| 需求 9 A1/Univer 入口 + 404 归类 | 2.1、2.3 |
| 需求 10 缓存隔离/单行 stale/项目年 | 6.3、6.4 |
| 需求 11 最小数据运行坐实空数据 | 7.1、6.4(run_id) |
| 需求 12 全量门禁 8 断言+幂等 | 8.1 |
| 需求 13 底稿 wp 收敛 | 1.2、1.4、4.2、5.2、5.4 |
| 需求 14 附注 note 收敛（不动鉴权） | 4.1 |
| 需求 15 报表 report 口径与鉴权 | 4.3、5.3 |
| 需求 16 试算表 tb 鉴权与传播 | 5.2、5.5* |
| 需求 17 合并报表先诊断后决策 | 7.2、7.3 |
| 需求 18 合并附注先诊断后决策 | 7.2、7.3 |
| 需求 19 合并底稿先诊断后决策 | 7.2、7.3 |
| 需求 20 碎片化/spec 状态/门禁噪声 | 8.2*、8.3、8.4*、8.5 |

**结论：20 条需求全部有任务承接，无遗漏。**

### design §5 八步 → Phase 对齐
| design §5 步骤 | Phase | 任务 |
|---|---|---|
| 步骤 1 P0 止错 | Phase 1 | 1.1（前置 grep）、1.2、1.3、1.4、1.5 |
| 步骤 2 统一入口 + 404 归类 | Phase 2 | 2.1、2.2、2.3 |
| 步骤 3 左右栏契约 | Phase 3 | 3.1、3.2 |
| 步骤 4 权威源与执行语义 | Phase 4 | 4.1、4.2、4.3 |
| 步骤 5 项目鉴权与原子性 | Phase 5 | 5.1、5.2、5.3、5.4、5.5* |
| 步骤 6 执行/传播可观测性 | Phase 6 | 6.1、6.2、6.3、6.4 |
| 步骤 7 最小数据运行 | Phase 7 | 7.1、7.2、7.3 |
| 步骤 8 P2 治理 + 全量门禁 | Phase 8 | 8.1、8.2*、8.3、8.4*、8.5 |

**结论：八步全对齐，Phase 顺序不改。**

### design §7 全量门禁 → 任务
- §7.1 运行时权威分母、§7.2 八断言（含⑤拆 ⑤a/⑤b/⑤c、⑦ pending）、§7.3 豁免、§7.4 幂等三条、§7.5 四变异 + surfaced 变异 → **全部由 Task 8.1 承接**。
- 断言⑦ pending 前置 = Phase 5 全部对象型端点加固 + Task 5.1 §6.1 坐实。
- 变异映射：⑤a→Task 1.2、⑤b→Task 1.4、⑤c→Task 1.4+1.5、①/③→Task 2.1。

**结论：§7 门禁全要素（8 断言含⑤a/⑤b/⑤c 与⑦ pending、四变异含 surfaced 变异、幂等三条）均有任务承接。**

### 报告第十三节 14 条待办 → 任务
| 待办 ID | 承接任务 |
|---|---|
| FM-P0-01 当前 sheet 串页 | 1.2、1.3、3.1 |
| FM-P0-02 surfaced 假可编辑+错保存域 | 1.4、1.5 |
| FM-P0-03 多入口丢上下文 | 2.1、2.2、2.3 |
| FM-P0-04 附注用户公式保存后不执行 | 4.1 |
| FM-P0-05 项目隔离缺失 | 5.1、5.2、5.3、5.4、5.5*（+报表侧 4.3、5.3） |
| P1-左栏非当前页地址 | 3.1、3.2 |
| P1-表间审核契约错 | 6.1、6.2 |
| P1-函数按钮/运行不一致 | 4.2 |
| P1-A1/Univer 无入口 | 2.1、2.3 |
| P1-缓存未隔离/传播 | 6.3、6.4、5.2(tb-detail) |
| P1-正式运行数据为空 | 7.1 |
| P2-局部 dialog 碎片化 | 8.2* |
| P2-spec 归档 100%≠可靠 | 8.3、8.1（门禁配套） |
| P2-门禁告警噪声 | 8.4*、8.5 |
| 三 consol 子节统一（12.5/12.6/12.7） | 7.2、7.3 |

**结论：14 条待办 + 三 consol 子节全部有任务承接，无遗漏。**

### 其他硬约束核对
- design §10 实施前重做 §1 全部 20 条现状 grep → **Task 1.1（Phase 1 首任务、强制前置）**。✅
- FM-P0-05「先 §6.1 TestClient 坐实再加固」→ **Task 5.1（前置·先坐实）** 为 Phase 5 加固任务与门禁⑦的硬前置。✅
- Phase 7 合并三类「先诊断后决策」两段式 → Task 7.2（诊断·禁改代码）+ Task 7.3（决策），措辞禁「重写/重建合并链」。✅
- 附注鉴权不纳入整改（ADR-FMC-07）→ Task 4.1、5.2 显式「不动附注端点」。✅
- tb_detail `FORMULA_CONFIG_CHANGED` 条件项不实施 → **Task 5.5\*** `*` 标记 + 记录「本轮不实施 + 触发条件」边界。✅
- P2 可用 `*` 标记条件项并记录决策边界 → Task 5.5\*、8.2\*、8.4\* 已标并写边界。✅
