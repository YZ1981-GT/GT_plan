/**
 * useM4ReserveCheck — M4-4 检查表 composable
 *
 * Spec: .kiro/specs/m4-capital-reserve/
 * Task: 3.4
 * Requirements: 5.1-5.2
 *
 * 职责：
 * - 凭证核对行管理（资本公积变动凭证抽查）
 * - 检查金额/本期发生额 比率计算（检查覆盖率）
 * - 审计结论区（el-card包裹）
 * - AI辅助section标题行按钮
 * - J3股份支付核对（确认差异展示）
 * - M2外币折算差异核对
 *
 * 科目：4002 资本公积（**贷方/权益类！**）
 * 检查关注：增加凭证（贷方：溢价/股份支付/外币折算）+ 减少凭证（借方：转增/弥补）
 */
import { computed, ref, type ComputedRef } from 'vue'
import { calcSubtotal } from './useM4FormulaEngine'
import { calcShareBasedDiff } from './useM4ReserveEngine'
import type { useM4FormData } from './useM4FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 凭证核对行 */
export interface M4VoucherCheckRow {
  /** 序号 */
  index: number
  /** 凭证号 */
  voucherNo: string
  /** 凭证日期 */
  voucherDate: string
  /** 摘要 */
  summary: string
  /** 科目 */
  accountName: string
  /** 借方金额 */
  debitAmount: number
  /** 贷方金额 */
  creditAmount: number
  /** 检查金额（借方或贷方，取较大值） */
  checkAmount: number
  /** 核对结果 */
  checkResult: '√' | '×' | '?' | ''
  /** 差异说明 */
  diffNote: string
  /** 凭证附件OCR结果（📎列） */
  ocrResult: string
}

/** 核对清单项 */
export interface M4ChecklistItem {
  /** 序号 */
  index: number
  /** 检查项目 */
  item: string
  /** 是否通过 */
  passed: boolean | null
  /** 说明/备注 */
  note: string
}

/** 检查覆盖率 */
export interface M4CheckRatio {
  /** 检查金额合计 */
  checkedAmount: number
  /** 本期发生额（贷方增加+借方减少） */
  periodAmount: number
  /** 检查比率 */
  ratio: number | null
}

