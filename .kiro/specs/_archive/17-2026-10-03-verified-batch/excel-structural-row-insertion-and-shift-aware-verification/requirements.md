# Requirements Document

## Introduction

本 spec 解除「结构性插行」这条禁令，让**所有**受管 Excel 底稿都能双向回写 —— 而不只是 HTML 侧行数恰好不超过模板骨架行数的那一小部分。

只读调查的当前基线（实测，作本次修订背景；运行时仍以机器判据为准）：

- `excel_materialize.plan_managed_writes` 第 4 步对「merged projection 的行身份在 substrate 上没有物理行」**无条件** `RowSetDivergenceError`。模块 docstring 第四节第 1 条把它写成判据：「不做结构性插行/删行」。
- 该禁令的成因是四道门叠加：① `_managed_sheet_cell_digest` 逐格 digest 带 `r=`，插入点以下每个未管理格坐标都变；② `_sheet_structure_digest` 把 `mergeCells` 整段序列化，K11 实测受管区域**之下**有 `E30:F30`；③ `assert_footer_anchor_stable` 要求实测 marker 行与冻结 `GT_FOOTER_ROW` **相等**，footer 下移即红；④ `assert_footer_formula_covers_managed_rows` 明文「共享公式主格不得在此处被改写」，而 K11 的 `SUM(B7:B25)` 正是 `t="shared" si="3"` 主格。
- 全代码库**只有两处**承认插行合法：`_classify_parts` 把 `xl/tables/**` 整类排除（注释原文「插删行会合法改 ref」），以及 `assert_identity_inventory_retained` 的子集语义（「行号与行区间一概不进判据」）。**不存在**任何「允许预期位移」的参数、容差或归一化概念。
- `dimension` / `hyperlinks` / `autoFilter` / `rowBreaks` / `pageSetup` 当前**不在任何 aspect 里**：它们不在 `_SHEET_STRUCTURE_BLOCKS` 的六个 tag 内，而受管 sheet part 又被 `_classify_parts` 的 `managed_parts` 整件排除。改动它们时 verifier 不会红 —— 这是假绿风险，不是通行证。
- 写入层现存 `_insert_row` 的 docstring 明写「**不位移**任何既有行」；`_patch_sheet_xml` 逐 write 用 `str.replace(view.raw, new, 1)`，没有任何重编号能力。
- 代码里**没有** si → 共享公式成员集合 的索引（`_cell_view` 只判 `ref` 含不含冒号，从不解析 `si` 数值）。
- 真实需求规模实测：D2 的 `D2-detail-rows` 有 **729** 行而模板骨架 `A13:AN25` 只有 **13** 行；H1 的 `H1-8-rows` 全库 0 行而骨架声明 15 行，其中第 27 行的 A 列实际是 `'……'`（表单续行符）而非整数。

本 spec 的完成定义是：受管表的物理行数可按 merged projection 的行集**按需增长**，插行引起的位移被 verifier 按**预期位移量**归一化后判等价，footer 两道门改为位移感知，且原「插不了就红」的残余分支仍然可达可打红。

### Glossary

- **结构性插行**：在受管区域内新增物理 `<row>`，并把插入点及其以下的全部行号、以及一切携带行号的 OOXML 引用整体下移。
- **预期位移（planned shift）**：由 materialize 计划显式声明的插入点与插入行数。verifier 只接受与该声明一致的位移；未声明的位移仍是漂移。
- **位移敏感结构**：任何在 XML 里携带行号的元素/属性。本 spec 要求它有一份成文清单，并由守卫与实现双向锁死。
- **共享公式主格**：`<f t="shared" ref="A1:A9" si="N">` 中带 `ref` 的那一格；同 `si` 的其余格是无文本成员，其公式由主格翻译得出。
- **合计区间扩张**：footer 合计公式的 A1 区间末行随受管行区间增长而增长。它必然改写共享公式主格的 `<f>` 文本与 `ref`。
- **骨架行**：模板预置的物理数据行。**不含**表单脚手架行（如 `'……'` 续行符行、`合计` 行）。
- **shift-aware digest**：把行号按预期位移反向归一化后再喂 hash 的未管理区域 digest。归一化只作用于比对，不改动 artifact。

