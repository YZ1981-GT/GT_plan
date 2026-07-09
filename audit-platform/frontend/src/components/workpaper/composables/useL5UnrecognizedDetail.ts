/**
 * useL5UnrecognizedDetail — L5-3 未确认融资费用明细表 composable
 *
 * Spec: .kiro/specs/l5-long-term-payables/
 * Task: 3.4
 * Requirements: 3.3-3.6
 *
 * 职责：
 * - 30列备抵类方向（期末=初始-累计摊销）
 * - 与L5-2按款项一一对应
 * - 到期日分布统计
 * - 动态行增删
 * - 与L5-5摊销测算核对
 *
 * 科目：未确认融资费用（借方/负债备抵类！期末=期初+借方-贷方）
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcContraLiabilityEndBalance, calcSubtotal } from './useL5FormulaEngine'
import type { useL5FormData } from './useL5FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** L5-3 未确认融资费用明细行数据 */
export interface L5UnrecognizedRow {
  /** 行唯一标识（与L5-2款项对应） */
  key: string
  /** 款项名称 */
  payableName: string
  /** 债权人 */
  creditor: string
  /** 起始日期 */
  startDate: string
  /** 到期日期 */
  maturityDate: string
  /** 初始未确认融资费用 */
  initialUnrecognized: number
  /** 期初余额 */
  beginning: number
  /** 本期新增（借方） */
  periodIncrease: number
  /** 本期摊销（贷方，减少未确认） */
  periodAmortization: number
  /** 累计摊销 */
  cumulativeAmortization: number
  /** 未确认余额（公式列：初始-累计摊销） */
  unrecognizedBalance: number
  /** 实际利率（EIR） */
  effectiveRate: number
  /** 未审数 */
  unadjusted: number
  /** AJE */
  aje: number
  /** RJE */
  rje: number
  /** 审定数 */
  audited: number
  /** 备注 */
  remark: string
}

/** 到期日分布段 */
export interface MaturityDistribution {
  /** 1年以内 */
  within1Year: number
  /** 1-2年 */
  within2Years: number
  /** 2-3年 */
  within3Years: number
  /** 3-5年 */
  within5Years: number
  /** 5年以上 */
  over5Years: number
}

/** 区段Tab */
export type L5UnrecognizedSegment = 'basic' | 'amortization' | 'audit'

// ─── Constants ───────────────────────────────────────────────────────────────

/** 区段Tab定义 */
export const L5_UNRECOGNIZED_SEGMENTS = [
  {
    key: 'basic' as const,
    label: '基础信息',
    fields: ['payableName', 'creditor', 'startDate', 'maturityDate', 'initialUnrecognized', 'effectiveRate'],
  },
  {
    key: 'amortization' as const,
    label: '摊销信息',
    fields: ['beginning', 'periodIncrease', 'periodAmortization', 'cumulativeAmortization', 'unrecognizedBalance'],
  },
  {
    key: 'audit' as const,
    label: '审计调整',
    fields: ['unadjusted', 'aje', 'rje', 'audited', 'remark'],
  },
] as const

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L5-3 未确认融资费用明细表业务逻辑
 *
 * @param formData 由调用方传入的 useL5FormData 实例
 * @param unrecognizedRows reactive ref of rows
 */
