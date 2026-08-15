# Requirements Document

## Introduction

K 循环（K0~K13，共 14 个底稿）的「四表入库 → 底稿取数 → 披露表 → 附注模块」全链收口。

## Glossary

| 术语 | 本 spec 内的含义 |
|---|---|
| **活错数**（ACTIVE_WRONG） | row_code 写错且该码 formula 非 NULL、解析出的科目在客户科目表存在且方向一致 ⇒ 审定表取到**别的科目的钱**。K9 / K6 属此级 |
| **恒空**（SILENT_EMPTY） | 错码解析出的科目方向与主体相反且未声明 `is_liability`/`gross_direction` ⇒ 被 `split_gross_provision` 判成备抵 ⇒ `gross` 变空 ⇒ 显示 0。K4 属此级 |
| **仅溯源失真**（TRACE_ONLY） | 错码的 formula 为 NULL 或是 `ROW()` 派生行 ⇒ `extract_signed_codes` 抽不出 `TB()` ⇒ 退兜底码 ⇒ **金额正确**、只有 `resolved_from` 谎报 `fallback`。K3/K5/K7/K8/K11/K12/K13 属此级 |
| **派生行** | `report_config.formula` 是 `ROW()` 组合而非 `TB()` 的报表行（如 `BS-015` 流动资产合计、`IS-022` 利润总额）。不可作为取数 row_code |
| **宁缺勿造** | 科目在 `account_chart` 按名按码两侧均零命中且报表公式为 NULL 时，返回空取数结果 + `empty_reason`，绝不回退到不存在的码。**是逐循环实证结论、不是设计偏好** |
| **可扩位** | 源模板留给审计师增行的占位行（`……` / `可无限量添加行` 等），在附注侧应标 `row_type='expandable'`；区别于「说明文字里的省略号」 |
| **fail-closed** | 载荷声明 `_row_scope` 而附注模板缺 `report_row_code` 时，**跳过该表写入**（不退化为整表覆盖） |
| **三向比对** | 源 xlsx（openpyxl 直读）↔ 附注模板 JSON ↔ 前端载荷 columns，三者逐字一致 |

本 spec 的立项依据全部来自 2026-08-09 的只读实证（`report_config` 四变体逐条对账、`account_chart` 双向查、openpyxl 直读 14 个源 xlsx 的 26 张披露 sheet、两份 `note_template_*.json` 的 26 个章节逐表 dump、13 个 `k*NoteSectionMap.ts` 源码扫描）。**实证推翻了 `backend/app/services/four_table/k_cycle_specs.py` 自带的那张「DB 只读实证表」** —— 该表把 listed / soe 两侧报表行号整体记错一档，导致 9 处 row_code 错位、其中 4 处是活的取数错误。

### 核心事实（全部实测）

**科目映射链路**（K 循环与全平台一致）：

```
tb_balance.account_code（客户原始码，点号 1221.12）
    │ account_mapping(project_id, original → standard)
    ▼
trial_balance.standard_account_code（标准码，横杠 1231-03）
    │ report_config.formula（按 applicable_standard 四变体）
    ▼
报表行 row_code
```

**正确落点全部是「两准则同号」**（按 `row_name` 反查 `report_config`，`applicable_standard NOT LIKE 'project:%'`）：

| 循环 | 科目 | 正确 row_code | formula（四变体） |
|---|---|---|---|
| K1 | 其他应收款 | `BS-009` | soe_standalone 含 `− TB('1231-03') + TB('1131')`；其余仅 `TB('1221')` |
| K2 | 其他流动资产 | `BS-014` | 四变体全 NULL |
| K3 | 其他应付款 | **`BS-050`** | standalone `TB('2241')+TB('2231')`；consolidated `TB('2241')` |
| K4 | 其他流动负债 | `BS-053` | 四变体全 NULL |
| K5 | 预计负债 | **`BS-065`** | 四变体一致 `TB('2801')` |
| K6 | 持有待售资产 | **`BS-012`** | 四变体一致 `TB('1481')` |
| K6 | 持有待售负债 | **`BS-051`** | 四变体一致 `TB('2245')` |
| K6 | 持有待售资产减值准备 | **`IMP-007`** | soe_standalone `TB('1482')` |
| K7 | 递延收益 | **`BS-066`** | 四变体一致 `TB('2401')` |
| K8 | 销售费用 | `IS-004` | 四变体一致 `TB('6601','本期发生额')` |
| K9 | 管理费用 | `IS-005` | 四变体一致 `TB('6602','本期发生额')` |
| K10 | 其他收益 | `IS-010` | 四变体一致 `TB('6117','本期发生额')` |
| K11 | 资产减值损失 | `IS-017` | 四变体一致 `TB('6701','本期发生额')` |
| K12 | 营业外收入 | `IS-020` | 四变体一致 `TB('6301','本期发生额')` |
| K13 | 营业外支出 | `IS-021` | 四变体一致 `TB('6711','本期发生额')` |

**声明表现状的 9 处错位**（`K_CYCLE_SPECS` 的 `row_code_soe` 全线错位 + 2 处 listed 错位）：

