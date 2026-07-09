/**
 * useH5Depletion — H5-12/13 折耗 composable
 *
 * 分支选择器(不含减值/含减值), 单位产量法, 折耗分配
 * H5-12 OO渲染(42/62公式) + H5-13折耗分配(11公式)
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/
 * Task: 3.4
 * Requirements: 7.1-7.6
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH5FormData'
import { calcSubtotal } from './useH5FormulaEngine'
import {
  calcUnitDepletion,
  calcDepletionRate,
  calcRemainingReserves,
  calcDepletionAfterImpairment,
  calcDepletionCapped,
} from './useH5DepletionEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type DepletionBranch = '不含减值' | '含减值'

export interface DepletionCalcRow {
  rowId: string
  category: string              // 资产分类
  cost: number                  // 原值
  salvage: number               // 残值
  totalReserves: number         // 总储量(万吨)
  accProduction: number         // 累计产量
  currentProduction: number     // 当期产量
  accDepletion: number          // 累计已提折耗
  remainReserves: number        // 剩余储量 - 公式
  currentDepletion: number      // 本期折耗 - 公式
  depletionRate: number         // 折耗率(%) - 公式
  // 含减值分支额外字段
  impairmentAmount: number      // 减值金额
  netValue: number              // 净值(含减值后)
}

export interface DepletionAllocRow {
  rowId: string
  costCenter: string            // 成本中心
  allocRatio: number            // 分配比例(%)
  allocAmount: number           // 分配金额 - 公式
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX_12 = 'H5-12'
const ITEM_PREFIX_13 = 'H5-13'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH5Depletion(opts: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  onSave?: (itemId: string, value: any) => void
  onPublishEvent?: (event: string, payload: any) => void
}) {
  const { allResponses, onSave } = opts

  const depletionBranch = ref<DepletionBranch>('不含减值')
  const calcRows = ref<DepletionCalcRow[]>([])
  const allocRows = ref<DepletionAllocRow[]>([])
  const auditNote = ref('')
  /** 是否使用OO渲染（H5-12复杂公式场景） */
  const useOnlyOffice = ref(true)

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _load(): void {
    const branchVal = allResponses.value.get(`${ITEM_PREFIX_12}-branch`)?.remark
    depletionBranch.value = branchVal === '含减值' ? '含减值' : '不含减值'

    const raw12 = allResponses.value.get(`${ITEM_PREFIX_12}-rows`)?.remark
    if (raw12) {
      try { calcRows.value = (JSON.parse(raw12) ?? []).map(_normalizeCalcRow) } catch { calcRows.value = [] }
    } else { calcRows.value = [] }

    const raw13 = allResponses.value.get(`${ITEM_PREFIX_13}-rows`)?.remark
    if (raw13) {
      try { allocRows.value = (JSON.parse(raw13) ?? []).map(_normalizeAllocRow) } catch { allocRows.value = [] }
    } else { allocRows.value = [] }

    auditNote.value = (allResponses.value.get(`${ITEM_PREFIX_12}-audit-note`)?.remark ?? '') as string
  }

  function _normalizeCalcRow(raw: any): DepletionCalcRow {
    const r: DepletionCalcRow = {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      category: raw.category ?? '',
      cost: Number(raw.cost) || 0,
      salvage: Number(raw.salvage) || 0,
      totalReserves: Number(raw.totalReserves) || 0,
      accProduction: Number(raw.accProduction) || 0,
      currentProduction: Number(raw.currentProduction) || 0,
      accDepletion: Number(raw.accDepletion) || 0,
      remainReserves: 0,
      currentDepletion: 0,
      depletionRate: 0,
      impairmentAmount: Number(raw.impairmentAmount) || 0,
      netValue: Number(raw.netValue) || 0,
    }
    _recalcRow(r)
    return r
  }

  function _normalizeAllocRow(raw: any): DepletionAllocRow {
    return {
      rowId: raw.rowId ?? `alloc-${Math.random().toString(36).slice(2, 10)}`,
      costCenter: raw.costCenter ?? '',
      allocRatio: Number(raw.allocRatio) || 0,
      allocAmount: Number(raw.allocAmount) || 0,
      remark: raw.remark ?? '',
    }
  }

  function _recalcRow(row: DepletionCalcRow): void {
    row.remainReserves = calcRemainingReserves(row.totalReserves, row.accProduction)

    if (depletionBranch.value === '含减值' && row.impairmentAmount > 0) {
      // 含减值分支：折耗基于净值
      const nv = row.cost - row.accDepletion - row.impairmentAmount
      row.netValue = nv
      row.currentDepletion = calcDepletionAfterImpairment(nv, row.salvage, row.currentProduction, row.remainReserves)
    } else {
      // 不含减值分支：标准单位产量法
      row.currentDepletion = calcUnitDepletion(row.cost, row.salvage, row.currentProduction, row.remainReserves)
    }

    // 封顶检查
    const cap = calcDepletionCapped(row.cost, row.salvage, row.accDepletion)
    if (row.currentDepletion > cap && cap > 0) {
      row.currentDepletion = cap
    }

    row.depletionRate = calcDepletionRate(row.accDepletion + row.currentDepletion, row.cost)
  }

  // ─── Computed ──────────────────────────────────────────────────────────────

  const totalCurrentDepletion = computed(() => calcSubtotal(calcRows.value.map((r) => r.currentDepletion)))
  const totalAllocAmount = computed(() => calcSubtotal(allocRows.value.map((r) => r.allocAmount)))
  const allocIsBalanced = computed(() => Math.abs(totalCurrentDepletion.value - totalAllocAmount.value) < 0.01)

  // ─── Actions ───────────────────────────────────────────────────────────────

  function switchBranch(branch: DepletionBranch): void {
    depletionBranch.value = branch
    calcRows.value.forEach(_recalcRow)
    onSave?.(`${ITEM_PREFIX_12}-branch`, branch)
    _persistCalc()
  }

  function updateCalcCell(rowId: string, field: keyof DepletionCalcRow, value: any): void {
    const row = calcRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _recalcRow(row)
    _persistCalc()
    _recalcAlloc()
  }

  function updateAllocCell(rowId: string, field: keyof DepletionAllocRow, value: any): void {
    const row = allocRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    if (field === 'allocRatio') {
      row.allocAmount = totalCurrentDepletion.value * (row.allocRatio / 100)
    }
    _persistAlloc()
  }

  /** 重算分配金额 */
  function _recalcAlloc(): void {
    const total = totalCurrentDepletion.value
    for (const row of allocRows.value) {
      row.allocAmount = total * (row.allocRatio / 100)
    }
    _persistAlloc()
  }

  /** 发布折耗分配到D5 */
  function publishDepletionAlloc(): void {
    opts.onPublishEvent?.('depletion:allocated', {
      wp_code: 'H5',
      totalDepletion: totalCurrentDepletion.value,
      allocations: allocRows.value.map((r) => ({ costCenter: r.costCenter, amount: r.allocAmount })),
    })
  }

  function _persistCalc(): void { onSave?.(`${ITEM_PREFIX_12}-rows`, calcRows.value) }
  function _persistAlloc(): void { onSave?.(`${ITEM_PREFIX_13}-rows`, allocRows.value) }

  watch(allResponses, () => _load(), { immediate: true })

  return {
    depletionBranch, calcRows, allocRows, auditNote, useOnlyOffice,
    totalCurrentDepletion, totalAllocAmount, allocIsBalanced,
    switchBranch, updateCalcCell, updateAllocCell, publishDepletionAlloc,
  }
}
