/**
 * k0MatrixSpec.ts — K0-1 下区「一、函证情况」品种矩阵**声明式真源**（2 品种 × 8 指标）
 *
 * spec: k0-confirmation-source-alignment · Task 4（Requirement 4.1~4.6 / 3.2）
 *
 * ─── 源模板事实（openpyxl 直读；后端 `test_k0_source_template_facts.py` 已固化）──
 * `函证结果汇总表K0-1` 下区 `C27 一、函证情况`：
 *   品种列头 `E28 其他应收款` / `F28 其他应付款` —— 🔴 **固定 2 个，无 `……` 可扩位**
 *   （G0 的 `H20` / H0 的 `H29` 才有可扩位，K0 没有 → 不做动态品种）
 *   指标行 `C29:C36`（8 行）与公式：
 *     R29 本期（期末）账面金额         —— **无公式 = 手填**
 *     R30 抽取样本的发函金额           = SUMIF(E7:E26, 品种, F7:F26)
 *     R31 发函金额占账面金额的比例(%)   = IF(ISERROR(R30/R29), 0, R30/R29)
 *     R32 回函确认金额                 = SUMIF(E7:E26, 品种, U7:U26)
 *     R33 回函可确认金额占发函金额比例  = IF(ISERROR(R32/R30), 0, R32/R30)
 *     R34 回函可确认金额占账面金额比例  = IF(ISERROR(R32/R29), 0, R32/R29)
 *     R35 替代测试确认金额             = SUMIF(E7:E26, 品种, Y7:Y26)
 *     R36 回函和替代确认金额占账面比例  = (R35+R32)/R29   ← **无 ISERROR 兜底**
 *   上区列语义：E=账户/交易（品种维度）· F=金额 · U=可确认金额 · Y=替代后可确认金额
 *
 * 🔴 源模板末行没有 ISERROR 兜底 ⇒ **平台侧必须自己保证不产出 NaN/Infinity**
 * （分母缺失或为 0 一律 `null` → 渲染「-」，绝不用 0 冒充，见 Requirement 3.4）。
 *
 * ─── 账面金额取数（`report_config` 只读实证，2026-08-04）────────────────────────
 * | 品种       | row_code | soe_standalone 公式                              | 备注 |
 * |------------|----------|--------------------------------------------------|------|
 * | 其他应收款 | `BS-009` | `TB('1221') − TB('1231-03') + TB('1131')`         | **净额口径**；其余三准则为 `TB('1221')` |
 * | 其他应付款 | `BS-050` | `TB('2241') + TB('2231')`                        | `*_consolidated` 仅 `TB('2241')`；2231 应付利息已并入其他应付款列报 |
 *
 * 🔴🔴 **必须按 row_code 精确匹配，不能按 row_name**：`BS-075` 在 soe 侧 row_name
 * 也是「其他应付款」但 `formula` 为 NULL，而在 listed 侧 row_name 竟是「股本」——
 * 同一 row_code 在不同准则下 row_name 不同，按名匹配必踩（同 K2 的 `BS-014`/`BS-017`）。
 *
 * 🔴 `fallbackAccountCodes` **只作兜底与展示**：运行态一律走 `four_table` 语义定位
 * （按科目名在**本项目**科目表定位 + 叶子聚合），不得让取数改回按硬编码码查询
 * （Requirement 4.5）。科目码只出现在本文件与 tooltip 文案里，**不进任何请求参数
 * 或事件载荷**。
 *
 * ─── 与 F0 / E0 / H0 / G0 三份既有矩阵的关系（裁决门 D = D-2）────────────────────
 * 平台已有**四份**品种矩阵（`e0SummaryMatrix` 6×6 / `f0SummaryAggregation` 4×8 /
 * `h0SummaryMatrix` 动态×8 / `g0SummaryMatrix` 8×8）。H0 落地时已明确范式与理由：
 * **复用 `safeRatio`/`sumByCategory` 两个纯函数、指标与品种常量各自声明**，因为
 * 「一侧源模板改动不应波及另一侧」。K0 沿用同法（Requirement 11.2），
 * **SHALL NOT** 把几份重构成统一内核（重构半径覆盖 E0/F0/H0/G0 四个 spec）。
 *
 * 🔴 收敛锚点：收敛 spec 靠 grep `CONVERGENCE_TARGET` 定位全部副本，勿删勿改名。
 */

/** 收敛锚点（裁决门 D = D-2）—— 矩阵类副本的统一标识 */
export const CONVERGENCE_TARGET = 'confirmation-summary-matrix-convergence'

/** 下区所在 sheet（源模板真实 tab 名，逐字；`审定表K0-1` 在源 xlsx **不存在**） */
export const K0_LOWER_ZONE_SHEET = '函证结果汇总表K0-1'

/** `sourceRef` 前缀（守卫断言 `sourceRef === K0_SOURCE_REF_PREFIX + anchor`，防两字段漂移） */
export const K0_SOURCE_REF_PREFIX = 'K0-1!'

// ─── 品种（固定 2 个） ────────────────────────────────────────────────────────

export type K0CategoryName = '其他应收款' | '其他应付款'

