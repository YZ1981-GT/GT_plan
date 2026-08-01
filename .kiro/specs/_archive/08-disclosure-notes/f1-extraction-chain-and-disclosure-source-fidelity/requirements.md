# Requirements Document

## Introduction

F1 预付账款的四表库取数链路与两个披露表（上市 §五、7 / 国企 §八、7）在归档 spec
`f1-prepayment-disclosure-template-alignment` 与 `f1-four-table-extraction-and-disclosure-alignment`
中已完成大部分对齐：报表行 `BS-008` 经 `report_config` 解析、叶子聚合走共享件
`app/services/four_table`、F1-1 审定表按性质预填、F1-2 明细自动从 `tb_aux_balance` 归集、
两个披露 Tab 的列结构与源 xlsx 逐字一致、附注两节结构随「附注模版 + 校验预设」口径。

本 spec 收口**本轮逐格复核源模板后新发现的 5 处链路缺口**。全部结论均有实证支撑
（openpyxl 直读 `backend/wp_templates/F/F1 预付账款.xlsx` + postgres 只读查询 + 运行态
`convert_prefill_presets()` 输出）：

1. **国企披露②表「账龄超过1年的大额预付款项」的数据源与源模板不一致。**
   源 xlsx `附注披露信息(国企)` R18~R20 四列公式逐格指向 F1-5：
   `B18='长期挂款检查表F1-5'!A6`（债务单位）、`C18=…!J6`（期末余额 = F1-5 **审定余额**列，
   已扣坏账准备）、`D18=…!C6`（账龄）、`E18=…!E6`（未结算的原因）。
   现实现 `useF1DisclosureSoe.over1YearRows` 读的是 `crossSheet.longTermRows`
   —— 由 F1-2 明细**派生**（`endAudited` 未扣坏账、`agingDescription` 为自动拼接串），
   且「未结算的原因」另存一份 `F1-note-soe-over1-meta`，与 F1-5 已有的 `reason` 列构成**重复录入**。

2. **国企披露②表「债权单位」列恒空。**
   源 xlsx A18~A20 是 `=RIGHT($A$3,LEN($A$3)-SEARCH("：",$A$3))`，即从底稿目录
   「被审计单位：XXX」截出的**被审计单位名称**。现实现只读 meta 覆盖值、缺省空串
   → 校验预设 `F7-9`（soe）「期末余额 ≠ 0 则债权单位/债务单位/账龄/未结算的原因均不应为空」
   恒不通过，且附注②表首列永远空白。

3. **减值准备（坏账准备-预付账款）只走 `tb_balance` 反解路径，未用 `trial_balance` 标准码。**
   postgres 实证（项目 `0ec33ac9`）：`account_mapping` 只有 `1231→1231`、`1231.01→1231-01`、
   `1231.02→1231-02`、`1231.03→1231-03`，**没有** `1231-04`；而 `trial_balance`
   **确有** `1231-04 坏账准备-预付账款` 行。故现路径（标准码 → 反解原始码 → `tb_balance` 前缀）
   必然退化为宽前缀 `1231` + 名称过滤「预付」→ 命中为空 → `impairment_prefill` 恒 `None`，
   而平台权威的标准码口径本可直接取到。公式预设里 `TB('1231-04','期末余额')` 走的正是后者，
   两条链路口径不一致。

4. **两个披露 sheet 与 F1-5 在公式管理页无任何公式预设。**
   运行态 `convert_prefill_presets()` 的 `workpaper:F1` 共 17 条，全部属
   `审定表F1-1` / `明细表F1-2` / `实质性分析F1-4` 三个 sheet。源模板披露 sheet 的每一个
   数据格都是跨 sheet 公式（`审定表F1-1'!I17`、`实质性分析F1-4'!B41`、`长期挂款检查表F1-5'!J6`），
   审计师在公式管理页看不到披露表与 F1-5 的取数来源。

5. **`tb_aux_balance` 自动归集把所有行标 `非关联方`，未用 render 已下发的关联方名单。**
   `build_f1_detail_rows_from_aux` 无条件写 `relationType: "非关联方"`，而 F1 render 早已
   输出 `project_context.related_parties`（取自 `related_party_registry`）。
   四表入库后 F1-2 的关联方列全错、F1-6 关联方检查表「从F1-2导入」筛不出任何行。

