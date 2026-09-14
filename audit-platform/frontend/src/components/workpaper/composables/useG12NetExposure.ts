/**
 * useG12NetExposure — G12-5 风险净敞口检查（对齐 Excel 五区段头寸表 + 多币种分行）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import {
  G12_NET_EXPOSURE_SEED,
  G12_NET_EXPOSURE_SAMPLE_CRITERIA,
  G12_NET_EXPOSURE_TEST_OBJECTIVE,
} from './g12NetExposureSeed'
import { G12_NET_EXPOSURE_CURRENCIES } from './g12Constants'
import { resolveRowCurrency, suggestNetPosition } from './g12NetExposureCalc'
import {
  extractHedgeRelationId,
  formatG12NetExposureCrossMessage,
  type G12NetExposureCrossIssue,
} from './g12NetExposureCross'
import { groupNetExposureRows, normNetExposureItem } from './g12NetExposureGroups'
import {
  buildG12NetExposureAiContext,
  inferEvidenceType,
} from './g12NetExposureEvidence'
import { planG12NetPositionSync } from './g12NetHedgePositionSync'
import type { G12HedgeDetailRow } from './useG12HedgeDetail'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

export interface G12NetExposureRow {
  rowId: string
  seq: number
  hedgeRelationId: string
  item: string
  currency: string
  position1Desc: string
  position1Amount: string
  position2Desc: string
  position2Amount: string
  netPosition: string
  netPositionManual: boolean
  /** 证据类型（结构化） */
  evidenceType: string
  /** 证据明细/备注（自由文本） */
  supportingEvidence: string
  hedgingInstrument: string
  indexRef: string
}

const ROWS_ID = 'G12-net-exposure-rows'
const META_ID = 'G12-net-exposure-meta'
const CONCLUSION_ID = 'G12-net-exposure-conclusion'
const NOTE_ID = 'G12-net-exposure-audit-note'

