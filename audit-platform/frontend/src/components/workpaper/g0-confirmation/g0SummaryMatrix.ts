/**
 * g0SummaryMatrix.ts — G0-1 下区「一、函证情况」品种矩阵（8 品种 × 8 指标）
 *
 * spec: g0-confirmation-source-alignment，Task 4/5/6（Requirement 3.2~3.5 / 4.1~4.5）
 *
 * ─── 源模板事实（openpyxl 直读，后端 `test_g0_source_template_facts.py` 已固化）──
 * `函证结果汇总表G0-1` 下区 `C19 一、函证情况`：
 *   品种列头 `E20:H20` = 交易性金融资产 / 长期股权投资 / 债权投资 / `……`（可扩位）
 *   指标行 `C21:C28`（8 行）与公式：
 *     R21 本期（期末）账面金额         —— 手填，无公式
 *     R22 抽取样本的发函金额           = SUMIF($E$8:$E$17, 品种, $F$8:$F$17)
 *     R23 发函金额占账面金额的比例(%)   = IF(ISERROR(R22/R21), 0, R22/R21)
 *     R24 回函确认金额                 = SUMIF($E$8:$E$17, 品种, U8:U17)
 *     R25 回函可确认金额占发函金额比例  = IF(ISERROR(R24/R22), 0, R24/R22)
 *     R26 回函可确认金额占账面金额比例  = IF(ISERROR(R24/R21), 0, R24/R21)
 *     R27 替代测试确认金额             = SUMIF($E$8:$E$17, 品种, $Y$8:$Y$17)
 *     R28 回函和替代确认金额占账面比例  = (R27+R24)/R21
 *   上区列语义：E=账户/交易（品种维度）· F=账面期末余额 · U=可确认金额 · Y=替代后可确认金额
 *
 * ─── 与 `confirmation/composables/f0SummaryAggregation.ts` 的关系（裁决门 D = D-2）──
 * 用户裁决「各自实现后收敛」→ 本模块是**独立副本**，`f0SummaryAggregation.ts` 与
 * `e0SummaryMatrix.ts` 一行不改。逐条登记同源关系与差异点：
 *
 * | 维度         | F0 (`f0SummaryAggregation`)        | G0（本模块）                          |
 * |--------------|-----------------------------------|---------------------------------------|
 * | 指标         | 8 条，同构                        | 8 条，`label` 与 F0 **逐字相同**      |
 * | 公式         | SUMIF(E,品种,F/U/Y) + 3 比例 + 末行| **完全同构**（源模板两表同源）        |
 * | 品种         | 4 个（预付账款/应付票据/应付账款/本期采购）| 8 个投资品种                   |
 * | 账面取数     | F1/F3/F4 的 `tb_amount`           | G1/G4/G5/G6/G7/G8/G9/G10 的 `tb_amount`|
 * | 分母 0/缺失  | 返 `null`                          | 返 `null`（同）                        |
 * | 品种可见性   | 固定 4 列                          | **动态**（裁决门 A「有就显示没有隐藏」）|
 *
 * 同源性由 `__tests__/g0SummaryMatrix.spec.ts` 的 Property 7 机器保证：对同一输入，
 * 两侧 8 个指标的 `label`/`kind`/`editable`/`value` 逐字节相同 → 收敛前不会各自漂移。
 *
 * 🔴 收敛锚点：收敛 spec 靠 grep `CONVERGENCE_TARGET` 定位全部副本，勿删勿改名。
 */

import type { ConfirmationRow } from '../confirmation/confirmationTypes'

/** 收敛锚点（裁决门 D = D-2）—— 矩阵类副本的统一标识 */
export const CONVERGENCE_TARGET = 'confirmation-summary-matrix-convergence'

// ─── 指标（源 C21:C28 逐字） ──────────────────────────────────────────────────

export type G0MetricKey =
  | 'book_amount'
  | 'send_amount'
  | 'send_ratio'
  | 'reply_confirmed'
  | 'reply_over_send'
  | 'reply_over_book'
  | 'alt_confirmed'
  | 'reply_alt_over_book'

export interface G0MetricDef {
  key: G0MetricKey
  /** 源模板逐字标签（去掉行尾冒号；源单元格含「：」） */
  label: string
  kind: 'amount' | 'ratio'
  /** true = 可手填（仅账面金额行；源模板该行无公式） */
  editable: boolean
  /** 金额类：聚合的 grid 字段 */
  sum?: 'amount' | 'confirmed_amount' | 'alt_confirmed'
  /** 比例类：分子（可多项相加）/ 分母 */
  ratio?: { num: G0MetricKey[]; den: G0MetricKey }
  /** 源锚点 */
  source_ref: string
}

