# Design Document

## Overview

补齐 N 类（N1~N5）附注模板的表格结构（`_tables` + `columns` + `guidance`），补充 3 个披露 sheet 的公式预设块，并端到端验证「四表入库→render 取数→披露 Tab→同步附注→正确渲染」全链路。

## Architecture

### 源模板结构事实基线（openpyxl 逐格实证）

#### N1 递延所得税（五、30 / 八、31）—— 4/5 张表

**表(1) 未经抵销的递延所得税资产和递延所得税负债**
- 上市 R10:R11 两级表头：`项目` rowspan2 / `期末余额` colspan2 (`可抵扣/应纳税暂时性差异`, `递延所得税资产/负债`) / `上年年末余额` colspan2 (同)
- 国企 R10:R11 两级表头：`项目` rowspan2 / `期末余额` colspan2 (`递延所得税资产/负债`, `可抵扣/应纳税暂时性差异`) / `年初余额` colspan2 (同) ← **列序反转**
- 合并区实证：`A10:A11`(项目), `B10:C10`(期末), `D10:E10`(上年/年初)
- 资产段固定行（R12「递延所得税资产：」+ R13~R19 七分类 + R20 空行可扩 + R21 小计 SUM(B13:B20)）
- 负债段固定行（R22「递延所得税负债：」+ R23~R27 五分类 + R28 空行可扩 + R29 小计）
- 国企资产段 R13~R19 的 A 列全是 `='附注披露信息（上市公司）'!A13~A19`（跨 sheet 引用）

**表(2) 以抵销后净额列示（不适用的删除）**
- 上市 R33:R34 表头 5 列：项目 / 递延所得税资产和负债期末互抵金额 / 抵销后递延所得税资产或负债期末余额 / 同期初
- 国企 (2)A 互抵后：R34 5 列 `项目 / 报告期末互抵后的递延所得税资产或负债 / …暂时性差异 / 报告年初…`
- 固定 2 行：递延所得税资产 / 递延所得税负债

**国企独有 (2)B 互抵明细（R49~）**
- R49:R50 两级表头：项目 / 期末余额{互抵金额,互抵后金额} / 年初余额{互抵金额,互抵后金额}
- 固定 2 行：递延所得税资产 / 递延所得税负债

**表(3) 未确认DTA的可抵扣暂时性差异及可抵扣亏损明细**
- 上市 R37:R38 / 国企 R56: 3 列 flat（项目/期末余额/上年年末余额 | 项目/期末余额/年初余额）
- 固定 2 行 + 合计 = SUM

**表(4) 未确认DTA的可抵扣亏损到期年度**
- 上市 R44:R45 / 国企 R63: 4 列 flat（年份/期末余额/上年年末余额/备注 | 年份/期末余额/年初余额/备注）
- 动态行：auditYear+1 ~ auditYear+5 + 无使用期限（共 6 行）

#### N2 应交税费（五、41 / 八、41）—— 各 1 张表

**上市**：R7 表头 3 列 `税项 | 期末余额 | 上年年末余额`
- R8~R22 动态（公式 `='应交税费审定表N2-1'!A7~A19`，I 列审定数、E 列期初）
- R23 合计 = SUM(B8:B22) / SUM(C8:C22)
- R25~R27 说明文字

**国企**：R7 表头 5 列 `项目 | 期初余额 | 本期应交 | 本期已交 | 期末余额`
- R8~R22 动态（公式 `='应交税费明细表N2-2'!A10~A22`，M/N/O 列）
- E 列行内公式 `=B8+C8-D8`
- R23 合计 5 列 SUM
- R24 提示

#### N4 税金及附加（五、63）—— 1 张表（仅上市）

R7 表头 3 列 `项目 | 本期发生额 | 上期发生额`
- R8~R16 动态（公式 `='税金及附加审定表N4-1'!A7~A14`，I 列/E 列）
- R17 合计 = SUM(B8:B16) / SUM(C8:C16)
- R18 说明
- **国企 R6 逐字「无」→ 不建表**

#### N5 所得税费用（三、所得税费用 / 八、78）—— 各 2 张表