---

## Glossary

| 术语 | 含义 |
|---|---|
| 结构性插行 | 在受管 sheet 的受管区插入物理行，其后的行整体下移 |
| 位移（shift） | 因插行导致的行号变化；`row >= insert_at` 时 `row += count` |
| 位移计划 | `RowShiftPlan`，一次插行的冻结声明（`insert_at` / `count` / `style_from`） |
| 声明值 vs 观测值 | 验证器用计划里的声明位移量归一化，**不用**从 diff 反推的观测量 —— 后者等于让被检查对象自证合法 |
| 位移敏感结构 | 携带行号的 sheet 级元素（`mergeCell` / `dataValidation@sqref` / `hyperlink@ref` / `dimension` / `rowBreaks` 等），插行时必须同步平移 |
| 共享公式 | `<f t="shared" ref="B26:G26" si="3">`，一个主格 + 若干成员格共用一份公式文本 |
| 主格 / 成员 | 带 `ref` 的是主格，只带 `si` 的是成员；主格永不换成字面量 |
| 区间扩张 | footer 合计公式的区间末行恰为 `insert_at - 1` 时末行 `+= count`，否则新行漏算 |
| shift-aware 验证 | 未管理区域摘要在比对前按声明位移量归一化行号，`t`/`s`/`f`/`v` 照旧逐字参与 |
| footer 两道门 | `assert_footer_anchor_stable` 与 `assert_footer_formula_covers_managed_rows` |
| 跨 sheet 引用 | 形如 `'明细表K11-2'!F29`；本 spec 只保证不改坏，联动传播由 `excel-workbook-wide-row-change-propagation` 承接 |

## Requirements

### Requirement 1: 位移敏感结构的成文清单与全覆盖

**User Story:** 作为平台维护者，我要「插行会影响哪些 OOXML 结构」有一份机器可读清单，且每一项都真的被检查，不能靠"没人改过它"侥幸。

#### Acceptance Criteria

1.1. THE 系统 SHALL 提供一份位移敏感结构清单，至少覆盖 `row@r`、`c@r`、`mergeCells/mergeCell@ref`、`dataValidations/dataValidation@sqref`、`conditionalFormatting@sqref`、`hyperlinks/hyperlink@ref`、`autoFilter@ref`、`rowBreaks/brk@id`、`dimension@ref`、共享公式 `f@ref`、共享公式文本内的 A1 区间、Excel Table `@ref`。
1.2. WHEN 清单新增一项 THEN 位移实现与 shift-aware 归一化 SHALL 同时覆盖它，否则守卫打红。
1.3. THE `_SHEET_STRUCTURE_BLOCKS` SHALL 补入 `dimension`、`hyperlinks`、`autoFilter`、`rowBreaks`，使它们从「不在任何 aspect 里」变为被逐元素锁定。
1.4. WHEN `_SHEET_STRUCTURE_BLOCKS` 或 `UNMANAGED_ASPECTS` 变更 THEN `UnmanagedRegionDigest.__post_init__` 的齐备判据 SHALL 同步生效，缺项即抛。
1.5. THE 清单 SHALL 与实现按**结构判据**双向锁死：清单里有的项，位移函数必须有对应处理分支；位移函数处理了的项，必须在清单里登记。
1.6. IF 受管 sheet 上出现清单外的、携带行号的元素 THEN 系统 SHALL fail closed 并指出该元素 tag，不得静默放过。

### Requirement 2: 位移计划是显式冻结声明

**User Story:** 作为审计平台开发者，我要位移量在写第一个字节之前就被冻结成计划的一部分，这样 verifier 才能判断"这次位移是预期的还是漂移"。

#### Acceptance Criteria