| 循环 | 声明 row_code_soe | 该码实际是什么 | 后果 |
|---|---|---|---|
| K9 | `IS-023` | **减：所得税费用** `TB('6801','本期发生额')` | 🔴 **活错数**：`6801` 在 `account_chart` standard 9 / client 7 项目均存在且 `direction=debit`（不被备抵拆分挡住）⇒ 管理费用审定表取到所得税费用 |
| K6 | `BS-024` | **长期股权投资** `TB('1511','期末余额')` | 🔴 **活错数**：`1511` 在 8 个客户项目存在且 `direction=debit` ⇒ 持有待售资产审定表取到长期股权投资 |
| K4 | `BS-081` | **实收资本（或股本）** `TB('4001','期末余额')` | 🔴 **活错数被掩盖**：`4001` client 侧 8 项目 `direction=credit`，而 K4 未声明 `is_liability`/`gross_direction` ⇒ 被 `split_gross_provision` 判成**备抵** ⇒ `gross` 变空 ⇒ 表现为「恒空」而非错数 |
| K8 | `IS-022` | **三、利润总额**（`ROW()` 派生行） | 溯源失真：`extract_signed_codes` 抽不出 `TB()` ⇒ codes 空 ⇒ 退兜底 `6601`，金额对但 `resolved_from` 谎报 |
| K3 | `BS-075` | 其他应付款（名对但 **formula NULL**） | 退兜底 `2241`，金额对但**漏 `2231` 应付利息** |
| K5 | `BS-094` | 预计负债（formula NULL） | 退兜底 `2801`，金额对、溯源失真 |
| K7 | `BS-095` | 递延收益（formula NULL） | 退兜底 `2401`，同上 |
| K11 | `IS-038` | 资产减值损失（formula NULL） | 退兜底 `6701`，同上 |
| K12/K13 | `IS-041`/`IS-043` | 营业外收入/支出（formula NULL） | 退兜底，同上 |

另 3 处 listed 错位：K6 `BS-015` = **流动资产合计**（`ROW()` 派生）· K7 `BS-069` = **非流动负债合计**（`ROW()` 派生）· **K3 `BS-053` = 其他流动负债**（= K4 应改指的那个码 ⇒ **K3 与 K4 跨循环撞码**，`BS-053` 四变体公式全 NULL 故 K3 listed 也是「退兜底 `2241`、漏 `2231`」）。

**Wave 1 守卫首跑（连库）新查出 2 处 spec 未记的 soe 错位**（初稿只记「K10~K13 四条 formula NULL」，实为其中两条是**指向别的科目**）：

| 循环 | 声明 `row_code_soe` | 该码实际指向 | 分级 |
|---|---|---|---|
| K10 其他收益 | `IS-030` | **五、其他综合收益的税后净额**（formula NULL） | TRACE_ONLY |
| K11 资产减值损失 | `IS-038` | listed 侧 `5. 其他` / soe 侧 `资产减值损失（损失以"－"号填列）`（**一码两义**，两侧 formula 均 NULL） | TRACE_ONLY |

⇒ **错位总数由初稿的 9 处修正为 12 处**（含 K3 listed / K10 soe / K11 soe），分级分布 **2 ACTIVE_WRONG（K6 soe / K9 soe）· 1 SILENT_EMPTY（K4 soe）· 9 TRACE_ONLY**。守卫实测输出见 Task 1 实录。

**「宁缺勿造」判断亦被推翻**：`k_cycle_specs.py` 称 K4/K6 的科目「三表零命中」，实测 `account_chart` client 侧 `1481 持有待售资产`(debit) / `1482 持有待售资产减值准备`(debit) / `2245 持有待售负债`(credit) **各有 1 个项目存在**，且 `report_config` 的 `BS-012`/`BS-051`/`IMP-007` 公式都在。K4（其他流动负债）四变体公式确实全 NULL、`account_chart` 按名按码均零命中 ⇒ **只有 K4 的宁缺勿造成立，K6 不成立**。

**披露 sheet 事实**（openpyxl 直读，26 张全 `visible`）：**14 个 workbook / 144 张 visible sheet**，其中 **8 个 workbook 另有 hidden `GT_Custom`**（K0/K1/K10/K12/K13/K2/K3/K7；K11/K4/K5/K6/K8/K9 无 hidden sheet）。括号写法 **6 种并存**：

| 写法 | 循环 | 形态 |
|---|---|---|
| `（上市公司）` / `（国企）` 全角全角 | K10 K11 K12 K13 K2 K4 K8 K9 | 主流 |
| `(上市公司）` | K1 | 前半后全 |
| `（国企）` | K1 K13 K6(仅 listed 侧全角) | — |
| `(上市公司)` + `(国企)` | K3 | 半角半角 |
| `（上市公司)` | K5 | 前全后半 |
| `(国企）` | K6 | 前半后全 |
| **`（国有企业）`** | **K7** | 唯一用「国有企业」 |

⇒ 按 `== "附注披露信息（上市公司）"` 精确匹配会漏 K1/K3/K5；按 `"国企" in name` 会漏 K7。**K0 无披露 sheet**（11 个 sheet 全是函证程序/汇总/替代程序/舞弊评价）。

