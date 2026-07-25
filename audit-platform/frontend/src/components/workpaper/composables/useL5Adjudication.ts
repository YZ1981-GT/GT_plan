/**
 * useL5Adjudication — L5-1 长期应付款审定表 composable（双期结构·三区段，2026-07 复盘重建）
 *
 * 对齐致同源模板「审定表L5-1」：
 * - 三区段：一、原值 / 二、未确认融资费用 / 三、净值（净值 = 原值 − 未确认融资费用，逐行）
 * - 每区段 3 行：应付融资租赁款 / 分期付款方式购入固定资产 / 其他 + 合计
 * - 双期结构：期初数(未审/账项调整/重分类/审定/减一年内到期/最终审定) + 期末数(同)
 * - 变动分析：本期审定 vs 期初审定（变动额/率）
 * - 与经审计财报核对：长期应付款审定数(=净值最终审定合计) + 专项应付款审定数(手填) + 合计
 * - 审计说明 + 结论
 * - TB回写（科目 2701 原值审定 + 未确认融资费用审定）+ EventBus
 *
 * ⚠️ 旧版为单期 roll-forward（期初/贷方/借方/期末 + 单期未审/AJE/RJE），净值仅合计级摘要；
 *    与源模板双期 + 三区段(净值逐行) + 减一年内到期结构不符。本次重建。
 *    保留 L5-L5-1-rows JSON 存储 + hydration（P0 数据丢失已修）。
 */
