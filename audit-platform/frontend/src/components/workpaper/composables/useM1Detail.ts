/**
 * useM1Detail — M1-2 明细表 composable（27列区段Tab管理）
 *
 * Spec: .kiro/specs/m1-dividends-payable/
 * Task: 3.4
 * Requirements: 3.1-3.5
 *
 * 职责：
 * - 38×27 列，按股东列示应付股利明细
 * - 27列区段Tab拆分（3段：股东信息/宣告金额/支付情况，行同步）
 * - 动态行新增（ElMessageBox.prompt 输入股东名称）
 * - 公式：期末应付=期初+本期宣告-本期支付（负债类贷方）
 * - 与M1-1审定表交叉验证（合计行）
 *
 * 科目：2232 应付股利（贷方/负债类！期末=期初+贷方-借方）
 * 宣告在贷方增加，支付在借方减少
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  calcLiabilityEndBalance,
  calcSubtotal,
} from './useM1FormulaEngine'
import type { useM1FormData } from './useM1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** M1-2 明细表行数据（27列按股东） */
export interface M1DetailRow {
  /** 行唯一标识 */
  key: string
  /** 序号 */
  seq: number
  // ─── 区段1: 股东信息 ───
  /** 股东名称 */
  shareholderName: string
  /** 持股比例(%) */
  shareholdingRatio: number
  /** 币种 */
  currency: string
  /** 股东类型（自然人/法人/基金等） */
  shareholderType: string
  /** 备注 */
  remark: string
  // ─── 区段2: 宣告金额（贷方增加） ───
  /** 期初应付余额 */
  beginBalance: number
  /** 本期宣告股利（贷方增加） */
  declaredAmount: number
  /** 宣告日期 */
  declaredDate: string
  /** 决议文号 */
  resolutionRef: string
  /** 分配比例(%) */
  distributionRatio: number
  /** 分配基数（可供分配利润） */
  distributionBase: number
  /** 应宣告=基数×比例 */
  expectedDeclared: number
  /** 宣告差异=实际宣告-应宣告 */
  declareDiff: number
  // ─── 区段3: 支付情况（借方减少） ───
  /** 本期支付（借方减少） */
  paidAmount: number
  /** 支付日期 */
  paidDate: string
  /** 支付方式（银行转账/现金等） */
  paymentMethod: string
  /** 代扣代缴税金 */
  withholdingTax: number
  /** 实际支付净额=支付-代扣 */
  netPaidAmount: number
  /** 期末应付余额（公式=期初+宣告-支付） */
  endBalance: number
  /** 期末应付（审定数） */
  endAudited: number
  /** 与M1-1交叉验证差额 */
  crossRefDiff: number
  // ─── 公式列 ───
  /** 本期变动=宣告-支付 */
  periodChange: number
}

/** 区段Tab类型 */
export type M1DetailSegment = 'shareholder' | 'declared' | 'payment'

// ─── Constants ───────────────────────────────────────────────────────────────

/** 区段Tab定义：27列拆3段 */
export const M1_DETAIL_SEGMENTS = [
  {
    key: 'shareholder' as const,
    label: '股东信息',
    fields: ['seq', 'shareholderName', 'shareholdingRatio', 'currency', 'shareholderType', 'remark'],
  },
  {
    key: 'declared' as const,
    label: '宣告金额',
    fields: [
      'beginBalance', 'declaredAmount', 'declaredDate', 'resolutionRef',
      'distributionRatio', 'distributionBase', 'expectedDeclared', 'declareDiff',
    ],
  },
  {
    key: 'payment' as const,
    label: '支付情况',
    fields: [
      'paidAmount', 'paidDate', 'paymentMethod', 'withholdingTax',
      'netPaidAmount', 'endBalance', 'endAudited', 'crossRefDiff', 'periodChange',
    ],
  },
] as const

/** 支付方式选项 */
export const PAYMENT_METHOD_OPTIONS = [
  { value: 'bank_transfer', label: '银行转账' },
  { value: 'cash', label: '现金' },
  { value: 'offset', label: '抵扣' },
  { value: 'other', label: '其他' },
]

