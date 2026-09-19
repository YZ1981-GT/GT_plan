/**
 * useJ1GeneralCheck — J1-8 检查表 composable
 *
 * 核心：贷方检查(计提)+借方检查(发放)+期后支付 三区块
 * Source: J1-8 检查表 58行×16列
 *
 * Spec: .kiro/specs/j1-employee-compensation/
 */
import { ref, computed, type Ref } from 'vue'
import { calcSubtotal, parseNum } from './useJ1FormulaEngine'

export interface GeneralCheckRow {
  id: string
  section: 'credit' | 'debit' | 'post_period'  // 贷方/借方/期后
  voucherNo: string        // 凭证号
  date: string             // 日期
  subject: string          // 摘要
  amount: number           // 金额
  counterAccount: string   // 对方科目
  checkResult: string      // 检查结果
  hasAttachment: boolean   // 是否有附件
  ocrContent: string       // OCR内容
}

export function useJ1GeneralCheck(htmlData: Ref<Record<string, unknown>>) {
  const creditRows: Ref<GeneralCheckRow[]> = ref([])
  const debitRows: Ref<GeneralCheckRow[]> = ref([])
  const postPeriodRows: Ref<GeneralCheckRow[]> = ref([])

  function initFromHtmlData(data: Record<string, unknown>) {
    const rawRows = (data.general_check_rows || []) as Array<Record<string, unknown>>
    const allRows = rawRows.map(r => ({
      id: String(r.id || ''),
      section: (r.section || 'credit') as GeneralCheckRow['section'],
      voucherNo: String(r.voucher_no || ''),
      date: String(r.date || ''),
      subject: String(r.subject || ''),
      amount: parseNum(r.amount as number),
      counterAccount: String(r.counter_account || ''),
      checkResult: String(r.check_result || ''),
      hasAttachment: Boolean(r.has_attachment),
      ocrContent: String(r.ocr_content || ''),
    }))
    creditRows.value = allRows.filter(r => r.section === 'credit')
    debitRows.value = allRows.filter(r => r.section === 'debit')
    postPeriodRows.value = allRows.filter(r => r.section === 'post_period')
  }

  const creditTotal = computed(() => calcSubtotal(creditRows.value.map(r => r.amount)))
  const debitTotal = computed(() => calcSubtotal(debitRows.value.map(r => r.amount)))
  const postPeriodTotal = computed(() => calcSubtotal(postPeriodRows.value.map(r => r.amount)))

  return {
    creditRows,
    debitRows,
    postPeriodRows,
    creditTotal,
    debitTotal,
    postPeriodTotal,
    initFromHtmlData,
  }
}
