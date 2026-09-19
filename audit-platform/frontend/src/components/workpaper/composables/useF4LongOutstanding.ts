/**
 * useF4LongOutstanding — F4-5 账龄1年以上应付账款检查表
 *
 * 源表字段：债权人、期末余额、账龄、经济业务说明、未偿还/未结转原因、
 * 是否无法支付、是否诉讼、支付计划、审定金额、支持性证据、备注。
 */
import { computed, inject, onBeforeUnmount, ref, watch, type ComputedRef, type Ref } from 'vue'
import { calcSubtotal, parseNum } from './useF4AccPayFormulaEngine'
import { computeF4DetailRow, migrateF4DetailRows } from './useF4Detail'
import { readRowJson, type ChecklistResponse } from './useF4FormData'
import {
  PRESET_SEGMENTS,
  useAgingConfig,
  DEFAULT_SUBJECT_PRESETS,
  type AgingSegment,
} from '@/composables/useAgingConfig'
import { f4AgingLabel, f4AgingValue } from './f4AgingModel'

/**
 * @deprecated 账龄档位改由项目账龄配置驱动（`buildF4LongAgingOptions(segments)`）；
 * 本常量仅保留为 3 年段回退与旧调用方兼容。
 */
export const F4_LONG_AGING_OPTIONS = ['1～2年', '2～3年', '3年以上'] as const
export const F4_YES_NO_OPTIONS = ['是', '否', '不适用'] as const
export const F4_DISPOSAL_CONCLUSIONS = [
  '应确认收入',
  '应退回',
  '正常挂账',
  '应转营业外收入',
  '待确定',
] as const

export interface F4LongOutstandingOcrFields {
  creditor?: string
  closingBalance?: number | string
  aging?: string
  businessDescription?: string
  unsettledReason?: string
  unableToPay?: string
  litigation?: string
  paymentPlan?: string
  auditedAmount?: number | string
  supportingEvidence?: string
  remark?: string
}

export interface LongOutstandingRow {
  rowId: string
  seq: number
  attSlot: number
  /** F4-2归集行ID组合；空表示手工行。 */
  sourceRowId: string
  creditor: string
  closingBalance: number
  aging: string
  businessDescription: string
  unsettledReason: string
  unableToPay: string
  litigation: string
  paymentPlan: string
  auditedAmount: number
  supportingEvidence: string
  disposalConclusion: string
  remark: string
  linked: boolean
  adjustmentAmount: number
  riskFlags: string[]
  highlightLevel: 'none' | 'warning' | 'danger'
}

interface StoredLongOutstandingRow {
  rowId: string
  seq: number
  attSlot: number
  sourceRowId: string
  creditor: string
  closingBalance: number
  aging: string
  businessDescription: string
  unsettledReason: string
  unableToPay: string
  litigation: string
  paymentPlan: string
  auditedAmount: number
  supportingEvidence: string
  disposalConclusion: string
  remark: string
}

export interface F4LongOutstandingCandidate {
  sourceRowId: string
  creditor: string
  closingBalance: number
  aging: string
  businessDescription: string
  auditedAmount: number
}

export interface UseF4LongOutstandingOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

const STORAGE_KEY = 'F4-5-rows'
const DETAIL_KEY = 'F4-2-rows'
const NOTE_KEY = 'F4-5-audit-note'
const CONCLUSION_KEY = 'F4-5-audit-conclusion'
const LEGACY_NOTE_KEY = 'F4-5-note'
const TOLERANCE = 0.005