**表(1) 所得税费用明细**
- 上市 R7:R8 表头 3 列 flat `项目 | 本期发生额 | 上期发生额`（C 列起始，B 列空）
- 上市 3 行：按税法及相关规定计算的当期所得税 / 递延所得税费用 / 合计
- 国企 R7 同列，**4 行**：当期所得税费用 / 递延所得税调整 / **其他** / 合计

**表(2) 会计利润与所得税费用调整过程**
- 上市 R12:R13 表头同列
- 上市 R14~R25 动态（12 行，公式从 N5-2!A9~A20/B9~B20/D9~D20）
- 国企 R13:R14 同；R15~R28 动态（14 行，从 N5-2!A9~A22/B/D）
- R27~R29/R30~R32 提示文字

### 列定义设计

全部复用现有 `n1NoteSectionMap.ts` / `n2NoteSectionMap.ts` / `n4NoteSectionMap.ts` / `n5NoteSectionMap.ts` 中已声明的列 key/label/group：

- N1 表(1)：`group='期末余额'` + 叶子 `diff`/`dta_dtl`，`group='上年年末余额'`/`年初余额` + 叶子同
- N2 上市：flat 3 列 `label/end/prior`
- N2 国企：flat 5 列 `label/opening/payable/paid/end`
- N4：flat 3 列 `label/current/prior`
- N5 表(1)：flat 3 列 `label/current/prior`
- N5 表(2)：flat 3 列 `label/current/prior`

### 动态插行区识别

| 表 | 动态区域 | 驱动源 |
|---|---|---|
| N1(1) 资产段 | R13~R20（第 20 行空行可扩）| tb_balance 1811 子科目按名归类 |
| N1(1) 负债段 | R23~R28 | tb_balance 2901 子科目按名归类 |
| N1(4) 亏损到期 | 5~6 年动态 | `auditYear+1 ~ auditYear+5` + 无使用期限 |
| N2 上市 | R8~R22 税种行 | N2-1 审定表实际税种行 |
| N2 国企 | R8~R22 税种行 | N2-2 明细表实际税种行 |
| N4 | R8~R16 税种行 | N4-1 审定表实际行 |
| N5(2) | R14~R25/R28 调整项 | N5-2 实际填写的调整行 |

### 公式预设设计

#### N2 披露块
```
block: "附注披露信息（上市公司）"
  - 税项期末审定数: WP('N2','应交税费审定表N2-1','期末审定数合计')
  - 上年年末余额: PREV('N2','附注披露信息（上市公司）','期末余额')

block: "附注披露信息（国企）"
  - 期初余额: WP('N2','应交税费明细表N2-2','期初余额合计')
  - 本期应交: WP('N2','应交税费明细表N2-2','本期应交合计')
  - 本期已交: WP('N2','应交税费明细表N2-2','本期已交合计')
```

#### N4 披露块
```
block: "附注披露信息（上市公司）"
  - 本期发生额: WP('N4','税金及附加审定表N4-1','本期审定数合计')
  - 上期发生额: PREV('N4','附注披露信息（上市公司）','本期发生额')
```

#### N5 披露块
```
block: "附注披露信息（上市公司）" / "附注披露信息（国企）"
  - 当期所得税: WP('N5','所得税费用审定表N5-1','当期所得税审定数')
  - 递延所得税: WP('N5','所得税费用审定表N5-1','递延所得税审定数')
  - 调整项×12/14: WP('N5','所得税费用明细表N5-2','各行金额')
```

## Components and Interfaces

### 幂等脚本 `backend/scripts/fix/fix_note_n_cycle_full_structure.py`

- 按 `_note_structure_kit` 共享工具实现
- 逐章节声明 `columns`/`guidance`/`rows`（rows 只用于初始骨架行，动态行由推送覆盖）
- `--check` exit 0 = 无欠账

### 前端契约 `nCycleNoteSubtableContract.spec.ts`

- 复用 `_disclosureSubtableContract.helper.spec.ts` 的 P1~P6
- 覆盖 N1(4表)/N2(2表)/N4(1表)/N5(4表) 共 11 张表

### 后端守卫 `test_note_n_cycle_full_structure.py`

- openpyxl 直读源 xlsx 交叉比对行数/列头/合并区
- 反向自检（`_norm` + 文件长度 + 表数锚点）

