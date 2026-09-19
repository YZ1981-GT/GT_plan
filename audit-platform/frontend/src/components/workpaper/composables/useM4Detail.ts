/**
 * useM4Detail — M4-2 明细表 composable
 *
 * Spec: .kiro/specs/m4-capital-reserve/
 * Task: 3.4
 * Requirements: 3.1-3.6
 *
 * 职责：
 * - 管理两区段：资本溢价明细（出资超面值部分）+ 其他资本公积明细
 * - 24列宽表拆2区段Tab（资本溢价/其他资本公积，行同步）
 * - 权益类贷方期末：期末=期初+本期增加(贷方)-本期减少(借方)
 * - 31公式实时计算
 * - 动态行新增（ElMessageBox.prompt 输入来源项目名）
 * - 与M4-1审定表交叉验证（emit分类小计）
 * - 接收J3股份支付/M2外币折算差异
 *
 * 科目：4002 资本公积（**贷方/权益类！期末=期初+贷方-借方**）
 * 50×24 结构，31唯一模式公式
 */
import { computed, ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcEquityEndBalance, calcSubtotal } from './useM4FormulaEngine'
import type { useM4FormData } from './useM4FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 明细表区段类型 */
export type M4DetailSegment = 'premium' | 'other'

/** M4-2 明细表行数据（24列结构） */
export interface M4DetailRow {
  /** 行唯一标识 */
  key: string
  /** 所属区段：premium=资本溢价/股本溢价, other=其他资本公积 */
  segment: M4DetailSegment
  /** 来源项目名称（如：某投资者出资溢价/J3股份支付等） */
  sourceName: string
  /** 期初余额（贷方余额） */
  beginning: number
  /** 本期增加（贷方发生） */
  increase: number
  /** 本期减少（借方发生） */
  decrease: number
  /** 期末余额（公式=期初+增加-减少，权益类贷方！） */
  endBalance: number
  /** 变动原因 */
  reason: string
  /** 未审期初 */
  unadjBeginning: number
  /** 未审增加 */
  unadjIncrease: number
  /** 未审减少 */
  unadjDecrease: number
  /** 未审期末 */
  unadjEnd: number
  /** 账项调整-期初 */
  ajeBeginning: number
  /** 账项调整-增加 */
  ajeIncrease: number
  /** 账项调整-减少 */
  ajeDecrease: number
  /** 重分类-期初 */
  rjeBeginning: number
  /** 重分类-增加 */
  rjeIncrease: number
  /** 重分类-减少 */
  rjeDecrease: number
  /** 审定期初（=未审期初+AJE期初+RJE期初） */
  auditedBeginning: number
  /** 审定增加（=未审增加+AJE增加+RJE增加） */
  auditedIncrease: number
  /** 审定减少（=未审减少+AJE减少+RJE减少） */
  auditedDecrease: number
  /** 审定期末（=审定期初+审定增加-审定减少，权益类！） */
  auditedEnd: number
  /** 来源索引（GtIndexChip跳转如J3/M2） */
  refIndex: string
  /** 备注 */
  remark: string
}

