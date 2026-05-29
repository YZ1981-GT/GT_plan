# E1-2 现金明细表 prefill 映射设计稿

> 锚定 tasks.md 1.6a / requirements F2.2;基于 Sprint 0.4 表样基线;评审通过后落入 prefill_formula_mapping.json (Task 1.7)
>
> v0.2 修订(2026-05-17):核验后纠正"AUX 取币种"假设——`tb_aux_balance.aux_type` 实际场景多为 客户/项目/部门 等业务维度,而**币种是 tb_balance.currency_code 列**(grep 实测 yonyou/identifier 适配器都把"币种"映射到 `currency_code` 标准字段)。E1-2 多币种 prefill 必须改走"按 currency_code 过滤的 TB"路径,不能用现有 AUX 解析器。

## 1. sheet 名(唯一真源)

`现金明细表E1-2`(精确名,带 sheet 编号后缀,与 wp_template_metadata.formula_cells 中保持一致)

## 2. 表样格式核验(openpyxl 实测,2026-05-17)

| 行号 | A 列 | B 列 | C 列 | D 列 | E 列 | F 列 | G 列 | H 列 | I 列 | J 列 |
|------|------|------|------|------|------|------|------|------|------|------|
| R13 | 币种 | 未审数(人民币) | (合并) | (合并) | (合并) | (合并) | (合并) | 审计调整-原币 | 期末审定数 | 备注 |
| R14 | (合并) | 期初余额 | 本期增加 | 本期减少 | 期末余额(原币) | 期末折算汇率 | 期末折算人民币金额 | (合并) | (合并) | (合并) |
| R15 | 人民币 | (TB 取数) | (LEDGER 借方) | (LEDGER 贷方) | =B15+C15-D15 (内置) | 1.0 | =E15*F15 (内置) | (用户填) | =G15+H15*F15 (内置) | NOTE1 |
| R16 | 美元 | (按 currency 取数) | (按 currency 取数) | (按 currency 取数) | (内置) | (用户填) | (内置) | (用户填) | (内置) | |
| R17 | 日元 | (同上) | (同上) | (同上) | (内置) | (用户填) | (内置) | (用户填) | (内置) | |
| R18 | 澳元 | (同上) | (同上) | (同上) | (内置) | (用户填) | (内置) | (用户填) | (内置) | |
| R19 | 欧元 | (同上) | (同上) | (同上) | (内置) | (用户填) | (内置) | (用户填) | (内置) | |
| R20 | (空,可选币种) | | | | (内置) | (用户填) | (内置) | (用户填) | (内置) | |
| R21 | (空,可选币种) | | | | (内置) | (用户填) | (内置) | (用户填) | (内置) | |
| **R22** | **合计** | **=SUM(B15:B21)** | **=SUM(C15:C21)** | **=SUM(D15:D21)** | **=SUM(E15:E21)** | **=SUM(F15:F21)** | **=SUM(G15:G21)** | **=SUM(H15:H21)** | **=SUM(I15:I21)** | |
| R23 | 其中:存放在境外的款项总额 | (用户填) | (用户填) | (用户填) | =B23+C23-D23 (内置) | (用户填) | =E23+F23 (内置) | | | |

**关键约束**:R22/R23 已含合计/计算公式,**严禁 prefill 覆盖**(由 Task 1.1 _is_formula_cell 守护)。

## 3. prefill 目标 cell 设计(本轮可落地)

### 3.1 R15 人民币行 — 主科目 1001 全币种汇总(单测可覆盖,本轮必做)

| cell_ref | formula | formula_type | 说明 |
|----------|---------|--------------|------|
| B15 | `=TB('1001','期初余额')` | TB | 库存现金期初余额(全币种合计,单币种项目即等于本币) |
| C15 | `=LEDGER('1001','借','全年')` | LEDGER | 库存现金本期借方发生额(本期增加) |
| D15 | `=LEDGER('1001','贷','全年')` | LEDGER | 库存现金本期贷方发生额(本期减少) |
| F15 | 1.0 (常量) | _literal | 人民币本币汇率默认 1.0 |

**注**:E15(期末原币)/G15(期末人民币)/I15(审定数) 是 Univer 内置公式,不 prefill。

### 3.2 R16-R19 外币行 — 暂不 prefill 数据(本轮)

理由:`tb_balance.currency_code` 是表上字段不是 aux 维度,现有 6 种公式(TB/SUM_TB/AUX/PREV/ADJ/NOTE) + 新增 4 种(WP/LEDGER/LEDGER_DETAIL/COUNT_LEDGER) 都无法精确按"科目+币种"过滤。

**TD-11 后续扩展方案**(独立 spec):
- 增加第 11 种公式 `TB_CCY('1001','USD','期初余额')` → tb_balance WHERE account_code='1001' AND currency_code='USD'
- 或扩展 TB 签名 `TB('1001','期初余额', currency='USD')`(向后兼容)
- 或扩展 LEDGER 接受 currency 第 4 参数 `LEDGER('1001','借','全年','USD')`

**本轮 fallback**:外币行 R16-R19 留空让用户手填,避免给错误 0 误导审计判断。

### 3.3 R20-R21 预留扩展币种 — 不 prefill

### 3.4 R23 境外款项 — 不 prefill(用户判断填列)

## 4. 总计 prefill cell 数(本轮)

**4 cells**(B15/C15/D15/F15)— 即 1.6a 落地的最小集合;TD-11 落地后可扩展到 16 cells

## 5. 前置条件与 fallback

- 当 `Project.has_foreign_currency = false` 时,无影响(只填 R15)
- LEDGER 公式期间默认"全年";若需期间分段(如截止测试)走 LEDGER_DETAIL 不在本 mapping 范围
- F15 = 1.0 是常量 prefill,通过 prefill_engine 写入"_literal" 类型(若 prefill_engine 不支持常量,降级为后端 ChainOrchestrator 直接写值)

## 6. 评审锚点

- [x] 列头位置实测(R13/R14 双行复合表头)
- [x] R22/R23 合计公式标记为禁写区
- [x] LEDGER 公式期间默认"全年"
- [x] 外币行 R16-R19 标记为 TD-11 范围,本 spec 不实施(避免提交错误数据)
- [x] grep 反查"币种"实际字段:确认 `tb_balance.currency_code` 不是 aux_type
