/**
 * useM5Detail — M5-2 明细表 composable
 *
 * Spec: .kiro/specs/m5-surplus-reserve/
 * Task: 3.4
 * Requirements: 3.1-3.5
 *
 * 职责：
 * - 管理两区段：法定盈余公积明细 + 任意盈余公积明细
 * - 列结构：项目 | 期初 | 本期计提 | 本期转增资本 | 本期弥补亏损 | 期末
 *           + 未审期初/增减/期末 | AJE | RJE | 审定期初/增减/期末
 * - 权益类贷方期末：期末=期初+本期计提(贷方)-本期转增(借方)-本期弥补(借方)
 * - 41公式实时计算
 * - 动态行新增（ElMessageBox.prompt 命名后创建）
 * - 与M5-1审定表合计交叉验证
 *
 * 科目：4101 盈余公积（**贷方/权益类！期末=期初+贷方-借方**）
 * 38×17 结构，41公式
 */
import { computed, ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcEquityEndBalance, calcSubtotal } from './useM5FormulaEngine'
import type { useM5FormData } from './useM5FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 明细表区段类型 */
export type M5DetailSegment = 'statutory' | 'discretionary'

/** M5-2 明细表行数据（17列结构） */
export interface M5DetailRow {
  /** 行唯一标识 */
  key: string
  /** 所属区段：statutory=法定盈余公积, discretionary=任意盈余公积 */
  segment: M5DetailSegment
  /** 来源项目名称（如：按净利润10%计提/股东会决议计提等） */
  sourceName: string
  /** 期初余额（贷方余额） */
  beginning: number
  /** 本期计提（贷方发生：法定10%或任意决议比例） */
  accrual: number
  /** 本期转增资本（借方发生：转增实收资本） */
  capitalConversion: number
  /** 本期弥补亏损（借方发生：弥补以前年度亏损） */
  lossOffset: number
  /** 期末余额（公式=期初+计提-转增-弥补，权益类贷方！） */
  endBalance: number
  /** 未审期初 */
  unadjBeginning: number
  /** 未审本期计提 */
  unadjAccrual: number
  /** 未审本期转增 */
  unadjConversion: number
  /** 未审本期弥补 */
  unadjLossOffset: number
  /** 未审期末 */
  unadjEnd: number
  /** AJE净影响 */
  ajeAmount: number
  /** RJE净影响 */
  rjeAmount: number
  /** 审定期末（=未审期末+AJE+RJE） */
  auditedEnd: number
  /** 备注 */
  remark: string
}

