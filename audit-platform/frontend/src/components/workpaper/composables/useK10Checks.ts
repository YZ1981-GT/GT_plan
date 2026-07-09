/**
 * useK10Checks — K10-5应收政府补助 + K10-6综合检查表共用逻辑
 *
 * Spec: .kiro/specs/k10-other-income/
 * Task: 3.4
 * Requirements: 5.1-5.4
 *
 * 职责：
 * - K10-5应收政府补助检查：批文依据/收款权利确凿性/预期可收回/确认时点
 * - K10-6综合检查表：逐项"合规/不合规/不适用"判断（含分类正确性：
 *   与日常活动相关计其他收益 vs 与日常活动无关计营业外收入）
 * - 检查覆盖率计算（K10-6: 检查金额合计/明细合计）
 * - 不合规项红色高亮 + 摘要统计
 *
 * Item IDs:
 * - "K10-5-check-rows": 应收政府补助检查行（JSON-packed）
 * - "K10-6-check-rows": 综合检查行（JSON-packed）
 * - "K10-6-coverage-rate": 检查覆盖率
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useK10FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 检查状态 */
export type CheckStatus = '合规' | '不合规' | '不适用'

/** K10-5 应收政府补助检查行 */
export interface K10ReceivableCheckRow {
  rowKey: string
  /** 补助项目 */
  projectName: string
  /** 批文依据 */
  documentBasis: string
  /** 收款权利确凿性 */
  receivableRight: CheckStatus
  /** 预期可收回性 */
  expectedRecoverable: CheckStatus
  /** 确认时点合理性 */
  recognitionTiming: CheckStatus
  /** 金额 */
  amount: number
  /** 备注 */
  remark: string
  /** 可编辑标记 */
  isEditable: boolean
}

/** K10-6 综合检查行 */
export interface K10IncomeCheckRow {
  rowKey: string
  /** 检查项目名称 */
  checkItem: string
  /** 检查金额 */
  checkAmount: number
  /** 分类判断（其他收益/营业外收入） */
  classification: string
  /** 分类正确性 */
  classificationCorrect: CheckStatus
  /** 确认条件满足 */
  conditionMet: CheckStatus
  /** 总体结论 */
  overallStatus: CheckStatus
  /** 备注 */
  remark: string
  /** 可编辑标记 */
  isEditable: boolean
}

/** 检查统计摘要 */
export interface CheckSummary {
  total: number
  compliant: number
  nonCompliant: number
  notApplicable: number
  /** 不合规项目列表（用于红色摘要提示） */
  nonCompliantItems: string[]
}

