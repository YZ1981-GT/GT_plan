/**
 * l0SummaryMatrix.ts — L0-1 下区「一、函证情况」品种矩阵（2 品种 × 8 指标）
 *
 * spec: l0-confirmation-source-alignment，Task 9（Requirements 3.1 / 3.2）
 *
 * ─── 源模板事实（openpyxl 直读，后端 `test_l0_source_template_facts.py` 已固化）──
 * `函证结果汇总表L0-1` 下区 `C28 一、函证情况`：
 *   品种列头 `E29 长期应付款` / `F29 应付债券` —— **恰 2 个，无 `……` 可扩位**
 *   （与 G0 的「8 品种 + 可扩 + 有就显示没有隐藏」不同，L0 固定 2 列）
 *   标签列头 `C29 项目`
 *   指标行 `C30:C37`（8 行，含行尾冒号）与公式：
 *     R30 本期（期末）账面金额          —— **手填，无公式**（矩阵唯一录入位）
 *     R31 抽取样本的发函金额            = SUMIF(E8:E27, 品种, F8:F27)
 *     R32 发函金额占账面金额的比例(%)    = IF(ISERROR(R31/R30), 0, R31/R30)
 *     R33 回函确认金额                  = SUMIF(E8:E27, 品种, U8:U27)
 *     R34 回函可确认金额占发函金额比例   = IF(ISERROR(R33/R31), 0, R33/R31)
 *     R35 回函可确认金额占账面金额比例   = IF(ISERROR(R33/R30), 0, R33/R30)
 *     R36 替代测试确认金额              = SUMIF(E8:E27, 品种, Y8:Y27)
 *     R37 回函和替代确认金额占账面比例   = (R36+R33)/R30
 *   上区列语义：E=账户/交易（品种维度）· F=金额 · U=可确认金额 · Y=替代后可确认金额
 *   上区数据行 8~27（20 行）
 *
 * 🔴 **三条 SUMIF 无「相符」过滤** —— 源模板 R33 直取 `U` 列（可确认金额），
 * 业务规则已在 `useConfirmationData.computeConfirmedAmount` 的派生里
 * （相符→amount / 不符→reply_amount / 消极式未回函→视同相符）。
 * 再叠一层 `match_status === '相符'` 是**双重口径**（F0 那轮已定论）。
 *
 * ─── 与 `confirmation/composables/f0SummaryAggregation.ts` 的关系（裁决门 D = D-2）──
 * 用户裁决「各自实现后收敛」→ 本模块是**独立副本**，`f0SummaryAggregation.ts` /
 * `e0SummaryMatrix.ts` / `g0SummaryMatrix.ts` / `h0SummaryMatrix.ts` 一行不改。
 *
 * | 维度         | F0 (`f0SummaryAggregation`)         | L0（本模块）                          |
 * |--------------|-------------------------------------|---------------------------------------|
 * | 指标         | 8 条                                | 8 条，`label`/`kind`/`editable` 逐字同 |
 * | 公式         | SUMIF(E,品种,F/U/Y) + 3 比例 + 末行 | **完全同构**（源模板两表同源）        |
 * | 品种         | 4 个（预付账款/应付票据/应付账款/本期采购）| **2 个**（长期应付款/应付债券）  |
 * | 账面取数     | F1/F3/F4 的 `tb_amount`（前端拉）   | **后端注入** `project_context.l0_book_amounts` |
 * | 分母 0/缺失  | 返 `null`                            | 返 **`0`**（忠实源模板 `ISERROR`→0）  |
 * | 品种可见性   | 固定 4 列                            | 固定 2 列（源模板无可扩位）           |
 * | metric key   | label-as-key（无独立 key 字段）      | **key + label 两字段**（收敛目标形态） |
 *
 * 同源性由 `__tests__/l0SummaryMatrix.spec.ts` 的 Property 9 机器保证：对同一输入，
 * 两侧 8 个指标的 `label`/`kind`/`editable`/`value` 逐字节相同 → 收敛前不会各自漂移。
 *
 * 🔴 **比例列分母为 0/非有限时返 `0` 不返 `null`** —— 源模板三个比例列是
 * `IF(ISERROR(...), 0, ...)`，忠实实现即返 0。这与 F0/G0 的 `null` 口径**有意不同**
 * （那两处源模板同形，属既有实现选择差异），收敛 spec 需先吸收该差异。
 *
 * 🔴 收敛锚点：收敛 spec 靠 grep `CONVERGENCE_TARGET` 定位全部副本，勿删勿改名。
 */

