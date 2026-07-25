/**
 * useN1Adjudication — 审定表N1-1 逻辑层
 *
 * Spec: .kiro/specs/n1-deferred-tax-assets/
 * Task: 3.4
 * Requirements: 2.1-2.9
 *
 * 职责：
 * - 9大类暂时性差异项目行管理（资产减值准备/可弥补亏损/内部交易未实现利润/公允价值变动/预提费用/递延收益/合同负债/股份支付/其他）
 * - 列结构：期初(未审/AJE/RJE/审定) + 期末(未审/AJE/RJE/审定) + 比较(变动额×2/变动率×2) + 原因分析
 * - 公式：审定数=未审+AJE+RJE；资产类期末=期初+借-贷
 * - 交叉验证：vs N1-2明细合计（useN1CrossSheet）
 * - TB回写：审定数变化 → trial_balance 1811期末余额
 * - 审计说明+结论
 *
 * 科目：1811 递延所得税资产（**借方/资产类**！期末余额=期初+借-贷）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcSubtotal,
  calcChangeProportion,
  parseNum,
} from './useN1FormulaEngine'
import type { useN1FormData } from './useN1FormData'
import type { useN1CrossSheet } from './useN1CrossSheet'

// ─── Types ───────────────────────────────────────────────────────────────────

/**
 * 审定表行分类（对齐致同源模板 N1-1 审定表 A7~A13 固定7类资产侧暂时性差异）
 * 源模板顺序：资产减值准备/可抵扣亏损/内部交易未实现利润/公允价值变动/租赁负债/
 *            购入摊销年限小于税法规定的资产/其他
 */
export type N1AdjudicationCategory =
  | '资产减值准备'
  | '可抵扣亏损'
  | '内部交易未实现利润'
  | '公允价值变动'
  | '租赁负债'
  | '购入摊销年限小于税法规定的资产'
  | '其他'

/** 审定表单行数据（可编辑字段） */
export interface N1AdjudicationRow {
  /** 暂时性差异项目分类 */
  category: N1AdjudicationCategory
  /** 期初未审数 */
  beginUnadjusted: number
  /** 期初AJE */
  beginAje: number
  /** 期初RJE */
  beginRje: number
  /** 期末未审数 */
  endUnadjusted: number
  /** 期末AJE */
  endAje: number
  /** 期末RJE */
  endRje: number
  /** 原因分析（文本） */
  reason: string
}

/** 审定表行计算结果 */
export interface N1AdjudicationComputed extends N1AdjudicationRow {
  /** 期初审定数 = beginUnadjusted + beginAje + beginRje */
  beginAudited: number
  /** 期末审定数 = endUnadjusted + endAje + endRje */
  endAudited: number
  /** 变动额（未审）= 期末未审 - 期初未审 */
  changeUnadjusted: number
  /** 变动额（审定）= 期末审定 - 期初审定 */
  changeAudited: number
  /** 变动率（未审）*/
  changeRateUnadjusted: number
  /** 变动率（审定）*/
  changeRateAudited: number
}

/** 审定表合计行 */
export interface N1AdjudicationTotals {
  beginUnadjusted: number
  beginAje: number
  beginRje: number
  beginAudited: number
  endUnadjusted: number
  endAje: number
  endRje: number
  endAudited: number
  changeUnadjusted: number
  changeAudited: number
}

export interface UseN1AdjudicationOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  formData: ReturnType<typeof useN1FormData>
  crossSheet?: ReturnType<typeof useN1CrossSheet>
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 源模板 N1-1 审定表固定7类资产侧暂时性差异项目（A7~A13） */
export const N1_ADJUDICATION_CATEGORIES: N1AdjudicationCategory[] = [
  '资产减值准备',
  '可抵扣亏损',
  '内部交易未实现利润',
  '公允价值变动',
  '租赁负债',
  '购入摊销年限小于税法规定的资产',
  '其他',
]