/** J3股份支付核对结果 */
export interface M4ShareBasedCheck {
  /** J3确认金额 */
  j3Amount: number
  /** 账面其他资本公积增加 */
  bookedAmount: number
  /** 差异 */
  diff: number
  /** 是否一致（差异绝对值≤阈值） */
  isConsistent: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 股份支付差异阈值（超过则红色高亮） */
const SHARE_BASED_DIFF_THRESHOLD = 100

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M4-4 检查表业务逻辑（凭证核对+覆盖率+J3核对+结论）
 *
 * @param formData 由调用方传入的 useM4FormData 实例
 */
export function useM4ReserveCheck(formData: ReturnType<typeof useM4FormData>) {
  const { debouncedSave, saveBatch } = formData

  // ─── 1. State ─────────────────────────────────────────────────────────

  const voucherRows = ref<M4VoucherCheckRow[]>([])
  const checklist = ref<M4ChecklistItem[]>([])
  const conclusion = ref('')
  /** 本期发生额（由外部设置：贷方增加+借方减少合计） */
  const periodOccurrence = ref(0)
  /** J3股份支付确认金额（由 EventBus 'j3:equity-settled' 设置） */
  const j3EquitySettled = ref(0)
  /** 账面其他资本公积增加（由M4-2明细表 other 区段增加合计） */
  const bookedOtherIncrease = ref(0)

  // ─── 2. 凭证核对计算 ──────────────────────────────────────────────────

  /** 凭证核对行（自动计算 checkAmount） */
  const computedVoucherRows: ComputedRef<M4VoucherCheckRow[]> = computed(() => {
    return voucherRows.value.map(row => ({
      ...row,
      checkAmount: Math.max(row.debitAmount, row.creditAmount),
    }))
  })

  /** 检查金额合计 */
  const totalCheckAmount: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedVoucherRows.value.map(r => r.checkAmount))
  })

  /** 检查覆盖率 = 检查金额 / 本期发生额 */
  const checkRatio: ComputedRef<M4CheckRatio> = computed(() => {
    const checkedAmount = totalCheckAmount.value
    const periodAmount = periodOccurrence.value
    const ratio = periodAmount !== 0
      ? checkedAmount / periodAmount
      : null
    return { checkedAmount, periodAmount, ratio }
  })

  // ─── 3. J3股份支付核对 ────────────────────────────────────────────────

  /** J3股份支付确认差异核对 */
  const shareBasedCheck: ComputedRef<M4ShareBasedCheck> = computed(() => {
    const j3Amount = j3EquitySettled.value
    const bookedAmount = bookedOtherIncrease.value
    const diff = calcShareBasedDiff(j3Amount, bookedAmount)
    const isConsistent = Math.abs(diff) <= SHARE_BASED_DIFF_THRESHOLD
    return { j3Amount, bookedAmount, diff, isConsistent }
  })

  // ─── 4. 凭证行操作 ────────────────────────────────────────────────────

  /** 新增凭证核对行 */
  function addVoucherRow(): void {
    const newRow: M4VoucherCheckRow = {
      index: voucherRows.value.length + 1,
      voucherNo: '',
      voucherDate: '',
      summary: '',
      accountName: '',
      debitAmount: 0,
      creditAmount: 0,
      checkAmount: 0,
      checkResult: '',
      diffNote: '',
      ocrResult: '',
    }
    voucherRows.value.push(newRow)
    _saveVoucherRows()
  }

  /** 删除凭证核对行 */
  function removeVoucherRow(index: number): void {
    if (index < 0 || index >= voucherRows.value.length) return
    voucherRows.value.splice(index, 1)
    // 重新编号
    voucherRows.value.forEach((r, i) => { r.index = i + 1 })
    _saveVoucherRows()
  }

  /** 更新凭证核对行 */
  function updateVoucherRow(index: number, field: keyof M4VoucherCheckRow, value: string | number): void {
    if (index < 0 || index >= voucherRows.value.length) return
    const row = voucherRows.value[index] as any
    row[field] = value
    // 重算 checkAmount
    row.checkAmount = Math.max(row.debitAmount, row.creditAmount)
    _saveVoucherRows()
  }

  // ─── 5. 清单操作 ──────────────────────────────────────────────────────

  /** 更新清单项 */
  function updateChecklistItem(index: number, field: 'passed' | 'note', value: boolean | null | string): void {
    if (index < 0 || index >= checklist.value.length) return
    const item = checklist.value[index] as any
    item[field] = value
    _saveChecklist()
  }

  /** 设置审计结论 */
  function setConclusion(text: string): void {
    conclusion.value = text
    debouncedSave('M4-4-conclusion', { remark: text })
  }

  // ─── 6. 设置外部联动值 ────────────────────────────────────────────────

  /** 设置本期发生额（由M4-1审定表贷方+借方合计注入） */
  function setPeriodOccurrence(amount: number): void {
    periodOccurrence.value = amount
  }

  /** 设置J3股份支付确认金额（由EventBus 'j3:equity-settled'） */
  function setJ3EquitySettled(amount: number): void {
    j3EquitySettled.value = amount
  }

  /** 设置账面其他资本公积增加（由M4-2明细表other区段增加合计） */
  function setBookedOtherIncrease(amount: number): void {
    bookedOtherIncrease.value = amount
  }

  // ─── 7. 保存逻辑 ──────────────────────────────────────────────────────

  function _saveVoucherRows(): void {
    voucherRows.value.forEach((row, i) => {
      const n = i + 1
      debouncedSave(`M4-4-voucher-${n}`, {
        remark: JSON.stringify({
          voucherNo: row.voucherNo,
          voucherDate: row.voucherDate,
          summary: row.summary,
          accountName: row.accountName,
          debitAmount: row.debitAmount,
          creditAmount: row.creditAmount,
          checkResult: row.checkResult,
          diffNote: row.diffNote,
          ocrResult: row.ocrResult,
        }),
      })
    })
  }

  function _saveChecklist(): void {
    checklist.value.forEach((item, i) => {
      const n = i + 1
      debouncedSave(`M4-4-checklist-${n}`, {
        remark: JSON.stringify({ passed: item.passed, note: item.note }),
      })
    })
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // State
    voucherRows,
    checklist,
    conclusion,
    periodOccurrence,
    j3EquitySettled,
    bookedOtherIncrease,

    // 计算
    computedVoucherRows,
    totalCheckAmount,
    checkRatio,
    shareBasedCheck,

    // 凭证行操作
    addVoucherRow,
    removeVoucherRow,
    updateVoucherRow,

    // 清单+结论
    updateChecklistItem,
    setConclusion,

    // 外部联动
    setPeriodOccurrence,
    setJ3EquitySettled,
    setBookedOtherIncrease,
  }
}

export default useM4ReserveCheck