**动态插行标记 148 处 / 5 种写法**（openpyxl 全 sheet 扫描；**推翻立项初稿记的「24 处 / 3 种」**）：

| 写法 | 处数 | 说明 |
|---|---|---|
| `……` | 91 | 主流 |
| **`…`（单字符）** | **10** | **确实存在**：K6-6 处置组减值测试表 3 处 / K8-5·K9-5 合同检查表各 2 处 / K11-2 · K12-2 · K13-2 等 |
| `?`（问号占位） | 41 | 多为「XX」式待填提示的伴生形态 |
| `可无限量添加行` | 4 | K1 listed(A27/A109) / K3 两版(A16) |
| `......`（半角） | 2 | K11 `审定表K11-1!A25` / `明细表K11-2!B29` |

**其中落在 26 张披露 sheet 内的只有 15 处**：K1 listed A27/A109（`可无限量添加行`）· K1 soe A24/A33 · K3 两版 A16（`可无限量添加行`）· K6 listed A15/A37/A41/A58/A64/A71/A77（7 处）· K6 soe A14/A18/A27/A31/A54（5 处）· K13 soe A14。**其余 133 处在非披露 sheet**（底稿目录说明段 / 程序表 / 检查表 / 替代程序 / 调整分录汇总的 `F5`），属**正文省略号**不是可扩位 ⇒ **判据必须限定在披露 sheet 内**，否则会把说明文字标成 expandable。

**附注模板侧**（26 章节全部命中，`columns` 无一为 0、`guidance` 全有、`headers` 无 HTML）：

- **K 类 26 个章节的 `expandable` 行数 = 0**（全库 listed 79 / soe 42 行全部落在非 K 章节）⇒ 披露 sheet 内的 11 处动态插行区在附注侧**无一被标记**
- **`report_row_code` 全为 `None`**（K1 listed 21 表 + K1 soe 19 表 + K2 listed 3 表逐表实测）⇒ 声明 `_row_scope` 后 `find_segment` 必返 None ⇒ **fail-closed 整表跳过写入**
- 列 key 风格分叉：K1 用**中文字面量**（`期末账面余额`/`预期信用损失率`），K2~K7 用**英文 key**（`end_amount`/`prior_amount`/`begin_amount`）
- 账龄字面两版不同：listed 首档 `1年以内`，soe 首档 **`1年以内（含1年）`**

**前端载荷侧**（13 个 `k*NoteSectionMap.ts` 全部存在）：

- **K1 无 `build*Columns`、无 `buildK1SyncPayload`**（`col_keys` 与 `flat_count` 均为 0）—— 它是唯一走另一条推送路径的循环（两个 Tab 的 `sync-from-workpaper` 计数为 0）
- **K7_LISTED_SUBTABLE / K7_SOE_SUBTABLE 是空数组**
- **K8~K13 的 `X_LISTED_SUBTABLE` 里混入了表头文字与英文 key**（`项目` / `本期发生额` / `上期发生额` / `non_recurring_amount` / `amount`）—— 子表名常量被污染
- 26 个披露 Tab **全部已接** `syncToDisclosureNotes` + `useDisclosureAutoSync` + `scheduleAutoSync`（无缺口）

**公式预设**（`prefill_formula_mapping.json` 共 282 块，K 前缀 26 块）：

