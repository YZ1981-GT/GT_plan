/**
 * h0SummaryMatrix.ts — H0-1「一、函证情况」品种矩阵纯函数（动态品种列 × 8 指标）
 *
 * 源模板：`函证结果汇总表H0-1` R28:R37（下区第一块）
 *
 * ─── 公式逐格实证（2026-08-04 openpyxl `data_only=False` 直读） ───
 *
 * 上区列语义（R6 表头）：E=账户/交易 · F=金额或合同条款 · U=可确认金额/条款 ·
 * Y=替代后可确认金额。
 *
 * | 行  | 源模板公式                          | 本模块实现                                     |
 * |-----|-------------------------------------|------------------------------------------------|
 * | R30 | 手填                                | 后端按品种语义定位取数 + 手工覆盖              |
 * | R31 | `SUMIF(E8:E27,E29,F8:F27)`          | `sumByCategory(rows, cat, 'amount')`           |
 * | R32 | `IF(ISERROR(E31/E30),0,E31/E30)`    | `safeRatio(R31, R30)`（缺失返 null 不返 0）    |
 * | R33 | `SUMIF(E8:E27,E29,U8:U27)`          | `sumByCategory(rows, cat, 'confirmed_amount')` |
 * | R34 | `IF(ISERROR(E33/E31),0,E33/E31)`    | `safeRatio(R33, R31)`                          |
 * | R35 | `IF(ISERROR(E33/E30),0,E33/E30)`    | `safeRatio(R33, R30)`                          |
 * | R36 | `SUMIF(E8:E27,E29,Y8:Y27)`          | `sumByCategory(rows, cat, 'alt_confirmed')`    |
 * | R37 | `(E36+E33)/E30`                     | `safeRatio(R33 + R36, R30)`                    |
 *
 * ─── 与 F0 矩阵的关系 ───
 *
 * 8 个指标标签与公式与 `f0SummaryAggregation` **逐字相同** → 复用其
 * `safeRatio` / `sumByCategory` 两个纯函数，但**指标与品种常量各自声明**
 * （一侧源模板改动不应波及另一侧）。
 *
 * ─── 与 F0/E0 矩阵的关键差异：品种列是动态的 ───
 *
 * 源模板 `H29='……'` 是可扩位；且 H0A/H0-1/H0-4/H0-5 的标题都写
 * 「固定资产/工程物资/使用权资产/租赁负债/……」而矩阵只 seed 了 3 列
 * （**源模板自身的遗漏，登记不修**）。按平台铁律「横向展开的表禁写死列数」+
 * 「key 不能用 label 会撞键」→ 默认 seed 3 列（逐字 E29/F29/G29），
 * 其余品种由用户从 `confirmation_account_type` 枚举增列。
 *
 * spec: .kiro/specs/h0-confirmation-source-fidelity-and-linkage/
 *       Requirements 2.2~2.5 / 3.1 / 3.8；Property 3/4/5/6
 */

import type { ConfirmationRow } from './confirmationTypes'
import { safeRatio, sumByCategory } from './composables/f0SummaryAggregation'

// ─── 指标常量（源模板 C30:C37 逐字，去尾冒号） ────────────────────────────────

export const H0_MATRIX_METRIC_LABELS = [
  '本期（期末）账面金额',
  '抽取样本的发函金额',
  '发函金额占账面金额的比例(%)',
  '回函确认金额',
  '回函可确认金额占发函金额的比例(%)',
  '回函可确认金额占账面金额的比例(%)',
  '替代测试确认金额',
  '回函和替代确认金额占账面金额的比例(%)',
] as const

export type H0Metric = typeof H0_MATRIX_METRIC_LABELS[number]

/** 源模板锚点（守卫用后端导出的 fixture 交叉比对） */
export const H0_MATRIX_METRIC_ANCHORS = ['C30', 'C31', 'C32', 'C33', 'C34', 'C35', 'C36', 'C37'] as const

/** 唯一可手填的指标下标（源模板 R30 是手填行，其余为公式行） */
export const H0_MATRIX_EDITABLE_METRIC_INDEX = 0

