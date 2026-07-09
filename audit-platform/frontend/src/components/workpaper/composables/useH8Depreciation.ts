/**
 * useH8Depreciation — H8-8 + H8-9 折旧 composable
 *
 * H8-8双分支：
 * - 不含减值（51行25列62公式）→ H8TabDepreciationNoImpair.vue
 * - 含减值（49行27列86公式）→ H8TabDepreciationWithImpair.vue
 *
 * H8-9 折旧分配分析表（24行10列11公式）
 *
 * 核心公式：折旧期 = min(租赁期, 使用寿命)（CAS21第21条）
 * 折旧方法：直线法，月折旧额 = 使用权资产入账值 / 折旧期月数
 *
 * Spec: .kiro/specs/h8-right-of-use-assets/
 * Task: 3.4
 * Requirements: 6.1-6.6
 */
import { ref, computed, watch, type Ref } from 'vue'
import { calcDepreciationPeriod } from './useH8CAS21Engine'
import { calcSubtotal } from './useH8FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H8-8折旧分支 */
export type H8DepreciationBranch = '不含减值' | '含减值'

/** 折旧参数行（每笔租赁合同一行） */
export interface H8DepreciationRow {
  rowId: string
  /** 合同号 */
  contractNo: string
  /** 资产名称 */
  assetName: string
  /** 使用权资产入账值 */
  rouAmount: number
  /** 租赁期（月） */
  leaseTermMonths: number
  /** 使用寿命（月） */
  usefulLifeMonths: number
  /** 折旧期（月）= min(租赁期, 寿命) */
  depPeriodMonths: number
  /** 月折旧额 = 入账值 / 折旧期 */
  monthlyDep: number
  /** 本期计提折旧（=月折旧×当期月数） */
  currentPeriodDep: number
  /** 当期月数 */
  monthsInPeriod: number
  /** 累计折旧 */
  accumulatedDep: number
  /** 减值金额（仅含减值分支用） */
  impairmentAmount: number
}