- **144 张 visible sheet 中 118 张无预设**（K 前缀 26 块覆盖 26 张）；**26 张披露 sheet 全部零预设**
- **`formula_type` 缺失的块 = 12 块**（**推翻初稿记的 7 块**）：整块缺失 7 块（K3 审定表 6/6 · K5 审定表 6/6 · K7 审定表 6/6 · K10 审定表 5/5 · K11 审定表 5/5 · K12 审定表 5/5 · K13 审定表 5/5 · K5 明细表 4/4，共 **8** 块全缺）+ **部分缺失 4 块**（K8 审定表 1/8 · K9 审定表 1/9 · K8 分析程序 1/3 · K8 实质性分析 1/5）⇒ 合计 **12 块 / 48 个 cell** 缺 `formula_type`
- **「K10~K13 期初与未审公式逐字相同」经逐格 dump 确认成立**（我第一轮扫描器把「期初/上年」与「未审/本期」两类关键词分组比对，而 K10~K13 的 cell 名恰为 `期初余额` 与 `未审数` ⇒ 分组判据本身漏了这一对，属**扫描器缺陷不是 spec 错**）：四块的 `期初余额` 与 `未审数` 均为 `TB('6xxx','本期发生额')` **逐字相同**，且 `期初余额` 的 description 写「兜底 6117/6701/6301/6711」⇒ 损益类无期初，该格应走 `PREV()` 或删除
- **🔴 K8/K9 审定表的损益口径错**（spec 只记「可疑」，实为确定错误）：`期初余额=TB('6601','期初余额')` / `未审数=TB('6601','期末余额')`，description 写「期初/期末**累计发生额**」—— 而 `report_config` 的 `IS-004`/`IS-005` 四变体一致用 **`本期发生额`**；`trial_balance` 的损益类权威口径也是发生额 ⇒ 这两格取的是余额列（损益类年末结转后恒 0）
- **🔴 K8 `实质性分析K8-4` 另有 3 处同族错**：`本年发生额=TB('6601','贷方发生额')`（销售费用是**借方**科目，且该列未注册）+ `本年期初=TB('6601','期初余额')` + `本年期末=TB('6601','期末余额')`
- **🔴 K8 `分析程序K8-3` 用 `TB_SUM('6601~6603','期末余额')`** —— 区间把管理费用 `6602` 与财务费用 `6603` 一起扫进销售费用分析，且列名错（应 `本期发生额`）；`SUM_TB`/`TB_SUM` 两种写法在本文件与 `report_config` 中并存（后者只用 `SUM_TB`）
- **K8/K9 月度明细逐格确认是 1~10 月**（cell 名 `销售费用_1月_合计` ~ `_10月_合计`，description 逐月对应，无合计行）⇒ **缺 11/12 月**，R6.8 成立
- **K1/K3 明细块的硬编码辅助项**实为 **`AUX('1221','三方收款标识','SKT211'|'YG01'|'YG02',…)`**（K1，6 处）与 **`AUX('2241','代收代付类别','A001'|'A011'|'A012',…)`**（K3，6 处）—— **维度名不是初稿写的「职员」/「客户」**，按初稿写守卫会 0 命中
- **K8 `分析程序K8-3` 块 wp_name 写「管理费用分析程序」且 account_codes = `['6601','6602','6603']`** —— 贴错标签（K8 是销售费用 `6601`）
- K5 用 `TB('2801','借方发生额')`(1 处) / `TB('2801','贷方发生额')`(2 处) —— 未注册列名，会静默回退期末余额
- K4/K5/K6 的 sheet 名**带空格**：`审定表 K4-1` / `审定表 K5-1` / `明细表 K5-2` / `审定表 K6-1`（源模板核实：K4 有 `调整分录汇总 K4-3`/`其他流动负债检查表 K4-4`、K5 有 `调整分录汇总 K5-3`/`未决诉讼检查表 K5-6`/`预计负债检查表 K5-7`、K6 有 `调整分录汇总 K6-3`/`处置组减值测试表（后续计量） K6-6` ⇒ **空格是源模板事实，预设保留空格是对的**）
- **🔴 但 `PREV()` 实参与 `block.sheet` 不一致 2 处**：K5 的 `block.sheet='审定表 K5-1'`（带空格）而 `PREV('K5','审定表K5-1',…)`（无空格）；K5 明细块 `block.sheet='明细表 K5-2'` 而 `WP('K5','明细表K5-2',…)` —— 两处实参指向源 xlsx 不存在的 tab
- K8/K9 月度明细块 `LEDGER_DETAIL` 各 10 个 cell（需逐 cell 核 `description` 确认是 1~10 月还是含合计行，Wave 1 定）
- **K8/K9 已有跨循环 `WP()` 联动**（`WP('H1','折旧分配分析表H1-13')` / `WP('J1','审定表')` / `WP('I1','审定表')`）⇒ R7.3 说「K10~K13 零 `WP()`」成立，但 K8/K9 不在缺口内

## Requirements

### Requirement 1: K 循环科目定位声明真源改正

**User Story:** 作为审计助理，我需要 K 循环各底稿的审定表在四表入库后取到**本科目**的数据，而不是别的科目的数据。

#### Acceptance Criteria

1.1. WHEN 读取 `k_cycle_specs.py` 的 `K_CYCLE_SPECS` THEN 每个循环的 `row_code_listed` 与 `row_code_soe` SHALL 与 `report_config` 中该科目名对应的行逐字一致（按 `row_name` 反查，四变体全列）
1.2. WHEN 某科目在 `report_config` 四变体下 row_code 相同 THEN 声明表 SHALL 两侧填同一个码（不得为了「看起来分变体」而填不同码）
1.3. K3 的 row_code SHALL 改为 `BS-050`，且声明中 SHALL 包含 `2231 应付利息` 作为附加科目（`BS-050` 在 standalone 变体下是 `TB('2241')+TB('2231')`）
1.4. K5 的 `row_code_soe` SHALL 由 `BS-094` 改为 `BS-065`；K7 的 `row_code_listed`/`row_code_soe` SHALL 由 `BS-069`/`BS-095` 改为 `BS-066`
1.5. K6 的 row_code SHALL 由 `BS-015`/`BS-024` 改为资产侧 `BS-012`、负债侧 `BS-051`、备抵侧 `IMP-007`
1.6. K8 的 `row_code_soe` SHALL 由 `IS-022`（利润总额派生行）改为 `IS-004`；K9 的 `row_code_soe` SHALL 由 `IS-023`（所得税费用）改为 `IS-005`
1.7. K10~K13 的 `row_code_soe` SHALL 分别改为 `IS-010` / `IS-017` / `IS-020` / `IS-021`
1.8. K4 的 `has_account=False`（宁缺勿造）SHALL 保留，且其 `row_code` SHALL 改为 `BS-053`（该行四变体公式确为 NULL、`account_chart` 按名按码均零命中，是唯一成立的宁缺勿造）
1.9. K6 的 `has_account` SHALL 由 `False` 改为 `True`（实证 `1481`/`1482`/`2245` 在 client 侧存在、三条报表行公式都在），并保留「本项目无该科目时返回空取数结果」的降级
1.10. WHEN 声明表中某 row_code 的 `report_config` 公式是 `ROW()` 组合（派生行） THEN 声明 SHALL 标注 `trust_report_config=False` 或改指非派生行（`extract_signed_codes` 抽不出 `TB()` 会静默退兜底）
1.11. 声明表的 docstring SHALL 重写为本次实测结论，且 SHALL 删除或改正原有那张记错的「实证表」
1.12. 每条改正 SHALL 在声明中留下「原值 / 该原值实际指向的科目 / 后果分级（活错数 / 恒空 / 仅溯源失真）」