/**
 * 默认品种列 —— 逐字取源模板 `E29/F29/G29`。
 *
 * 🔴 `H29='……'` 是**可扩位不 seed**；`使用权资产` 虽出现在 sheet 标题里但
 * 源模板矩阵未列（源模板自身遗漏），按「宁缺勿造」不 seed，由用户增列。
 */
export const H0_MATRIX_DEFAULT_CATEGORIES = ['固定资产', '工程物资', '租赁负债'] as const

/**
 * 后端语义槽键 → 中文标签（`h_cycle_specs` 各 `SemanticAccountSlot.label` 的镜像）。
 *
 * 用途：把 `project_context.h0_book_conflicts` 的三元组
 * `[槽键, 报表公式给的码, 按名定位到的实际码]` 翻成可读句子 —— 直接 `String()`
 * 会渲染成 `impairment,1601,1602,1606,1603` 这种裸串（浏览器实测暴露）。
 *
 * 🔴 键集须与后端 `four_table/h_cycle_specs.H_CYCLE_SPECS` 的槽键一致
 * （守卫 `h0SummaryMatrix.spec.ts` 读 py 源码交叉锁死）。
 */
export const H0_SLOT_LABELS: Readonly<Record<string, string>> = Object.freeze({
  gross: '原值',
  accum_dep: '累计折旧',
  accum_amort: '累计摊销',
  accum_depletion: '累计折耗',
  impairment: '减值准备',
  eng_mat: '工程物资',
  cip: '在建工程（核对用）',
  unearned_finance: '未确认融资费用',
})

// ─── 类型 ────────────────────────────────────────────────────────────────────

export interface H0MatrixCategory {
  /** 稳定 key，形态 `cat_{seq}` —— 🔴 不得用 label 作 key（同名品种会撞键） */
  key: string
  /** 品种名，须 ∈ `confirmation_account_type` 枚举（否则按品种 SUMIF 恒空） */
  label: string
}

export type H0CellOrigin = 'auto' | 'manual' | 'derived' | 'absent' | 'empty'

export interface H0MatrixCell {
  categoryKey: string
  categoryLabel: string
  metric: H0Metric
  metricIndex: number
  /** null = 无法计算/无此科目 → 渲染「-」，**绝不产出 NaN/Infinity/0 冒充** */
  value: number | null
  kind: 'amount' | 'ratio'
  editable: boolean
  origin: H0CellOrigin
  sourceHint?: string
}

export interface H0MatrixInput {
  /** H0-1 上区明细行 */
  rows: readonly ConfirmationRow[]
  /** 品种列定义（动态） */
  categories: readonly H0MatrixCategory[]
  /**
   * 后端按品种语义定位取到的账面金额。
   * - 键不存在 = 未取数（可手填）
   * - 值为 `null` = 本项目无此科目（两态必须可区分，见 R3.8 / Error Handling）
   */
  bookAmounts?: Readonly<Record<string, number | null>>
  /** 手工覆盖（key = `${categoryKey}::${metricIndex}`） */
  manualOverrides?: Readonly<Record<string, number>>
}

// ─── 工具 ────────────────────────────────────────────────────────────────────

/** 两位小数归一（避免浮点漂移进矩阵与勾稽） */
function round2(n: number): number {
  return Math.round(n * 100) / 100
}

/** 手工覆盖持久化 itemId */
export function h0MatrixOverrideItemId(categoryKey: string, metricIndex: number): string {
  return `H0-1-matrix-${categoryKey}-${metricIndex}`
}

/** 品种列定义持久化 itemId（改名/增删列必须落库，否则刷新即丢） */
export const H0_MATRIX_CATEGORIES_KEY = 'H0-1-matrix-categories'

/**
 * 品种列 key 的**单调计数器**持久化 itemId。
 *
 * 🔴 为什么需要它：只按「现有列最大 seq + 1」生成 key 会在**删列后复用旧 key** ——
 * 删掉 `cat_3` 再增列又得 `cat_3`，而 `H0-1-matrix-cat_3-0` 这类历史手工覆盖值
 * 若未被清干净（并发失败 / 旧数据 / 手工改库），就会串到新品种列上显示错误金额。
 * 用持久化计数器保证 key 永不复用。
 */
export const H0_MATRIX_SEQ_KEY = 'H0-1-matrix-seq'

