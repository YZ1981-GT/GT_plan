/**
 * useL2Detail — L2-2 明细表核心逻辑 composable
 *
 * Spec: .kiro/specs/l2-interest-payable/
 * Task: 3.4
 * Requirements: 3.1-3.5, 4.1-4.5
 *
 * 职责：
 * - 管理明细行（动态行，~16数据行，27列4区段分组）
 * - 区段分组：
 *   A~K (来源+未审): source/contractName/currency/principal/rate/period/beginBalance/accrued/paid/endBalance/remark
 *   L~Q (调整): entityReclass/endUnadjusted/aje/rje/audited/auditedEndBalance
 *   R~U (审定): adjustedBegin/adjustedAccrued/adjustedPaid/adjustedEnd
 *   V~AA (逾期+附注): overdueMonths/overdueReason/pledgeType/noteRef/isOverdue/noteDisclosure
 * - 行内公式：期末应付 = 期初 + 本期计提 - 本期支付（负债类 calcLiabilityEndBalance）
 * - subtotalRow / verificationRow computed
 * - 动态行 addRow / removeRow / updateCell
 * - searchQuery + filteredRows 模糊搜索
 * - 与 useL2ImportExport 集成
 *
 * 科目：2231 应付利息（贷方/负债类）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import { calcLiabilityEndBalance, calcSubtotal } from './useL2FormulaEngine'
import type { ChecklistResponse } from './useL2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface DetailRow {
  rowId: string
  // ── 区段A~K（来源+未审）──
  source: string              // 借款来源类别（短期借款/长期借款/应付债券）
  contractName: string        // 合同/借款名称
  creditor: string            // 债权人名称（源模板C列）
  currency: string            // 币种
  principal: number           // 本金
  rate: number                // 年利率(%)
  periodStart: string         // 计息期间起
  periodEnd: string           // 计息期间止
  beginBalance: number        // 期初应付利息
  accrued: number             // 本期计提
  paid: number                // 本期支付
  endBalance: number          // 期末应付利息 = 期初+计提-支付（负债类，自动）
  // ── 区段L~Q（调整）──
  entityReclass: number       // 被审计单位重分类
  endUnadjusted: number       // 期末未审 = endBalance + entityReclass（自动）
  aje: number                 // AJE调整
  rje: number                 // RJE调整
  audited: number             // 审定数 = endUnadjusted + aje + rje（自动）
  // ── 区段R~U（审定验证）──
  adjustedBegin: number       // 审定期初
  adjustedAccrued: number     // 审定本期计提
  adjustedPaid: number        // 审定本期支付
  adjustedEnd: number         // 审定期末 = 审定期初 + 审定计提 - 审定支付（自动）
  // ── 区段V~AA（逾期+附注）──
  overdueMonths: number       // 逾期月数
  overdueReason: string       // 逾期原因
  pledgeType: string          // 抵质押类型
  noteRef: string             // 附注引用编号
  isOverdue: boolean          // 是否逾期标记
  remark: string              // 备注
}

/** 区段定义（用于Tab切换） */
export type AreaGroup = 'source' | 'adjustment' | 'audited' | 'overdue'

export interface UseL2DetailOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  wpCode?: Ref<string>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  saveField: (itemId: string, value: { conclusion?: string; remark?: string }) => Promise<void>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'L2-L2-2-rows'

/** 来源分类选项 */
export const SOURCE_OPTIONS = ['短期借款利息', '长期借款利息', '应付债券利息'] as const

/** 区段列映射 */
export const AREA_GROUPS: Record<AreaGroup, string[]> = {
  source: ['source', 'contractName', 'creditor', 'currency', 'principal', 'rate', 'periodStart', 'periodEnd', 'beginBalance', 'accrued', 'paid', 'endBalance'],
  adjustment: ['entityReclass', 'endUnadjusted', 'aje', 'rje', 'audited'],
  audited: ['adjustedBegin', 'adjustedAccrued', 'adjustedPaid', 'adjustedEnd'],
  overdue: ['overdueMonths', 'overdueReason', 'pledgeType', 'noteRef', 'isOverdue', 'remark'],
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 安全解析 JSON 数组 */
function safeParseRows(jsonStr: string | null | undefined): DetailRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch {
    return []
  }
}

