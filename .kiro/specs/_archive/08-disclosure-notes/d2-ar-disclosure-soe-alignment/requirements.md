# Requirements: d2-ar-disclosure-soe-alignment

## Introduction

以致同 2025 修订版源模板 `D2-1至D2-4 应收账款-审定表明细表（Leap-常规程序）.xlsx` 的
`附注披露信息(国企)` sheet（A1:K138 实测）为唯一基准，校正三层：

1. **底稿层** — D2 国企披露表（`D2DisclosureNoteBody.vue` + `useD2DisclosureNote.ts`）
2. **同步层** — `d2NoteSectionMap.ts` 的 `D2_TABLE_NAMES.soe` / 列头常量 / `buildD2SyncPayload`
3. **附注层** — `note_template_soe.json` 章节 `八、5 应收账款` 的 TAB（tables）/ 表格结构 / 文本节

姊妹 spec `d2-ar-disclosure-template-alignment` 已完成上市版（五、5）的底稿层与同步层，
本 spec 只做国企版（八、5），并补齐上市版遗留的两处公共欠账：
附注模板多级表头透传（`disclosure_engine`）与过期契约测试。

### 源模板披露逻辑（梳理结论，作为全部需求的事实基础）

源 sheet 结构 = **1 张引导表 + 6 个编号披露事项**，按「先总额结构 → 再计提方法 → 再变动 → 再个别事项」递进：

| 源行 | 内容 | 披露意图 |
|------|------|----------|
| r6~r15 | 账龄表（6 档 + 小计 + 减：坏账准备 + 合计） | 账龄结构 → 净额，与审定表勾稽 |
| r16~r28 | （1）按坏账准备计提方法分类（**双期各 5 值列**：账面余额{金额,比例%} / 坏账准备{金额,预期信用损失率%} / 账面价值） | 单项 vs 组合的计提方法与损失率对比 |
| r29~r33 | 期末按单项计提明细（债务人 / 账面余额 / 坏账准备 / 账龄 / 预期信用损失率%） | 单项判断可追溯 |
| r34~r79 | 按信用风险特征组合计提：每组合 **期末数表 + 续：期初数表**，列 = 账龄 × {应收账款, 比例（%）, 坏账准备} | 组合内账龄结构与损失率 |
| r80~r92 | 采用余额百分比或其他组合方法（组合名称 × 双期{账面余额, 计提比例（%）, 坏账准备}） | 非账龄组合口径 |
| r93~r105 | （2）本期计提/收回或转回（类别 × 期初数 / **本期变动金额{计提, 收回或转回, 转销或核销}** / 期末数）+ 收回或转回明细 + 注释 | 变动完整性、重要转回单独列报 |
| r106~r110 | （3）本期实际核销（含履行的核销程序、是否因关联交易产生） | CAS30 关联交易核销单独披露 |
| r111~r118 | （4）按欠款方归集的期末余额前五名 | 集中度风险 |
| r119~r128 | （5）由金融资产转移而终止确认 + 说明 A（不附追索权贴现）/ B（不符合终止确认条件的质押） | 转移与继续确认的边界 |
| r129~r138 | （6）转移继续涉入形成的资产、负债（项目 × 期末金额，资产/负债分块小计）+ 说明 | 继续涉入敞口 |

编号口径说明：源 sheet 把账龄表作为不编号的引导表，`（1)` 从分类披露起算；
附注模板 `八、5` 既有口径把账龄表编为 `（1）`，后续顺延。本 spec **沿用附注模板既有编号**
（避免动摇 `note_template_bindings.json` / `report_note_linkage` / 既有测试），
仅把源模板 `（6）继续涉入` 顺延为附注侧 `（7）`。

## Requirements

### Requirement 1 — 国企组合计提分表恢复源模板 3 值列 × 双期

**User Story:** 作为审计助理，我要在国企披露表的每个信用风险组合分表里录入期末与期初的
应收账款、比例、坏账准备，以便附注按源模板口径披露组合内账龄结构。

#### Acceptance Criteria
1. WHEN 渲染国企版组合分表 THEN 表头为两级：`账 龄` + `期末数{应收账款, 比例(%), 坏账准备}` + `期初数{应收账款, 比例(%), 坏账准备}`
2. WHEN 录入某账龄段的应收账款 THEN `比例(%)` 为只读派生列 = 该段应收账款 ÷ 该组合本期合计 × 100，分母为 0 时显示 0.00
3. WHEN 组合分表同步到附注 THEN `sub_table_data` 行含 6 个数值业务键，`columns` 含 `group` 标注供多级表头渲染
4. WHERE 账龄段来自项目账龄配置 THE 分表行数随配置变化，已录入同 key 金额保留

### Requirement 2 — 「采用余额百分比或其他组合方法」恢复源模板 7 列

**User Story:** 作为现场经理，我要看到非账龄组合的计提比例与坏账准备双期数据，而不是只有两个余额。