export function useL5UnrecognizedDetail(
  formData: ReturnType<typeof useL5FormData>,
  unrecognizedRows: Ref<L5UnrecognizedRow[]>,
) {
  const { debouncedSave } = formData

  // ─── 1. 区段Tab状态 ────────────────────────────────────────────────────

  const activeSegment = ref<L5UnrecognizedSegment>('basic')

  function switchSegment(segment: L5UnrecognizedSegment): void {
    activeSegment.value = segment
  }

  // ─── 2. 计算属性 ──────────────────────────────────────────────────────

  /** 各行未确认余额自动计算：初始 - 累计摊销 */
  const computedRows: ComputedRef<L5UnrecognizedRow[]> = computed(() => {
    return unrecognizedRows.value.map(row => ({
      ...row,
      // 未确认余额 = 初始未确认 - 累计摊销
      unrecognizedBalance: row.initialUnrecognized - row.cumulativeAmortization,
    }))
  })

  /** 未确认余额合计（供L5-5交叉验证） */
  const totalUnrecognizedBalance: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.unrecognizedBalance))
  })

  /** 本期摊销合计 */
  const totalPeriodAmortization: ComputedRef<number> = computed(() => {
    return calcSubtotal(unrecognizedRows.value.map(r => r.periodAmortization))
  })

  /** 初始未确认融资费用合计 */
  const totalInitialUnrecognized: ComputedRef<number> = computed(() => {
    return calcSubtotal(unrecognizedRows.value.map(r => r.initialUnrecognized))
  })

  // ─── 3. 到期日分布统计 ────────────────────────────────────────────────

  /** 按到期日分布统计未确认融资费用余额 */
  const maturityDistribution: ComputedRef<MaturityDistribution> = computed(() => {
    const now = new Date()
    const result: MaturityDistribution = {
      within1Year: 0,
      within2Years: 0,
      within3Years: 0,
      within5Years: 0,
      over5Years: 0,
    }

    for (const row of computedRows.value) {
      if (!row.maturityDate) continue
      const maturity = new Date(row.maturityDate)
      const diffYears = (maturity.getTime() - now.getTime()) / (365.25 * 24 * 60 * 60 * 1000)

      if (diffYears <= 1) {
        result.within1Year += row.unrecognizedBalance
      } else if (diffYears <= 2) {
        result.within2Years += row.unrecognizedBalance
      } else if (diffYears <= 3) {
        result.within3Years += row.unrecognizedBalance
      } else if (diffYears <= 5) {
        result.within5Years += row.unrecognizedBalance
      } else {
        result.over5Years += row.unrecognizedBalance
      }
    }

    return result
  })

  // ─── 4. 动态行增删 ────────────────────────────────────────────────────

  /**
   * 新增未确认融资费用明细行（与L5-2对应）
   */
  async function addRow(): Promise<void> {
    try {
      const { value: payableName } = await ElMessageBox.prompt(
        '请输入对应款项名称（应与L5-2明细对应）',
        '新增未确认融资费用明细',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '如：XX融资租赁',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '款项名称不能为空'
            return true
          },
        },
      )

      const key = `l5-unrec-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const newRow: L5UnrecognizedRow = {
        key,
        payableName: payableName?.trim() || '',
        creditor: '',
        startDate: '',
        maturityDate: '',
        initialUnrecognized: 0,
        beginning: 0,
        periodIncrease: 0,
        periodAmortization: 0,
        cumulativeAmortization: 0,
        unrecognizedBalance: 0,
        effectiveRate: 0,
        unadjusted: 0,
        aje: 0,
        rje: 0,
        audited: 0,
        remark: '',
      }

      unrecognizedRows.value.push(newRow)
      _triggerSave()
    } catch {
      // 用户取消
    }
  }

  /** 删除指定行 */
  function removeRow(index: number): void {
    if (index < 0 || index >= unrecognizedRows.value.length) return
    unrecognizedRows.value.splice(index, 1)
    _triggerSave()
  }

  /** 更新某行某字段 */
  function updateRow(index: number, field: keyof L5UnrecognizedRow, value: string | number): void {
    if (index < 0 || index >= unrecognizedRows.value.length) return
    const row = unrecognizedRows.value[index] as any
    row[field] = value

    // 如果是累计摊销或初始未确认变化，重算余额
    if (['initialUnrecognized', 'cumulativeAmortization'].includes(field)) {
      row.unrecognizedBalance = row.initialUnrecognized - row.cumulativeAmortization
    }

    _triggerSave()
  }

  // ─── 5. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(): void {
    // 序列化为JSON供CrossSheet勾稽
    debouncedSave('L5-L5-3-rows', {
      remark: JSON.stringify(unrecognizedRows.value.map(r => ({
        key: r.key,
        payableName: r.payableName,
        unrecognizedBalance: r.initialUnrecognized - r.cumulativeAmortization,
        initialUnrecognized: r.initialUnrecognized,
        cumulativeAmortization: r.cumulativeAmortization,
        periodAmortization: r.periodAmortization,
      }))),
    })
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 区段Tab
    activeSegment,
    switchSegment,

    // 计算属性
    computedRows,
    totalUnrecognizedBalance,
    totalPeriodAmortization,
    totalInitialUnrecognized,

    // 到期日分布
    maturityDistribution,

    // 行操作
    addRow,
    removeRow,
    updateRow,
  }
}

export default useL5UnrecognizedDetail