本 spec **不改**已定论的两处口径（写下来防复盘重复提议）：
- 附注①按账龄表保持 **5 列 + 小计/减：减值准备/合计 7 行**（校验预设 `F7-6`/`F7-7`/`F7-8`
  是裁决者；国企源 xlsx 的 7 列三级表头是**底稿收集形态**，底稿 Tab 已忠实渲染，
  同步时投影为附注形状 —— 平台铁律「附注是交付物，底稿可多留审计列」）。
- 附注 seed 骨架的 4 个账龄档（3 年段）不改：`note_template` 是 variant 级共享骨架，
  推送时整表覆盖，且 `guidance` 已注明随项目账龄枚举自适配。

## Requirements

### Requirement 1: 国企披露②表以 F1-5 为权威数据源

**User Story:** 作为审计助理，我在 F1-5 长期挂款检查表里录了债务人、账龄、未结转原因和坏账准备后，
希望国企披露②表直接呈现这些内容（含审定余额口径），而不是让我在披露表里把原因再录一遍。

#### Acceptance Criteria

1. WHEN F1-5（`F1-lt-rows`）存在至少一行有效行 THEN 国企披露②表的行集 SHALL 取自 F1-5，
   且「期末余额」取 F1-5 的**审定余额**（`auditedBalance` = 期末余额 − 坏账准备，对应源 J 列）。
2. WHEN 行来自 F1-5 THEN 「账龄」SHALL 取 F1-5 的 `aging` 列（源 C 列），
   「未结算的原因」SHALL 取 F1-5 的 `reason` 列（源 E 列）。
3. WHEN F1-5 为空 THEN 行集 SHALL 回退到既有的 `crossSheet.longTermRows`（F1-2 派生），
   保证升级零回归。
4. WHEN 行来自 F1-5 且用户在披露表内改「账龄」或「未结算的原因」THEN 覆盖值 SHALL 持久化在披露表
   自己的 meta 里，并优先于 F1-5 值（手工优先），且 SHALL NOT 回写 F1-5。
5. 披露表 SHALL 显示每行的来源（F1-5 / F1-2 / 手工新增），供审计追溯。

### Requirement 2: 国企披露②表「债权单位」缺省取被审计单位名称

**User Story:** 作为审计助理，我不想为②表的每一行手工重复敲一遍被审计单位名称，
因为源模板里这一列本来就是从底稿目录自动带出的。

#### Acceptance Criteria

1. WHEN 项目 `client_name` 非空且该行未被手工覆盖 THEN 「债权单位」SHALL 缺省显示被审计单位名称。
2. WHEN 用户手工填写「债权单位」THEN 手工值 SHALL 优先，且清空后 SHALL 回落到缺省值。
3. 推送到附注的载荷 SHALL 使用与界面一致的最终值（缺省值也要推，不能推空串）。
4. 缺省值的取用 SHALL NOT 依赖底稿目录 sheet 的单元格解析（改用 render 已下发的
   `project_context.client_name`）。

### Requirement 3: 减值准备双口径取数

**User Story:** 作为现场经理，我需要「坏账准备-预付账款」在客户没做科目映射时也能按标准码取到，
并且能看到两条取数路径各自的结果，才能判断差异是数据问题还是口径问题。

#### Acceptance Criteria

1. F1 render SHALL 增加一条经 `trial_balance` 标准码（`1231-04` 及报表公式解析出的备抵标准码）
   直取期末减值准备的路径。
2. WHEN `tb_balance` 反解路径为空且 `trial_balance` 路径有非零值 THEN `impairment_prefill`
   SHALL 采用 `trial_balance` 的期末值；期初 SHALL 保持 `null`（`trial_balance` v2 无期初列，
   不得臆造）。
3. WHEN 两条路径都为空 THEN `impairment_prefill` SHALL 整键省略（宁缺勿造，保持手工录入）。
4. 溯源输出 SHALL 同时给出两条路径的科目码与金额，供 `F1FourTableSourcePanel` 展示差异。
5. 名称过滤（「预付」）SHALL 只在备抵侧反解退化为宽前缀时生效（`provision_exact=false`），
   `trial_balance` 标准码路径 SHALL NOT 叠名称过滤（标准码本身已精确）。

### Requirement 4: 补齐披露 sheet 与 F1-5 的公式预设

