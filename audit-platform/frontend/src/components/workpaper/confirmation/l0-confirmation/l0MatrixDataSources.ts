/**
 * l0MatrixDataSources.ts — L0-1 矩阵账面金额的取数与手工覆盖键
 *
 * spec: l0-confirmation-source-alignment，Task 10（Requirements 3.4 / 3.5）
 *
 * ─── 与 F0/G0 取数路径的关键差异 ──────────────────────────────────────────
 * F0/G0 是**前端**去拉相邻循环审定表的 render-config（`project_context.tb_amount`）。
 * L0 不走这条路 —— L1~L8 的 render 并不统一下发该键（同 H 循环的情形），照抄必得
 * `undefined`（dead output）。L0 的账面金额由**后端** `_inject_l0_book_amounts`
 * 按语义科目定位算好后注入 `project_context.l0_book_amounts`，本模块只做读取与归一。
 *
 * 🔴 **三态必须原样保留，禁 `?? {}` 兜底**：
 * | 形态                            | 含义                    | UI 文案            |
 * |---------------------------------|-------------------------|--------------------|
 * | `l0_book_amounts` 键不存在      | 注入未发生/取数整体失败 | 未取数（可手填）   |
 * | 键存在、品种值为 `null`         | 本项目科目表无该科目    | 本项目无此科目     |
 * | 键存在、品种值为 `0`            | 科目存在且余额为 0      | 0.00               |
 * 写 `?? {}` 会把第一种变成第二种，让全部品种显示「本项目无此科目」。
 *
 * 🔴 **诊断必须有渲染出口** —— F0 那轮的教训：`diagnostics.errors` 只收集不渲染，
 * 让「链路失效」与「本项目确实没这科目」不可区分，掩盖了一个 http 客户端错配 P0。
 */

import type { L0MetricKey } from './l0SummaryMatrix'
import { L0_MATRIX_CATEGORIES, L0_MATRIX_CATEGORY_NAMES } from './l0SummaryMatrix'

/** 手工覆盖 item_id 前缀（下区所有键的公共前缀之一，见 `l0SummaryLowerZone`） */
export const L0_MATRIX_KEY_PREFIX = 'L0-1-matrix'

/**
 * 手工覆盖键。
 *
 * 🔴 形态沿用 G0/K0 已确立的 `X0-1-matrix-{品种}-{指标key}`：
 * - **品种段是源模板中文字面**（同时是上区 `E 账户/交易` 列 SUMIF 的 criteria，
 *   属源模板事实非可改文案）
 * - **指标段是稳定 key**（`book_amount` 等），**不得用中文 label** —— 改文案会让
 *   既有录入值失联（F0 的 label-as-key 形态正是收敛时要改掉的那一侧）
 */
export function matrixOverrideItemId(category: string, metric: L0MetricKey): string {
  return `${L0_MATRIX_KEY_PREFIX}-${category}-${metric}`
}

/** 账面金额的手工覆盖键（矩阵 8 指标里唯一可覆盖的一行） */
export function bookAmountOverrideItemId(category: string): string {
  return matrixOverrideItemId(category, 'book_amount')
}

// ─── 账面金额与溯源的读取 ───────────────────────────────────────────────────

/** 后端 `l0_book_source_codes[品种]` 的形状（与 `l0_book_amounts.py` 的 source dict 对齐） */
export interface L0BookSource {
  category?: string
  source_wp_code?: string
  row_code?: string | null
  formula_hint?: string
  notes?: string[]
  gross?: string[]
  gross_standard?: string[]
  resolved_from?: string
  found?: boolean
  net_of?: string[]
  net_of_slots?: string[]
  net_of_skipped?: string[]
  conflicts?: string[]
  chart_available?: boolean | null
  absent_reason?: string
  parent_check?: Record<string, number>
}

/** 账面金额取数的三态 */
export type L0BookAmountState = 'not_fetched' | 'absent' | 'value'

export interface L0BookAmountView {
  category: string
  state: L0BookAmountState
  /** `state==='value'` 时为数值；否则 `null` */
  value: number | null
  source: L0BookSource | null
  /** UI 文案（中文，直接渲染） */
  text: string
}

/** 三态文案（UI 全中文化；三者互不相同是 Property 12 的断言点） */
export const L0_BOOK_STATE_TEXT: Readonly<Record<L0BookAmountState, string>> = Object.freeze({
  not_fetched: '未取数（可手填）',
  absent: '本项目无此科目',
  value: '',
})

/**
 * 从 render-config 的 `html_data` 读账面金额与溯源。
 *
 * @param htmlData 该 sheet 的 `html_data`（**不要**在调用侧写 `?? {}`）
 */