/**
 * 8 个指标。`label` 与 `F0_MATRIX_LABELS` **逐字相同**（同源守卫依赖此点）。
 */
export const G0_MATRIX_METRICS: readonly G0MetricDef[] = Object.freeze([
  { key: 'book_amount', label: '本期（期末）账面金额', kind: 'amount', editable: true, source_ref: 'G0-1!C21' },
  { key: 'send_amount', label: '抽取样本的发函金额', kind: 'amount', editable: false, sum: 'amount', source_ref: 'G0-1!C22' },
  { key: 'send_ratio', label: '发函金额占账面金额的比例(%)', kind: 'ratio', editable: false, ratio: { num: ['send_amount'], den: 'book_amount' }, source_ref: 'G0-1!C23' },
  { key: 'reply_confirmed', label: '回函确认金额', kind: 'amount', editable: false, sum: 'confirmed_amount', source_ref: 'G0-1!C24' },
  { key: 'reply_over_send', label: '回函可确认金额占发函金额的比例(%)', kind: 'ratio', editable: false, ratio: { num: ['reply_confirmed'], den: 'send_amount' }, source_ref: 'G0-1!C25' },
  { key: 'reply_over_book', label: '回函可确认金额占账面金额的比例(%)', kind: 'ratio', editable: false, ratio: { num: ['reply_confirmed'], den: 'book_amount' }, source_ref: 'G0-1!C26' },
  { key: 'alt_confirmed', label: '替代测试确认金额', kind: 'amount', editable: false, sum: 'alt_confirmed', source_ref: 'G0-1!C27' },
  { key: 'reply_alt_over_book', label: '回函和替代确认金额占账面金额的比例(%)', kind: 'ratio', editable: false, ratio: { num: ['alt_confirmed', 'reply_confirmed'], den: 'book_amount' }, source_ref: 'G0-1!C28' },
])

/** 指标 label 序列（供同源守卫与渲染表头） */
export const G0_MATRIX_LABELS: readonly string[] = Object.freeze(G0_MATRIX_METRICS.map((m) => m.label))

// ─── 品种（候选全集 8 个；裁决门 A） ─────────────────────────────────────────

export interface G0CategoryDef {
  /** 与 grid 上区 `account_type`（源 E 列「账户/交易」）取值逐字相同 */
  name: string
  /**
   * 账面金额取数口径。
   * - `rowCode`：`report_config` 报表行（**权威**，postgres 实测四准则一致）
   * - `wpCode`：账面金额来源底稿（读其 render-config 的 `project_context.tb_amount`）
   * - `hint`：溯源 tooltip 文案。🔴 科目码**只**出现在这里，不进任何请求参数/事件载荷
   */
  book: { rowCode: string; wpCode: string; hint: string }
  source_ref: string
}

/**
 * 候选全集 8 个投资品种。
 *
 * 前 3 个取自源模板 `G0-1!E20:H20`（第 4 格是 `……` 可扩位）；
 * 后 5 个取自 `函证程序表G0A!B7`（程序 1 明列的函证品种全集）。
 * 裁决门 A：「列 8 个品种 + 预留可扩展 + 有就显示没有隐藏」。
 */
export const G0_MATRIX_CATEGORIES: readonly G0CategoryDef[] = Object.freeze([
  { name: '交易性金融资产', book: { rowCode: 'BS-003', wpCode: 'G1', hint: "报表行 BS-003 = TB('1101','期末余额') — G1 审定表" }, source_ref: 'G0-1!E20' },
  { name: '长期股权投资', book: { rowCode: 'BS-024', wpCode: 'G7', hint: "报表行 BS-024 = TB('1511','期末余额') — G7 审定表" }, source_ref: 'G0-1!F20' },
  { name: '债权投资', book: { rowCode: 'BS-021', wpCode: 'G4', hint: "报表行 BS-021 = TB('1504','期末余额') — G4 审定表" }, source_ref: 'G0-1!G20' },
  { name: '长期应收款', book: { rowCode: 'BS-023', wpCode: 'G5', hint: "报表行 BS-023 = TB('1531','期末余额') — G5 审定表" }, source_ref: 'G0A!B7' },
  { name: '其他债权投资', book: { rowCode: 'BS-022', wpCode: 'G6', hint: "报表行 BS-022 = TB('1506','期末余额') — G6 审定表" }, source_ref: 'G0A!B7' },
  { name: '其他权益工具投资', book: { rowCode: 'BS-025', wpCode: 'G8', hint: "报表行 BS-025 = TB('1507','期末余额') — G8 审定表" }, source_ref: 'G0A!B7' },
  { name: '其他非流动金融资产', book: { rowCode: 'BS-026', wpCode: 'G9', hint: "报表行 BS-026 = TB('1519','期末余额') — G9 审定表" }, source_ref: 'G0A!B7' },
  { name: '交易性金融负债', book: { rowCode: 'BS-042', wpCode: 'G10', hint: "报表行 BS-042 = TB('2101','期末余额') — G10 审定表" }, source_ref: 'G0A!B7' },
])