## Data Models

### 附注模板新增 `_tables` 结构一览

| 章节 | 表名 | columns 数 | 行数(seed) | flat/group |
|------|------|-----------|-----------|------------|
| 五、30 | 未经抵销的递延所得税资产和递延所得税负债 | 5(两级) | 资产7+空+小计 + 负债5+空+小计 = 16 | group |
| 五、30 | 以抵销后净额列示的递延所得税资产或负债 | 5 | 2 | flat |
| 五、30 | 未确认递延所得税资产的可抵扣暂时性差异及可抵扣亏损明细 | 3 | 2+合计 | flat |
| 五、30 | 未确认递延所得税资产的可抵扣亏损将于以下年度到期 | 4 | 6(动态年份) | flat |
| 八、31 | 已确认递延所得税资产和递延所得税负债 | 5(两级) | 同 | group |
| 八、31 | 互抵后的递延所得税资产或负债 | 5 | 2 | flat |
| 八、31 | 递延所得税资产和递延所得税负债互抵明细 | 5(两级) | 2 | group |
| 八、31 | 未确认递延所得税资产明细 | 3 | 2+合计 | flat |
| 八、31 | 未确认递延所得税资产的可抵扣亏损将于以下年度到期 | 4 | 6 | flat |
| 五、41 | 应交税费 | 3 | 15(动态)+合计 | flat |
| 八、41 | 应交税费 | 5 | 15(动态)+合计 | flat |
| 五、63 | 税金及附加 | 3 | 8(动态)+合计 | flat |
| 三、所得税费用 | 所得税费用明细 | 3 | 3+合计 | flat |
| 三、所得税费用 | 会计利润与所得税费用调整过程 | 3 | 12(动态) | flat |
| 八、78 | 所得税费用 | 3 | 4+合计 | flat |
| 八、78 | 会计利润与所得税费用调整过程 | 3 | 14(动态) | flat |

## Correctness Properties

### Property 1: 附注模板表数覆盖
**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7**

`fix_note_n_cycle_full_structure.py --check` exit 0 且各章节 `_tables` 非空。

### Property 2: 列定义双向锁死
**Validates: Requirements 1.8**

前端 `buildNxListedColumns`/`buildNxSoeColumns` 的 key 集合 ≡ 模板 `_tables[].columns[].key` 集合（逐表逐字）。

### Property 3: 动态行标识正确
**Validates: Requirements 1.1, 1.3, 1.5, 1.6, 1.7**

N1(1) 资产/负债段的可扩行、N2/N4/N5 的动态税种/调整行在 seed 中用骨架行表示，推送时整表覆盖。

### Property 4: 公式预设完备
**Validates: Requirements 2.1, 2.2, 2.3**

N2/N4/N5 三个披露 sheet 块各有 ≥2 条公式，科目码与 render 的 `_resolve_account_codes` 一致。

### Property 5: 全链路数据贯通
**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

真实 DB 直跑 render 后 `tb_source_codes` 非空 → 披露 Tab 可构造载荷 → POST 成功 → 附注 `last_sync_at` 前移 + 子表正确。

### Property 6: 无凭空父表头
**Validates: Requirements 3.5**

所有推送路径的 `_column_groups` 为 `[]`（flat 生效）或正确的显式分组，绝不出现 `_infer_groups_from_headers` 推断产物。

### Property 7: 国企 N4 不推送
**Validates: Requirements 3.3**

`buildN4SyncPayload('soe')` 恒返回 null，国企 Tab 显示「本版不适用」。

### Property 8: N3 无独立章节
**Validates: Requirements 3.1**

N3 循环无披露 Tab、无附注章节（与 N1 共节 五、30/八、31），守卫 `CYCLES_WITHOUT_DISCLOSURE.N3` 存在。

### Property 9: 幂等脚本幂等
**Validates: Requirements 1.10**

连续执行两次 `--apply` 后，第二次 `--check` 仍 exit 0 且 JSON 逐字节不变。

### Property 10: CI 守卫覆盖
**Validates: Requirements 4.1, 4.2, 4.3, 4.4**

`governance-checks.yml` 含 job `note-n-cycle-full-structure`，跑后端 + 前端守卫，全绿。
