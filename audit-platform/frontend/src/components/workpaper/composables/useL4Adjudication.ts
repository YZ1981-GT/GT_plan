/**
 * useL4Adjudication — L4-1 应付债券审定表 composable（双期结构，2026-07 复盘重建）
 *
 * 对齐致同源模板「审定表L4-1」：
 * - 品种×子项：(一)普通应付债券 + (二)可转换公司债券，各含 成本/利息调整/应计利息 + 品种小计
 * - 双期结构：期初数(未审/账项调整/重分类/审定/减一年内到期/最终审定) + 期末数(同)
 * - 变动分析：本期未审 vs 期初未审(变动额/率) + 本期审定 vs 期初审定(变动额/率)
 * - 原因分析（每叶子行文本）
 * - 从 L4-2 明细带入（按品种×子项聚合摊余成本）
 * - TB回写（科目 2502，期末审定合计）+ EventBus 'substantive:adjudicated'
 * - 写 L4-L4-1-adjudication-total 供 useL4CrossSheet 消费
 *
 * 科目：2502 应付债券（贷方/负债类）：审定 = 未审 + 账项调整 + 重分类调整
 *   最终审定数 = 审定数 − 减：一年内到期的应付债券（流动/非流动重分类）
 *
 * ⚠️ 旧版为单期 roll-forward（期初/贷方/借方/期末 + 单期未审/AJE/RJE），
 *    且 adjudicationData 是组件本地 reactive（每次挂载归零、可编辑输入从不持久化/hydrate）
 *    → 与源模板双期结构不符 + 刷新数据全丢。本次重建为源模板双期结构 + 自 allResponses hydrate。
 */