import type { ConfirmationRow } from '../confirmationTypes'

/** 收敛锚点（裁决门 D = D-2）—— 矩阵类副本的统一标识 */
export const CONVERGENCE_TARGET = 'confirmation-summary-matrix-convergence'

// ─── 指标（源 C30:C37 逐字，去行尾冒号） ────────────────────────────────────

/**
 * 🔴 key 逐字沿用 `g0SummaryMatrix.ts` 的命名 —— 收敛时无需再改名，
 * 同源守卫也能直接按 key 对齐比对。
 */
export type L0MetricKey =
  | 'book_amount'
  | 'send_amount'
  | 'send_ratio'
  | 'reply_confirmed'
  | 'reply_over_send'
  | 'reply_over_book'
  | 'alt_confirmed'
  | 'reply_alt_over_book'

export interface L0MetricDef {
  key: L0MetricKey
  /** 源模板逐字标签（去掉行尾冒号；源单元格含「：」） */
  label: string
  kind: 'amount' | 'ratio'
  /** true = 可手填（仅账面金额行；源模板该行无公式） */
  editable: boolean
  /** 金额类：聚合的 grid 字段（对应源模板 SUMIF 的 sum_range） */
  sum?: 'amount' | 'confirmed_amount' | 'alt_confirmed'
  /** 比例类：分子（可多项相加）/ 分母 */
  ratio?: { num: L0MetricKey[]; den: L0MetricKey }
  /** 源锚点 */
  source_ref: string
}

/** 8 个指标。`label`/`kind`/`editable` 与 F0/G0 **逐字相同**（同源守卫依赖此点）。 */
export const L0_MATRIX_METRICS: readonly L0MetricDef[] = Object.freeze([
  { key: 'book_amount', label: '本期（期末）账面金额', kind: 'amount', editable: true, source_ref: 'L0-1!C30' },
  { key: 'send_amount', label: '抽取样本的发函金额', kind: 'amount', editable: false, sum: 'amount', source_ref: 'L0-1!C31' },
  { key: 'send_ratio', label: '发函金额占账面金额的比例(%)', kind: 'ratio', editable: false, ratio: { num: ['send_amount'], den: 'book_amount' }, source_ref: 'L0-1!C32' },
  { key: 'reply_confirmed', label: '回函确认金额', kind: 'amount', editable: false, sum: 'confirmed_amount', source_ref: 'L0-1!C33' },
  { key: 'reply_over_send', label: '回函可确认金额占发函金额的比例(%)', kind: 'ratio', editable: false, ratio: { num: ['reply_confirmed'], den: 'send_amount' }, source_ref: 'L0-1!C34' },
  { key: 'reply_over_book', label: '回函可确认金额占账面金额的比例(%)', kind: 'ratio', editable: false, ratio: { num: ['reply_confirmed'], den: 'book_amount' }, source_ref: 'L0-1!C35' },
  { key: 'alt_confirmed', label: '替代测试确认金额', kind: 'amount', editable: false, sum: 'alt_confirmed', source_ref: 'L0-1!C36' },
  { key: 'reply_alt_over_book', label: '回函和替代确认金额占账面金额的比例(%)', kind: 'ratio', editable: false, ratio: { num: ['alt_confirmed', 'reply_confirmed'], den: 'book_amount' }, source_ref: 'L0-1!C37' },
])