/** 候选品种名（渲染顺序 = 源模板顺序 + G0A 顺序） */
export const G0_CATEGORY_NAMES: readonly string[] = Object.freeze(G0_MATRIX_CATEGORIES.map((c) => c.name))

/**
 * 新增自定义品种的前提提示（源 `H20` 的 `……` 可扩位）。
 * 名称必须与 grid 上区「账户/交易」列取值一致，否则该品种三个金额指标恒为 0。
 */
export const G0_CUSTOM_CATEGORY_HINT =
  '新增品种的名称必须与上区「账户/交易」列的取值完全一致，否则该品种的发函/回函/替代金额无法聚合（将显示 0）。'

// ─── 计算 ────────────────────────────────────────────────────────────────────

export interface G0MatrixCell {
  category: string
  metric: G0MetricKey
  label: string
  /** null = 分母缺失或为 0 → 渲染「-」；绝不产出 NaN/Infinity */
  value: number | null
  kind: 'amount' | 'ratio'
  editable: boolean
  sourceHint?: string
  isManual?: boolean
}

export interface G0MatrixInput {
  /** G0-1 上区 grid 明细行 */
  rows: readonly ConfirmationRow[]
  /** 各品种账面金额（相邻 G 循环 `project_context.tb_amount`）；缺该品种 = undefined ≠ 0 */
  bookAmounts?: Readonly<Record<string, number | undefined>>
  /** 手工覆盖（key = `${category}::${metricKey}`），只对 `editable` 指标生效 */
  manualOverrides?: Readonly<Record<string, number>>
  /** 品种全集（默认候选 8 个；传入可含自定义品种） */
  categories?: readonly string[]
}

/** 安全除法：分母缺失或为 0 → null；结果非有限 → null */
export function safeRatio(numerator?: number | null, denominator?: number | null): number | null {
  if (numerator == null || denominator == null) return null
  if (denominator === 0) return null
  const r = numerator / denominator
  if (!Number.isFinite(r)) return null
  return r
}

/** 按品种（grid `account_type`，源 E 列）求和指定金额字段 —— 对齐源模板 SUMIF */
export function sumByCategory(
  rows: readonly ConfirmationRow[],
  category: string,
  field: 'amount' | 'confirmed_amount' | 'alt_confirmed',
): number {
  let total = 0
  for (const row of rows) {
    if (row.account_type !== category) continue
    const v = (row as unknown as Record<string, unknown>)[field]
    if (typeof v === 'number' && Number.isFinite(v)) total += v
  }
  return round2(total)
}

function round2(n: number): number {
  return Math.round(n * 100) / 100
}

function manualKey(category: string, metric: G0MetricKey): string {
  return `${category}::${metric}`
}

/**
 * 构建品种 × 8 指标矩阵。返回 `result[catIdx][metricIdx]`（品种顺序 = 入参 categories 顺序）。
 *
 * 计算口径逐条对齐源模板（见文件头公式表）：
 * - 金额类 = `SUMIF(E, 品种, F|U|Y)`
 * - 比例类 = 分子/分母，分母缺失或 0 → `null`
 * - 手工值只对 `editable` 指标生效（账面金额行），且优先于自动取数
 */
export function buildG0SummaryMatrix(input: G0MatrixInput): G0MatrixCell[][] {
  const { rows, bookAmounts, manualOverrides } = input
  const categories = input.categories ?? G0_CATEGORY_NAMES
  const result: G0MatrixCell[][] = []

  for (const category of categories) {
    // 先算出全部指标的原始值，供比例类按 key 引用
    const values: Partial<Record<G0MetricKey, number | null>> = {}

    for (const def of G0_MATRIX_METRICS) {
      if (def.key === 'book_amount') {
        const manual = manualOverrides?.[manualKey(category, def.key)]
        values[def.key] = manual ?? bookAmounts?.[category] ?? null
        continue
      }
      if (def.sum) {
        values[def.key] = sumByCategory(rows, category, def.sum)
        continue
      }
      if (def.ratio) {
        const nums = def.ratio.num.map((k) => values[k])
        // 任一分子缺失 → null（不把 undefined 当 0）
        const num = nums.some((v) => v == null) ? null : nums.reduce((a, b) => (a as number) + (b as number), 0)
        values[def.key] = safeRatio(num as number | null, values[def.ratio.den])
      }
    }

    const cells: G0MatrixCell[] = G0_MATRIX_METRICS.map((def) => {
      const isManual = def.editable && manualOverrides?.[manualKey(category, def.key)] != null
      return {
        category,
        metric: def.key,
        label: def.label,
        value: values[def.key] ?? null,
        kind: def.kind,
        editable: def.editable,
        sourceHint: buildSourceHint(def, category, isManual),
        isManual,
      }
    })
    result.push(cells)
  }

  return result
}