function genId() {
  return `g12ne-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

function normItem(item: string): string {
  return normNetExposureItem(item)
}

function isLegacyQuestionnaireRow(r: Record<string, unknown>): boolean {
  return 'checkItem' in r || 'compliance' in r || 'sectionTitle' in r
}

function enrichRow(raw: Partial<G12NetExposureRow> & { rowId?: string }, seq: number): G12NetExposureRow {
  const supportingEvidence = raw.supportingEvidence ?? ''
  let evidenceType = raw.evidenceType ?? ''
  if (!evidenceType && supportingEvidence) {
    evidenceType = inferEvidenceType(supportingEvidence)
  }
  const row = {
    rowId: raw.rowId ?? genId(),
    seq,
    hedgeRelationId: raw.hedgeRelationId ?? '',
    item: raw.item ?? '',
    currency: raw.currency ?? '',
    position1Desc: raw.position1Desc ?? '',
    position1Amount: raw.position1Amount ?? '',
    position2Desc: raw.position2Desc ?? '',
    position2Amount: raw.position2Amount ?? '',
    netPosition: raw.netPosition ?? '',
    netPositionManual: raw.netPositionManual ?? Boolean(raw.netPosition),
    evidenceType,
    supportingEvidence,
    hedgingInstrument: raw.hedgingInstrument ?? '',
    indexRef: raw.indexRef ?? '',
  }
  if (!row.currency) row.currency = resolveRowCurrency(row)
  if (!row.hedgeRelationId && row.indexRef) {
    row.hedgeRelationId = extractHedgeRelationId(row.indexRef)
  }
  return row
}

function rowFromSeed(seed: (typeof G12_NET_EXPOSURE_SEED)[number], seq: number): G12NetExposureRow {
  return enrichRow({
    item: seed.item,
    currency: seed.currency,
    position1Desc: seed.position1Desc,
    position1Amount: seed.position1Amount,
    position2Desc: seed.position2Desc,
    position2Amount: seed.position2Amount,
    netPosition: seed.netPosition,
    netPositionManual: false,
    supportingEvidence: seed.supportingEvidence,
    evidenceType: seed.evidenceType ?? '',
    hedgingInstrument: seed.hedgingInstrument,
    indexRef: seed.indexRef,
  }, seq)
}

function defaultRows(): G12NetExposureRow[] {
  return G12_NET_EXPOSURE_SEED.map((s, i) => rowFromSeed(s, i + 1))
}

function parseRows(json: string | null | undefined): G12NetExposureRow[] {
  if (!json) return defaultRows()
  try {
    const parsed = JSON.parse(json)
    if (!Array.isArray(parsed) || !parsed.length) return defaultRows()
    if (isLegacyQuestionnaireRow(parsed[0] as Record<string, unknown>)) return defaultRows()
    return parsed.map((r: Partial<G12NetExposureRow> & { rowId?: string }, i: number) =>
      enrichRow(r, r.seq ?? i + 1),
    )
  } catch {
    return defaultRows()
  }
}

function resequence(rows: G12NetExposureRow[]): G12NetExposureRow[] {
  return rows.map((r, i) => ({ ...r, seq: i + 1 }))
}

function suggestForRow(row: G12NetExposureRow): string {
  return suggestNetPosition(row.position1Amount, row.position2Amount, row.currency)
}

export function useG12NetExposure(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  wpId?: Ref<string>
}) {
  const rows = ref<G12NetExposureRow[]>(defaultRows())
  const testObjective = ref(G12_NET_EXPOSURE_TEST_OBJECTIVE)
  const sampleCriteria = ref(G12_NET_EXPOSURE_SAMPLE_CRITERIA)
  const overallConclusion = ref('')
  const auditNote = ref('')
  const aiLoading = ref(false)

  watch(() => opts.allResponses.value.get(ROWS_ID)?.remark, (j) => {
    rows.value = parseRows(j)
  }, { immediate: true })

  watch(() => opts.allResponses.value.get(META_ID)?.remark, (j) => {
    if (!j) return
    try {
      const meta = JSON.parse(j) as { testObjective?: string; sampleCriteria?: string }
      testObjective.value = meta.testObjective ?? G12_NET_EXPOSURE_TEST_OBJECTIVE
      sampleCriteria.value = meta.sampleCriteria ?? G12_NET_EXPOSURE_SAMPLE_CRITERIA
    } catch { /* ignore */ }
  }, { immediate: true })

  watch(() => opts.allResponses.value.get(CONCLUSION_ID)?.conclusion, (v) => {
    overallConclusion.value = v ?? ''
  }, { immediate: true })

  watch(() => opts.allResponses.value.get(NOTE_ID)?.remark, (v) => {
    auditNote.value = v ?? ''
  }, { immediate: true })

  const incompleteRows = computed(() =>
    rows.value.filter((r) =>
      !r.item.trim()
      || !r.currency.trim()
      || !r.position1Desc.trim()
      || !r.position2Desc.trim()
      || !r.netPosition.trim(),
    ),
  )

  const netPositionHints = computed(() =>
    rows.value.map((r) => (r.netPositionManual ? '' : suggestForRow(r))),
  )

  /** 同项目多币种分组（折叠 UI） */
  const itemGroups = computed(() => groupNetExposureRows(rows.value))

  const distinctCurrencyCount = computed(() =>
    new Set(rows.value.map((r) => r.currency).filter(Boolean)).size,
  )

  function persistRows() {
    opts.debouncedSave(ROWS_ID, { remark: JSON.stringify(rows.value) })
  }

  function persistMeta() {
    opts.debouncedSave(META_ID, {
      remark: JSON.stringify({
        testObjective: testObjective.value,
        sampleCriteria: sampleCriteria.value,
      }),
    })
  }

  function refreshNetPosition(idx: number, next: G12NetExposureRow[]) {
    const row = next[idx]
    if (!row.netPositionManual) {
      const suggested = suggestForRow(row)
      if (suggested) row.netPosition = suggested
    }
  }

  function updateCell(rowId: string, field: keyof G12NetExposureRow, value: unknown) {
    if (opts.isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const next = [...rows.value]
    next[idx] = { ...next[idx], [field]: value }

    if (field === 'position1Amount' || field === 'position2Amount' || field === 'currency') {
      refreshNetPosition(idx, next)
    }
    if (field === 'netPosition') {
      next[idx].netPositionManual = true
    }

    rows.value = next
    persistRows()
  }

  function applyNetPositionHint(rowId: string) {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const hint = suggestForRow(rows.value[idx])
    if (!hint) return
    const next = [...rows.value]
    next[idx] = { ...next[idx], netPosition: hint, netPositionManual: false }
    rows.value = next
    persistRows()
  }

  function addRow(seed?: Partial<G12NetExposureRow>) {
    if (opts.isReadonly.value) return
    rows.value = resequence([
      ...rows.value,
      enrichRow({
        currency: seed?.currency ?? 'USD',
        ...seed,
      }, rows.value.length + 1),
    ])
    persistRows()
  }

  function removeRow(rowId: string) {
    if (opts.isReadonly.value) return
    if (rows.value.length <= 1) {
      ElMessage.warning('至少保留一行测试项目')
      return
    }
    rows.value = resequence(rows.value.filter((r) => r.rowId !== rowId))
    persistRows()
  }

  /** 同项目下新增币种分行（复制项目/头寸描述，清空金额） */
  function addCurrencyRow(sourceRowId: string, currency?: string) {
    if (opts.isReadonly.value) return
    const srcIdx = rows.value.findIndex((r) => r.rowId === sourceRowId)
    if (srcIdx === -1) return
    const src = rows.value[srcIdx]
    const itemKey = normItem(src.item) || `__row_${src.rowId}`

    const used = rows.value
      .filter((r) => (normItem(r.item) || `__row_${r.rowId}`) === itemKey)
      .map((r) => r.currency)

    const pick = currency
      ?? G12_NET_EXPOSURE_CURRENCIES.map((c) => c.value).find((c) => !used.includes(c))
      ?? ''

    if (!pick) {
      ElMessage.warning('常用币种均已分行，请手动选择其他币种')
      return
    }
    if (used.includes(pick)) {
      ElMessage.warning(`该项目已有 ${pick} 币种分行`)
      return
    }

    const newRow = enrichRow({
      item: src.item,
      hedgeRelationId: src.hedgeRelationId,
      currency: pick,
      position1Desc: src.position1Desc,
      position2Desc: src.position2Desc,
      evidenceType: src.evidenceType,
      supportingEvidence: src.supportingEvidence,
      hedgingInstrument: '',
      indexRef: '',
    }, srcIdx + 2)

    const next = [...rows.value]
    let insertAt = srcIdx + 1
    while (
      insertAt < next.length
      && (normItem(next[insertAt].item) || `__row_${next[insertAt].rowId}`) === itemKey
    ) {
      insertAt += 1
    }
    next.splice(insertAt, 0, newRow)
    rows.value = resequence(next)
    persistRows()
    ElMessage.success(`已新增 ${pick} 币种分行`)
  }

  function importFromHedgeDetail(hedgeRows: Array<{
    item: string
    netPosition?: string
    hedgingInstrument: string
    indexRef: string
    hedgeRelationId?: string
  }>) {
    if (opts.isReadonly.value) return
    if (!hedgeRows.length) {
      ElMessage.info('G12-2 暂无净敞口套期明细')
      return
    }
    for (const h of hedgeRows) {
      const item = String(h.item ?? '').trim()
      const instrument = String(h.hedgingInstrument ?? '').trim()
      if (!item && !instrument) continue
      const relId = String(h.hedgeRelationId ?? '').trim()
        || extractHedgeRelationId(h.indexRef ?? '')
        || item
      const currency = inferRiskCurrency(h.netPosition ?? item)
      addRow({
        hedgeRelationId: relId,
        item: item || relId,
        currency,
        position1Desc: item,
        position2Desc: '',
        netPosition: h.netPosition ?? '',
        netPositionManual: Boolean(h.netPosition),
        hedgingInstrument: instrument,
        indexRef: h.indexRef ? `G12-2/${h.indexRef}` : 'G12-2',
      })
    }
    ElMessage.success(`已从 G12-2 带入 ${hedgeRows.length} 行`)
  }

  /** G12-2 → G12-5：同步已匹配行的净头寸 */
  function syncNetPositionFromG12_2(detailRows: G12HedgeDetailRow[]): number {
    if (opts.isReadonly.value) return 0
    const plan = planG12NetPositionSync('g12-2', detailRows, rows.value)
    if (!plan.neUpdates.length) return 0
    rows.value = rows.value.map((r) => {
      const hit = plan.neUpdates.find((u) => u.rowId === r.rowId)
      return hit ? { ...r, netPosition: hit.netPosition, netPositionManual: hit.netPositionManual } : r
    })
    persistRows()
    return plan.syncedCount
  }

  function updateTestObjective(v: string) {
    if (opts.isReadonly.value) return
    testObjective.value = v
    persistMeta()
  }

  function updateSampleCriteria(v: string) {
    if (opts.isReadonly.value) return
    sampleCriteria.value = v
    persistMeta()
  }

  function updateOverallConclusion(v: string) {
    if (opts.isReadonly.value) return
    overallConclusion.value = v
    opts.debouncedSave(CONCLUSION_ID, { conclusion: v })
  }

  function updateAuditNote(v: string) {
    if (opts.isReadonly.value) return
    auditNote.value = v
    opts.debouncedSave(NOTE_ID, { conclusion: null, remark: v })
  }

  async function generateAiConclusion(crossIssues: G12NetExposureCrossIssue[] = []): Promise<void> {
    if (opts.isReadonly.value || !opts.wpId?.value) return
    aiLoading.value = true
    try {
      const relatedContext = buildG12NetExposureAiContext({
        rows: rows.value,
        incompleteCount: incompleteRows.value.length,
        crossIssues,
        crossSummary: formatG12NetExposureCrossMessage(crossIssues),
        auditNote: auditNote.value,
        testObjective: testObjective.value,
      })
      const res = await api.post(
        `/api/workpapers/${opts.wpId.value}/g12/ai/net-position-conclusion`,
        {
          existingContent: overallConclusion.value,
          relatedContext,
        },
        { _silent: true } as any,
      )
      const content = res?.data?.data?.content ?? res?.data?.content ?? res?.content ?? ''
      if (content) updateOverallConclusion(content)
    } catch {
      const crossHint = crossIssues.length
        ? `交叉验证发现 ${crossIssues.length} 处差异，需在结论中说明处理情况。`
        : '交叉验证未见差异。'
      updateOverallConclusion(
        overallConclusion.value
        || `经检查，风险净敞口测试项目的相对头寸、净头寸与支持性证据已获取；${crossHint}与 G12-2/G12-4 勾稽后，净敞口套期指定与证据充分性可接受。`,
      )
    } finally {
      aiLoading.value = false
    }
  }

  function validateBeforeSave(): boolean {
    const missing = incompleteRows.value
    if (missing.length) {
      ElMessage.warning(`还有 ${missing.length} 行未完成项目/币种/头寸/净头寸填写`)
      return false
    }
    return true
  }

  function saveValidated(): boolean {
    if (!validateBeforeSave()) return false
    persistRows()
    persistMeta()
    ElMessage.success('校验通过，已保存')
    return true
  }

  return {
    rows,
    testObjective,
    sampleCriteria,
    overallConclusion,
    auditNote,
    incompleteRows,
    netPositionHints,
    itemGroups,
    distinctCurrencyCount,
    updateCell,
    applyNetPositionHint,
    addRow,
    addCurrencyRow,
    removeRow,
    importFromHedgeDetail,
    syncNetPositionFromG12_2,
    updateTestObjective,
    updateSampleCriteria,
    updateOverallConclusion,
    updateAuditNote,
    generateAiConclusion,
    aiLoading,
    validateBeforeSave,
    saveValidated,
    persistRows,
    ROWS_ID,
    META_ID,
    CONCLUSION_ID,
    NOTE_ID,
  }
}

/** 从被套期风险/项目描述推断币种 */
function inferRiskCurrency(text: string): string {
  const t = text.toLowerCase()
  if (/欧元|eur/.test(t)) return 'EUR'
  if (/英镑|gbp/.test(t)) return 'GBP'
  if (/日元|jpy/.test(t)) return 'JPY'
  if (/港币|hkd/.test(t)) return 'HKD'
  if (/人民币|cny|rmb/.test(t)) return 'CNY'
  if (/美元|usd|外汇|外币/.test(t)) return 'USD'
  return 'USD'
}
