# Design Document

## Overview

将八套函证替代程序数据 composable 收敛为「单一 Shared_Core 工厂 `createAlternativeConfirmationData(config)` + 每套薄适配器」。设计以 requirements 的**零回归**为最高约束：工厂只吸收八套**逐字相同**的核心逻辑；八套之间**真实存在的异质面**（经本阶段实测，见 §2 差异矩阵）由每套薄适配器保留，不强行塞入工厂造成行为漂移。

**设计基调（实测后修正）**：初判"八套近乎逐字重复、可一个工厂全覆盖"过于乐观。实测发现异质性显著——构造签名四种、比例方法名两类、K06 的 load/persist 是 http IO（非内存 htmlData）、K05/L05 有独有 `balanceSummary`、依赖不同 FormulaEngine。因此工厂覆盖**Shared_Core（约占每文件 70%）**，异质面经 config 参数化或在适配器旁挂。此为 Requirement 3（边界）实测结论的落地。

## Architecture

三层结构：

1. **Shared_Core 工厂层** `createAlternativeConfirmationData(config)`：单一实现八套逐字相同的核心逻辑（state、公司/区块 CRUD、getBlockTotal、通用 getRatio、getCompletionStatus、hasAbnormal、metrics 骨架、可选 init/watch、buildPayload 骨架）。
2. **配置层** `AltConfig`：以纯数据声明八套差异（format / defaultBalance / getSumFields / 比例规则 / 基数 / metrics 映射 / FormulaEngine 注入 / emptyBase）。
3. **适配器层**（八套 Alt_Composable 各一，保持原导出名与签名）：构造 AltConfig 调用工厂，并承载无法配置化的异质面（命名比例方法别名、构造签名变体、K06 的 http load/persist、importFromSummary、balanceSummary、独有导出）。

数据流：Caller → 适配器（原签名不变）→ 工厂（Shared_Core + config 驱动）→ 返回与收敛前逐字一致的对象形状。工厂**不吸收 IO**（K06 的 http load/persist 留在适配器），保证零行为漂移。

## 2. 八套差异矩阵（实测，Requirement 2/3 的单一参考）

| 维度 | D05 | D06 | F05 | F06 | H05 | K05 | K06 | L05 |
|---|---|---|---|---|---|---|---|---|
| 构造签名 | `(props)` | `(props)` | `(props)` | `(props)` | `(props+wpId/projectId)` | `(wpId,projectId)‖(props)` 重载 default | `(wpId,projectId)` default | `(props+wpId/projectId)` +default |
| `_format` | alternative-d05-v1 | -d06-v1 | -f05-v1 | -f06-v1 | -h05-v1 | -k05-v1 | -k06-v1 | -l05-v1 |
| 默认 balance | `{}` | `{}` | `{item_name:预付账款}` | `{item_name:应付账款}` | `{item_name:固定资产}` | `{item_name:其他应收款}` | `{item_name:其他应付款}` | `{item_name:长期应付款/借款}` |
| getSumFields 来源 | blockColumnConfigs | blockColumnConfigsD06 | …F05 | …F06 | …H05 | 内联 SUM_FIELDS(K05) | 内联 SUM_FIELDS(K06) | 内联 SUM_FIELDS(L05) |
| 比例 API | `getCheckRatio(c,'receipt'‖'shipment')` | 同 | `(c,'payment'‖'inbound')` | 同 | `(c,'ownership'‖'acceptance')` | `(c,'post_receipt'‖'reconcile')` | **`getPostPaymentRatio(c)`+`getReconcileRatio(c)`** | **`getRepaymentRatio(c)`+`getMortgageRatio(c)`** |
| 比例基数 | `sales_amount` | `sales_amount` | `purchase_amount??sales_amount` | 同 | `closing_balance??ending_balance` | `closing_balance` | `closing_balance??credit_amount` | `closing_balance` |
| 比例1（block/字段） | receipt=b3.receipt_amount | receipt=**b4**.receipt_amount | payment=b3.(payment_amount??bank_amount) | inbound=b3.(voucher??invoice) | ownership=b2.(contract??invoice??payment) | post_receipt=b1.receipt_amount | postPayment=b1.paymentAmount | repayment=b1.(repayment_principal??voucher) |
| 比例2（block/字段） | shipment=b4.product_amount | shipment=**b3**.product_amount | inbound=b4.(voucher??invoice) | payment=b4.(payment??bank) | acceptance=b1.voucher_amount | reconcile=b4.self_balance | reconcile=b4.amount | mortgage=b4.(mortgage_amount??voucher) |
| 空基数返回 | null | null | null | null | null | null | null | **0（非 null）** |
| payload 比例键 | receipt_check_ratio / shipment_check_ratio | 同 | payment_check_ratio / inbound_check_ratio | inbound_check_ratio / payment_check_ratio | ownership_check_ratio / post_acceptance_ratio | receipt_check_ratio / reconcile_check_ratio | receipt_check_ratio / shipment_check_ratio | receipt_check_ratio / shipment_check_ratio |
| metrics receipt_ratio← | receipt | receipt | payment | payment | acceptance | post_receipt | postPayment | repayment |
| metrics shipment_ratio← | shipment | shipment | inbound | inbound | ownership | reconcile | reconcile | mortgage |
| FormulaEngine | 无(纯算术) | 无 | 无 | 无 | useH0FormulaEngine | useK0FormulaEngine | useK0FormulaEngine | useL0FormulaEngine |
| init/watch | htmlData+watch | 同 | 同 | 同 | htmlData+watch(loadAll) | htmlData+watch | **http render-config(loadAll)，无 watch** | htmlData+watch |
| persistAll | 无(仅 buildPayload) | 无 | 无 | 无 | =buildPayload | =buildPayload | **逐块 POST checklist-responses** | =buildPayload(+isDirty=false) |
| importFromSummary | 无 | 无 | 无 | 无 | 有(h0/H0-5) | 有(k0/K0-5) | 有(k0/K0-6) | 有(l0/L0-5，内部调 importCompanies) |
| loading ref | 无 | 无 | 无 | 无 | 有 | 有 | 有 | 有 |
| 独有返回 | — | — | — | — | loadAll/persistAll | +balanceSummary,getReconcileDiff | +BLOCK_TITLES_K06,无 balanceSummary | +balanceSummary,getBlockRows,getClosingBalance |

