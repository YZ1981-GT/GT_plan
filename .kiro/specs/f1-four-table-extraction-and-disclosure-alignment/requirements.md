# Requirements Document

## Introduction

F1「预付款项」循环的披露/附注结构已由归档 spec `f1-prepayment-disclosure-template-alignment`
对齐过一轮（`fix_note_prepayment_structure.py --check` 当前零欠账），账龄枚举单一真源
（`useF1AgingScope`）与自动同步（`useDisclosureAutoSync` 包装 save）也已贯通。本 spec 收口
**剩余三类欠账**，全部经 DB 只读实证 + 源 xlsx openpyxl 直读确认：

**一、四表库取数链路仍是硬编码方言，且科目映射链路只用了一半**

`_f1_prepayment.py` 的实现与平台共享件 `app/services/four_table/`（K1 spec Wave 1 已建成、
D1 已委托）完全脱节：

1. **前缀集硬编码** `_F1_TB_PREFIXES = ("1123", "1401", "2202")`，`_resolve_prepaid_codes`
   虽然解析了 `BS-008` 的报表映射，但解析结果**只喂给 `trial_balance`**，`tb_balance`
   聚合仍走硬编码前缀 → 客户把预付编到别的原始码时 `tb_balance` 侧取数落空。
2. **缺 `account_mapping` 反解**：报表公式给的是**标准码**（横杠分级），`tb_balance` 存的是
   **原始码**（点号分级）→ 不反解就无法正确前缀匹配（这正是 D1/K1 已解决的问题）。
3. **叶子判定与前缀匹配都缺点号边界**：`_is_leaf` 用 `other.startswith(code)`、聚合用
   `code.startswith(prefix)` → `1123.1` 会被 `1123.10` 误判为非叶子；前缀 `2202` 会误吃
   `22020`。共享件 `four_table.leaf_aggregation` 已严格要求 `code == p or code.startswith(p + '.')`。
4. **完全没有 `_build_adjudication_prefill`** —— 违反平台铁律「X-1 审定表未审数从
   `tb_balance` 明细子科目预填」。而 F1 恰恰是**最适合**该铁律的循环：DB 实证 `1123`
   子科目树天然对应 F1-1「按性质分类」五行：

   | 原始码 | 科目名 | → F1-1 性质行 |
   |--------|--------|---------------|
   | `1123.01` | 预付账款_预付货款 | 货款 |
   | `1123.02.01` | 预付账款_长期资产款_一次购置 | 设备款 |
   | `1123.02.02` | 预付账款_长期资产款_分期购置 | 设备款 |
   | `1123.02.03` | 预付账款_长期资产款_工程款 | 工程款 |
   | `1123.03` | 预付账款_短期待摊费用 | 服务费 |
   | `1123.99` | 预付账款_其他 | 其他 |

   （项目 `0ec33ac9`/2025 实测：`1123` 期末 13,576,792.21 = 叶子 `1123.01` 13,576,792.21；
   项目 `2aa00f57`/2025：期末 1,301,918.43 = `1123.01` 2,430.64 + `1123.03` 1,299,487.79。
   两项目均逐分自洽。）
5. **减值准备从未取数**：标准科目表有 `1231-04 坏账准备-预付账款`（`direction='credit'`），
   但 `BS-008` 四个准则下的公式一律只有 `TB('1123','期末余额')`（**不减备抵**）→ 两个披露表
   的「减：减值准备」行、上市②表「减值准备」列、国企逐段坏账准备列、国企③表「减值准备」列
   **全部只能手工录入**。
6. **`tb_source_codes` 是 dead output**：render 已输出 `project_context.tb_source_codes`，
   前端 grep **0 命中**。

**二、公式管理预设只有一条通用样板**

`prefill_formula_mapping.json` 全库 210 条映射中 F1 仅 **1 条**（`审定表F1-1`，5 个通用
cell：期初/未审/AJE/RJE/上年审定，全部只引用 `1123`）。对比 F2 有 18 条、N1 的 F1-1 块含
`WP()` 跨底稿取数。F1 缺：坏账 `1231-04`、借贷发生额、往来单位 `AUX()`、F1-1←F1-2 的
`WP()`、F1-4 跨循环（存货 `1401` / 应付 `2202` / 存货采购）。

