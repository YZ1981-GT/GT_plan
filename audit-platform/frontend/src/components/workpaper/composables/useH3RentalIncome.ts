/**
 * useH3RentalIncome — H3-14 租金收入测算 composable
 *
 * 三区域（合同汇总/月度12列/到期管理）+ 27公式
 * + 空置率 + 到期预警 + 交叉验证收入
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.18
 * Requirements: 14.1-14.8
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'
import {
  calcRentalIncome,
  calcRentalYield,
  calcVacancyLoss,
  calcPerSqmRent,
  calcSubtotal,
} from './useH3FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface RentalContractRow {
  rowId: string
  assetName: string
  tenant: string
  contractPeriod: string      // 合同期(yyyy-mm ~ yyyy-mm)
  monthlyRent: number         // 月租
  annualRent: number          // 年租金（公式）
  area: number                // 面积
  perSqmRent: number | null   // 每平米租金
  bookValue: number           // 账面原值
  rentalYield: number | null  // 租金回报率
}

export interface MonthlyRentalRow {
  rowId: string
  assetName: string
  months: number[]            // 12个月收入
  totalActual: number         // 实际合计
  totalCalc: number           // 测算合计（月租×12）
  diff: number                // 差异
  diffRate: number            // 差异率%
}

export interface ExpiryRow {
  rowId: string
  assetName: string
  tenant: string
  expiryDate: string          // 合同到期日
  monthsToExpiry: number      // 到期月数（公式）
  renewalStatus: string       // 续租状态
  vacancyForecast: number     // 空置预测月数
}

const ITEM_CONTRACT = 'H3-14-contract-rows'
const ITEM_MONTHLY = 'H3-14-monthly-rows'
const ITEM_EXPIRY = 'H3-14-expiry-rows'

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
  const monthlyRows = ref<MonthlyRentalRow[]>([])
  const expiryRows = ref<ExpiryRow[]>([])

  function loadData(): void {
    const rawC = getValue(ITEM_CONTRACT)
    contractRows.value = Array.isArray(rawC) ? rawC.map(_normContract) : []
    const rawM = getValue(ITEM_MONTHLY)
    monthlyRows.value = Array.isArray(rawM) ? rawM.map(_normMonthly) : []
    const rawE = getValue(ITEM_EXPIRY)
    expiryRows.value = Array.isArray(rawE) ? rawE.map(_normExpiry) : []
  }

  function _normContract(raw: any): RentalContractRow {
    const monthly = Number(raw.monthlyRent) || 0
    const area = Number(raw.area) || 0
    const book = Number(raw.bookValue) || 0
    const annual = monthly * 12
    return {
      rowId: raw.rowId ?? `rc-${Math.random().toString(36).slice(2, 8)}`,
      assetName: raw.assetName ?? '',
      tenant: raw.tenant ?? '',
      contractPeriod: raw.contractPeriod ?? '',
      monthlyRent: monthly,
      annualRent: annual,
      area,
      perSqmRent: calcPerSqmRent(monthly, area),
      bookValue: book,
      rentalYield: calcRentalYield(annual, book),
    }
  }

  function _normMonthly(raw: any): MonthlyRentalRow {
    const months: number[] = Array.isArray(raw.months)
      ? raw.months.map((m: any) => Number(m) || 0)
      : Array(12).fill(0)
    const totalActual = calcSubtotal(months)
    const monthlyRent = Number(raw.monthlyRent) || (totalActual / 12)
    const totalCalc = monthlyRent * 12
    const diff = totalActual - totalCalc
    return {
      rowId: raw.rowId ?? `rm-${Math.random().toString(36).slice(2, 8)}`,
      assetName: raw.assetName ?? '',
      months,
      totalActual,
      totalCalc,
      diff,
      diffRate: totalCalc !== 0 ? (diff / totalCalc) * 100 : 0,
    }
  }

  function _normExpiry(raw: any): ExpiryRow {
    const expiry = raw.expiryDate ?? ''
    let monthsToExpiry = 0
    if (expiry) {
      const expiryTime = new Date(expiry).getTime()
      const now = Date.now()
      monthsToExpiry = Math.max(0, Math.round((expiryTime - now) / (30 * 24 * 3600 * 1000)))
    }
    return {
      rowId: raw.rowId ?? `re-${Math.random().toString(36).slice(2, 8)}`,
      assetName: raw.assetName ?? '',
      tenant: raw.tenant ?? '',
      expiryDate: expiry,
      monthsToExpiry,
      renewalStatus: raw.renewalStatus ?? '',
      vacancyForecast: Number(raw.vacancyForecast) || 0,
    }
  }

  /** 合同汇总统计 */
  const contractSummary = computed(() => ({
    totalAnnualRent: calcSubtotal(contractRows.value.map((r) => r.annualRent)),
    assetCount: contractRows.value.length,
    avgPerSqm: contractRows.value.length > 0
      ? calcSubtotal(contractRows.value.map((r) => r.perSqmRent ?? 0)) / contractRows.value.length
      : 0,
  }))

  /** 差异>5%的月度行（黄色高亮） */
  const monthlyDiffAlerts = computed(() => monthlyRows.value.filter((r) => Math.abs(r.diffRate) > 5))
  /** 到期月数≤3的行（橙色高亮） */
  const expiryAlerts = computed(() => expiryRows.value.filter((r) => r.monthsToExpiry <= 3))

  /** 空置率（基于到期管理区空置预测） */
  const vacancyRate = computed(() => {
    const totalMonths = expiryRows.value.length * 12
    const vacantMonths = calcSubtotal(expiryRows.value.map((r) => r.vacancyForecast))
    return totalMonths > 0 ? vacantMonths / totalMonths : 0
  })

  function addContractRow(assetName: string): void {
    contractRows.value.push(_normContract({ assetName, rowId: `rc-${Date.now()}` }))
    setValue(ITEM_CONTRACT, contractRows.value)
  }

  function removeContractRow(index: number): void {
    contractRows.value.splice(index, 1)
    setValue(ITEM_CONTRACT, contractRows.value)
  }

  function updateContractCell(index: number, field: keyof RentalContractRow, value: any): void {
    const row = contractRows.value[index]
    if (!row) return
    ;(row as any)[field] = typeof value === 'number' ? value : (Number(value) || value)
    const recalced = _normContract({ ...row })
    Object.assign(row, recalced)
    setValue(ITEM_CONTRACT, contractRows.value)
  }

  function updateMonthlyCell(index: number, monthIdx: number, value: number): void {
    const row = monthlyRows.value[index]
    if (!row) return
    row.months[monthIdx] = value
    const recalced = _normMonthly({ ...row })
    Object.assign(row, recalced)
    setValue(ITEM_MONTHLY, monthlyRows.value)
  }

  watch(allResponses, () => loadData(), { immediate: true })

  return {
    contractRows, monthlyRows, expiryRows,
    contractSummary, monthlyDiffAlerts, expiryAlerts, vacancyRate,
    addContractRow, removeContractRow, updateContractCell, updateMonthlyCell, loadData,
  }
}

export default useH3RentalIncome