### 关键结论
- **Shared_Core 完全一致**（八套逐字相同）：`companies/isDirty/selectedCompanyId` state、公司 CRUD（add/delete/update/importCompanies 去重）、区块行 CRUD（add/delete/update）、`getBlockTotal`、`getCompletionStatus`（4 块非空计数）、`hasAbnormal`、`ensureCompanyId/ensureRowId`、`generateId`、`precise`、`metrics` 骨架。→ **工厂只写这一份。**
- **可配置化差异**：`_format`、默认 balance、`getSumFields`、比例规则（key/block/字段优先级/基数/空基数策略/payloadKey）、metrics ratio 映射、calc 函数（FormulaEngine 注入）。→ **进 Alt_Config。**
- **异质面（不进工厂，适配器旁挂）**：命名比例方法（K06/L05）、构造签名变体、K06 的 http load/per-block persist、importFromSummary、balanceSummary（K05/L05）、getReconcileDiff/getBlockRows/getClosingBalance/BLOCK_TITLES 等独有导出。→ **每套薄适配器保留原行为。**

## Data Models

工厂的核心数据模型是配置对象 `AltConfig` 与比例规则 `RatioRule`（下方 §Components 定义），以及复用既有的 `AlternativeCompany`/`CheckRow`/`BlockType`/`AlternativeD05Metrics`（`alternative*Types.ts`，不改）。八套 payload 类型（`AlternativeD05Payload`…`AlternativeL05Payload`）保持各自 literal `_format` 类型，由适配器的返回类型标注保留（Requirement 1.3）。

## Components and Interfaces

### 3. 工厂 API

```ts
// createAlternativeConfirmationData.ts
export interface RatioRule {
  key: string                 // 逻辑比例名，如 'receipt' | 'payment' | 'ownership' | 'postPayment'
  block: BlockType            // 求和目标区块
  fields: string[]            // 求和字段优先级（取第一个存在的 total）
  payloadKey: string          // 写回 balance 的字段名，如 'receipt_check_ratio'
}
export interface AltConfig {
  format: string                                   // payload _format
  getSumFields: (blockType: string) => string[]    // 区块合计字段来源
  defaultBalance: () => Record<string, any>        // 新增/导入公司默认 balance（函数避免共享引用）
  baseAmount: (company: AlternativeCompany) => number   // 比例分母（各自回退顺序封装于此）
  ratios: RatioRule[]                              // 两个比例规则
  emptyBase?: 'null' | 'zero'                      // 基数为 0/缺失时比例返回（默认 'null'；L05='zero'）
  metricRatioKeys: { receipt: string; shipment: string }  // metrics.ratio_distribution 映射到哪两个 ratio key
  calcTotal?: (amounts: number[]) => number        // 可注入 FormulaEngine 的合计（默认纯 sum）
  calcRatio?: (num: number, den: number) => number // 可注入 FormulaEngine 的比例（默认 num/den）
  parseNum?: (v: any) => number                    // 可注入（默认 Number()＋NaN→0，与各套一致）
  htmlData?: () => any                             // 提供则工厂做 init+watch；K06 不传（自管 loadAll）
}

export interface AltCoreReturn {
  companies: Ref<AlternativeCompany[]>
  isDirty: Ref<boolean>
  selectedCompanyId: Ref<string | null>
  addCompany; deleteCompany; updateCompany; importCompanies
  addBlockRow; deleteBlockRow; updateBlockField
  getBlockTotal
  getRatio: (company, key: string) => number | null   // 按 config.ratios[key] 计算（通用）
  getCompletionStatus; hasAbnormal
  metrics: ComputedRef<AlternativeD05Metrics>
  buildPayload: () => { _format: string; companies: AlternativeCompany[] }
  // 内部工具暴露给适配器复用
  _getBlockRows; _ensureCompanyId; _generateId; _precise; _initFromHtmlData
}

export function createAlternativeConfirmationData(config: AltConfig): AltCoreReturn
```

