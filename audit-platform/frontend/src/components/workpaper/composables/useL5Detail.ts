/**
 * useL5Detail — L5-2 明细表 composable（30列按区段Tab管理）
 *
 * Spec: .kiro/specs/l5-long-term-payables/
 * Task: 3.4
 * Requirements: 3.1-3.2, 3.5-3.6
 *
 * 职责：
 * - 30列按区段Tab管理（未审数区/调整区/审定数区）
 * - 动态行增删（先弹ElMessageBox.prompt输入款项名称）
 * - 期末余额计算：负债类 期末=期初+贷方(增加)-借方(偿还)
 * - 与L5-1交叉验证（明细合计=审定表合计）
 * - 与L5-5摊销测算按款项一一对应
 *
 * 科目：2701 长期应付款（贷方/负债类！期末=期初+贷方-借方）
 */
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcLiabilityEndBalance, calcSubtotal } from './useL5FormulaEngine'
import type { useL5FormData, ChecklistResponse } from './useL5FormData'

/** 🔴 P0 修复：JSON 存储键（此前组件无 hydration + 保存仅序列化字段子集 → 刷新数据丢失/大部分字段丢失） */
const ITEM_ROWS = 'L5-L5-2-rows'

// ─── Types ───────────────────────────────────────────────────────────────────

/** L5-2 明细表行数据（30列） */
export interface L5DetailRow {
  /** 行唯一标识（多区段共享） */
  key: string
  /** 款项来源/名称 */
  payableName: string
  /** 债权人 */
  creditor: string
  /** 起始日期 */
  startDate: string
  /** 到期日期 */
  maturityDate: string
  /** 款项类型：融资租赁/分期付款/其他 */
  category: string
  /** 名义金额（合同总价） */
  nominalAmount: number
  /** 折现率（实际利率） */
  discountRate: number
  /** 现值 */
  presentValue: number
  /** 期初余额 */
  beginning: number
  /** 本期增加（贷方） */
  periodIncrease: number
  /** 本期偿还（借方） */
  periodRepayment: number
  /** 期末余额（公式列：期初+贷方-借方） */
  endBalance: number
  /** 未审数 */
  unadjusted: number
  /** AJE调整 */
  aje: number
  /** RJE调整 */
  rje: number
  /** 审定数 */
  audited: number
  /** 币种 */
  currency: string
  /** 担保方式 */
  guaranteeType: string
  /** 备注 */
  remark: string
}

/** 区段Tab类型：3区段 */
export type L5DetailSegment = 'unadjusted' | 'adjustment' | 'audited'

// ─── Constants ───────────────────────────────────────────────────────────────

/** 区段Tab定义：30列拆3段 */
export const L5_DETAIL_SEGMENTS = [
  {
    key: 'unadjusted' as const,
    label: '未审数区',
    fields: [
      'payableName', 'creditor', 'startDate', 'maturityDate', 'category',
      'nominalAmount', 'discountRate', 'presentValue', 'beginning',
      'periodIncrease', 'periodRepayment', 'endBalance',
    ],
  },
  {
    key: 'adjustment' as const,
    label: '调整区',
    fields: ['unadjusted', 'aje', 'rje', 'audited'],
  },
  {
    key: 'audited' as const,
    label: '审定数区',
    fields: ['currency', 'guaranteeType', 'remark'],
  },
] as const

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L5-2 明细表业务逻辑（30列区段Tab）
 *
 * @param formData 由调用方传入的 useL5FormData 实例
 * @param detailRows reactive ref of detail rows
 */
