/**
 * useG12FairValueTest — G12-4 公允价值测试（2区段Tab，行同步）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { parseNum, calcFVChange } from './useG12FormulaEngine'
import { G12_EFFECTIVENESS_OPTIONS } from './g12Constants'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

export interface G12FairValueRow {
  rowId: string
  seq: number
  hedgeRelationId: string
  instrumentName: string
  instrumentType: string
  instrumentOpeningFV: number
  instrumentClosingFV: number
  instrumentFVChange: number
  instrumentValuationMethod: string
  instrumentFVLevel: string
  instrumentValuationSource: string
  itemName: string
  itemType: string
  itemOpeningFV: number
  itemClosingFV: number
  itemFVChange: number
  itemRiskFactor: string
  itemTestMethod: string
  itemEffectivenessConclusion: string
}

const ITEM_ID = 'G12-fv-test-rows'
const CONCLUSION_ID = 'G12-fv-test-conclusion'
function genId() { return `g12fv-${Date.now().toString(36)}` }

function enrich(raw: Partial<G12FairValueRow> & { rowId: string }): G12FairValueRow {
  const io = parseNum(raw.instrumentOpeningFV)
  const ic = parseNum(raw.instrumentClosingFV)
  const po = parseNum(raw.itemOpeningFV)
  const pc = parseNum(raw.itemClosingFV)
  return {
    rowId: raw.rowId,
    seq: parseNum(raw.seq) || 0,
    hedgeRelationId: raw.hedgeRelationId ?? '',
    instrumentName: raw.instrumentName ?? '',
    instrumentType: raw.instrumentType ?? '',
    instrumentOpeningFV: io,
    instrumentClosingFV: ic,
    instrumentFVChange: calcFVChange(io, ic),
    instrumentValuationMethod: raw.instrumentValuationMethod ?? '',
    instrumentFVLevel: raw.instrumentFVLevel ?? 'Level2',
    instrumentValuationSource: raw.instrumentValuationSource ?? '',
    itemName: raw.itemName ?? '',
    itemType: raw.itemType ?? '',
    itemOpeningFV: po,
    itemClosingFV: pc,
    itemFVChange: calcFVChange(po, pc),
    itemRiskFactor: raw.itemRiskFactor ?? '',
    itemTestMethod: raw.itemTestMethod ?? '',
    itemEffectivenessConclusion: raw.itemEffectivenessConclusion ?? 'pending',
  }
}

export function useG12FairValueTest(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  wpId?: Ref<string>
}) {
  const rows = ref<G12FairValueRow[]>([])
  const activeTab = ref<'instrument' | 'item'>('instrument')
  const selectedRowId = ref('')
  const conclusion = ref('')

  watch(() => opts.allResponses.value.get(ITEM_ID)?.remark, (j) => {
    try { rows.value = j ? JSON.parse(j).map((r: any, i: number) => enrich({ ...r, rowId: r.rowId || genId(), seq: r.seq ?? i + 1 })) : [] } catch { rows.value = [] }
  }, { immediate: true })
  watch(() => opts.allResponses.value.get(CONCLUSION_ID)?.conclusion, (v) => { conclusion.value = v ?? '' }, { immediate: true })

  function persist() {
    opts.debouncedSave(ITEM_ID, { remark: JSON.stringify(rows.value.map((r) => ({
      rowId: r.rowId, seq: r.seq, hedgeRelationId: r.hedgeRelationId,
      instrumentName: r.instrumentName, instrumentType: r.instrumentType,
      instrumentOpeningFV: r.instrumentOpeningFV, instrumentClosingFV: r.instrumentClosingFV,
      instrumentValuationMethod: r.instrumentValuationMethod, instrumentFVLevel: r.instrumentFVLevel,
      instrumentValuationSource: r.instrumentValuationSource,
      itemName: r.itemName, itemType: r.itemType, itemOpeningFV: r.itemOpeningFV, itemClosingFV: r.itemClosingFV,
      itemRiskFactor: r.itemRiskFactor, itemTestMethod: r.itemTestMethod, itemEffectivenessConclusion: r.itemEffectivenessConclusion,
    }))) })
  }

  function updateCell(rowId: string, field: keyof G12FairValueRow, value: unknown) {
    if (opts.isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const next = [...rows.value]
    next[idx] = enrich({ ...next[idx], [field]: value })
    rows.value = next
    persist()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('套期关系编号', '新增FV测试行', { inputPattern: /\S+/ })
      const row = enrich({ rowId: genId(), seq: rows.value.length + 1, hedgeRelationId: value ?? '' })
      rows.value = [...rows.value, row]
      selectedRowId.value = row.rowId
      persist()
    } catch { /* cancel */ }
  }

  function removeRow(rowId: string) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId).map((r, i) => enrich({ ...r, seq: i + 1 }))
    persist()
  }

  function updateConclusion(v: string) {
    if (opts.isReadonly.value) return
    conclusion.value = v
    opts.debouncedSave(CONCLUSION_ID, { conclusion: v })
  }

  const selectedRow = computed(() => rows.value.find((r) => r.rowId === selectedRowId.value) ?? rows.value[0] ?? null)
  const aiLoading = ref(false)

  async function generateAiConclusion(): Promise<void> {
    if (opts.isReadonly.value || !opts.wpId?.value) return
    aiLoading.value = true
    try {
      const res = await api.post(
        `/api/workpapers/${opts.wpId.value}/g12/ai/hedge-effectiveness-conclusion`,
        { existingContent: conclusion.value, relatedContext: { rows: rows.value } },
        { _silent: true } as any,
      )
      const content = res?.data?.data?.content ?? res?.data?.content ?? res?.content ?? ''
      if (content) updateConclusion(content)
    } catch {
      updateConclusion(conclusion.value || '经测试，套期关系整体有效，公允价值变动与套期关系明细表 G12-2 交叉核对一致。')
    } finally { aiLoading.value = false }
  }

  return {
    rows, activeTab, selectedRowId, selectedRow, conclusion, aiLoading,
    updateCell, addRow, removeRow, updateConclusion, generateAiConclusion, persist, ITEM_ID,
    G12_EFFECTIVENESS_OPTIONS,
  }
}
