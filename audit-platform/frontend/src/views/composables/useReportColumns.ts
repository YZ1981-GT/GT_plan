import { computed, type ComputedRef, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import type { ReportRow } from '@/services/auditPlatformApi'

// ─── Interfaces ─────────────────────────────────────────────────────────────

export interface UseReportColumnsOptions {
  isConsolidated: ComputedRef<boolean>
  activeTab: Ref<string>
  rows: Ref<ReportRow[]>
}

export interface UseReportColumnsReturn {
  // Equity columns
  eqColumns: ComputedRef<{ key: string; label: string }[]>
  eqTotalCols: ComputedRef<number>
  equitySpanMethod: (params: { row: any; column: any; rowIndex: number; columnIndex: number }) => { rowspan: number; colspan: number }
  eqRowClassName: (params: { row: any }) => string
  eqCellVal: (row: any, colKey: string) => any

  // Impairment columns
  impIncCols: { key: string; label: string }[]
  impDecCols: { key: string; label: string }[]
  impRowClassName: (params: { row: any }) => string

  // Shared helpers
  getRowType: (row: ReportRow) => string
  rowClassName: (params: { row: ReportRow }) => string
  compareRowClassName: (params: { row: any }) => string
  formatReportAmount: (value: any) => { text: string; isNegative: boolean }
  getNoteSection: (rowCode: string) => string | null
  goToNote: (rowCode: string) => void
}

// ─── Implementation ─────────────────────────────────────────────────────────

const eqColumnsBase = [
  { key: 'paid_in_capital', label: '实收资本' },
  { key: 'other_equity_preferred', label: '优先股' },
  { key: 'other_equity_perpetual', label: '永续债' },
  { key: 'other_equity_other', label: '其他' },
  { key: 'capital_reserve', label: '资本公积' },
  { key: 'treasury_stock', label: '减：库存股' },
  { key: 'oci', label: '其他综合收益' },
  { key: 'special_reserve', label: '专项储备' },
  { key: 'surplus_reserve', label: '盈余公积' },
  { key: 'general_risk', label: '一般风险准备' },
  { key: 'retained_earnings', label: '未分配利润' },
]

const eqConsolExtra = [
  { key: 'subtotal', label: '小计' },
  { key: 'minority', label: '少数股东权益' },
]

const impIncCols = [
  { key: 'provision', label: '本期计提额' },
  { key: 'merge_add', label: '合并增加额' },
  { key: 'other_add', label: '其他原因增加额' },
  { key: 'add_total', label: '合计' },
]

const impDecCols = [
  { key: 'reversal', label: '转回额' },
  { key: 'writeoff', label: '转销额' },
  { key: 'merge_dec', label: '合并减少额' },
  { key: 'other_dec', label: '其他原因减少额' },
  { key: 'dec_total', label: '合计' },
]

// 报表行→附注跳转映射
const _ROW_NOTE_MAP: Record<string, string> = {
  'BS-002': '五、1', 'BS-003': '五、2', 'BS-004': '五、2', 'BS-005': '五、3',
  'BS-006': '五、4', 'BS-007': '五、5', 'BS-008': '五、6', 'BS-012': '五、7',
  'BS-013': '五、8', 'BS-014': '五、9', 'BS-015': '五、10', 'BS-016': '五、12',
  'BS-017': '五、14', 'BS-018': '五、15', 'BS-031': '五、16', 'BS-033': '五、17',
  'BS-034': '五、18', 'BS-035': '五、19', 'BS-036': '五、20', 'BS-037': '五、21',
  'BS-041': '五、22', 'BS-051': '五、24', 'BS-052': '五、25', 'BS-053': '五、26',
  'BS-054': '五、27', 'BS-055': '五、28',
  'IS-001': '五、29', 'IS-002': '五、29',
}

export function useReportColumns(options: UseReportColumnsOptions): UseReportColumnsReturn {
  const { isConsolidated } = options
  const router = useRouter()

  // ─── Equity columns (computed) ──────────────────────────────────────────────
  const eqColumns = computed(() => {
    const base = [...eqColumnsBase]
    if (isConsolidated.value) {
      base.push(...eqConsolExtra)
    }
    base.push({ key: 'total', label: '所有者权益合计' })
    return base
  })

  const eqTotalCols = computed(() => eqColumns.value.length)

  // ─── Equity span-method ─────────────────────────────────────────────────────
  function equitySpanMethod({ row, columnIndex }: { row: any; column: any; rowIndex: number; columnIndex: number }) {
    if (row.indent_level === 0 && !row.is_total_row && columnIndex === 0) {
      return { rowspan: 1, colspan: 1 + eqColumns.value.length * 2 }
    }
    if (row.indent_level === 0 && !row.is_total_row && columnIndex > 0) {
      return { rowspan: 0, colspan: 0 }
    }
    return { rowspan: 1, colspan: 1 }
  }

  // ─── Equity row class ───────────────────────────────────────────────────────
  function eqRowClassName({ row }: { row: any }) {
    if (row.is_total_row) return 'gt-rv-eq-total-row'
    if (row.indent_level === 0) return 'gt-rv-eq-category'
    return ''
  }

  // ─── Equity cell value ──────────────────────────────────────────────────────
  function eqCellVal(row: any, colKey: string): any {
    if (!row) return 0
    if (row.source_accounts && row.source_accounts[colKey] != null) {
      return row.source_accounts[colKey]
    }
    return 0
  }

  // ─── Impairment row class ───────────────────────────────────────────────────
  function impRowClassName({ row }: { row: any }) {
    if (row.is_total_row) return 'gt-rv-eq-total-row'
    return ''
  }

  // ─── Row type detection (6 types) ──────────────────────────────────────────
  function getRowType(row: ReportRow): string {
    if (row.row_name && (row.row_name.includes('：') || row.row_name.includes(':'))) return 'header'
    if (row.is_total_row) return 'total'
    if (row.row_name && (row.row_name.startsWith('△') || row.row_name.startsWith('▲'))) return 'special'
    if (!row.formula_used && row.current_period_amount === '0') return 'manual'
    if (parseFloat(row.current_period_amount || '0') === 0 && !row.current_period_amount?.includes('.')) return 'zero'
    return 'data'
  }

  // ─── Row class name ─────────────────────────────────────────────────────────
  function rowClassName({ row }: { row: ReportRow }) {
    const type = getRowType(row)
    return `report-row--${type}`
  }

  // ─── Compare row class name ─────────────────────────────────────────────────
  function compareRowClassName({ row }: { row: any }) {
    const type = getRowType(row)
    if (row.adjustment && row.adjustment !== 0) return `report-row--${type} diff-row`
    return `report-row--${type}`
  }

  // ─── Amount formatting (thousands separator + negative brackets) ─────────────
  function formatReportAmount(value: any): { text: string; isNegative: boolean } {
    if (value === null || value === undefined || value === '') return { text: '', isNegative: false }
    const num = typeof value === 'string' ? parseFloat(value) : Number(value)
    if (isNaN(num)) return { text: String(value), isNegative: false }
    if (num === 0) return { text: '0.00', isNegative: false }
    const isNeg = num < 0
    const abs = Math.abs(num)
    const parts = abs.toFixed(2).split('.')
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',')
    const formatted = parts.join('.')
    const text = isNeg ? `(${formatted})` : formatted
    return { text, isNegative: isNeg }
  }

  // ─── Note section mapping ───────────────────────────────────────────────────
  function getNoteSection(rowCode: string): string | null {
    return _ROW_NOTE_MAP[rowCode] || null
  }

  function goToNote(rowCode: string) {
    const section = getNoteSection(rowCode)
    if (section) {
      router.push({ path: `/projects/${router.currentRoute.value.params.projectId}/disclosure-notes`, query: { section } })
    }
  }

  return {
    eqColumns,
    eqTotalCols,
    equitySpanMethod,
    eqRowClassName,
    eqCellVal,
    impIncCols,
    impDecCols,
    impRowClassName,
    getRowType,
    rowClassName,
    compareRowClassName,
    formatReportAmount,
    getNoteSection,
    goToNote,
  }
}
