# 需求文档：公式管理平台缺陷闭环（formula-manager-closure）

> 关联设计：#[[file:.kiro/specs/formula-manager-closure/design.md]]
> 唯一权威输入：`docs/proposals/formula-management-platform-audit-2026-10-17.md`（全面审计报告，HEAD `84def65b`，复核更正绑定 HEAD `e5ee550f`）。
> 工作流：Design-First。EARS 风格（WHEN … THEN … SHALL / IF … THEN … SHALL）。
> 类型：bugfix + 接线收敛 + 安全加固 + 可观测性闭合 + 诊断（**非新功能**；本 spec 本轮只产出三件套文档，不实施生产代码）。

## 引言（Introduction）

用户的原始诉求是确认「公式管理平台」是否真正打通——不同底稿之间取数勾稽、单底稿内部计算校对、wp/TB/报表/附注/aux/合并等跨模块链路、每个可访问底稿页面是否都有可用的「公式管理」入口、点击后能否正常弹窗、左栏是否严格是当前页地址、右栏是否严格是当前页公式——并据审计报告中的问题与建议生成 spec 来解决。

审计报告的总判断是：平台已有丰富的公式「零件」（公式语法、报表求值、静态依赖图、ACNR、stale、formula_push、合并公式），但「公式管理中心 = 每页统一入口 + 当前页精确地址 + 当前页权威公式 + 可验证执行/校对 + 安全保存/传播」的产品闭环**尚未形成**，不能据四个已归档 100% 的 spec 宣称「全部打通」。

本 spec 承接报告第九节（P0/P1/P2 缺口与根因）、第十节（最小闭环整改七步 + 验收标准 + 建议全量门禁）、第十二节（分模块深化 12.1~12.7）、第十三节（14 条待办追踪表），把每一类缺陷转写为可追溯、可验收的需求。报告中凡标注「复核发现（HEAD e5ee550f）」的加注为权威现状更正，优先采信。

### 一条贯穿全文的证据纪律

报告第一节 C2 校准确立了关键口径：一批 **DB 计数 = 0**（附注 `_formulas/_user_formulas`、`formula_push_run/state`、`consol_note_formula/consol_push_run`、`cross_check_results`、`formula_runtime_outbox` 等）**有双重可能**——(a) 链路已断裂（须补/改代码，成本高）；(b) 链路已接线但从未被真实使用（只差一次数据运行即可点亮，成本低）。本报告据当前证据只能判「**未证明打通**」，**不**据 count=0 直接断为「已断裂」。因此本 spec 的需求措辞必须严格区分「已证实的缺陷（源码/运行时坐实）」与「未证明、须先诊断再决策」两类，**禁止把 count=0 直接写成「重写 / 重建链路」**。

### 范围内（In Scope）

- 修复已运行时/源码坐实的 P0：当前 sheet 串页（FM-P0-01）、surfaced 假可编辑 + 错保存域（FM-P0-02）、多入口丢上下文（FM-P0-03）、附注用户公式保存后不执行（FM-P0-04）。
- 坐实并整改 FM-P0-05（项目隔离缺失，静态高危待动态坐实）——以一条 TestClient 跨项目越权用例坐实后再据结果加固。
- 整改主要 P1：左栏非当前页地址、表间审核契约错、函数按钮支持与运行支持不一致、A1/Univer 无入口（含 10 个 classification 404 的一次性归类）、缓存未按项目隔离 + 保存用错年份、正式运行数据为空。
- 建立建议的全量自动门禁 `formula-manager-all-accessible-pages.spec.ts`（8 条断言 + 幂等输出）。
- 七类模块深化（12.1 底稿 / 12.2 附注 / 12.3 报表 / 12.4 试算表 / 12.5 合并报表 / 12.6 合并附注 / 12.7 合并底稿）的可落地优化，其中合并三类先做「最小数据运行」诊断再决策。

### 范围外（Out of Scope，明确不做）

- **不重写 / 不重建合并链路（consolidation report/note/wp）**。报告明确三个 consol 子节真库 count=0 是「数据阻塞 ≠ 断链」，当前证据只能判「未证明」；本 spec 只要求先做一次最小数据运行诊断，再据结果决定是否改代码。
- **不把附注公式三端点（`apply/list/upsert`）列为待修鉴权项**。报告复核发现（HEAD e5ee550f）：三端点均已挂 `require_project_access`，附注层项目隔离与审计留痕是健全的，**不在鉴权缺陷列内**。
- 不改 `report_config` 作为全局模板表（无 `project_id` 列、按 `applicable_standard` 的 4 标准区分）的既有范式；只补鉴权与口径文案。
- 不新增「公式语法 / 求值内核（L1 AST + 白名单）」能力；现有安全求值基线复用。
- 不在本轮实施任何生产代码、不启动/重启服务、不写业务数据——本轮交付物仅为 requirements/design/tasks 三件套文档。

## 术语（Glossary）