function buildSourceHint(def: G0MetricDef, category: string, isManual: boolean): string | undefined {
  if (def.key === 'book_amount') {
    if (isManual) return '手工填写（优先于自动取数）'
    const cat = G0_MATRIX_CATEGORIES.find((c) => c.name === category)
    return cat ? cat.book.hint : '本项目无此科目或未编制对应审定表 —— 请手工填写'
  }
  if (def.sum === 'amount') return `源模板 SUMIF(E,${category},F) — Σ 上区[账户/交易=${category}].账面期末余额`
  if (def.sum === 'confirmed_amount') return `源模板 SUMIF(E,${category},U) — Σ 上区[账户/交易=${category}].可确认金额`
  if (def.sum === 'alt_confirmed') return `源模板 SUMIF(E,${category},Y) — Σ 上区[账户/交易=${category}].替代后可确认金额`
  return undefined
}

// ─── 品种可见性（裁决门 A「有就显示没有隐藏」） ───────────────────────────────

export interface G0VisibilityInput {
  rows: readonly ConfirmationRow[]
  bookAmounts?: Readonly<Record<string, number | undefined>>
  manualOverrides?: Readonly<Record<string, number>>
  /** 品种全集（默认候选 8 个） */
  categories?: readonly string[]
  /** 「显示全部品种」开关（默认 false） */
  showAll?: boolean
}

/**
 * 某品种是否「有内容」—— 三条任一成立（Requirement 3.2.2）：
 * ① grid 上区存在该品种的行 ② 取到账面金额 ③ 有手工值
 */
export function hasG0CategoryContent(category: string, input: G0VisibilityInput): boolean {
  if (input.rows.some((r) => r.account_type === category)) return true
  const book = input.bookAmounts?.[category]
  if (typeof book === 'number' && Number.isFinite(book)) return true
  if (input.manualOverrides) {
    const prefix = `${category}::`
    for (const k of Object.keys(input.manualOverrides)) {
      if (k.startsWith(prefix)) return true
    }
  }
  return false
}

/**
 * 可见品种列表。
 *
 * 🔴 两条防死锁规则（Requirement 3.2.3 / 3.2.4）：
 * - `showAll=true` → 返回全部候选
 * - **一个品种都没有内容 → 返回全部候选**（否则空底稿是空白区，且审计师无法为任何
 *   品种录入账面金额来让它「有内容」，形成永久死锁）
 */
export function visibleG0Categories(input: G0VisibilityInput): string[] {
  const all = [...(input.categories ?? G0_CATEGORY_NAMES)]
  if (input.showAll) return all
  const visible = all.filter((c) => hasG0CategoryContent(c, input))
  return visible.length > 0 ? visible : all
}

// ─── 账面金额取数 ────────────────────────────────────────────────────────────

/** 品种 → 账面金额来源底稿 wp_code（供调用方批量拉 render-config） */
export const G0_BOOK_AMOUNT_WP_CODES: readonly string[] = Object.freeze(
  Array.from(new Set(G0_MATRIX_CATEGORIES.map((c) => c.book.wpCode))),
)

/**
 * 从相邻 G 循环的 render-config `html_data` 提取账面金额。
 *
 * 设计约束：
 * - 缺失返回 `undefined`（**非 0**）—— 「本项目无此科目」与「余额为 0」是两种状态
 * - 只读 `project_context.tb_amount`（trial_balance 期末），不臆造
 */
export function fetchG0BookAmounts(
  htmlDataByWpCode: Readonly<Record<string, { project_context?: { tb_amount?: unknown } } | undefined>>,
): Record<string, number> {
  const out: Record<string, number> = {}
  for (const cat of G0_MATRIX_CATEGORIES) {
    const amount = htmlDataByWpCode[cat.book.wpCode]?.project_context?.tb_amount
    if (typeof amount === 'number' && Number.isFinite(amount)) {
      out[cat.name] = amount
    }
  }
  return out
}

/** 从矩阵中提取某指标行（按品种列顺序），便于模板按行渲染 */
export function getG0MatrixRow(matrix: G0MatrixCell[][], metric: G0MetricKey): G0MatrixCell[] {
  return matrix.map((cells) => cells.find((c) => c.metric === metric)!).filter(Boolean)
}
