export type ConsolDrillSource = 'tb' | 'report'
export type ConsolDrillPeriod = 'current' | 'prior'

export interface ConsolDrillTarget {
  readonly source: ConsolDrillSource
  readonly rowCode: string
  readonly reportType: string
  readonly nodeKey: string
  readonly period: ConsolDrillPeriod
  readonly itemName: string
  readonly colName: string
  readonly totalValue: number | null
  readonly accountCode?: string
}

export interface ConsolDrillTargetContext {
  source: ConsolDrillSource | null
  reportType: string
  nodeKey: string
}

interface DrillContextInput {
  reportType: unknown
  nodeKey: unknown
  accountCode?: unknown
}

interface ReportColumnInput {
  label: unknown
  currentLabel: string
  priorLabel: string
}

function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

export function consolDrillNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function freezeTarget(target: ConsolDrillTarget): ConsolDrillTarget {
  return Object.freeze(target)
}

export function createTbConsolDrillTarget(
  row: Record<string, unknown>,
  context: DrillContextInput,
): ConsolDrillTarget | null {
  const rowCode = text(row.row_code)
  const reportType = text(context.reportType)
  const nodeKey = text(context.nodeKey)
  if (!rowCode || !reportType || !nodeKey) return null
  const accountCode = text(context.accountCode) || text(row.standard_account_code)
  return freezeTarget({
    source: 'tb',
    rowCode,
    reportType,
    nodeKey,
    period: 'current',
    itemName: text(row.row_name) || rowCode,
    colName: '合并审定数',
    totalValue: consolDrillNumber(row.consolidated),
    ...(accountCode ? { accountCode } : {}),
  })
}

export function createReportConsolDrillTarget(
  row: Record<string, unknown>,
  column: ReportColumnInput,
  context: DrillContextInput,
): ConsolDrillTarget | null {
  const label = text(column.label)
  const period: ConsolDrillPeriod | null = label === column.currentLabel
    ? 'current'
    : label === column.priorLabel
      ? 'prior'
      : null
  const rowCode = text(row.row_code)
  const reportType = text(context.reportType)
  const nodeKey = text(context.nodeKey)
  if (!period || !rowCode || !reportType || !nodeKey) return null
  const accountCode = text(context.accountCode)
  const amount = period === 'current' ? row.current_period_amount : row.prior_period_amount
  return freezeTarget({
    source: 'report',
    rowCode,
    reportType,
    nodeKey,
    period,
    itemName: text(row.row_name) || rowCode,
    colName: label,
    totalValue: consolDrillNumber(amount),
    ...(accountCode ? { accountCode } : {}),
  })
}

export function isConsolDrillTargetCurrent(
  target: ConsolDrillTarget | null,
  context: ConsolDrillTargetContext,
): boolean {
  return !!target
    && target.source === context.source
    && target.reportType === context.reportType
    && target.nodeKey === context.nodeKey
}

export function consolDrillTargetKey(target: ConsolDrillTarget | null): string {
  if (!target) return ''
  return JSON.stringify([
    target.source,
    target.rowCode,
    target.reportType,
    target.nodeKey,
    target.period,
    target.accountCode ?? '',
  ])
}