const ITEM_PREFIX = 'N1-1-adj'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useN1Adjudication(options: UseN1AdjudicationOptions) {
  const { allResponses, formData } = options

  // ─── 1. 数据行（从 allResponses 恢复或初始化） ───────────────────────────

  const rows = ref<N1AdjudicationRow[]>(_initRows())

  function _initRows(): N1AdjudicationRow[] {
    return N1_ADJUDICATION_CATEGORIES.map((cat, i) => {
      const stored = allResponses.value.get(`${ITEM_PREFIX}-${i}`)
      if (stored?.conclusion) {
        try {
          return { category: cat, ...JSON.parse(stored.conclusion) }
        } catch { /* fallback */ }
      }
      return _emptyRow(cat)
    })
  }

  function _emptyRow(category: N1AdjudicationCategory): N1AdjudicationRow {
    return {
      category,
      beginUnadjusted: 0,
      beginAje: 0,
      beginRje: 0,
      endUnadjusted: 0,
      endAje: 0,
      endRje: 0,
      reason: '',
    }
  }

  // ─── 2. 计算属性：公式列自动计算 ──────────────────────────────────────────

  const computedRows: ComputedRef<N1AdjudicationComputed[]> = computed(() => {
    return rows.value.map((row) => {
      const beginAudited = calcAuditedAmount(row.beginUnadjusted, row.beginAje, row.beginRje)
      const endAudited = calcAuditedAmount(row.endUnadjusted, row.endAje, row.endRje)
      const changeUnadjusted = parseNum(row.endUnadjusted) - parseNum(row.beginUnadjusted)
      const changeAudited = endAudited - beginAudited
      return {
        ...row,
        beginAudited,
        endAudited,
        changeUnadjusted,
        changeAudited,
        changeRateUnadjusted: calcChangeProportion(changeUnadjusted, row.beginUnadjusted),
        changeRateAudited: calcChangeProportion(changeAudited, beginAudited),
      }
    })
  })

  // ─── 3. 合计行 ─────────────────────────────────────────────────────────

  const totals: ComputedRef<N1AdjudicationTotals> = computed(() => {
    const r = computedRows.value
    const beginAudited = calcSubtotal(r.map(x => x.beginAudited))
    const endAudited = calcSubtotal(r.map(x => x.endAudited))
    return {
      beginUnadjusted: calcSubtotal(r.map(x => x.beginUnadjusted)),
      beginAje: calcSubtotal(r.map(x => x.beginAje)),
      beginRje: calcSubtotal(r.map(x => x.beginRje)),
      beginAudited,
      endUnadjusted: calcSubtotal(r.map(x => x.endUnadjusted)),
      endAje: calcSubtotal(r.map(x => x.endAje)),
      endRje: calcSubtotal(r.map(x => x.endRje)),
      endAudited,
      changeUnadjusted: calcSubtotal(r.map(x => x.changeUnadjusted)),
      changeAudited: endAudited - beginAudited,
    }
  })

  // ─── 4. 行操作 ─────────────────────────────────────────────────────────

  /** 更新行可编辑字段 */
  function updateRow(
    index: number,
    field: keyof Omit<N1AdjudicationRow, 'category'>,
    value: number | string,
  ): void {
    if (index < 0 || index >= rows.value.length) return
    ;(rows.value[index] as any)[field] = value
    _persistRow(index)
  }

  /** 添加调整（aje/rje 累加到对应期） */
  function addAdjustment(index: number, period: 'begin' | 'end', type: 'aje' | 'rje', amount: number): void {
    if (index < 0 || index >= rows.value.length) return
    const field = period === 'begin'
      ? (type === 'aje' ? 'beginAje' : 'beginRje')
      : (type === 'aje' ? 'endAje' : 'endRje')
    rows.value[index][field] += parseNum(amount)
    _persistRow(index)
  }

  /** 移除调整（对应字段归零） */
  function removeAdjustment(index: number, period: 'begin' | 'end', type: 'aje' | 'rje'): void {
    if (index < 0 || index >= rows.value.length) return
    const field = period === 'begin'
      ? (type === 'aje' ? 'beginAje' : 'beginRje')
      : (type === 'aje' ? 'endAje' : 'endRje')
    rows.value[index][field] = 0
    _persistRow(index)
  }

  // ─── 5. 审计结论 + 说明 ────────────────────────────────────────────────

  const auditConclusion = ref<string>(
    allResponses.value.get('N1-1-conclusion')?.conclusion || '',
  )
  const auditNotes = ref<string>(
    allResponses.value.get('N1-1-notes')?.remark || '',
  )

  // ─── 6. 持久化 ─────────────────────────────────────────────────────────

  function _persistRow(index: number): void {
    const row = rows.value[index]
    const { category: _cat, ...data } = row
    formData.debouncedSave(`${ITEM_PREFIX}-${index}`, {
      conclusion: JSON.stringify(data),
    })
  }

  /** 持久化合计（供 crossSheet 读取） */
  function _persistTotals(): void {
    formData.saveField('N1-1-total-audited', { remark: String(totals.value.endAudited) })
    formData.saveField('N1-1-total-begin', { remark: String(totals.value.beginAudited) })
  }

  // ─── 7. TB回写触发（审定数变化） ───────────────────────────────────────

  watch(
    () => totals.value.endAudited,
    async (newVal, oldVal) => {
      if (oldVal !== undefined && newVal !== oldVal) {
        _persistTotals()
        await formData.writebackTB(newVal)
      }
    },
  )

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    rows: computedRows,
    totals,
    addAdjustment,
    removeAdjustment,
    updateRow,
    auditConclusion,
    auditNotes,
  }
}

export default useN1Adjudication
