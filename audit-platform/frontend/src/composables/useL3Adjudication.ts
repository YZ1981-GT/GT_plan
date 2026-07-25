/**
 * useL3Adjudication — L3-1 长期借款审定表 composable
 *
 * 对齐致同源模板「审定表L3-1」结构（2026-07 复盘重建）：
 * - 分类行（源模板 4 类：质押借款/抵押借款/保证借款/信用借款 + 合计）
 * - 双期结构：期初数(未审/账项调整/重分类/审定/减一年内到期/披露审定) + 期末数(同)
 * - 变动分析：本期未审 vs 期初未审(变动额/率) + 本期审定 vs 期初审定(变动额/率)
 * - 原因分析（每行文本）
 * - 审计说明（增减原因/已到期未偿还/抵押质押/关联方保证）+ 审计结论
 * - 从 L3-2 明细带入（SUMIF 等价按借款类型聚合）
 * - TB回写（科目 2501，期末审定合计）+ EventBus 'substantive:adjudicated'
 *
 * 科目：2501 长期借款（贷方/负债类）：审定 = 未审 + 账项调整 + 重分类调整
 *   披露审定数 = 审定数 − 减：一年内到期的长期借款（流动/非流动重分类）
 *
 * ⚠️ 旧版为单期 roll-forward（期初/贷方/借方/期末），与源模板双期变动分析结构不符；
 *    且旧版 inject('l3FormData')/('l3AdjudicationData') 无 provide → 崩溃/不 hydrate。
 *    本次重建为源模板结构 + 自 formData.allResponses hydrate。
 */