2.1. THE `MaterializePlan` SHALL 携带一个可选的位移计划，至少含插入点行号、插入行数、样式来源行号。
2.2. THE 位移计划 SHALL 是冻结值对象且零写入面，与 `CellWrite` 同款约定。
2.3. WHEN 位移计划为空 THEN 写入行为 SHALL 与本 spec 之前逐字节相同（纯增量，零回归）。
2.4. THE 位移计划 SHALL 进入 `MaterializePlan.as_dict()`，使 evidence 能复算本次插了几行、插在哪。
2.5. THE 插入点 SHALL 落在受管区域内且不早于第一个数据行；否则拒绝并给出独立 `error_code`。
2.6. THE 插入行数 SHALL 等于 merged projection 行集中在 substrate 上无物理行的身份数量；两者不等即拒绝。
2.7. WHEN 位移计划非空 THEN 受管区域 SHALL 按 `last_row + count` 重新构造，footer 与合计判据一律用新区间求值。

### Requirement 3: 位移是纯函数且在写格之前完成

**User Story:** 作为维护者，我要位移与写格严格分阶段，避免"坐标算在旧 XML 上、写在新 XML 上"的静默错位。

#### Acceptance Criteria

3.1. THE 位移 SHALL 实现为对 sheet XML 的纯函数：输入原 XML 与位移计划，输出新 XML，不碰磁盘、不改入参。
3.2. THE 位移 SHALL 在任何 `_cell_view` 求值**之前**完成；写格阶段只在位移后的 XML 上定位坐标。
3.3. WHEN 位移完成 THEN 插入点以下的每个 `row@r` 与 `c@r` SHALL 恰好增加插入行数，其余行号不变。
3.4. THE 新插入行 SHALL 从声明的样式来源行继承每一列的 `s=` 样式；不得产出无样式格。
3.5. THE 新插入行 SHALL 不携带任何业务值；业务值由随后的写格阶段按 projection 落入。
3.6. WHEN 样式来源行在 XML 里不存在 THEN 系统 SHALL fail closed 并给出独立 `error_code`。
3.7. THE 位移 SHALL 保持 `<row>` 元素按行号升序，且不产生重复 `r`。
3.8. THE 位移 SHALL 更新 `dimension@ref` 的末行；不得留下小于实际行数的 dimension。

### Requirement 4: 共享公式的位移与区间扩张

**User Story:** 作为审计师，我要插行后合计公式把新行算进去，且原有公式组不失效。

#### Acceptance Criteria

4.1. THE 系统 SHALL 建立 `si` → (主格坐标, `ref` 区间) 的解析层；当前代码只判 `ref` 含不含冒号，无法定位组成员。
4.2. WHEN 共享公式主格位于插入点之上且其 `ref` 区间跨过插入点 THEN `ref` 末行与公式文本内的对应区间末行 SHALL 增加插入行数。
4.3. WHEN 共享公式主格位于插入点之下 THEN `ref` 首末行 SHALL 整体增加插入行数。
4.4. WHEN 契约声明该 footer 携带合计公式 THEN 合计区间末行 SHALL 随受管区间末行一起扩张，且扩张后 `assert_footer_formula_covers_managed_rows` SHALL 通过。
4.5. IF 契约未声明 footer 携带合计公式 THEN 系统 SHALL 不改写该 footer 的任何公式，并保持既有 fail-closed 语义。
4.6. THE 合计区间扩张 SHALL 只作用于契约声明的 footer 行；受管区域之外的其它共享公式组只做位移，不做扩张。
4.7. WHEN 主格 `ref` 改写后同组成员的行跨度与主格不一致 THEN 系统 SHALL fail closed。
4.8. THE `SharedFormulaMasterWriteError` 的既有禁令 SHALL 保留：本 spec 只允许**位移与扩张**主格的区间，不允许把主格替换成字面量。

### Requirement 5: 契约必须能声明 footer 是否带合计公式

**User Story:** 作为契约作者，我要能声明"这个 footer 有合计公式、插行时区间要跟着长"，而不是让引擎去猜。

