/**
 * useH3RentalIncome — H3-14 租金收入测算 composable
 *
 * 单一 contractRows 行模型贯穿三区域（合同汇总 / 月度12列 / 到期管理），
 * 字段命名与 H3TabRentalIncome.vue 模板保持一致：
 *   assetName/tenant/leaseStart/leaseEnd/monthlyRent/area/monthlyActual[12]/renewalStatus/vacancyForecast/monthsToExpiry
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.18
 * Requirements: 14.1-14.8
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'
import { calcSubtotal } from './useH3FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface RentalContractRow {
  rowId: string
  assetName: string
  tenant: string
  leaseStart: string
  leaseEnd: string
  monthlyRent: number
  area: number
  monthlyActual: number[]     // 12个月实际收入
  renewalStatus: string       // 续租状态
  vacancyForecast: string     // 空置预测
  monthsToExpiry: number | null // 到期月数（公式，基于 leaseEnd）
}

const ITEM_CONTRACT = 'H3-14-contract-rows'

export function useH3RentalIncome(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
}) {
  const { allResponses, getValue, setValue } = params

  const contractRows = ref<RentalContractRow[]>([])

  function loadData(): void {
    const raw = getValue(ITEM_CONTRACT)
    contractRows.value = Array.isArray(raw) ? raw.map(_normContract) : []
  }

  function _monthsToExpiry(leaseEnd: string): number | null {
    if (!leaseEnd) return null
    const t = new Date(leaseEnd).getTime()
    if (Number.isNaN(t)) return null
    return Math.max(0, Math.round((t - Date.now()) / (30 * 24 * 3600 * 1000)))
  }

  function _normContract(raw: any): RentalContractRow {
    const monthlyActual: number[] = Array.isArray(raw?.monthlyActual)
      ? raw.monthlyActual.slice(0, 12).map((m: any) => Number(m) || 0)
      : Array(12).fill(0)
    while (monthlyActual.length < 12) monthlyActual.push(0)
    const leaseEnd = raw?.leaseEnd ?? ''
    return {
      rowId: raw?.rowId ?? `rc-${Math.random().toString(36).slice(2, 8)}`,
      assetName: raw?.assetName ?? '',
      tenant: raw?.tenant ?? '',
      leaseStart: raw?.leaseStart ?? '',
      leaseEnd,
      monthlyRent: Number(raw?.monthlyRent) || 0,
      area: Number(raw?.area) || 0,
      monthlyActual,
      renewalStatus: raw?.renewalStatus ?? '',
      vacancyForecast: raw?.vacancyForecast ?? '',
      monthsToExpiry: _monthsToExpiry(leaseEnd),
    }
  }

  // ─── 汇总统计 ────────────────────────────────────────────────────────────────
  const contractSummary = computed(() => ({
    totalAnnualRent: calcSubtotal(contractRows.value.map((r) => (Number(r.monthlyRent) || 0) * 12)),
    assetCount: contractRows.value.length,
  }))

  /** 到期月数≤3的行（橙色高亮） */
  const expiryAlerts = computed(() =>
    contractRows.value.filter((r) => r.monthsToExpiry != null && r.monthsToExpiry <= 3),
  )

  // ─── 操作 ──────────────────────────────────────────────────────────────────────
  function addContractRow(assetName?: string): void {
    contractRows.value.push(_normContract({ assetName: assetName ?? '', rowId: `rc-${Date.now()}` }))
    _persist()
  }

  function removeContractRow(index: number): void {
    contractRows.value.splice(index, 1)
    _persist()
  }

  /** 合同行变更：重算到期月数并持久化（组件调用 updateContractRow(index, row)） */
  function updateContractRow(index: number, _row?: any): void {
    const row = contractRows.value[index]
    if (!row) return
    row.monthlyRent = Number(row.monthlyRent) || 0
    row.area = Number(row.area) || 0
    row.monthsToExpiry = _monthsToExpiry(row.leaseEnd)
    _persist()
  }

  /** 月度数据变更：持久化（组件已 v-model 就地修改 monthlyActual[]） */
  function updateMonthlyData(index: number, _row?: any): void {
    const row = contractRows.value[index]
    if (!row) return
    row.monthlyActual = row.monthlyActual.map((m) => Number(m) || 0)
    _persist()
  }

  function _persist(): void { setValue(ITEM_CONTRACT, contractRows.value) }
  watch(allResponses, () => loadData(), { immediate: true })

  return {
    contractRows,
    contractSummary, expiryAlerts,
    addContractRow, removeContractRow, updateContractRow, updateMonthlyData, loadData,
  }
}

export default useH3RentalIncome