### Requirement 2: 负债与权益类方向声明补齐

**User Story:** 作为审计助理，我需要负债类循环的审定表取到原值而不是空值，且溯源面板不把原值科目显示成备抵科目。

#### Acceptance Criteria

2.1. WHEN K 循环的科目在 `account_chart` 中 `direction='credit'`（负债/权益类） THEN 该循环的 `ReportLineAccountSpec` SHALL 声明 `is_liability=True` 或 `gross_direction='credit'`
2.2. K3 / K4 / K5 / K7 SHALL 声明负债方向（实测 `2241`/`2231`/`2801`/`2401` 在 `account_chart` 均为 `credit`）
2.3. K6 的负债侧规格 SHALL 声明负债方向（`2245` 为 `credit`），资产侧 SHALL 不声明（`1481`/`1482` 为 `debit`）
2.4. WHEN 未声明方向且科目为 credit THEN 守卫 SHALL 打红并指出「原值会被判成备抵、gross 变空」
2.5. 声明方向后 `resolved_from` SHALL 为 `report_config`（而非退化为 `fallback`）

### Requirement 3: K1/K2 纳入声明真源

**User Story:** 作为开发者，我需要 K 循环的科目声明只有一处真源，避免「改一处另一处不动」。

#### Acceptance Criteria

3.1. K1 与 K2 的科目定位声明 SHALL 收进 `K_CYCLE_SPECS`（当前它们各写私有 spec、不在真源内）
3.2. K1 的声明 SHALL 保留其 `provision_row_code`/`provision_name_filter`/`extra_standard_codes`（`1131` 应收股利 / `1132` 应收利息）等既有语义
3.3. K2 的声明 SHALL 保留 `BS-014` + 兜底码 `1901` 与既有 `k2AccountScope.ts` 交叉锁死关系
3.4. 收进真源后 K1/K2 的 render 行为 SHALL 逐字节不变（characterization 守卫）
3.5. `k1AccountScope.ts` SHALL 新建（当前 K1 是唯一无前端科目真源的 K 循环），并与后端声明交叉锁死

### Requirement 4: 取数完整性补齐（parent_check / adjudication_prefill）

**User Story:** 作为审计助理，我需要每个 K 循环的审定表都能「从四表库带入未审数」，并能看到叶子和与父额的勾稽结果。

#### Acceptance Criteria

4.1. K6 SHALL 输出 `adjudication_prefill`（当前是余额类循环中唯一缺失者）
4.2. K1 / K2 / K4 / K6 SHALL 输出 `parent_check`（三口径勾稽：叶子和 / 父行 / trial_balance）
4.3. WHEN 某槽 `found=False` THEN `parent_check` SHALL 不产生该键（三态语义，不得填 0）
4.4. WHEN 科目族内存在反方向 contra 子科目 THEN 聚合 SHALL 走 `resolve_leaf_totals`（按方向自校验），不得裸 `aggregate_leaves`
4.5. `adjudication_prefill` SHALL 只在无持久化审定数时生效（手工优先）
4.6. WHEN 本项目无该科目 THEN 前端 SHALL 显示「本项目无此科目」而非 `0.00`

### Requirement 5: 语义驱动定位接线

**User Story:** 作为开发者，我需要 K 循环按科目名在本项目科目表定位，而不是硬编码标准码，因为客户可能用另一套编码。

#### Acceptance Criteria

5.1. `k_cycle_specs.to_semantic_spec` / `semantic_spec_of` SHALL 有真实生产消费方，或 SHALL 被明确撤回并登记理由（当前两者零消费方 = 死代码）
5.2. IF 接线 THEN `to_semantic_spec` SHALL 按 `applicable_standards` 选 row_code（当前硬编码 `row_code_soe`）
5.3. IF 接线 THEN 多槽规格 SHALL 关闭报表公式兜底层（`allow_report_config_tier = len(slots) == 1`）
5.4. IF 撤回 THEN 撤回理由 SHALL 含实证（K 循环科目码在项目间是否一致的对账结果）
5.5. 无论接线或撤回，守卫 SHALL 钉死结论，防下个会话重新发起一轮批量迁移

### Requirement 6: 公式预设科目与口径改正

**User Story:** 作为审计助理，我需要底稿当页的公式管理里的预设公式指向本底稿的科目、用对取数口径。

#### Acceptance Criteria

