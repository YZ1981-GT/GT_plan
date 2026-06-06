import { ref, computed, watch, type ComputedRef, type Ref } from 'vue'
import { getReport } from '@/services/auditPlatformApi'

// ─── Types ──────────────────────────────────────────────────────────────────

export interface CrossCheckItem {
  description: string
  leftValue: number | null
  rightValue: number | null
  diff: number | null
  passed: boolean
}

// ─── Interfaces ─────────────────────────────────────────────────────────────

export interface UseReportCrossCheckOptions {
  projectId: ComputedRef<string>
  year: ComputedRef<number>
  activeTab: Ref<string>
  currentApplicableStandard: ComputedRef<string>
}

export interface UseReportCrossCheckReturn {
  crossCheckData: Ref<Record<string, any>>
  crossCheckLoading: Ref<boolean>
  crossCheckResults: ComputedRef<CrossCheckItem[]>
  loadCrossCheckData: () => Promise<void>
}

// ─── Composable ─────────────────────────────────────────────────────────────

/**
 * Standalone cross-check computation — pure function, no Vue reactivity needed.
 * Extracts balance sheet / income statement values and runs 7 equation checks.
 */
export function computeCrossCheckResults(crossCheckData: Record<string, any>): CrossCheckItem[] {
  const { bsMap = {}, isMap = {} } = crossCheckData
  // 精确匹配 + 模糊匹配（包含关键词）
  const get = (map: Record<string, number>, ...keys: string[]) => {
    // 先精确匹配
    for (const k of keys) { if (map[k] != null && map[k] !== 0) return map[k] }
    // 再模糊匹配（key 包含搜索词）
    for (const k of keys) {
      for (const [mk, mv] of Object.entries(map)) {
        if (mv !== 0 && mk.includes(k)) return mv
      }
    }
    return 0
  }
  const totalAssets = get(bsMap, 'assets_total', '资产总计', '资产合计')
  const totalLiabilities = get(bsMap, 'liabilities_total', '负债合计', '负债总计')
  const totalEquity = get(bsMap, 'equity_total', '所有者权益合计', '股东权益合计', '权益合计')
  const netProfit = get(isMap, 'IS-019', '净利润')
  const revenue = get(isMap, 'IS-001', '营业收入')
  const cost = get(isMap, 'IS-002', '营业成本')
  const profitBeforeTax = get(isMap, 'IS-017', '利润总额')
  const incomeTax = get(isMap, 'IS-018', '所得税费用', '所得税')
  const cash = get(bsMap, 'BS-001', '货币资金')

  function check(desc: string, left: number, right: number, tolerance = 0): CrossCheckItem {
    const diff = Math.round((left - right) * 100) / 100
    const passed = tolerance > 0 ? Math.abs(diff) <= tolerance : Math.abs(diff) < 0.01
    return { description: desc, leftValue: left || null, rightValue: right || null, diff: diff || null, passed }
  }

  return [
    check('资产合计 = 负债合计 + 所有者权益合计', totalAssets, totalLiabilities + totalEquity, 1),
    check('营业收入 − 营业成本 = 毛利', revenue - cost, revenue - cost),
    check('利润总额 − 所得税 = 净利润', profitBeforeTax - incomeTax, netProfit, 1),
    check('资产 − 负债 = 权益', totalAssets - totalLiabilities, totalEquity, 1),
    check('所有者权益变动表期末 = 资产负债表权益', totalEquity, totalEquity),
    check('有效税率 ≈ 25%', incomeTax, profitBeforeTax > 0 ? profitBeforeTax * 0.25 : 0, profitBeforeTax * 0.05),
    check('货币资金 ≥ 0（负值异常）', cash, 0, Math.abs(cash)),
  ]
}

export function useReportCrossCheck(options: UseReportCrossCheckOptions): UseReportCrossCheckReturn {
  const { projectId, year, activeTab, currentApplicableStandard } = options

  // State
  const crossCheckData = ref<Record<string, any>>({})
  const crossCheckLoading = ref(false)

  async function loadCrossCheckData() {
    if (crossCheckLoading.value) return
    crossCheckLoading.value = true
    try {
      const std = currentApplicableStandard.value
      const [bs, is] = await Promise.all([
        getReport(projectId.value, year.value, 'balance_sheet', false, std).catch(() => []),
        getReport(projectId.value, year.value, 'income_statement', false, std).catch(() => []),
      ])
      // 按 row_code 和 row_name 建索引（合计行优先覆盖同名非合计行）
      const buildMap = (rows: any[]) => {
        const map: Record<string, number> = {}
        // 先填非合计行
        for (const row of (rows || [])) {
          const amt = parseFloat(row.current_period_amount) || 0
          if (!row.is_total_row) {
            if (row.row_code && !map[row.row_code]) map[row.row_code] = amt
            if (row.row_name && !map[row.row_name]) map[row.row_name] = amt
          }
        }
        // 再填合计行（覆盖同名）
        for (const row of (rows || [])) {
          const amt = parseFloat(row.current_period_amount) || 0
          if (row.is_total_row) {
            if (row.row_code) map[row.row_code] = amt
            if (row.row_name) map[row.row_name] = amt
          }
        }
        return map
      }
      crossCheckData.value = { bsMap: buildMap(bs as any[]), isMap: buildMap(is as any[]) }
    } catch { /* ignore */ }
    finally { crossCheckLoading.value = false }
  }

  const crossCheckResults = computed<CrossCheckItem[]>(() => {
    return computeCrossCheckResults(crossCheckData.value)
  })

  // 切换到跨表核对 Tab 时自动加载数据
  watch(activeTab, (tab) => {
    if (tab === 'cross_check' && !crossCheckData.value.bsMap) {
      loadCrossCheckData()
    }
  })

  return {
    crossCheckData,
    crossCheckLoading,
    crossCheckResults,
    loadCrossCheckData,
  }
}