export function readL0BookAmounts(htmlData: unknown): {
  amounts: Record<string, number | null> | undefined
  sources: Record<string, L0BookSource> | undefined
  conflicts: string[]
} {
  const ctx = (htmlData as { project_context?: Record<string, unknown> } | null | undefined)
    ?.project_context
  const rawAmounts = ctx?.['l0_book_amounts']
  const rawSources = ctx?.['l0_book_source_codes']
  const rawConflicts = ctx?.['l0_book_conflicts']
  return {
    // 🔴 键不存在时返 `undefined`（不是 `{}`）—— 让「未取数」与「无此科目」可分
    amounts: isRecord(rawAmounts) ? (rawAmounts as Record<string, number | null>) : undefined,
    sources: isRecord(rawSources) ? (rawSources as Record<string, L0BookSource>) : undefined,
    conflicts: Array.isArray(rawConflicts) ? rawConflicts.map((x) => String(x)) : [],
  }
}

function isRecord(v: unknown): boolean {
  return !!v && typeof v === 'object' && !Array.isArray(v)
}

/** 逐品种解析三态视图（供矩阵单元格与溯源面板共用）。 */
export function buildL0BookAmountViews(htmlData: unknown): L0BookAmountView[] {
  const { amounts, sources } = readL0BookAmounts(htmlData)
  return L0_MATRIX_CATEGORY_NAMES.map((category) => {
    const source = sources?.[category] ?? null
    if (!amounts || !(category in amounts)) {
      return { category, state: 'not_fetched', value: null, source, text: L0_BOOK_STATE_TEXT.not_fetched }
    }
    const raw = amounts[category]
    if (raw === null || raw === undefined) {
      return { category, state: 'absent', value: null, source, text: L0_BOOK_STATE_TEXT.absent }
    }
    const n = Number(raw)
    if (!Number.isFinite(n)) {
      return { category, state: 'not_fetched', value: null, source, text: L0_BOOK_STATE_TEXT.not_fetched }
    }
    return { category, state: 'value', value: n, source, text: '' }
  })
}

// ─── 取数诊断（必须有渲染出口） ─────────────────────────────────────────────

export interface L0MatrixDiagnostics {
  /** 需在 UI 以 warning 提示条渲染（F0 教训：只收集不渲染会掩盖链路失效） */
  errors: string[]
  /** `report_config` 与项目科目表不一致（审计追溯，必须可见） */
  conflicts: string[]
  /** 「叶子和 == 父额」勾稽不成立的科目（非 0 即符号约定或父子双算） */
  parentCheckIssues: string[]
  /** 本项目科目表不可用 */
  chartUnavailable: boolean
}

/** 容差：与后端 `resolve_leaf_totals` 的 `tolerance=0.005` 同口径 */
const PARENT_CHECK_TOLERANCE = 0.005

/**
 * 汇总矩阵取数的诊断信息。
 *
 * 🔴 「未取数」也算 error —— 它意味着注入链路没跑到（不是业务上没有该科目），
 * 必须让审计师看见，否则与「本项目无此科目」不可区分。
 */
export function buildL0MatrixDiagnostics(htmlData: unknown): L0MatrixDiagnostics {
  const { amounts, sources, conflicts } = readL0BookAmounts(htmlData)
  const errors: string[] = []
  const parentCheckIssues: string[] = []
  let chartUnavailable = false

  if (!amounts) {
    errors.push('账面金额未取数：后端未下发 l0_book_amounts（可手工填写账面金额）')
  }

  for (const cat of L0_MATRIX_CATEGORIES) {
    const src = sources?.[cat.name]
    if (!src) continue
    if (src.chart_available === false) chartUnavailable = true
    if (src.absent_reason && src.absent_reason !== '本项目科目表无该科目') {
      errors.push(`${cat.name}：${src.absent_reason}`)
    }
    for (const [code, diff] of Object.entries(src.parent_check ?? {})) {
      if (Math.abs(Number(diff) || 0) > PARENT_CHECK_TOLERANCE) {
        parentCheckIssues.push(
          `${cat.name}·科目 ${code} 叶子合计与父科目余额差 ${Number(diff).toFixed(2)}`,
        )
      }
    }
  }

  return { errors, conflicts, parentCheckIssues, chartUnavailable }
}

/** 是否存在需要提示用户的诊断（供 UI 决定是否渲染提示条） */
export function hasL0MatrixDiagnostics(d: L0MatrixDiagnostics): boolean {
  return d.errors.length > 0 || d.conflicts.length > 0
    || d.parentCheckIssues.length > 0 || d.chartUnavailable
}