**三、披露表三处与源模板/平台铁律不一致**

以 `backend/wp_templates/F/F1 预付账款.xlsx` 的 `附注披露信息(上市公司)` /
`附注披露信息(国企)` 为唯一裁决者（`基础数据/附注模版/*.md` 在本仓库不存在），
逐格比对后确认：

| # | 变体 | 问题 | 源模板证据 |
|---|------|------|-----------|
| 1 | listed | 按账龄表两级表头父组名写成 `期末余额` / `上年年末余额` | 源 `B8=期末数`、`D8=上年年末数` |
| 2 | 两版 | 标签列与金额列字面丢了源模板空格 | listed `A8=账  龄`、`B9=金  额`；soe `A8=账  龄`、`B10=金 额`（单空格） |
| 3 | listed | ③前五名「汇总披露格式」与「分别披露格式」**同时推送** | 源 `A23=（…汇总**或**分别披露…）`、`A24=汇总披露格式：`、`A26=分别披露格式：` —— 二选一 |
| 4 | 两版 | 8 处金额控件是 `el-input-number`（千分符从未生效，平台已双证该 prop 不存在） | `WpAmountInput.vue` 为平台唯一正解 |
| 5 | 两版 | **无勾稽面板** —— `note_check_preset_formulas.json` 的 F7-1~F7-14（listed/soe 双份）14 条规则全未落地为界面校验 | D1/H1/J1/N1 均已有 `XDisclosureConsistencyPanel` 范式 |

本 spec 只做 F1；F2/F3/F4 沿用本 spec 建立的范式另立（F0 存货循环函证 / F5 营业成本源模板
**无附注 sheet**，已确认属正常，不在范围内）。

## Glossary

| 术语 | 含义 |
|------|------|
| 原始码 | `tb_balance.account_code` / `account_mapping.original_account_code`，客户自有编码，**点号**分级（`1123.02.01`） |
| 标准码 | `trial_balance.standard_account_code` / `report_config` 公式引用码，**横杠**分级（`1231-04`） |
| 科目映射模块 | `account_mapping` 表（project 级，原始码 → 标准码） |
| 报表映射规则 | `report_config.formula`（按 `applicable_standard`），把标准码组合成报表行；F1 = `BS-008 预付款项` |
| 叶子科目 | `tb_balance` 中不存在以「本码 + `.`」开头的同数据集兄弟行的最明细行 |
| 备抵科目 | 贷方性质的减值/坏账科目；F1 侧为 `1231-04 坏账准备-预付账款` |
| 账龄枚举模块 | `useF1AgingScope`（表级覆盖 > 项目级 `useAgingConfig(projectId,'F1')` > `THREE_YEAR`），3年段/5年段/自定义 2~10 段 |
| 三向比对 | 源 xlsx 单元格文本 ↔ `note_template` `headers`/`columns` ↔ 同步载荷 `columns` 逐字一致 |
| F7-* | `note_check_preset_formulas.json` 中 `note_section='五、7'` 的 14 条校验预设（listed / soe 各一份） |
| 动态插行区 | 源模板「可无限量添加行」/空白行骨架对应的底稿动态增删行区块 |

## Requirements

### Requirement 1: F1 科目定位改由报表映射规则驱动

**User Story:** 作为审计助理，我希望四表入库后 F1 的取数科目由报表映射规则决定，
这样客户把预付编在自定义科目上时底稿也能取到数。

#### Acceptance Criteria

1.1 WHEN F1 render 解析科目 THEN 系统 SHALL 复用
`four_table.resolve_report_line_accounts(ctx, ReportLineAccountSpec(row_code='BS-008', …))`
经「报表行 → `report_config.formula`（按项目 `applicable_standard_v2` 派生的准则列表精确匹配）
→ 标准码集 → `account_mapping` 反解 → 客户原始码集」链路定位，SHALL NOT 保留硬编码
`_F1_TB_PREFIXES` 中的 `1123`。

