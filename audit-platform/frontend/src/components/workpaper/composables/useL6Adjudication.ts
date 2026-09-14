/**
 * useL6Adjudication — L6-1 审定表 composable
 *
 * Spec: .kiro/specs/l6-special-payables/
 * Task: 3.4
 * Requirements: 2.1-2.7
 *
 * 职责：
 * - 管理专项应付款审定数据（按专项项目分类+小计）
 * - 列结构（来源xlsx L6-1）：
 *   项目(A) | 期初(未审B/AJE_C/RJE_D/审定E) | 期末(未审F/AJE_G/RJE_H/审定I) | 变动额J | 变动率K
 * - 审定数公式：审定=未审+AJE+RJE
 * - 负债类：期末=期初+贷方-借方
 * - 审定数变化→writebackTB(2601)+EventBus
 * - subscribe附注刷新
 *
 * 科目：2601 专项应付款（贷方/负债类！期末=期初+贷方-借方）
 */
import { computed, watch, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
  calcVariance,
  calcVarianceRate,
} from './useL6FormulaEngine'
import type { useL6FormData } from './useL6FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表行数据（对应xlsx L6-1 各专项项目行） */
export interface L6AdjudicationRow {
  /** 行唯一标识 */
  key: string
  /** 专项项目名称（A列） */
  project: string
  /** 期初未审数（B列） */
  beginUnadjusted: number
  /** 期初AJE（C列） */
  beginAje: number
  /** 期初RJE（D列） */
  beginRje: number
  /** 期初审定数（E列，公式=B+C+D） */
  beginAudited: number
  /** 期末未审数（F列） */
  endUnadjusted: number
  /** 期末AJE（G列） */
  endAje: number
  /** 期末RJE（H列） */
  endRje: number
  /** 期末审定数（I列，公式=F+G+H） */
  endAudited: number
  /** 变动额（J列，公式=I-E） */
  variance: number
  /** 变动率（K列） */
  varianceRate: number
}

