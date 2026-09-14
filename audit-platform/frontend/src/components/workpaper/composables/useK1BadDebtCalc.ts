/**
 * useK1BadDebtCalc — K1-8 坏账准备测算
 *
 * Spec: .kiro/specs/k1-other-receivables/
 * Task: 3.4
 * Requirements: 6.1-6.6
 *
 * 职责：
 * - 2区段Tab: 账龄迁徙/ECL测算
 * - 62行 × 19列 × 11公式
 * - ECL=EAD×PD×LGD + 差异=测算-账面
 * - 差异>重要性红色标记
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { calcECL, calcAgingLoss, calcProvisionVariance } from './useK1BadDebtCalcEngine'
import { calcSubtotal } from './useK1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 账龄迁徙区段行 */
export interface K1AgingMigrationRow {
  id: string
  agingBucket: string        // 账龄区间名称
  endBalance: number         // 期末余额
  migrationRate: number      // 迁徙率(0~1)
  expectedLossRate: number   // 预期损失率(0~1)
  expectedLoss: number       // 预期损失（公式）
}

/** ECL测算区段行 */
export interface K1ECLCalcRow {
  id: string
  counterparty: string       // 往来对象
  ead: number                // 违约风险暴露
  pd: number                 // 违约概率(0~1)
  lgd: number                // 违约损失率(0~1)
  ecl: number                // ECL=EAD×PD×LGD（公式）
  bookedProvision: number    // 企业计提
  variance: number           // 差异=测算-企业计提（公式）
  conclusion: string         // 测算结论
}

export interface K1CalcTotals {
  totalECL: number
  totalBooked: number
  totalVariance: number
}

export interface UseK1BadDebtCalcOpts {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK1BadDebtCalc(opts: UseK1BadDebtCalcOpts) {
  const { allResponses } = opts

  const agingRows = ref<K1AgingMigrationRow[]>([])
  const eclRows = ref<K1ECLCalcRow[]>([])
  const materialityLevel = ref<number>(0)

  // ─── 加载 ──────────────────────────────────────────────────────────────────

  function loadData(): void {
    // 账龄迁徙行
    const agingRaw = allResponses.value.get('K1-8-aging-rows')?.remark
    if (agingRaw) {
      try {
        const parsed = JSON.parse(agingRaw)
        agingRows.value = Array.isArray(parsed) ? parsed.map(recalcAgingRow) : []
      } catch { agingRows.value = [] }
    }
    // ECL测算行
    const eclRaw = allResponses.value.get('K1-8-ecl-rows')?.remark
    if (eclRaw) {
      try {
        const parsed = JSON.parse(eclRaw)
        eclRows.value = Array.isArray(parsed) ? parsed.map(recalcEclRow) : []
      } catch { eclRows.value = [] }
    }
    // 重要性水平
    const mat = allResponses.value.get('K1-8-materiality')?.remark
    materialityLevel.value = Number(mat) || 0
  }

  // ─── 公式重算 ─────────────────────────────────────────────────────────────

  function recalcAgingRow(row: K1AgingMigrationRow): K1AgingMigrationRow {
    row.expectedLoss = calcAgingLoss(row.endBalance, row.expectedLossRate)
    return row
  }

  function recalcEclRow(row: K1ECLCalcRow): K1ECLCalcRow {
    row.ecl = calcECL(row.ead, row.pd, row.lgd)
    row.variance = calcProvisionVariance(row.ecl, row.bookedProvision)
    return row
  }

  // ─── 行更新 ────────────────────────────────────────────────────────────────

  function updateAgingRow(id: string, field: keyof K1AgingMigrationRow, value: any): void {
    const row = agingRows.value.find(r => r.id === id)
    if (!row) return
    ;(row as any)[field] = value
    row.expectedLoss = calcAgingLoss(row.endBalance, row.expectedLossRate)
  }

  function updateEclRow(id: string, field: keyof K1ECLCalcRow, value: any): void {
    const row = eclRows.value.find(r => r.id === id)
    if (!row) return
    ;(row as any)[field] = value
    row.ecl = calcECL(row.ead, row.pd, row.lgd)
    row.variance = calcProvisionVariance(row.ecl, row.bookedProvision)
  }

  // ─── 合计 ──────────────────────────────────────────────────────────────────

  const totals: ComputedRef<K1CalcTotals> = computed(() => {
    const totalECL = calcSubtotal(eclRows.value.map(r => r.ecl))
    const totalBooked = calcSubtotal(eclRows.value.map(r => r.bookedProvision))
    const totalVariance = calcProvisionVariance(totalECL, totalBooked)
    return { totalECL, totalBooked, totalVariance }
  })

  // ─── 差异>重要性标记 ───────────────────────────────────────────────────────

  function isVarianceExceedsMateriality(row: K1ECLCalcRow): boolean {
    return materialityLevel.value > 0 && Math.abs(row.variance) > materialityLevel.value
  }

  const hasExceedingVariance: ComputedRef<boolean> = computed(() =>
    eclRows.value.some(r => isVarianceExceedsMateriality(r))
  )

  // ─── 序列化 ────────────────────────────────────────────────────────────────

  function serializeData(): { aging: string; ecl: string } {
    return {
      aging: JSON.stringify(agingRows.value),
      ecl: JSON.stringify(eclRows.value),
    }
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    agingRows,
    eclRows,
    materialityLevel,
    totals,
    hasExceedingVariance,
    loadData,
    updateAgingRow,
    updateEclRow,
    isVarianceExceedsMateriality,
    serializeData,
  }
}