import { computed, watch, onBeforeUnmount, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import type { useL3FormData, ChecklistResponse } from '@/components/workpaper/composables/useL3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface L3AdjRow {
  rowKey: string
  label: string
  isEditable: boolean
  // 期初数
  beginUnadjusted: number
  beginAje: number
  beginRje: number
  beginAudited: number      // = beginUnadjusted + beginAje + beginRje
  beginCurrent: number      // 减：期初一年内到期
  beginDisclosed: number    // = beginAudited - beginCurrent
  // 期末数
  endUnadjusted: number
  endAje: number
  endRje: number
  endAudited: number        // = endUnadjusted + endAje + endRje
  endCurrent: number        // 减：期末一年内到期
  endDisclosed: number      // = endAudited - endCurrent
  // 变动分析
  unadjChange: number       // = endUnadjusted - beginUnadjusted
  unadjRate: number
  auditedChange: number     // = endAudited - beginAudited
  auditedRate: number
  // 原因分析
  reason: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 分类行定义（对齐源模板 A7~A10） */
export const L3_SOURCE_ROWS = [
  { rowKey: 'pledge', label: '质押借款' },
  { rowKey: 'mortgage', label: '抵押借款' },
  { rowKey: 'guarantee', label: '保证借款' },
  { rowKey: 'credit', label: '信用借款' },
] as const

const PREFIX = 'L3-L3-1'

/** 明细借款类型 → 审定表 rowKey 关键词映射 */
function loanTypeToRowKey(loanType: string): string {
  const s = loanType || ''
  if (s.includes('质押')) return 'pledge'
  if (s.includes('抵押')) return 'mortgage'
  if (s.includes('保证')) return 'guarantee'
  if (s.includes('信用')) return 'credit'
  return 'credit'
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeItemId(rowKey: string, field: string): string {
  return `${PREFIX}-${rowKey}-${field}`
}

function parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function getNum(responses: Map<string, ChecklistResponse>, itemId: string): number {
  return parseNum(responses.get(itemId)?.remark)
}

function getStr(responses: Map<string, ChecklistResponse>, itemId: string): string {
  return responses.get(itemId)?.remark ?? ''
}

function calcRate(base: number, change: number): number {
  if (base === 0) return change === 0 ? 0 : (change > 0 ? 1 : -1)
  return change / base
}

function buildRow(
  def: { rowKey: string; label: string },
  responses: Map<string, ChecklistResponse>,
): L3AdjRow {
  const beginUnadjusted = getNum(responses, makeItemId(def.rowKey, 'beginUnadjusted'))
  const beginAje = getNum(responses, makeItemId(def.rowKey, 'beginAje'))
  const beginRje = getNum(responses, makeItemId(def.rowKey, 'beginRje'))
  const beginCurrent = getNum(responses, makeItemId(def.rowKey, 'beginCurrent'))
  const endUnadjusted = getNum(responses, makeItemId(def.rowKey, 'endUnadjusted'))
  const endAje = getNum(responses, makeItemId(def.rowKey, 'endAje'))
  const endRje = getNum(responses, makeItemId(def.rowKey, 'endRje'))
  const endCurrent = getNum(responses, makeItemId(def.rowKey, 'endCurrent'))
  const reason = getStr(responses, makeItemId(def.rowKey, 'reason'))

  const beginAudited = beginUnadjusted + beginAje + beginRje
  const endAudited = endUnadjusted + endAje + endRje
  const unadjChange = endUnadjusted - beginUnadjusted
  const auditedChange = endAudited - beginAudited

  return {
    rowKey: def.rowKey,
    label: def.label,
    isEditable: true,
    beginUnadjusted, beginAje, beginRje,
    beginAudited,
    beginCurrent,
    beginDisclosed: beginAudited - beginCurrent,
    endUnadjusted, endAje, endRje,
    endAudited,
    endCurrent,
    endDisclosed: endAudited - endCurrent,
    unadjChange,
    unadjRate: calcRate(beginUnadjusted, unadjChange),
    auditedChange,
    auditedRate: calcRate(beginAudited, auditedChange),
    reason,
  }
}

function buildTotalRow(rows: L3AdjRow[]): L3AdjRow {
  const sum = (f: (r: L3AdjRow) => number) => rows.reduce((s, r) => s + f(r), 0)
  const beginUnadjusted = sum(r => r.beginUnadjusted)
  const beginAje = sum(r => r.beginAje)
  const beginRje = sum(r => r.beginRje)
  const beginCurrent = sum(r => r.beginCurrent)
  const endUnadjusted = sum(r => r.endUnadjusted)
  const endAje = sum(r => r.endAje)
  const endRje = sum(r => r.endRje)
  const endCurrent = sum(r => r.endCurrent)
  const beginAudited = beginUnadjusted + beginAje + beginRje
  const endAudited = endUnadjusted + endAje + endRje
  const unadjChange = endUnadjusted - beginUnadjusted
  const auditedChange = endAudited - beginAudited

  return {
    rowKey: '__total__',
    label: '合计',
    isEditable: false,
    beginUnadjusted, beginAje, beginRje,
    beginAudited,
    beginCurrent,
    beginDisclosed: beginAudited - beginCurrent,
    endUnadjusted, endAje, endRje,
    endAudited,
    endCurrent,
    endDisclosed: endAudited - endCurrent,
    unadjChange,
    unadjRate: calcRate(beginUnadjusted, unadjChange),
    auditedChange,
    auditedRate: calcRate(beginAudited, auditedChange),
    reason: '',
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useL3Adjudication(formData: ReturnType<typeof useL3FormData>) {
  const { allResponses, saveField, debouncedSave, writebackTB } = formData

  // ─── Rows ────────────────────────────────────────────────────────────────

  const rows: ComputedRef<L3AdjRow[]> = computed(() =>
    L3_SOURCE_ROWS.map(def => buildRow(def, allResponses.value)),
  )

  const totalRow: ComputedRef<L3AdjRow> = computed(() => buildTotalRow(rows.value))

  const totalAuditedAmount: ComputedRef<number> = computed(() => totalRow.value.endAudited)

  // 同步期末审定合计到 allResponses 供跨sheet消费（useL3CrossSheet.adjudicationVsDetail）
  watch(totalAuditedAmount, (val) => {
    allResponses.value.set('L3-L3-1-adjudication-total', {
      item_id: 'L3-L3-1-adjudication-total',
      conclusion: null,
      remark: String(val),
    })
  }, { immediate: true })

  // ─── 审计说明 / 结论 ────────────────────────────────────────────────────

  const noteChange = computed(() => getStr(allResponses.value, `${PREFIX}-note-change`))
  const noteOverdue = computed(() => getStr(allResponses.value, `${PREFIX}-note-overdue`))
  const notePledge = computed(() => getStr(allResponses.value, `${PREFIX}-note-pledge`))
  const noteGuarantee = computed(() => getStr(allResponses.value, `${PREFIX}-note-guarantee`))
  const conclusion = computed(() => getStr(allResponses.value, `${PREFIX}-conclusion`))

  function updateNote(field: 'note-change' | 'note-overdue' | 'note-pledge' | 'note-guarantee' | 'conclusion', value: string): void {
    debouncedSave(`${PREFIX}-${field}`, { remark: value })
  }

  // ─── updateCell ────────────────────────────────────────────────────────

  function updateCell(rowKey: string, field: string, value: number | string): void {
    const itemId = makeItemId(rowKey, field)
    const strValue = typeof value === 'number' ? String(value) : value
    debouncedSave(itemId, { remark: strValue })
  }

  // ─── 从 L3-2 明细带入（SUMIF 等价按借款类型聚合） ──────────────────────

  /** @returns 带入的分类数 */
  function importFromDetail(): number {
    const detailResp = allResponses.value.get('L3-L3-2-rows')
    if (!detailResp?.remark) return 0
    let detailRows: any[] = []
    try {
      const parsed = JSON.parse(detailResp.remark)
      detailRows = Array.isArray(parsed) ? parsed : []
    } catch {
      return 0
    }
    if (detailRows.length === 0) return 0

    const agg: Record<string, { beginUnadj: number; endUnadj: number; endCurrent: number }> = {}
    for (const r of detailRows) {
      const key = loanTypeToRowKey(r.loanType)
      if (!agg[key]) agg[key] = { beginUnadj: 0, endUnadj: 0, endCurrent: 0 }
      agg[key].beginUnadj += parseNum(r.beginning)
      agg[key].endUnadj += parseNum(r.endBalance)
      agg[key].endCurrent += parseNum(r.currentPortion)
    }

    let count = 0
    for (const [rowKey, v] of Object.entries(agg)) {
      updateCell(rowKey, 'beginUnadjusted', v.beginUnadj)
      updateCell(rowKey, 'endUnadjusted', v.endUnadj)
      updateCell(rowKey, 'endCurrent', v.endCurrent)
      count++
    }
    return count
  }

  // ─── TB回写 ──────────────────────────────────────────────────────────────

  async function submitAdjudication(): Promise<void> {
    const amount = totalAuditedAmount.value
    await writebackTB(amount)
    await saveField('L3-L3-1-adjudication-total', { remark: String(amount) })
  }

  // ─── EventBus（明细/调整变化 → allResponses 自动响应） ─────────────────

  function onAdjustmentCreated(): void { /* rows computed 自动响应 allResponses 变化 */ }
  eventBus.on('adjustment:created', onAdjustmentCreated)
  onBeforeUnmount(() => {
    eventBus.off('adjustment:created', onAdjustmentCreated)
  })

  return {
    rows,
    totalRow,
    totalAuditedAmount,
    noteChange,
    noteOverdue,
    notePledge,
    noteGuarantee,
    conclusion,
    updateNote,
    updateCell,
    importFromDetail,
    submitAdjudication,
    L3_SOURCE_ROWS,
  }
}

export default useL3Adjudication
