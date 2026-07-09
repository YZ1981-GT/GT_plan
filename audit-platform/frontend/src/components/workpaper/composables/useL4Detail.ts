/**
 * useL4Detail — L4-2 明细表 composable（89列极宽表！）
 *
 * Spec: .kiro/specs/l4-bonds-payable/
 * Task: 3.4
 * Requirements: 3.1-3.5
 *
 * 职责：
 * - 89列极宽表管理（债券名称|发行日|到期日|面值|票面利率|实际利率|付息方式|期初/期末摊余成本...）
 * - 区段Tab管理（5区段：基础信息/发行信息/计息付息/摊余成本/兑付信息）
 * - 动态行新增（先弹ElMessageBox.prompt输入债券名称）
 * - 行同步（多区段共享同一行key）
 * - 与审定表L4-1交叉验证 + 与L4-6/L4-7对应
 *
 * 科目：2502 应付债券（贷方/负债类）
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcLiabilityEndBalance, calcSubtotal } from './useL4FormulaEngine'
import type { useL4FormData } from './useL4FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** L4明细表行数据（89列全字段） */
export interface L4DetailRow {
  /** 行唯一标识（多区段共享） */
  key: string
  /** 债券名称 */
  bondName: string
  /** 发行日期 */
  issueDate: string
  /** 到期日期 */
  maturityDate: string
  /** 面值总额 */
  faceValue: number
  /** 票面利率（年） */
  couponRate: number
  /** 实际利率（EIR） */
  effectiveRate: number
  /** 付息方式：'bullet'=到期一次还本付息 | 'installment'=分期付息 */
  paymentType: 'bullet' | 'installment'
  /** 发行价格 */
  issuePrice: number
  /** 交易费用 */
  transactionCost: number
  /** 初始入账金额 */
  initialAmount: number
  /** 溢折价 */
  premiumDiscount: number
  /** 期初摊余成本（成本） */
  beginCostPrincipal: number
  /** 期初摊余成本（利息调整） */
  beginCostInterestAdj: number
  /** 期初摊余成本（应计利息） */
  beginCostAccrued: number
  /** 贷方发生额（发行） */
  creditIssue: number
  /** 贷方发生额（利息调整增加） */
  creditInterestAdj: number
  /** 借方发生额（兑付） */
  debitRedemption: number
  /** 借方发生额（利息调整减少） */
  debitInterestAdj: number
  /** 期末摊余成本（成本） */
  endCostPrincipal: number
  /** 期末摊余成本（利息调整） */
  endCostInterestAdj: number
  /** 期末摊余成本（应计利息） */
  endCostAccrued: number
  /** 本期票面利息 */
  couponInterest: number
  /** 本期实际利息费用 */
  interestExpense: number
  /** 本期利息调整摊销 */
  amortization: number
  /** 兑付日期 */
  redemptionDate: string
  /** 兑付金额 */
  redemptionAmount: number
  /** 是否已兑付 */
  isRedeemed: boolean
  /** 备注 */
  remark: string
}

/** 区段Tab类型：5区段 */
export type L4DetailSegment = 'basic' | 'issue' | 'interest' | 'amortized' | 'redemption'

// ─── Constants ───────────────────────────────────────────────────────────────

/** 区段Tab定义：89列拆5段 */
export const L4_DETAIL_SEGMENTS = [
  {
    key: 'basic' as const,
    label: '基础信息',
    fields: ['bondName', 'issueDate', 'maturityDate', 'faceValue', 'couponRate', 'effectiveRate', 'paymentType'],
  },
  {
    key: 'issue' as const,
    label: '发行信息',
    fields: ['issuePrice', 'transactionCost', 'initialAmount', 'premiumDiscount'],
  },
  {
    key: 'interest' as const,
    label: '计息付息',
    fields: ['couponInterest', 'interestExpense', 'amortization'],
  },
  {
    key: 'amortized' as const,
    label: '摊余成本',
    fields: [
      'beginCostPrincipal', 'beginCostInterestAdj', 'beginCostAccrued',
      'creditIssue', 'creditInterestAdj', 'debitRedemption', 'debitInterestAdj',
      'endCostPrincipal', 'endCostInterestAdj', 'endCostAccrued',
    ],
  },
  {
    key: 'redemption' as const,
    label: '兑付信息',
    fields: ['redemptionDate', 'redemptionAmount', 'isRedeemed', 'remark'],
  },
] as const

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L4-2 明细表业务逻辑（89列极宽表！）
 *
 * @param formData 由调用方传入的 useL4FormData 实例
 * @param detailRows reactive ref of detail rows
 */
