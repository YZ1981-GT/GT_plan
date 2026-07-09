/**
 * useJ1IndustryCompare — J1-5 同行业对比分析 composable
 *
 * 对比维度：人均薪酬/薪酬占收入比/各险种费率/人均公积金
 * Source: J1-5 与同行业对比分析表
 *
 * Spec: .kiro/specs/j1-employee-compensation/
 * Requirements: 5.2-5.4
 */
import { ref, computed, type Ref } from 'vue'
import { calcIndustryDiffRate, parseNum } from './useJ1FormulaEngine'
import { calcPerCapitaSalary, calcSalaryRevenueRatio } from './useJ1SalaryCalc'

export interface IndustryCompareRow {
  id: string
  metric: string              // 指标名称
  companyValue: number        // 公司值
  industryAvg: number         // 行业均值
  industryMin: number         // 行业最小值
  industryMax: number         // 行业最大值
  diffRate: number | null     // 差异率(%)
  isAbnormal: boolean         // 超出正常范围
}

export function useJ1IndustryCompare(htmlData: Ref<Record<string, unknown>>) {
  const rows: Ref<IndustryCompareRow[]> = ref([])
  const companyInfo = ref({ headcount: 0, totalSalary: 0, revenue: 0 })

  function initFromHtmlData(data: Record<string, unknown>) {
    // 公司基础数据
    const info = data.company_info as Record<string, unknown> | undefined
    if (info) {
      companyInfo.value = {
        headcount: parseNum(info.headcount as number),
        totalSalary: parseNum(info.total_salary as number),
        revenue: parseNum(info.revenue as number),
      }
    }

    const rawRows = (data.industry_compare_rows || []) as Array<Record<string, unknown>>
    rows.value = rawRows.map(r => {
      const companyValue = parseNum(r.company_value as number)
      const industryAvg = parseNum(r.industry_avg as number)
      const industryMin = parseNum(r.industry_min as number)
      const industryMax = parseNum(r.industry_max as number)
      const diffRate = calcIndustryDiffRate(companyValue, industryAvg)
      return {
        id: String(r.id || ''),
        metric: String(r.metric || ''),
        companyValue,
        industryAvg,
        industryMin,
        industryMax,
        diffRate,
        isAbnormal: diffRate !== null && Math.abs(diffRate) > 30,
      }
    })
  }

  const perCapita = computed(() =>
    calcPerCapitaSalary(companyInfo.value.totalSalary, companyInfo.value.headcount),
  )

  const revenueRatio = computed(() =>
    calcSalaryRevenueRatio(companyInfo.value.totalSalary, companyInfo.value.revenue),
  )

  const hasAbnormal = computed(() => rows.value.some(r => r.isAbnormal))

  return { rows, companyInfo, perCapita, revenueRatio, hasAbnormal, initFromHtmlData }
}
