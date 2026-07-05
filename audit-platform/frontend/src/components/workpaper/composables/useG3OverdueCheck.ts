/**
 * useG3OverdueCheck — G3-5 长期未收回检查（13列）
 *
 * Spec: .kiro/specs/g3-dividend-receivable/ Task 5.3
 *
 * 职责：
 * - 定义 OverdueDividendRow 类型（13列）
 * - 公式链：逾期天数 = MAX(0, 当前日期 - 约定付款日)  (calcOverdueDays)
 * - 风险高亮：>180天 红色 / >90天 橙色
 * - 预计可收回性下拉：全额可收回/部分可收回/很可能无法收回/无法收回
 * - 风险等级下拉：低/中/高/极高
 * - 底部汇总（逾期笔数 / 逾期总金额 / 高风险笔数）
 * - 动态行增删（ElMessageBox.prompt 输入被投资方名称）
 * - 存储到 allResponses 'G3-5-overdue-rows' key
 *
 * Requirements: 8.1~8.8
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  parseNum,
  calcOverdueDays,
  calcSubtotal,
} from './useG3DivRecFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 预计可收回性下拉选项 */
export type Recoverability = 'full' | 'partial' | 'unlikely' | 'irrecoverable'

/** 风险等级下拉选项 */
export type RiskLevel = 'low' | 'medium' | 'high' | 'extreme'

/** G3-5 长期未收回行（13列） */
export interface OverdueDividendRow {
  id: string
  seq: number
  investeeName: string                // 被投资方
  receivableAmount: number            // 应收金额
  declarationDate: string             // 宣告日
  agreedPaymentDate: string           // 约定付款日
  overdueDays: number                 // 逾期天数(公式)
  overdueReason: string               // 逾期原因
  investeeOperatingStatus: string     // 被投资方经营状况
  historicalDividendRecord: string    // 历史分红记录
  recoverability: Recoverability      // 预计可收回性(下拉)
  riskLevel: RiskLevel                // 风险等级(下拉)
  auditSuggestion: string             // 审计建议
  remark: string                      // 备注
}

export interface OverdueColumn {
  prop: keyof OverdueDividendRow
  label: string
  width: number
  formula?: boolean
  type?: 'text' | 'number' | 'date' | 'dropdown'
}

// ─── Column Constants ────────────────────────────────────────────────────────

export const OVERDUE_COLUMNS: OverdueColumn[] = [
  { prop: 'seq', label: '序号', width: 60, formula: true },
  { prop: 'investeeName', label: '被投资方', width: 160, type: 'text' },
  { prop: 'receivableAmount', label: '应收金额', width: 120, type: 'number' },
  { prop: 'declarationDate', label: '宣告日', width: 120, type: 'date' },
  { prop: 'agreedPaymentDate', label: '约定付款日', width: 120, type: 'date' },
  { prop: 'overdueDays', label: '逾期天数', width: 100, type: 'number', formula: true },
  { prop: 'overdueReason', label: '逾期原因', width: 150, type: 'text' },
  { prop: 'investeeOperatingStatus', label: '被投资方经营状况', width: 160, type: 'text' },
  { prop: 'historicalDividendRecord', label: '历史分红记录', width: 160, type: 'text' },
  { prop: 'recoverability', label: '预计可收回性', width: 140, type: 'dropdown' },
  { prop: 'riskLevel', label: '风险等级', width: 100, type: 'dropdown' },
  { prop: 'auditSuggestion', label: '审计建议', width: 180, type: 'text' },
  { prop: 'remark', label: '备注', width: 120, type: 'text' },
]

// ─── Dropdown Options ────────────────────────────────────────────────────────

export const RECOVERABILITY_OPTIONS: { value: Recoverability; label: string }[] = [
  { value: 'full', label: '全额可收回' },
  { value: 'partial', label: '部分可收回' },
  { value: 'unlikely', label: '很可能无法收回' },
  { value: 'irrecoverable', label: '无法收回' },
]

export const RISK_LEVEL_OPTIONS: { value: RiskLevel; label: string }[] = [
  { value: 'low', label: '低' },
  { value: 'medium', label: '中' },
  { value: 'high', label: '高' },
  { value: 'extreme', label: '极高' },
]

// ─── Storage Key ─────────────────────────────────────────────────────────────

const DATA_KEY = 'G3-5-overdue-rows'

// ─── Summary Type ────────────────────────────────────────────────────────────