| 术语 | 含义 |
|------|------|
| FM-P0-0x | 报告第九节 P0 缺陷编号（01~05） |
| 当前页串页 | 右栏模糊包含匹配把 `E1-1` 命中 `E1-10/E1-14`、`D2-1` 命中 `D2-10/D2-12` |
| surfaced | 后端 `wp_formula.py:_build_surfaced_formulas` 组装的**只读投影**（逐条 `readonly:true`），非权威定义 |
| extraction | D/F 四表提取块（Tier A/B），仅 D 循环 + 灰度开关开启时出现 |
| stable_sheet_key / sheet_uid | 结构化 sheet 身份键，用于精确等值匹配，替代模糊 `includes` |
| CanonicalWorkpaperLocation | 统一入口提交的完整上下文（projectId/wpId/wpCode/sheetUid/…） |
| canonical command | `createOpenFormulaManagerCommand` / `decideSaveDraft` 等已设计好但生产零调用的命令 |
| node-only 入口 | E1 / D4-33~36 仅发 `nodeKey`、丢失实例/项目/sheet 的旁路按钮 |
| 最小数据运行 | 在未删除的 standalone 与 consolidated 项目各造一套隔离公式，触发执行/推送，逐值对拍权威表并观察 run/state/outbox 是否落库 |
| require_project_access | 平台项目级鉴权依赖（readonly/edit），区别于仅 `get_current_user` 或仅角色门控 |
| IDOR | 不安全直接对象引用（知道对象 id 即可跨项目读/写/执行） |
| 现算值 | 交付时由脚本重新统计得出的计数，**禁写死进判据**（沿用报告附录脚本 `fm_audit_db_snapshot.py`） |

---

## 分组 P0：阻断「平台核心闭环」宣称的缺陷

### 需求 1：消除当前 sheet 串页，右栏按结构化 sheet 身份精确匹配

> 对应 FM-P0-01 / 整改步骤 1、3 / 第十三节待办「FM-P0-01 当前 sheet 串页」/ 深化 12.1 优化①。

**用户故事**：作为审计助理，我希望在 D2-1 / E1-1 底稿页打开公式管理时，右栏只显示本页公式，而不是被模糊匹配混入 D2-10/D2-12 或 E1-10/E1-14/E1-15 的公式，以免误把别页公式当成本页去编辑或执行。

**现状证据**：前端 `matchSheetCode` 为 `a===b || a.includes(b) || b.includes(a)`（模糊包含），运行时观察到 D2-1 显示「本页公式18」实际混入 D2-10×4、D2-12×3；E1-1 显示「本页公式28」混入 E1-10/E1-14/E1-15（报告第五、六节，源码 + 运行时坐实）。

### 验收标准

1. WHEN 右栏为某 `sheet_uid` 聚合公式 THEN 匹配 SHALL 用 `wp_formula.stable_sheet_key`（列已存在）做**精确等值**，SHALL NOT 使用 `includes` 子串包含。
2. WHEN 打开 D2-1 THEN 右栏 SHALL NOT 含任何 `D2-10` / `D2-12` 来源的公式行；WHEN 打开 E1-1 THEN 右栏 SHALL NOT 含任何 `E1-10` / `E1-14` / `E1-15` 来源的公式行。
3. THE 验收 SHALL 以报告列出的前缀反例（`E1-1` vs `E1-10/14/15`、`D2-1` vs `D2-10/12`）逐一构造，每个反例都 SHALL 判定为不串页。
4. IF 某公式行缺少可解析的结构化 sheet 身份 THEN 右栏 SHALL 以 fail-closed 方式排除该行（不得因无法判定而退回模糊匹配）。

---

### 需求 2：surfaced/extraction 投影强制只读，工作底稿保存走 wpFormula.upsert

> 对应 FM-P0-02 / 整改步骤 1、4 / 第十三节待办「FM-P0-02 surfaced 假可编辑 + 错保存域」/ 深化 12.1 优化②③。

**用户故事**：作为审计助理，我不希望把说明性的 surfaced 投影当成可编辑的正式公式去「编辑 / 保存」，更不希望保存时把一个伪 id（如 `E1-surfaced-tb-check`）发到 report-config 端点污染报表模板，以免把文档化元数据误当权威公式、把本页编辑写错库。

**现状证据**：后端 `wp_formula.py` 对 `E1-surfaced-*` / `{base}-surfaced-*` / Tier B 溯源条目**逐条硬标 `readonly:true`**（已核验，不随 HEAD 漂移）。复核收窄（HEAD e5ee550f）：现存缺陷为两点——(a) surfaced 可被点开编辑而其后端语义是只读；(b) 任何「有 id 的非报表行」保存时**无 kind 校验**即发 report-config detail 端点。中央仍把说明元数据包装成「健康度100%/自定义」。

### 验收标准

1. THE surfaced 与 extraction 投影在前端 SHALL 被渲染为只读：其点击区 SHALL NOT 出现「编辑」按钮，SHALL NOT 显示「自定义」「健康度100%」等将说明元数据包装成正式公式的标签。
2. WHEN 用户对工作底稿行执行保存 THEN SHALL 调用 `wpFormula.upsert`（`PUT /api/workpapers/{wp_id}/formulas`），SHALL NOT 把工作底稿公式写入 `report_config`。
3. IF 保存一个「有 id 的非报表行」 THEN 保存链 SHALL 先按行的 kind 校验目标端点，SHALL NOT 在未校验 kind 的情况下把该 id 发往 report-config detail 端点。
4. WHEN 前端读取后端返回的工作底稿公式字段 THEN SHALL 正确读取 `category` / `description`，SHALL NOT 错读成 `formula_category` / `formula_description`。
5. THE 配套变异（把 save 改回写 `report_config`）SHALL 被门禁用例捕获为失败（见需求 12）。

---

### 需求 3：统一入口，消除 node-only 旁路并补齐 A1/Univer

> 对应 FM-P0-03 / 整改步骤 2 / 第十三节待办「FM-P0-03 多入口丢上下文」「P1-A1/Univer 无入口」。