#### Acceptance Criteria

5.1. THE `FooterAnchorSpec` SHALL 解析并保留 `carries_total_formula` 布尔字段；当前它在解析时被静默丢弃。
5.2. WHEN 契约 JSON 未给该字段 THEN 默认值 SHALL 为假，即保持既有 fail-closed 行为（纯增量）。
5.3. THE 字段名 SHALL 不违反既有 CS-12 对 `row` / `row_index` / `row_number` 三个键名的禁令。
5.4. WHEN `carries_total_formula` 为真但该 footer 行上一处公式都找不到 THEN 系统 SHALL fail closed（声明与模板不符）。
5.5. THE 契约 canonical payload 变更 SHALL 走既有 `template → instrumentation → contract → bundle → representation` 发布链；不得原地改写已发布 definition。

### Requirement 6: shift-aware 未管理区域验证

**User Story:** 作为平台管理员，我要 verifier 能区分"预期插行造成的位移"与"真实漂移"，不能因为支持插行就把整类检查关掉。

#### Acceptance Criteria

6.1. THE `unmanaged_region_digest` SHALL 接受可选的预期位移参数。
6.2. WHEN 给出预期位移 THEN 非受管格的 digest SHALL 把插入点以下的行号反向归一化后再喂 hash。
6.3. WHEN 给出预期位移 THEN 结构块中携带行号的属性 SHALL 同样反向归一化后再喂 hash。
6.4. WHEN 未给出预期位移 THEN digest 计算 SHALL 与本 spec 之前逐字节相同。
6.5. THE 新插入行本身的格 SHALL 被排除在「非受管格」之外；它们是受管区域的一部分。
6.6. IF 归一化之后仍存在差异 THEN verifier SHALL 报告首个差异 aspect，语义与既有一致。
6.7. THE 归一化 SHALL 只作用于比对，不得改动任何 artifact 字节。
6.8. THE 归一化 SHALL 不放宽「改动已有 sharedStrings 条目」「protected_parts 变化」「跨 sheet 部件变化」等与行位移无关的判据。
6.9. WHEN 预期位移声称插了 N 行而实测位移量不等于 N THEN verifier SHALL 判不等价。

### Requirement 7: footer 两道门改为位移感知

**User Story:** 作为审计师，我要插行后 footer 跟着下移是正常的，但不明原因的下移仍然要被拦住。

#### Acceptance Criteria

7.1. THE `assert_footer_anchor_stable` SHALL 接受预期位移，判据由「实测 == 冻结」改为「实测 == 冻结 + 预期位移」。
7.2. WHEN 预期位移为零 THEN 判据 SHALL 与本 spec 之前逐字相同。
7.3. IF 实测行号与「冻结 + 预期位移」不等 THEN 系统 SHALL 保持 `FooterAnchorDriftError` 并在消息中同时给出三个数值。
7.4. THE `assert_footer_formula_covers_managed_rows` SHALL 用位移后的受管区间求值。
7.5. WHEN 合计区间已按 Requirement 4.4 扩张 THEN 本判据 SHALL 通过；未扩张则仍报 `FooterFormulaRangeError`。
7.6. THE 两道门的返回值语义 SHALL 保持不变（`None` 表示契约无 footer 声明，空元组表示本次未检查任何坐标）。

### Requirement 8: 残余 fail-closed 分支必须保留且可达

**User Story:** 作为质控复核人，我要"插不了行就红"这条路径在支持插行之后仍然存在，否则原有的变异守卫会变成空转。

#### Acceptance Criteria

8.1. THE `RowSetDivergenceError` 与其 `error_code` SHALL 保留在 `FAILURE_KINDS` 登记表中。
8.2. WHEN 插行被判为不可安全执行 THEN 系统 SHALL 抛 `RowSetDivergenceError`，并在消息中给出具体拒绝原因。
8.3. THE 既有变异锚点所指向的守卫 SHALL 仍然可被打红；改动后必须实测确认，不得只看退出码。
8.4. THE 不可安全执行的判据 SHALL 至少包含：受管 sheet 上出现清单外的位移敏感元素、样式来源行缺失、共享公式组成员跨度与主格不一致、插入点越界。
8.5. THE 每条拒绝原因 SHALL 有独立 `error_code` 或独立可断言的诊断片段，两两可分辨。