import { computed, watch, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import type { useL5FormData } from './useL5FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export type L5PayableCategory = '融资租赁' | '分期付款' | '其他'

/** 审定表叶子行（原值/未确认 区段共用；仅存可编辑字段） */
export interface L5AdjRow {
  key: string
  category: L5PayableCategory
  itemName: string
  // 期初数
  beginUnadjusted: number
  beginAje: number
  beginRje: number
  beginCurrent: number
  // 期末数
  endUnadjusted: number
  endAje: number
  endRje: number
  endCurrent: number
  // 原因分析
  reason: string
}

/** 派生列（计算后行） */
export interface L5AdjComputedRow extends L5AdjRow {
  beginAudited: number
  beginDisclosed: number
  endAudited: number
  endDisclosed: number
  auditedChange: number
  auditedRate: number
}

/** 区段合计/净值行（派生） */
export interface L5AdjTotalRow {
  label: string
  category?: L5PayableCategory
  beginUnadjusted: number
  beginAje: number
  beginRje: number
  beginCurrent: number
  beginAudited: number
  beginDisclosed: number
  endUnadjusted: number
  endAje: number
  endRje: number
  endCurrent: number
  endAudited: number
  endDisclosed: number
  auditedChange: number
  auditedRate: number
}

/** 双区段可编辑数据结构 */
export interface L5AdjudicationData {
  /** 一、原值（长期应付款贷方/负债）行 */
  grossRows: L5AdjRow[]
  /** 二、未确认融资费用（借方/备抵）行 */
  unrecognizedRows: L5AdjRow[]
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 🔴 完整双区段行 JSON 存储键（P0：保存可编辑输入 + hydration） */
const ITEM_ROWS = 'L5-L5-1-rows'
const CATEGORIES: L5PayableCategory[] = ['融资租赁', '分期付款', '其他']

// ─── Helpers ─────────────────────────────────────────────────────────────────

function calcRate(base: number, change: number): number {
  if (base === 0) return change === 0 ? 0 : (change > 0 ? 1 : -1)
  return change / base
}

function deriveRow(row: L5AdjRow): L5AdjComputedRow {
  const beginAudited = row.beginUnadjusted + row.beginAje + row.beginRje
  const endAudited = row.endUnadjusted + row.endAje + row.endRje
  const auditedChange = endAudited - beginAudited
  return {
    ...row,
    beginAudited,
    beginDisclosed: beginAudited - row.beginCurrent,
    endAudited,
    endDisclosed: endAudited - row.endCurrent,
    auditedChange,
    auditedRate: calcRate(beginAudited, auditedChange),
  }
}

const SUM_FIELDS = [
  'beginUnadjusted', 'beginAje', 'beginRje', 'beginCurrent',
  'endUnadjusted', 'endAje', 'endRje', 'endCurrent',
] as const

function sumRows(rows: L5AdjRow[], label: string): L5AdjTotalRow {
  const base: any = { label }
  for (const f of SUM_FIELDS) base[f] = rows.reduce((s, r) => s + (r as any)[f], 0)
  const beginAudited = base.beginUnadjusted + base.beginAje + base.beginRje
  const endAudited = base.endUnadjusted + base.endAje + base.endRje
  const auditedChange = endAudited - beginAudited
  return {
    ...base,
    beginAudited,
    beginDisclosed: beginAudited - base.beginCurrent,
    endAudited,
    endDisclosed: endAudited - base.endCurrent,
    auditedChange,
    auditedRate: calcRate(beginAudited, auditedChange),
  }
}

/** 净值行 = 原值 − 未确认（逐字段） */
function netRow(gross: L5AdjTotalRow | L5AdjComputedRow, unrec: L5AdjTotalRow | L5AdjComputedRow, label: string, category?: L5PayableCategory): L5AdjTotalRow {
  const base: any = { label, category }
  for (const f of SUM_FIELDS) base[f] = (gross as any)[f] - (unrec as any)[f]
  const beginAudited = base.beginUnadjusted + base.beginAje + base.beginRje
  const endAudited = base.endUnadjusted + base.endAje + base.endRje
  const auditedChange = endAudited - beginAudited
  return {
    ...base,
    beginAudited,
    beginDisclosed: beginAudited - base.beginCurrent,
    endAudited,
    endDisclosed: endAudited - base.endCurrent,
    auditedChange,
    auditedRate: calcRate(beginAudited, auditedChange),
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useL5Adjudication(
  formData: ReturnType<typeof useL5FormData>,
  adjudicationData: L5AdjudicationData,
) {
  const { allResponses, debouncedSave, saveField, writebackTB } = formData

  // ─── Hydration（读回完整双区段行，一次性水合避免覆盖编辑） ───────────────
  let _hydratedOnce = false
  function hydrate(): void {
    const raw = allResponses.value.get(ITEM_ROWS)?.remark
    if (!raw) return
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed?.grossRows)) {
        adjudicationData.grossRows.splice(0, adjudicationData.grossRows.length, ...parsed.grossRows)
      }
      if (Array.isArray(parsed?.unrecognizedRows)) {
        adjudicationData.unrecognizedRows.splice(0, adjudicationData.unrecognizedRows.length, ...parsed.unrecognizedRows)
      }
      _hydratedOnce = true
    } catch { /* ignore */ }
  }
  hydrate()
  watch(
    () => allResponses.value.get(ITEM_ROWS)?.remark,
    (v) => { if (v && !_hydratedOnce) hydrate() },
  )

  function _persistRows(): void {
    debouncedSave(ITEM_ROWS, {
      remark: JSON.stringify({
        grossRows: adjudicationData.grossRows,
        unrecognizedRows: adjudicationData.unrecognizedRows,
      }),
    })
  }

  // ─── 计算行 ────────────────────────────────────────────────────────────

  const computedGrossRows: ComputedRef<L5AdjComputedRow[]> = computed(() =>
    adjudicationData.grossRows.map(deriveRow),
  )
  const computedUnrecognizedRows: ComputedRef<L5AdjComputedRow[]> = computed(() =>
    adjudicationData.unrecognizedRows.map(deriveRow),
  )

  // ─── 净值行（逐行 = 原值 − 未确认，按 category 对齐） ───────────────────
  const computedNetRows: ComputedRef<L5AdjTotalRow[]> = computed(() => {
    return CATEGORIES.map(cat => {
      const g = computedGrossRows.value.find(r => r.category === cat)
      const u = computedUnrecognizedRows.value.find(r => r.category === cat)
      const gRow = g ?? (sumRows([], '') as any)
      const uRow = u ?? (sumRows([], '') as any)
      return netRow(gRow, uRow, g?.itemName || cat, cat)
    })
  })

  // ─── 区段合计 ──────────────────────────────────────────────────────────
  const grossTotal: ComputedRef<L5AdjTotalRow> = computed(() => sumRows(adjudicationData.grossRows, '原值合计'))
  const unrecognizedTotal: ComputedRef<L5AdjTotalRow> = computed(() => sumRows(adjudicationData.unrecognizedRows, '未确认融资费用合计'))
  const netTotal: ComputedRef<L5AdjTotalRow> = computed(() => netRow(grossTotal.value, unrecognizedTotal.value, '净值合计'))

  /** 长期应付款净值最终审定合计（= 净值合计最终审定数 M21，供财报核对/披露/TB回写） */
  const netFinalAudited: ComputedRef<number> = computed(() => netTotal.value.endDisclosed)

  // 同步供跨sheet消费
  watch(() => grossTotal.value.endAudited, (val) => {
    allResponses.value.set('L5-L5-1-adjudication-total', {
      item_id: 'L5-L5-1-adjudication-total', conclusion: null, remark: String(val),
    })
  }, { immediate: true })

  // ─── 与经审计财报核对 ───────────────────────────────────────────────────
  const specialPayableAudited = computed(() => {
    const v = allResponses.value.get('L5-L5-1-special-payable')?.remark
    return v ? Number(v) || 0 : 0
  })
  function updateSpecialPayable(value: number): void {
    saveField('L5-L5-1-special-payable', { remark: String(value) })
  }
  /** 长期应付款 + 专项应付款 合计（期末最终审定） */
  const reconTotal = computed(() => netFinalAudited.value + specialPayableAudited.value)

  // ─── 审计说明 / 结论 ────────────────────────────────────────────────────
  const auditNote = computed(() => allResponses.value.get('L5-L5-1-note')?.remark ?? '')
  const conclusion = computed(() => allResponses.value.get('L5-L5-1-conclusion')?.remark ?? '')
  function updateText(field: 'note' | 'conclusion', value: string): void {
    debouncedSave(`L5-L5-1-${field}`, { remark: value })
  }

  // ─── 行操作 ────────────────────────────────────────────────────────────
  type EditableField = typeof SUM_FIELDS[number]

  function updateGrossRow(index: number, field: EditableField, value: number): void {
    const rows = adjudicationData.grossRows
    if (index < 0 || index >= rows.length) return
    ;(rows[index] as any)[field] = value
    _persistRows()
  }
  function updateUnrecognizedRow(index: number, field: EditableField, value: number): void {
    const rows = adjudicationData.unrecognizedRows
    if (index < 0 || index >= rows.length) return
    ;(rows[index] as any)[field] = value
    _persistRows()
  }
  function updateGrossReason(index: number, value: string): void {
    const rows = adjudicationData.grossRows
    if (index < 0 || index >= rows.length) return
    rows[index].reason = value
    _persistRows()
  }
  function updateUnrecognizedReason(index: number, value: string): void {
    const rows = adjudicationData.unrecognizedRows
    if (index < 0 || index >= rows.length) return
    rows[index].reason = value
    _persistRows()
  }

  // ─── TB回写 + EventBus ─────────────────────────────────────────────────
  async function saveAndWriteback(): Promise<void> {
    _persistRows()
    await saveField('L5-L5-1-adjudication-total', { remark: String(grossTotal.value.endAudited) })
    // 双科目回写：原值(2701) + 未确认融资费用（writebackTB 内部已 emit 'substantive:adjudicated'）
    await writebackTB({
      payableAmount: grossTotal.value.endAudited,
      unrecognizedAmount: unrecognizedTotal.value.endAudited,
    })
  }

  function subscribeDisclosure(callback: () => void): () => void {
    const handler = () => callback()
    eventBus.on('disclosure:note-text-updated' as any, handler)
    return () => eventBus.off('disclosure:note-text-updated' as any, handler)
  }

  return {
    // 计算行
    computedGrossRows,
    computedUnrecognizedRows,
    computedNetRows,
    // 合计
    grossTotal,
    unrecognizedTotal,
    netTotal,
    netFinalAudited,
    // 财报核对
    specialPayableAudited,
    updateSpecialPayable,
    reconTotal,
    // 文本
    auditNote,
    conclusion,
    updateText,
    // 行操作
    updateGrossRow,
    updateUnrecognizedRow,
    updateGrossReason,
    updateUnrecognizedReason,
    // 保存
    saveAndWriteback,
    subscribeDisclosure,
    CATEGORIES,
  }
}

export default useL5Adjudication
