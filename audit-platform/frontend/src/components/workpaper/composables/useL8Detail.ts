/**
 * useL8Detail — L8-2 明细表 composable（23列区段Tab管理）
 *
 * Spec: .kiro/specs/l8-financial-expenses/
 * Task: 3.4
 * Requirements: 3.1-3.6
 *
 * 职责：
 * - 23列按区段Tab管理（费用项目/月度金额/期末汇总+审定，行同步）
 * - 行结构：利息费用总额/减利息资本化/利息费用/减利息收入/利息净支出
 *   /未确认融资费用/减未实现融资收益/.../合计
 * - 公式：
 *   N=SUM(B:M)（本期未审合计=1月~12月之和）
 *   Q=N+O+P（本期审定=未审合计+AJE+RJE）
 *   R=Q/Q合计（占比）
 *   W=T+U+V（上期审定=上期未审+上期AJE+上期RJE）
 * - 自动计算净财务费用（calcNetFinanceExpense）
 * - 变动率计算 + 异常高亮
 * - 与审定表L8-1交叉验证
 *
 * 科目：6603 财务费用（借方/损益类！取发生额）
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  calcAuditedAmount,
  calcSubtotal,
  calcChangeRate,
  calcChangeAmount,
  calcNetFinanceExpense,
  isChangeRateExceeding,
} from './useL8FormulaEngine'
import type { useL8FormData } from './useL8FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** L8-2 明细表行数据（23列） */
export interface L8DetailRow {
  /** 行唯一标识 */
  key: string
  /** 费用项目名称（A列） */
  itemName: string
  /** 1月~12月发生额（B~M列） */
  monthly: [number, number, number, number, number, number, number, number, number, number, number, number]
  /** 本期未审合计（N列，公式=SUM(B:M)） */
  periodUnadjusted: number
  /** AJE（O列） */
  aje: number
  /** RJE（P列） */
  rje: number
  /** 本期审定（Q列，公式=N+O+P） */
  periodAudited: number
  /** 占比（R列，公式=Q/Q合计行×100） */
  ratio: number
  /** 与相关科目勾稽（S列，备注文本） */
  crossRef: string
  /** 上期未审（T列） */
  priorUnadjusted: number
  /** 上期AJE（U列） */
  priorAje: number
  /** 上期RJE（V列） */
  priorRje: number
  /** 上期审定（W列，公式=T+U+V） */
  priorAudited: number
}

/** 区段Tab类型 */
export type L8DetailSegment = 'items' | 'monthly' | 'summary'

// ─── Constants ───────────────────────────────────────────────────────────────

/** 区段Tab定义：23列拆3段 */
export const L8_DETAIL_SEGMENTS = [
  {
    key: 'items' as const,
    label: '费用项目',
    fields: ['itemName', 'crossRef'],
  },
  {
    key: 'monthly' as const,
    label: '月度金额(1月~12月)',
    fields: ['monthly'],
  },
  {
    key: 'summary' as const,
    label: '期末汇总+审定',
    fields: [
      'periodUnadjusted', 'aje', 'rje', 'periodAudited', 'ratio',
      'priorUnadjusted', 'priorAje', 'priorRje', 'priorAudited',
    ],
  },
] as const

/** 默认费用明细行（对齐L8-1审定表结构） */
export const L8_DETAIL_DEFAULT_ITEMS = [
  '利息费用总额',
  '减：利息资本化',
  '利息费用',
  '减：利息收入',
  '利息净支出',
  '未确认融资费用',
  '减：未实现融资收益',
  '承兑汇票贴息',
  '汇兑损失',
  '减：汇兑收益',
  '减：汇兑损益资本化',
  '手续费及其他',
]

/** 变动率异常阈值（20%） */
const CHANGE_RATE_THRESHOLD = 20

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L8-2 明细表业务逻辑（23列区段Tab）
 *
 * @param formData 由调用方传入的 useL8FormData 实例
 * @param detailRows reactive ref of detail rows
 */