**User Story:** 作为审计助理，我在披露表和 F1-5 这两页打开公式管理时，希望能看到本页每个
数据格的取数公式，而不是一片空白。

#### Acceptance Criteria

1. `prefill_formula_mapping.json` SHALL 新增 `附注披露信息(上市公司)`、`附注披露信息(国企)`、
   `长期挂款检查表F1-5` 三个 F1 块，sheet 名与源 xlsx tab 名逐字一致。
2. 每条预设的 `cell_ref` SHALL 在 `workpaper:F1` 页内全局唯一
   （`convert_prefill_presets` 的 `page_key` 忽略 sheet，同名会被静默去重丢弃）。
3. 披露块的公式 SHALL 只用 `TB` / `WP` / `AUX` 已注册函数，且 `WP()` 只指向
   `审定表F1-1` / `实质性分析F1-4` / `长期挂款检查表F1-5` / `明细表F1-2`
   —— 披露块自身 SHALL NOT 被别的块 `WP()` 引用（防循环）。
4. 新增预设 SHALL 通过 `validate_formula`（返回空错误列表）。
5. 守卫 SHALL 断言运行态 `workpaper:F1` 预设条数增加且无 `cell_ref` 冲突。

### Requirement 5: 辅助余额归集自动识别关联方

**User Story:** 作为审计助理，四表入库后 F1-2 自动归集出来的往来单位里本就有关联方，
我希望系统按项目关联方名单先标出来，而不是一律标成「非关联方」让我逐行核。

#### Acceptance Criteria

1. `build_f1_detail_rows_from_aux` SHALL 接受关联方名单入参，并在往来单位名称命中名单时
   把 `relationType` 置为关联方标识，否则保持 `非关联方`。
2. 名称匹配 SHALL 做去空白归一，并支持「名单项 ⊆ 往来单位名」与「往来单位名 ⊆ 名单项」双向包含
   （客户账套里同一主体常带分支后缀）。
3. 名单为空时行为 SHALL 与改造前逐字一致（全部 `非关联方`）。
4. merge 语义 SHALL 不变：已存在的往来单位名称不重复导入，不覆盖手工录入。

### Requirement 6: 守卫与实测

**User Story:** 作为质量控制复核合伙人，我需要这些口径被测试钉住，
避免下一次 md 重建或并发改动把它们悄悄改回去。

#### Acceptance Criteria

1. SHALL 有后端守卫用 openpyxl 直读源 xlsx，断言国企②表四列的公式确实指向 F1-5 的
   A/J/C/E 列（即 R1 的依据不会被后续改动悄悄推翻），并含反向自检。
2. SHALL 有前端守卫断言：F1-5 有行时②表取 F1-5、F1-5 空时回退 F1-2、手工覆盖优先、
   债权单位缺省为被审计单位名。
3. SHALL 有守卫断言两个披露表的列常量与附注模板 `columns`、源 xlsx 列头三方一致
   （沿用既有 `f1NoteSubtableContract.spec.ts` 的 P1~P6 helper，不新造机制）。
4. SHALL 在真实项目上实测：四表入库 → 打开 F1 → F1-2 自动归集 → F1-1 预填 →
   国企披露②表带出 F1-5 内容与债权单位 → 推送 → `disclosure_notes` §八、7 落库正确；
   实测数据 SHALL 完整复原。

## Glossary

| 术语 | 含义 |
|---|---|
| F1-5 | 「账龄1年以上的大额预付账款检查表」底稿 sheet，13 列；J 列「审定余额」= B 期末余额 − I 计提坏账准备 |
| ②表 | 披露小节「（2）账龄超过1年的大额预付款项」（国企）/「（2）账龄超过1年的重要预付款项」（上市） |
| 反解 | 由标准码经 `account_mapping` 反向查出客户原始码前缀，用于 `tb_balance` 前缀匹配 |
| 宽前缀退化 | 反解无命中时退回标准码的一级段（如 `1231-04` → `1231`），必须叠名称过滤才可用 |
| 备抵 | 资产减值/坏账准备类贷方科目（F1 为 `1231-04 坏账准备-预付账款`） |
| page_key | 公式预设的页键 `workpaper:{wp_code}`，**忽略 sheet** → `cell_ref` 须页内唯一 |