**用户故事**：作为审计助理，我希望每个底稿页面的「公式管理」按钮都提交完整当前页上下文（项目/实例/sheet），而不是有的按钮只发一个 `nodeKey` 把我带进错误作用域（如 E1 页内第二按钮实测落 `report` scope 并产生两个 422），以便任意入口打开的都是本页的公式管理。

**现状证据**：E1 与 D4-33~36 子组件入口仅发 `nodeKey`（`GtE1MonetaryFund.vue:280-287`、`D4TabOther*.vue`），丢失实例/项目/sheet；设计好的 `createOpenFormulaManagerCommand` / capability / dirty-pin **生产零调用**（仅测试调用）。A1（`a1-dashboard`）自管工具栏无公式入口；Univer 主路径工具栏只有「同步公式」无 FormulaManager 入口（报告第四、五、六节）。

### 验收标准

1. THE 生产代码 SHALL 真正调用 `createOpenFormulaManagerCommand`，所有公共与局部按钮打开公式管理时 SHALL 只提交一个 `CanonicalWorkpaperLocation`（含 projectId/wpId/wpCode/sheetUid 等完整上下文）。
2. THE E1 页内第二按钮与 D4-33~36 的 node-only 旁路 SHALL 被删除或改为提交完整 location；WHEN 从这些入口打开 THEN scope 标签 SHALL 与面包屑一致（底稿入口不得落入 `report` scope），且 SHALL NOT 产生 `/report-config/types` 或缺 year 的 422。
3. THE A1（`a1-dashboard`）与 Univer 主路径 SHALL 补同一 primary outlet 的公式管理入口。
4. THE `redirect-materiality`（B15）SHALL 登记为带 owner/reason/expires_at 的正式豁免。
5. WHEN 枚举 220 个声明 componentType THEN 每一项 SHALL 恰有「当前页入口覆盖」或「带期限的正式豁免」，SHALL NOT 存在未知未覆盖项。

---

### 需求 4：附注用户公式保存后可被执行（权威源二选一收敛）

> 对应 FM-P0-04 / 整改步骤 4 / 第十三节待办「FM-P0-04 附注用户公式保存后不执行」/ 深化 12.2 优化①②。

**用户故事**：作为审计助理，我希望在附注里保存的自定义公式真的会被「应用/执行」，而不是保存到 `_user_formulas` 后 apply 却只执行模板预设 `_formulas/check_presets`、导致我在中央弹窗里看不到也跑不了自己的公式。

**现状证据**：附注公式双存储于 `disclosure_notes.table_data`——`apply_formulas` 只读 `_formulas/check_presets`（`note_formula_generator.py`），而 `upsert_note_formulas` 写 `_user_formulas`；两者互不可见，中央 `FormulaManagerDialog` 甚至不读 `_user_formulas`。真库三键全 0（源码 + DB 坐实）。

### 验收标准

1. THE 附注公式权威源 SHALL 二选一收敛：**要么** `execute_note_formulas` 同时消费 `_user_formulas`（用户公式真执行）；**要么**取消 `_user_formulas` 可编辑、统一回「模板预设 + 项目级覆盖」。design 阶段 SHALL 在两方案中明确选定一个并给出理由。
2. IF 选定「apply 消费 `_user_formulas`」 THEN WHEN 用户保存附注公式后触发 apply THEN 该用户公式 SHALL 被执行并回填目标单元格。
3. THE 中央 `FormulaManagerDialog` 的附注节点 SHALL 调用 `list_note_formulas`（含用户集），SHALL NOT 仅只读模板预设——即「保存后弹窗能看到自己的公式」。
4. THE 附注公式三端点（`apply/list/upsert`）的既有 `require_project_access` 鉴权 SHALL 保持不变（本 spec 不动附注鉴权）。

---

### 需求 5：坐实并整改项目隔离缺失（跨项目越权 403 且 0 副作用）

> 对应 FM-P0-05 / 整改步骤 5 / 第十三节待办「FM-P0-05 项目隔离缺失」/ 深化 12.1 优化④、12.3、12.4 优化 / 建议门禁第⑦条。

**用户故事**：作为平台安全负责人，我希望任何登录用户都无法凭 `wp_id` / config UUID / body 里的 `project_id` 去读、写或执行别的项目的公式，以免发生跨项目越权（IDOR）。

**定级依据与张力（须显式声明）**：FM-P0-05 定为 P0 是基于**静态读码**（`wp_formula`/`report_config`/`execute`/`formula-scope`/`linkage`/`legacy address`/`tb_detail` 等端点仅 `get_current_user` 或仅角色门控）与平台**已有 IDOR 先例**（`t_accounts`/`formula_audit_log` 同型越权）的**高置信推断**；但本轮**未执行任何跨项目越权读/写/执行探测**。因此本条严格表述为「**静态高危、待一条 TestClient 跨项目用例坐实**」，而非「已复现的事故」。在坐实前，本条是「必须优先验证的高危假设」。

### 验收标准