export function useL5Detail(
  formData: ReturnType<typeof useL5FormData>,
  detailRows: Ref<L5DetailRow[]>,
) {
  const { allResponses, debouncedSave } = formData

  // ─── 0. Hydration（从 allResponses 解析完整行 JSON） ─────────────────────
  function hydrate(): void {
    const raw = allResponses.value.get(ITEM_ROWS)?.remark
    if (!raw) return
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) detailRows.value = parsed
    } catch { /* ignore */ }
  }
  hydrate()
  watch(
    () => allResponses.value.get(ITEM_ROWS)?.remark,
    (v) => { if (v && detailRows.value.length === 0) hydrate() },
  )

  // ─── 1. 区段Tab状态 ────────────────────────────────────────────────────

  const activeSegment = ref<L5DetailSegment>('unadjusted')

  function switchSegment(segment: L5DetailSegment): void {
    activeSegment.value = segment
  }

  // ─── 2. 计算属性：负债类期末余额 ─────────────────────────────────────────

  /** 各行期末余额自动计算（负债类：期初+贷方-借方） */
  const computedRows: ComputedRef<L5DetailRow[]> = computed(() => {
    return detailRows.value.map(row => ({
      ...row,
      // 负债类：期末 = 期初 + 本期增加(贷方) - 本期偿还(借方)
      endBalance: calcLiabilityEndBalance(row.beginning, row.periodIncrease, row.periodRepayment),
    }))
  })

  /** 期末余额合计（供L5-1交叉验证） */
  const totalEndBalance: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.endBalance))
  })

  /** 期初余额合计 */
  const totalBeginning: ComputedRef<number> = computed(() => {
    return calcSubtotal(detailRows.value.map(r => r.beginning))
  })

  /** 名义金额合计 */
  const totalNominalAmount: ComputedRef<number> = computed(() => {
    return calcSubtotal(detailRows.value.map(r => r.nominalAmount))
  })

  // ─── 3. 动态行增删 ────────────────────────────────────────────────────

  /**
   * 新增明细行（先弹 ElMessageBox.prompt 输入款项名称）
   */
  async function addRow(): Promise<void> {
    try {
      const { value: payableName } = await ElMessageBox.prompt(
        '请输入款项来源/名称',
        '新增长期应付款明细',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '如：XX融资租赁/XX设备分期付款',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '款项名称不能为空'
            return true
          },
        },
      )

      const key = `l5-detail-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const newRow: L5DetailRow = {
        key,
        payableName: payableName?.trim() || '',
        creditor: '',
        startDate: '',
        maturityDate: '',
        category: '',
        nominalAmount: 0,
        discountRate: 0,
        presentValue: 0,
        beginning: 0,
        periodIncrease: 0,
        periodRepayment: 0,
        endBalance: 0,
        unadjusted: 0,
        aje: 0,
        rje: 0,
        audited: 0,
        currency: 'CNY',
        guaranteeType: '',
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
  function updateRow(index: number, field: keyof L5DetailRow, value: string | number): void {
    if (index < 0 || index >= detailRows.value.length) return
    const row = detailRows.value[index] as any
    row[field] = value

    // 如果是金额字段，重算期末余额
    if (['beginning', 'periodIncrease', 'periodRepayment'].includes(field)) {
      row.endBalance = calcLiabilityEndBalance(row.beginning, row.periodIncrease, row.periodRepayment)
    }

    _triggerSave(index)
  }

  // ─── 4. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(_rowIndex?: number): void {
    // 序列化完整行数据（含所有字段）+ 保证 endBalance 新鲜，供持久化+CrossSheet勾稽
    const payload = detailRows.value.map(r => ({
      ...r,
      endBalance: calcLiabilityEndBalance(r.beginning, r.periodIncrease, r.periodRepayment),
    }))
    debouncedSave(ITEM_ROWS, { remark: JSON.stringify(payload) } as Partial<ChecklistResponse>)
  }

  function _triggerSaveAll(): void {
    _triggerSave()
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 区段Tab
    activeSegment,
    switchSegment,

    // 计算属性
    computedRows,
    totalEndBalance,
    totalBeginning,
    totalNominalAmount,

    // 行操作
    addRow,
    removeRow,
    updateRow,
  }
}

export default useL5Detail
