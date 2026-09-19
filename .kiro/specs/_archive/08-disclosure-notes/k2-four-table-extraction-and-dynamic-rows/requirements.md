# Requirements Document

## Introduction

K2「其他流动资产」循环的四表库取数链路存在**比 K1 更严重**的缺陷 —— K1 是取错了子科目，
K2 是取错了**整个科目族**。全部经 DB 只读 + 源 xlsx openpyxl + 活体 `render-config` 实证。

### 一、后端取的是坏账准备，不是其他流动资产

`_k2_other_current_assets.py` 写着：

```python
# 科目前缀：1231其他流动资产(借方/资产类)
_K2_ACCOUNT_PREFIXES = {"1231": ("other_current_unadjusted", "other_current_audited")}
```

但 `1231` 是**坏账准备**（应收款项的贷方备抵科目）。`report_config` 实证：

| row_code | row_name | applicable_standard | formula |
|---|---|---|---|
| `BS-014` | 其他流动资产 | soe_standalone / soe_consolidated / listed_consolidated | `TB('1901','期末余额')` |
| `BS-014` | 其他流动资产 | listed_standalone | `TB('1901','期末余额') + TB('1131','期末余额')` |

真科目是 `1901 待处理财产损溢`。活体 `render-config` 实测后果：

| 项目 | K2 显示的「其他流动资产」 | 实际是什么 |
|---|---|---|
| `0ec33ac9` / wp `919e3387` | `tb_values.other_current_audited = 28,464,225.16`；`adjudication_prefill` 建出 3 行：**坏账准备_应收账款 26,401,719.77 / 坏账准备_应收票据 1,162,288.03 / 坏账准备_其他应收款 900,217.36** | 全是坏账准备 |
| `2aa00f57` / wp `d5f0d168` | `3,436,387.56`；预填 2 行坏账准备（金额为负） | 同上 |

即 K2 把**别的循环的备抵科目当成资产列示**，且与 D1/D2/K1 的坏账准备重复计入。
`1901` 在本库全部项目均为 0 → K2 真实口径下本应无数据。

### 二、K2-1 审定表的二级子明细是固定 8 行（应为动态行）

`useK2Adjudication.K2_ADJ_ITEMS` 硬编码 8 行：

```
合同取得成本 / 预付款项 / 待摊费用 / 待抵扣税额 / 合同资产 / 押金保证金 / 应收款项转让 / 其他
```

这 8 行本身是其他流动资产的**二级子明细**（客户可能把预付性质、押金性质的款项挂在
其他流动资产下核算），不是别的循环的科目，**不做「外来行」判定、不加警示、不删除**。
问题只在「固定枚举」这一点上：

1. **与源模板举例不符**。源 xlsx `审定表K2-1` A7:A13 是
   `待摊费用 / 待抵扣进项税 / 房租物业费 / 预缴企业所得税 / 委托贷款 / 预缴其他税费 / 应收退货成本`
   —— 与那 8 行不重合，两组都只是二级子明细的举例。
2. **固定枚举两头堵**：客户实际有的项目无处填，客户实际没有的项目占着空行。
3. **本应是动态行**。源模板上市披露 sheet `A5` 逐字写着
   「其他流动资产（注：**根据实际情况列示；不存在的项目请删除**）」，国企侧 `A6` 写
   「（根据性质选择披露方式）」；`明细表K2-2` A19 留空白追加行、A30 编制说明引用
   财会〔2018〕15号列举「一年内到期的债权投资 / 合同取得成本（摊销期≤1年）/ 应收退货成本」
   —— 均说明项目行随客户实际情况增删，不是固定枚举。
   同循环的 `useK2Detail`（K2-2 明细表）**已经是动态行**（`addRow` + `ElMessageBox.prompt`
   命名 + `removeRow` + `addRowDirect`），只有 K2-1 审定表停留在固定行。

`seedFromPrefill` 还用**模糊包含匹配**把预填行名往 8 个固定 label 上凑，未命中一律塞
`other` 行 → 当前实测下「坏账准备_应收账款」等三行全部堆进「其他」行。

### 三、公式管理预设整块是销售费用（复制粘贴事故）

`prefill_formula_mapping.json` 的 K2 块：

```json
{ "wp_code": "K2", "wp_name": "销售费用审定表", "sheet": "审定表K2-1",
  "account_codes": ["6601"],
  "cells": [ {"formula": "=TB('6601','期初余额')"}, {"formula": "=TB('6601','期末余额')"},
             {"formula": "=ADJ('6601','aje_net')"}, {"formula": "=ADJ('6601','rje_net')"}, ... ] }
```

`6601` 是**销售费用**（K8 循环的科目），`wp_name` 也写成「销售费用审定表」。