export function useL4Detail(
  formData: ReturnType<typeof useL4FormData>,
  detailRows: Ref<L4DetailRow[]>,
) {
  const { debouncedSave } = formData

  // ─── 1. 区段Tab状态（行同步：切换Tab不影响行选择） ───────────────────────

  const activeSegment = ref<L4DetailSegment>('basic')

  function switchSegment(segment: L4DetailSegment): void {
    activeSegment.value = segment
  }

  // ─── 2. 计算属性 ──────────────────────────────────────────────────────

  /** 各行期末摊余成本合计（=成本+利息调整+应计利息） */
  const computedRows: ComputedRef<L4DetailRow[]> = computed(() => {
    return detailRows.value.map(row => {
      // 负债类：期末=期初+贷方-借方（各子项分别计算）
      const endPrincipal = calcLiabilityEndBalance(
        row.beginCostPrincipal, row.creditIssue, row.debitRedemption,
      )
      const endInterestAdj = calcLiabilityEndBalance(
        row.beginCostInterestAdj, row.creditInterestAdj, row.debitInterestAdj,
      )
      return {
        ...row,
        endCostPrincipal: endPrincipal,
        endCostInterestAdj: endInterestAdj,
      }
    })
  })

  /** 期末摊余成本合计（供L4-1交叉验证） */
  const totalEndAmortizedCost: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r =>
      r.endCostPrincipal + r.endCostInterestAdj + r.endCostAccrued,
    ))
  })

  /** 面值合计 */
  const totalFaceValue: ComputedRef<number> = computed(() => {
    return calcSubtotal(detailRows.value.map(r => r.faceValue))
  })

  // ─── 3. 动态行增删 ────────────────────────────────────────────────────

  /**
   * 新增明细行（先弹 ElMessageBox.prompt 输入债券名称）
   */
  async function addRow(): Promise<void> {
    try {
      const { value: bondName } = await ElMessageBox.prompt(
        '请输入债券名称',
        '新增应付债券明细',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '如：2024年第一期中期票据',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '债券名称不能为空'
            return true
          },
        },
      )

      const key = `bond-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const newRow: L4DetailRow = {
        key,
        bondName: bondName?.trim() || '',
        issueDate: '',
        maturityDate: '',
        faceValue: 0,
        couponRate: 0,
        effectiveRate: 0,
        paymentType: 'installment',
        issuePrice: 0,
        transactionCost: 0,
        initialAmount: 0,
        premiumDiscount: 0,
        beginCostPrincipal: 0,
        beginCostInterestAdj: 0,
        beginCostAccrued: 0,
        creditIssue: 0,
        creditInterestAdj: 0,
        debitRedemption: 0,
        debitInterestAdj: 0,
        endCostPrincipal: 0,
        endCostInterestAdj: 0,
        endCostAccrued: 0,
        couponInterest: 0,
        interestExpense: 0,
        amortization: 0,
        redemptionDate: '',
        redemptionAmount: 0,
        isRedeemed: false,
        remark: '',
      }

      detailRows.value.push(newRow)
      _triggerSave(detailRows.value.length - 1)
    } catch {
      // 用户取消
    }
  }

  /** 删除指定行 */
  function removeRow(index: number): void {
    if (index < 0 || index >= detailRows.value.length) return
    detailRows.value.splice(index, 1)
    _triggerSaveAll()
  }

  /** 更新某行某字段 */
  function updateRow(index: number, field: keyof L4DetailRow, value: string | number | boolean): void {
    if (index < 0 || index >= detailRows.value.length) return
    const row = detailRows.value[index] as any
    row[field] = value

    // 如果是金额/利率字段，重算公式列
    if (['beginCostPrincipal', 'creditIssue', 'debitRedemption'].includes(field)) {
      row.endCostPrincipal = calcLiabilityEndBalance(row.beginCostPrincipal, row.creditIssue, row.debitRedemption)
    }
    if (['beginCostInterestAdj', 'creditInterestAdj', 'debitInterestAdj'].includes(field)) {
      row.endCostInterestAdj = calcLiabilityEndBalance(row.beginCostInterestAdj, row.creditInterestAdj, row.debitInterestAdj)
    }

    _triggerSave(index)
  }

  // ─── 4. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = detailRows.value[rowIndex]
    if (!row) return
    const n = rowIndex + 1
    const fields: (keyof L4DetailRow)[] = [
      'bondName', 'issueDate', 'maturityDate', 'faceValue', 'couponRate',
      'effectiveRate', 'paymentType', 'issuePrice', 'transactionCost',
      'beginCostPrincipal', 'beginCostInterestAdj', 'beginCostAccrued',
      'creditIssue', 'creditInterestAdj', 'debitRedemption', 'debitInterestAdj',
      'endCostPrincipal', 'endCostInterestAdj', 'endCostAccrued',
      'couponInterest', 'interestExpense', 'amortization',
      'redemptionDate', 'redemptionAmount', 'isRedeemed', 'remark',
    ]
    for (const field of fields) {
      const val = (row as any)[field]
      debouncedSave(`L4-2-row-${n}-${field}`, {
        remark: val != null && val !== '' && val !== 0 && val !== false ? String(val) : null,
      })
    }
  }

  function _triggerSaveAll(): void {
    for (let i = 0; i < detailRows.value.length; i++) {
      _triggerSave(i)
    }
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 区段Tab
    activeSegment,
    switchSegment,

    // 计算属性
    computedRows,
    totalEndAmortizedCost,
    totalFaceValue,

    // 行操作
    addRow,
    removeRow,
    updateRow,
  }
}

export default useL4Detail
