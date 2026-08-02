# Requirements Document

## Introduction

F 类循环（F0 存货循环函证 / F1 预付账款 / F2 存货 / F3 应付票据 / F4 应付账款 / F5 营业成本）的
「四表入库 → 底稿刷新取数 → 披露表 → 推送附注」全链条**只有 F1/F2 接了平台共享件**，
F3/F4/F5 仍是各自硬编码科目前缀的方言实现。本 spec 把 G/K/D/N 循环已跑通的范式推广到
F3/F4/F5，并复核 F1/F2 的残余缺口、F 类四个附注章节与源模板的一致性、以及 F1~F5 的公式预设。

### 调查已确认的事实（DB / 源 xlsx 实证，本 spec 的裁决基准）

**① 报表行映射真源 = `report_config`（DB 只读实证，四准则一致除注明）**

| 循环 | 科目 | 报表行 | 公式 |
|------|------|--------|------|
| F1 预付账款 | 1123 | `BS-008` | `TB('1123','期末余额')`（不减备抵） |
| F2 存货 | 1401~1499 | `BS-010` | `SUM_TB('1401~1499','期末余额')`；`listed_standalone` 另 `- TB('1416','期末余额')` |
| F3 应付票据 | 2201 | **`BS-044`** | `TB('2201','期末余额')` |
| F4 应付账款 | 2202 | **`BS-045`** | `TB('2202','期末余额')` |
| F5 营业成本 | 6401~6499 | **`IS-002`** | `SUM_TB('6401~6499','本期发生额')` |

**② 客户子科目天然对应审定表分类行**（同 D1 `1121.0x`／F1 `1123.0x`／G7 `1511.0x` 范式）

- `2201.01 应付票据_银行承兑汇票` / `2201.02 _商业承兑汇票` / `2201.03 _信用证`
  → F3-1 审定表三个分类行。**`2201.03 信用证` 是活体大额科目**（项目 `0ec33ac9` 期末
  93,443,600.00，占 2201 的 92%；`a7fc75e5` 期末 34,137,381.81），而 F3-1 现在只有
  银行承兑 / 商业承兑两个固定行，信用证行仅在 F3-2 明细录入后才动态出现。
- `2202.01 应付货款` / `.02 暂估应付款` / `.03 红字信息表` / `.04 预提供应商返利` /
  `.11 工程设备款` / `.96 门店统购款` / `.97 进项税` / `.98 商务系统`
  → F4-1 审定表「一、按照性质分类」五桶（货款 / 工程款 / 设备款 / 服务费 / 其他）。

**③ 叶子勾稽自洽**（实证 4 个项目）：`2201` 叶子和 == 父科目额；`2202` 按方向带符号
叶子和 == 父科目额（`0ec33ac9`：232,903,579.67 + 24,864,901.78 − 482,915.48 −
3,096,093.59 = 254,189,472.38 ✓）。

**④ 负债科目两种符号约定并存**：`0ec33ac9` 存正数、`12c15a96` / `2aa00f57` 存负数
（同一份数据两种存法）→ 聚合结果必须 `abs()` 归一。

**⑤ F5 损益类不能用 Σ借−Σ贷**：实证 `2aa00f57` 的 `6401` 四行 `debit_amount ==
credit_amount`（年末结转损益），`debit − credit` 恒为 0.00。正确口径 = 叶子
`debit_amount` 之和（404,670,957.97 − 768,809.84 = 403,902,148.13 = 父科目借方）。

**⑥ F5 科目编码语义在项目间冲突**（同存货变体范式）：`6402` 在 6 个项目是「其他业务成本」、
在 `df5b8403` 是「其他业务支出」，另有项目把「其他业务成本」编在 `6404`。故
`LIKE '6401%'` 既漏 6402 也漏 6404，必须走 `IS-002` 的 `6401~6499` 区间 + 按名称归类。

**⑦ 附注模板 F 类四章节结构已齐备**（前序 spec 成果，本 spec 只复核不重建）：
`五、7`/`八、7` 预付款项、`五、9`/`八、10` 存货、`五、36`/`八、36` 应付票据、
`五、37`/`八、37` 应付账款 —— `columns` 齐备、`flat`/`group` 已表态、`guidance` 有、
`_aligned_by` 已标记。**F0 / F5 源模板确认无「附注披露信息」sheet**（F0 是 11 张函证程序
底稿、F5 是 10 张成本程序底稿），不得为其新建披露 Tab 或附注章节。