/** 指标 label 序列（供同源守卫与渲染表头） */
export const L0_MATRIX_LABELS: readonly string[] = Object.freeze(
  L0_MATRIX_METRICS.map((m) => m.label),
)

/** 标签列表头（源 `C29`） */
export const L0_MATRIX_LABEL_HEADER = '项目'

// ─── 品种（源 E29/F29，固定 2 个） ─────────────────────────────────────────

export interface L0CategoryDef {
  /** 与 grid 上区 `account_type`（源 E 列「账户/交易」）取值逐字相同 —— 同时是 SUMIF 的 criteria */
  name: string
  /**
   * 账面金额溯源口径。
   * - `rowCode`：`report_config` 报表行（**权威**，postgres 实测四准则一致）
   * - `wpCode`：数据来源循环（仅供溯源展示）
   * - `hint`：溯源 tooltip 文案。🔴 科目码**只**出现在这里，不进任何请求参数/事件载荷
   */
  book: { rowCode: string; wpCode: string; hint: string }
  source_ref: string
}

/**
 * 恰 2 个品种（源 `L0-1!E29`/`F29`）。
 *
 * 🔴 **不做动态可见性** —— 源模板该行**无 `……` 可扩位**（后端守卫
 * `test_l0_source_template_facts.TestSummaryLowerZone.test_matrix_has_exactly_two_categories_no_ellipsis`
 * 已固化 `G29` 为空）。G0 的「有就显示没有隐藏 + 显示全部品种开关」是为它的 8 品种
 * 候选全集设计的，L0 照搬会凭空引入可扩语义。
 *
 * 🔴 品种名是**源模板字面**，改它等于改 SUMIF 的 criteria 与手工覆盖键的品种段
 * （`L0-1-matrix-{品种}-book_amount`），会让既有录入值失联。
 */
export const L0_MATRIX_CATEGORIES: readonly L0CategoryDef[] = Object.freeze([
  {
    name: '长期应付款',
    book: {
      rowCode: 'BS-064',
      wpCode: 'L5',
      hint: "报表行 BS-064 = TB('2701','期末余额')（四准则一致）；未确认融资费用 2702 是独立一级科目，该口径不扣减",
    },
    source_ref: 'L0-1!E29',
  },
  {
    name: '应付债券',
    book: {
      rowCode: 'BS-062',
      wpCode: 'L4',
      hint: "报表行 BS-062 = TB('2502','期末余额')（四准则一致）；客户常设 面值/利息调整/应计利息 子科目，按方向带符号聚合",
    },
    source_ref: 'L0-1!F29',
  },
])

/** 品种名序列（供渲染表头与守卫） */
export const L0_MATRIX_CATEGORY_NAMES: readonly string[] = Object.freeze(
  L0_MATRIX_CATEGORIES.map((c) => c.name),
)

// ─── 矩阵单元格 ─────────────────────────────────────────────────────────────

export interface L0MatrixCell {
  /** 稳定 key（**非**中文 label；手工覆盖键的指标段用它） */
  metric: L0MetricKey
  /** 源模板逐字标签 */
  label: string
  kind: 'amount' | 'ratio'
  editable: boolean
  /** `null` = 不可得（账面金额未取数/本项目无此科目）；比例列恒为数值（源模板 ISERROR→0） */
  value: number | null
}

export interface BuildL0MatrixInput {
  /** 上区 grid 行 */
  rows: readonly ConfirmationRow[]
  /**
   * 后端注入的账面金额（`project_context.l0_book_amounts`）。
   *
   * 🔴 三态语义**必须**原样传入，不得 `?? {}` 兜底：
   * - `undefined`（整个键不存在）= 注入未发生 / 取数整体失败 → 「未取数（可手填）」
   * - `null`（键存在值为 null）  = 本项目科目表无该科目 → 「本项目无此科目」
   * - `0`                        = 科目存在且余额为 0
   */
  bookAmounts?: Record<string, number | null> | undefined
  /** 审计师手工覆盖（键见 `l0MatrixDataSources.matrixOverrideItemId`） */
  manualOverrides?: Record<string, number> | undefined
}