1. THE 坐实手段 SHALL 为一条 TestClient 跨项目越权用例：以属于项目 A 的凭据，对项目 B 的 `wp_formula` 读/写、`report_config` 更新、`/api/formula/execute`、`formula-scope/{project_id}`、`tb_detail` 公式读/写分别发起请求。
2. WHEN 该跨项目用例运行 THEN 读、写、执行请求 SHALL 全部返回 403，且 SHALL 产生 0 副作用（目标项目数据无变更）。
3. THE 对象型端点（路径只有 `{wp_id}`）SHALL 先按 id 最小反查 `project_id`，再 `require_project_access("edit"/"readonly")`；body/query 里的 `project_id` 同样 SHALL 校验。
4. THE 全局模板（`report_config`）与全局自定义函数的写/删/注册操作 SHALL 限 admin。
5. THE `tb_detail` 公式读端点（当前仅 `get_current_user`，IDOR）SHALL 补项目级 `require_project_access`；写端（当前仅 `require_role` 角色门控）SHALL 在角色之外叠加项目归属校验。
6. THE 直接 `wp_formula` CRUD SHALL 写 `append_audit_log` 哈希审计链。
7. THE 附注公式端点 SHALL NOT 被纳入本需求整改范围（复核发现已挂 `require_project_access`）。
8. IF 坐实用例意外显示某端点已安全（现状已隔离）THEN SHALL 据运行时结果更新定级并在 design 记录，SHALL NOT 继续按「已越权」处置。

---

## 分组 P1：主流程可用但结果/覆盖不可信的缺陷

### 需求 6：左栏严格显示当前页地址坐标

> 对应 P1「左栏非当前页地址」/ 整改步骤 3 / 第十三节待办「P1-左栏非当前页地址」。

**用户故事**：作为审计助理，我希望公式管理左栏只列出当前 sheet 的地址坐标（anchors），而不是一棵包含 TB/report/note/wp/合并/表间审核/数据质量的全局树，以便左右栏始终对应同一个当前页。

**现状证据**：左栏标题「数据源」，调用 `/api/acnr/entries` 构建全局树，**根本不调用当前 sheet 的 `listCells`/`anchors`**（报告第二、五、六节，源码 + 运行时坐实）。

### 验收标准

1. THE 左栏 SHALL 调用当前 sheet 的 anchors/listCells 接口（`GET addresses?project_id&wp_id&sheet_uid` 或等价），SHALL 只显示属于精确当前 sheet 的 `addr_id`。
2. THE 左右栏返回的每一行 SHALL 带同一个 location identity（projectId/wpId/sheetUid）。
3. IF 当前页 location identity 缺失 THEN 左栏 SHALL fail-closed（显式告警 + 空集），SHALL NOT 退回展示全局树。
4. THE「全局浏览」SHALL 作为独立显式按钮提供，SHALL NOT 作为缺上下文时的默认回退。

---

### 需求 7：修复表间审核契约

> 对应 P1「表间审核契约错」/ 整改步骤 6 / 第十三节待办「P1-表间审核契约错」。

**用户故事**：作为审计助理，我希望表间审核能真正返回执行结果并把我新增/编辑的规则落库，而不是每次 GET 因缺 year 恒 422 退回静态示例、新增规则一关闭就丢。

**现状证据**：表间审核 GET 缺 `year` 恒 422（后端强制 year，前端未传）；响应本是执行结果却被按「规则列表」解析；失败后展示静态示例；新增/编辑规则只改内存关闭即丢；树父/叶 key 与规则 map 不一致（报告第五、六节）。

### 验收标准

1. WHEN 前端请求表间审核 THEN SHALL 携带 `year`，GET SHALL NOT 再因缺 year 返回 422。
2. THE 前端 SHALL 按「执行结果」解析响应，SHALL NOT 按「规则列表」误解析。
3. WHEN 新增或编辑表间审核规则 THEN SHALL 落库持久化，关闭弹窗后再打开 SHALL 仍可见；SHALL NOT 仅改内存。
4. THE 树的父/叶 key SHALL 与规则 map 的 key 一致。
5. IF 执行结果为空 THEN SHALL 显式呈现「无结果」，SHALL NOT 用静态示例冒充执行结果。

---

### 需求 8：公式函数「按钮支持」与「运行支持」一致，禁静默 0

> 对应 P1「函数按钮支持与运行支持不一致」/ 整改步骤 4 / 第十三节待办「P1-函数按钮/运行不一致」/ 深化 12.1 优化、12.3。

**用户故事**：作为审计助理，我希望 UI 里能点的每个函数（NOTE/REPORT/ROW/AUX/PREV/ADJ 等）在当前执行器里都能真正运行或被明确标为「此处不支持」，而不是点了之后被静默阻断或返回 0。

**现状证据**：workpaper UI 提供 NOTE/REPORT/ROW/AUX/PREV/ADJ，实际多数阻断或空 ctx→0；report 路径明确把 PREV/AUX 替换为 0；中央 batch 未注入 ADJ 实时数据（报告第三、五、九节，源码坐实）。

### 验收标准

1. THE 每个函数 SHALL 按执行器维护一张「支持矩阵」（函数 × 执行器 → 支持/不支持）。
2. IF 某函数在当前执行器不支持 THEN UI SHALL 显式标注不支持或禁用该函数，SHALL NOT 允许点击后静默返回 0。
3. WHEN 函数在当前执行器支持 THEN 运行 SHALL 产生真实结果，SHALL NOT 以空 ctx 静默回退为 0。
4. THE 支持矩阵 SHALL 覆盖 wp evaluator（真支持 TB/SUM_TB/WP）、report 路径（PREV/AUX 被置 0）、note 执行器、以及中央 batch（ADJ 实时数据注入）。

---

### 需求 9：A1/Univer 入口补齐与 classification 404 的一次性归类

> 对应 P1「A1/Univer 无入口」+「10 个 classification 404 未判定」/ 整改步骤 2 / 第四节待办「classification 404 可进一步拆分」。

