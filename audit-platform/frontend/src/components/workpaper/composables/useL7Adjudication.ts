/**
 * useL7Adjudication — L7-1 审定表 composable
 *
 * Spec: .kiro/specs/l7-other-noncurrent-liabilities/
 * Task: 3.4
 * Requirements: 2.1-2.7
 *
 * 职责：
 * - 管理5个项目行 + 合计行
 * - 列结构（xlsx B-K列）：
 *   项目(A) | 期初(未审B/AJE_C/RJE_D/审定E) | 期末(未审F/AJE_G/RJE_H/审定I) | 变动额J | 变动率K
 * - 审定数公式：审定=未审+AJE+RJE
 * - 负债类期末校验：calcLiabilityEndBalance
 * - 审定数变化→writebackTB(2801)+EventBus
 *
 * 科目：2801 其他非流动负债（贷方/负债类！期末=期初+贷方-借方）
 */
import { computed, watch, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
  calcVariance,
  calcVarianceRate,
} from './useL7FormulaEngine'
import type { useL7FormData } from './useL7FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表行数据（对应xlsx L7-1 row7~row11） */
export interface L7AdjudicationRow {
  /** 行唯一标识 */
  key: string
  /** 项目名称（A列，来自L7-2明细表） */
  itemName: string
  /** 期初未审数（B列） */
  beginUnadjusted: number
  /** 期初AJE（C列，账项调整） */
  beginAje: number
  /** 期初RJE（D列，重分类调整） */
  beginRje: number
  /** 期初审定数（E列，公式=B+C+D） */
  beginAudited: number
  /** 期末未审数（F列） */
  endUnadjusted: number
  /** 期末AJE（G列，账项调整） */
  endAje: number
  /** 期末RJE（H列，重分类调整） */
  endRje: number
  /** 期末审定数（I列，公式=F+G+H） */
  endAudited: number
  /** 变动额（J列，公式=I-E） */
  variance: number
  /** 变动率（K列） */
  varianceRate: number
}

/** 合计行数据 */
export interface L7AdjudicationTotal {
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

// ─── Constants ───────────────────────────────────────────────────────────────

/** 默认5个项目行（与xlsx row7~row11对应） */
const DEFAULT_ROW_COUNT = 5

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L7-1 审定表业务逻辑（单区块负债类+5项目行+合计）
 *
 * @param formData 由调用方传入的 useL7FormData 实例
 * @param rows reactive ref of adjudication rows
 */
export function useL7Adjudication(
  formData: ReturnType<typeof useL7FormData>,
  rows: { value: L7AdjudicationRow[] },
) {
  const { allResponses, writebackTB, saveBatch, debouncedSave } = formData

  // ─── 0. Hydration（读回 per-row 完整数据；此前 onMounted 只 loadData 无 restore → 刷新丢失） ──
  let _hydratedOnce = false
  function hydrate(): void {
    let any = false
    for (let i = 0; i < rows.value.length; i++) {
      const resp = allResponses.value.get(`L7-L7-1-row-${i + 1}-data`)
      if (!resp?.remark) continue
      try {
        const p = JSON.parse(resp.remark)
        Object.assign(rows.value[i], {
          itemName: p.itemName ?? rows.value[i].itemName,
          beginUnadjusted: Number(p.beginUnadjusted) || 0,
          beginAje: Number(p.beginAje) || 0,
          beginRje: Number(p.beginRje) || 0,
          endUnadjusted: Number(p.endUnadjusted) || 0,
          endAje: Number(p.endAje) || 0,
          endRje: Number(p.endRje) || 0,
        })
        any = true
      } catch { /* ignore */ }
    }
    if (any) _hydratedOnce = true
  }
  hydrate()
  watch(allResponses, () => { if (!_hydratedOnce) hydrate() })

  // ─── 1. 计算属性：公式列自动计算 ──────────────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<L7AdjudicationRow[]> = computed(() => {
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

  /** 合计行（xlsx row12 SUM公式） */
  const totalRow: ComputedRef<L7AdjudicationTotal> = computed(() => {
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
  function addRow(itemName?: string): void {
    const key = `l7-adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const newRow: L7AdjudicationRow = {
      key,
      itemName: itemName || '',
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

  /** 更新行某字段 */
  function updateRow(
    index: number,
    field: 'itemName' | 'beginUnadjusted' | 'beginAje' | 'beginRje' | 'endUnadjusted' | 'endAje' | 'endRje',
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

  // ─── 4. 保存 + TB回写 ─────────────────────────────────────────────────

  /**
   * 保存审定表并触发TB回写 + EventBus
   * - 回写 trial_balance 科目 2801
   * - publish 'substantive:adjudicated'
   */
  async function saveAndWriteback(): Promise<void> {
    const items = computedRows.value.map((row, i) => {
      const n = i + 1
      return [
        { itemId: `L7-L7-1-row-${n}-name`, data: { remark: row.itemName } },
        { itemId: `L7-L7-1-row-${n}-beginAudited`, data: { remark: String(row.beginAudited) } },
        { itemId: `L7-L7-1-row-${n}-endAudited`, data: { remark: String(row.endAudited) } },
      ]
    }).flat()

    // 合计值（供 CrossSheet 勾稽）
    items.push({
      itemId: 'L7-L7-1-total-audited',
      data: { remark: String(totalRow.value.endAudited) },
    })

    await saveBatch(items)

    // TB回写（科目2801）
    await writebackTB(totalRow.value.endAudited)
  }

  // ─── 5. 审定数变化监听 → 自动回写 ────────────────────────────────────────

  watch(
    () => totalRow.value.endAudited,
    async (newVal, oldVal) => {
      if (oldVal !== undefined && newVal !== oldVal) {
        await saveAndWriteback()
      }
    },
  )

  // ─── 6. EventBus 订阅附注刷新 ────────────────────────────────────────────

  /** 订阅附注变化通知 */
  function subscribeDisclosure(callback: () => void): () => void {
    const handler = () => callback()
    eventBus.on('disclosure:note-text-updated' as any, handler)
    return () => eventBus.off('disclosure:note-text-updated' as any, handler)
  }

  // ─── 7. 内部保存触发 ──────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = rows.value[rowIndex]
    if (!row) return
    const n = rowIndex + 1
    debouncedSave(`L7-L7-1-row-${n}-data`, {
      remark: JSON.stringify({
        key: row.key,
        itemName: row.itemName,
        beginUnadjusted: row.beginUnadjusted,
        beginAje: row.beginAje,
        beginRje: row.beginRje,
        endUnadjusted: row.endUnadjusted,
        endAje: row.endAje,
        endRje: row.endRje,
      }),
    })
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 计算行
    computedRows,
    // 合计行
    totalRow,
    // 行操作
    addRow,
    updateRow,
    // 保存+回写
    saveAndWriteback,
    subscribeDisclosure,
  }
}

export default useL7Adjudication
