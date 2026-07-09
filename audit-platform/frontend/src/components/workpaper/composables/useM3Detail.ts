/**
 * useM3Detail — M3-2 明细表 composable
 *
 * Spec: .kiro/specs/m3-treasury-stock/
 * Task: 3.4
 * Requirements: 3.1-3.5
 *
 * 职责：
 * - 动态行（每行=一个回购批次）管理，59×19 结构
 * - 19列拆3区段Tab（回购信息/注销情况/期末余额，行同步）
 * - 期末库存股数 = 期初 + 回购 - 注销（备抵借方增加！）
 * - 期末金额 = 期初金额 + 回购金额 - 注销金额（同方向）
 * - 动态行新增（ElMessageBox.prompt 输入批次名）
 * - 与M3-1审定表交叉验证（totalEndAmount）
 *
 * 科目：4002 库存股（**借方/权益备抵类！**）
 * 回购=借方增加（期末股数增加），注销=贷方减少（期末股数减少）
 */
import { computed, ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcContraEquityEndBalance, calcSubtotal } from './useM3FormulaEngine'
import type { useM3FormData } from './useM3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** M3明细表行数据（按回购批次） */
export interface M3DetailRow {
  /** 行唯一标识 */
  key: string
  /** 回购批次名称 */
  batchName: string
  /** 回购日期 */
  repurchaseDate: string
  /** 回购股数（股） */
  repurchaseShares: number
  /** 回购单价（元/股） */
  price: number
  /** 回购金额（借方发生额） */
  repurchaseAmount: number
  /** 注销股数 */
  cancelShares: number
  /** 注销金额（贷方发生额） */
  cancelAmount: number
  /** 期初股数 */
  beginShares: number
  /** 期初金额 */
  beginAmount: number
  /** 期末库存股数（公式=期初+回购-注销） */
  endShares: number
  /** 期末金额（公式=期初金额+回购金额-注销金额） */
  endAmount: number
  /** 回购目的 */
  purpose: string
  /** 股份来源 */
  source: string
  /** 决议文号 */
  resolutionNo: string
  /** 币种 */
  currency: string
  /** 备注 */
  remark: string
}

/** 区段Tab类型：3组 */
export type M3DetailSegment = 'repurchase' | 'cancel' | 'endBalance'

// ─── Constants ───────────────────────────────────────────────────────────────

/** 区段Tab定义：19列拆3段 */
export const M3_DETAIL_SEGMENTS = [
  { key: 'repurchase' as const, label: '回购信息', fields: ['batchName', 'repurchaseDate', 'repurchaseShares', 'price', 'repurchaseAmount', 'purpose', 'source', 'resolutionNo', 'currency'] },
  { key: 'cancel' as const, label: '注销情况', fields: ['cancelShares', 'cancelAmount'] },
  { key: 'endBalance' as const, label: '期末余额', fields: ['beginShares', 'beginAmount', 'endShares', 'endAmount', 'remark'] },
] as const

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M3-2 明细表业务逻辑（按回购批次+动态行+3区段Tab）
 *
 * @param formData 由调用方传入的 useM3FormData 实例
 * @param detailRows reactive ref of detail rows
 */
export function useM3Detail(
  formData: ReturnType<typeof useM3FormData>,
  detailRows: { value: M3DetailRow[] },
) {
  const { debouncedSave } = formData

  // ─── 1. 区段Tab状态 ────────────────────────────────────────────────────

  const activeSegment = ref<M3DetailSegment>('repurchase')

  function switchSegment(segment: M3DetailSegment): void {
    activeSegment.value = segment
  }

  // ─── 2. 计算属性：公式列自动计算 ──────────────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<M3DetailRow[]> = computed(() => {
    return detailRows.value.map(row => ({
      ...row,
      // 权益备抵借方：期末股数=期初+回购-注销
      endShares: calcContraEquityEndBalance(row.beginShares, row.repurchaseShares, row.cancelShares),
      // 权益备抵借方：期末金额=期初金额+回购金额-注销金额
      endAmount: calcContraEquityEndBalance(row.beginAmount, row.repurchaseAmount, row.cancelAmount),
    }))
  })

  /** 合计：期末金额（供与M3-1审定表交叉验证） */
  const totalEndAmount: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.endAmount))
  })

  /** 合计：期末股数 */
  const totalEndShares: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.endShares))
  })

  /** 合计：回购金额 */
  const totalRepurchaseAmount: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.repurchaseAmount))
  })

  /** 合计：注销金额 */
  const totalCancelAmount: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.cancelAmount))
  })

  // ─── 3. 动态行增删 ────────────────────────────────────────────────────

  /**
   * 新增明细行（先弹 ElMessageBox.prompt 输入批次名）
   */
  async function addRow(): Promise<void> {
    try {
      const { value: batchName } = await ElMessageBox.prompt(
        '请输入回购批次名称',
        '新增库存股明细',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '如：2024年第一次回购',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '批次名称不能为空'
            return true
          },
        },
      )

      const key = `m3-det-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const newRow: M3DetailRow = {
        key,
        batchName: batchName?.trim() || '',
        repurchaseDate: '',
        repurchaseShares: 0,
        price: 0,
        repurchaseAmount: 0,
        cancelShares: 0,
        cancelAmount: 0,
        beginShares: 0,
        beginAmount: 0,
        endShares: 0,
        endAmount: 0,
        purpose: '',
        source: '',
        resolutionNo: '',
        currency: 'CNY',
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
  function updateRow(index: number, field: keyof M3DetailRow, value: string | number): void {
    if (index < 0 || index >= detailRows.value.length) return
    const row = detailRows.value[index] as any
    row[field] = value

    // 金额字段变动→重算公式列
    if (['beginShares', 'repurchaseShares', 'cancelShares'].includes(field as string)) {
      row.endShares = calcContraEquityEndBalance(row.beginShares, row.repurchaseShares, row.cancelShares)
    }
    if (['beginAmount', 'repurchaseAmount', 'cancelAmount'].includes(field as string)) {
      row.endAmount = calcContraEquityEndBalance(row.beginAmount, row.repurchaseAmount, row.cancelAmount)
    }

    _triggerSave(index)
  }

  // ─── 4. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = detailRows.value[rowIndex]
    if (!row) return
    const n = rowIndex + 1
    debouncedSave(`M3-M3-2-row-${n}-data`, {
      remark: JSON.stringify({
        key: row.key,
        batchName: row.batchName,
        repurchaseDate: row.repurchaseDate,
        repurchaseShares: row.repurchaseShares,
        price: row.price,
        repurchaseAmount: row.repurchaseAmount,
        cancelShares: row.cancelShares,
        cancelAmount: row.cancelAmount,
        beginShares: row.beginShares,
        beginAmount: row.beginAmount,
        purpose: row.purpose,
        source: row.source,
        resolutionNo: row.resolutionNo,
        currency: row.currency,
        remark: row.remark,
      }),
    })
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
    totalEndAmount,
    totalEndShares,
    totalRepurchaseAmount,
    totalCancelAmount,

    // 行操作
    addRow,
    removeRow,
    updateRow,
  }
}

export default useM3Detail