**用户故事**：作为审计助理，我希望 A1 看板页和 Univer 编辑页也有统一的公式管理入口，并希望真实项目里那 10 个 classification 404 的底稿被明确归类（可修的数据漂移 vs 口径外的未建模底稿），而不是长期悬在「无法判定」。

**现状证据**：A1 自管 toolbar 无入口、Univer 只有「同步公式」；医疗器械真实项目 208 底稿里 10 个 classification API 返 404 未逐一判定（报告第四节已给出区分法：有 override 映射却 404 = 数据漂移可修；本就无映射 = 口径外）。

### 验收标准

1. THE A1 与 Univer SHALL 补同需求 3 所述的统一 primary outlet 公式管理入口（本需求与需求 3 第 3 条合并实现，不重复计覆盖）。
2. THE 10 个 classification 404 的 wp_code SHALL 各查一次 `wp_code_overrides.json` 映射完成一次性归类：有映射 → 判「数据漂移」（应落 override 或补 classification 行）；无映射 → 判「口径外」（不计入按钮分母）。
3. WHEN 归类完成 THEN 第四节「无法判定」子类 SHALL 被解除，每个 404 wp_code SHALL 有明确归属。
4. IF 判为「数据漂移」 THEN SHALL 记录修复动作（补映射或补 classification 行）；IF 判为「口径外」 THEN SHALL 从按钮覆盖分母中剔除并记录理由。

---

### 需求 10：项目缓存隔离、单行保存触发统一 stale、保存使用项目年份

> 对应 P1「缓存未按项目隔离 + 保存全部用错年份」/ 整改步骤 6 / 第十三节待办「P1-缓存未隔离/传播」/ 深化 12.4 优化。

**用户故事**：作为审计助理，我希望切换项目后公式管理不残留上一个项目的陈旧上下文，单行保存也能触发统一 stale 传播，且保存用的是项目所属年份而不是系统当前年，以免数据跨项目串、传播漏触发、年份写错。

**现状证据**：`report/note/cross-check` cache 未按 project key（`noteTreeLoaded/reportTypesLoaded/crossCheckLoaded` 切项目不清）；中央「保存全部」用系统当前年而非 `props.year`；单行保存不走统一 stale 调用；真库 `formula_runtime_outbox=0`（源码 + DB 坐实）。

### 验收标准

1. THE `report/note/cross-check` 等缓存 SHALL 按 project key 隔离；WHEN 切换项目 THEN 旧项目缓存 SHALL 失效，旧响应 SHALL NOT 覆盖新项目结果。
2. WHEN 执行「保存全部」或单行保存 THEN 所用年份 SHALL 取 `props.year`（项目年份），SHALL NOT 使用系统当前年。
3. WHEN 单行保存公式 THEN SHALL 触发与「保存全部」相同的统一 stale 传播调用。
4. THE 观察到的 ACNR GET abort 后重发场景 SHALL NOT 导致跨项目陈旧上下文污染。

---

### 需求 11：以最小数据运行坐实「正式运行数据为空」

> 对应 P1「正式运行数据为空」/ 整改步骤 7 / 第十三节待办「P1-正式运行数据为空」。

**用户故事**：作为质控复核人，我希望平台至少有一次端到端、逐值对拍过的真实公式运行记录，而不是所有 29 条 wp_formula 都属已软删项目、computed/refs/binding 全 0、push/cross-check/consol 运行表全 0。

**现状证据**：29 条 wp_formula 全属已软删项目「辽宁卫生服务」，0 computed/refs/source_scope/binding；活跃项目 wp_formula=0；`formula_push_run/state`、`cross_check_results`、`formula_runtime_outbox`、`consol_*` 运行表全 0（DB 坐实）。

### 验收标准

1. THE 坐实手段 SHALL 为一次最小数据运行：在未删除的 standalone 项目造一套隔离公式并保存、重开、执行。
2. WHEN 新公式保存后重开 THEN 右栏 SHALL 与保存内容一致。
3. WHEN 执行该公式 THEN 目标值 SHALL 改变，`last_computed_at` SHALL 更新。
4. WHEN 执行完成 THEN `stale` / `formula_runtime_outbox` / audit SHALL 均带同一个 `run_id`。
5. THE 验收 SHALL 以逐值对拍权威表为准，SHALL NOT 只看组件或 mock API。

---

## 分组 GATE：全量自动门禁

### 需求 12：建立 formula-manager-all-accessible-pages 全量门禁（8 条断言 + 幂等输出）

> 对应 第十节「建议新增的全量自动门禁」/ 整改步骤 2、3、5、6 / 第十三节待办「P2-spec 归档 100%≠可靠」「P2-门禁告警噪声」（配套治理）。

**用户故事**：作为质控复核人，我希望有一道自动门禁枚举全部可访问底稿页面并逐页核验公式管理入口与左右栏契约，且这道门禁本身是幂等、不会恒红的，以便分母任何新增或任一契约回退都能被自动拦住，而不是训练团队忽略它。

**现状证据**：现有 toolbar E2E 允许 `triggerCount>=0`、只数关闭态 dialog≤1，从未点按钮核左右栏（第八节盲区④）；且报告第十节明确要求幂等输出以避免「永红门禁」（memory 铁律㉗）。

### 验收标准