- `getRatio(company, key)`：查 `config.ratios[key]` → `getBlockTotal(company, rule.block)` → 取 `rule.fields` 首个非空 total → `base = config.baseAmount(company)` → base 无效时按 `emptyBase` 返回 null/0 → 否则 `precise(calcRatio(sum, base)*100)`。
- `buildPayload`：`{_format: config.format, companies: companies.map(c => ({...c, balance: {...c.balance, [ratio.payloadKey]: getRatio(c, ratio.key), ...}}))}`。
- `metrics`：`ratio_distribution` 用 `getRatio(c, metricRatioKeys.receipt/shipment)`。

## 4. 每套薄适配器设计

每套 Alt_Composable 退化为「构造 AltConfig + 调工厂 + 组装该套对外返回签名」。适配器负责：签名适配、命名比例方法别名、独有能力（balanceSummary/importFromSummary/K06 IO 等）。

### 4.1 无附加能力组（D05/D06/F05/F06）— 最干净
```ts
export function useAlternativeF05Data(props) {
  const core = createAlternativeConfirmationData({
    format: 'alternative-f05-v1',
    getSumFields: getSumFieldsF05,
    defaultBalance: () => ({ item_name: '预付账款' }),
    baseAmount: (c) => Number(c.balance?.purchase_amount ?? c.balance?.sales_amount ?? 0),
    ratios: [
      { key: 'payment', block: 'block3', fields: ['payment_amount','bank_amount'], payloadKey: 'payment_check_ratio' },
      { key: 'inbound', block: 'block4', fields: ['voucher_amount','invoice_amount'], payloadKey: 'inbound_check_ratio' },
    ],
    metricRatioKeys: { receipt: 'payment', shipment: 'inbound' },
    htmlData: props.htmlData,
  })
  // getCheckRatio(c, type) 别名 → core.getRatio(c, type)
  return { ...core, getCheckRatio: (c, type) => core.getRatio(c, type), buildPayload: core.buildPayload }
}
```
- D06 注意 receipt/shipment 的 block 与 D05 相反（receipt=b4, shipment=b3）——由 ratios 配置表达，非代码分支。
- D05 默认 balance `{}`；D05/D06 base=`sales_amount`。

### 4.2 H05（+loadAll/persistAll/importFromSummary/loading，FormulaEngine）
- config 注入 `calcTotal=calcBlockTotal(H0)`、`calcRatio=calcCheckRatio(H0)`、`parseNum(H0)`；`emptyBase:'null'`。
- 适配器旁挂：`loading` ref、`importFromSummary`(http h0/H0-5)、`loadAll=()=>core._initFromHtmlData(props.htmlData())`、`persistAll=core.buildPayload`。
- `getCheckRatio(c,'ownership'|'acceptance')` 别名 → `core.getRatio`。

### 4.3 K05（+balanceSummary+getReconcileDiff）
- config 注入 useK0FormulaEngine 的 calc*；ratios post_receipt(b1.receipt_amount)/reconcile(b4.self_balance)；base=`closing_balance`。
- 适配器旁挂：`balanceSummary`(computed，复用 core.getBlockTotal + core.companies)、`getReconcileDiff(row)`(calcReconcileDiff)、`loading`、`importFromSummary`(k0/K0-5)、`loadAll`、`persistAll`。
- 构造重载 `(wpId,projectId)‖(props)` 保留在适配器（内部归一后传 core）。