export function useL8Detail(
  formData: ReturnType<typeof useL8FormData>,
  detailRows: Ref<L8DetailRow[]>,
) {
  const { debouncedSave } = formData

  // ─── 1. 区段Tab状态 ────────────────────────────────────────────────────

  const activeSegment = ref<L8DetailSegment>('items')

  function switchSegment(segment: L8DetailSegment): void {
    activeSegment.value = segment
  }

  // ─── 2. 计算属性：公式列自动计算 ─────────────────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<L8DetailRow[]> = computed(() => {
    // 先计算各行审定数以确定合计行审定值（用于占比计算）
    const rowsWithFormulas = detailRows.value.map(row => {
      // N=SUM(B:M) 本期未审合计
      const periodUnadjusted = calcSubtotal(row.monthly as unknown as number[])
      // Q=N+O+P 本期审定
      const periodAudited = calcAuditedAmount(periodUnadjusted, row.aje, row.rje)
      // W=T+U+V 上期审定
      const priorAudited = calcAuditedAmount(row.priorUnadjusted, row.priorAje, row.priorRje)
      return { ...row, periodUnadjusted, periodAudited, priorAudited }
    })

    // 计算合计行的审定数（用于占比）
    const totalAudited = calcSubtotal(rowsWithFormulas.map(r => r.periodAudited))

    // 添加占比列
    return rowsWithFormulas.map(row => ({
      ...row,
      ratio: totalAudited !== 0 ? (row.periodAudited / totalAudited) * 100 : 0,
    }))
  })

  // ─── 3. 合计行 ────────────────────────────────────────────────────────

  /** 本期审定合计（供L8-1交叉验证） */
  const totalPeriodAudited: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.periodAudited))
  })

  /** 上期审定合计 */
  const totalPriorAudited: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.priorAudited))
  })

  /** 变动率（合计行） */
  const totalChangeRate: ComputedRef<number | 'N/A'> = computed(() => {
    return calcChangeRate(totalPeriodAudited.value, totalPriorAudited.value)
  })

  /** 变动额（合计行） */
  const totalChangeAmount: ComputedRef<number> = computed(() => {
    return calcChangeAmount(totalPeriodAudited.value, totalPriorAudited.value)
  })

  // ─── 4. 异常变动率行 ──────────────────────────────────────────────────

  /** 变动率超阈值的行索引 */
  const abnormalRows: ComputedRef<number[]> = computed(() => {
    const indices: number[] = []
    computedRows.value.forEach((row, idx) => {
      const rate = calcChangeRate(row.periodAudited, row.priorAudited)
      if (isChangeRateExceeding(rate, CHANGE_RATE_THRESHOLD)) {
        indices.push(idx)
      }
    })
    return indices
  })

  // ─── 5. 动态行增删 ────────────────────────────────────────────────────

  /**
   * 新增明细行（先弹 ElMessageBox.prompt 输入项目名称）
   */
  async function addRow(): Promise<void> {
    try {
      const { value: itemName } = await ElMessageBox.prompt(
        '请输入费用项目名称',
        '新增明细项目',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '如：银行手续费/保函费/信用证费用',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '项目名称不能为空'
            return true
          },
        },
      )

      const key = `l8-detail-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const newRow: L8DetailRow = {
        key,
        itemName: itemName?.trim() || '',
        monthly: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        periodUnadjusted: 0,
        aje: 0,
        rje: 0,
        periodAudited: 0,
        ratio: 0,
        crossRef: '',
        priorUnadjusted: 0,
        priorAje: 0,
        priorRje: 0,
        priorAudited: 0,
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
    _triggerSaveAll()
  }

  /** 更新某行某字段 */
  function updateRow(index: number, field: keyof L8DetailRow, value: any): void {
    if (index < 0 || index >= detailRows.value.length) return
    const row = detailRows.value[index] as any
    row[field] = value
    _triggerSave(index)
  }

  /** 更新某行某月金额（B~M列） */
  function updateMonthly(rowIndex: number, monthIndex: number, value: number): void {
    if (rowIndex < 0 || rowIndex >= detailRows.value.length) return
    if (monthIndex < 0 || monthIndex > 11) return
    detailRows.value[rowIndex].monthly[monthIndex] = value
    _triggerSave(rowIndex)
  }

  // ─── 6. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = detailRows.value[rowIndex]
    if (!row) return
    const computed = computedRows.value[rowIndex]
    // 保存净发生额（供CrossSheet勾稽）
    if (computed) {
      debouncedSave(`L8-2-row-${rowIndex}-audited`, {
        remark: String(computed.periodAudited),
      })
    }
    // 保存行完整数据
    debouncedSave(`L8-2-row-${rowIndex}-data`, {
      remark: JSON.stringify({
        key: row.key,
        itemName: row.itemName,
        monthly: row.monthly,
        aje: row.aje,
        rje: row.rje,
        priorUnadjusted: row.priorUnadjusted,
        priorAje: row.priorAje,
        priorRje: row.priorRje,
        crossRef: row.crossRef,
      }),
    })
    // 保存明细表净财务费用合计（供 CrossSheet 交叉验证）
    debouncedSave('L8-2-netFinExpense', {
      remark: String(totalPeriodAudited.value),
    })
    // 🔴 修复：保存完整行到 L8-2-full-data（组件 _restoreRows 读此键；此前从不写 → 刷新数据全丢）
    debouncedSave('L8-2-full-data', {
      remark: JSON.stringify(detailRows.value),
    })
  }

  function _triggerSaveAll(): void {
    computedRows.value.forEach((_, i) => {
      _triggerSave(i)
    })
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 区段Tab
    activeSegment,
    switchSegment,

    // 计算属性
    computedRows,
    totalPeriodAudited,
    totalPriorAudited,
    totalChangeRate,
    totalChangeAmount,
    abnormalRows,

    // 行操作
    addRow,
    removeRow,
    updateRow,
    updateMonthly,
  }
}

export default useL8Detail