6.1. WHEN 预设块的 `wp_name` 或 `account_codes` 与该 wp_code 的科目不符 THEN SHALL 改正（K8 `分析程序K8-3` 块写「管理费用分析程序」且含 `6602`/`6603`）
6.2. **12 个**含 `formula_type` 缺失的块（整块缺失 8：K3/K5/K7/K10/K11/K12/K13 审定表 + K5 明细表；部分缺失 4：K8/K9 审定表各 1、K8 分析程序 1、K8 实质性分析 1）SHALL 补齐类型字段，合计 **48 个 cell**
6.3. K10~K13 审定表的 `期初余额` 格（当前与 `未审数` 逐字同为 `TB('6xxx','本期发生额')`）SHALL 走 `PREV()` 或删除该格（损益类无期初）
6.4. 损益类循环的取数列 SHALL 是 `本期发生额`；SHALL 改正 K8/K9 审定表的 `期初余额`/`期末余额`、K8 `实质性分析K8-4` 的 `期初余额`/`期末余额`/`贷方发生额`
6.5. 未注册列名 SHALL 改为已注册名（`本期借方`/`本期贷方`）或改 `PLACEHOLDER` 并写明真源：K5 的 `借方发生额`(1) / `贷方发生额`(2)、K8 `实质性分析K8-4` 的 `贷方发生额`(1)
6.6. K1/K3 明细块中硬编码的具体辅助项编码 SHALL 删除（K1 是 `AUX('1221','三方收款标识','SKT211'|'YG01'|'YG02',…)` 6 处；K3 是 `AUX('2241','代收代付类别','A001'|'A011'|'A012',…)` 6 处 —— **维度名逐字如此，不是「职员」/「客户」**）
6.7. 预设块的 `sheet` 名 SHALL 与源 xlsx tab 名逐字一致；K4/K5/K6 的空格是源模板事实 SHALL 保留
6.8. K8/K9 月度明细块 SHALL 覆盖 12 个月（逐格确认当前是 1~10 月、无合计行）
6.11. K8 `分析程序K8-3` 的 `TB_SUM('6601~6603','期末余额')` SHALL 改为销售费用单码 + `本期发生额`（该区间把管理费用 `6602`、财务费用 `6603` 扫进销售费用分析）
6.12. `PREV()`/`WP()` 实参的 sheet 名 SHALL 与 `block.sheet` 及源 xlsx 一致；SHALL 改正 K5 两处不一致（`block.sheet='审定表 K5-1'` 带空格而实参 `'审定表K5-1'` 无空格；`'明细表 K5-2'` vs `'明细表K5-2'`）
6.9. 改正 SHALL 由幂等脚本落地（`--dry-run` / `--check` / round-trip 自检），`--check` SHALL 归零
6.10. 幂等脚本 SHALL 同时改 `block.sheet` 与公式实参里的旧 sheet 名（`PREV('K1','审定表K1-1',…)` 形态）。**实测 2 处实参与 `block.sheet` 不一致**：K5 审定块 `block.sheet='审定表 K5-1'`（带空格）而实参 `PREV('K5','审定表K5-1',…)`（无空格）· K5 明细块 `block.sheet='明细表 K5-2'` 而实参 `WP('K5','明细表K5-2',…)` ⇒ 两处实参指向源 xlsx 不存在的 tab，SHALL 改为带空格
6.13. WHEN 预设块的 `sheet` 名带空格 THEN SHALL 保留空格（实测 K4/K5/K6 源 xlsx 确有带空格的 tab：`调整分录汇总 K4-3` / `未决诉讼检查表 K5-6` / `处置组减值测试表（后续计量） K6-6` ⇒ 空格是源模板事实，SHALL NOT 当笔误去掉）

### Requirement 7: 公式预设覆盖面补齐

**User Story:** 作为审计助理，我需要打开 K 循环任一 sheet 时公式管理页有该页的预设，而不是空白。

#### Acceptance Criteria

7.1. 26 张披露 sheet SHALL 有预设块（当前全部零预设）
7.2. 有四表可取数的 sheet SHALL 补预设；纯手工/外部证据类 sheet SHALL **显式登记「无预设」** 并写明理由（不得留空）
7.3. 审定表块 SHALL 有 `WP()` 底稿间联动。**缺口精确到 K10~K13 四个循环**（各 5 cell 全无 `WP()`）；K8/K9 已有跨循环联动（`WP('H1','折旧分配分析表H1-13')` / `WP('J1','审定表')` / `WP('I1','审定表')`）SHALL 保留不动，K1/K2/K3/K5/K7 已有同循环 `WP()` 亦保留
7.4. 明细表块 SHALL NOT 反向引用审定表（防成环）
7.5. `WP()` 的目标 sheet SHALL 是源 xlsx 真实 tab 名
7.6. 覆盖面判据 SHALL 排除白名单（`底稿目录` / `GT_Custom` / 程序表 `*A`），并 SHALL 断言白名单本身非空

### Requirement 8: 披露表结构与源模板对齐

**User Story:** 作为审计助理，我需要底稿的上市/国企披露表结构与致同源模板一致，列数、列头、行集都对得上。