export interface K0CategorySpec {
  /** 品种名 —— 必须与上区 grid 的 `account_type`（源 `E` 列「账户/交易」）取值逐字相同 */
  category: K0CategoryName
  /** 源模板单元格出处（`K0-1!E28` / `K0-1!F28`） */
  sourceRef: string
  /** 裸锚点（守卫用 `sourceRef === prefix + anchor` 交叉校验） */
  anchor: 'E28' | 'F28'
  /**
   * `report_config` 报表行编码 —— 🔴 **按 row_code 精确匹配，不按 row_name**。
   * `BS-050` 才是有公式的其他应付款行；`BS-075` 是同名 NULL 行（listed 侧还叫「股本」）。
   */
  reportRowCode: 'BS-009' | 'BS-050'
  /** 兜底与展示用科目码；运行态走语义定位，**不据此取数**（R4.5） */
  fallbackAccountCodes: readonly string[]
  /** 取数口径说明（溯源 tooltip；科目码只出现在这里） */
  amountHint: string
  /** 提供账面金额的相邻底稿 wp_code（读其 render-config 的 `project_context.tb_amount`） */
  bookAmountFrom: 'K1' | 'K3'
  /** 是否净额口径（含备抵扣减）—— 守卫据此断言 BS-009 必须为 true */
  netOfProvision: boolean
}

export const K0_MATRIX_CATEGORIES: readonly K0CategorySpec[] = Object.freeze([
  Object.freeze({
    category: '其他应收款',
    sourceRef: 'K0-1!E28',
    anchor: 'E28',
    reportRowCode: 'BS-009',
    // 1221 原值 / 1231-03 坏账准备（减项）/ 1131 应收股利（加项）
    fallbackAccountCodes: Object.freeze(['1221', '1231-03', '1131']),
    amountHint:
      "报表行 BS-009（soe_standalone 为净额口径 TB('1221')−TB('1231-03')+TB('1131')；" +
      "其余三准则为 TB('1221')）— K1 审定表",
    bookAmountFrom: 'K1',
    netOfProvision: true,
  }),
  Object.freeze({
    category: '其他应付款',
    sourceRef: 'K0-1!F28',
    anchor: 'F28',
    reportRowCode: 'BS-050',
    // 2241 其他应付款 / 2231 应付利息（财会[2018]15 号起并入其他应付款列报）
    fallbackAccountCodes: Object.freeze(['2241', '2231']),
    amountHint:
      "报表行 BS-050（*_standalone 为 TB('2241')+TB('2231')；*_consolidated 仅 TB('2241')）" +
      '— K3 审定表。⚠ 同名行 BS-075 的 formula 为 NULL，必须按 row_code 匹配',
    bookAmountFrom: 'K3',
    netOfProvision: false,
  }),
]) as readonly K0CategorySpec[]

/** 品种名（渲染顺序 = 源模板 E28→F28） */
export const K0_CATEGORY_NAMES: readonly K0CategoryName[] = Object.freeze(
  K0_MATRIX_CATEGORIES.map((c) => c.category),
) as readonly K0CategoryName[]

/** 品种 → 账面金额来源底稿 wp_code（供调用方批量拉 render-config） */
export const K0_BOOK_AMOUNT_WP_CODES: readonly string[] = Object.freeze(
  Array.from(new Set(K0_MATRIX_CATEGORIES.map((c) => c.bookAmountFrom))),
)

// ─── 指标（源 C29:C36 逐字，去尾冒号） ───────────────────────────────────────

/**
 * 8 个指标标签。与 `f0SummaryAggregation` / `h0SummaryMatrix` / `g0SummaryMatrix`
 * 的同名指标**逐字相同**（四表源模板同源）—— 同源性由守卫机器保证，
 * 使副本在收敛前不会各自漂移。
 */
export const K0_MATRIX_METRIC_LABELS: readonly string[] = Object.freeze([
  '本期（期末）账面金额',
  '抽取样本的发函金额',
  '发函金额占账面金额的比例(%)',
  '回函确认金额',
  '回函可确认金额占发函金额的比例(%)',
  '回函可确认金额占账面金额的比例(%)',
  '替代测试确认金额',
  '回函和替代确认金额占账面金额的比例(%)',
])

/** 指标锚点（源 C29..C36，与 `K0_MATRIX_METRIC_LABELS` 一一对应） */
export const K0_MATRIX_METRIC_ANCHORS: readonly string[] = Object.freeze([
  'C29', 'C30', 'C31', 'C32', 'C33', 'C34', 'C35', 'C36',
])

/** 唯一可手填的指标下标（源 `R29` 无公式 = 手填） */
export const K0_MATRIX_EDITABLE_METRIC_INDEX = 0

/**
 * 品种 × 指标的**手工覆盖键**（也是公式预设的 `cell_ref` 形态）。
 *
 * 沿用 G0 已落地的形态 `K0-1-matrix-{品种}-{指标key}`：
 * 🔴 用**指标 key**（`book_amount`）而不是中文 label 构键 —— 改文案不会让已录入值失联
 * （F0 侧仍是 label-as-key，属待收敛项）。
 */
export function k0MatrixOverrideItemId(category: string, metricKey: string): string {
  return `K0-1-matrix-${category}-${metricKey}`
}

// ─── 便捷索引 ────────────────────────────────────────────────────────────────

export function getK0Category(name: string): K0CategorySpec | undefined {
  return K0_MATRIX_CATEGORIES.find((c) => c.category === name)
}

/** 某品种账面金额的溯源提示（取不到时如实说明，不显示 0） */
export function k0BookAmountHint(name: string): string {
  return getK0Category(name)?.amountHint ?? '本项目无此科目或未编制对应审定表 —— 请手工填写'
}