### 4.4 K06（异质最大：http load + per-block persist + 命名比例）
- **不传 `htmlData` 给工厂**（工厂不 init/watch）；适配器保留原 `loadAll`（http render-config 提取 K0-6 sheet）与 `persistAll`（逐块 POST checklist-responses）**逐字不变**。
- ratios postPayment(b1.paymentAmount)/reconcile(b4.amount)；base=`closing_balance??credit_amount`；payloadKey receipt_check_ratio/shipment_check_ratio。
- 命名方法别名：`getPostPaymentRatio(c)=core.getRatio(c,'postPayment')`、`getReconcileRatio(c)=core.getRatio(c,'reconcile')`；metrics receipt→postPayment、shipment→reconcile。
- 构造 `(wpId,projectId)` positional 保留；导出 `BLOCK_TITLES_K06`、`getSumFieldsK06` 原样保留。
- 适配器在末尾调 `loadAll()`（保留原 init 时机）。

### 4.5 L05（命名比例 + balanceSummary + 独有导出 + 空基数=0）
- config `emptyBase:'zero'`；注入 useL0FormulaEngine（calcBlockTotal/calcRepaymentRatio）；ratios repayment(b1.repayment_principal??voucher_amount)/mortgage(b4.mortgage_amount??voucher_amount)；base=`closing_balance`。
- **注意 L05 两比例算法微异**：`getRepaymentRatio` 用 `calcRepaymentRatio`，`getMortgageRatio` 用纯 `(mortgageAmt/balance)*100` 且 `balance>0` 才算否则 0。→ ratios 支持 per-rule `calcRatio` 覆盖（repayment 用 calcRepaymentRatio，mortgage 用默认），保证逐字等价。
- 命名别名 `getRepaymentRatio/getMortgageRatio`；导出 `getBlockRows/getClosingBalance`（适配器直接暴露 core 内部工具或本地实现）；`balanceSummary`(含 currentLoan + avg 比例，旁挂)。

## 5. 边界处置汇总（Requirement 3）

| Extra_Capability | 处置 | 理由 |
|---|---|---|
| Shared_Core（CRUD/合计/完成度/异常/metrics/init 骨架） | **进工厂** | 八套逐字相同 |
| `_format`/默认 balance/getSumFields/比例规则/metrics 映射 | **进 AltConfig** | 纯数据差异 |
| FormulaEngine（calcTotal/calcRatio/parseNum） | **AltConfig 注入** | 保证与各套逐字等价（引擎实现不改） |
| 命名比例方法（K06/L05） | **适配器别名**（over core.getRatio） | 保持对外方法名不变（Req 1.2） |
| 构造签名变体（4 种） | **适配器各自保留** | 68 caller 零改动 |
| K06 http loadAll + per-block persistAll | **适配器保留原实现，不传 htmlData 给工厂** | IO 行为逐字不能变（Req 1） |
| importFromSummary（H05/K05/K06/L05） | **适配器保留** | 依赖 wpId+per-cycle 端点+item_name |
| balanceSummary（K05/L05）/getReconcileDiff/getBlockRows/getClosingBalance/BLOCK_TITLES | **适配器保留/暴露** | 独有导出，非共性 |

## Correctness Properties

正确性属性（PBT / 测试守卫），由各套 Characterization_Test + 工厂通用单测承载：

### Property 1: format 恒等
∀ 配置，`buildPayload()._format === config.format`。
**Validates: Requirements 1.4**

### Property 2: 比例等价
∀ company 输入，工厂 `getRatio(c,key)` 与收敛前该套 `getCheckRatio/命名方法` 逐字相同（含 null/0 边界、precise 精度、字段回退优先级）。
**Validates: Requirements 1.5, 2.2**

### Property 3: 区块合计
`getBlockTotal(c,b)[f] === precise(calcTotal(rows.map(parseNum f)))` 对每个 sumField f。
**Validates: Requirements 2.1, 2.6**

### Property 4: 完成度
`getCompletionStatus.completed === 4 块中非空块数`；rate=round(completed/4*100)。
**Validates: Requirements 1.1, 2.6**

### Property 5: 异常检测
`hasAbnormal(c) ⟺ 任一块任一行 is_abnormal==='是'`。
**Validates: Requirements 1.1, 2.6**

### Property 6: CRUD 不变式
addCompany 后 seq=max+1 且 isDirty=true；importCompanies 按 confirm_index 去重且 seq 续接；deleteCompany 后 selectedCompanyId 回退首个。
**Validates: Requirements 1.1, 2.6**

### Property 7: metrics 聚合
total=公司数；completed=完全完成公司数；abnormal=有异常公司数；ratio_distribution 用 metricRatioKeys 映射的 getRatio。
**Validates: Requirements 1.1, 2.4**