**⑧ F4 披露两版口径不对称（源 xlsx 实证，非缺陷）**：上市 `附注披露信息(上市公司)` 主表按
**款项性质**列示（A6 `项 目` / C6 `期末余额` / D6 `上年年末余额`，行 货款/工程款/
可无限量添加行/合 计）；国企主表按**账龄**列示（A6 `账  龄` / C6 `期末余额` /
D6 `期初余额`）。两版都附「账龄超过 1 年的重要应付账款」表（取自 F4-5）。

### 范围外发现（本 spec 只报告与规避，不修改）

- **G1 `trial_balance` 部分项目父子双算**：`2aa00f57` 的 `2202` = 534,617,953.54
  （= 父额 267,308,976.77 × 2）、`6401` = 1,211,706,444.39（= 四行全加 = 真值 3 倍）。
  `trial_balance_service` 现版本已有 `leaf_cond` 叶子过滤 → 这些是**旧版 recalc 写入的
  陈旧数据**，需重跑 recalc，属平台级 data-hygiene。
- **G2 `trial_balance` 损益类发生额口径缺陷**：`trial_balance_service` 第 1b 段用
  `debit_amount - credit_amount`，在含年末结转损益的全年账上结构性恒为 0 → 一旦重跑
  recalc，F5/N4/N5/K8~K13/I6 的「试算平衡表数」会全部归零。正确口径 = 叶子
  `debit_amount` 之和。属平台级缺陷，须另立 spec。

因 G1/G2 存在，F 类审定表的「试算平衡表数」核对行**不能以 `trial_balance` 为唯一口径**，
必须沿用 F1 已验证的做法：并列展示「叶子聚合口径」与「`trial_balance` 口径」，两者不一致
时在溯源面板显式检出差异，让审计师看到而不是被静默误导。

---

## Requirements

### Requirement 1: F3 应付票据四表取数走共享件

**User Story:** 作为审计助理，我希望四表入库后打开 F3 底稿就能看到应付票据按票据种类
预填的审定表未审数与试算核对基准，而不是一张全零表。

#### Acceptance Criteria

1.1 WHEN 后端渲染 F3 底稿 THEN 系统 SHALL 通过 `four_table.resolve_report_line_accounts`
    以 `ReportLineAccountSpec(row_code='BS-044', fallback_gross=('2201',))` 解析科目，
    而不是使用硬编码常量 `_F3_ACCOUNT = "2201"`。
1.2 WHEN 解析出科目码后 THEN 系统 SHALL 用 `four_table.select_leaves` 做叶子聚合
    （严格点号边界），不得使用 `code.startswith(prefix)` 裸前缀判定。
1.3 WHEN 聚合负债科目金额 THEN 系统 SHALL 对结果取绝对值归一，以同时兼容正数与负数两种
    存储约定。
1.4 WHEN 项目科目表存在 `2201` 的子科目 THEN 系统 SHALL 输出 `adjudication_prefill`，
    按叶子科目**名称**归类到票据种类桶（银行承兑 / 商业承兑 / 信用证 / 供应链 / 其他），
    每桶给出期初与期末两期金额。
1.5 WHEN 项目科目表只有父科目 `2201` 而无子科目 THEN 系统 SHALL 不输出预填（宁缺勿造），
    审定表回退手工录入，但试算核对行仍显示总额。
1.6 WHEN 渲染完成 THEN 系统 SHALL 输出 `tb_source_codes` 溯源信息（含 `row_code`、
    `resolved_from`、`gross_standard`、`gross` 原始码前缀集），且该输出 SHALL 有前端消费方。
1.7 WHEN 输出 `tb_values` THEN 系统 SHALL 同时给出期初与期末两期（F3-1 是双期表），
    并同时给出「叶子聚合口径」与「`trial_balance` 口径」两个值供交叉核对。

### Requirement 2: F4 应付账款四表取数走共享件