/** 按默认品种生成初始列定义 */
export function createDefaultH0Categories(): H0MatrixCategory[] {
  return H0_MATRIX_DEFAULT_CATEGORIES.map((label, i) => ({ key: `cat_${i + 1}`, label }))
}

/** 现有列里的最大 seq（无合法 key 时返回 0） */
export function maxH0CategorySeq(existing: readonly H0MatrixCategory[]): number {
  let max = 0
  for (const c of existing) {
    const m = /^cat_(\d+)$/.exec(c.key)
    if (m) max = Math.max(max, Number(m[1]))
  }
  return max
}

/**
 * 生成下一个稳定 key（`cat_{seq}`）—— **永不复用已发放过的 key**。
 *
 * @param existing 当前列
 * @param storedSeq 持久化的单调计数器（`H0_MATRIX_SEQ_KEY`）；缺省时退化为
 *   「现有最大 seq」，此时删列后再增列会复用旧 key → 调用方**必须**传它。
 */
export function nextH0CategoryKey(
  existing: readonly H0MatrixCategory[],
  storedSeq?: number,
): string {
  const fromList = maxH0CategorySeq(existing)
  const fromStore = typeof storedSeq === 'number' && Number.isFinite(storedSeq) ? storedSeq : 0
  return `cat_${Math.max(fromList, fromStore) + 1}`
}

/** 解析持久化的计数器（脏数据回退 0） */
export function parseH0Seq(raw: unknown): number {
  const n = Number(raw)
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0
}

/** 反序列化持久化的品种列（脏数据/空值回退默认列） */
export function parseH0Categories(raw: unknown): H0MatrixCategory[] {
  if (!Array.isArray(raw) || raw.length === 0) return createDefaultH0Categories()
  const out: H0MatrixCategory[] = []
  const seen = new Set<string>()
  for (const item of raw) {
    const key = String((item as any)?.key ?? '').trim()
    const label = String((item as any)?.label ?? '').trim()
    if (!/^cat_\d+$/.test(key) || !label || seen.has(key)) continue
    seen.add(key)
    out.push({ key, label })
  }
  return out.length ? out : createDefaultH0Categories()
}

// ─── 主函数 ──────────────────────────────────────────────────────────────────

/**
 * 构建 H0-1「一、函证情况」矩阵。
 *
 * 返回按品种分组的二维数组：`result[catIdx][metricIdx]`
 */
export function buildH0SummaryMatrix(input: H0MatrixInput): H0MatrixCell[][] {
  const { rows, categories, bookAmounts, manualOverrides } = input
  const result: H0MatrixCell[][] = []

  for (const cat of categories) {
    // R31 发函金额 = SUMIF(E, 品种, F)
    const sendAmount = round2(sumByCategory(rows, cat.label, 'amount'))
    // R33 回函确认 = SUMIF(E, 品种, U)（无相符过滤 —— 业务规则已内含在 U 列派生里）
    const confirmAmount = round2(sumByCategory(rows, cat.label, 'confirmed_amount'))
    // R36 替代确认 = SUMIF(E, 品种, Y)
    const altAmount = round2(sumByCategory(rows, cat.label, 'alt_confirmed'))

    // R30 账面金额：手工覆盖 > 后端取数 > 未取数
    const manual = manualOverrides?.[h0MatrixOverrideItemId(cat.key, 0)]
    const hasBookKey = !!bookAmounts && Object.prototype.hasOwnProperty.call(bookAmounts, cat.label)
    const autoBook = hasBookKey ? bookAmounts![cat.label] : undefined

    let book: number | null
    let bookOrigin: H0CellOrigin
    let bookHint: string
    if (typeof manual === 'number' && Number.isFinite(manual)) {
      book = round2(manual)
      bookOrigin = 'manual'
      bookHint = '手工覆盖（清空可回落自动取数）'
    } else if (!hasBookKey) {
      book = null
      bookOrigin = 'empty'
      bookHint = '未取数 —— 可手工填写，或检查四表是否已入库'
    } else if (autoBook === null || autoBook === undefined) {
      book = null
      bookOrigin = 'absent'
      bookHint = '本项目科目表无该科目（不是余额为 0）'
    } else {
      book = round2(autoBook)
      bookOrigin = 'auto'
      bookHint = '按品种语义定位自 tb_balance 叶子聚合（原值 − 备抵）'
    }

    const cells: H0MatrixCell[] = [
      mk(cat, 0, book, 'amount', true, bookOrigin, bookHint),
      mk(cat, 1, sendAmount, 'amount', false, 'derived',
        `源模板 SUMIF(E,${cat.label},F) — Σ 上区[账户/交易=${cat.label}].金额或合同条款`),
      mk(cat, 2, safeRatio(sendAmount, book), 'ratio', false, 'derived', 'R31 ÷ R30'),
      mk(cat, 3, confirmAmount, 'amount', false, 'derived',
        `源模板 SUMIF(E,${cat.label},U) — Σ 上区[账户/交易=${cat.label}].可确认金额/条款`),
      mk(cat, 4, safeRatio(confirmAmount, sendAmount), 'ratio', false, 'derived', 'R33 ÷ R31'),
      mk(cat, 5, safeRatio(confirmAmount, book), 'ratio', false, 'derived', 'R33 ÷ R30'),
      mk(cat, 6, altAmount, 'amount', false, 'derived',
        `源模板 SUMIF(E,${cat.label},Y) — Σ 上区[账户/交易=${cat.label}].替代后可确认金额`),
      mk(cat, 7, safeRatio(confirmAmount + altAmount, book), 'ratio', false, 'derived',
        '（R33 + R36）÷ R30'),
    ]
    result.push(cells)
  }

  return result
}