/** 数值归一：非有限值（NaN/±Infinity）与空串一律视为 0。 */
function num(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : 0
}

/**
 * 按品种聚合上区某个字段（源模板 `SUMIF(E8:E27, 品种, <字段列>)`）。
 *
 * 🔴 criteria 是 `account_type`（源 E 列「账户/交易」），**不叠相符过滤**。
 */
function sumByCategory(
  rows: readonly ConfirmationRow[],
  category: string,
  field: 'amount' | 'confirmed_amount' | 'alt_confirmed',
): number {
  let total = 0
  for (const r of rows) {
    if (String((r as Record<string, unknown>).account_type ?? '') !== category) continue
    total += num((r as Record<string, unknown>)[field])
  }
  return total
}

/**
 * 比例：源模板 `IF(ISERROR(num/den), 0, num/den)` —— 分母 0 或非有限值返 **0**。
 */
function safeRatio(numerator: number, denominator: number): number {
  if (!Number.isFinite(numerator) || !Number.isFinite(denominator) || denominator === 0) return 0
  const r = numerator / denominator
  return Number.isFinite(r) ? r : 0
}

/**
 * 构建 2 品种 × 8 指标矩阵。
 *
 * 返回外层按**品种**、内层按**指标**（与 `L0_MATRIX_CATEGORIES` /
 * `L0_MATRIX_METRICS` 顺序一致）。
 */
export function buildL0SummaryMatrix(input: BuildL0MatrixInput): L0MatrixCell[][] {
  const rows = input.rows ?? []
  return L0_MATRIX_CATEGORIES.map((cat) => {
    // 先算金额类（比例类要引用它们）
    const values = new Map<L0MetricKey, number | null>()

    // 账面金额：手工覆盖 > 后端注入（三态）
    const overrideKey = `L0-1-matrix-${cat.name}-book_amount`
    const manual = input.manualOverrides?.[overrideKey]
    if (manual !== undefined && Number.isFinite(Number(manual))) {
      values.set('book_amount', Number(manual))
    } else if (input.bookAmounts && cat.name in input.bookAmounts) {
      const raw = input.bookAmounts[cat.name]
      // null = 本项目无此科目 → 保持 null（不塌陷成 0）
      values.set('book_amount', raw === null ? null : num(raw))
    } else {
      // 键不存在 = 未取数 → null（与「本项目无此科目」在 UI 层用 source_codes 区分）
      values.set('book_amount', null)
    }

    for (const m of L0_MATRIX_METRICS) {
      if (m.kind === 'amount' && m.sum) {
        values.set(m.key, sumByCategory(rows, cat.name, m.sum))
      }
    }
    for (const m of L0_MATRIX_METRICS) {
      if (m.kind !== 'ratio' || !m.ratio) continue
      const den = values.get(m.ratio.den)
      const numerator = m.ratio.num.reduce((acc, k) => acc + num(values.get(k)), 0)
      values.set(m.key, safeRatio(numerator, num(den)))
    }

    return L0_MATRIX_METRICS.map<L0MatrixCell>((m) => ({
      metric: m.key,
      label: m.label,
      kind: m.kind,
      editable: m.editable,
      value: values.has(m.key) ? (values.get(m.key) as number | null) : null,
    }))
  })
}

/** 便捷取值：按品种 + 指标 key 取单格。 */
export function pickL0MatrixCell(
  matrix: readonly L0MatrixCell[][],
  category: string,
  metric: L0MetricKey,
): L0MatrixCell | undefined {
  const idx = L0_MATRIX_CATEGORY_NAMES.indexOf(category)
  if (idx < 0) return undefined
  return matrix[idx]?.find((c) => c.metric === metric)
}
