/**
 * useH2CostComparison — H2-7 工程造价比较 composable
 *
 * 对齐致同「工程造价比较分析表」编制逻辑：
 * 1) 单方造价 vs 可比价（均值/差异/差异率）
 * 2) 本期增加额 vs 计入现金流量金额（项目层 + 主体层汇总勾稽）
 *
 * 从 H2-2 取：工程名称、预算(总造价)、建筑面积、本期增加合计
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface H2CostComparisonRow {
  rowId: string
  /** 工程名称 */
  name: string
  /** 工程项目总造价（可研/概预算） */
  totalCost: number
  /** 建筑面积(㎡)；装置类等可空 */
  buildingArea: number | null
  /** 单方造价 (公式) */
  unitCost: number | null
  /** 可比价1/2/3 */
  comparable1: number | null
  comparable2: number | null
  comparable3: number | null
  /** 可比价均值 (公式) */
  comparableAvg: number | null
  /** 与可比价差异 = 单方造价 - 均值 (公式) */
  unitCostDiff: number | null
  /** 差异率(%) (公式) */
  unitCostDiffRate: number | null
  /** 可比价来源索引 */
  comparableSourceIndex: string
  /** 本期增加额 */
  periodIncrease: number
  /** 本期计入现金流量金额 */
  cashFlowAmount: number
  /** 勾稽差异 = 增加额 - 现金流 (公式) */
  cashDiff: number | null
  /** 差异原因/关注事项 */
  diffReason: string
}

/** 主体层现金流勾稽汇总 */
export interface H2CostCashFlowRecon {
  /** 现金流量表购建固定资产等支付的现金 */
  cfsCapexAmount: number | null
  /** 勾稽说明 */
  reconNote: string
}

export type CostHighlight = 'red-unit-diff' | 'red-cash-diff' | null

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H2-7-rows'
const NOTE_KEY = 'H2-7-audit-note'
const CONCLUSION_KEY = 'H2-7-audit-conclusion'
const RECON_KEY = 'H2-7-cashflow-recon'
/** 单方造价差异率绝对值超过该阈值(%)时红色高亮 */
export const UNIT_DIFF_THRESHOLD = 15

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _avgComparables(a: number | null, b: number | null, c: number | null): number | null {
  const vals = [a, b, c].filter((v): v is number => v != null && !Number.isNaN(v))
  if (!vals.length) return null
  return vals.reduce((s, v) => s + v, 0) / vals.length
}