**User Story:** 作为审计助理，我希望四表入库后 F4-1 审定表的「按性质分类」区能按客户
子科目自动预填，并且期初、期末两期都有数。

#### Acceptance Criteria

2.1 WHEN 后端渲染 F4 底稿 THEN 系统 SHALL 以
    `ReportLineAccountSpec(row_code='BS-045', fallback_gross=('2202',))` 解析科目。
2.2 WHEN 取数 THEN 系统 SHALL 委托 `four_table.select_leaves` 叶子聚合并 `abs()` 归一。
2.3 WHEN 项目科目表存在 `2202` 子科目 THEN 系统 SHALL 输出 `adjudication_prefill`，
    按叶子科目**名称**归类到 F4-1 源模板的五个性质桶，且每桶给出期初 / 期末两期金额。
2.4 WHEN 归类规则声明 THEN 系统 SHALL 把规则集中在单一真源 dataclass 中，每条规则带
    `source_ref` 指向源 xlsx 单元格，顺序即优先级，并支持 `exclude_keywords` 否决词。
2.5 WHEN 某叶子科目名同时命中多个桶关键字（实证 `2202.11 应付账款_工程设备款` 同时含
    「工程」与「设备」）THEN 系统 SHALL 按声明顺序取首个命中桶，并在溯源面板展示
    `叶子科目 → 桶` 的归类结果，使审计师可复核与手工调整。
2.6 WHEN 渲染完成 THEN 系统 SHALL 输出 `tb_source_codes`，且有前端消费方。
2.7 WHEN 输出试算核对基准 THEN 系统 SHALL 同时给出期初与期末（现实现只有期末），
    以填满 F4-1 的双期「试算平衡表数」行。

### Requirement 3: F5 营业成本四表取数纠错

**User Story:** 作为审计助理，我希望 F5-1 的「试算平衡表数」是完整的营业成本（含其他业务
成本），而不是只有主营业务成本导致差异数常亮假告警。

#### Acceptance Criteria

3.1 WHEN 后端渲染 F5 底稿 THEN 系统 SHALL 以
    `ReportLineAccountSpec(row_code='IS-002', fallback_gross=('6401~6499',))` 解析科目，
    覆盖 6401 主营业务成本与 6402/6404 其他业务成本。
3.2 WHEN 聚合损益类金额 THEN 系统 SHALL 取叶子的 `debit_amount` 之和（保留符号），
    SHALL NOT 使用 `debit_amount - credit_amount`（含年末结转损益的全年账上恒为 0）。
3.3 WHEN 归类主营业务成本与其他业务成本 THEN 系统 SHALL 按叶子科目**名称**归类
    （因 `6402` 在项目间既可能是「其他业务成本」也可能是「其他业务支出」，另有项目把
    「其他业务成本」编在 `6404`），SHALL NOT 按编码写死。
3.4 WHEN 渲染完成 THEN 系统 SHALL 输出 `tb_source_codes` 与两段（主营 / 其他）的
    `adjudication_prefill`，且有前端消费方。
3.5 WHEN `trial_balance` 口径与叶子聚合口径不一致 THEN 系统 SHALL 两个值都下发，
    由前端溯源面板显式提示差异，SHALL NOT 静默取其一。
3.6 现有 `_ROLLFORWARD_ACCOUNTS` 的裸 `code.startswith(prefix)` 判定 SHALL 改为共享件的
    严格点号边界判定。

### Requirement 4: F1/F2 残余缺口补齐

**User Story:** 作为审计助理，我希望 F1/F2 的取数溯源与 F3/F4/F5 一致，能看到父子勾稽是否成立。

#### Acceptance Criteria

4.1 WHEN F1/F2 渲染 THEN 系统 SHALL 输出 `parent_check`（叶子和 vs 父科目额的差额），
    与 G 循环范式一致。
4.2 WHEN F2 解析科目 THEN 系统 SHALL 确认走 `BS-010` 报表行而非兜底常量，并在
    `tb_source_codes` 中标注 `resolved_from`。
4.3 F1/F2 既有的取数行为 SHALL 保持逐字等价（既有测试零回归）。

### Requirement 5: 公式预设纠错与补齐

**User Story:** 作为现场经理，我希望公式管理页里 F 类每张底稿的取数公式都指向正确科目，
并且底稿之间的取数联动与源模板的单元格引用一致。