### 四、后端披露 sheet 名与源 xlsx 漂移

后端 `K2_SHEETS` 写 `附注披露信息（国有企业）`，源 xlsx tab 名是 `附注披露信息（国企）`
（openpyxl 实测；前端常量 `K2_DISCLOSURE_SHEET_NAME` 已经是对的）。

### 范围界定

K2 的**披露表 / 附注结构**已由归档 spec `k2-other-current-assets-disclosure-alignment`
完成（22/22 + 浏览器实测），本 spec **不动**披露列结构与附注模板，只做：四表取数口径、
K2-1 动态行、公式预设、sheet 名。K3~K13 的同类问题沿用本 spec 范式另立。

## Glossary

| 术语 | 含义 |
|------|------|
| 原始码 | `tb_balance.account_code`，客户自有科目编码，点号分级 |
| 标准码 | `trial_balance.standard_account_code` / `report_config` 公式引用码，横杠分级 |
| 四表共享件 | `backend/app/services/four_table/{report_line_accounts,leaf_aggregation}.py`（K1 spec 建立） |
| 动态行 | 可增删改名的行（`rowId` 标识），新增须先 `ElMessageBox.prompt` 输入名称 |
| 宁缺勿造 | 无法从四表库干净映射的项目行**不 seed**，留给审计师手工录入 |
| 别循环已占用科目 | 已被其它报表行引用的科目（如 `1123` 预付款项 → `BS-008`），K2 不得重复取 |

## Requirements

### Requirement 1: K2 科目定位改由报表映射规则解析

**User Story:** 作为审计助理，我希望 K2 显示的其他流动资产是真的其他流动资产，
而不是别的科目的坏账准备。

#### Acceptance Criteria

1.1 WHEN K2 render 解析科目 THEN 系统 SHALL 经共享件
`resolve_report_line_accounts(ctx, spec)` 按报表行 `BS-014` 解析（复用 K1 建立的
`four_table/report_line_accounts.py`），SHALL NOT 硬编码任何科目前缀。

1.2 WHEN 解析完成 THEN 原值科目集 SHALL NOT 包含 `1231*`（坏账准备族）；
`account_codes` 输出 SHALL 反映解析结果而非写死 `["1231"]`。

1.3 WHEN 报表公式含 `TB('1131')`（实证 `listed_standalone` 的 `BS-014` 引用了应收股利）
THEN 系统 SHALL 把它归入 `extra_standard_codes` 单列，SHALL NOT 并入其他流动资产原值
（`1131` 已被 `BS-009 其他应收款` 引用，重复计入会虚增资产）。

1.4 WHEN 聚合 `tb_balance` THEN 系统 SHALL 用共享件 `select_leaves` + `aggregate_leaves`
的**叶子口径**，且前缀匹配 SHALL 要求点号边界（`1901` 不得命中 `19010`）。

1.5 WHEN 从 `trial_balance` 取未审/审定额 THEN 系统 SHALL 按**最长前缀**归属，
SHALL NOT 让父码与子码双计。

1.6 IF 解析链任一环失败 THEN 系统 SHALL fail-open 回退兜底科目并继续渲染，
且在 `tb_source_codes.resolved_from` 标注来源。

1.7 WHEN render 返回 THEN 输出 SHALL 含 `tb_source_codes`，且被前端 K2 界面消费展示
（复用 K1 的溯源面板范式，不得成为 dead output）。

### Requirement 2: K2-1 审定表改为动态行

**User Story:** 作为审计助理，我希望 K2-1 的项目行能按客户实际情况增删改名，
而不是被 8 个写死的项目框住。

#### Acceptance Criteria

2.1 WHEN 渲染 K2-1 审定表 THEN 行集 SHALL 由持久化的动态行清单驱动
（`rowId` 标识 + 行名可编辑），SHALL NOT 由硬编码枚举驱动。

2.2 WHEN 用户新增行 THEN 系统 SHALL 先 `ElMessageBox.prompt` 要求输入项目名称
（平台铁律：动态行新增需命名），名称为空或重复时 SHALL 提示并拒绝。

2.3 WHEN 用户删除行 THEN 系统 SHALL 同时清理该行所有 `K2-1-{rowId}-*` 持久化键，
不留孤儿数据。

2.4 WHEN 存在历史固定行数据（`K2-1-contract-cost-*` 等 8 个旧 rowKey）
THEN 系统 SHALL 迁移为动态行（保留行名与金额），SHALL NOT 丢数据。

2.5 WHEN 迁移历史数据 THEN 那 8 个旧行 SHALL 一视同仁按二级子明细迁移
（有录入的迁、从未填过的不占位），SHALL NOT 按「归属别的报表行」做任何警示或差异化处理
—— 它们都是其他流动资产的二级子明细。