/** 规范化行数据 */
function normalizeRow(raw: any): DetailRow {
  return {
    rowId: raw.rowId || generateRowId(),
    source: raw.source || '',
    contractName: raw.contractName || '',
    creditor: raw.creditor || '',
    currency: raw.currency || 'CNY',
    principal: parseNum(raw.principal),
    rate: parseNum(raw.rate),
    periodStart: raw.periodStart || '',
    periodEnd: raw.periodEnd || '',
    beginBalance: parseNum(raw.beginBalance),
    accrued: parseNum(raw.accrued),
    paid: parseNum(raw.paid),
    endBalance: parseNum(raw.endBalance),
    entityReclass: parseNum(raw.entityReclass),
    endUnadjusted: parseNum(raw.endUnadjusted),
    aje: parseNum(raw.aje),
    rje: parseNum(raw.rje),
    audited: parseNum(raw.audited),
    adjustedBegin: parseNum(raw.adjustedBegin),
    adjustedAccrued: parseNum(raw.adjustedAccrued),
    adjustedPaid: parseNum(raw.adjustedPaid),
    adjustedEnd: parseNum(raw.adjustedEnd),
    overdueMonths: parseNum(raw.overdueMonths),
    overdueReason: raw.overdueReason || '',
    pledgeType: raw.pledgeType || '',
    noteRef: raw.noteRef || '',
    isOverdue: Boolean(raw.isOverdue),
    remark: raw.remark || '',
  }
}

/**
 * 行内公式重算（负债类方向！）
 * - endBalance = 期初 + 计提 - 支付
 * - endUnadjusted = endBalance + entityReclass
 * - audited = endUnadjusted + aje + rje
 * - adjustedEnd = adjustedBegin + adjustedAccrued - adjustedPaid
 */
export function recalcRowFormulas(row: DetailRow): DetailRow {
  const endBalance = calcLiabilityEndBalance(row.beginBalance, row.accrued, row.paid)
  const endUnadjusted = endBalance + row.entityReclass
  const audited = endUnadjusted + row.aje + row.rje
  const adjustedEnd = calcLiabilityEndBalance(row.adjustedBegin, row.adjustedAccrued, row.adjustedPaid)

  return {
    ...row,
    endBalance,
    endUnadjusted,
    audited,
    adjustedEnd,
    isOverdue: row.overdueMonths > 0,
  }
}