#### Acceptance Criteria

8.1. 每个循环的 `X_DISCLOSURE_SHEET_NAME` SHALL 与源 xlsx tab 名逐字一致。实测 **6 种括号写法**（非初稿记的 4 种）：全角全角 20 张（K2/K4/K8/K9/K10/K11/K12/K13 两版 + K1 soe + K6 listed + K7 listed）· **K1 listed `附注披露信息(上市公司）`** 前半后全 · **K3 两版 `附注披露信息(上市公司)` / `附注披露信息(国企)`** 半半 · **K5 listed `附注披露信息（上市公司)`** 前全后半 · **K6 soe `附注披露信息(国企）`** 前半后全 · **K7 soe `附注披露信息（国有企业）`**（唯一「国有企业」）。守卫 SHALL openpyxl 直读比对，SHALL NOT 按「统一成全角」修正
8.2. 披露表的列头字面 SHALL 取自源 xlsx（两版用语不同者 SHALL 分变体声明，不得共用一份常量）
8.3. 披露表的两级表头 SHALL 用 `group` + 叶子 label 表达，SHALL NOT 压扁成带前缀的单级
8.4. 单级表的列 SHALL 显式标 `flat`（防 `_infer_groups_from_headers` 推出凭空父表头）
8.5. `flat`/`group` SHALL 在 seed 路径（模板 JSON）与推送路径（载荷 columns）**两侧都表态**
8.6. 源模板自身缺陷 SHALL 按意图实现并登记，SHALL NOT 照抄：K6 两版合计行的账面价值列是说明文字（`C=A+B=报表数` / `A+B=报表数`）SHALL 按「账面余额 − 减值准备」派生；K3 soe 按性质表标签列列头是 `账  龄`（listed 侧是 `项 目` 才对）SHALL 按 listed 字面；K1 两版共 11 处 `#REF!` 断链 SHALL 登记为「源模板取数已坏、数据靠底稿录入」
8.7. K11 两版注文「本科目明细表按照正数填列、披露表按照负数填列」SHALL 在载荷层实现符号翻转

### Requirement 9: 动态插行区识别与标记

**User Story:** 作为审计助理，我需要披露表里源模板留的可扩位在附注侧也是可扩的，而不是被渲染成一行空披露数据。

#### Acceptance Criteria

9.1. **披露 sheet 内的 21 处**动态插行标记 SHALL 逐处判定「作行」还是「作列头」（**判定面 = 26 张披露 sheet**，非全部 148 处；其余 127 处落在程序表/检查表/底稿目录/调整分录汇总，不进附注，SHALL 显式排除并登记排除理由）
9.2. 作**行**的标记 SHALL 在附注模板对应行标 `row_type='expandable'`（当前 K 类 26 章节的 expandable 行数为 0）
9.3. 作**列头**的标记 SHALL 展开为实际类别名，SHALL NOT 保留占位符
9.4. `expandable` 行 SHALL 被投影与 Word 导出视为零可见内容
9.5. 标记 SHALL 复用 `note_expandable_markers` 判据真源，SHALL NOT 另写一份词表
9.6. WHEN 某循环的幂等脚本重写整表 rows THEN 该脚本 SHALL marker-aware（防把标好的 expandable 翻回 `data`）
9.7. K 类判据 SHALL 覆盖实测出现的 **5 种写法**（`……` 91 / `?` 41 / `…` 10 / `可无限量添加行` 4 / `......` 2）；`…`（单字符）**确实存在** SHALL NOT 被排除；`预留`/`可改名` 在 K 类零命中 SHALL NOT 加入判据并 SHALL 配零命中自检
9.8. WHEN 某处标记是「说明文字里的省略号」（如 `1.XX费用较上期增长XX%，本期大幅增加原因……`） THEN SHALL 判为**非可扩位**并登记，SHALL NOT 标 `expandable`（`?` 41 处与部分 `……` 属此类，判据不得只看是否含标记字符）

### Requirement 10: 账龄口径统一为枚举

**User Story:** 作为审计助理，我需要账龄档位跟着项目的账龄配置走，而不是写死 5 年段。

#### Acceptance Criteria

10.1. K 循环披露表的账龄行集 SHALL 由 `disclosureAgingLabels` 单一真源驱动
10.2. 国企侧首档字面 SHALL 取 `DISCLOSURE_AGING_WITHIN1_SOE`（实测 soe 是 `1年以内（含1年）`，listed 是 `1年以内`）
10.3. 账龄作**列维度**的表（K1 两版的前五名表与政府补助表共 4 处）SHALL 保留为列，SHALL NOT 改成行
10.4. K1 listed 的月度细分行（`其中：0-X个月` / `X-Y个月`）SHALL 保留（源模板事实）
10.5. K3 两版的「账龄超过1年」段 SHALL 保持为独立表（表内无账龄列/行）
10.6. 无账龄维度的 11 个循环（K2/K4/K5/K6/K7/K8/K9/K10/K11/K12/K13）SHALL NOT 引入账龄枚举，守卫 SHALL 反向锁死

### Requirement 11: 附注模板行级合并支持

