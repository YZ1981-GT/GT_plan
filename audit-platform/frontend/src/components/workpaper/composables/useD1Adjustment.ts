/**

 * useD1Adjustment — D1-5 调整分录（D1-entry-rows JSON + legacy 兼容）

 */

import { computed, watch, type Ref, type ComputedRef } from 'vue'

import type { ChecklistItem, ChecklistResponse } from './useD1FormData'

import { parseNum } from './useD1FormulaEngine'



export type AdjustmentType = 'AJE' | 'RJE'



export interface AdjustmentEntry {

  rowId?: string

  index: number

  type: AdjustmentType

  debitAccount: string

  creditAccount: string

  amount: number

  description: string

  isPushedToAdjTable: boolean

}



export interface AdjustmentCreatedPayload {

  wpCode: string

  entryType: AdjustmentType

  debitAccount: string

  creditAccount: string

  amount: number

  description: string

}



export type SaveFn = (items: ChecklistItem[]) => Promise<void>



export interface UseD1AdjustmentOptions {

  allResponses: Ref<Map<string, ChecklistResponse>>

  saveImmediate: SaveFn

  isReadonly: Ref<boolean>

}



const STORAGE_KEY = 'D1-entry-rows'



function generateRowId(): string {

  return `d1-adj-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`

}



function parseJsonEntries(raw: string | null | undefined): AdjustmentEntry[] | null {

  if (!raw) return null

  try {

    const parsed = JSON.parse(raw)

    if (!Array.isArray(parsed)) return null

    return parsed.map((r: any, i: number) => ({

      rowId: r.rowId || generateRowId(),

      index: r.index ?? i + 1,

      type: (r.type || r.entryType || 'AJE') as AdjustmentType,

      debitAccount: r.debitAccount || r.debit || '',

      creditAccount: r.creditAccount || r.credit || '',

      amount: parseNum(r.amount),

      description: r.description || r.desc || '',

      isPushedToAdjTable: r.isPushedToAdjTable ?? r.pushed === 'Y',

    }))

  } catch {

    return null

  }

}