#### Acceptance Criteria

5.1 WHEN 检查 F5 预设 THEN 系统 SHALL 把 `TB('6401','期初余额')` / `TB('6401','期末余额')`
    改为损益口径 `TB('6401','本期发生额')`（损益类无期初期末概念）。
5.2 WHEN 检查 F2 预设 THEN 系统 SHALL 修正三类科目码语义错误：
    (a) `生产成本明细表` / `直接人工分析表` / `制造费用明细表` 引用 `TB('1402',...)` 并
        描述为「在产品（生产成本）」，而 `1402` 在两个标准科目表变体中都是**在途物资**；
    (b) 5 个盘点类块把 `1403` 描述为「库存商品」，而 `1403` 在两变体中都是**原材料**；
    (c) `存货审定表` 首两条 `TB_SUM('1401~1461',...)` 与同块后两条 `1401~1499` 口径不一致。
5.3 WHEN 检查 F3/F4 明细表预设 THEN 系统 SHALL 删除虚构辅助维度值
    `AUX('2201','供应商','TOP1',...)` / `AUX('2202','供应商','TOP2',...)` 等
    （`TOP1`/`TOP2`/`TOP3` 不是真实供应商名，取数恒空），改为 `XX单位` 占位范式（同 F1）。
    同理处理 F2 的 `AUX('1403','存货分类','A类',...)` 与 `AUX('1403','库龄','长库龄',...)`。
5.4 WHEN 补 F3 预设 THEN 系统 SHALL 新增审定表 ← F3-2 明细表的 `WP()` 联动
    （源模板 F3-1 的 B/F/G/H/I 列全部是 `SUMPRODUCT` 自 `明细表F3-2`），
    并新增两个披露 sheet 块（现在完全无预设）。
5.5 WHEN 补 F4 预设 THEN 系统 SHALL 新增审定表 ← F4-2 明细表的 `WP()` 联动
    （源模板按性质区 F/G/H 列是 `SUMIF` 自 `明细表F4-2`、按账龄区引 `明细表F4-2!N32:X32`）、
    审定表 ← F4-5 长期挂账的 `WP()` 联动，并新增两个披露 sheet 块。
5.6 WHEN 补 F5 预设 THEN 系统 SHALL 新增 F5-1 ← F5-2 主营业务成本月度明细表 /
    ← F5-3 其他业务成本明细表 / ← F5-4 调整分录汇总的 `WP()` 联动。
5.7 明细表块 SHALL NOT 反向引用审定表（防公式成环，同平台既有约定）。
5.8 所有改动 SHALL 通过幂等脚本落地（带 `--dry-run` / `--check`），SHALL NOT 手改 JSON。

### Requirement 6: 披露表逻辑复核与增强

**User Story:** 作为审计助理，我希望披露表的行集合能跟随项目实际情况（票据种类、款项性质、
账龄档位）动态适配，而不是写死档位数。

#### Acceptance Criteria

6.1 WHEN F3 披露表渲染 THEN 系统 SHALL 在项目存在 `2201.03 信用证` 等第三类票据时
    自动列示该行，而不要求先手工录入 F3-2 明细。
6.2 WHEN F4 国企披露表渲染 THEN 账龄档位 SHALL 跟随项目账龄枚举配置（3 年段 / 5 年段 /
    自定义），SHALL NOT 写死 4 档。
6.3 WHEN F4 上市披露表渲染 THEN 按性质行 SHALL 支持动态增删（源模板 A9 逐字
    「可无限量添加行」），并复用平台共享件 `composables/shared/dynamicAdjudicationRows.ts`。
6.4 WHEN 披露表金额格可编辑 THEN SHALL 使用 `WpAmountInput`，
    SHALL NOT 使用 `el-input-number :formatter`（该 prop 在 EP 2.13.6 不存在）。
6.5 WHEN 披露表展示只读金额 THEN SHALL 走 `displayPrefs.fmtAmount()` 单一真源。
6.6 F1/F2/F3/F4 披露表 SHALL 各有一个内部勾稽面板，规则取自源模板公式或
    `note_check_preset_formulas.json` 的 F7-x 校验预设。