/** 创建空行 */
export function createEmptyRow(source?: string): DetailRow {
  return {
    rowId: generateRowId(),
    source: source || '',
    contractName: '',
    creditor: '',
    currency: 'CNY',
    principal: 0,
    rate: 0,
    periodStart: '',
    periodEnd: '',
    beginBalance: 0,
    accrued: 0,
    paid: 0,
    endBalance: 0,
    entityReclass: 0,
    endUnadjusted: 0,
    aje: 0,
    rje: 0,
    audited: 0,
    adjustedBegin: 0,
    adjustedAccrued: 0,
    adjustedPaid: 0,
    adjustedEnd: 0,
    overdueMonths: 0,
    overdueReason: '',
    pledgeType: '',
    noteRef: '',
    isOverdue: false,
    remark: '',
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useL2Detail(options: UseL2DetailOptions) {
  const { allResponses, wpId, projectId, wpCode, debouncedSave, saveField } = options

  // ─── Reactive rows ─────────────────────────────────────────────────────

  const rows = ref<DetailRow[]>([])
  const searchQuery = ref('')
  const activeArea = ref<AreaGroup>('source')

  // Load rows from allResponses
  watch(
    () => allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (jsonStr) => {
      const parsed = safeParseRows(jsonStr)
      rows.value = parsed.map(recalcRowFormulas)
    },
    { immediate: true },
  )

  // ─── Persist ───────────────────────────────────────────────────────────

  function persistRows(): void {
    debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  // ─── filteredRows ──────────────────────────────────────────────────────

  const filteredRows: ComputedRef<DetailRow[]> = computed(() => {
    if (!searchQuery.value) return rows.value
    const q = searchQuery.value.toLowerCase()
    return rows.value.filter(row =>
      row.contractName.toLowerCase().includes(q)
      || row.source.toLowerCase().includes(q),
    )
  })

  // ─── subtotalRow ───────────────────────────────────────────────────────

  const subtotalRow: ComputedRef<DetailRow> = computed(() => {
    const allRows = rows.value
    return {
      rowId: '__subtotal__',
      source: '',
      contractName: '合计',
      creditor: '',
      currency: '',
      principal: calcSubtotal(allRows.map(r => r.principal)),
      rate: 0,
      periodStart: '',
      periodEnd: '',
      beginBalance: calcSubtotal(allRows.map(r => r.beginBalance)),
      accrued: calcSubtotal(allRows.map(r => r.accrued)),
      paid: calcSubtotal(allRows.map(r => r.paid)),
      endBalance: calcSubtotal(allRows.map(r => r.endBalance)),
      entityReclass: calcSubtotal(allRows.map(r => r.entityReclass)),
      endUnadjusted: calcSubtotal(allRows.map(r => r.endUnadjusted)),
      aje: calcSubtotal(allRows.map(r => r.aje)),
      rje: calcSubtotal(allRows.map(r => r.rje)),
      audited: calcSubtotal(allRows.map(r => r.audited)),
      adjustedBegin: calcSubtotal(allRows.map(r => r.adjustedBegin)),
      adjustedAccrued: calcSubtotal(allRows.map(r => r.adjustedAccrued)),
      adjustedPaid: calcSubtotal(allRows.map(r => r.adjustedPaid)),
      adjustedEnd: calcSubtotal(allRows.map(r => r.adjustedEnd)),
      overdueMonths: 0,
      overdueReason: '',
      pledgeType: '',
      noteRef: '',
      isOverdue: false,
      remark: '',
    }
  })

  // ─── 按来源小计 ────────────────────────────────────────────────────────

  /** 按 source 分组小计（用于与L2-1审定表交叉验证） */
  const subtotalBySource: ComputedRef<Record<string, number>> = computed(() => {
    const result: Record<string, number> = {}
    for (const row of rows.value) {
      if (!row.source) continue
      result[row.source] = (result[row.source] || 0) + row.endBalance
    }
    return result
  })

  // ─── 逾期行统计 ────────────────────────────────────────────────────────

  const overdueRows: ComputedRef<DetailRow[]> = computed(() => {
    return rows.value.filter(r => r.isOverdue)
  })

  const overdueTotal: ComputedRef<number> = computed(() => {
    return calcSubtotal(overdueRows.value.map(r => r.endBalance))
  })

  // ─── L2→L8 联动：发布 l2:accrual-calculated 事件 ───────────────────────

  /**
   * 当明细行 accrued（本期计提）变化时，广播总计提额供 L8 财务费用订阅。
   * 事件载荷：totalAccrued + bySource 分类。
   * Requirements: 4.6 (L2→L8联动)
   */
  watch(
    () => rows.value.map(r => r.accrued),
    () => {
      const totalAccrued = calcSubtotal(rows.value.map(r => r.accrued))
      const bySource: Array<{ source: string; amount: number }> = []
      const sourceMap: Record<string, number> = {}
      for (const row of rows.value) {
        if (!row.source) continue
        sourceMap[row.source] = (sourceMap[row.source] || 0) + row.accrued
      }
      for (const [source, amount] of Object.entries(sourceMap)) {
        bySource.push({ source, amount })
      }

      eventBus.emit('l2:accrual-calculated', {
        wpCode: wpCode?.value || 'L2',
        totalAccrued,
        bySource,
        timestamp: Date.now(),
      })
    },
    { deep: true },
  )

  // ─── addRow ────────────────────────────────────────────────────────────

  /**
   * 新增明细行
   * @param source - 预填来源分类（可选）
   */
  function addRow(source?: string): void {
    const newRow = createEmptyRow(source)
    rows.value = [...rows.value, newRow]
    persistRows()
  }

  // ─── removeRow ─────────────────────────────────────────────────────────

  function removeRow(rowId: string): void {
    rows.value = rows.value.filter(r => r.rowId !== rowId)
    persistRows()
  }

  // ─── updateCell ────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return

    const row = { ...rows.value[idx] }

    // 数值字段列表
    const numericFields = [
      'principal', 'rate', 'beginBalance', 'accrued', 'paid',
      'entityReclass', 'aje', 'rje',
      'adjustedBegin', 'adjustedAccrued', 'adjustedPaid',
      'overdueMonths',
    ]

    if (numericFields.includes(field)) {
      ;(row as any)[field] = parseNum(value)
    } else if (field === 'isOverdue') {
      row.isOverdue = Boolean(value)
    } else {
      ;(row as any)[field] = value
    }

    // Recalculate formula chain
    const recalculated = recalcRowFormulas(row)

    const newRows = [...rows.value]
    newRows[idx] = recalculated
    rows.value = newRows

    persistRows()
  }

  // ─── batchImportRows（供导入使用） ─────────────────────────────────────

  /**
   * 批量导入行数据（从 useL2ImportExport 调用）
   */
  function batchImportRows(importedRows: Partial<DetailRow>[]): void {
    if (importedRows.length === 0) {
      ElMessage.info('导入数据为空')
      return
    }

    const newRows: DetailRow[] = importedRows.map(raw => {
      const normalized = normalizeRow(raw)
      return recalcRowFormulas(normalized)
    })

    rows.value = [...rows.value, ...newRows]
    persistRows()
    ElMessage.success(`成功导入 ${newRows.length} 行明细数据`)
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 数据
    rows,
    filteredRows,
    subtotalRow,
    subtotalBySource,
    overdueRows,
    overdueTotal,
    // 搜索 & 区段
    searchQuery,
    activeArea,
    // 操作
    addRow,
    removeRow,
    updateCell,
    batchImportRows,
    // 常量
    AREA_GROUPS,
    SOURCE_OPTIONS,
  }
}

export default useL2Detail