1. THE 门禁 SHALL 先通过项目 API 枚举全部可访问 `working_paper`，逐张 GET render-config 并展开「每个真实 sheet + whole_workbook + redirect」，形成运行时权威分母；每项 SHALL 记录 `project_id/wp_id/wp_code/sheet_uid/sheet_code/host/componentType`。
2. THE 每个非 redirect 项 SHALL 满足以下 8 条断言：
   - ① 恰好一个 `[data-testid=formula-manager-open]`；
   - ② 点击只出现一个中心弹窗；
   - ③ 抓包断言请求带完整 location；
   - ④ 左侧返回的 `addr_id` 全属于精确当前 sheet；
   - ⑤ 右侧每条 `stable_sheet_key` 精确相等，且 surfaced 只读；
   - ⑥ 切 sheet/项目后集合变化，且旧响应不能覆盖；
   - ⑦ admin/auditor/readonly 分别验证 view/edit 权限；
   - ⑧ 0 console error、0 当前请求 abort、0 4xx。
3. THE redirect / 不可渲染项 SHALL 用带 owner/reason/expires_at 的可伪证豁免登记。
4. THE 门禁 SHALL 输出 JSON 分母矩阵；WHEN 分母任何新增 THEN SHALL 自动变红。
5. THE 配套变异 SHALL 全部被指定测试命中：注入 `E1-10`（串页）、删除按钮、去掉 `wp_id`、把 save 改回写 `report_config`，四种 SHALL 各命中对应断言。
6. THE 门禁输出 SHALL 幂等（防永红）：
   - ① 分母 JSON 内容不变则不改时间戳、排序稳定、不含机器名/绝对路径；
   - ② 沿用仓库既有 `--check` 约定（漂移 exit 2 并点名新增项），SHALL NOT 用 `--write` 后 `git diff`；
   - ③ 子进程捕获输出 SHALL 设 `PYTHONIOENCODING=utf-8` + `errors='replace'` 且断言 stdout 含预期内容（只看 returncode 的守卫在 Windows gbk 下必假绿）。

---

## 分组 MODULE：七类模块深化（12.1~12.7）

### 需求 13：底稿 wp 模块六要素收敛

> 对应 深化 12.1（现状 + 四条可落地优化）/ 整改步骤 1、3、4、5。本需求的具体整改动作已分别由需求 1（串页/精确匹配）、需求 2（surfaced 只读 + upsert）、需求 5（鉴权 + 审计）覆盖，此处补该模块的收敛性验收。

**用户故事**：作为审计助理，我希望底稿公式的三套集合（正式 `wp_formula` / 只读 `surfaced` / D-F `extraction`）权威边界清晰，中央弹窗读写与执行语义一致。

### 验收标准

1. THE 工作底稿正式公式的唯一权威源 SHALL 为 `wp_formula`；`surfaced`/`extraction` SHALL 被明确标为只读投影/文档化目录，SHALL NOT 被当作权威定义编辑或保存。
2. THE wp evaluator 的函数支持 SHALL 遵守需求 8 的支持矩阵（真支持 TB/SUM_TB/WP，其余显式标注）。
3. THE 底稿公式的校对结果（logic_check → `cross_check_results`）与保存后传播（`formula_runtime_outbox`）SHALL 由需求 10、11 的运行坐实验收。
4. THE 底稿端点项目隔离与哈希审计 SHALL 由需求 5 覆盖。

---

### 需求 14：附注 note 模块权威源收敛

> 对应 深化 12.2。具体整改由需求 4 覆盖；此处锁定「不动附注鉴权」的边界。

**用户故事**：作为审计助理，我希望附注公式只有一个权威源，且既有健全的项目隔离不被本次改动破坏。

### 验收标准

1. THE 附注公式权威源收敛 SHALL 按需求 4 执行（二选一）。
2. THE 附注三端点 `apply/list/upsert` 的 `require_project_access` 与 `stamp_section_edit` 留痕 SHALL 保持不变（复核发现已健全）。

---

### 需求 15：报表 report 模块口径与鉴权

> 对应 深化 12.3（含克隆判定 DB 证据）/ 整改步骤 5。

**用户故事**：作为质控复核人，我希望报表链的「生产实证」口径按 distinct 模板/标准计量而非按项目克隆数夸大，且报表配置的写操作受项目与角色约束。

**现状证据**：`report_config` 为全局模板表（无 `project_id`，按 4 个 `applicable_standard` 区分；1191 行/318 含公式）；`financial_report` 492 条含公式行去重 `(row_code+formula_used)` 仅 82 对、跨项目公式冲突 0 → 6 项目各 82 行是同一套模板的 6 份克隆（6×82=492），不是 6 份独立证据。

### 验收标准

1. THE「报表链生产实证」口径 SHALL 按 distinct 模板/标准计（量级 ≈ 82 条模板公式），SHALL NOT 按项目数（6）夸大为 6 倍。
2. THE `report_config` 的 list/get/clone/update/create/delete/execute-batch SHALL 补 `require_project_access`（body/query 的 `project_id` 同样校验），全局模板写操作 SHALL 限 admin（与需求 5 合并实现）。
3. THE 报表链的运行实证 SHALL 由需求 11 的最小数据运行逐值对拍坐实（运行时待验）。

---

### 需求 16：试算表 tb 模块鉴权与传播

> 对应 深化 12.4（tb_summary 复用 report_config / tb_detail 存 wizard_state）/ 整改步骤 5、6。

**用户故事**：作为平台安全负责人，我希望 tb_detail 公式的读/写都受项目级约束，而不是读端 IDOR、写端仅角色门控。

