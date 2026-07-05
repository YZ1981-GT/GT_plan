/**
 * useG4EclVoucherCheck — G4-13 凭证检查表 composable
 *
 * Spec: .kiro/specs/g4-bond-investment-ecl/
 * Task: 9.2
 *
 * 职责：
 * - 借贷平衡实时校验（调用 isDebitCreditBalanced + calcDebitCreditDifference）
 * - 凭证异常判定（调用 isVoucherNormal）
 * - 抽凭结果填入逻辑（fillVoucherSamples）
 * - 行CRUD（addRow / removeRow 含 ElMessageBox.prompt）
 * - 数据持久化（loadRows / toJSON）
 *
 * Requirements: 6.6, 6.7
 */
import { ref, computed } from 'vue'
import {
  isDebitCreditBalanced,
  calcDebitCreditDifference,
  isVoucherNormal,
  calcSumColumn,
} from '@/composables/useG4EclFormulaEngine'
import { ElMessageBox } from 'element-plus'
import type { VoucherCheckRow } from './useG4EclFormData'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG4EclVoucherCheck() {
  const rows = ref<VoucherCheckRow[]>([])
  const activeTab = ref<'tab1' | 'tab2' | 'tab3'>('tab1')
  const activeRowIndex = ref(0)

  // ─── 借方/贷方分区（computed） ────────────────────────────────────────────

  /** 借方区行 */
  const debitRows = computed(() => rows.value.filter(r => r.section === 'debit'))

  /** 贷方区行 */
  const creditRows = computed(() => rows.value.filter(r => r.section === 'credit'))

  // ─── 借贷平衡校验（Requirements: 6.6） ────────────────────────────────────

  /** 借方金额合计 */
  const debitTotal = computed(() =>
    calcSumColumn(debitRows.value.map(r => r.debitAmount))
  )

  /** 贷方金额合计 */
  const creditTotal = computed(() =>
    calcSumColumn(creditRows.value.map(r => r.creditAmount))
  )

  /** 借贷差额 */
  const difference = computed(() =>
    calcDebitCreditDifference(
      debitRows.value.map(r => r.debitAmount),
      creditRows.value.map(r => r.creditAmount)
    )
  )

  /** 是否平衡 */
  const isBalanced = computed(() =>
    isDebitCreditBalanced(
      debitRows.value.map(r => r.debitAmount),
      creditRows.value.map(r => r.creditAmount)
    )
  )

  // ─── 凭证异常判定（Requirements: 6.7） ────────────────────────────────────

  /**
   * 重新计算某行的异常状态：
   * 6项核对任一 false → isAbnormal = true
   */
  function recalcAbnormal(row: VoucherCheckRow): void {
    const checks = [
      row.checkOriginalComplete,
      row.checkAuthorized,
      row.checkAccountingCorrect,
      row.checkInitialCostCorrect,
      row.checkInterestCorrect,
      row.checkImpairmentCorrect,
    ]
    row.isAbnormal = !isVoucherNormal(checks)
  }

  /**
   * 判断某行是否全部核对通过
   */
  function isAllChecked(row: VoucherCheckRow): boolean {
    return isVoucherNormal([
      row.checkOriginalComplete,
      row.checkAuthorized,
      row.checkAccountingCorrect,
      row.checkInitialCostCorrect,
      row.checkInterestCorrect,
      row.checkImpairmentCorrect,
    ])
  }

  // ─── 抽凭结果填入（Requirements: 6.3） ────────────────────────────────────

  /**
   * 从抽凭引擎结果批量填入行
   * samples: 抽样引擎返回的样本列表
   */
  function fillVoucherSamples(samples: Array<{
    voucherNo: string
    date?: string
    businessContent?: string
    counterAccount?: string
    detailAccount?: string
    debitAmount?: number
    creditAmount?: number
    section?: 'debit' | 'credit'
  }>): void {
    for (const sample of samples) {
      const section = sample.section ?? (sample.debitAmount ? 'debit' : 'credit')
      const sectionRows = rows.value.filter(r => r.section === section)
      const newRow: VoucherCheckRow = {
        id: crypto.randomUUID(),
        seq: sectionRows.length + 1,
        section,
        date: sample.date ?? '',
        voucherNo: sample.voucherNo,
        businessContent: sample.businessContent ?? '',
        counterAccount: sample.counterAccount ?? '',
        detailAccount: sample.detailAccount ?? '',
        debitAmount: sample.debitAmount ?? 0,
        creditAmount: sample.creditAmount ?? 0,
        attachment: null,
        supportingDocDesc: '',
        checkOriginalComplete: false,
        checkAuthorized: false,
        checkAccountingCorrect: false,
        checkInitialCostCorrect: false,
        checkInterestCorrect: false,
        checkImpairmentCorrect: false,
        indexRef: '',
        isAbnormal: true, // 未核对前默认异常
        abnormalNote: '',
        remark: '',
      }
      rows.value.push(newRow)
    }
    // 重新排序
    _resequence()
  }

  // ─── 行 CRUD（Requirements: 6.10） ────────────────────────────────────────

  /**
   * 新增行（ElMessageBox.prompt输入凭证编号）
   */
  async function addRow(section: 'debit' | 'credit', defaultVoucherNo?: string): Promise<void> {
    let voucherNo = defaultVoucherNo
    if (!voucherNo) {
      const { value } = await ElMessageBox.prompt('请输入凭证编号', '新增凭证行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputValidator: (v) => (v?.trim() ? true : '凭证编号不能为空'),
      })
      if (!value?.trim()) return
      voucherNo = value.trim()
    }

    const sectionRows = rows.value.filter(r => r.section === section)
    const newRow: VoucherCheckRow = {
      id: crypto.randomUUID(),
      seq: sectionRows.length + 1,
      section,
      date: '',
      voucherNo: voucherNo!,
      businessContent: '',
      counterAccount: '',
      detailAccount: '',
      debitAmount: 0,
      creditAmount: 0,
      attachment: null,
      supportingDocDesc: '',
      checkOriginalComplete: false,
      checkAuthorized: false,
      checkAccountingCorrect: false,
      checkInitialCostCorrect: false,
      checkInterestCorrect: false,
      checkImpairmentCorrect: false,
      indexRef: '',
      isAbnormal: true,
      abnormalNote: '',
      remark: '',
    }
    rows.value.push(newRow)
    _resequence()
  }

  /**
   * 删除行
   */
  function removeRow(id: string): void {
    rows.value = rows.value.filter(r => r.id !== id)
    _resequence()
  }

  /** 内部：按section重新编号 */
  function _resequence(): void {
    let debitSeq = 0
    let creditSeq = 0
    for (const row of rows.value) {
      if (row.section === 'debit') {
        row.seq = ++debitSeq
      } else {
        row.seq = ++creditSeq
      }
    }
  }

  // ─── 数据持久化 ───────────────────────────────────────────────────────────

  /**
   * 加载行数据
   */
  function loadRows(data: VoucherCheckRow[]): void {
    rows.value = (data || []).map((r, i) => ({
      ...r,
      id: r.id || crypto.randomUUID(),
    }))
    _resequence()
  }

  /**
   * 导出为 JSON
   */
  function toJSON(): {
    rows: VoucherCheckRow[]
    debitTotal: number
    creditTotal: number
    difference: number
    isBalanced: boolean
  } {
    return {
      rows: rows.value.map(r => ({ ...r })),
      debitTotal: debitTotal.value,
      creditTotal: creditTotal.value,
      difference: difference.value,
      isBalanced: isBalanced.value,
    }
  }

  return {
    // State
    rows,
    activeTab,
    activeRowIndex,
    // Computed - 分区
    debitRows,
    creditRows,
    // Computed - 借贷平衡
    debitTotal,
    creditTotal,
    difference,
    isBalanced,
    // Validation
    recalcAbnormal,
    isAllChecked,
    // Sampling
    fillVoucherSamples,
    // CRUD
    addRow,
    removeRow,
    // Data
    loadRows,
    toJSON,
  }
}

export default useG4EclVoucherCheck