1.2 WHEN 报表公式解析出的标准码集拆分原值/备抵 THEN 系统 SHALL 使用共享
`split_gross_provision`（`direction=='credit'` → 名称含「坏账准备/减值准备/信用减值」
→ 码族 `1231` 三级优先），且原值集与备抵集无交集。

1.3 WHEN `BS-008` 公式不含备抵科目（实证四个准则均为 `TB('1123','期末余额')`）
THEN 系统 SHALL 用兜底标准码 `1231-04` 并把该侧 `provision_resolved_from` 标为 `fallback`。

1.4 IF 备抵侧反解退化为宽前缀（该项目 `account_mapping` 无 `1231-04` 记录 —— 实证 9 个项目
**全部**如此）THEN 系统 SHALL 叠加名称过滤「预付」，避免把应收票据/应收账款/其他应收款的
坏账（`1231.01/.02/.03`，实证均存在且金额重大）计入 F1。

1.5 WHEN 四表库无 `预付` 备抵科目 THEN 减值准备预填 SHALL 为「无预填」（宁缺勿造），
SHALL NOT 写 0 占位、SHALL NOT 清空既有手工值。

1.6 IF 链路任一环失败（无 `report_config` 行 / `account_chart` 空 / `account_mapping` 空 /
DB 异常）THEN 系统 SHALL 回退到与改动前等价的兜底科目（原值 `1123`）并继续渲染，绝不抛错。

1.7 WHEN render 返回 THEN 输出 SHALL 含结构化 `tb_source_codes`（报表行 / 公式原文 /
标准码 / 原始码 / 解析来源），且该字段 SHALL 被前端界面消费展示（不得继续是 dead output）。

### Requirement 2: tb_balance 聚合改为共享叶子口径

**User Story:** 作为现场经理，我希望 F1 从四表库带出的金额等于科目余额表期末余额，
这样才能和总账核对。

#### Acceptance Criteria

2.1 WHEN 聚合 `tb_balance` THEN 系统 SHALL 使用共享
`four_table.leaf_aggregation`（`to_leaf_rows` / `select_leaves` / `aggregate_leaves`），
SHALL NOT 保留本地 `_is_leaf`（其 `startswith` 缺点号边界）。

2.2 WHEN 前缀过滤 THEN 系统 SHALL 严格要求点号边界（`code == p` 或 `code.startswith(p + '.')`），
使前缀 `2202` 不误吃 `22020`。

2.3 WHEN 叶子集合确定 THEN 叶子金额之和 SHALL 等于该前缀父科目行金额
（实证 `0ec33ac9`：13,576,792.21；`2aa00f57`：1,301,918.43）。

2.4 WHEN 聚合备抵科目 THEN 系统 SHALL 对**聚合结果**取绝对值（`tb_balance` 存在
「无符号 + 方向列」与「已带符号」两种约定并存 —— 实证 `0ec33ac9` 的 `1231.02` 为正、
`12c15a96` 的同科目为负），SHALL NOT 在行级做方向翻转（会破坏 2.3 勾稽）。

2.5 WHEN 取 F1-4 跨循环锚点（存货 `1401` / 应付账款 `2202`）THEN 系统 SHALL 走同一叶子口径，
应付侧继续取绝对值供正数展示（与改动前行为等价）。

### Requirement 3: F1-1 审定表「按性质分类」四表预填

**User Story:** 作为审计助理，我希望四表入库后打开 F1-1 就能看到按性质分类的未审数，
并能显式重新带入。

#### Acceptance Criteria

3.1 WHEN render 构建预填 THEN 系统 SHALL 遍历 `1123` 的**全部叶子**，按科目名关键字归入
`NATURE_ROWS` 五桶（货款 / 工程款 / 设备款 / 服务费 / 其他），未命中关键字的叶子归「其他」，
使五桶之和 == `1123` 叶子合计（不丢科目）。