/** H8-9 折旧分配行 */
export interface H8DepAllocRow {
  rowId: string
  /** 费用类型（管理费用/销售费用等） */
  expenseType: string
  /** 分配比例(%) */
  allocRatio: number
  /** 分配金额 */
  allocAmount: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const BRANCH_KEY = 'H8-8-branch'
const DEP_ROWS_KEY = 'H8-8-dep-rows'
const ALLOC_ROWS_KEY = 'H8-9-alloc-rows'
const DEP_TOTAL_KEY = 'H8-8-dep-total'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH8Depreciation(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const branch = ref<H8DepreciationBranch>('不含减值')
  const depRows = ref<H8DepreciationRow[]>([])
  const allocRows = ref<H8DepAllocRow[]>([])

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeDepRow(raw: any): H8DepreciationRow {
    const rou = Number(raw.rouAmount) || 0
    const lt = Number(raw.leaseTermMonths) || 0
    const ul = Number(raw.usefulLifeMonths) || 0
    const depPeriod = calcDepreciationPeriod(lt, ul)
    const monthly = depPeriod > 0 ? rou / depPeriod : 0
    const monthsInPeriod = Number(raw.monthsInPeriod) || 12

    return {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      contractNo: raw.contractNo ?? '',
      assetName: raw.assetName ?? '',
      rouAmount: rou,
      leaseTermMonths: lt,
      usefulLifeMonths: ul,
      depPeriodMonths: depPeriod,
      monthlyDep: monthly,
      monthsInPeriod,
      currentPeriodDep: monthly * monthsInPeriod,
      accumulatedDep: Number(raw.accumulatedDep) || 0,
      impairmentAmount: Number(raw.impairmentAmount) || 0,
    }
  }

  function _normalizeAllocRow(raw: any): H8DepAllocRow {
    return {
      rowId: raw.rowId ?? `alloc-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      expenseType: raw.expenseType ?? '',
      allocRatio: Number(raw.allocRatio) || 0,
      allocAmount: Number(raw.allocAmount) || 0,
    }
  }

  // ─── Load ──────────────────────────────────────────────────────────────────

  function load(): void {
    const branchVal = _getString(BRANCH_KEY)
    branch.value = branchVal === '含减值' ? '含减值' : '不含减值'

    const depData = _getJson(DEP_ROWS_KEY)
    depRows.value = Array.isArray(depData) ? depData.map(_normalizeDepRow) : []

    const allocData = _getJson(ALLOC_ROWS_KEY)
    allocRows.value = Array.isArray(allocData) ? allocData.map(_normalizeAllocRow) : []
  }

  watch(allResponses, () => load(), { immediate: true })

  // ─── Computed ──────────────────────────────────────────────────────────────

  /** 本期折旧合计 */
  const depTotal = computed(() =>
    calcSubtotal(depRows.value.map(r => r.currentPeriodDep)),
  )

  /** 累计折旧合计 */
  const accDepTotal = computed(() =>
    calcSubtotal(depRows.value.map(r => r.accumulatedDep)),
  )

  /** 分配合计 */
  const allocTotal = computed(() =>
    calcSubtotal(allocRows.value.map(r => r.allocAmount)),
  )

  /** 分配比例合计（应=100%） */
  const allocRatioTotal = computed(() =>
    calcSubtotal(allocRows.value.map(r => r.allocRatio)),
  )

  // ─── Actions ───────────────────────────────────────────────────────────────

  function setBranch(b: H8DepreciationBranch): void {
    branch.value = b
    onSave?.(BRANCH_KEY, b)
  }

  function addDepRow(contractNo: string): void {
    if (!contractNo?.trim()) return
    depRows.value.push(_normalizeDepRow({ contractNo: contractNo.trim() }))
    _persistDep()
  }

  function deleteDepRow(rowId: string): void {
    const idx = depRows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    depRows.value.splice(idx, 1)
    _persistDep()
  }

  function updateDepCell(rowId: string, field: string, value: any): void {
    const row = depRows.value.find(r => r.rowId === rowId)
    if (!row) return

    if (field === 'contractNo' || field === 'assetName') {
      ;(row as any)[field] = String(value ?? '')
      _persistDep()
      return
    }

    const numVal = Number(value) || 0
    switch (field) {
      case 'rouAmount': row.rouAmount = numVal; break
      case 'leaseTermMonths': row.leaseTermMonths = numVal; break
      case 'usefulLifeMonths': row.usefulLifeMonths = numVal; break
      case 'monthsInPeriod': row.monthsInPeriod = numVal; break
      case 'accumulatedDep': row.accumulatedDep = numVal; break
      case 'impairmentAmount': row.impairmentAmount = numVal; break
      default: return
    }

    // 重算折旧期/月折旧/本期折旧
    row.depPeriodMonths = calcDepreciationPeriod(row.leaseTermMonths, row.usefulLifeMonths)
    row.monthlyDep = row.depPeriodMonths > 0 ? row.rouAmount / row.depPeriodMonths : 0
    row.currentPeriodDep = row.monthlyDep * row.monthsInPeriod

    _persistDep()
  }

  function addAllocRow(expenseType: string): void {
    if (!expenseType?.trim()) return
    allocRows.value.push(_normalizeAllocRow({ expenseType: expenseType.trim() }))
    _persistAlloc()
  }

  function deleteAllocRow(rowId: string): void {
    const idx = allocRows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    allocRows.value.splice(idx, 1)
    _persistAlloc()
  }

  function updateAllocCell(rowId: string, field: string, value: any): void {
    const row = allocRows.value.find(r => r.rowId === rowId)
    if (!row) return
    if (field === 'expenseType') {
      row.expenseType = String(value ?? '')
    } else if (field === 'allocRatio') {
      row.allocRatio = Number(value) || 0
      // 自动计算分配金额
      row.allocAmount = depTotal.value * row.allocRatio / 100
    } else if (field === 'allocAmount') {
      row.allocAmount = Number(value) || 0
    }
    _persistAlloc()
  }

  function save(): void { _persistDep(); _persistAlloc() }

  function _persistDep(): void {
    if (!onSave) return
    onSave(DEP_ROWS_KEY, depRows.value.map(r => ({
      rowId: r.rowId, contractNo: r.contractNo, assetName: r.assetName,
      rouAmount: r.rouAmount, leaseTermMonths: r.leaseTermMonths,
      usefulLifeMonths: r.usefulLifeMonths, monthsInPeriod: r.monthsInPeriod,
      accumulatedDep: r.accumulatedDep, impairmentAmount: r.impairmentAmount,
    })))
    onSave(DEP_TOTAL_KEY, depTotal.value)
  }

  function _persistAlloc(): void {
    if (!onSave) return
    onSave(ALLOC_ROWS_KEY, allocRows.value.map(r => ({
      rowId: r.rowId, expenseType: r.expenseType,
      allocRatio: r.allocRatio, allocAmount: r.allocAmount,
    })))
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    branch, depRows, allocRows,
    depTotal, accDepTotal, allocTotal, allocRatioTotal,
    setBranch, addDepRow, deleteDepRow, updateDepCell,
    addAllocRow, deleteAllocRow, updateAllocCell,
    save, load,
  }
}

export default useH8Depreciation
