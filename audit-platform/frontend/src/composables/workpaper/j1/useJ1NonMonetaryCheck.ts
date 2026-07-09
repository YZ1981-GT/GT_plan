/**
 * useJ1NonMonetaryCheck — J1-9 非货币性福利检查表 composable
 *
 * 核心：非货币性福利的形式、来源、计量方式检查
 * Source: J1-9 非货币性福利检查表 29行×13列
 *
 * Spec: .kiro/specs/j1-employee-compensation/
 */
import { ref, computed, type Ref } from 'vue'
import { calcSubtotal, parseNum } from './useJ1FormulaEngine'

export interface NonMonetaryRow {
  id: string
  benefitType: string       // 福利形式（房屋/汽车/商品/服务等）
  source: string           // 实物来源
  measureMethod: string    // 计量方式（公允/成本/评估）
  amount: number           // 金额
  voucherNo: string        // 凭证号
  employeeCount: number    // 受益人数
  checkResult: string      // 检查结论
  isCompliant: boolean     // 是否合规
}

export function useJ1NonMonetaryCheck(htmlData: Ref<Record<string, unknown>>) {
  const rows: Ref<NonMonetaryRow[]> = ref([])

  function initFromHtmlData(data: Record<string, unknown>) {
    const rawRows = (data.non_monetary_rows || []) as Array<Record<string, unknown>>
    rows.value = rawRows.map(r => ({
      id: String(r.id || ''),
      benefitType: String(r.benefit_type || ''),
      source: String(r.source || ''),
      measureMethod: String(r.measure_method || ''),
      amount: parseNum(r.amount as number),
      voucherNo: String(r.voucher_no || ''),
      employeeCount: parseNum(r.employee_count as number),
      checkResult: String(r.check_result || ''),
      isCompliant: r.is_compliant !== false,
    }))
  }

  const totalAmount = computed(() => calcSubtotal(rows.value.map(r => r.amount)))
  const hasNonCompliant = computed(() => rows.value.some(r => !r.isCompliant))

  return { rows, totalAmount, hasNonCompliant, initFromHtmlData }
}