export interface OverdueSummary {
  /** 逾期笔数（逾期天数 > 0） */
  overdueCount: number
  /** 逾期总金额 */
  overdueTotal: number
  /** 高风险笔数（riskLevel === 'high' || 'extreme'） */
  highRiskCount: number
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateId(): string {
  return `od-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function emptyRow(id: string, seq: number): OverdueDividendRow {
  return {
    id,
    seq,
    investeeName: '',
    receivableAmount: 0,
    declarationDate: '',
    agreedPaymentDate: '',
    overdueDays: 0,
    overdueReason: '',
    investeeOperatingStatus: '',
    historicalDividendRecord: '',
    recoverability: 'full',
    riskLevel: 'low',
    auditSuggestion: '',
    remark: '',
  }
}

/** 公式求解 — 逾期天数 = MAX(0, 当前日期 - 约定付款日) */
function enrich(r: OverdueDividendRow): OverdueDividendRow {
  const agreedDate = r.agreedPaymentDate ? new Date(r.agreedPaymentDate) : null
  const overdueDays =
    agreedDate && !isNaN(agreedDate.getTime())
      ? calcOverdueDays(new Date(), agreedDate)
      : 0

  return {
    ...r,
    overdueDays,
  }
}

function loadRows(map: Map<string, ChecklistResponse>): OverdueDividendRow[] {
  const raw = map.get(DATA_KEY)?.conclusion
  if (!raw) return [enrich(emptyRow(generateId(), 1))]
  try {
    const parsed = JSON.parse(raw) as Partial<OverdueDividendRow>[]
    if (!Array.isArray(parsed) || parsed.length === 0) {
      return [enrich(emptyRow(generateId(), 1))]
    }
    return parsed.map((p, i) =>
      enrich({ ...emptyRow(p.id ?? generateId(), p.seq ?? i + 1), ...p }),
    )
  } catch {
    return [enrich(emptyRow(generateId(), 1))]
  }
}

function calcSummary(list: OverdueDividendRow[]): OverdueSummary {
  const overdueRows = list.filter((r) => r.overdueDays > 0)
  return {
    overdueCount: overdueRows.length,
    overdueTotal: calcSubtotal(overdueRows.map((r) => parseNum(r.receivableAmount))),
    highRiskCount: list.filter(
      (r) => r.riskLevel === 'high' || r.riskLevel === 'extreme',
    ).length,
  }
}

// ─── Risk Highlighting ───────────────────────────────────────────────────────

/**
 * 获取行的风险高亮样式 class
 * >180天 → 红色 (danger)
 * >90天且≤180天 → 橙色 (warning)
 * 其他 → 无
 */
export function getOverdueRiskClass(row: OverdueDividendRow): string {
  if (row.overdueDays > 180) return 'overdue-danger'
  if (row.overdueDays > 90) return 'overdue-warning'
  return ''
}

/**
 * 判断行是否为高风险（>180天红色）
 */
export function isOverdueDanger(row: OverdueDividendRow): boolean {
  return row.overdueDays > 180
}

/**
 * 判断行是否为中风险（>90天橙色）
 */
export function isOverdueWarning(row: OverdueDividendRow): boolean {
  return row.overdueDays > 90 && row.overdueDays <= 180
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG3OverdueCheck(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const rows = ref<OverdueDividendRow[]>(loadRows(opts.allResponses.value))

  function loadAll() {
    rows.value = loadRows(opts.allResponses.value)
  }

  // allResponses 异步加载完成后回填
  watch(
    () => opts.allResponses.value.get(DATA_KEY)?.conclusion,
    (raw) => {
      if (raw) rows.value = loadRows(opts.allResponses.value)
    },
  )

  /** 底部汇总 */
  const summary = computed<OverdueSummary>(() => calcSummary(rows.value))

  function persistAll() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
    }
  }

  function updateRow(id: string, patch: Partial<OverdueDividendRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrich({ ...r, ...patch }) : r))
    persistAll()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入被投资方名称', '新增逾期检查行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '被投资方名称不能为空',
      })
      const seq = rows.value.length + 1
      rows.value = [
        ...rows.value,
        enrich({ ...emptyRow(generateId(), seq), investeeName: value }),
      ]
      persistAll()
    } catch {
      /* cancelled */
    }
  }

  function removeRow(id: string) {
    if (opts.isReadonly.value || rows.value.length <= 1) return
    rows.value = rows.value
      .filter((r) => r.id !== id)
      .map((r, i) => ({ ...r, seq: i + 1 }))
    persistAll()
  }

  return {
    columns: OVERDUE_COLUMNS,
    rows,
    summary,
    loadAll,
    persistAll,
    updateRow,
    addRow,
    removeRow,
    getOverdueRiskClass,
    isOverdueDanger,
    isOverdueWarning,
    RECOVERABILITY_OPTIONS,
    RISK_LEVEL_OPTIONS,
  }
}

export default useG3OverdueCheck
