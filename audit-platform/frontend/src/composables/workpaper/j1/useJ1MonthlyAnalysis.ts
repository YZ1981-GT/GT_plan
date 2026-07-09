/**
 * useJ1MonthlyAnalysis — J1-4 月度分析 composable（12列横向矩阵+趋势图）
 *
 * 列结构(16列)：项目 | 1月~12月 | 合计 | 月均 | 波动分析
 * 行结构：短期薪酬小计 + 各明细项 + 合计 + 去年同期行
 *
 * Source: J1-4 月度分析表 B12=SUM(B13:B16) 每月合计
 *
 * Spec: .kiro/specs/j1-employee-compensation/
 * Requirements: 3.4, 3.5
 */
import { ref, computed, type Ref } from 'vue'
import { calcMonthlyTotal, calcMonthlyAverage, calcChangeRate, parseNum } from './useJ1FormulaEngine'

export interface MonthlyRow {
  id: string
  label: string
  category: string
  months: number[]          // 12个月数值
  total: number             // 合计=SUM(12月)
  average: number           // 月均=合计/12
  priorYearTotal: number    // 去年合计
  changeRate: number        // 同比变动率
  isSubtotal: boolean       // 是否小计行
}

export interface MonthlyFluctuation {
  rowId: string
  monthIndex: number        // 0-11
  amount: number
  avgDeviation: number      // 偏离月均的百分比
  isAbnormal: boolean       // 是否异常(偏离>30%)
}

export function useJ1MonthlyAnalysis(htmlData: Ref<Record<string, unknown>>) {
  const rows: Ref<MonthlyRow[]> = ref([])
  const fluctuations: Ref<MonthlyFluctuation[]> = ref([])

  function initFromHtmlData(data: Record<string, unknown>) {
    const rawRows = (data.monthly_rows || []) as Array<Record<string, unknown>>
    rows.value = rawRows.map(r => {
      const months = Array.isArray(r.months)
        ? (r.months as unknown[]).map(v => parseNum(v as number))
        : Array(12).fill(0)
      const total = calcMonthlyTotal(months)
      const average = calcMonthlyAverage(months)
      const priorYearTotal = parseNum(r.prior_year_total as number)
      return {
        id: String(r.id || ''),
        label: String(r.label || ''),
        category: String(r.category || ''),
        months,
        total,
        average,
        priorYearTotal,
        changeRate: calcChangeRate(total, priorYearTotal),
        isSubtotal: Boolean(r.is_subtotal),
      }
    })
    detectFluctuations()
  }

  // ── 波动检测 ──────────────────────────────────────────────────────────────

  function detectFluctuations() {
    const results: MonthlyFluctuation[] = []
    for (const row of rows.value) {
      if (row.isSubtotal || row.average === 0) continue
      for (let i = 0; i < 12; i++) {
        const deviation = ((row.months[i] - row.average) / Math.abs(row.average)) * 100
        if (Math.abs(deviation) > 30) {
          results.push({
            rowId: row.id,
            monthIndex: i,
            amount: row.months[i],
            avgDeviation: deviation,
            isAbnormal: true,
          })
        }
      }
    }
    fluctuations.value = results
  }

  // ── 趋势图数据 ────────────────────────────────────────────────────────────

  const chartData = computed(() => {
    const totalRow = rows.value.find(r => r.isSubtotal && r.category === 'total')
    if (!totalRow) {
      // 用所有非小计行合计
      const months = Array(12).fill(0)
      rows.value
        .filter(r => !r.isSubtotal)
        .forEach(r => r.months.forEach((v, i) => { months[i] += v }))
      return months
    }
    return totalRow.months
  })

  const hasAbnormalFluctuation = computed(() => fluctuations.value.length > 0)

  return {
    rows,
    fluctuations,
    chartData,
    hasAbnormalFluctuation,
    initFromHtmlData,
  }
}