### Property 8: init 格式门
仅当 `data._format===config.format` 时载入 companies，否则空（K06 除外——保留其 http loadAll 语义）。
**Validates: Requirements 1.6, 2.1**

### Property 9: payload 比例固化
buildPayload 每公司 balance 写入 `ratio.payloadKey = getRatio(c, ratio.key)`，键名与收敛前逐字一致。
**Validates: Requirements 1.3, 2.2**

### Property 10: emptyBase 语义
base 无效时，`emptyBase:'null'` 组返回 null、`'zero'`（L05）返回 0。
**Validates: Requirements 2.3**

这些属性由各套已有/新增的 Characterization_Test 承载；工厂本身另加一份通用工厂单测（用最小 fake config 验 P1/P3/P4/P5/P6/P7/P8/P9/P10）。

## Testing Strategy

### 7. 迁移策略（Requirement 5）与前置门（Requirement 4）

**前置门**：八套 Characterization_Test 全部就位（D05/D06/F05/F06/H05 已有；**K05/K06/L05 待补**，需覆盖含 balanceSummary/命名比例/K06 IO 的行为）→ 才启动任何收敛。

**顺序**（每套独立提交、测试即时全绿、失败即停不放宽断言）：
1. 建工厂 `createAlternativeConfirmationData` + 通用工厂单测。
2. D05 试点（最简，已有测试）→ 全绿。
3. D06 → F05 → F06（无附加能力组）。
4. H05（FormulaEngine 注入 + loadAll/persistAll/importFromSummary 旁挂）。
5. K05（+balanceSummary/getReconcileDiff）。
6. L05（命名比例 + emptyBase:'zero' + per-rule calcRatio + 独有导出）。
7. K06（异质最大：http load/persist 旁挂 + 命名比例 + positional 构造）——放最后，风险最高。

**回退**：任一套失败保持其原实现（不标"已收敛"），已绿套不回退；整体完成以 §8 全绿为准。

## 8. 验证与文档（Requirement 6）

- 全部 confirmation vitest（八套 Characterization + 工厂单测 + coordination + 其它）全绿。
- `get_diagnostics` 工厂 + 八套适配器 + 改动测试文件无错误。
- Vite 可 transform 八套 + 68 caller（无 import 解析失败/命名导出缺失）——收敛后跑一次全树 transform 冒烟（前端崩溃类 bug 只 Vite 暴露，见 memory 铁律）。
- 本 design §2 差异矩阵即"八套×配置项"单一参考文档。
- 结果：八套 Alt_Composable 各自文件行数显著下降（每套 ≈ config + 别名 + 旁挂）。

## Error Handling

- **格式不匹配**：工厂 `_initFromHtmlData` 仅当 `data._format===config.format` 载入，否则置空——与各套现状一致（K06 例外，保留其 http loadAll 的 catch→置空语义）。
- **基数为 0/缺失**：按 `config.emptyBase` 返回 null（D~K）或 0（L05），不抛异常。
- **importFromSummary http 失败**：适配器保留各套原有的 `try/finally`（loading 复位）与失败返回 0 / catch 置空语义，不改。
- **K06 persistAll 逐块 POST 失败**：保留原 `.catch(() => {})` 静默语义（逐字不变）。
- **parseNum NaN**：注入的 parseNum 与各套一致（`Number()` 后 NaN→0 或 `!isNaN` 过滤），不改数值语义。
- 工厂**不新增**任何错误处理路径（零行为变更）；所有异常处置沿用各套现状。

## 9. 风险与缓解

- **R1 命名比例/构造签名不统一** → 适配器保留对外签名，工厂只提供通用 `getRatio`；契约由 Req 1.2 + Characterization 守卫。
- **R2 K06 的 http IO 与内存模式冲突** → 不让工厂接管 K06 的 load/persist，仅接管 CRUD/metrics/buildPayload；K06 loadAll/persistAll 逐字保留。
- **R3 FormulaEngine 与纯算术数值差异** → config 注入各套原用的 calc 函数（不改引擎），P2/P3 守卫等价。
- **R4 L05 mortgage 与 repayment 算法不同源** → RatioRule 支持 per-rule calcRatio 覆盖。
- **R5 收敛引入前端崩溃（命名导出/ref 解包）** → §8 Vite 全树 transform 冒烟 + 每套迁移后 get_diagnostics。
- **R6 68 caller 隐性依赖某内部行为** → 逐套迁移 + 每套 Characterization 全绿后才下一套；失败即停。
