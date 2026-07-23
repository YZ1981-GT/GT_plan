/**
 * useK1OverdueCheck — K1-10 长期未收回款项检查表（对齐致同 Excel + G2-6 增强）
 *
 * 列：债务人 | 期初 | 借方 | 贷方 | 期末(公式) | 账龄 | 经济业务说明 |
 *     未收回或未结转原因 | 是否诉讼 | 是否无法收回 | 处理计划 |
 *     计提坏账准备 | 审定余额 | 期后收款 | 备注
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useG2IntRecFormulaEngine'
import { calcAssetEndBalance, calcNetValue } from './useK1FormulaEngine'
import {
  useAgingConfig,
  PRESET_SEGMENTS,
  type AgingSegment,
  type AgingPreset,
} from '@/composables/useAgingConfig'
import { loadK1DetailPartials, filterLongTermFromK1Detail, computeK110ProvisionReconciliation, stageLabelToNumber, type K110ProvisionReconciliation } from './k1CrossHelpers'
import {
  parseK1StageRowsFromMap,
  mergeOverdueStageHintsToK7,
  buildK110StageHintsFromSources,
  K1_STAGE_ROWS_KEY,
  type OverdueStageHint,
} from './useK1StageCheck'
import {
  fetchK1PostPaymentFromLedger,
  resolveK1BsDate,
} from './k1PostPaymentFromLedger'
import {
  suggestEclStageFromAging,
  estimateOverdueDaysFromAging,
  UNCOLLECTIBLE_OPTIONS,
  type UncollectibleFlag,
} from './useG2OverdueCheck'

export { UNCOLLECTIBLE_OPTIONS }
export type { UncollectibleFlag, K110ProvisionReconciliation }

export interface K1OverdueCheckRow {
  id: string
  seq: number
  debtorName: string
  openingBalance: number
  periodDebit: number
  periodCredit: number
  closingBalance: number
  aging: string
  businessDesc: string
  unrecoveredReason: string
  litigation: '' | '是' | '否'
  isUncollectible: UncollectibleFlag
  actionPlan: string
  provision: number
  auditedBalance: number
  postPeriodCollection: number
  remark: string
  overdueDays: number
  sourceRowId: string
}

interface StoredK1OverdueRow {
  id: string
  seq: number
  debtorName: string
  openingBalance: number
  periodDebit: number
  periodCredit: number
  aging: string
  businessDesc: string
  unrecoveredReason: string
  litigation: '' | '是' | '否'
  isUncollectible: UncollectibleFlag
  actionPlan: string
  provision: number
  auditedBalance: number
  postPeriodCollection: number
  remark: string
  sourceRowId: string
}

export interface K1OverdueCheckSummary {
  openingBalance: number
  periodDebit: number
  periodCredit: number
  closingBalance: number
  provision: number
  auditedBalance: number
  postPeriodCollection: number
  longTermCount: number
  uncollectibleCount: number
  litigationCount: number
}

const STORAGE_KEY = 'K1-10-overdue'
const AGING_PRESET_KEY = 'K1-10-aging-preset'
const AGING_CUSTOM_KEY = 'K1-10-aging-custom-segments'

function generateId(): string {
  return `k1-overdue-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function labelsToCustomSegments(labels: string[]): AgingSegment[] {
  return labels.map((label, i) => ({
    key: `custom-${i}`,
    label,
    dayFrom: 0,
    dayTo: null,
  }))
}

function parseCustomLabels(raw: string | null | undefined): string[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.map((x) => String(x || '').trim()).filter(Boolean)
  } catch {
    return []
  }
}

function buildStageHints(rows: K1OverdueCheckRow[]): OverdueStageHint[] {
  return buildK110StageHintsFromSources(rows.map((row) => ({
    debtorName: row.debtorName,
    closingBalance: row.closingBalance,
    aging: row.aging,
    overdueDays: row.overdueDays,
    isUncollectible: row.isUncollectible,
    litigation: row.litigation,
  })))
}

function resolveOverdueStage(
  row: K1OverdueCheckRow,
  stageLabel: ReturnType<typeof suggestEclStageFromAging>,
): 1 | 2 | 3 | null {
  let stage = stageLabelToNumber(stageLabel)
  if (row.isUncollectible === '是') stage = 3
  else if (row.isUncollectible === '部分' && (!stage || stage < 2)) stage = 2
  if (row.litigation === '是' && (!stage || stage < 2)) stage = 2
  return stage
}

function isLongTermAging(aging: string): boolean {
  const a = String(aging || '').trim()
  if (!a) return false
  if (/^1年以内|一年以内|within\s*1/i.test(a)) return false
  return true
}

function computeRow(stored: StoredK1OverdueRow): K1OverdueCheckRow {
  const closingBalance = calcAssetEndBalance(
    stored.openingBalance,
    stored.periodDebit,
    stored.periodCredit,
  )
  return {
    ...stored,
    closingBalance,
    overdueDays: estimateOverdueDaysFromAging(stored.aging),
  }
}

function createEmptyRow(seq: number): StoredK1OverdueRow {
  return {
    id: generateId(),
    seq,
    debtorName: '',
    openingBalance: 0,
    periodDebit: 0,
    periodCredit: 0,
    aging: '',
    businessDesc: '',
    unrecoveredReason: '',
    litigation: '',
    isUncollectible: '',
    actionPlan: '',
    provision: 0,
    auditedBalance: 0,
    postPeriodCollection: 0,
    remark: '',
    sourceRowId: '',
  }
}

function migrateLegacyRow(row: any, seq: number): StoredK1OverdueRow {
  if (
    row &&
    ('openingBalance' in row ||
      'periodDebit' in row ||
      'beginBalance' in row ||
      'debit' in row ||
      'debtorName' in row)
  ) {
    return {
      id: String(row.id || generateId()),
      seq: Number(row.seq) || seq,
      debtorName: String(row.debtorName || ''),
      openingBalance: parseNum(row.openingBalance ?? row.beginBalance),
      periodDebit: parseNum(row.periodDebit ?? row.debit),
      periodCredit: parseNum(row.periodCredit ?? row.credit),
      aging: String(row.aging || ''),
      businessDesc: String(row.businessDesc || ''),
      unrecoveredReason: String(row.unrecoveredReason || row.reason || ''),
      litigation: (['是', '否'].includes(row.litigation) ? row.litigation : '') as '' | '是' | '否',
      isUncollectible: (['是', '否', '部分'].includes(row.isUncollectible)
        ? row.isUncollectible
        : row.unrecoverable === '是'
          ? '是'
          : '') as UncollectibleFlag,
      actionPlan: String(row.actionPlan || row.plan || ''),
      provision: parseNum(row.provision),
      auditedBalance: parseNum(row.auditedBalance),
      postPeriodCollection: parseNum(row.postPeriodCollection ?? row.postCollection),
      remark: String(row.remark || ''),
      sourceRowId: String(row.sourceRowId || ''),
    }
  }
  return createEmptyRow(seq)
}

function safeParseBundle(jsonStr: string | null | undefined): {
  rows: StoredK1OverdueRow[]
  auditNote: string
  conclusion: string
  conclusionOption: string
} {
  if (!jsonStr) {
    return { rows: [], auditNote: '', conclusion: '', conclusionOption: '' }
  }
  try {
    const parsed = JSON.parse(jsonStr)
    if (Array.isArray(parsed)) {
      return {
        rows: parsed.map((r, i) => migrateLegacyRow(r, i + 1)),
        auditNote: '',
        conclusion: '',
        conclusionOption: '',
      }
    }
    const rawRows = parsed.rows ?? parsed.tables?.rows
    const rows = Array.isArray(rawRows)
      ? rawRows.map((r: any, i: number) => migrateLegacyRow(r, i + 1))
      : []
    return {
      rows,
      auditNote: String(parsed.auditNote ?? ''),
      conclusion: String(parsed.conclusion ?? ''),
      conclusionOption: String(parsed.conclusionOption ?? ''),
    }
  } catch {
    return { rows: [], auditNote: '', conclusion: '', conclusionOption: '' }
  }
}

export interface UseK1OverdueCheckOptions {
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly?: Ref<boolean>
  bsDate?: Ref<string>
  year?: Ref<number | undefined>
  onSave: (itemId: string, payload: { remark: string }) => void
}

export function useK1OverdueCheck(options: UseK1OverdueCheckOptions) {
  const { allResponses, projectId, isReadonly, onSave, bsDate, year } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const postPaymentLoading = ref(false)

  const auditNote = ref('')
  const conclusion = ref('')
  const conclusionOption = ref('')

  const { segments: projectSegments, preset: projectPreset } = useAgingConfig(projectId, 'K1')
  const sheetAgingPreset = ref<'' | AgingPreset>('')
  const customSegments = ref<AgingSegment[]>([])

  function loadMeta(): void {
    const bundle = safeParseBundle(allResponses.value.get(STORAGE_KEY)?.remark)
    auditNote.value = bundle.auditNote
    conclusion.value = bundle.conclusion
    conclusionOption.value = bundle.conclusionOption

    const rawPreset = String(allResponses.value.get(AGING_PRESET_KEY)?.remark || '').trim().toUpperCase()
    sheetAgingPreset.value =
      rawPreset === 'THREE_YEAR' || rawPreset === 'FIVE_YEAR' || rawPreset === 'CUSTOM' ? rawPreset : ''

    const labels = parseCustomLabels(allResponses.value.get(AGING_CUSTOM_KEY)?.remark)
    customSegments.value = labels.length >= 2 ? labelsToCustomSegments(labels) : []
  }

  watch(
    () => allResponses.value.get(STORAGE_KEY)?.remark,
    () => loadMeta(),
    { immediate: true },
  )
  watch(
    () => allResponses.value.get(AGING_PRESET_KEY)?.remark,
    (v) => {
      const raw = String(v || '').trim().toUpperCase()
      sheetAgingPreset.value =
        raw === 'THREE_YEAR' || raw === 'FIVE_YEAR' || raw === 'CUSTOM' ? raw : ''
    },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get(AGING_CUSTOM_KEY)?.remark,
    (v) => {
      const labels = parseCustomLabels(v)
      customSegments.value = labels.length >= 2 ? labelsToCustomSegments(labels) : []
    },
    { immediate: true },
  )

  const agingPreset: ComputedRef<AgingPreset> = computed(() => {
    if (sheetAgingPreset.value) return sheetAgingPreset.value
    const p = projectPreset.value
    if (p === 'THREE_YEAR' || p === 'FIVE_YEAR' || p === 'CUSTOM') return p
    return 'THREE_YEAR'
  })

  const segments: ComputedRef<AgingSegment[]> = computed(() => {
    if (sheetAgingPreset.value === 'CUSTOM') {
      if (customSegments.value.length >= 2) return customSegments.value
      if (projectPreset.value === 'CUSTOM' && projectSegments.value.length >= 2) {
        return projectSegments.value
      }
      return PRESET_SEGMENTS.THREE_YEAR
    }
    if (sheetAgingPreset.value === 'THREE_YEAR' || sheetAgingPreset.value === 'FIVE_YEAR') {
      return PRESET_SEGMENTS[sheetAgingPreset.value]
    }
    if (projectSegments.value.length) return projectSegments.value
    return PRESET_SEGMENTS.THREE_YEAR
  })

  const agingOptions: ComputedRef<string[]> = computed(() =>
    segments.value.map((s) => s.label),
  )

  const dataRows: ComputedRef<K1OverdueCheckRow[]> = computed(() => {
    const bundle = safeParseBundle(allResponses.value.get(STORAGE_KEY)?.remark)
    return bundle.rows.map(computeRow)
  })

  const displayRows: ComputedRef<K1OverdueCheckRow[]> = computed(() => {
    const rows = dataRows.value
    if (!rows.length) return rows
    const t = summary.value
    return [
      ...rows,
      {
        id: '__subtotal__',
        seq: 0,
        debtorName: '合计',
        openingBalance: t.openingBalance,
        periodDebit: t.periodDebit,
        periodCredit: t.periodCredit,
        closingBalance: t.closingBalance,
        aging: '',
        businessDesc: '',
        unrecoveredReason: '',
        litigation: '',
        isUncollectible: '',
        actionPlan: '',
        provision: t.provision,
        auditedBalance: t.auditedBalance,
        postPeriodCollection: t.postPeriodCollection,
        remark: '',
        overdueDays: 0,
        sourceRowId: '',
      },
    ]
  })

  const summary: ComputedRef<K1OverdueCheckSummary> = computed(() => {
    const rows = dataRows.value
    const longTermCount = rows.filter((r) => isLongTermAging(r.aging)).length
    const uncollectibleCount = rows.filter(
      (r) => r.isUncollectible === '是' || r.isUncollectible === '部分',
    ).length
    const litigationCount = rows.filter((r) => r.litigation === '是').length
    return {
      openingBalance: calcSubtotal(rows.map((r) => r.openingBalance)),
      periodDebit: calcSubtotal(rows.map((r) => r.periodDebit)),
      periodCredit: calcSubtotal(rows.map((r) => r.periodCredit)),
      closingBalance: calcSubtotal(rows.map((r) => r.closingBalance)),
      provision: calcSubtotal(rows.map((r) => r.provision)),
      auditedBalance: calcSubtotal(rows.map((r) => r.auditedBalance)),
      postPeriodCollection: calcSubtotal(rows.map((r) => r.postPeriodCollection)),
      longTermCount,
      uncollectibleCount,
      litigationCount,
    }
  })

  const provisionReconciliation: ComputedRef<K110ProvisionReconciliation> = computed(() =>
    computeK110ProvisionReconciliation(
      allResponses.value,
      dataRows.value.map((r) => ({ debtorName: r.debtorName, provision: r.provision })),
    ),
  )

  function isMetaRow(row: K1OverdueCheckRow): boolean {
    return row.id === '__subtotal__'
  }

  function isLongTerm(row: K1OverdueCheckRow): boolean {
    return isLongTermAging(row.aging)
  }

  function serializeBundle(rows: StoredK1OverdueRow[]): string {
    return JSON.stringify({
      rows,
      auditNote: auditNote.value,
      conclusion: conclusion.value,
      conclusionOption: conclusionOption.value,
    })
  }

  function persistRows(rows: StoredK1OverdueRow[]): void {
    const remark = serializeBundle(rows)
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark,
    })
    debounceSave(STORAGE_KEY, remark)
  }

  function debounceSave(itemId: string, remark: string): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      onSave(itemId, { remark })
    }, 400)
  }

  function flushSave(): void {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
    const remark = allResponses.value.get(STORAGE_KEY)?.remark
    if (remark != null) onSave(STORAGE_KEY, { remark: String(remark) })
  }

  function getStoredRows(): StoredK1OverdueRow[] {
    return safeParseBundle(allResponses.value.get(STORAGE_KEY)?.remark).rows
  }

  function addRow(): void {
    if (readonly.value) return
    const current = getStoredRows()
    const nextSeq = current.length ? Math.max(...current.map((r) => r.seq)) + 1 : 1
    current.push(createEmptyRow(nextSeq))
    persistRows(current)
  }

  function removeRow(id: string): void {
    if (readonly.value) return
    const current = getStoredRows().filter((r) => r.id !== id)
    current.forEach((r, i) => { r.seq = i + 1 })
    persistRows(current)
  }

  function updateCell(rowId: string, field: string, value: string | number): void {
    if (readonly.value || rowId === '__subtotal__') return
    const current = getStoredRows()
    const idx = current.findIndex((r) => r.id === rowId)
    if (idx === -1) return

    const alias: Record<string, string> = {
      beginBalance: 'openingBalance',
      debit: 'periodDebit',
      credit: 'periodCredit',
      reason: 'unrecoveredReason',
      plan: 'actionPlan',
      unrecoverable: 'isUncollectible',
      postCollection: 'postPeriodCollection',
    }
    const key = alias[field] || field
    const numeric = [
      'openingBalance',
      'periodDebit',
      'periodCredit',
      'provision',
      'auditedBalance',
      'postPeriodCollection',
    ]
    if (numeric.includes(key)) {
      ;(current[idx] as any)[key] = typeof value === 'number' ? value : parseNum(value)
    } else {
      ;(current[idx] as any)[key] = value
    }
    persistRows(current)
  }

  function setAgingPreset(preset: AgingPreset, customLabels?: string[]): boolean {
    if (readonly.value) return false
    if (preset === 'CUSTOM') {
      const labels = (customLabels || customSegments.value.map((s) => s.label))
        .map((x) => String(x || '').trim())
        .filter(Boolean)
      if (labels.length < 2) return false
      sheetAgingPreset.value = 'CUSTOM'
      customSegments.value = labelsToCustomSegments(labels.slice(0, 10))
      allResponses.value.set(AGING_PRESET_KEY, {
        item_id: AGING_PRESET_KEY,
        conclusion: null,
        remark: 'CUSTOM',
      })
      allResponses.value.set(AGING_CUSTOM_KEY, {
        item_id: AGING_CUSTOM_KEY,
        conclusion: null,
        remark: JSON.stringify(labels.slice(0, 10)),
      })
    } else {
      sheetAgingPreset.value = preset
      customSegments.value = []
      allResponses.value.set(AGING_PRESET_KEY, {
        item_id: AGING_PRESET_KEY,
        conclusion: null,
        remark: preset,
      })
      allResponses.value.set(AGING_CUSTOM_KEY, {
        item_id: AGING_CUSTOM_KEY,
        conclusion: null,
        remark: '[]',
      })
    }
    onSave(AGING_PRESET_KEY, { remark: preset })
    debounceSave(AGING_CUSTOM_KEY, allResponses.value.get(AGING_CUSTOM_KEY)?.remark ?? '[]')
    return true
  }

  /** 审定余额 = 期末 − 坏账准备 */
  function syncAuditedFromNet(rowId: string): void {
    if (readonly.value) return
    const current = getStoredRows()
    const idx = current.findIndex((r) => r.id === rowId)
    if (idx === -1) return
    const closing = calcAssetEndBalance(
      current[idx].openingBalance,
      current[idx].periodDebit,
      current[idx].periodCredit,
    )
    current[idx].auditedBalance = calcNetValue(closing, current[idx].provision)
    persistRows(current)
  }

  /** 从 K1-2 导入账龄超 1 年挂账 */
  function importFromDetail(): { imported: number; updated: number } {
    if (readonly.value) return { imported: 0, updated: 0 }
    const details = loadK1DetailPartials(allResponses.value)
    const longTerm = filterLongTermFromK1Detail(details)
    if (!longTerm.length) return { imported: 0, updated: 0 }

    const options = agingOptions.value
    const resolveAging = (label: string): string => {
      if (!label) return options.find((o) => !/^1年以内|一年以内/.test(o)) || options[1] || label
      const hit = options.find((o) => o === label || o.includes(label) || label.includes(o))
      return hit || label
    }

    const current = getStoredRows()
    const byName = new Map(current.map((r) => [r.debtorName.trim(), r]))
    let imported = 0
    let updated = 0
    let nextSeq = current.length ? Math.max(...current.map((r) => r.seq)) + 1 : 1

    for (const src of longTerm) {
      const name = src.debtorName.trim()
      if (!name) continue
      const aging = resolveAging(src.aging)
      const existing = byName.get(name)
      if (existing) {
        existing.openingBalance = src.openingBalance
        existing.provision = src.provision
        existing.auditedBalance = src.auditedBalance
        existing.aging = aging
        if (!existing.businessDesc && src.businessDesc) existing.businessDesc = src.businessDesc
        if (!existing.unrecoveredReason && src.unrecoveredReason) {
          existing.unrecoveredReason = src.unrecoveredReason
        }
        if (src.sourceRowId) existing.sourceRowId = src.sourceRowId
        const closing = src.closingBalance
        existing.periodDebit = Math.max(0, closing - existing.openingBalance)
        existing.periodCredit = Math.max(0, existing.openingBalance - closing)
        updated += 1
      } else {
        const closing = src.closingBalance
        const opening = src.openingBalance
        const row = createEmptyRow(nextSeq++)
        row.debtorName = name
        row.openingBalance = opening
        row.periodDebit = Math.max(0, closing - opening)
        row.periodCredit = Math.max(0, opening - closing)
        row.aging = aging
        row.businessDesc = src.businessDesc
        row.unrecoveredReason = src.unrecoveredReason
        row.provision = src.provision
        row.auditedBalance = src.auditedBalance
        row.remark = '来自K1-2超1年'
        row.sourceRowId = src.sourceRowId
        current.push(row)
        byName.set(name, row)
        imported += 1
      }
    }

    persistRows(current)
    return { imported, updated }
  }

  /** K1-10 → K1-7：写入阶段升级信号（只升不降） */
  function syncStagesToK17(): { added: number; upgraded: number; skipped: number } {
    if (readonly.value) return { added: 0, upgraded: 0, skipped: 0 }
    const hints = buildStageHints(dataRows.value)
    if (!hints.length) return { added: 0, upgraded: 0, skipped: dataRows.value.length }

    const current = parseK1StageRowsFromMap(allResponses.value)
    const merged = mergeOverdueStageHintsToK7(current, hints)
    const remark = JSON.stringify(merged.rows)
    allResponses.value.set(K1_STAGE_ROWS_KEY, {
      item_id: K1_STAGE_ROWS_KEY,
      conclusion: null,
      remark,
    })
    onSave(K1_STAGE_ROWS_KEY, { remark })
    const skipped = dataRows.value.length - hints.length
    return { added: merged.added, upgraded: merged.upgraded, skipped }
  }

  function persistTextFields(): void {
    persistRows(getStoredRows())
  }

  /** 从序时账 1221 贷方取期后回款，按债务人归集填入 postPeriodCollection */
  async function importPostPaymentFromLedger(monthsAfter = 6): Promise<{ matched: number; filledAmount: number }> {
    const empty = { matched: 0, filledAmount: 0 }
    if (readonly.value) return empty
    postPaymentLoading.value = true
    try {
      const current = getStoredRows()
      const result = await fetchK1PostPaymentFromLedger({
        projectId: projectId.value || '',
        bsDate: resolveK1BsDate(bsDate?.value, year?.value),
        rows: current.map((r) => ({ id: r.id, name: r.debtorName })),
        monthsAfter,
      })
      if (result.cancelled || result.matched === 0) return empty
      for (const [id, amt] of result.amounts) {
        const row = current.find((r) => r.id === id)
        if (row) row.postPeriodCollection = amt
      }
      persistRows(current)
      return { matched: result.matched, filledAmount: result.filledAmount }
    } finally {
      postPaymentLoading.value = false
    }
  }

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    auditNote,
    conclusion,
    conclusionOption,
    dataRows,
    displayRows,
    summary,
    provisionReconciliation,
    agingOptions,
    agingPreset,
    customSegments,
    isMetaRow,
    isLongTerm,
    addRow,
    removeRow,
    updateCell,
    setAgingPreset,
    syncAuditedFromNet,
    importFromDetail,
    importPostPaymentFromLedger,
    postPaymentLoading,
    syncStagesToK17,
    persistTextFields,
    flushSave,
    getStageSuggestion: (row: K1OverdueCheckRow) =>
      suggestEclStageFromAging(row.aging, row.overdueDays || 0),
    resolveOverdueStage: (row: K1OverdueCheckRow) =>
      resolveOverdueStage(row, suggestEclStageFromAging(row.aging, row.overdueDays || 0)),
  }
}

export default useK1OverdueCheck