/** 区段小计 */
export interface M4DetailSubtotal {
  beginning: number
  increase: number
  decrease: number
  endBalance: number
  auditedBeginning: number
  auditedIncrease: number
  auditedDecrease: number
  auditedEnd: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 区段Tab定义 */
export const M4_DETAIL_SEGMENTS = [
  { key: 'premium' as const, label: '资本溢价（股本溢价）' },
  { key: 'other' as const, label: '其他资本公积' },
] as const

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M4-2 明细表业务逻辑（双区段Tab+动态行+24列+31公式）
 *
 * @param formData 由调用方传入的 useM4FormData 实例
 * @param detailRows reactive ref of detail rows
 */
export function useM4Detail(
  formData: ReturnType<typeof useM4FormData>,
  detailRows: { value: M4DetailRow[] },
) {
  const { debouncedSave } = formData

  // ─── 1. 区段Tab状态 ────────────────────────────────────────────────────

  const activeSegment = ref<M4DetailSegment>('premium')

  function switchSegment(segment: M4DetailSegment): void {
    activeSegment.value = segment
  }

  // ─── 2. 计算属性：公式列自动计算（31公式） ────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<M4DetailRow[]> = computed(() => {
    return detailRows.value.map(row => {
      // 权益类贷方：期末=期初+增加(贷方)-减少(借方)
      const endBalance = calcEquityEndBalance(row.beginning, row.increase, row.decrease)
      // 未审期末
      const unadjEnd = calcEquityEndBalance(row.unadjBeginning, row.unadjIncrease, row.unadjDecrease)
      // 审定期初=未审期初+AJE期初+RJE期初
      const auditedBeginning = row.unadjBeginning + row.ajeBeginning + row.rjeBeginning
      // 审定增加=未审增加+AJE增加+RJE增加
      const auditedIncrease = row.unadjIncrease + row.ajeIncrease + row.rjeIncrease
      // 审定减少=未审减少+AJE减少+RJE减少
      const auditedDecrease = row.unadjDecrease + row.ajeDecrease + row.rjeDecrease
      // 审定期末=审定期初+审定增加-审定减少（权益类！）
      const auditedEnd = calcEquityEndBalance(auditedBeginning, auditedIncrease, auditedDecrease)

      return {
        ...row,
        endBalance,
        unadjEnd,
        auditedBeginning,
        auditedIncrease,
        auditedDecrease,
        auditedEnd,
      }
    })
  })

  /** 当前活动区段的行 */
  const activeSegmentRows: ComputedRef<M4DetailRow[]> = computed(() => {
    return computedRows.value.filter(r => r.segment === activeSegment.value)
  })

  // ─── 3. 区段小计（供M4-1交叉验证） ───────────────────────────────────

  /** 资本溢价区段小计 */
  const premiumSubtotal: ComputedRef<M4DetailSubtotal> = computed(() => {
    return _calcSegmentSubtotal('premium')
  })

  /** 其他资本公积区段小计 */
  const otherSubtotal: ComputedRef<M4DetailSubtotal> = computed(() => {
    return _calcSegmentSubtotal('other')
  })

  /** 全部合计 */
  const grandTotal: ComputedRef<M4DetailSubtotal> = computed(() => {
    const r = computedRows.value
    return {
      beginning: calcSubtotal(r.map(x => x.beginning)),
      increase: calcSubtotal(r.map(x => x.increase)),
      decrease: calcSubtotal(r.map(x => x.decrease)),
      endBalance: calcSubtotal(r.map(x => x.endBalance)),
      auditedBeginning: calcSubtotal(r.map(x => x.auditedBeginning)),
      auditedIncrease: calcSubtotal(r.map(x => x.auditedIncrease)),
      auditedDecrease: calcSubtotal(r.map(x => x.auditedDecrease)),
      auditedEnd: calcSubtotal(r.map(x => x.auditedEnd)),
    }
  })

  function _calcSegmentSubtotal(segment: M4DetailSegment): M4DetailSubtotal {
    const r = computedRows.value.filter(x => x.segment === segment)
    return {
      beginning: calcSubtotal(r.map(x => x.beginning)),
      increase: calcSubtotal(r.map(x => x.increase)),
      decrease: calcSubtotal(r.map(x => x.decrease)),
      endBalance: calcSubtotal(r.map(x => x.endBalance)),
      auditedBeginning: calcSubtotal(r.map(x => x.auditedBeginning)),
      auditedIncrease: calcSubtotal(r.map(x => x.auditedIncrease)),
      auditedDecrease: calcSubtotal(r.map(x => x.auditedDecrease)),
      auditedEnd: calcSubtotal(r.map(x => x.auditedEnd)),
    }
  }

  // ─── 4. 动态行增删 ────────────────────────────────────────────────────

  /**
   * 新增明细行（先弹 ElMessageBox.prompt 输入来源项目名）
   */
  async function addRow(segment?: M4DetailSegment): Promise<void> {
    const targetSegment = segment || activeSegment.value
    const segmentLabel = targetSegment === 'premium' ? '资本溢价' : '其他资本公积'

    try {
      const { value: sourceName } = await ElMessageBox.prompt(
        `请输入${segmentLabel}明细来源项目名称`,
        '新增明细行',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: targetSegment === 'premium'
            ? '如：某投资者出资溢价'
            : '如：J3股份支付权益结算',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '来源项目名称不能为空'
            return true
          },
        },
      )

      const key = `m4-det-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const newRow: M4DetailRow = {
        key,
        segment: targetSegment,
        sourceName: sourceName?.trim() || '',
        beginning: 0,
        increase: 0,
        decrease: 0,
        endBalance: 0,
        reason: '',
        unadjBeginning: 0,
        unadjIncrease: 0,
        unadjDecrease: 0,
        unadjEnd: 0,
        ajeBeginning: 0,
        ajeIncrease: 0,
        ajeDecrease: 0,
        rjeBeginning: 0,
        rjeIncrease: 0,
        rjeDecrease: 0,
        auditedBeginning: 0,
        auditedIncrease: 0,
        auditedDecrease: 0,
        auditedEnd: 0,
        refIndex: '',
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
  function updateRow(index: number, field: keyof M4DetailRow, value: string | number): void {
    if (index < 0 || index >= detailRows.value.length) return
    const row = detailRows.value[index] as any
    row[field] = value

    // 金额字段变动→重算公式列
    if (['beginning', 'increase', 'decrease'].includes(field as string)) {
      row.endBalance = calcEquityEndBalance(row.beginning, row.increase, row.decrease)
    }
    if (['unadjBeginning', 'unadjIncrease', 'unadjDecrease'].includes(field as string)) {
      row.unadjEnd = calcEquityEndBalance(row.unadjBeginning, row.unadjIncrease, row.unadjDecrease)
    }
    // 审定列联动
    const auditedFields = ['unadjBeginning', 'ajeBeginning', 'rjeBeginning', 'unadjIncrease', 'ajeIncrease', 'rjeIncrease', 'unadjDecrease', 'ajeDecrease', 'rjeDecrease']
    if (auditedFields.includes(field as string)) {
      row.auditedBeginning = row.unadjBeginning + row.ajeBeginning + row.rjeBeginning
      row.auditedIncrease = row.unadjIncrease + row.ajeIncrease + row.rjeIncrease
      row.auditedDecrease = row.unadjDecrease + row.ajeDecrease + row.rjeDecrease
      row.auditedEnd = calcEquityEndBalance(row.auditedBeginning, row.auditedIncrease, row.auditedDecrease)
    }

    _triggerSave(index)
  }

  // ─── 5. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = detailRows.value[rowIndex]
    if (!row) return
    const n = rowIndex + 1
    debouncedSave(`M4-2-row-${n}-data`, {
      remark: JSON.stringify({
        key: row.key,
        segment: row.segment,
        sourceName: row.sourceName,
        beginning: row.beginning,
        increase: row.increase,
        decrease: row.decrease,
        reason: row.reason,
        unadjBeginning: row.unadjBeginning,
        unadjIncrease: row.unadjIncrease,
        unadjDecrease: row.unadjDecrease,
        ajeBeginning: row.ajeBeginning,
        ajeIncrease: row.ajeIncrease,
        ajeDecrease: row.ajeDecrease,
        rjeBeginning: row.rjeBeginning,
        rjeIncrease: row.rjeIncrease,
        rjeDecrease: row.rjeDecrease,
        refIndex: row.refIndex,
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
    activeSegmentRows,

    // 区段小计（供M4-1交叉验证）
    premiumSubtotal,
    otherSubtotal,
    grandTotal,

    // 行操作
    addRow,
    removeRow,
    updateRow,
  }
}

export default useM4Detail