3.2 WHEN 归类 THEN 判定顺序 SHALL 为「工程 → 设备/长期资产/购置 → 服务/待摊/费用/保险/租金
→ 货款/材料/商品/采购 → 其他」（工程优先于设备：实证 `1123.02.03 长期资产款_工程款`
同时含「长期资产」与「工程」，应归工程款）。

3.3 WHEN 预填 THEN 系统 SHALL 同时给出期初（`opening_balance`）与期末（`closing_balance`）
两组值，供 F1-1「期初数-未审数」「期末数-未审数」两列。

3.4 WHEN F1-1 已存在任一 `F1-adj-nature-*-priorUnadjusted` / `-currentUnadjusted` 手工值
THEN 系统 SHALL NOT 覆盖（手工优先）。

3.5 WHEN F1-2 明细已编制（`crossSheet.detailRowCount > 0`）THEN 优先级 SHALL 为
「手工 > F1-2 明细聚合 > 四表库预填」（明细更细且已审定）。

3.6 WHEN 用户点击 F1-1 的「从四表库带入未审数」按钮 THEN 系统 SHALL 把预填值**持久化**为
未审数，只覆盖预填中出现的性质桶、不清零未出现的桶。

3.7 WHEN 四表库无 `1123` 叶子数据 THEN 预填 SHALL 为空对象（不写 0 占位）。

### Requirement 4: 减值准备四表取数与溯源

**User Story:** 作为审计助理，我希望预付款项的坏账准备也能从四表库带出，而不是每次手抄。

#### Acceptance Criteria

4.1 WHEN 备抵科目解析成功且四表库有数据 THEN 上市披露表 SHALL 在
`F1-note-listed-impairment-provision` / `-prior` **无持久化值**时用四表库期末/期初预填。

4.2 WHEN 国企披露表的减值准备是**逐账龄段**列（四表库无账龄维度）THEN 系统 SHALL NOT
按段编造分摊（宁缺勿造），而 SHALL 在溯源面板展示四表库总额，并由勾稽规则校验
「逐段减值准备合计 vs 四表库 `1231-04` 期末」。

4.3 WHEN 减值准备预填生效 THEN 溯源面板 SHALL 显示解析来源（`report_config` / `fallback`）
与实际命中的原始码，使审计师能判断该数是否可信。

### Requirement 5: 公式管理预设补齐

**User Story:** 作为现场经理，我希望在底稿当页的公式管理里看到 F1 的完整取数公式，
可追溯可覆盖。

#### Acceptance Criteria

5.1 WHEN 查看 F1-1 公式预设 THEN 系统 SHALL 提供坏账准备期初/期末
（`TB('1231-04','期初余额')` / `TB('1231-04','期末余额')`）与借贷发生额
（`TB('1123','本期借方')` / `TB('1123','本期贷方')`）条目。

5.2 WHEN 查看 F1-1 公式预设 THEN 系统 SHALL 提供跨底稿取数
`WP('F1','明细表F1-2', …)`（期末审定合计）与 `WP('F1','长期挂款检查表F1-5', …)`（1 年以上审定余额）。

5.3 WHEN 查看 F1-2 明细表公式预设 THEN 条目 SHALL NOT 含 `WP(`（防 F1-1 ↔ F1-2 循环），
只含 `TB()` / `AUX('1123','客户',…)`（实证 `tb_aux_balance` 的 1123 维度为「客户」5851 行）。

5.4 WHEN 查看 F1-4 实质性分析公式预设 THEN 系统 SHALL 提供存货 `TB('1401','期末余额')`、
应付账款 `TB('2202','期末余额')`、存货采购 `TB('1401','本期借方')` 条目
（与 render 下发的 `inventory_balance_current` / `payable_balance_current` 同口径）。

5.5 WHEN `convert_prefill_presets()` 收敛 THEN F1 条目 SHALL 全部归入 `workpaper:F1`
且 `formula_type` 为受支持类型。

### Requirement 6: 披露表列头对齐源模板字面