**User Story:** 作为审计助理，我需要多个底稿共享同一附注章节时，各自只覆盖自己负责的行，不互相清空。

#### Acceptance Criteria

11.1. K 类附注章节中承载多科目的表 SHALL 有 `report_row_code`（当前 K1 listed 21 表 + soe 19 表 + K2 3 表全为 `None`）
11.2. `report_row_code` SHALL 与 `report_config` 对账后填写，SHALL NOT 按行名猜
11.3. WHEN 载荷声明 `_row_scope` 而模板缺 `report_row_code` THEN 写入 SHALL fail-closed（跳过该表）且 SHALL 记录可诊断的原因
11.4. K1 与 G2/G3 共用 `五、8`/`八、9` 的情形 SHALL 在 `_row_scope` 下各自只写自己的段
11.5. 单 owner 独占整表的循环 SHALL 登记豁免（不强制 `_row_scope`）

### Requirement 12: 前端载荷子表名与列定义收口

**User Story:** 作为审计助理，我需要点「推送到附注」后附注里出现的是正式表名的表，而不是孤儿表。

#### Acceptance Criteria

12.1. 每个 `X_SUBTABLE` 常量的值 SHALL 与附注模板 `tables[].name` 逐字一致
12.2. `X_LISTED_SUBTABLE` / `X_SOE_SUBTABLE` SHALL NOT 混入表头文字或英文列 key（实测 K8~K13 混入了 `项目`/`本期发生额`/`上期发生额`/`non_recurring_amount`/`amount`）
12.3. K7 的 `K7_LISTED_SUBTABLE` / `K7_SOE_SUBTABLE` SHALL NOT 为空数组
12.4. K1 SHALL 有 `build*Columns` 与 `buildK1SyncPayload`，或其现有推送路径 SHALL 被显式登记并加守卫（当前它是唯一无这两者的循环）
12.5. 列 key 风格 SHALL 在同一循环内一致；跨循环风格分叉（K1 中文 vs K2~K7 英文）SHALL 登记裁决理由（改 key 会丢已录入数据）
12.6. 载荷 SHALL 带 `_removed_table_keys`（条件表被关闭时清理孤儿），且 SHALL 与本次推送键求差集
12.7. `_note_texts` SHALL 带中文 `title`，SHALL 过滤空文本
12.8. 标签列 key SHALL 用 `label`（平台惯例 91%）

### Requirement 13: 守卫与 CI

**User Story:** 作为开发者，我需要这些改正被守卫钉死，不会被下一轮会话回退。

#### Acceptance Criteria

13.1. row_code 守卫 SHALL 连库按 `row_name` 反查 `report_config` 并与声明表精确比对（不得用静态冻结表，否则数据改了守卫不知道）
13.2. 守卫 SHALL 覆盖全部 14 个 K 循环（当前 `test_cycle_specs_row_code_evidence._all_specs()` 缺 K 与 H）
13.3. 守卫 SHALL 断言「同一 row_code 不得被两个循环认领」
13.4. 守卫 SHALL 断言「负债类科目必须声明方向」
13.5. 守卫 SHALL 断言「派生行（`ROW()` 组合）不得作为取数 row_code」
13.6. 披露 sheet 名守卫 SHALL openpyxl 直读源 xlsx 比对（不得只比常量与 registry）
13.7. 附注结构守卫 SHALL 做三向比对（源 xlsx ↔ 模板 JSON ↔ 载荷 columns）
13.8. 每个守卫 SHALL 配反向自检（复现旧缺陷形态必须打红）
13.9. 变异检验 SHALL ≥ 12 项且逐条 RED，SHALL 按「失败测试名集合差集」判定（不看退出码）
13.10. CI SHALL 新增 job 覆盖后端守卫与前端契约
13.11. 幂等脚本 `--check` SHALL 在 CI 中归零

### Requirement 14: 真实库验收与浏览器实测

**User Story:** 作为审计助理，我需要确认四表入库后底稿真的有数据、点推送后附注真的有数据。

#### Acceptance Criteria

14.1. 真实库验收 SHALL 对全部在册项目 × 14 个 K 循环逐组合直跑 render，输出 `resolved_from` / row_code / 科目码 / 金额
14.2. 验收 SHALL 交叉核对「叶子和 == 父科目期末」（用独立 SQL，不拿被测函数证明自己）
14.3. 验收 SHALL 证明改正前后金额差异，并逐条归因（活错数 / 恒空 / 仅溯源）
14.4. 浏览器实测 SHALL 覆盖：审定表带入未审数 / 溯源面板 / 披露表两变体渲染 / 推送到附注后落库
14.5. 实测 SHALL 查 `disclosure_notes` 确认子表数、列元数据、`_column_groups`、`expandable` 行
14.6. 实测数据 SHALL 按基线逐字节复原，并用独立只读查询核实
14.7. WHEN 某变体无活体项目 THEN SHALL 如实登记「未实测」，SHALL NOT 用 fixture 冒充
14.8. 零回归 SHALL 用前后对照（当前态 → 施加幂等改动 → 对照），SHALL NOT 用 HEAD-swap（本 spec 改动的数据文件混着并发会话成果）
