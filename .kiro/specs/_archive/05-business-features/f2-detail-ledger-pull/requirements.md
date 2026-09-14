# Requirements Document

## Introduction

F2-3~F2-13 存货明细表（原材料/库存商品/委托加工/开发产品/开发成本/合同履约/消耗性生物/商品进销差价/周转材料/自制半成品/发出商品）当前审计师**逐行手打**期初/本期增加/本期减少——缺少从四表库（序时账 `tb_ledger` / 辅助余额 `tb_aux_balance`）一键取数入口。

K8/K9 管理/销售费用已证范式=`expenseLedgerMonthlyPull.ts`（纯前端游标分页拉 `/api/projects/{pid}/ledger/entries/{account_code}`，按明细科目×月聚合借−贷），可直接复用于存货明细。

### 实测依据

- 各明细表对应科目：F2-3(1401)/F2-4(1402)/F2-5(1403)/F2-6(1404)/F2-7(1405)/F2-8(1406)/F2-9(1407)/F2-10(1408)/F2-11(1409)/F2-12(1410)/F2-13(1411)（1412 商品进销差价无独立明细表；1471 跌价走 F2-14 调整分录）
- `tb_ledger` 对存货科目有真实数据（借方=增加/贷方=减少，按月+按明细科目名归集）
- 前端已有 `expenseLedgerMonthlyPull.ts`（K8/K9 proven），逻辑=按 account_code 拉序时账→按 account_name 分组×月→聚合借−贷→产出行
- F2 各明细表行模型有 `itemName`/`opening`/`increase`/`decrease`/`closing`/`auditAdj` 等字段

### 诚实的取数边界

- **只取序时账科目级明细**（按明细科目名归集），不做项目/规格/仓库级拆分（tb_aux_balance 维度因企业而异，宁缺勿造）
- 「从序时账取数」≠ 替代手工录入：取数结果是**参考初始种子**，审计师可编辑/调整/覆盖
- 1412 商品进销差价无独立明细表→不在范围
- F2-14 调整分录/F2-1 审定表已由 `f2-four-table-extraction-refresh` spec 覆盖

## Requirements

### Requirement 1: 各明细表加「📥 从序时账取数」按钮

**User Story:** 作为审计助理，我希望 F2-3~F2-13 各明细表有「📥 从序时账取数」入口，一键按明细科目从序时账归集期初/增加/减少填入行。

#### Acceptance Criteria

1. WHEN F2-3 至 F2-13 中任一明细表的工具栏 THEN 系统 SHALL 显示「📥 从序时账取数」按钮，受编辑权限门控（只读禁用），灰度开关 `F2_FOUR_TABLE_EXTRACTION_ENABLED` 关闭时不显示。
2. WHEN 用户点击「从序时账取数」 THEN 系统 SHALL 调用前端纯游标分页拉取 `/api/projects/{pid}/ledger/entries/{account_code}?year={year}`（复用 K8/K9 `expenseLedgerMonthlyPull` 范式），按明细科目名（`account_name`）分组聚合：本期增加 = Σ借方（`debit_amount`）、本期减少 = Σ贷方（`credit_amount`）。
3. WHEN 取数完成 THEN 系统 SHALL 以 ElMessageBox.confirm 预览结果（匹配行数 / 未匹配行数 / 新增行数），用户确认后填入明细表行。
4. WHERE 明细表已有同名行（`itemName` 精确匹配归一化名称） THE 系统 SHALL 只覆盖空值字段（increase/decrease），不覆盖已有非零手工值（手工优先）。
5. WHERE 取数结果含明细表不存在的行 THE 系统 SHALL 追加新行（itemName=明细科目名，increase/decrease 从序时账填入）。
6. IF 序时账该科目无数据或取数失败 THEN 系统 SHALL 弹提示（ElMessage.info/warning），不阻断、不清空既有行。

### Requirement 2: 期初余额从 tb_balance 补填

**User Story:** 作为审计助理，各明细表行的「期初余额」也应能从四表库自动填入。

#### Acceptance Criteria

1. WHEN 「从序时账取数」执行时 THEN 系统 SHALL 同时查询 `tb_balance`（经 render 输出或前端 API）该科目前缀的叶子子科目期初余额（`opening_balance`），按明细科目名归集。
2. WHERE 某行 `opening` 字段为空或 0 THE 系统 SHALL 用 tb_balance 的 opening_balance 补填。
3. WHERE `opening` 字段已有非零值 THE 系统 SHALL 不覆盖（手工优先）。
4. WHERE tb_balance 无该子科目 THE 系统 SHALL 该字段不填（宁缺勿造）。