**User Story:** 作为业务合伙人，我希望附注里的表头和致同模板逐格一致。

#### Acceptance Criteria

6.1 WHEN seed/推送上市按账龄表 THEN 两级表头父组名 SHALL 为 `期末数` / `上年年末数`
（源 `B8` / `D8`），SHALL NOT 继续用 `期末余额` / `上年年末余额`。

6.2 WHEN seed/推送两版按账龄表 THEN 标签列 SHALL 为 `账  龄`（源 `A8`，双空格），
金额列 SHALL 为上市 `金  额`（源 `B9`，双空格）/ 国企 `金 额`（源 `B10`，单空格）。

6.3 WHEN 上述字面改动落地 THEN 数据键（`label` / `end_amount` / `end_pct` /
`prior_amount` / `prior_pct`）SHALL 逐字不变（改 key 会让整表数据丢落点）。

6.4 WHEN 底稿披露 Tab 渲染列头 THEN 界面字面 SHALL 与同步 `columns[].label` /
`group` 同源（禁两处各写一份）。

6.5 WHEN 其余列（上市②③表、国企②③表）比对源模板 THEN 现有列结构 SHALL 保持不变
（已由 F7-9/F7-13 双份预设与源 xlsx 三向印证：上市②无「账龄」「未结算的原因」列、
上市③无「减值准备」列、国企③第 4 列名为「减值准备」）。

### Requirement 7: 上市前五名「汇总 / 分别」二选一

**User Story:** 作为业务合伙人，我希望前五名披露按源模板要求只出一种格式，
不要在附注里同时出现汇总句和明细表。

#### Acceptance Criteria

7.1 WHEN 渲染上市③前五名区块 THEN 界面 SHALL 提供「汇总披露格式 / 分别披露格式」
二选一开关（`el-radio-group`），选择 SHALL 持久化。

7.2 WHEN 选中「分别披露格式」（默认）THEN 载荷 SHALL 推送前五名表，
SHALL NOT 推送 `listed-top5-summary` 汇总句。

7.3 WHEN 选中「汇总披露格式」THEN 载荷 SHALL 推送 `listed-top5-summary` 汇总句，
且 SHALL 把前五名表名放入 `_removed_table_keys`（否则用户切换后附注永久残留过时明细）。

7.4 WHEN 切换模式 THEN 已录入的汇总句覆盖文本与前五名派生数据 SHALL 各自保留
（切回即复原，不清数据）。

### Requirement 8: 披露内部勾稽面板

**User Story:** 作为质量控制复核合伙人，我希望打开披露表就能看到勾稽是否成立、
差异在哪，而不是等附注校验才发现。

#### Acceptance Criteria

8.1 WHEN 渲染两个披露 Tab THEN 系统 SHALL 显示紧凑单行勾稽 bar（通过 / 异常计数）
+ 可折叠明细表，明细含「规则 / 左值 / 右值 / 差异 / 级别 / 索引追溯」。

8.2 WHEN 构建勾稽规则 THEN 规则 SHALL 全部取自 F7-1~F7-14（按变体取对应那份）
与源模板可判定的关系，SHALL NOT 自造审计判断：
- F7-1/F7-2 合计行期末/期初 = 报表「预付款项」期末/期初
- F7-6 各账龄段之和 = 小计（期末/期初各独立）
- F7-7 合计行 = 小计 − 减值准备行（期末/期初各独立）
- F7-8 比例 = 该行金额 ÷ 小计金额 × 100（小计应为 100；减值准备行与合计行不参与）
- F7-3 ②表明细之和 = ②表合计
- F7-11 ②表合计 ≤ ①表 1 年以上各段期末之和（引擎按当前账龄枚举自动适配段集）
- F7-4 ③表明细之和 = ③表合计（逐数值列）
- F7-12 ③表合计账面余额 ≤ ①表小计期末
- F7-13 ③表合计减值准备 ≤ ①表减值准备行期末（**仅国企**；上市③无该列 → 跳过）
- F7-9 完整性（国企②表期末余额 ≠ 0 的行四列不得为空；上市②表仅债务人名称）
- 国企附加：逐段减值准备合计 = 四表库 `1231-04` 期末（仅四表库有数时评估）