### Requirement 7: 附注同步链路复核

**User Story:** 作为审计助理，我希望在披露表点「同步到附注」后，附注对应章节的表格结构、
列头、行集合、文本框内容都与源模板一致。

#### Acceptance Criteria

7.1 WHEN 复核 F 类四个附注章节 THEN 系统 SHALL 用 openpyxl 直读源 xlsx 与模板 headers、
    同步载荷 `columns` 三向比对，并配反向自检。
7.2 WHEN 同步载荷推送 THEN 每张子表名 SHALL 与 `note_template_{listed,soe}.json` 的
    `tables[].name` 逐字一致（否则产生孤儿子表）。
7.3 WHEN 动态区行集合变化（票据种类增减 / 账龄档位切换 / 性质行增删）THEN 系统 SHALL
    整表覆盖推送，并对不再推送的历史表名上报 `_removed_table_keys`（与本次推送键求差集）。
7.4 WHEN 推送 `_note_texts` THEN 每条 SHALL 带中文 `title`，空文本 SHALL 被过滤。
7.5 F0 / F5 SHALL NOT 有披露 Tab 或附注同步链路（源模板无披露 sheet），并 SHALL 在
    平台守卫 `CYCLES_WITHOUT_DISCLOSURE` 中登记依据。

### Requirement 8: 守卫与实测

**User Story:** 作为质量控制复核合伙人，我希望这些修正有守卫钉死，不会被后续改动静默回退。

#### Acceptance Criteria

8.1 WHEN 新增科目定位逻辑 THEN SHALL 有后端守卫断言「科目码 ∈ 标准科目表」且
    「科目码 ∈ 本循环报表行引用的科目集合」，并含反向自检（打乱规则顺序应打红）。
8.2 WHEN 新增分类桶规则 THEN SHALL 有参数化测试覆盖两个标准科目表变体，并有 PBT
    验证「各桶金额之和 == 叶子合计」。
8.3 WHEN 修改公式预设 THEN SHALL 有守卫断言科目码与 `report_config` 一致、sheet 名与源
    xlsx tab 名一致、公式语法合法、无成环。
8.4 WHEN 前端新增取数消费点 THEN SHALL 有守卫扫描宿主模板确认必需 props 已传递
    （`:html-data` / `:project-id`），并断言 composable 返回键集 ⊇ 组件解构键集。
8.5 WHEN 完成实现 THEN SHALL 用真实 DB 直跑 render 验证多个项目的取数结果，
    并用浏览器实测披露→附注推送链路，实测数据 SHALL 完整复原。
8.6 SHALL 新增 CI job 覆盖本 spec 的后端与前端守卫。

---

## Glossary

| 术语 | 含义 |
|------|------|
| 四表库 | `tb_balance`（余额表）/ `tb_ledger`（序时账）/ `tb_aux_balance`（辅助余额）/ `account_chart`（科目表）四张导入表 |
| 报表行 | `report_config` 中的一行（如 `BS-044`），其 `formula` 声明该行由哪些标准科目构成 |
| 原始码 | 客户科目表里的编码，点号分级（`2201.03`），存于 `tb_balance.account_code` |
| 标准码 | 平台标准科目编码，横杠分级（`1231-04`），存于 `trial_balance.standard_account_code` |
| 叶子科目 | 没有被映射子科目的最明细行；平台铁律「只汇总叶子」，叶子和须等于父科目额 |
| `tb_source_codes` | render 下发的取数溯源结构（报表行 / 解析来源 / 标准码 / 原始码前缀） |
| `adjudication_prefill` | render 下发的审定表未审数预填结构（按分类桶给期初 / 期末） |
| `parent_check` | 叶子聚合额与父科目额的差额，用于自证取数正确 |
| 分类桶 | 审定表 / 披露表的分类行（如 F4 五性质桶），按叶子科目名称归类 |
| 账龄枚举 | 项目级账龄档位配置（3 年段 / 5 年段 / 自定义），见 `composables/useAgingConfig` |
| 孤儿子表 | 同步载荷的子表名与附注模板 `tables[].name` 不一致时产生的表，附注永空且数据丢失 |
| F7-x | `note_check_preset_formulas.json` 中 F 类披露的校验预设编号 |