2.6 WHEN 从四表库 seed 行 THEN 系统 SHALL 按实际叶子科目名建行（宁缺勿造：
解析不出科目时不建行、不塞「其他」兜底行）。

2.9 WHEN 四表库重新入库后用户点「刷新取数」 THEN 系统 SHALL 动态插入新出现的明细子科目行，
对已有行 SHALL 按**科目码**优先匹配（行名被改过也不重复建行）；
金额有变化时 SHALL 先弹确认，确认后 SHALL 只覆盖 `source='tb'` 的行，
手工新增 / 历史迁移行的已录值 SHALL NOT 被覆盖。

2.7 WHEN K2-2 明细表已有行 THEN K2-1 SHALL 提供「从 K2-2 带入」按钮按行名聚合，
与既有 `useK2CrossSheet` 同源。

2.8 WHEN 合计行计算 THEN SHALL 覆盖全部动态行，三角勾稽（期末 = 期初 + 借 − 贷）
与审定公式（审定 = 未审 + AJE + RJE）行为不变。

### Requirement 3: 公式管理预设纠偏

**User Story:** 作为现场经理，我希望 K2 的公式预设是其他流动资产的公式，不是销售费用的。

#### Acceptance Criteria

3.1 WHEN 查看 K2-1 公式预设 THEN `wp_name` SHALL 为「其他流动资产审定表」，
`account_codes` SHALL NOT 含 `6601`。

3.2 WHEN 查看 K2-1 公式预设 THEN 公式 SHALL 引用 `BS-014` 解析出的科目
（`TB('1901','期初余额')` / `TB('1901','期末余额')` / `ADJ('1901',…)`），
SHALL NOT 出现任何 `6601` 或 `1231`。

3.3 WHEN 查看 K2-1 公式预设 THEN SHALL 含跨底稿取数
`WP('K2','明细表K2-2','审定数期末数')`（审定表可用 WP）。

3.4 WHEN 查看 K2-2 明细表预设 THEN SHALL NOT 引入 `WP()`（防 K2-1↔K2-2 循环）。

3.5 WHEN `convert_prefill_presets()` 收敛 THEN K2 条目 SHALL 归入 `workpaper:K2`
且 `formula_type == 'auto_calc'`。

### Requirement 4: 披露 sheet 名与源 xlsx 逐字一致

**User Story:** 作为审计助理，我希望附注里点「打开同步底稿」能直接跳到 K2 的披露页，而不是落回底稿目录。

#### Acceptance Criteria

4.1 WHEN 后端 `K2_SHEETS` 声明披露 sheet THEN 名称 SHALL 逐字等于源 xlsx tab 名
（`附注披露信息（上市公司）` / `附注披露信息（国企）`），SHALL NOT 写「国有企业」。

4.2 WHEN 守卫运行 THEN SHALL 用 openpyxl 直读源 xlsx 比对后端常量与前端
`K2_DISCLOSURE_SHEET_NAME`，三者逐字一致。

### Requirement 5: 守卫

**User Story:** 作为质量控制复核合伙人，我希望取错科目族这种错误一旦修好就不会再被悄悄改回去。

#### Acceptance Criteria

5.1 WHEN 运行 K2 后端守卫 THEN SHALL 断言：科目解析不含 `1231*`、叶子口径、
`trial_balance` 最长前缀归属、fail-open、`tb_source_codes` 形态。

5.2 WHEN 运行 K2 前端守卫 THEN SHALL 断言：动态行增删改名、历史固定行迁移不丢数、
四表 seed 宁缺勿造（无科目不建行）、合计覆盖动态行。

5.3 WHEN 运行守卫 THEN SHALL 含**反向自检**（断言旧的错误口径确实会被判红），
防断言空转。

5.4 WHEN 运行公式预设守卫 THEN SHALL 断言 K2 块无 `6601`/`1231`、K2-2 无 `WP(`。

### Requirement 6: 端到端实测

**User Story:** 作为用户，我要在界面上确认 K2 不再显示坏账准备，且项目行能按实际情况增删。

#### Acceptance Criteria

6.1 WHEN 在真实项目打开 K2-1 THEN 界面 SHALL NOT 再出现「坏账准备_*」项目行，
`tb_values` SHALL NOT 等于 `1231` 口径金额（`0ec33ac9` 的 28,464,225.16）。

6.2 WHEN 新增/改名/删除动态行 THEN 持久化 SHALL 正确落库并在刷新后保持。

6.3 WHEN 实测完成 THEN 所有为实测写入的数据 SHALL 被复原。
