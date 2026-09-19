/**
 * useJ1AccrualCheck — J1-6 计提情况检查表 composable
 *
 * 核心：人数×均薪测算 vs 实际计提 → 差异率判断合理性
 * Source: J1-6 计提情况检查表 60行×11列
 *
 * Spec: .kiro/specs/j1-employee-compensation/
 * Requirements: 4.6, 5.2-5.4
 */
import { ref, computed, type Ref } from 'vue'
import { parseNum } from './useJ1FormulaEngine'
import {
  calcSalaryEstimate,
  calcInsuranceEstimate,
  calcHousingFundEstimate,
  calcAccrualDiffRate,
} from './useJ1SalaryCalc'

export interface AccrualCheckRow {
  id: string
  category: string          // 工资/社保/公积金/福利费等
  headcount: number         // 人数
  base: number             // 基数（均薪/缴费基数）
  rate: number             // 比例（社保/公积金）
  months: number           // 月数
  estimated: number        // 应提=基数×比例×月数 或 人数×均薪×月数
  actual: number           // 实提
  diffRate: number | null  // 差异率
  isAbnormal: boolean      // 差异率>5%
  note: string             // 说明
}

export function useJ1AccrualCheck(htmlData: Ref<Record<string, unknown>>) {
  const rows: Ref<AccrualCheckRow[]> = ref([])

  function initFromHtmlData(data: Record<string, unknown>) {
    const rawRows = (data.accrual_check_rows || []) as Array<Record<string, unknown>>
    rows.value = rawRows.map(r => {
      const category = String(r.category || '')
      const headcount = parseNum(r.headcount as number)
      const base = parseNum(r.base as number)
      const rate = parseNum(r.rate as number)
      const months = parseNum(r.months as number) || 12
      const actual = parseNum(r.actual as number)

      // 根据类别选择测算方法
      let estimated: number
      if (category === '工资' || category.includes('薪') || category.includes('奖金')) {
        estimated = calcSalaryEstimate(headcount, base, months)
      } else if (category.includes('公积金')) {
        estimated = calcHousingFundEstimate(base, rate, months)
      } else {
        estimated = calcInsuranceEstimate(base, rate, months)
      }

      const diffRate = calcAccrualDiffRate(actual, estimated)

      return {
        id: String(r.id || ''),
        category,
        headcount,
        base,
        rate,
        months,
        estimated,
        actual,
        diffRate,
        isAbnormal: diffRate !== null && Math.abs(diffRate) > 5,
        note: String(r.note || ''),
      }
    })
  }

  const totalEstimated = computed(() => rows.value.reduce((s, r) => s + r.estimated, 0))
  const totalActual = computed(() => rows.value.reduce((s, r) => s + r.actual, 0))
  const overallDiffRate = computed(() => calcAccrualDiffRate(totalActual.value, totalEstimated.value))
  const hasAbnormal = computed(() => rows.value.some(r => r.isAbnormal))

  return { rows, totalEstimated, totalActual, overallDiffRate, hasAbnormal, initFromHtmlData }
}