import { computed, watch, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import type { useL4FormData, ChecklistResponse } from './useL4FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export type L4Variety = '普通债券' | '可转换债券'

export interface L4AdjRow {
  rowKey: string
  variety: L4Variety
  subLabel: string          // 成本 / 利息调整 / 应计利息
  label: string             // 展示标签
  isEditable: boolean
  isSubtotal: boolean
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

/** 叶子行定义（对齐源模板品种×子项） */
export const L4_SOURCE_ROWS = [
  { rowKey: 'normal-cost', variety: '普通债券' as L4Variety, subLabel: '成本' },
  { rowKey: 'normal-interestAdj', variety: '普通债券' as L4Variety, subLabel: '利息调整' },
  { rowKey: 'normal-accrued', variety: '普通债券' as L4Variety, subLabel: '应计利息' },
  { rowKey: 'convertible-cost', variety: '可转换债券' as L4Variety, subLabel: '成本' },
  { rowKey: 'convertible-interestAdj', variety: '可转换债券' as L4Variety, subLabel: '利息调整' },
  { rowKey: 'convertible-accrued', variety: '可转换债券' as L4Variety, subLabel: '应计利息' },
] as const

const VARIETIES: L4Variety[] = ['普通债券', '可转换债券']
const PREFIX = 'L4-L4-1'

const NUM_FIELDS = [
  'beginUnadjusted', 'beginAje', 'beginRje', 'beginCurrent',
  'endUnadjusted', 'endAje', 'endRje', 'endCurrent',
] as const

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

function _derive(row: {
  beginUnadjusted: number; beginAje: number; beginRje: number; beginCurrent: number
  endUnadjusted: number; endAje: number; endRje: number; endCurrent: number
}): {
  beginAudited: number; beginDisclosed: number; endAudited: number; endDisclosed: number
  unadjChange: number; unadjRate: number; auditedChange: number; auditedRate: number
} {
  const beginAudited = row.beginUnadjusted + row.beginAje + row.beginRje
  const endAudited = row.endUnadjusted + row.endAje + row.endRje
  const unadjChange = row.endUnadjusted - row.beginUnadjusted
  const auditedChange = endAudited - beginAudited
  return {
    beginAudited,
    beginDisclosed: beginAudited - row.beginCurrent,
    endAudited,
    endDisclosed: endAudited - row.endCurrent,
    unadjChange,
    unadjRate: calcRate(row.beginUnadjusted, unadjChange),
    auditedChange,
    auditedRate: calcRate(beginAudited, auditedChange),
  }
}

function buildLeaf(
  def: { rowKey: string; variety: L4Variety; subLabel: string },
  responses: Map<string, ChecklistResponse>,
): L4AdjRow {
  const base = {
    beginUnadjusted: getNum(responses, makeItemId(def.rowKey, 'beginUnadjusted')),
    beginAje: getNum(responses, makeItemId(def.rowKey, 'beginAje')),
    beginRje: getNum(responses, makeItemId(def.rowKey, 'beginRje')),
    beginCurrent: getNum(responses, makeItemId(def.rowKey, 'beginCurrent')),
    endUnadjusted: getNum(responses, makeItemId(def.rowKey, 'endUnadjusted')),
    endAje: getNum(responses, makeItemId(def.rowKey, 'endAje')),
    endRje: getNum(responses, makeItemId(def.rowKey, 'endRje')),
    endCurrent: getNum(responses, makeItemId(def.rowKey, 'endCurrent')),
  }
  return {
    rowKey: def.rowKey,
    variety: def.variety,
    subLabel: def.subLabel,
    label: `${def.variety}—${def.subLabel}`,
    isEditable: true,
    isSubtotal: false,
    ...base,
    ..._derive(base),
    reason: getStr(responses, makeItemId(def.rowKey, 'reason')),
  }
}

function buildSubtotal(variety: L4Variety, leaves: L4AdjRow[]): L4AdjRow {
  const sum = (f: (r: L4AdjRow) => number) => leaves.reduce((s, r) => s + f(r), 0)
  const base = {
    beginUnadjusted: sum(r => r.beginUnadjusted),
    beginAje: sum(r => r.beginAje),
    beginRje: sum(r => r.beginRje),
    beginCurrent: sum(r => r.beginCurrent),
    endUnadjusted: sum(r => r.endUnadjusted),
    endAje: sum(r => r.endAje),
    endRje: sum(r => r.endRje),
    endCurrent: sum(r => r.endCurrent),
  }
  return {
    rowKey: `__subtotal_${variety}__`,
    variety,
    subLabel: '小计',
    label: `${variety}（小计）`,
    isEditable: false,
    isSubtotal: true,
    ...base,
    ..._derive(base),
    reason: '',
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useL4Adjudication(formData: ReturnType<typeof useL4FormData>) {
  const { allResponses, saveField, debouncedSave, writebackTB } = formData

  // ─── 叶子行 ────────────────────────────────────────────────────────────

  const leafRows: ComputedRef<L4AdjRow[]> = computed(() =>
    L4_SOURCE_ROWS.map(def => buildLeaf(def, allResponses.value)),
  )

  /** 展示行序列：每品种 3 叶子 + 品种小计 */
  const displayRows: ComputedRef<L4AdjRow[]> = computed(() => {
    const out: L4AdjRow[] = []
    for (const v of VARIETIES) {
      const leaves = leafRows.value.filter(r => r.variety === v)
      out.push(...leaves)
      out.push(buildSubtotal(v, leaves))
    }
    return out
  })

  /** 合计行（全品种叶子） */
  const totalRow: ComputedRef<L4AdjRow> = computed(() => {
    const all = leafRows.value
    const sum = (f: (r: L4AdjRow) => number) => all.reduce((s, r) => s + f(r), 0)
    const base = {
      beginUnadjusted: sum(r => r.beginUnadjusted),
      beginAje: sum(r => r.beginAje),
      beginRje: sum(r => r.beginRje),
      beginCurrent: sum(r => r.beginCurrent),
      endUnadjusted: sum(r => r.endUnadjusted),
      endAje: sum(r => r.endAje),
      endRje: sum(r => r.endRje),
      endCurrent: sum(r => r.endCurrent),
    }
    return {
      rowKey: '__total__', variety: '普通债券', subLabel: '合计', label: '合  计',
      isEditable: false, isSubtotal: true,
      ...base, ..._derive(base), reason: '',
    }
  })

  const totalAuditedAmount: ComputedRef<number> = computed(() => totalRow.value.endAudited)

  // 同步期末审定合计到 allResponses 供跨sheet消费（useL4CrossSheet.adjudicationVsDetail）
  watch(totalAuditedAmount, (val) => {
    allResponses.value.set('L4-L4-1-adjudication-total', {
      item_id: 'L4-L4-1-adjudication-total',
      conclusion: null,
      remark: String(val),
    })
  }, { immediate: true })

  // ─── 审计说明 / 结论 ────────────────────────────────────────────────────

  const auditNote = computed(() => getStr(allResponses.value, `${PREFIX}-note`))
  const conclusion = computed(() => getStr(allResponses.value, `${PREFIX}-conclusion`))

  function updateText(field: 'note' | 'conclusion', value: string): void {
    debouncedSave(`${PREFIX}-${field}`, { remark: value })
  }

  // ─── updateCell ────────────────────────────────────────────────────────

  type EditableField = typeof NUM_FIELDS[number]

  function updateCell(rowKey: string, field: EditableField | 'reason', value: number | string): void {
    const itemId = makeItemId(rowKey, field)
    const strValue = typeof value === 'number' ? String(value) : value
    debouncedSave(itemId, { remark: strValue })
  }

  // ─── 从 L4-2 明细带入（按品种×子项聚合摊余成本） ──────────────────────

  /** @returns 命中并更新的叶子行数 */
  function importFromDetail(): number {
    const detailResp = allResponses.value.get('L4-2-rows')
    if (!detailResp?.remark) return 0
    let rows: any[] = []
    try {
      const parsed = JSON.parse(detailResp.remark)
      rows = Array.isArray(parsed) ? parsed : []
    } catch {
      return 0
    }
    if (rows.length === 0) return 0

    // 按品种聚合：成本/利息调整/应计利息，期初/期末
    const agg: Record<string, {
      costBegin: number; costEnd: number
      iaBegin: number; iaEnd: number
      accBegin: number; accEnd: number
    }> = {
      '普通债券': { costBegin: 0, costEnd: 0, iaBegin: 0, iaEnd: 0, accBegin: 0, accEnd: 0 },
      '可转换债券': { costBegin: 0, costEnd: 0, iaBegin: 0, iaEnd: 0, accBegin: 0, accEnd: 0 },
    }
    for (const r of rows) {
      const v: L4Variety = r.variety === '可转换债券' ? '可转换债券' : '普通债券'
      const a = agg[v]
      a.costBegin += parseNum(r.beginCostPrincipal)
      a.costEnd += parseNum(r.beginCostPrincipal) + parseNum(r.creditIssue) - parseNum(r.debitRedemption)
      a.iaBegin += parseNum(r.beginCostInterestAdj)
      a.iaEnd += parseNum(r.beginCostInterestAdj) + parseNum(r.creditInterestAdj) - parseNum(r.debitInterestAdj)
      a.accBegin += parseNum(r.beginCostAccrued)
      a.accEnd += parseNum(r.endCostAccrued)
    }

    let count = 0
    const map: Array<[string, L4Variety, 'cost' | 'ia' | 'acc']> = [
      ['normal-cost', '普通债券', 'cost'],
      ['normal-interestAdj', '普通债券', 'ia'],
      ['normal-accrued', '普通债券', 'acc'],
      ['convertible-cost', '可转换债券', 'cost'],
      ['convertible-interestAdj', '可转换债券', 'ia'],
      ['convertible-accrued', '可转换债券', 'acc'],
    ]
    for (const [rowKey, variety, kind] of map) {
      const a = agg[variety]
      const begin = kind === 'cost' ? a.costBegin : kind === 'ia' ? a.iaBegin : a.accBegin
      const end = kind === 'cost' ? a.costEnd : kind === 'ia' ? a.iaEnd : a.accEnd
      updateCell(rowKey, 'beginUnadjusted', begin)
      updateCell(rowKey, 'endUnadjusted', end)
      count++
    }
    return count
  }

  // ─── TB回写 ──────────────────────────────────────────────────────────────

  async function submitAdjudication(): Promise<void> {
    const amount = totalAuditedAmount.value
    await saveField('L4-L4-1-adjudication-total', { remark: String(amount) })
    await writebackTB(amount)  // useL4FormData.writebackTB 内部已 emit 'substantive:adjudicated'
  }

  // ─── EventBus（调整变化 → allResponses 自动响应） ─────────────────────

  return {
    leafRows,
    displayRows,
    totalRow,
    totalAuditedAmount,
    auditNote,
    conclusion,
    updateText,
    updateCell,
    importFromDetail,
    submitAdjudication,
    L4_SOURCE_ROWS,
  }
}

export default useL4Adjudication