function mk(
  cat: H0MatrixCategory,
  metricIndex: number,
  value: number | null,
  kind: 'amount' | 'ratio',
  editable: boolean,
  origin: H0CellOrigin,
  sourceHint?: string,
): H0MatrixCell {
  // 双保险：任何非有限值一律归一为 null（Property 5 禁 NaN/Infinity）
  const safe = typeof value === 'number' && Number.isFinite(value) ? value : null
  return {
    categoryKey: cat.key,
    categoryLabel: cat.label,
    metric: H0_MATRIX_METRIC_LABELS[metricIndex],
    metricIndex,
    value: safe,
    kind,
    editable,
    origin,
    sourceHint,
  }
}

/** 转成「指标行 × 品种列」的表格数据（`el-table` 直接消费） */
export interface H0MatrixTableRow {
  metric: H0Metric
  metricIndex: number
  kind: 'amount' | 'ratio'
  editable: boolean
  /** categoryKey → cell */
  cells: Record<string, H0MatrixCell>
}

export function toH0MatrixTableRows(matrix: H0MatrixCell[][]): H0MatrixTableRow[] {
  return H0_MATRIX_METRIC_LABELS.map((metric, metricIndex) => {
    const cells: Record<string, H0MatrixCell> = {}
    for (const catCells of matrix) {
      const cell = catCells[metricIndex]
      if (cell) cells[cell.categoryKey] = cell
    }
    const first = matrix[0]?.[metricIndex]
    return {
      metric,
      metricIndex,
      kind: first?.kind ?? 'amount',
      editable: metricIndex === H0_MATRIX_EDITABLE_METRIC_INDEX,
      cells,
    }
  })
}

/** 覆盖率红线：回函+替代确认占账面比例低于阈值的品种（审计充分性提示） */
export interface H0CoverageAlert {
  categoryKey: string
  categoryLabel: string
  ratio: number
  level: 'warn' | 'error'
}

export function detectH0CoverageAlerts(
  matrix: H0MatrixCell[][],
  opts: { warnBelow?: number; errorBelow?: number } = {},
): H0CoverageAlert[] {
  const warnBelow = opts.warnBelow ?? 0.8
  const errorBelow = opts.errorBelow ?? 0.5
  const out: H0CoverageAlert[] = []
  for (const catCells of matrix) {
    const cell = catCells[7] // R37 回函和替代确认金额占账面金额的比例
    if (!cell || cell.value === null) continue
    if (cell.value < errorBelow) {
      out.push({ categoryKey: cell.categoryKey, categoryLabel: cell.categoryLabel, ratio: cell.value, level: 'error' })
    } else if (cell.value < warnBelow) {
      out.push({ categoryKey: cell.categoryKey, categoryLabel: cell.categoryLabel, ratio: cell.value, level: 'warn' })
    }
  }
  return out
}