export interface UseK10ChecksParams {
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  /** 区分使用场景：'K10-5' 或 'K10-6' */
  sheetKey: 'K10-5' | 'K10-6'
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK10Checks(params: UseK10ChecksParams) {
  const { allResponses, projectId, wpId, sheetKey, isReadonly, onSave } = params

  const ROWS_KEY = `${sheetKey}-check-rows`

  // ─── State ─────────────────────────────────────────────────────────────────

  const receivableRows = ref<K10ReceivableCheckRow[]>([])
  const incomeCheckRows = ref<K10IncomeCheckRow[]>([])
  const isChanged = ref(false)

  // ─── Load ──────────────────────────────────────────────────────────────────

  function initFromResponses(): void {
    const raw = _getJson(ROWS_KEY)
    if (sheetKey === 'K10-5') {
      receivableRows.value = Array.isArray(raw) ? raw.map(_normalizeReceivableRow) : []
    } else {
      incomeCheckRows.value = Array.isArray(raw) ? raw.map(_normalizeIncomeCheckRow) : []
    }
  }

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _normalizeReceivableRow(raw: any): K10ReceivableCheckRow {
    return {
      rowKey: raw.rowKey ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      projectName: raw.projectName ?? '',
      documentBasis: raw.documentBasis ?? '',
      receivableRight: _toCheckStatus(raw.receivableRight),
      expectedRecoverable: _toCheckStatus(raw.expectedRecoverable),
      recognitionTiming: _toCheckStatus(raw.recognitionTiming),
      amount: parseNum(raw.amount),
      remark: raw.remark ?? '',
      isEditable: raw.isEditable ?? true,
    }
  }

  function _normalizeIncomeCheckRow(raw: any): K10IncomeCheckRow {
    return {
      rowKey: raw.rowKey ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      checkItem: raw.checkItem ?? '',
      checkAmount: parseNum(raw.checkAmount),
      classification: raw.classification ?? '',
      classificationCorrect: _toCheckStatus(raw.classificationCorrect),
      conditionMet: _toCheckStatus(raw.conditionMet),
      overallStatus: _toCheckStatus(raw.overallStatus),
      remark: raw.remark ?? '',
      isEditable: raw.isEditable ?? true,
    }
  }

  function _toCheckStatus(val: any): CheckStatus {
    if (val === '合规' || val === '不合规' || val === '不适用') return val
    return '不适用'
  }

  // ─── K10-5: 应收补助检查统计 ──────────────────────────────────────────────

  const receivableSummary: ComputedRef<CheckSummary> = computed(() => {
    const items = receivableRows.value
    const total = items.length
    const nonCompliantItems: string[] = []
    let compliant = 0
    let nonCompliant = 0
    let notApplicable = 0

    for (const row of items) {
      // 综合判断：任意一项不合规则整行不合规
      const statuses = [row.receivableRight, row.expectedRecoverable, row.recognitionTiming]
      if (statuses.includes('不合规')) {
        nonCompliant++
        nonCompliantItems.push(row.projectName)
      } else if (statuses.every(s => s === '不适用')) {
        notApplicable++
      } else {
        compliant++
      }
    }
    return { total, compliant, nonCompliant, notApplicable, nonCompliantItems }
  })

  // ─── K10-6: 综合检查统计 + 覆盖率 ────────────────────────────────────────

  const incomeCheckSummary: ComputedRef<CheckSummary> = computed(() => {
    const items = incomeCheckRows.value
    const total = items.length
    const nonCompliantItems: string[] = []
    let compliant = 0
    let nonCompliant = 0
    let notApplicable = 0

    for (const row of items) {
      if (row.overallStatus === '不合规') {
        nonCompliant++
        nonCompliantItems.push(row.checkItem)
      } else if (row.overallStatus === '不适用') {
        notApplicable++
      } else {
        compliant++
      }
    }
    return { total, compliant, nonCompliant, notApplicable, nonCompliantItems }
  })

  /** K10-6 检查覆盖率 = 检查金额合计 / 明细合计 */
  const coverageRate: ComputedRef<number | null> = computed(() => {
    if (sheetKey !== 'K10-6') return null
    const checkTotal = calcSubtotal(incomeCheckRows.value.map(r => r.checkAmount))
    // 明细合计从 K10-2-subtotal 获取
    const detailTotalRaw = allResponses.value.get('K10-2-subtotal')
    const detailTotal = parseNum(detailTotalRaw?.remark ?? detailTotalRaw?.conclusion ?? 0)
    if (detailTotal === 0) return null
    return checkTotal / detailTotal
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateReceivableCell(rowKey: string, field: string, value: any): void {
    if (isReadonly?.value) return
    const row = receivableRows.value.find(r => r.rowKey === rowKey)
    if (!row || !row.isEditable) return
    ;(row as any)[field] = value
    isChanged.value = true
    _persist()
  }

  function updateIncomeCheckCell(rowKey: string, field: string, value: any): void {
    if (isReadonly?.value) return
    const row = incomeCheckRows.value.find(r => r.rowKey === rowKey)
    if (!row || !row.isEditable) return
    ;(row as any)[field] = value
    isChanged.value = true
    _persist()
  }

  // ─── 动态行操作 ────────────────────────────────────────────────────────────

  function addReceivableRow(projectName: string): void {
    if (isReadonly?.value) return
    receivableRows.value.push({
      rowKey: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      projectName,
      documentBasis: '',
      receivableRight: '不适用',
      expectedRecoverable: '不适用',
      recognitionTiming: '不适用',
      amount: 0,
      remark: '',
      isEditable: true,
    })
    isChanged.value = true
    _persist()
  }

  function addIncomeCheckRow(checkItem: string): void {
    if (isReadonly?.value) return
    incomeCheckRows.value.push({
      rowKey: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      checkItem,
      checkAmount: 0,
      classification: '',
      classificationCorrect: '不适用',
      conditionMet: '不适用',
      overallStatus: '不适用',
      remark: '',
      isEditable: true,
    })
    isChanged.value = true
    _persist()
  }

  function removeRow(rowKey: string): void {
    if (isReadonly?.value) return
    if (sheetKey === 'K10-5') {
      const idx = receivableRows.value.findIndex(r => r.rowKey === rowKey)
      if (idx >= 0) receivableRows.value.splice(idx, 1)
    } else {
      const idx = incomeCheckRows.value.findIndex(r => r.rowKey === rowKey)
      if (idx >= 0) incomeCheckRows.value.splice(idx, 1)
    }
    isChanged.value = true
    _persist()
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    if (!onSave) return
    if (sheetKey === 'K10-5') {
      onSave(ROWS_KEY, receivableRows.value)
    } else {
      onSave(ROWS_KEY, incomeCheckRows.value)
      // 存覆盖率供其他组件使用
      onSave(`${sheetKey}-coverage-rate`, coverageRate.value)
    }
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch(allResponses, () => initFromResponses(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // K10-5
    receivableRows,
    receivableSummary,
    // K10-6
    incomeCheckRows,
    incomeCheckSummary,
    coverageRate,
    // common
    isChanged,
    updateReceivableCell,
    updateIncomeCheckCell,
    addReceivableRow,
    addIncomeCheckRow,
    removeRow,
    initFromResponses,
  }
}

export default useK10Checks
