/**

 * useG12Disclosure — 附注披露（上市 1 行 / 国企 2 行，对齐 Excel 附注模板）

 */

import { ref, computed, watch, onMounted, onBeforeUnmount, getCurrentInstance, type Ref } from 'vue'

import { ElMessage } from 'element-plus'

import { parseNum, calcChangeAmount, calcChangeRate } from './useG12FormulaEngine'

import {

  G12_ACCOUNT_CODE,

  G12_DISCLOSURE_LISTED_ROWS,

  G12_DISCLOSURE_SOE_ROWS,

} from './g12Constants'

import {

  buildG12DisclosureSyncPatch,

  calcG12DisclosureReconciliationDiff,

  migrateG12DisclosureRows,

} from './g12DisclosureSync'

import type { ChecklistResponse } from './useF1FormData'

import { api } from '@/services/apiProxy'



export interface G12DisclosureRow {

  rowKey: string

  label: string

  currentAmount: number

  priorAmount: number

  changeAmount: number

  changeRate: number | null

  remark: string

}



export interface G12DisclosurePatchResult {

  changed: boolean

  sourceFound: boolean

  fieldsChanged: number

}



function rowDefs(variant: 'listed' | 'soe') {

  return variant === 'listed' ? G12_DISCLOSURE_LISTED_ROWS : G12_DISCLOSURE_SOE_ROWS

}



function defaultRows(variant: 'listed' | 'soe'): G12DisclosureRow[] {

  return rowDefs(variant).map((def) => ({

    rowKey: def.rowKey,

    label: def.label,

    currentAmount: 0,

    priorAmount: 0,

    changeAmount: 0,

    changeRate: null,

    remark: '',

  }))

}



function enrichRow(raw: Partial<G12DisclosureRow> & { rowKey: string }, variant: 'listed' | 'soe'): G12DisclosureRow {

  const def = rowDefs(variant).find((d) => d.rowKey === raw.rowKey)

  const currentAmount = parseNum(raw.currentAmount)

  const priorAmount = parseNum(raw.priorAmount)

  return {

    rowKey: raw.rowKey,

    label: def?.label ?? raw.label ?? raw.rowKey,

    currentAmount,

    priorAmount,

    changeAmount: calcChangeAmount(currentAmount, priorAmount),

    changeRate: calcChangeRate(priorAmount, currentAmount),

    remark: raw.remark ?? '',

  }

}



function parsePriorStore(raw?: string | null): Record<string, { priorUnadjusted?: number; priorAdjustment?: number; priorAudited?: number }> {

  if (!raw) return {}

  try {

    return JSON.parse(raw) as Record<string, { priorUnadjusted?: number; priorAdjustment?: number; priorAudited?: number }>

  } catch {

    return {}

  }

}



function optionalAmount(raw: unknown): number | null {

  if (raw == null || (typeof raw === 'string' && raw.trim() === '')) return null

  const amount = typeof raw === 'number' ? raw : Number(raw)

  return Number.isFinite(amount) ? amount : null

}