export function useD1Adjustment(options: UseD1AdjustmentOptions) {

  const { allResponses, saveImmediate, isReadonly } = options



  function getVal(itemId: string): ChecklistResponse {

    return allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }

  }



  function setLocal(itemId: string, conclusion: string | null, remark: string | null = null): ChecklistItem {

    const item: ChecklistItem = { item_id: itemId, conclusion, remark }

    allResponses.value.set(itemId, item)

    return item

  }



  function loadLegacyEntries(): AdjustmentEntry[] {

    const count = parseNum(getVal('D1-entry-count').remark) || 0

    const list: AdjustmentEntry[] = []

    for (let i = 1; i <= count; i++) {

      list.push({

        rowId: generateRowId(),

        index: i,

        type: (getVal(`D1-entry-${i}-type`).conclusion as AdjustmentType) || 'AJE',

        debitAccount: getVal(`D1-entry-${i}-debit`).remark || '',

        creditAccount: getVal(`D1-entry-${i}-credit`).remark || '',

        amount: parseNum(getVal(`D1-entry-${i}-amount`).remark),

        description: getVal(`D1-entry-${i}-desc`).remark || '',

        isPushedToAdjTable: getVal(`D1-entry-${i}-pushed`).conclusion === 'Y',

      })

    }

    return list

  }



  function loadEntries(): AdjustmentEntry[] {

    const json = parseJsonEntries(getVal(STORAGE_KEY).remark)

    if (json?.length) return json.map((e, i) => ({ ...e, index: i + 1 }))

    return loadLegacyEntries()

  }



  function persistEntries(list: AdjustmentEntry[]): void {

    const normalized = list.map((e, i) => ({ ...e, index: i + 1 }))

    const items: ChecklistItem[] = [

      setLocal(STORAGE_KEY, null, JSON.stringify(normalized)),

      setLocal('D1-entry-count', null, String(normalized.length)),

    ]

    normalized.forEach((e, i) => {

      const n = i + 1

      items.push(setLocal(`D1-entry-${n}-type`, e.type))

      items.push(setLocal(`D1-entry-${n}-debit`, null, e.debitAccount))

      items.push(setLocal(`D1-entry-${n}-credit`, null, e.creditAccount))

      items.push(setLocal(`D1-entry-${n}-amount`, null, String(e.amount)))

      items.push(setLocal(`D1-entry-${n}-desc`, null, e.description))

      items.push(setLocal(`D1-entry-${n}-pushed`, e.isPushedToAdjTable ? 'Y' : null))

    })

    saveImmediate(items)

  }



  const entries: ComputedRef<AdjustmentEntry[]> = computed(() => loadEntries())



  const ajeTotal: ComputedRef<number> = computed(() =>

    entries.value.filter(e => e.type === 'AJE').reduce((s, e) => s + e.amount, 0),

  )



  const rjeTotal: ComputedRef<number> = computed(() =>

    entries.value.filter(e => e.type === 'RJE').reduce((s, e) => s + e.amount, 0),

  )



  const debitTotal = computed(() => ajeTotal.value + rjeTotal.value)

  const creditTotal = debitTotal

  const balanceDiff = computed(() => 0)

  const isBalanced = computed(() => true)



  function publishAdjustmentCreated(entry: AdjustmentEntry): void {

    const payload: AdjustmentCreatedPayload = {

      wpCode: 'D1',

      entryType: entry.type,

      debitAccount: entry.debitAccount,

      creditAccount: entry.creditAccount,

      amount: entry.amount,

      description: entry.description,

    }

    try {

      window.dispatchEvent(new CustomEvent('adjustment:created', { detail: payload }))

    } catch { /* silent */ }

  }



  function addEntry(entry: Partial<AdjustmentEntry> = {}): void {

    if (isReadonly.value) return

    const list = loadEntries()

    const newEntry: AdjustmentEntry = {

      rowId: generateRowId(),

      index: list.length + 1,

      type: entry.type || 'AJE',

      debitAccount: entry.debitAccount || '',

      creditAccount: entry.creditAccount || '',

      amount: entry.amount ?? 0,

      description: entry.description || '',

      isPushedToAdjTable: false,

    }

    list.push(newEntry)

    persistEntries(list)

    publishAdjustmentCreated(newEntry)

  }



  function removeEntry(index: number): void {

    if (isReadonly.value) return

    const list = loadEntries().filter(e => e.index !== index)

    persistEntries(list)

  }



  function updateEntry(index: number, data: Partial<AdjustmentEntry>): void {

    if (isReadonly.value) return

    const list = loadEntries()

    const idx = list.findIndex(e => e.index === index)

    if (idx < 0) return

    list[idx] = { ...list[idx], ...data }

    persistEntries(list)

  }



  function pushToA13(indices: number[]): void {

    const selected = entries.value.filter(e => indices.includes(e.index))

    if (selected.length === 0) return

    const misstatements = selected.map(entry => ({

      wpCode: 'D1',

      entryType: entry.type,

      description: entry.description,

      debitAccount: entry.debitAccount,

      creditAccount: entry.creditAccount,

      amount: entry.amount,

    }))

    try {

      window.dispatchEvent(new CustomEvent('a13:push-misstatement', { detail: { items: misstatements } }))

    } catch { /* silent */ }

    for (const entry of selected) {

      updateEntry(entry.index, { isPushedToAdjTable: true })

    }

  }



  watch([ajeTotal, rjeTotal], ([newAje, newRje]) => {

    saveImmediate([

      setLocal('D1-adj-bank-acceptance-aje-dr', null, String(newAje)),

      setLocal('D1-adj-bank-acceptance-rje-dr', null, String(newRje)),

    ])

  })



  return {

    entries,

    ajeTotal,

    rjeTotal,

    debitTotal,

    creditTotal,

    isBalanced,

    balanceDiff,

    addEntry,

    removeEntry,

    updateEntry,

    pushToA13,

    publishAdjustmentCreated,

  }

}



export default useD1Adjustment