**现状证据**：`get_tb_detail_formulas` 仅 `get_current_user`（可读任意项目 tb 公式配置，IDOR）；`save_tb_detail_formulas` 仅 `require_role`（角色门控非项目门控，有 manager 即可改任意项目）；含 `tb_detail_formulas` 键的项目数 = 0；无哈希审计链（复核发现）。

### 验收标准

1. THE `get_tb_detail_formulas` 读端点 SHALL 补项目级 `require_project_access`（消除 IDOR）。
2. THE `save_tb_detail_formulas` 写端点 SHALL 在既有 `require_role` 之外叠加项目归属校验。
3. IF tb_detail 公式要进统一传播 THEN 保存后 SHALL 发 `FORMULA_CONFIG_CHANGED` 触发 stale。
4. THE tb_summary 复用 `report_config` 的部分 SHALL 随需求 15 的报表鉴权整改一并受约束。

---

### 需求 17：合并报表 consol-report —— 先最小数据运行诊断再决策

> 对应 深化 12.5 / 整改步骤 7 / 第十三节「三个 consol 子节坐实状态统一」。

**用户故事**：作为质控复核人，我希望先用一次最小数据运行弄清合并报表链是「已接线但未使用」还是「已断裂」，再决定是否改代码，而不是在 count=0 的情况下就贸然重写合并链。

**现状证据**：真库仅 1 个 consolidated 项目，`consol_push_run=0`；count=0 无法区分「已接线未使用（成本低）」与「已断裂（成本高）」，当前只能判「未证明」（DB 证据，运行时待验）。

### 验收标准

1. THE 诊断手段 SHALL 为一次最小数据运行：在未删除的 consolidated 项目造一套隔离合并公式并触发推送，逐值对拍 `consol_report_values`，观察 `consol_push_run` 是否落库。
2. IF 运行后 run/值均按预期落库并对拍一致 THEN SHALL 判「已打通（仅数据阻塞）」，本模块 SHALL NOT 改代码。
3. IF 运行后 run 未落库或值对拍不一致 THEN SHALL 判「已断裂」，并据失败点定位最小改动，SHALL NOT 预先假定需重写整条合并链。
4. THE 需求措辞 SHALL NOT 写成「重写合并链」；诊断结果 SHALL 作为是否改代码的前置分支。

---

### 需求 18：合并附注 consol-note —— 先最小数据运行诊断再决策

> 对应 深化 12.6 / 整改步骤 7。

**用户故事**：作为质控复核人，我希望先弄清合并附注公式链是未用还是断裂，再决定是否改代码。

**现状证据**：`consol_note_formula`（未删）=0、`consol_note_data`=2（2 行未必来自公式执行）、`consol_push_run`=0；count=0 双重可能，只能判「未证明」。

### 验收标准

1. THE 诊断手段 SHALL 为一次最小数据运行：造合并附注公式 + 执行，逐值对拍 `consol_note_data`，观察 `consol_push_run` 是否落库。
2. IF 运行后落库且对拍一致 THEN 判「已打通（仅阻塞）」，SHALL NOT 改代码；IF 不落库或不一致 THEN 判「已断裂」并定位最小改动。
3. THE 需求措辞 SHALL NOT 写成「重建合并附注链」。

---

### 需求 19：合并底稿 consol-wp —— 先最小数据运行诊断再决策

> 对应 深化 12.7 / 整改步骤 7。

**用户故事**：作为质控复核人，我希望先弄清合并底稿（差额表/抵销单源 + 读时计算内核）链路是未用还是断裂，再决定是否改代码。

**现状证据**：合并底稿不独立存公式网格，其「公式」体现在差额表引擎中间节点；真库 1 个合并项目、`formula_push_run/state=0`、`consol_push_run=0`；count=0 双重可能，只能判「未证明」。

### 验收标准

1. THE 诊断手段 SHALL 与需求 17、18 合并为一次覆盖合并报表/附注/底稿的最小数据运行：在未删除的 standalone 与 consolidated 项目各造一套隔离公式，触发推送/重算，逐值对拍 `consol_report_values`/`consol_note_data` 并观察 `consol_push_run` 落库。
2. IF 落库且对拍一致 THEN 判「已打通（仅阻塞）」，SHALL NOT 改代码；IF 不落库或不一致 THEN 判「已断裂」并定位最小改动。
3. THE 需求措辞 SHALL NOT 写成「重写合并底稿链」。

---

## 分组 P2：治理与可维护性

### 需求 20：收敛局部 dialog 碎片化、对齐 spec 状态、收敛门禁噪声

> 对应 第九节 P2 1~3 / 第十三节待办「P2-局部 dialog 碎片化」「P2-spec 归档 100%≠可靠」「P2-门禁告警噪声」。

**用户故事**：作为项目经理，我希望至少 7 套 local formula dialog/drawer 要么收敛到中央、要么明确分工，spec 任务状态与运行事实对齐，门禁告警噪声被收敛，以免团队被历史假红和海量 warning 训练到忽略门禁。

**现状证据**：≥7 套 local formula dialog/drawer 权威源各异；4 个相关 spec 归档 100% 但 2 条前端测试为历史假红/脆化（`FormulaManagerPageWiring`、`formulaStatusPanelDisplay`）；formula_push 套件 1164 warnings，RTK 吞失败退出码（第八、九节）。

### 验收标准

