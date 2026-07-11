/**
 * useH3Depreciation — H3-7 折旧测算 composable（仅成本模式）
 *
 * depreciationBranch状态(noImpair/withImpair) + 2分支共用数据
 * + 仅成本模式显示 + 折旧计算 + 差异验证
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.12
 * Requirements: 8.1-8.8
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'
import {
  calcStraightLineDepreciation,
  calcDepreciationWithImpairment,
  calcSubtotal,
} from './useH3FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type DepreciationBranch = 'noImpair' | 'withImpair'

export interface H3DepreciationRow {
  rowId: string
  assetName: string
  originalCost: number        // 原值
  salvageRate: number         // 残值率
  usefulLife: number          // 使用年限(年)
  elapsedYears: number        // 已使用年数
  impairment: number          // 减值准备(含减值分支)
  monthlyDep: number          // 月折旧（公式）
  annualDep: number           // 年折旧
  accDepCalc: number          // 测算累计折旧
  accDepBook: number          // 账面累计折旧
  difference: number          // 差异
  remark: string
}

const ITEM_ID = 'H3-7-dep-rows'
const BRANCH_ID = 'H3-7-branch'

export function useH3Depreciation(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
}) {
  const { allResponses, getValue, setValue } = params

  const branch = ref<DepreciationBranch>('noImpair')
  const rows = ref<H3DepreciationRow[]>([])

  function loadRows(): void {
    branch.value = (getValue(BRANCH_ID) as DepreciationBranch) || 'noImpair'
    const raw = getValue(ITEM_ID)
    rows.value = Array.isArray(raw) ? raw.map(_normalize) : []
  }

  function _normalize(raw: any): H3DepreciationRow {
    const cost = Number(raw.originalCost) || 0
    const salvage = Number(raw.salvageRate) || 0.05
    const life = Number(raw.usefulLife) || 20
    const elapsed = Number(raw.elapsedYears) || 0
    const impairment = Number(raw.impairment) || 0
    const bookDep = Number(raw.accDepBook) || 0

    let monthly: number
    if (branch.value === 'withImpair' && impairment > 0) {
      monthly = calcDepreciationWithImpairment(cost, salvage, life, impairment, elapsed)
    } else {
      monthly = calcStraightLineDepreciation(cost, salvage, life)
    }
    const annual = monthly * 12
    const accCalc = monthly * elapsed * 12

    return {
      rowId: raw.rowId ?? `dep-${Math.random().toString(36).slice(2, 8)}`,
      assetName: raw.assetName ?? '',
      originalCost: cost,
      salvageRate: salvage,
      usefulLife: life,
      elapsedYears: elapsed,
      impairment,
      monthlyDep: monthly,
      annualDep: annual,
      accDepCalc: accCalc,
      accDepBook: bookDep,
      difference: accCalc - bookDep,
      remark: raw.remark ?? '',
    }
  }

  const totalAccDepCalc = computed(() => calcSubtotal(rows.value.map((r) => r.accDepCalc)))
  const totalAccDepBook = computed(() => calcSubtotal(rows.value.map((r) => r.accDepBook)))
  const totalDifference = computed(() => totalAccDepCalc.value - totalAccDepBook.value)

  /** 存在差异的行 */
  const hasDiscrepancy = computed(() => rows.value.some((r) => Math.abs(r.difference) > 0.01))

  function setBranch(b: DepreciationBranch): void {
    branch.value = b
    setValue(BRANCH_ID, b)
    // 切换后重算
    rows.value = rows.value.map((r) => _normalize({ ...r }))
    _persist()
  }

  function addRow(assetName: string): void {
    rows.value.push(_normalize({ assetName, rowId: `dep-${Date.now()}` }))
    _persist()
  }

  function removeRow(index: number): void {
    rows.value.splice(index, 1)
    _persist()
  }

  function updateCell(index: number, field: keyof H3DepreciationRow, value: any): void {
    const row = rows.value[index]
    if (!row) return
    ;(row as any)[field] = typeof value === 'number' ? value : Number(value) || 0
    const recalced = _normalize({ ...row })
    Object.assign(row, recalced)
    _persist()
  }

  /**
   * 行变更：组件已 v-model 就地修改 row（同引用），此处重算折旧公式并持久化。
   * 组件调用 updateRow(index, row)。
   */
  function updateRow(index: number, _row?: any): void {
    const row = rows.value[index]
    if (!row) return
    const recalced = _normalize({ ...row })
    Object.assign(row, recalced)
    _persist()
  }

  function _persist(): void { setValue(ITEM_ID, rows.value) }
  watch(allResponses, () => loadRows(), { immediate: true })

  return {
    branch, rows, totalAccDepCalc, totalAccDepBook, totalDifference, hasDiscrepancy,
    setBranch, addRow, removeRow, updateCell, updateRow, loadRows,
  }
}

export default useH3Depreciation
