/**
 * useL1Adjudication — L1-1 短期借款审定表 composable（双期结构，2026-07 复盘重建）
 *
 * 对齐致同源模板「审定表L1-1」：
 * - 分类行（源模板 4 类：信用/抵押/保证/质押 + 合计）
 * - 双期结构：期初数(未审/账项调整/重分类/审定) + 期末数(未审/账项调整/重分类/审定)
 * - 变动分析：本期未审 vs 期初未审(变动额/率) + 本期审定 vs 期初审定(变动额/率)
 * - 原因分析（每行文本）
 * - 从 L1-2 明细带入（SUMIF 等价按借款类型聚合期初/期末未审）
 * - TB回写（科目 2001，期末审定合计）+ EventBus 'substantive:adjudicated'
 *
 * 科目：2001 短期借款（贷方/负债类）：审定 = 未审 + 账项调整 + 重分类调整
 *
 * ⚠️ 旧版为单期 roll-forward（期初/贷方/借方/期末 + 单期未审/AJE/RJE），
 *    与源模板双期变动分析结构不符（缺期初审定分解/变动额率/原因分析）。
 *    本次重建为源模板双期结构。明细表 L1-2 仍保留 roll-forward（期末=期初+贷-借）。
 */
import { computed, watch, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { calcSubtotal } from '@/composables/useL1FormulaEngine'
import type { useL1FormData } from '@/composables/useL1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表分类计算结果（含派生列） */
export interface AdjudicationComputed {
  name: string
  // 期初数
  beginUnadjusted: number
  beginAje: number
  beginRje: number
  beginAudited: number      // = beginUnadjusted + beginAje + beginRje
  // 期末数
  endUnadjusted: number
  endAje: number
  endRje: number
  endAudited: number        // = endUnadjusted + endAje + endRje
  // 变动分析
  unadjChange: number       // = endUnadjusted - beginUnadjusted
  unadjRate: number
  auditedChange: number     // = endAudited - beginAudited
  auditedRate: number
  // 原因分析
  reason: string
}

/** 审定表合计行 */
export interface AdjudicationTotal {
  beginUnadjusted: number
  beginAje: number
  beginRje: number
  beginAudited: number
  endUnadjusted: number
  endAje: number
  endRje: number
  endAudited: number
  unadjChange: number
  unadjRate: number
  auditedChange: number
  auditedRate: number
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 变动率（base=0 时：无变动→0，正向→1，负向→-1） */
function calcRate(base: number, change: number): number {
  if (base === 0) return change === 0 ? 0 : (change > 0 ? 1 : -1)
  return change / base
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L1-1 审定表业务逻辑
 *
 * @param formData 由调用方传入的 useL1FormData 实例
 */
export function useL1Adjudication(formData: ReturnType<typeof useL1FormData>) {
  const { adjudicationData, detailRows, saveImmediate, writebackTB } = formData

  // ─── 1. 计算属性：每行派生列 ───────────────────────────────────────────

  const computedCategories: ComputedRef<AdjudicationComputed[]> = computed(() => {
    return adjudicationData.value.categories.map(cat => {
      const beginAudited = cat.beginUnadjusted + cat.beginAje + cat.beginRje
      const endAudited = cat.endUnadjusted + cat.endAje + cat.endRje
      const unadjChange = cat.endUnadjusted - cat.beginUnadjusted
      const auditedChange = endAudited - beginAudited
      return {
        name: cat.name,
        beginUnadjusted: cat.beginUnadjusted,
        beginAje: cat.beginAje,
        beginRje: cat.beginRje,
        beginAudited,
        endUnadjusted: cat.endUnadjusted,
        endAje: cat.endAje,
        endRje: cat.endRje,
        endAudited,
        unadjChange,
        unadjRate: calcRate(cat.beginUnadjusted, unadjChange),
        auditedChange,
        auditedRate: calcRate(beginAudited, auditedChange),
        reason: cat.reason,
      }
    })
  })

  // ─── 2. 合计行 ─────────────────────────────────────────────────────────

  const total: ComputedRef<AdjudicationTotal> = computed(() => {
    const cats = computedCategories.value
    const beginUnadjusted = calcSubtotal(cats.map(c => c.beginUnadjusted))
    const beginAje = calcSubtotal(cats.map(c => c.beginAje))
    const beginRje = calcSubtotal(cats.map(c => c.beginRje))
    const beginAudited = calcSubtotal(cats.map(c => c.beginAudited))
    const endUnadjusted = calcSubtotal(cats.map(c => c.endUnadjusted))
    const endAje = calcSubtotal(cats.map(c => c.endAje))
    const endRje = calcSubtotal(cats.map(c => c.endRje))
    const endAudited = calcSubtotal(cats.map(c => c.endAudited))
    const unadjChange = endUnadjusted - beginUnadjusted
    const auditedChange = endAudited - beginAudited
    return {
      beginUnadjusted, beginAje, beginRje, beginAudited,
      endUnadjusted, endAje, endRje, endAudited,
      unadjChange,
      unadjRate: calcRate(beginUnadjusted, unadjChange),
      auditedChange,
      auditedRate: calcRate(beginAudited, auditedChange),
    }
  })

  /** 期末审定合计（供跨sheet/逾期表L1-7/TB回写消费） */
  const totalAuditedAmount: ComputedRef<number> = computed(() => total.value.endAudited)

  // ─── 3. 行操作 ─────────────────────────────────────────────────────────

  type EditableField = 'beginUnadjusted' | 'beginAje' | 'beginRje'
    | 'endUnadjusted' | 'endAje' | 'endRje'

  /** 更新某分类的可编辑数值字段（派生列由 computed 自动刷新） */
  function updateCategory(index: number, field: EditableField, value: number): void {
    const categories = adjudicationData.value.categories
    if (index < 0 || index >= categories.length) return
    categories[index][field] = value
  }

  /** 更新原因分析文本 */
  function updateReason(index: number, value: string): void {
    const categories = adjudicationData.value.categories
    if (index < 0 || index >= categories.length) return
    categories[index].reason = value
  }

  // ─── 4. 从 L1-2 明细带入（SUMIF 等价按借款类型聚合） ──────────────────

  /** 借款种类关键词 → 审定表分类 name 映射 */
  function _loanTypeToCategoryName(loanType: string): string {
    const s = loanType || ''
    if (s.includes('质押')) return '质押借款'
    if (s.includes('抵押')) return '抵押借款'
    if (s.includes('保证')) return '保证借款'
    if (s.includes('信用')) return '信用借款'
    return '信用借款'
  }

  /**
   * 从 L1-2 明细按借款种类聚合期初/期末未审数带入审定表。
   * @returns 命中并更新的分类数
   */
  function importFromDetail(): number {
    const rows = detailRows.value
    if (!rows || rows.length === 0) return 0

    const agg: Record<string, { begin: number; end: number }> = {}
    for (const r of rows) {
      const name = _loanTypeToCategoryName(r.loanType)
      if (!agg[name]) agg[name] = { begin: 0, end: 0 }
      agg[name].begin += Number(r.beginning) || 0
      // 明细期末未审 = 期初 + 贷 - 借（负债类 roll-forward）
      const end = (Number(r.beginning) || 0) + (Number(r.creditAmount) || 0) - (Number(r.debitAmount) || 0)
      agg[name].end += end
    }

    let count = 0
    const categories = adjudicationData.value.categories
    for (const cat of categories) {
      const v = agg[cat.name]
      if (!v) continue
      cat.beginUnadjusted = v.begin
      cat.endUnadjusted = v.end
      count++
    }
    return count
  }

  // ─── 5. TB回写 + EventBus ──────────────────────────────────────────────

  /**
   * 保存审定表并触发TB回写 + EventBus。
   * 序列化「可编辑输入字段」（beginUnadjusted/beginAje/beginRje/endUnadjusted/endAje/endRje/reason），
   * 派生列由 computedCategories 重算，无需持久化。
   */
  async function saveAndWriteback(): Promise<void> {
    const items = adjudicationData.value.categories.map((cat, i) => {
      const n = i + 1
      return [
        { item_id: `L1-adj-${n}-beginUnadjusted`, conclusion: null, remark: String(cat.beginUnadjusted) },
        { item_id: `L1-adj-${n}-beginAje`, conclusion: null, remark: String(cat.beginAje) },
        { item_id: `L1-adj-${n}-beginRje`, conclusion: null, remark: String(cat.beginRje) },
        { item_id: `L1-adj-${n}-endUnadjusted`, conclusion: null, remark: String(cat.endUnadjusted) },
        { item_id: `L1-adj-${n}-endAje`, conclusion: null, remark: String(cat.endAje) },
        { item_id: `L1-adj-${n}-endRje`, conclusion: null, remark: String(cat.endRje) },
        { item_id: `L1-adj-${n}-reason`, conclusion: null, remark: cat.reason || null },
      ]
    }).flat()

    await saveImmediate(items)

    // TB回写（期末审定合计）
    const auditedTotal = total.value.endAudited
    await writebackTB(auditedTotal)

    // EventBus publish
    eventBus.emit('substantive:adjudicated', {
      accountCode: '2001',
      auditedAmount: auditedTotal,
      wpCode: 'L1',
      timestamp: Date.now(),
    })
  }

  // ─── 6. 可编辑字段变化监听 → 自动保存 + 回写 ──────────────────────────

  const _editableSignature = computed(() =>
    adjudicationData.value.categories
      .map(c => `${c.beginUnadjusted}|${c.beginAje}|${c.beginRje}|${c.endUnadjusted}|${c.endAje}|${c.endRje}|${c.reason}`)
      .join(';'),
  )
  watch(_editableSignature, async (newVal, oldVal) => {
    if (oldVal !== undefined && newVal !== oldVal) {
      await saveAndWriteback()
    }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    computedCategories,
    total,
    totalAuditedAmount,
    updateCategory,
    updateReason,
    importFromDetail,
    saveAndWriteback,
  }
}

export default useL1Adjudication