### Requirement 3: 取数口径与审定表一致

**User Story:** 明细表取数与 F2-1 审定表 Tier B 预填须口径一致，防汇总时与审定表有不可解释差异。

#### Acceptance Criteria

1. WHEN 明细表取数 THEN 系统 SHALL 用与审定表 Tier B 同源口径（`get_active_filter` 数据集版本，只取叶子科目 `_is_leaf`，跳零余额，资产借正贷负）。
2. WHERE 明细表汇总（期初合计/增加合计/减少合计） THE 系统 SHALL 与审定表 F2-1 该类别的 opening/increase/decrease 预期一致（容差 ≤ 1 元）。
3. IF 取数后两侧不一致 THEN 系统 SHALL 在明细表底部显示勾稽提示（与审定表差异值），不阻断。

### Requirement 4: 复用既有范式，不新造

**User Story:** 作为平台维护者，要求复用 K8/K9 已证的 `expenseLedgerMonthlyPull` 纯前端取数范式，不新造后端端点。

#### Acceptance Criteria

1. WHEN 实现明细表取数 THEN 系统 SHALL 复用或镜像 `expenseLedgerMonthlyPull.ts` 的纯前端游标分页逻辑（`/ledger/entries/{code}?year=&page=&page_size=200` 循环翻页，按 `account_name` 分组聚合），不新建后端 resolver/端点。
2. WHERE 期初数据（opening）需查 tb_balance THE 系统 SHALL 复用 render 已输出的 `tb_values`（灰度开含各类别期初）或前端调已有 API。
3. WHERE 取数结果需填入明细表行 THE 系统 SHALL 调各明细表 composable 既有的 `addRow` / `updateCell` / `setField` 接口，不绕开现有持久化路径。

### Requirement 5: 按明细表科目一一对应

**User Story:** 各明细表只取自己对应的科目，不混入其他科目数据。

#### Acceptance Criteria

1. WHEN F2-3 明细表取数 THEN 系统 SHALL 仅拉 account_code=1401（原材料）的序时账。
2. WHEN F2-4/5/6/7/8/9/10/11/12/13 THEN 分别对应 1402/1403/1404/1405/1406/1407/1408/1409/1410/1411。
3. WHERE 某明细表对应科目的子科目（如 1401.01/1401.02）在序时账有独立行 THEN 取数 SHALL 按子科目名各自归集产出行（非按父科目合并），对齐审定表的叶子级聚合口径。

### Requirement 6: 零回归 + 灰度门控

**User Story:** 不破坏各明细表现有手工录入、导入导出、跨表联动、AI。

#### Acceptance Criteria

1. WHERE 引入「从序时账取数」入口 THE 系统 SHALL 受灰度开关 `F2_FOUR_TABLE_EXTRACTION_ENABLED` 门控（关闭时不显示按钮，明细表行为逐字节等价当前）。
2. WHEN 取数完成 THEN 系统 SHALL 不改变明细表 composable 的 `_triggerSave` / `_syncFullData` 路径（取数结果经正常 save 路径持久化，不绕开）。
3. WHEN 取数后 THEN F2-2 明细汇总 / F2-1 审定表 crossSheet 聚合 / F2 附注联动 / F2 导入导出 SHALL 不受影响。

### Requirement 7: 正确性属性可测

**User Story:** 作为质控，关键取数正确性属性须有属性测试守卫。

#### Acceptance Criteria

1. WHEN 编写测试 THEN 覆盖：R1.2 按科目名归集 / R1.4 手工优先 / R1.5 追加新行 / R1.6 取数失败不阻断 / R2.1 期初从 tb_balance / R3.1 get_active_filter + _is_leaf / R4.1 复用 ledger/entries 端点 / R5.1-3 科目一一对应 / R6.1 灰度零回归。

## Glossary

| 术语 | 含义 |
|------|------|
| F2-3~F2-13 | 存货 11 张明细表（原材料/材料采购在途/周转材料/自制半成品/委托加工/库存商品/发出商品/开发产品/开发成本/合同履约/消耗性生物） |
| `expenseLedgerMonthlyPull` | K8/K9 已证的纯前端序时账取数范式（游标分页拉 ledger/entries，按科目名×月归集） |
| 手工优先 | 明细表行已有非零手工值时不被取数覆盖 |
| 灰度开关 | `F2_FOUR_TABLE_EXTRACTION_ENABLED`（默认 False，关闭时功能不可见） |
| `_is_leaf` | 叶子科目判定（code 不是任何其它 code 前缀，防 rollup 双算） |
