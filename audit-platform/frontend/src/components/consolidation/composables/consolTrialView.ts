/**
 * 合并试算平衡表页的纯逻辑（spec consol-elimination-single-source-push 任务 11 / 需求 4）。
 *
 * 页面只读 `GET /worksheet/report-trial`：五列都是后端按报表公式求值的净额（与合并报表同一函数），
 * 前端不再按「借减贷」重算合并审定数；这里只做展示辅助、穿透合计与审核（行恒等式核对）。
 */
import Decimal from 'decimal.js'
import type {
  ConsolPushStatus,
  ConsolReportTrialRow,
  ConsolTrialMeasure,
} from '@/services/consolidationApi'

/** 报表类型（与合并报表页一致） */
export const TRIAL_REPORT_TYPES: ReadonlyArray<{ key: string; label: string }> = [
  { key: 'balance_sheet', label: '资产负债表' },
  { key: 'income_statement', label: '利润表' },
  { key: 'cash_flow_statement', label: '现金流量表' },
  { key: 'equity_statement', label: '权益变动表' },
  { key: 'cash_flow_supplement', label: '现金流附表' },
  { key: 'impairment_provision', label: '资产减值准备表' },
]

/** 五列（后端 columns 缺省时的兜底；顺序即展示顺序） */
export const TRIAL_MEASURES: ReadonlyArray<{ key: ConsolTrialMeasure; label: string }> = [
  { key: 'individual', label: '审定汇总' },
  { key: 'elim_equity', label: '权益抵销' },
  { key: 'elim_trade', label: '往来交易抵销' },
  { key: 'adjustment', label: '报表调整' },
  { key: 'consolidated', label: '合并审定数' },
]

const PARTS: ReadonlyArray<ConsolTrialMeasure> = ['individual', 'elim_equity', 'elim_trade', 'adjustment']

export function reportTypeLabel(key: string): string {
  return TRIAL_REPORT_TYPES.find((t) => t.key === key)?.label || key
}

/** 单元格显示值：无公式的行（标题行）不显示 0，免得像算出来的结果 */
export function cellValue(
  row: Pick<ConsolReportTrialRow, 'has_formula' | ConsolTrialMeasure>, measure: ConsolTrialMeasure,
): string | null {
  if (!row.has_formula) return null
  return row[measure] ?? null
}