/** 区段小计 */
export interface M5DetailSubtotal {
  beginning: number
  accrual: number
  capitalConversion: number
  lossOffset: number
  endBalance: number
  auditedEnd: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 区段定义 */
export const M5_DETAIL_SEGMENTS = [
  { key: 'statutory' as const, label: '法定盈余公积' },
  { key: 'discretionary' as const, label: '任意盈余公积' },
] as const

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M5-2 明细表业务逻辑（双区段+动态行+17列+41公式）
 *
 * @param formData 由调用方传入的 useM5FormData 实例
 * @param detailRows reactive ref of detail rows
 */
export function useM5Detail(
  formData: ReturnType<typeof useM5FormData>,
  detailRows: { value: M5DetailRow[] },
) {
  const { debouncedSave } = formData

  // ─── 1. 区段状态 ───────────────────────────────────────────────────────

  const activeSegment = ref<M5DetailSegment>('statutory')

  function switchSegment(segment: M5DetailSegment): void {
    activeSegment.value = segment
  }

  // ─── 2. 计算属性：公式列自动计算（41公式） ────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<M5DetailRow[]> = computed(() => {
    return detailRows.value.map(row => {
      // 权益类贷方：期末=期初+计提(贷方)-转增(借方)-弥补(借方)
      const endBalance = calcEquityEndBalance(
        row.beginning,
        row.accrual,
        row.capitalConversion + row.lossOffset,
      )
      // 未审期末
      const unadjEnd = calcEquityEndBalance(
        row.unadjBeginning,
        row.unadjAccrual,
        row.unadjConversion + row.unadjLossOffset,
      )
      // 审定期末=未审期末+AJE+RJE
      const auditedEnd = unadjEnd + row.ajeAmount + row.rjeAmount

      return { ...row, endBalance, unadjEnd, auditedEnd }
    })
  })

  /** 当前活动区段的行 */
  const activeSegmentRows: ComputedRef<M5DetailRow[]> = computed(() => {
    return computedRows.value.filter(r => r.segment === activeSegment.value)
  })

  // ─── 3. 区段小计（供M5-1交叉验证） ───────────────────────────────────

  /** 法定盈余公积区段小计 */
  const statutorySubtotal: ComputedRef<M5DetailSubtotal> = computed(() => {
    return _calcSegmentSubtotal('statutory')
  })

  /** 任意盈余公积区段小计 */
  const discretionarySubtotal: ComputedRef<M5DetailSubtotal> = computed(() => {
    return _calcSegmentSubtotal('discretionary')
  })

  /** 全部合计 */
  const grandTotal: ComputedRef<M5DetailSubtotal> = computed(() => {
    const r = computedRows.value
    return {
      beginning: calcSubtotal(r.map(x => x.beginning)),
      accrual: calcSubtotal(r.map(x => x.accrual)),
      capitalConversion: calcSubtotal(r.map(x => x.capitalConversion)),
      lossOffset: calcSubtotal(r.map(x => x.lossOffset)),
      endBalance: calcSubtotal(r.map(x => x.endBalance)),
      auditedEnd: calcSubtotal(r.map(x => x.auditedEnd)),
    }
  })

  function _calcSegmentSubtotal(segment: M5DetailSegment): M5DetailSubtotal {
    const r = computedRows.value.filter(x => x.segment === segment)
    return {
      beginning: calcSubtotal(r.map(x => x.beginning)),
      accrual: calcSubtotal(r.map(x => x.accrual)),
      capitalConversion: calcSubtotal(r.map(x => x.capitalConversion)),
      lossOffset: calcSubtotal(r.map(x => x.lossOffset)),
      endBalance: calcSubtotal(r.map(x => x.endBalance)),
      auditedEnd: calcSubtotal(r.map(x => x.auditedEnd)),
    }
  }

  // ─── 4. 动态行增删 ────────────────────────────────────────────────────

  /**
   * 新增明细行（先弹 ElMessageBox.prompt 输入来源项目名）
   */
  async function addRow(segment?: M5DetailSegment): Promise<void> {
    const targetSegment = segment || activeSegment.value
    const segmentLabel = targetSegment === 'statutory' ? '法定盈余公积' : '任意盈余公积'

    try {
      const { value: sourceName } = await ElMessageBox.prompt(
        `请输入${segmentLabel}明细来源项目名称`,
        '新增明细行',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: targetSegment === 'statutory'
            ? '如：按净利润10%提取法定盈余公积'
            : '如：股东会决议提取任意盈余公积',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '来源项目名称不能为空'
            return true
          },
        },
      )

      const key = `m5-det-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const newRow: M5DetailRow = {
        key,
        segment: targetSegment,
        sourceName: sourceName?.trim() || '',
        beginning: 0,
        accrual: 0,
        capitalConversion: 0,
        lossOffset: 0,
        endBalance: 0,
        unadjBeginning: 0,
        unadjAccrual: 0,
        unadjConversion: 0,
        unadjLossOffset: 0,
        unadjEnd: 0,
        ajeAmount: 0,
        rjeAmount: 0,
        auditedEnd: 0,
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
  function updateRow(index: number, field: keyof M5DetailRow, value: string | number): void {
    if (index < 0 || index >= detailRows.value.length) return
    const row = detailRows.value[index] as any
    row[field] = value

    // 金额字段变动→重算公式列
    if (['beginning', 'accrual', 'capitalConversion', 'lossOffset'].includes(field as string)) {
      row.endBalance = calcEquityEndBalance(
        row.beginning,
        row.accrual,
        row.capitalConversion + row.lossOffset,
      )
    }
    if (['unadjBeginning', 'unadjAccrual', 'unadjConversion', 'unadjLossOffset'].includes(field as string)) {
      row.unadjEnd = calcEquityEndBalance(
        row.unadjBeginning,
        row.unadjAccrual,
        row.unadjConversion + row.unadjLossOffset,
      )
    }
    // 审定期末联动
    if (['unadjBeginning', 'unadjAccrual', 'unadjConversion', 'unadjLossOffset', 'ajeAmount', 'rjeAmount'].includes(field as string)) {
      const unadjEnd = calcEquityEndBalance(
        row.unadjBeginning,
        row.unadjAccrual,
        row.unadjConversion + row.unadjLossOffset,
      )
      row.unadjEnd = unadjEnd
      row.auditedEnd = unadjEnd + row.ajeAmount + row.rjeAmount
    }

    _triggerSave(index)
  }

  // ─── 5. 与M5-1审定表交叉验证 ─────────────────────────────────────────

  /**
   * 与M5-1审定表交叉验证（明细合计 vs 审定表分区块小计）
   */
  function crossValidateWithAdjudication(
    adjStatutoryTotal: number,
    adjDiscretionaryTotal: number,
  ): { statutoryDiff: number; discretionaryDiff: number; isMatch: boolean } {
    const statutoryDiff = statutorySubtotal.value.auditedEnd - adjStatutoryTotal
    const discretionaryDiff = discretionarySubtotal.value.auditedEnd - adjDiscretionaryTotal
    const isMatch = Math.abs(statutoryDiff) < 0.01 && Math.abs(discretionaryDiff) < 0.01
    return { statutoryDiff, discretionaryDiff, isMatch }
  }

  // ─── 6. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = detailRows.value[rowIndex]
    if (!row) return
    const n = rowIndex + 1
    debouncedSave(`M5-2-row-${n}-data`, {
      remark: JSON.stringify({
        key: row.key,
        segment: row.segment,
        sourceName: row.sourceName,
        beginning: row.beginning,
        accrual: row.accrual,
        capitalConversion: row.capitalConversion,
        lossOffset: row.lossOffset,
        unadjBeginning: row.unadjBeginning,
        unadjAccrual: row.unadjAccrual,
        unadjConversion: row.unadjConversion,
        unadjLossOffset: row.unadjLossOffset,
        ajeAmount: row.ajeAmount,
        rjeAmount: row.rjeAmount,
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
    // 区段
    activeSegment,
    switchSegment,

    // 计算属性
    computedRows,
    activeSegmentRows,

    // 区段小计（供M5-1交叉验证）
    statutorySubtotal,
    discretionarySubtotal,
    grandTotal,

    // 行操作
    addRow,
    removeRow,
    updateRow,

    // 交叉验证
    crossValidateWithAdjudication,
  }
}

export default useM5Detail