1. THE ≥7 套 local formula dialog/drawer SHALL 被收敛到中央或明确分工（每套登记权威源与去留决定）。
2. THE 2 条历史假红/脆化前端测试 SHALL 被修正或更新，使其反映当前真实行为，SHALL NOT 继续以历史缺口为前提恒绿/恒红。
3. THE formula_push 套件的 1164 warnings（含 `Connection._cancel was never awaited`）SHALL 被收敛。
4. THE RTK 吞失败退出码问题 SHALL 被修正（验收须断言 stdout 内容，不能只看退出码）。

---

## 需求 → 报告锚点追溯表

> 供后续 design/tasks 引用。每条需求对应报告第九节 P0/P1/P2 缺陷 ID、第十节整改步骤号（1~7）、第十二节深化子节、第十三节待办编号。

| 需求 | 分组 | 报告缺陷 ID | 整改步骤（第十节） | 深化子节（第十二节） | 第十三节待办 | 证据强度 |
|---|---|---|---|---|---|---|
| 需求 1 当前 sheet 串页精确匹配 | P0 | FM-P0-01 | 1、3 | 12.1 优化① | FM-P0-01 当前 sheet 串页 | 源码 + 运行时 |
| 需求 2 surfaced 只读 + upsert 保存域 | P0 | FM-P0-02 | 1、4 | 12.1 优化②③ | FM-P0-02 surfaced 假可编辑 + 错保存域 | 源码 + DB |
| 需求 3 统一入口 / 删 node-only / 补 A1·Univer | P0 | FM-P0-03（+ P1 A1/Univer 无入口） | 2 | — | FM-P0-03 多入口丢上下文；P1-A1/Univer 无入口 | 源码 + 运行时 |
| 需求 4 附注用户公式保存后可执行 | P0 | FM-P0-04 | 4 | 12.2 优化①② | FM-P0-04 附注用户公式保存后不执行 | 源码 + DB |
| 需求 5 坐实并整改项目隔离 | P0 | FM-P0-05 | 5 | 12.1 优化④、12.3、12.4 | FM-P0-05 项目隔离缺失 | 源码（静态高危，未做越权探测） |
| 需求 6 左栏当前页地址 | P1 | P1-左栏非当前页地址 | 3 | — | P1-左栏非当前页地址 | 源码 + 运行时 |
| 需求 7 表间审核契约 | P1 | P1-表间审核契约错 | 6 | — | P1-表间审核契约错 | 源码 + 运行时 |
| 需求 8 函数支持矩阵禁静默 0 | P1 | P1-函数按钮/运行不一致 | 4 | 12.1、12.3 | P1-函数按钮/运行不一致 | 源码 |
| 需求 9 A1/Univer 入口 + 404 归类 | P1 | P1-A1/Univer 无入口 + 第四节 404 | 2 | 第四节 404 子类 | P1-A1/Univer 无入口 | 源码 + 运行时 |
| 需求 10 缓存隔离 / 单行 stale / 项目年 | P1 | P1-缓存未隔离/传播 | 6 | 12.4 优化 | P1-缓存未隔离/传播 | 源码 + DB |
| 需求 11 最小数据运行坐实空数据 | P1 | P1-正式运行数据为空 | 7 | — | P1-正式运行数据为空 | DB |
| 需求 12 全量门禁 8 断言 + 幂等 | GATE | 第十节建议门禁 | 2、3、5、6 | — | P2-spec 归档 100%≠可靠（配套） | 源码 + 运行时 |
| 需求 13 底稿 wp 收敛 | MODULE | FM-P0-01/02/05（汇） | 1、3、4、5 | 12.1 | FM-P0-01/02/05 | 源码 + DB |
| 需求 14 附注 note 收敛（不动鉴权） | MODULE | FM-P0-04 + 复核发现 | 4 | 12.2 | FM-P0-04 | 源码 + DB |
| 需求 15 报表 report 口径与鉴权 | MODULE | FM-P0-05 + 克隆判定 | 5 | 12.3 | FM-P0-05（报表侧） | DB |
| 需求 16 试算表 tb 鉴权与传播 | MODULE | FM-P0-05（tb-detail） | 5、6 | 12.4 | FM-P0-05（tb-detail，复核发现） | 源码 + DB |
| 需求 17 合并报表先诊断后决策 | MODULE | consol count=0（未证明） | 7 | 12.5 | 三 consol 子节统一 | DB |
| 需求 18 合并附注先诊断后决策 | MODULE | consol count=0（未证明） | 7 | 12.6 | 三 consol 子节统一 | DB |
| 需求 19 合并底稿先诊断后决策 | MODULE | consol count=0（未证明） | 7 | 12.7 | 三 consol 子节统一 | DB |
| 需求 20 碎片化/spec 状态/门禁噪声 | P2 | P2-1、P2-2、P2-3 | 4（P2-1）/—（P2-2/3） | — | P2-局部 dialog 碎片化；P2-spec 归档 100%≠可靠；P2-门禁告警噪声 | 源码 + 测试 |

> **口径提醒（继承报告 C2/C1）**：凡证据强度含「DB」而不含「运行时」者（需求 11/15/17/18/19 及合并三类），其结论当前为「**未证明打通**」，须经一次最小数据运行把「未证明」推进到「已证伪（断裂）」或「已打通（仅阻塞）」后，才能据结果决定是否改代码。需求 5（FM-P0-05）证据强度为「源码（静态高危）」，须经一条 TestClient 跨项目越权用例坐实后再据结果加固。附注公式端点（apply/list/upsert）已挂 `require_project_access`，**不在**鉴权缺陷追溯范围内。