function generateRowId(): string {
  return `f4lo-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function nextAttSlot(rows: StoredLongOutstandingRow[]): number {
  return Math.max(0, ...rows.map((row) => Number(row.attSlot) || 0)) + 1
}

export function emptyLongOutstandingRow(seq: number, attSlot = seq): StoredLongOutstandingRow {
  return {
    rowId: generateRowId(),
    seq,
    attSlot,
    sourceRowId: '',
    creditor: '',
    closingBalance: 0,
    aging: '',
    businessDescription: '',
    unsettledReason: '',
    unableToPay: '',
    litigation: '',
    paymentPlan: '',
    auditedAmount: 0,
    supportingEvidence: '',
    disposalConclusion: '',
    remark: '',
  }
}

function agingFromLegacyDays(days: number): string {
  if (days > 365 * 3) return '3年以上'
  if (days > 365 * 2) return '2～3年'
  if (days > 365) return '1～2年'
  return ''
}

function legacyRemark(raw: any): string {
  return [raw?.remark, raw?.suggestion ? `原处理建议：${raw.suggestion}` : '']
    .filter(Boolean)
    .join('；')
}

function migrateRow(raw: any, index: number): StoredLongOutstandingRow {
  const base = emptyLongOutstandingRow(index + 1, Number(raw?.attSlot) || index + 1)
  const closingBalance = parseNum(raw?.closingBalance ?? raw?.amount ?? raw?.hangAmount)
  return {
    ...base,
    rowId: String(raw?.rowId ?? raw?.id ?? generateRowId()),
    seq: Number(raw?.seq) || index + 1,
    sourceRowId: String(raw?.sourceRowId ?? ''),
    creditor: String(raw?.creditor ?? raw?.creditorName ?? ''),
    closingBalance,
    aging: String(raw?.aging || agingFromLegacyDays(parseNum(raw?.outstandingDays ?? raw?.hangDays))),
    businessDescription: String(raw?.businessDescription ?? raw?.paymentNature ?? raw?.nature ?? ''),
    unsettledReason: String(raw?.unsettledReason ?? raw?.reason ?? raw?.hangReason ?? ''),
    unableToPay: String(
      raw?.unableToPay
      ?? raw?.shouldTransferIncome
      ?? raw?.needTransferIncome
      ?? '',
    ),
    litigation: String(raw?.litigation ?? raw?.hasDispute ?? ''),
    paymentPlan: String(raw?.paymentPlan ?? ''),
    auditedAmount: raw?.auditedAmount == null ? closingBalance : parseNum(raw.auditedAmount),
    supportingEvidence: String(raw?.supportingEvidence ?? ''),
    disposalConclusion: String(raw?.disposalConclusion ?? ''),
    remark: legacyRemark(raw),
  }
}

export function migrateF4LongOutstandingRows(value: string | null | undefined): StoredLongOutstandingRow[] {
  if (!value) return []
  try {
    const parsed = JSON.parse(value)
    if (!Array.isArray(parsed)) return []
    return parsed.map(migrateRow).map((row, index) => ({ ...row, seq: index + 1 }))
  } catch {
    return []
  }
}

function ageLabels(amounts: number[], labels: readonly string[]): string {
  return labels
    .filter((_, index) => Math.abs(amounts[index] ?? 0) >= TOLERANCE)
    .join('、')
}

/** 「1 年以上」账龄段候选选项（dayFrom>=366，段驱动，取代硬编码 3 档） */
export function buildF4LongAgingOptions(segments: readonly AgingSegment[]): string[] {
  const segs = segments?.length ? segments : (PRESET_SEGMENTS.THREE_YEAR as AgingSegment[])
  return segs.filter((seg) => Number(seg.dayFrom) >= 366).map(f4AgingLabel)
}

/** 「3 年以上」段 label 集合（用于风险提示，段驱动） */
export function buildF4OverThreeLabels(segments: readonly AgingSegment[]): string[] {
  const segs = segments?.length ? segments : (PRESET_SEGMENTS.THREE_YEAR as AgingSegment[])
  return segs.filter((seg) => Number(seg.dayFrom) >= 1096).map(f4AgingLabel)
}

/** 从F4-2提取包含1年以上账龄的实际债权人，并按名称归集（账龄段驱动）。 */
export function extractF4LongOutstandingCandidates(
  value: string | null | undefined,
  segments?: readonly AgingSegment[],
): F4LongOutstandingCandidate[] {
  const segs = (segments?.length ? segments : PRESET_SEGMENTS.THREE_YEAR) as AgingSegment[]
  const detailRows = migrateF4DetailRows(value, segs).map((row) => computeF4DetailRow(row, segs))
  // 「1 年以上」段由 dayFrom>=366 派生（Property 4），残差行不属段故不参与
  const longSegs = segs.filter((seg) => Number(seg.dayFrom) >= 366)
  const longKeys = longSegs.map((seg) => String(seg.key))
  const longLabels = longSegs.map(f4AgingLabel)
  const grouped = new Map<string, {
    rowIds: string[]
    creditor: string
    closingBalance: number
    auditedAmount: number
    longAging: number[]
    descriptions: Set<string>
  }>()

  for (const row of detailRows) {
    const creditor = row.creditor.trim()
    if (!creditor) continue
    const auditedBuckets = longKeys.map((key) => f4AgingValue(row, 'audited', key))
    const unadjustedBuckets = longKeys.map((key) => f4AgingValue(row, 'current', key))
    const buckets = auditedBuckets.some((amount) => Math.abs(amount) >= TOLERANCE)
      ? auditedBuckets
      : unadjustedBuckets
    if (!buckets.some((amount) => Math.abs(amount) >= TOLERANCE)) continue

    const key = creditor.toLocaleLowerCase('zh-CN')
    const target = grouped.get(key) ?? {
      rowIds: [],
      creditor,
      closingBalance: 0,
      auditedAmount: 0,
      longAging: longKeys.map(() => 0),
      descriptions: new Set<string>(),
    }
    target.rowIds.push(row.rowId)
    target.closingBalance += row.closingUnadjusted
    target.auditedAmount += row.closingAdjusted
    buckets.forEach((amount, index) => { target.longAging[index] += amount })
    if (row.paymentNature) target.descriptions.add(row.paymentNature)
    grouped.set(key, target)
  }

  return [...grouped.values()]
    .sort((a, b) =>
      Math.abs(b.auditedAmount) - Math.abs(a.auditedAmount)
      || a.creditor.localeCompare(b.creditor, 'zh-CN'),
    )
    .map((row) => ({
      sourceRowId: row.rowIds.sort().join('|'),
      creditor: row.creditor,
      closingBalance: row.closingBalance,
      aging: ageLabels(row.longAging, longLabels),
      businessDescription: [...row.descriptions].join('、'),
      auditedAmount: row.auditedAmount,
    }))
}

function computeRow(
  stored: StoredLongOutstandingRow,
  source?: F4LongOutstandingCandidate,
  overThreeLabels: readonly string[] = ['3年以上'],
): LongOutstandingRow {
  const creditor = source?.creditor ?? stored.creditor
  const closingBalance = source?.closingBalance ?? stored.closingBalance
  const aging = source?.aging ?? stored.aging
  const businessDescription = stored.businessDescription || source?.businessDescription || ''
  const auditedAmount = source?.auditedAmount ?? stored.auditedAmount
  const labels = overThreeLabels.length ? overThreeLabels : ['3年以上']
  const hasOverThree = labels.some((label) => aging.includes(label))
  const riskFlags: string[] = []
  if (hasOverThree) riskFlags.push('含3年以上账龄')
  if (stored.unableToPay === '是') riskFlags.push('可能无法支付')
  else if (!stored.unableToPay) riskFlags.push('支付能力待判断')
  if (stored.litigation === '是') riskFlags.push('涉及诉讼')
  else if (!stored.litigation) riskFlags.push('诉讼状态待判断')
  if (creditor && !stored.unsettledReason.trim()) riskFlags.push('未说明长期挂账原因')
  if (creditor && !stored.paymentPlan.trim()) riskFlags.push('支付计划缺失')
  if (creditor && !stored.supportingEvidence.trim()) riskFlags.push('支持性证据待补')
  const adjustmentAmount = auditedAmount - closingBalance
  if (Math.abs(adjustmentAmount) >= TOLERANCE) riskFlags.push('存在审计调整')

  let highlightLevel: LongOutstandingRow['highlightLevel'] = 'none'
  if (stored.unableToPay === '是' || stored.litigation === '是' || hasOverThree) {
    highlightLevel = 'danger'
  } else if (riskFlags.length) {
    highlightLevel = 'warning'
  }

  return {
    ...stored,
    creditor,
    closingBalance,
    aging,
    businessDescription,
    auditedAmount,
    linked: !!source,
    adjustmentAmount,
    riskFlags,
    highlightLevel,
  }
}

export function isBlankLongOutstandingRow(row: StoredLongOutstandingRow): boolean {
  return !row.creditor && !row.closingBalance && !row.aging && !row.businessDescription
    && !row.unsettledReason && !row.paymentPlan && !row.auditedAmount
    && !row.supportingEvidence && !row.remark && !row.sourceRowId
}

export function useF4LongOutstanding(options: UseF4LongOutstandingOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const storedData = ref<StoredLongOutstandingRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  function loadRows(): void {
    storedData.value = migrateF4LongOutstandingRows(readRowJson(allResponses.value.get(STORAGE_KEY)))
    if (!storedData.value.length) storedData.value = [emptyLongOutstandingRow(1)]
  }

  watch(
    () => readRowJson(allResponses.value.get(STORAGE_KEY)),
    (raw) => {
      if (raw && raw === JSON.stringify(storedData.value)) return
      loadRows()
    },
    { immediate: true },
  )
  watch(
    () => [
      allResponses.value.get(NOTE_KEY)?.remark,
      allResponses.value.get(CONCLUSION_KEY)?.remark,
      allResponses.value.get(LEGACY_NOTE_KEY)?.remark,
    ],
    ([note, conclusion, legacy]) => {
      auditNote.value = note || ''
      auditConclusion.value = conclusion || legacy || ''
    },
    { immediate: true },
  )

  // ─── 账龄段（主入口 provide 优先） ──────────────────────────────────────────
  const injectedSegments = inject<Ref<AgingSegment[]> | null>('f4AgingSegments', null)
  const ownConfig = injectedSegments ? null : useAgingConfig(options.projectId, 'F4')
  const segments: ComputedRef<AgingSegment[]> = computed(() => {
    const raw = injectedSegments?.value ?? ownConfig?.segments.value ?? []
    return raw.length
      ? raw
      : (PRESET_SEGMENTS[DEFAULT_SUBJECT_PRESETS.F4 ?? 'THREE_YEAR'] as AgingSegment[])
  })
  /** 账龄下拉候选（1 年以上段，dayFrom>=366） */
  const agingOptions = computed(() => buildF4LongAgingOptions(segments.value))
  const overThreeLabels = computed(() => buildF4OverThreeLabels(segments.value))

  const detailCandidates = computed(() =>
    extractF4LongOutstandingCandidates(
      readRowJson(allResponses.value.get(DETAIL_KEY)),
      segments.value,
    ),
  )

  const rows: ComputedRef<LongOutstandingRow[]> = computed(() =>
    storedData.value.map((stored) => computeRow(
      stored,
      stored.sourceRowId
        ? detailCandidates.value.find((source) => source.sourceRowId === stored.sourceRowId)
        : undefined,
      overThreeLabels.value,
    )),
  )
  const filledCount = computed(() => rows.value.filter((row) =>
    row.creditor || Math.abs(row.closingBalance) >= TOLERANCE,
  ).length)
  const pendingSyncCount = computed(() => {
    const linked = new Set(storedData.value.map((row) => row.sourceRowId).filter(Boolean))
    return detailCandidates.value.filter((source) => !linked.has(source.sourceRowId)).length
  })

  const summary = computed(() => ({
    count: filledCount.value,
    closingTotal: calcSubtotal(rows.value.map((row) => row.closingBalance)),
    auditedTotal: calcSubtotal(rows.value.map((row) => row.auditedAmount)),
    adjustmentTotal: calcSubtotal(rows.value.map((row) => row.adjustmentAmount)),
    unableToPayAmount: calcSubtotal(
      rows.value.filter((row) => row.unableToPay === '是').map((row) => row.auditedAmount),
    ),
    litigationAmount: calcSubtotal(
      rows.value.filter((row) => row.litigation === '是').map((row) => row.auditedAmount),
    ),
    missingEvidenceCount: rows.value.filter((row) =>
      row.creditor && !row.supportingEvidence.trim(),
    ).length,
    highRiskCount: rows.value.filter((row) => row.highlightLevel === 'danger').length,
  }))

  function syncFromDetail(): number {
    if (readonly.value) return 0
    const linked = new Set(storedData.value.map((row) => row.sourceRowId).filter(Boolean))
    const pending = detailCandidates.value.filter((source) => !linked.has(source.sourceRowId))
    if (pending.length && storedData.value.length === 1 && isBlankLongOutstandingRow(storedData.value[0])) {
      storedData.value = []
    }
    for (const source of pending) {
      storedData.value.push({
        ...emptyLongOutstandingRow(storedData.value.length + 1, nextAttSlot(storedData.value)),
        sourceRowId: source.sourceRowId,
        creditor: source.creditor,
        closingBalance: source.closingBalance,
        aging: source.aging,
        businessDescription: source.businessDescription,
        auditedAmount: source.auditedAmount,
      })
    }
    if (pending.length) persistRows()
    return pending.length
  }

  function addRow(): void {
    if (readonly.value) return
    storedData.value.push(
      emptyLongOutstandingRow(storedData.value.length + 1, nextAttSlot(storedData.value)),
    )
    persistRows()
  }

  function removeRow(rowId: string): void {
    if (readonly.value) return
    const index = storedData.value.findIndex((row) => row.rowId === rowId)
    if (index === -1) return
    storedData.value.splice(index, 1)
    if (!storedData.value.length) storedData.value.push(emptyLongOutstandingRow(1))
    storedData.value.forEach((row, i) => { row.seq = i + 1 })
    persistRows()
  }

  function updateCell(rowId: string, field: string, value: unknown): void {
    if (readonly.value) return
    const row = storedData.value.find((item) => item.rowId === rowId)
    if (!row) return
    const numeric = new Set(['closingBalance', 'auditedAmount'])
    ;(row as any)[field] = numeric.has(field)
      ? parseNum(value as string | number | null | undefined)
      : String(value ?? '')
    persistRows()
  }

  function mergeOcrFields(
    rowId: string,
    fields: F4LongOutstandingOcrFields,
    overwrite = false,
  ): void {
    if (readonly.value) return
    const row = storedData.value.find((item) => item.rowId === rowId)
    if (!row) return
    const mapping: Array<[keyof StoredLongOutstandingRow, unknown]> = [
      ['creditor', fields.creditor],
      ['closingBalance', fields.closingBalance],
      ['aging', fields.aging],
      ['businessDescription', fields.businessDescription],
      ['unsettledReason', fields.unsettledReason],
      ['unableToPay', fields.unableToPay],
      ['litigation', fields.litigation],
      ['paymentPlan', fields.paymentPlan],
      ['auditedAmount', fields.auditedAmount],
      ['supportingEvidence', fields.supportingEvidence],
      ['remark', fields.remark],
    ]
    const numeric = new Set<keyof StoredLongOutstandingRow>(['closingBalance', 'auditedAmount'])
    for (const [field, value] of mapping) {
      if (value == null || value === '') continue
      const current = row[field]
      if (!overwrite && current !== '' && current !== 0) continue
      ;(row as any)[field] = numeric.has(field)
        ? parseNum(value as string | number | null | undefined)
        : String(value)
    }
    persistRows()
  }

  function setText(key: string, value: string): void {
    allResponses.value.set(key, { item_id: key, conclusion: null, remark: value })
    debounceSave()
  }

  function saveAuditNote(value: string): void {
    if (readonly.value) return
    auditNote.value = value
    setText(NOTE_KEY, value)
  }

  function saveAuditConclusion(value: string): void {
    if (readonly.value) return
    auditConclusion.value = value
    setText(CONCLUSION_KEY, value)
  }

  function persistRows(): void {
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark: JSON.stringify(storedData.value),
    })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 1200)
  }

  function flushSave(): void {
    const items = [STORAGE_KEY, NOTE_KEY, CONCLUSION_KEY]
      .map((key) => allResponses.value.get(key))
      .filter(Boolean)
    if (items.length) {
      window.dispatchEvent(new CustomEvent('f4:save-items', { detail: { items } }))
    }
  }

  function rowClassName({ row }: { row: LongOutstandingRow }): string {
    if (row.highlightLevel === 'danger') return 'long-outstanding-danger'
    if (row.highlightLevel === 'warning') return 'long-outstanding-warning'
    return ''
  }

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    rows,
    summary,
    filledCount,
    pendingSyncCount,
    segments,
    agingOptions,
    auditNote,
    auditConclusion,
    loadRows,
    syncFromDetail,
    addRow,
    removeRow,
    updateCell,
    mergeOcrFields,
    saveAuditNote,
    saveAuditConclusion,
    rowClassName,
  }
}

export default useF4LongOutstanding
