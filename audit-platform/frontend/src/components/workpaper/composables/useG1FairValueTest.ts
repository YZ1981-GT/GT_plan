/**
 * useG1FairValueTest — G1-6 公允价值测试（Level 1/2/3 互斥区段）
 */
import { ref, computed, watch, type Ref } from 'vue'
import {
  parseNum,
  calcFairValue,
  calcLevel1Diff,
} from './useG1TraFinFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export type FvLevel = 1 | 2 | 3

export interface G1FairValueRow {
  id: string
  securityName: string
  securityCode: string
  quantity: number
  bookValue: number
  fvLevel: FvLevel
  quoteDate: string
  quoteSource: string
  quoteValue: number
  marketValue: number
  level1Diff: number
  observableDesc: string
  valuationMethod: string
  level2Result: number
  level2Diff: number
  unobservableInput: string
  assumption: string
  level3Result: number
  level3Diff: number
  conclusion: string
  remark: string
}

const DATA_KEY = 'G1-6-rows'

function emptyRow(id: string): G1FairValueRow {
  return {
    id,
    securityName: '',
    securityCode: '',
    quantity: 0,
    bookValue: 0,
    fvLevel: 1,
    quoteDate: '',
    quoteSource: '',
    quoteValue: 0,
    marketValue: 0,
    level1Diff: 0,
    observableDesc: '',
    valuationMethod: '',
    level2Result: 0,
    level2Diff: 0,
    unobservableInput: '',
    assumption: '',
    level3Result: 0,
    level3Diff: 0,
    conclusion: '',
    remark: '',
  }
}

function enrichRow(r: G1FairValueRow): G1FairValueRow {
  const marketValue = calcFairValue(r.quantity, r.quoteValue)
  const level1Diff = calcLevel1Diff(r.quantity, r.quoteValue, r.bookValue)
  const level2Diff = r.level2Result - r.bookValue
  const level3Diff = r.level3Result - r.bookValue
  return { ...r, marketValue, level1Diff, level2Diff, level3Diff }
}

function loadRows(map: Map<string, ChecklistResponse>): G1FairValueRow[] {
  const raw = map.get(DATA_KEY)?.conclusion
  if (!raw) return [enrichRow(emptyRow('1'))]
  try {
    const parsed = JSON.parse(raw) as G1FairValueRow[]
    return parsed.length ? parsed.map(enrichRow) : [enrichRow(emptyRow('1'))]
  } catch {
    return [enrichRow(emptyRow('1'))]
  }
}

export function useG1FairValueTest(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const rows = ref<G1FairValueRow[]>(loadRows(opts.allResponses.value))
  const auditConclusion = ref(opts.allResponses.value.get('G1-6-conclusion')?.conclusion ?? '')

  const stats = computed(() => {
    const level1 = rows.value.filter((r) => r.fvLevel === 1).length
    const level2 = rows.value.filter((r) => r.fvLevel === 2).length
    const level3 = rows.value.filter((r) => r.fvLevel === 3).length
    const threshold = 0.01
    const overThreshold = rows.value.filter((r) => {
      const d = r.fvLevel === 1 ? r.level1Diff : r.fvLevel === 2 ? r.level2Diff : r.level3Diff
      return Math.abs(d) > threshold
    }).length
    return { level1, level2, level3, overThreshold }
  })

  function persist() {
    if (opts.isReadonly.value) return
    opts.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
  }

  watch(auditConclusion, (v) => {
    if (!opts.isReadonly.value) opts.debouncedSave('G1-6-conclusion', { conclusion: v })
  })

  function updateRow(id: string, patch: Partial<G1FairValueRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrichRow({ ...r, ...patch }) : r))
    persist()
  }

  function addRow() {
    if (opts.isReadonly.value) return
    const id = String(Date.now())
    rows.value = [...rows.value, enrichRow(emptyRow(id))]
    persist()
  }

  function removeRow(id: string) {
    if (opts.isReadonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id)
    persist()
  }

  return { rows, auditConclusion, stats, updateRow, addRow, removeRow }
}
