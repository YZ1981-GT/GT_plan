/**
 * 合并报表「差额表」视图的纯逻辑（spec consol-elimination-single-source-push 任务 12.1 / 需求 5）。
 *
 * 数据来自 `GET /worksheet/report-breakdown`：列 = 所选汇总节点的直接子节点（母公司 / 本部、子公司、下级合并、
 * 合并差额 / 母分差额），合计 = 该节点合并数 —— 与合并报表、合并试算平衡表同一个求值函数。
 * 这里只做展示辅助、P4 核对（线性行各列之和 = 合计）与导出，不在前端重算任何金额。
 */
import Decimal from 'decimal.js'
import type { ConsolBreakdownColumn, ConsolReportBreakdownRow } from '@/services/consolidationApi'

/** 列类型（后端 columns[].kind）的中文 */
export const COLUMN_KIND_LABELS: Record<string, string> = {
  elim: '差额',
  data: '单户',
  aggregate: '下级汇总',
}

export function columnKindLabel(kind: string | null | undefined): string {
  return COLUMN_KIND_LABELS[kind || ''] || ''
}

/** 差额列：归属该差额节点的已审批调整 / 抵销分录（浅黄底，可穿透到分录） */
export function isElimColumn(col: Pick<ConsolBreakdownColumn, 'kind'>): boolean {
  return col.kind === 'elim'
}

/** 子节点列的值；无公式的行（标题行）不显示 0 */
export function breakdownCell(
  row: Pick<ConsolReportBreakdownRow, 'has_formula' | 'cells'>, nodeKey: string,
): string | null {
  if (!row.has_formula) return null
  return row.cells?.[nodeKey] ?? null
}

/** 合计列（= 该汇总节点合并数）；无公式的行不显示 0 */
export function breakdownTotal(row: Pick<ConsolReportBreakdownRow, 'has_formula' | 'total'>): string | null {
  if (!row.has_formula) return null
  return row.total ?? null
}

function dec(v: string | number | null | undefined): Decimal | null {
  if (v === null || v === undefined || v === '') return null
  try {
    const d = new Decimal(v)
    return d.isFinite() ? d : null
  } catch {
    return null
  }
}

export interface BreakdownMismatch {
  row_code: string
  row_name: string
  sum: string
  total: string
  difference: string
}

export interface BreakdownCheck {
  /** 参与核对的线性行 */
  checked: number
  /** 各列之和 ≠ 合计的行 */
  mismatched: BreakdownMismatch[]
  /** 公式非线性：只给合计，不按子节点分解 */
  nonlinear: number
  /** 合计取不到数，或部分列取不到数 */
  blank: number
}

/**
 * P4 核对：线性行 Σ 各子节点列 = 合计（Decimal 精确到分）。
 * 非线性行只计数；合计或任一列取不到数的行计入「留空」，不参与核对（不把空当 0）。
 */
export function breakdownCheck(
  rows: ReadonlyArray<ConsolReportBreakdownRow>, columns: ReadonlyArray<Pick<ConsolBreakdownColumn, 'node_key'>>,
): BreakdownCheck {
  const out: BreakdownCheck = { checked: 0, mismatched: [], nonlinear: 0, blank: 0 }
  for (const row of rows) {
    if (!row.has_formula) continue
    const total = dec(row.total)
    if (total === null) {
      out.blank += 1
      continue
    }
    if (!row.linear) {
      out.nonlinear += 1
      continue
    }
    const parts = columns.map((c) => dec(row.cells?.[c.node_key]))
    if (parts.some((p) => p === null)) {
      out.blank += 1
      continue
    }
    out.checked += 1
    const sum = parts.reduce<Decimal>((s, p) => s.plus(p as Decimal), new Decimal(0))
    if (!sum.equals(total)) {
      // 规范文本交给金额单元格显示（不在脚本里格式化金额）
      out.mismatched.push({
        row_code: row.row_code,
        row_name: row.row_name,
        sum: sum.toString(),
        total: total.toString(),
        difference: sum.minus(total).toString(),
      })
    }
  }
  return out
}

export function breakdownCheckText(check: BreakdownCheck): string {
  const parts = [
    check.mismatched.length
      ? `${check.mismatched.length} 行各列之和 ≠ 合计`
      : `${check.checked} 行各列之和 = 合计`,
  ]
  if (check.nonlinear) parts.push(`${check.nonlinear} 行公式非线性只给合计`)
  if (check.blank) parts.push(`${check.blank} 行取不到数`)
  return `核对：${parts.join('；')}`
}

/** 导出：行次、项目、各子节点列（数字，便于 Excel 求和）、合计、说明 */
export function breakdownExportAoa(
  rows: ReadonlyArray<ConsolReportBreakdownRow>, columns: ReadonlyArray<ConsolBreakdownColumn>,
): (string | number | null)[][] {
  const num = (v: string | null) => (v === null ? null : Number(v))
  const header = [
    '行次', '项目',
    ...columns.map((c) => (isElimColumn(c) ? `${c.label}（差额）` : c.label)),
    '合计', '说明',
  ]
  const body = rows.map((r) => [
    r.row_code,
    r.row_name,
    ...columns.map((c) => num(breakdownCell(r, c.node_key))),
    num(breakdownTotal(r)),
    r.note || '',
  ])
  return [header, ...body]
}