export function useG12Disclosure(opts: {

  variant: 'listed' | 'soe'

  allResponses: Ref<Map<string, ChecklistResponse>>

  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void

  wpId: Ref<string>

  isReadonly: Ref<boolean>

}) {

  const itemId = opts.variant === 'listed' ? 'G12-disclosure-listed' : 'G12-disclosure-soe'

  const noteItemId = `${itemId}-note`



  const rows = ref<G12DisclosureRow[]>(defaultRows(opts.variant))

  const noteText = ref('')

  const adjudicatedAmount = ref<number | null>(null)

  const aiLoading = ref(false)



  function loadFromStore(): void {

    const raw = opts.allResponses.value.get(itemId)?.remark

    if (raw) {

      try {

        const parsed = JSON.parse(raw)

        if (Array.isArray(parsed)) {

          const migrated = migrateG12DisclosureRows(parsed, opts.variant)

          rows.value = migrated.map((r) => enrichRow({ ...r, rowKey: r.rowKey }, opts.variant))

          return

        }

        if (parsed && typeof parsed === 'object' && parsed.label) {

          rows.value = defaultRows(opts.variant).map((r) =>

            r.rowKey === 'net_hedge'

              ? enrichRow({ ...r, currentAmount: parsed.currentAmount, priorAmount: parsed.priorAmount, label: parsed.label }, opts.variant)

              : r,

          )

          return

        }

      } catch { /* fallback */ }

    }

    rows.value = defaultRows(opts.variant)

  }



  watch(() => opts.allResponses.value.get(itemId)?.remark, loadFromStore, { immediate: true })

  watch(() => opts.allResponses.value.get(noteItemId)?.remark, (v) => { if (v != null) noteText.value = v }, { immediate: true })



  const totalRow = computed(() => {

    const currentAmount = rows.value.reduce((s, r) => s + r.currentAmount, 0)

    const priorAmount = rows.value.reduce((s, r) => s + r.priorAmount, 0)

    return enrichRow({ rowKey: 'total', label: '合计', currentAmount, priorAmount, remark: '' }, opts.variant)

  })



  const displayRows = computed(() => [...rows.value, totalRow.value])



  const reconciliationDiff = computed(() =>

    calcG12DisclosureReconciliationDiff(totalRow.value.currentAmount, adjudicatedAmount.value),

  )



  const soeColumnLabel = computed(() =>

    opts.variant === 'soe' ? '产生净敞口套期收益的来源' : '项目',

  )



  function persist(): void {

    opts.debouncedSave(itemId, {

      remark: JSON.stringify(rows.value.map((r) => ({

        rowKey: r.rowKey, label: r.label, currentAmount: r.currentAmount,

        priorAmount: r.priorAmount, remark: r.remark,

      }))),

    })

    opts.debouncedSave(noteItemId, { remark: noteText.value })

    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {

      detail: {

        accountCode: G12_ACCOUNT_CODE,

        section: opts.variant,

        text: noteText.value,

        currentAmount: totalRow.value.currentAmount,

      },

    }))

  }



  function updateField(rowKey: string, field: keyof G12DisclosureRow, value: unknown): void {

    if (opts.isReadonly.value || rowKey === 'total') return

    const idx = rows.value.findIndex((r) => r.rowKey === rowKey)

    if (idx === -1) return

    const next = [...rows.value]

    next[idx] = enrichRow({ ...next[idx], [field]: value }, opts.variant)

    rows.value = next

    persist()

  }



  function updateNoteText(val: string): void {

    if (opts.isReadonly.value) return

    noteText.value = val

    persist()

  }



  function readAdjudicationContext() {

    const amtRaw = opts.allResponses.value.get('G12-1-adjudicated-amount')?.conclusion

    const adjudicatedTotal = optionalAmount(amtRaw)

    const priorStore = parsePriorStore(opts.allResponses.value.get('G12-adj-prior')?.remark)

    const hedgeDetailJson = opts.allResponses.value.get('G12-hedge-detail-rows')?.remark ?? null

    return { adjudicatedTotal, priorStore, hedgeDetailJson }

  }



  /**

   * 由 G12-1 审定 / G12-2 明细回填附注各行（只改内存）。缺失来源保留原值；显式 0 仍是有效来源。

   * 附注页离屏同步只调这一步，不写底稿（spec note-pull-followup-closure R1）。

   */

  function applyAdjudicationPatch(): G12DisclosurePatchResult {

    const { adjudicatedTotal, priorStore, hedgeDetailJson } = readAdjudicationContext()

    if (adjudicatedTotal != null) adjudicatedAmount.value = adjudicatedTotal



    const patch = buildG12DisclosureSyncPatch(rows.value, {

      variant: opts.variant,

      adjudicatedTotal,

      priorStore,

      hedgeDetailJson,

    })

    if (patch.changed) {

      rows.value = patch.rows.map((r) => enrichRow(r, opts.variant))

    }

    return {

      changed: patch.changed,

      sourceFound: patch.sourceFound,

      fieldsChanged: patch.fieldsChanged,

    }

  }



  function syncFromG12Adjudication(showMessage = true): number {

    const result = applyAdjudicationPatch()

    if (result.sourceFound && result.changed && !opts.isReadonly.value) {

      persist()

    }

    if (showMessage && result.sourceFound) {

      ElMessage.success('已从 G12-1 / G12-2 同步附注发生额')

    }

    return result.fieldsChanged

  }



  function handleAdjudicated(e: Event): void {

    const d = (e as CustomEvent<{ accountCode: string; adjudicatedAmount: number }>).detail

    if (d?.accountCode === G12_ACCOUNT_CODE) {

      adjudicatedAmount.value = d.adjudicatedAmount

      syncFromG12Adjudication(false)

    }

  }



  function pullLatestAdjudicated(): void {

    syncFromG12Adjudication(false)

  }



  function onHedgeDetailUpdated() {

    pullLatestAdjudicated()

  }



  async function generateAi(section = 'adjudication-analysis'): Promise<void> {

    if (opts.isReadonly.value || !opts.wpId.value) return

    aiLoading.value = true

    try {

      const res = await api.post(

        `/api/workpapers/${opts.wpId.value}/g12/ai/${section}`,

        { existingContent: noteText.value, relatedContext: { rows: rows.value, total: totalRow.value.currentAmount } },

        { _silent: true } as any,

      )

      const content = res?.data?.data?.content ?? res?.data?.content ?? res?.content ?? ''

      if (content) { noteText.value = content; persist() }

    } catch {

      const draft = `本期净敞口套期收益合计 ${totalRow.value.currentAmount.toLocaleString()} 元，与 G12-1 审定数及 G12-2 明细勾稽一致。`

      noteText.value = noteText.value ? `${noteText.value}\n${draft}` : draft

      persist()

    } finally { aiLoading.value = false }

  }



  async function generateAiConclusion(): Promise<void> {

    await generateAi('adjudication-analysis')

  }



  const title = computed(() => opts.variant === 'listed' ? '附注披露（上市公司）' : '附注披露（国企）')



  // 离屏实例化（附注页离屏同步在 effectScope 里调用，没有组件实例）不挂钩子、不订阅窗口事件；挂载时的回填由调用方

  // 显式调 `applyAdjudicationPatch`（不保存、不广播，spec note-pull-followup-closure R1）。组件内行为不变。

  if (getCurrentInstance()) {

    onMounted(() => {

      pullLatestAdjudicated()

      window.addEventListener('substantive:adjudicated', handleAdjudicated)

      window.addEventListener('g12:hedge-detail-updated', onHedgeDetailUpdated)

    })

    onBeforeUnmount(() => {

      window.removeEventListener('substantive:adjudicated', handleAdjudicated)

      window.removeEventListener('g12:hedge-detail-updated', onHedgeDetailUpdated)

    })

  }



  return {

    rows, displayRows, totalRow, noteText, adjudicatedAmount, aiLoading, title,

    reconciliationDiff, soeColumnLabel,

    updateField, updateNoteText, generateAi, generateAiConclusion,

    pullLatestAdjudicated, syncFromG12Adjudication, applyAdjudicationPatch,

  }

}


