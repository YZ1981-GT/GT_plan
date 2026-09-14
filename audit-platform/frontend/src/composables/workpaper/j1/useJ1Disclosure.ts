/**
 * useJ1Disclosure — J1 附注披露 composable（上市/国企双版本）
 *
 * Source: 附注披露信息（上市公司）54行×5列 / 附注披露信息（国有企业）44行×5列
 * 列结构：项目 | 上年年末数(期初余额) | 本期增加 | 本期减少 | 期末数(期末余额)
 *
 * Spec: .kiro/specs/j1-employee-compensation/
 */
import { ref, computed, type Ref } from 'vue'
import { calcLiabilityEndBalance, calcSubtotal, parseNum } from './useJ1FormulaEngine'

export type DisclosureMode = 'listed' | 'soe'

export interface DisclosureRow {
  id: string
  label: string
  category: string
  beginBalance: number
  increase: number
  decrease: number
  endBalance: number
  isSubtotal: boolean
}

export function useJ1Disclosure(htmlData: Ref<Record<string, unknown>>, mode: Ref<DisclosureMode>) {
  const rows: Ref<DisclosureRow[]> = ref([])

  function initFromHtmlData(data: Record<string, unknown>) {
    const key = mode.value === 'listed' ? 'disclosure_listed_rows' : 'disclosure_soe_rows'
    const rawRows = (data[key] || []) as Array<Record<string, unknown>>
    rows.value = rawRows.map(r => {
      const beginBalance = parseNum(r.begin_balance as number)
      const increase = parseNum(r.increase as number)
      const decrease = parseNum(r.decrease as number)
      return {
        id: String(r.id || ''),
        label: String(r.label || ''),
        category: String(r.category || ''),
        beginBalance,
        increase,
        decrease,
        endBalance: calcLiabilityEndBalance(beginBalance, increase, decrease),
        isSubtotal: Boolean(r.is_subtotal),
      }
    })
  }

  const totalEnd = computed(() =>
    calcSubtotal(rows.value.filter(r => r.isSubtotal).map(r => r.endBalance)),
  )

  return { rows, totalEnd, initFromHtmlData }
}