function _numOrNull(v: unknown): number | null {
  if (v === null || v === undefined || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

function _sum(nums: Array<number | null | undefined>): number {
  return nums.reduce<number>((s, v) => s + (Number(v) || 0), 0)
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2CostComparison(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}) {
  const rows = ref<H2CostComparisonRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  const cashFlowRecon = ref<H2CostCashFlowRecon>({
    cfsCapexAmount: null,
    reconNote: '',
  })

  function _getJson(itemId: string): any {
    const item = options.allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return null }
  }

  function _getString(itemId: string): string {
    const item = options.allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _recalcRow(row: H2CostComparisonRow): void {
    const area = row.buildingArea
    row.unitCost = area != null && area > 0 ? row.totalCost / area : null

    row.comparableAvg = _avgComparables(row.comparable1, row.comparable2, row.comparable3)

    if (row.unitCost != null && row.comparableAvg != null) {
      row.unitCostDiff = row.unitCost - row.comparableAvg
      row.unitCostDiffRate = row.comparableAvg !== 0
        ? (row.unitCostDiff / row.comparableAvg) * 100
        : null
    } else {
      row.unitCostDiff = null
      row.unitCostDiffRate = null
    }

    // 有任一现金流相关录入时计算差异
    const hasCash = row.periodIncrease !== 0 || row.cashFlowAmount !== 0
    row.cashDiff = hasCash ? row.periodIncrease - row.cashFlowAmount : null
  }

  function _normalizeRow(r: any): H2CostComparisonRow {
    // 兼容旧版「预算vs实际分项」字段：映射到新结构，避免已存数据丢失
    const totalCost = Number(
      r.totalCost ?? r.contractBudget ?? r.adjustedBudget ?? r.budgetAmount ?? 0,
    ) || 0
    const periodIncrease = Number(
      r.periodIncrease
      ?? r.actualTotal
      ?? ((Number(r.actualMaterial) || 0)
        + (Number(r.actualLabor) || 0)
        + (Number(r.actualMachinery) || 0)
        + (Number(r.actualOther) || 0))
      ?? 0,
    ) || 0

    const row: H2CostComparisonRow = {
      rowId: r.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      name: r.name ?? r.projectName ?? '',
      totalCost,
      buildingArea: _numOrNull(r.buildingArea ?? r.area),
      unitCost: null,
      comparable1: _numOrNull(r.comparable1),
      comparable2: _numOrNull(r.comparable2),
      comparable3: _numOrNull(r.comparable3),
      comparableAvg: null,
      unitCostDiff: null,
      unitCostDiffRate: null,
      comparableSourceIndex: r.comparableSourceIndex ?? r.sourceIndex ?? '',
      periodIncrease,
      cashFlowAmount: Number(r.cashFlowAmount) || 0,
      cashDiff: null,
      diffReason: r.diffReason ?? r.deviationReason ?? '',
    }
    _recalcRow(row)
    return row
  }

  function initFromAllResponses(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map(_normalizeRow)
    } else {
      const h2_2_resp = options.allResponses.value.get('H2-2-rows')
      const raw = h2_2_resp?.remark ?? h2_2_resp?.conclusion
      if (raw) {
        try {
          const h2Rows = JSON.parse(raw)
          if (Array.isArray(h2Rows)) {
            rows.value = h2Rows.map((r: any) => _normalizeRow({
              name: r.name,
              totalCost: r.budget,
              buildingArea: r.area,
              periodIncrease: r.increaseTotal,
            }))
          }
        } catch { /* empty */ }
      } else {
        rows.value = []
      }
    }

    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)

    const recon = _getJson(RECON_KEY)
    if (recon && typeof recon === 'object') {
      cashFlowRecon.value = {
        cfsCapexAmount: _numOrNull(recon.cfsCapexAmount),
        reconNote: String(recon.reconNote ?? ''),
      }
    } else {
      cashFlowRecon.value = { cfsCapexAmount: null, reconNote: '' }
    }
  }

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  /** 合计行 */
  const totalRow: ComputedRef<Partial<H2CostComparisonRow> & { name: string }> = computed(() => {
    const totalCost = _sum(rows.value.map(r => r.totalCost))
    const areaSum = _sum(rows.value.map(r => r.buildingArea))
    const periodIncrease = _sum(rows.value.map(r => r.periodIncrease))
    const cashFlowAmount = _sum(rows.value.map(r => r.cashFlowAmount))
    const hasArea = rows.value.some(r => r.buildingArea != null && r.buildingArea > 0)
    return {
      name: '合计',
      totalCost,
      buildingArea: hasArea ? areaSum : null,
      unitCost: hasArea && areaSum > 0 ? totalCost / areaSum : null,
      periodIncrease,
      cashFlowAmount,
      cashDiff: periodIncrease - cashFlowAmount,
    }
  })

  /** 主体层勾稽差异 = 上表增加合计 − 现金流量表金额 */
  const entityCashDiff: ComputedRef<number | null> = computed(() => {
    const cfs = cashFlowRecon.value.cfsCapexAmount
    if (cfs == null) return null
    return (totalRow.value.periodIncrease ?? 0) - cfs
  })

  const rowHighlights: ComputedRef<Map<string, CostHighlight>> = computed(() => {
    const map = new Map<string, CostHighlight>()
    for (const row of rows.value) {
      if (row.unitCostDiffRate != null && Math.abs(row.unitCostDiffRate) > UNIT_DIFF_THRESHOLD) {
        map.set(row.rowId, 'red-unit-diff')
      } else if (row.cashDiff != null && Math.abs(row.cashDiff) > 0.005) {
        map.set(row.rowId, 'red-cash-diff')
      } else {
        map.set(row.rowId, null)
      }
    }
    return map
  })

  function addRow(name: string): void {
    if (options.isReadonly.value) return
    if (!name?.trim()) return
    rows.value.push(_normalizeRow({ name: name.trim() }))
    _persist()
  }

  function removeRow(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx !== -1) {
      rows.value.splice(idx, 1)
      _persist()
    }
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    const formulaFields = [
      'unitCost', 'comparableAvg', 'unitCostDiff', 'unitCostDiffRate', 'cashDiff',
    ]
    if (formulaFields.includes(field)) return

    const nullableNumFields = ['buildingArea', 'comparable1', 'comparable2', 'comparable3']
    const numFields = ['totalCost', 'periodIncrease', 'cashFlowAmount']

    if (nullableNumFields.includes(field)) {
      ;(row as any)[field] = _numOrNull(value)
    } else if (numFields.includes(field)) {
      ;(row as any)[field] = Number(value) || 0
    } else {
      ;(row as any)[field] = String(value ?? '')
    }
    _recalcRow(row)
    _persist()
  }

  function updateRecon(patch: Partial<H2CostCashFlowRecon>): void {
    if (options.isReadonly.value) return
    cashFlowRecon.value = {
      ...cashFlowRecon.value,
      ...patch,
      cfsCapexAmount: patch.cfsCapexAmount !== undefined
        ? _numOrNull(patch.cfsCapexAmount)
        : cashFlowRecon.value.cfsCapexAmount,
    }
    options.onSave?.(RECON_KEY, { ...cashFlowRecon.value })
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options.onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options.onSave?.(CONCLUSION_KEY, conclusion)
  }

  function _persist(): void {
    if (!options.onSave) return
    options.onSave(ROWS_KEY, rows.value.map(r => ({
      rowId: r.rowId,
      name: r.name,
      totalCost: r.totalCost,
      buildingArea: r.buildingArea,
      comparable1: r.comparable1,
      comparable2: r.comparable2,
      comparable3: r.comparable3,
      comparableSourceIndex: r.comparableSourceIndex,
      periodIncrease: r.periodIncrease,
      cashFlowAmount: r.cashFlowAmount,
      diffReason: r.diffReason,
    })))
  }

  return {
    rows,
    auditNote,
    auditConclusion,
    cashFlowRecon,
    totalRow,
    entityCashDiff,
    rowHighlights,
    addRow,
    removeRow,
    updateCell,
    updateRecon,
    saveNote,
    saveConclusion,
    initFromAllResponses,
  }
}

export default useH2CostComparison