8.3 WHEN 相等类规则比较 THEN 容差 SHALL 为 0.01 元；比例类 SHALL 为 0.01 个百分点。

8.4 WHEN 某规则缺少可比数据（如报表数未取到、四表库无备抵）THEN 该规则 SHALL 标为
「未取数 / 跳过」而非「异常」。

### Requirement 9: 金额控件与平台铁律对齐

**User Story:** 作为审计助理，我希望披露表里的金额格显示千分符，输入体验和其它底稿一致。

#### Acceptance Criteria

9.1 WHEN 两个披露 Tab 渲染可编辑**金额**格 THEN SHALL 使用
`components/workpaper/shared/WpAmountInput.vue`，`el-input-number` 计数 SHALL 归零（8 处）。

9.2 WHEN 渲染比例 / 账龄 / 笔数等非金额字段 THEN SHALL NOT 套用 `WpAmountInput`。

9.3 WHEN 只读金额展示 THEN SHALL 继续走 `fmtAmount()` 单一真源（现状已合规，零回归）。

### Requirement 10: 动态插行区与账龄枚举贯通

**User Story:** 作为项目组，我希望账龄段切换后底稿与附注同时跟随，动态行增删也能正确落到附注。

#### Acceptance Criteria

10.1 WHEN 项目/表级账龄枚举为 3年段 / 5年段 / 自定义 2~10 段 THEN 两个披露表的①按账龄表
行集 SHALL 由 `useF1AgingScope.segments` 派生（现状已合规，须有守卫锁死）。

10.2 WHEN ①表账龄段变更 THEN 「小计 / 减：减值准备 / 合计」三行 SHALL 恒在尾部且
`is_total` 标记正确；被移除的段 SHALL NOT 残留为幽灵行。

10.3 WHEN 动态插行区（上市②、国企②）行被增删 THEN 载荷 SHALL 整表覆盖推送，
附注 `sub_table_data` SHALL 与界面行数一致。

10.4 WHEN 上市②/国企②表**清空到无行** THEN 载荷 SHALL 仍推送仅含合计行的表
（该表是模板正式表且底稿有录入区块），SHALL NOT 进入 `_removed_table_keys`。

10.5 WHEN 账龄段为自定义 THEN 披露侧行标签 SHALL 继续走 `disclosureAgingLabels` 单一真源，
未命中时回退段 label。

### Requirement 11: 守卫与端到端实测

**User Story:** 作为质控，我希望这次对齐之后不会被下一次改动悄悄破坏。

#### Acceptance Criteria

11.1 WHEN 运行 `fix_note_prepayment_structure.py --check` THEN 输出 SHALL 为零欠账。

11.2 WHEN 运行 F1 契约测试 THEN P1~P6 SHALL 全绿（子表名逐字 ⊆ 模板 / 章节号存在 /
`group`·`flat` 必表态 / 标签纯文本 / 标签列头对齐 `headers[0]` / 模板 headers 无 HTML）。

11.3 WHEN 运行后端结构守卫 THEN 测试 SHALL 用 openpyxl **直读源 xlsx** 三向比对
两级表头与列字面（含空格），并含反向自检（断言比对确实生效）。

11.4 WHEN 运行取数守卫 THEN 测试 SHALL 覆盖：性质归类五桶不丢科目、点号边界、
备抵名称过滤（断言不含 `1231.02` 金额）、手工优先、依赖缺失时与改动前等价的
characterization。

11.5 WHEN 在真实项目打开 F1-1 THEN 界面 SHALL 显示按性质分类的非零未审数与四表溯源面板；
两个披露 Tab 触发同步后 §五、7 / §八、7 的 `last_sync_at` SHALL 前移，
子表数与 `_sub_table_columns` 的 `group` 字面 SHALL 与本 spec 定义一致。

11.6 WHEN 实测完成 THEN 所有为实测写入的测试数据 SHALL 被复原。