/** 股东类型选项 */
export const SHAREHOLDER_TYPE_OPTIONS = [
  { value: 'natural', label: '自然人' },
  { value: 'legal', label: '法人' },
  { value: 'fund', label: '基金' },
  { value: 'foreign', label: '境外股东' },
  { value: 'other', label: '其他' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M1-2 明细表业务逻辑（27列区段Tab + 按股东动态行）
 *
 * @param formData 由调用方传入的 useM1FormData 实例
 * @param detailRows reactive ref of detail rows
 */
export function useM1Detail(
  formData: ReturnType<typeof useM1FormData>,
  detailRows: Ref<M1DetailRow[]>,
) {
  const { debouncedSave } = formData

  // ─── 1. 区段Tab状态 ────────────────────────────────────────────────────

  const activeSegment = ref<M1DetailSegment>('shareholder')

  function switchSegment(segment: M1DetailSegment): void {
    activeSegment.value = segment
  }

  // ─── 2. 计算属性：公式列自动计算 ─────────────────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<M1DetailRow[]> = computed(() => {
    return detailRows.value.map(row => {
      // 期末应付=期初+本期宣告-本期支付（负债类：贷方增-借方减）
      const endBalance = calcLiabilityEndBalance(row.beginBalance, row.declaredAmount, row.paidAmount)
      // 本期变动=宣告-支付
      const periodChange = row.declaredAmount - row.paidAmount
      // 应宣告=分配基数×分配比例
      const expectedDeclared = row.distributionBase * (row.distributionRatio / 100)
      // 宣告差异=实际宣告-应宣告
      const declareDiff = row.declaredAmount - expectedDeclared
      // 实际支付净额=支付-代扣
      const netPaidAmount = row.paidAmount - row.withholdingTax

      return {
        ...row,
        endBalance,
        periodChange,
        expectedDeclared,
        declareDiff,
        netPaidAmount,
        endAudited: endBalance, // 审定=期末余额
        crossRefDiff: 0, // 交叉验证差额由外部注入
      }
    })
  })

  // ─── 3. 合计行 ────────────────────────────────────────────────────────

  /** 期初合计 */
  const totalBeginBalance: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.beginBalance))
  })

  /** 本期宣告合计 */
  const totalDeclared: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.declaredAmount))
  })

  /** 本期支付合计 */
  const totalPaid: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.paidAmount))
  })

  /** 期末合计（供M1-1交叉验证） */
  const totalEndBalance: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.endBalance))
  })

  // ─── 4. 动态行增删 ────────────────────────────────────────────────────

  /**
   * 新增明细行（先弹 ElMessageBox.prompt 输入股东名称）
   */
  async function addRow(): Promise<void> {
    try {
      const { value: shareholderName } = await ElMessageBox.prompt(
        '请输入股东名称',
        '新增应付股利明细',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '如：XX投资有限公司/张三',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '股东名称不能为空'
            return true
          },
        },
      )

      const key = `m1-detail-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const seq = detailRows.value.length + 1
      const newRow: M1DetailRow = {
        key,
        seq,
        shareholderName: shareholderName?.trim() || '',
        shareholdingRatio: 0,
        currency: 'CNY',
        shareholderType: '',
        remark: '',
        beginBalance: 0,
        declaredAmount: 0,
        declaredDate: '',
        resolutionRef: '',
        distributionRatio: 0,
        distributionBase: 0,
        expectedDeclared: 0,
        declareDiff: 0,
        paidAmount: 0,
        paidDate: '',
        paymentMethod: '',
        withholdingTax: 0,
        netPaidAmount: 0,
        endBalance: 0,
        endAudited: 0,
        crossRefDiff: 0,
        periodChange: 0,
      }
      detailRows.value.push(newRow)
      _triggerSaveAll()
    } catch {
      // 用户取消
    }
  }

  /** 删除指定行 */
  function removeRow(index: number): void {
    if (index < 0 || index >= detailRows.value.length) return
    detailRows.value.splice(index, 1)
    // 重新编号
    detailRows.value.forEach((r, i) => { r.seq = i + 1 })
    _triggerSaveAll()
  }

  /** 更新某行某字段 */
  function updateRow(index: number, field: keyof M1DetailRow, value: any): void {
    if (index < 0 || index >= detailRows.value.length) return
    const row = detailRows.value[index] as any
    row[field] = value
    _triggerSave(index)
  }

  // ─── 5. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = detailRows.value[rowIndex]
    if (!row) return
    const computed = computedRows.value[rowIndex]
    // 保存期末余额（供CrossSheet勾稽）
    if (computed) {
      debouncedSave(`M1-M1-2-row-${rowIndex}-endBalance`, {
        remark: String(computed.endBalance),
      })
    }
    // 保存行完整数据
    debouncedSave(`M1-M1-2-row-${rowIndex}-data`, {
      remark: JSON.stringify({
        key: row.key,
        seq: row.seq,
        shareholderName: row.shareholderName,
        shareholdingRatio: row.shareholdingRatio,
        currency: row.currency,
        shareholderType: row.shareholderType,
        remark: row.remark,
        beginBalance: row.beginBalance,
        declaredAmount: row.declaredAmount,
        declaredDate: row.declaredDate,
        resolutionRef: row.resolutionRef,
        distributionRatio: row.distributionRatio,
        distributionBase: row.distributionBase,
        paidAmount: row.paidAmount,
        paidDate: row.paidDate,
        paymentMethod: row.paymentMethod,
        withholdingTax: row.withholdingTax,
      }),
    })
    // 保存明细表合计（供CrossSheet交叉验证）
    debouncedSave('M1-M1-2-totalEndBalance', {
      remark: String(totalEndBalance.value),
    })
  }

  function _triggerSaveAll(): void {
    detailRows.value.forEach((_, i) => _triggerSave(i))
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 区段Tab
    activeSegment,
    switchSegment,

    // 计算属性
    computedRows,
    totalBeginBalance,
    totalDeclared,
    totalPaid,
    totalEndBalance,

    // 行操作
    addRow,
    removeRow,
    updateRow,
  }
}

export default useM1Detail