/** 合计行数据 */
export interface L6AdjudicationTotal {
  beginUnadjusted: number
  beginAje: number
  beginRje: number
  beginAudited: number
  endUnadjusted: number
  endAje: number
  endRje: number
  endAudited: number
  variance: number
  varianceRate: number
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L6-1 审定表业务逻辑（单区块负债类+按专项项目+合计）
 *
 * @param formData 由调用方传入的 useL6FormData 实例
 * @param rows reactive ref of adjudication rows
 */
export function useL6Adjudication(
  formData: ReturnType<typeof useL6FormData>,
  rows: { value: L6AdjudicationRow[] },
) {
  const { writebackTB, saveBatch, debouncedSave } = formData

  // ─── 1. 计算属性：公式列自动计算 ──────────────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<L6AdjudicationRow[]> = computed(() => {
    return rows.value.map(row => {
      const beginAudited = calcAuditedAmount(row.beginUnadjusted, row.beginAje, row.beginRje)
      const endAudited = calcAuditedAmount(row.endUnadjusted, row.endAje, row.endRje)
      const variance = calcVariance(endAudited, beginAudited)
      const varianceRate = calcVarianceRate(endAudited, beginAudited)
      return {
        ...row,
        beginAudited,
        endAudited,
        variance,
        varianceRate,
      }
    })
  })

  // ─── 2. 合计行 ────────────────────────────────────────────────────────

  /** 合计行（所有专项项目SUM） */
  const totalRow: ComputedRef<L6AdjudicationTotal> = computed(() => {
    const r = computedRows.value
    const beginUnadjusted = calcSubtotal(r.map(x => x.beginUnadjusted))
    const beginAje = calcSubtotal(r.map(x => x.beginAje))
    const beginRje = calcSubtotal(r.map(x => x.beginRje))
    const beginAudited = calcSubtotal(r.map(x => x.beginAudited))
    const endUnadjusted = calcSubtotal(r.map(x => x.endUnadjusted))
    const endAje = calcSubtotal(r.map(x => x.endAje))
    const endRje = calcSubtotal(r.map(x => x.endRje))
    const endAudited = calcSubtotal(r.map(x => x.endAudited))
    const variance = calcVariance(endAudited, beginAudited)
    const varianceRate = calcVarianceRate(endAudited, beginAudited)
    return {
      beginUnadjusted,
      beginAje,
      beginRje,
      beginAudited,
      endUnadjusted,
      endAje,
      endRje,
      endAudited,
      variance,
      varianceRate,
    }
  })

  // ─── 3. 行操作 ────────────────────────────────────────────────────────

  /** 新增项目行 */
  function addRow(project?: string): void {
    const key = `l6-adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const newRow: L6AdjudicationRow = {
      key,
      project: project || '',
      beginUnadjusted: 0,
      beginAje: 0,
      beginRje: 0,
      beginAudited: 0,
      endUnadjusted: 0,
      endAje: 0,
      endRje: 0,
      endAudited: 0,
      variance: 0,
      varianceRate: 0,
    }
    rows.value.push(newRow)
  }

  /** 删除项目行 */
  function removeRow(index: number): void {
    if (index < 0 || index >= rows.value.length) return
    rows.value.splice(index, 1)
    _triggerSaveAll()
  }

  /** 更新行某字段 */
  function updateRow(
    index: number,
    field: 'project' | 'beginUnadjusted' | 'beginAje' | 'beginRje' | 'endUnadjusted' | 'endAje' | 'endRje',
    value: string | number,
  ): void {
    if (index < 0 || index >= rows.value.length) return
    const row = rows.value[index] as any
    row[field] = value

    // 重算公式列
    row.beginAudited = calcAuditedAmount(row.beginUnadjusted, row.beginAje, row.beginRje)
    row.endAudited = calcAuditedAmount(row.endUnadjusted, row.endAje, row.endRje)
    row.variance = calcVariance(row.endAudited, row.beginAudited)
    row.varianceRate = calcVarianceRate(row.endAudited, row.beginAudited)

    _triggerSave(index)
  }

  // ─── 4. 小计计算（按专项项目分类） ────────────────────────────────────

  /** 计算分类小计 */
  function computeSubtotals(category: string): L6AdjudicationTotal {
    const filtered = computedRows.value.filter(r => r.project.includes(category))
    const beginUnadjusted = calcSubtotal(filtered.map(r => r.beginUnadjusted))
    const beginAje = calcSubtotal(filtered.map(r => r.beginAje))
    const beginRje = calcSubtotal(filtered.map(r => r.beginRje))
    const beginAudited = calcSubtotal(filtered.map(r => r.beginAudited))
    const endUnadjusted = calcSubtotal(filtered.map(r => r.endUnadjusted))
    const endAje = calcSubtotal(filtered.map(r => r.endAje))
    const endRje = calcSubtotal(filtered.map(r => r.endRje))
    const endAudited = calcSubtotal(filtered.map(r => r.endAudited))
    const variance = calcVariance(endAudited, beginAudited)
    const varianceRate = calcVarianceRate(endAudited, beginAudited)
    return {
      beginUnadjusted,
      beginAje,
      beginRje,
      beginAudited,
      endUnadjusted,
      endAje,
      endRje,
      endAudited,
      variance,
      varianceRate,
    }
  }

  // ─── 5. 保存 + TB回写 ─────────────────────────────────────────────────

  /**
   * 保存审定表并触发TB回写 + EventBus
   * - 回写 trial_balance 科目 2601
   * - publish 'substantive:adjudicated'
   */
  async function saveAndWriteback(): Promise<void> {
    const items = computedRows.value.map((row, i) => {
      const n = i + 1
      return [
        { itemId: `L6-L6-1-row-${n}-name`, data: { remark: row.project } },
        { itemId: `L6-L6-1-row-${n}-beginAudited`, data: { remark: String(row.beginAudited) } },
        { itemId: `L6-L6-1-row-${n}-endAudited`, data: { remark: String(row.endAudited) } },
      ]
    }).flat()

    // 合计值（供 CrossSheet 勾稽）
    items.push({
      itemId: 'L6-L6-1-total-audited',
      data: { remark: String(totalRow.value.endAudited) },
    })

    await saveBatch(items)

    // TB回写（科目2601）
    await writebackTB(totalRow.value.endAudited)
  }

  // ─── 6. 审定数变化监听 → 自动回写 ────────────────────────────────────────

  watch(
    () => totalRow.value.endAudited,
    async (newVal, oldVal) => {
      if (oldVal !== undefined && newVal !== oldVal) {
        await saveAndWriteback()
      }
    },
  )

  // ─── 7. EventBus 订阅附注刷新 ────────────────────────────────────────────

  /** 订阅附注变化通知 */
  function subscribeDisclosure(callback: () => void): () => void {
    const handler = () => callback()
    eventBus.on('disclosure:note-text-updated', handler)
    return () => eventBus.off('disclosure:note-text-updated', handler)
  }

  // ─── 8. 内部保存触发 ──────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = rows.value[rowIndex]
    if (!row) return
    const n = rowIndex + 1
    debouncedSave(`L6-L6-1-row-${n}-data`, {
      remark: JSON.stringify({
        key: row.key,
        project: row.project,
        beginUnadjusted: row.beginUnadjusted,
        beginAje: row.beginAje,
        beginRje: row.beginRje,
        endUnadjusted: row.endUnadjusted,
        endAje: row.endAje,
        endRje: row.endRje,
      }),
    })
  }

  function _triggerSaveAll(): void {
    for (let i = 0; i < rows.value.length; i++) {
      _triggerSave(i)
    }
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 计算行
    computedRows,
    // 合计行
    totalRow,
    // 行操作
    addRow,
    removeRow,
    updateRow,
    // 小计
    computeSubtotals,
    // 保存+回写
    saveAndWriteback,
    subscribeDisclosure,
  }
}

export default useL6Adjudication