### Requirement 9: K11 冻结 fixture 与既有证据不得被打碎

**User Story:** 作为维护者，我要这次改动不把 Task 38 已冻结的模板事实与其它 spec 的 evidence 弄失效。

#### Acceptance Criteria

9.1. THE Task 38 锁死的四条 K11 模板事实 SHALL 继续成立：drawing 部件存在、受管区域之下的 merge 存在、共享公式组存在、footer 合计公式存在。
9.2. WHEN 位移计划为空 THEN 既有全部 Task 37 / Task 38 用例 SHALL 逐条通过，且产物 digest 逐字节不变。
9.3. THE 本 spec 的改动 SHALL 不修改 `backend/wp_templates/` 下任何字节。
9.4. THE 既有已发布 definition 与 bundle SHALL 不被原地改写；契约字段扩充按 Requirement 5.5 走发布链。
9.5. WHEN 既有测试因判据语义变化必须调整 THEN 调整 SHALL 逐条写明理由，且不得把判据改弱。

### Requirement 10: 全量底稿可达性

**User Story:** 作为产品负责人，我要这次改动之后"所有底稿都能双向回写"是一个可验证的结论，而不是一个愿望。

#### Acceptance Criteria

10.1. THE 系统 SHALL 提供一个只读清册，逐 entry 报告「HTML store 行数 / 模板骨架行数 / 是否需要插行 / 插行是否可安全执行」。
10.2. THE 清册结算 SHALL 落在封闭词表内，不得使用自由文本。
10.3. WHEN 某 entry 被判为不可插行 THEN 清册 SHALL 给出具体判据编号与解除条件。
10.4. THE 清册 SHALL 由真实库与真实模板现算，不得手填。
10.5. THE 实测覆盖 SHALL 至少包含一个真实超出骨架行数的 entry（D2 的 729 行）与一个骨架行数为零增长的 entry（回归对照）。
10.6. IF 清册中仍存在不可插行的 entry THEN 每一条 SHALL 有登记的阻塞原因与归属任务，不得留白。

### Requirement 11: 测试、变异与真实环境验证

**User Story:** 作为维护者，我要每条判据都经过变异检验，且插行结果在真实 Excel/OnlyOffice 上能打开。

#### Acceptance Criteria

11.1. THE 每条新增判据 SHALL 有至少一个变异锚点，并记录它所守的假绿形态。
11.2. THE 变异结果 SHALL 按 RED / GREEN / ANCHOR-MISS / WRONG-TEST 四态判读，不以退出码代替判读。
11.3. THE 变异 SHALL 覆盖：删除位移阶段、把归一化改成恒等、把 footer 判据的位移项去掉、把清单某一项从位移函数里删掉、把残余 `RowSetDivergenceError` 分支删掉、把新插入行的样式继承改成空样式。
11.4. THE 插行产物 SHALL 通过既有 OOXML 安全校验与 `structure_fingerprint` 采集（`errors` 必须为空）。
11.5. THE 插行产物 SHALL 能被 openpyxl 加载且受管区域行数等于预期。
11.6. THE 属性测试 SHALL 用 hypothesis，每条 `max_examples` 不低于 100。
11.7. THE 测试 SHALL 从仓库根调用 pytest，并按对本 spec 交付物的实际引用关系确定辐射面，不执行全量后端测试目录。
11.8. WHEN 真实 OnlyOffice 环境不可得 THEN 相关判据 SHALL 标记 UNVERIFIABLE 并保持未验收，不得用 fixture 冒充。

### Requirement 12: 范围边界

**User Story:** 作为业务合伙人，我要范围边界写进需求并各自说明理由，以便后续不因失焦把独立劳动量并进来。