/** 可穿透：有公式的行（取不到数的也可点开看原因） */
export function isDrillable(row: Pick<ConsolReportTrialRow, 'has_formula'>): boolean {
  return !!row.has_formula
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

/** 金额合计（空值跳过），到分的规范文本 */
export function sumAmounts(values: ReadonlyArray<string | number | null | undefined>): string {
  return values.reduce<Decimal>((s, v) => s.plus(dec(v) ?? 0), new Decimal(0)).toDecimalPlaces(2).toString()
}

export interface TrialAuditResult {
  section_title: string
  rule_name: string
  level: 'pass' | 'warn' | 'error'
  expected: string
  actual: string
  difference: string
  message: string
}

/**
 * 审核：逐行核对「审定汇总 + 权益抵销 + 往来交易抵销 + 报表调整 = 合并审定数」（线性行，精确到分）。
 * 取不到数的行逐条列出原因（warn）；公式非线性的行不能按列分解，只计数不校验。
 */
export function trialAuditResults(rows: ReadonlyArray<ConsolReportTrialRow>, sectionTitle: string): TrialAuditResult[] {
  const results: TrialAuditResult[] = []
  let checked = 0
  let nonlinear = 0
  for (const row of rows) {
    if (!row.has_formula) continue
    const total = dec(row.consolidated)
    if (total === null) {
      results.push({
        section_title: sectionTitle, rule_name: `取数 - ${row.row_name}`, level: 'warn',
        expected: '', actual: '', difference: '', message: row.note || '取不到数',
      })
      continue
    }
    if (!row.linear) {
      nonlinear += 1
      continue
    }
    const parts = PARTS.map((m) => dec(row[m]))
    if (parts.some((p) => p === null)) {
      results.push({
        section_title: sectionTitle, rule_name: `恒等式 - ${row.row_name}`, level: 'warn',
        expected: total.toString(), actual: '', difference: '', message: row.note || '部分列取不到数，无法核对',
      })
      continue
    }
    checked += 1
    const sum = parts.reduce<Decimal>((s, p) => s.plus(p as Decimal), new Decimal(0))
    if (!sum.equals(total)) {
      results.push({
        section_title: sectionTitle, rule_name: `恒等式 - ${row.row_name}`, level: 'error',
        expected: total.toString(), actual: sum.toString(), difference: sum.minus(total).toString(),
        message: '审定汇总 + 抵销 + 调整 ≠ 合并审定数',
      })
    }
  }
  const failed = results.filter((r) => r.level === 'error').length
  results.unshift({
    section_title: sectionTitle,
    rule_name: '行恒等式校验（审定汇总 + 权益抵销 + 往来交易抵销 + 报表调整 = 合并审定数）',
    level: failed ? 'error' : 'pass',
    expected: '', actual: `${checked} 行`, difference: failed ? `${failed} 行不等` : '',
    message: (failed ? `${failed} 行不相等` : `${checked} 行全部相等`)
      + (nonlinear ? `；${nonlinear} 行公式非线性，不按列分解、不校验` : ''),
  })
  return results
}

/** 导出：行次、项目、五列（数字，便于 Excel 求和）、说明 */
export function trialExportAoa(
  rows: ReadonlyArray<ConsolReportTrialRow>,
  columns: ReadonlyArray<{ key: ConsolTrialMeasure; label: string }>,
): (string | number | null)[][] {
  const header = ['行次', '项目', ...columns.map((c) => c.label), '说明']
  const body = rows.map((r) => [
    r.row_code,
    r.row_name,
    ...columns.map((c) => {
      const v = cellValue(r, c.key)
      return v === null ? null : Number(v)
    }),
    r.note || '',
  ])
  return [header, ...body]
}

// ─── 推送状态 ────────────────────────────────────────────────────────────────

const RUN_STATUS: Record<string, { label: string; type: 'success' | 'warning' | 'danger' | 'info' }> = {
  running: { label: '推送中', type: 'info' },
  succeeded: { label: '成功', type: 'success' },
  partial: { label: '部分成功', type: 'warning' },
  failed: { label: '失败', type: 'danger' },
}

const STEP_STATUS: Record<string, { label: string; type: 'success' | 'warning' | 'danger' | 'info' }> = {
  succeeded: { label: '成功', type: 'success' },
  failed: { label: '失败', type: 'danger' },
  skipped: { label: '已跳过', type: 'info' },
}

export function stepStatusLabel(status: string | null | undefined): string {
  return STEP_STATUS[status || '']?.label || status || ''
}

export function stepStatusType(status: string | null | undefined): 'success' | 'warning' | 'danger' | 'info' {
  return STEP_STATUS[status || '']?.type || 'info'
}

export function runStatusLabel(status: string | null | undefined): string {
  return RUN_STATUS[status || '']?.label || status || ''
}

export function runStatusType(status: string | null | undefined): 'success' | 'warning' | 'danger' | 'info' {
  return RUN_STATUS[status || '']?.type || 'info'
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleString('zh-CN', { hour12: false })
}

/** 最近一次推送的一句话说明（无记录 ⇒ 提示从未推送） */
export function pushStatusText(status: ConsolPushStatus | null | undefined): string {
  const run = status?.last_run
  if (!run) return '尚未推送过：合并报表与附注还没有按当前分录生成'
  const when = formatTime(run.finished_at || run.started_at)
  return `最近推送：${when}（${run.trigger_label || run.trigger_source}，${runStatusLabel(run.status)}）`
}