#### Acceptance Criteria
1. WHEN 渲染该表 THEN 列为 `组合名称` + `期末数{账面余额, 计提比例（%）, 坏账准备}` + `期初数{账面余额, 计提比例（%）, 坏账准备}`
2. WHEN 录入账面余额与坏账准备 THEN `计提比例（%）` 为只读派生列 = 坏账准备 ÷ 账面余额 × 100
3. WHEN 同步到附注 THEN 该表推送 6 个数值业务键与带 `group` 的列头
4. IF 历史持久化行只有 `endAmount`/`priorAmount` THEN 读入后新增字段默认 0，不丢原值

### Requirement 3 — 变动表列头对齐源模板并分组

**User Story:** 作为质量控制复核合伙人，我要在附注里看到「本期变动金额」跨三子列的合并表头，与源模板一致。

#### Acceptance Criteria
1. WHEN 构建国企变动表列头 THEN 三个变动列 label 逐字为 `计提` / `收回或转回` / `转销或核销`，且 `group` 均为 `本期变动金额`
2. WHEN 附注渲染该表 THEN 呈现两级表头（父表头「本期变动金额」跨 3 列）
3. WHERE 期初数 / 期末数 列 THE 无 `group`，纵向合并两行

### Requirement 4 — 国企补齐「（7）继续涉入」表与终止确认说明

**User Story:** 作为业务合伙人，我要国企附注也披露转移继续涉入形成的资产、负债，并有终止确认的文字说明。

#### Acceptance Criteria
1. WHEN 变体为国企 THEN `D2_TABLE_NAMES.soe` 含 `continuedInvolvement`，表名为 `（7）应收账款转移继续涉入形成的资产、负债的金额`
2. WHEN 该表同步到附注 THEN 按源模板 2 列（`项  目` / `期末金额`）推送，行结构为 `资产：` 分块 + `资产小计` + `负债：` 分块 + `负债小计`
3. WHEN 渲染国企终止确认块 THEN 表下方有「说明」文本框，占位提示含源模板 A（不附追索权贴现）/ B（不符合终止确认条件的质押）两段范式
4. WHEN 说明文本非空 THEN 随 `_note_texts` 以 `note-derecognition` / `note-continuedInvolvement` 同步到附注 `text_content`

### Requirement 5 — 附注模板 `八、5` 结构修订（TAB / 表格 / 文本框）

**User Story:** 作为审计助理，我在附注模块「财务报表主要项目注释 → 应收账款」看到的 TAB 与表格结构，
必须与底稿披露表、与源模板一致，未同步时也不能是被压扁的 3 列表。

#### Acceptance Criteria
1. WHEN 加载 `八、5` THEN 账龄表行为 6 档账龄 + `小 计`(subtotal) + `减：坏账准备`(data) + `合 计`(total)
2. WHEN 加载 `八、5` THEN 分类披露拆为 `（2）...` 与 `（2）...（续：期初数）` 两张 6 列表，各带 `_column_groups`
3. WHEN 加载 `八、5` THEN 组合计提示例分表列为 7 列（双期 × 3 值列），账龄行 6 档
4. WHEN 加载 `八、5` THEN 「采用余额百分比或其他组合方法」为 7 列
5. WHEN 加载 `八、5` THEN 变动表为 6 列且带 `本期变动金额` 分组
6. WHEN 加载 `八、5` THEN 新增 `（7）应收账款转移继续涉入形成的资产、负债的金额` TAB，`text_sections` 同步追加对应标题
7. WHEN 修订脚本重复执行 THEN 结果逐字节相等（幂等）

### Requirement 6 — 附注模板多级表头透传（复用既有机制，不新造）

**User Story:** 作为审计助理，我在附注模块尚未从底稿同步时，也要看到模板自带的两级表头。

> 实测结论：透传机制 `disclosure_engine._carry_seed_column_meta` /
> `_SEED_COLUMN_META_KEYS` **已由 spec `f2-inventory-disclosure-template-alignment` R5 实现**，
> 并已在 `generate_notes` / `get_note_detail` 的多表分支调用。
> 本 spec **不重复实现**，仅复用并为国企 `八、5` 补契约测试。

#### Acceptance Criteria
1. WHEN 模板表含 `_column_groups` THEN 生成的 `table_data._tables[n]` 带上该键
2. IF 模板表无该键 THEN built table 键集合不变（零回归）
3. WHEN 国企 `八、5` 三张宽表（分类披露 / 组合分表 / 变动表）走透传 THEN 分组区间与 R5 一致

### Requirement 7 — 契约测试与回归

**User Story:** 作为质量控制复核合伙人，我要有测试锁定列头字面与表数量，避免下次重建模板再次压扁。

#### Acceptance Criteria
1. WHEN 运行 `d2NoteSectionMap.spec.ts` THEN 全绿（含上市版遗留的 5 条过期断言已按现状修正）
2. WHEN 断言国企载荷 THEN 固定表数量 = 11 张（不含动态组合分表），`_note_texts` 覆盖 9 个子节键
3. WHEN 断言国企组合分表 / 其他组合表 / 变动表 THEN 列数分别为 7 / 7 / 6（含标签列），label 与源模板逐字一致
4. WHEN 断言附注模板 THEN `八、5` 表名集合、行口径、`_column_groups` 符合 R5；修订脚本连跑两次结果相等