#### Acceptance Criteria

12.1. THE 本需求范围 SHALL 不包含结构性**删行**（projection 行集少于物理行时的收缩）；删行涉及数据丢失裁决，与插行不同源。🔴 **2026-09-04 更新：该能力已由 `excel-workbook-wide-row-change-propagation` 承接**（其 Requirement 3 与 Property 10~15），本 spec 仍不实现，但不再是「无人承接的缺口」。✅ **2026-09-05 更新：承接方已交付。** `excel_workbook_row_change.shrink_sheet_rows` + `build_delete_plan`（悬空引用在**计划阶段** fail-closed，业务键 `row_uuid`→稳定序号→拒绝），判据 `test_workbook_row_change_delete.py` **38 passed**。两载体分工取证：D2 删得成（产物 openpyxl 可打开、`max_row` 减 1）、K11 100% 阻断（6 处单格引用悬空）。本 spec 仍不实现删行 —— `shift_sheet_rows` 的语义是「造新行 + 下移」，删行是「移除 + 上移」，承接方刻意**不复用**它（共用一个实现会让两边的边界条件互相干扰）。
12.2. THE 本需求范围 SHALL 不放宽 OOXML 安全策略的外部关系许可。
12.3. THE 本需求范围 SHALL 不修改 H1 契约把表单续行符行算作数据行的既有缺陷；该缺陷由独立任务承接。
12.4. THE 本需求范围 SHALL 不实现跨 sheet 引用在被引用侧插行时的联动改写；本 spec 只处理受管 sheet 自身。🔴 **2026-09-04 更新：该能力已由 `excel-workbook-wide-row-change-propagation` 承接**（其 Requirement 2 与 Property 4~9）。实测该缺口非边缘：351 份 xlsx 里 176 份含跨 sheet 引用，其中 **137 份**的被引用 sheet 自身含动态行占位（受影响 sheet 604 张）；K11 的受管 sheet `审定表K11-1` 被 2 张 sheet 的 **114 处**公式引用，被引用行号 7~25 **完全落在受管区 `A7:N25` 内**。本 spec 对跨 sheet 引用「逐字不动」的实现保证了不改坏，新 spec 负责让它联动

> ✅ **2026-09-05 更新：承接方已交付并接线，本条从「不实现」变成「由承接方在同一次 materialize 里完成」。**
>
> * **接线点在本 spec 的两个函数上**：`plan_managed_writes` 现在会在 `row_shift is not None` 时冻结一份 `plan.workbook_row_change` 声明；`apply_plan_zip_with_report` 在**位移之后、写格之前**按该声明改引用侧 sheet 与 `xl/workbook.xml`。`row_shift is None` 时两处均逐字节不变。
> * **`verify_unmanaged_regions` 新增 `propagation` 参数**：按**同一份声明**逆归一化引用侧 sheet。与 `row_shift` 同一条纪律 —— 只给 after 侧，且按**声明**而非观测。
> * 🔴 **本 spec 的一条判据因此翻转**（`test_excel_row_insertion_wiring.py` 的 `test_unmanaged_regions_are_equivalent_under_the_declared_plan`）：翻转前 `row_shift` + `total_formula_rows` 两个声明足以判等价；翻转后**少传 `propagation` 就判漂移**。那不是判据变弱，而是**多了一类必须声明的改动**。K11 上实测首个差异是 `workbook_and_styles`（definedNames 落在那一桶）。
> * 「跨 sheet 引用逐字不动」这条**旧**保证已不再成立，也不该成立 —— 它当时的作用是「不改坏」，现在的正确行为是「按声明联动」。本 spec 的零回归基线（144,154 处跨 sheet 引用逐字不变）仍然守着「**没有计划时**不得擅自改」这一半。正确。
12.5. THE 本需求范围 SHALL 不改变 `openpyxl_roundtrip` 分支的可达性判据。
12.6. THE 本需求范围 SHALL 不新增数据库迁移文件。
