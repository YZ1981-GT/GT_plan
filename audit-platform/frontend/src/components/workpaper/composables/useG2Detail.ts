/**
 * useG2Detail — G2-2 应收利息明细表
 *
 * 对齐纸质底稿滚动核对：
 *   期初审定 = 期初余额 + 期初调整数
 *   期末余额 = 期初审定 + 借方发生 − 贷方发生
 *   期末审定 = 期末余额 + 账项调整
 *
 * 账龄：期初/期末审定两期动态段（项目配置 + 表级 3年段/5年段枚举）
 * 计息核对字段（面值/利率/起止日等）保留，便于与 G2-5 交叉核对。
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAccruedDays,
  calcInterest365,
  calcNetReceivable,
  calcDebitBalance,
  calcAdjustedAmount,
} from './useG2IntRecFormulaEngine'
import {
  useAgingConfig,
  PRESET_SEGMENTS,
  type AgingSegment,
  type AgingPreset,
} from '@/composables/useAgingConfig'
import { remapRowAgingData } from '@/composables/useAgingMigration'
import type { ChecklistResponse } from './useF1FormData'
import { ElMessage } from 'element-plus'
import { syncG2AgingPresetToAllSheets, type G2AgingSyncDetail } from './g2AgingSync'

// ─── Types ────────────────────────────────────────────────────────────────────

export type AgingBucket = Record<string, number>

export interface InterestDetailRow {
  id: string
  seq: number
  /** 投资种类 */
  investType: string
  /** 投资项目 */
  investTarget: string
  /** 期初余额 */
  openingUnadjusted: number
  /** 期初调整数 */
  openingAdjustment: number
  /** 期初余额审定数（公式） */
  openingAudited: number
  /** 借方发生 */
  debit: number
  /** 贷方发生 */
  credit: number
  /** 期末余额（公式） */
  closingUnadjusted: number
  /** 账项调整 */
  closingAdjustment: number
  /** 应收利息余额审定数（公式） */
  closingAudited: number
  /** 结息日 / 应收取的日期 */
  interestDueDate: string
  /** 原计收项目期 */
  accrualPeriod: string
  /** 流通或期后收款情况 */
  collectionStatus: string
  /** 计息核对（可选，对接 G2-5） */
  faceValue: number
  couponRate: number
  accrualStart: string
  accrualEnd: string
  accruedDays: number
  accruedInterest: number
  receivedInterest: number
  netReceivable: number
  eclStage: 'Stage1' | 'Stage2' | 'Stage3'
  agingPrior: AgingBucket
  agingAudited: AgingBucket
  remark: string
  indexRef: string
}

interface StoredDetailRow {
  id: string
  seq: number
  investType: string
  investTarget: string
  openingUnadjusted: number
  openingAdjustment: number
  debit: number
  credit: number
  closingAdjustment: number
  interestDueDate: string
  accrualPeriod: string
  collectionStatus: string
  faceValue: number
  couponRate: number
  accrualStart: string
  accrualEnd: string
  receivedInterest: number
  eclStage: 'Stage1' | 'Stage2' | 'Stage3'
  agingPrior?: AgingBucket
  agingAudited?: AgingBucket
  remark: string
  indexRef: string
}

export interface InterestDetailTotals {
  openingUnadjusted: number
  openingAdjustment: number
  openingAudited: number
  debit: number
  credit: number
  closingUnadjusted: number
  closingAdjustment: number
  closingAudited: number
  faceValue: number
  accruedInterest: number
  netReceivable: number
  agingPrior: AgingBucket
  agingAudited: AgingBucket
}

const STORAGE_KEY = 'G2-2-detail-rows'
const AGING_PRESET_KEY = 'G2-2-aging-preset'
const AGING_CUSTOM_KEY = 'G2-2-aging-custom-segments'

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

function generateId(): string {
  return `detail-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function emptyAging(segs: AgingSegment[]): AgingBucket {
  const out: AgingBucket = {}
  for (const s of segs) out[s.key] = 0
  return out
}

function normalizeAging(raw: unknown, segs: AgingSegment[]): AgingBucket {
  const src = raw && typeof raw === 'object' ? (raw as AgingBucket) : {}
  const out = emptyAging(segs)
  for (const s of segs) {
    out[s.key] = parseNum(src[s.key])
  }
  return out
}

function sumAging(rows: InterestDetailRow[], field: 'agingPrior' | 'agingAudited', segs: AgingSegment[]): AgingBucket {
  const out = emptyAging(segs)
  for (const row of rows) {
    for (const s of segs) {
      out[s.key] += parseNum(row[field]?.[s.key])
    }
  }
  return out
}

function safeParseRows(jsonStr: string | null | undefined, segs: AgingSegment[]): StoredDetailRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r: any) => {
      let openingUnadjusted = parseNum(r.openingUnadjusted ?? r.priorUnadjusted)
      const openingAdjustment = parseNum(r.openingAdjustment ?? r.priorAdjustment)
      const debit = parseNum(r.debit)
      const credit = parseNum(r.credit)
      const closingAdjustment = parseNum(r.closingAdjustment ?? r.endAje ?? r.adjustment)
      const hasRollForward =
        r.openingUnadjusted != null || r.priorUnadjusted != null || r.debit != null || r.credit != null
      // 旧版仅有 bookValue：迁入期初余额，便于滚动公式自洽
      if (!hasRollForward && r.bookValue != null) {
        openingUnadjusted = parseNum(r.bookValue)
      }
      return {
        id: String(r.id || generateId()),
        seq: Number(r.seq) || 0,
        investType: String(r.investType || ''),
        investTarget: String(r.investTarget || ''),
        openingUnadjusted,
        openingAdjustment,
        debit,
        credit,
        closingAdjustment,
        interestDueDate: String(r.interestDueDate || r.dueDate || ''),
        accrualPeriod: String(r.accrualPeriod || ''),
        collectionStatus: String(r.collectionStatus || ''),
        faceValue: parseNum(r.faceValue),
        couponRate: parseNum(r.couponRate),
        accrualStart: String(r.accrualStart || ''),
        accrualEnd: String(r.accrualEnd || ''),
        receivedInterest: parseNum(r.receivedInterest),
        eclStage: (r.eclStage === 'Stage2' || r.eclStage === 'Stage3' ? r.eclStage : 'Stage1') as StoredDetailRow['eclStage'],
        agingPrior: normalizeAging(r.agingPrior, segs),
        agingAudited: normalizeAging(r.agingAudited, segs),
        remark: String(r.remark || ''),
        indexRef: String(r.indexRef || ''),
      }
    })
  } catch {
    return []
  }
}

function computeRow(stored: StoredDetailRow, segs: AgingSegment[]): InterestDetailRow {
  const openingAudited = calcAdjustedAmount(stored.openingUnadjusted, stored.openingAdjustment, 0)
  const closingUnadjusted = calcDebitBalance(openingAudited, stored.debit, stored.credit)
  const closingAudited = calcAdjustedAmount(closingUnadjusted, stored.closingAdjustment, 0)
  const accruedDays = calcAccruedDays(stored.accrualStart, stored.accrualEnd)
  const accruedInterest = calcInterest365(stored.faceValue, stored.couponRate, accruedDays)
  const netReceivable = calcNetReceivable(accruedInterest, stored.receivedInterest)
  return {
    id: stored.id,
    seq: stored.seq,
    investType: stored.investType,
    investTarget: stored.investTarget,
    openingUnadjusted: stored.openingUnadjusted,
    openingAdjustment: stored.openingAdjustment,
    openingAudited,
    debit: stored.debit,
    credit: stored.credit,
    closingUnadjusted,
    closingAdjustment: stored.closingAdjustment,
    closingAudited,
    interestDueDate: stored.interestDueDate,
    accrualPeriod: stored.accrualPeriod,
    collectionStatus: stored.collectionStatus,
    faceValue: stored.faceValue,
    couponRate: stored.couponRate,
    accrualStart: stored.accrualStart,
    accrualEnd: stored.accrualEnd,
    accruedDays,
    accruedInterest,
    receivedInterest: stored.receivedInterest,
    netReceivable,
    eclStage: stored.eclStage,
    agingPrior: normalizeAging(stored.agingPrior, segs),
    agingAudited: normalizeAging(stored.agingAudited, segs),
    remark: stored.remark,
    indexRef: stored.indexRef,
  }
}

function createEmptyStoredRow(seq: number, segs: AgingSegment[]): StoredDetailRow {
  return {
    id: generateId(),
    seq,
    investType: '',
    investTarget: '',
    openingUnadjusted: 0,
    openingAdjustment: 0,
    debit: 0,
    credit: 0,
    closingAdjustment: 0,
    interestDueDate: '',
    accrualPeriod: '',
    collectionStatus: '',
    faceValue: 0,
    couponRate: 0,
    accrualStart: '',
    accrualEnd: '',
    receivedInterest: 0,
    eclStage: 'Stage1',
    agingPrior: emptyAging(segs),
    agingAudited: emptyAging(segs),
    remark: '',
    indexRef: '',
  }
}

export interface UseG2DetailOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export function useG2Detail(options: UseG2DetailOptions) {
  const { allResponses, projectId, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const { segments: projectSegments, preset: projectPreset } = useAgingConfig(projectId, 'G2')

  /** 表级覆盖：空串表示跟随项目配置（含项目 CUSTOM） */
  const sheetAgingPreset = ref<'' | AgingPreset>('')
  const customSegments = ref<AgingSegment[]>([])

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
    // 表级自定义
    if (sheetAgingPreset.value === 'CUSTOM') {
      if (customSegments.value.length >= 2) return customSegments.value
      if (projectPreset.value === 'CUSTOM' && projectSegments.value.length >= 2) {
        return projectSegments.value
      }
      return PRESET_SEGMENTS.THREE_YEAR
    }
    // 表级 3/5 年段覆盖
    if (sheetAgingPreset.value === 'THREE_YEAR' || sheetAgingPreset.value === 'FIVE_YEAR') {
      return PRESET_SEGMENTS[sheetAgingPreset.value] || PRESET_SEGMENTS.THREE_YEAR
    }
    // 跟随项目（含 CUSTOM）
    if (projectSegments.value.length) return projectSegments.value
    return PRESET_SEGMENTS.THREE_YEAR
  })

  const bands = computed(() =>
    segments.value.map((seg) => ({
      key: seg.key,
      label: seg.label,
      priorField: `agingPrior.${seg.key}`,
      auditedField: `agingAudited.${seg.key}`,
    })),
  )

  const dataRows: ComputedRef<InterestDetailRow[]> = computed(() => {
    const segs = segments.value
    const resp = allResponses.value.get(STORAGE_KEY)
    return safeParseRows(resp?.remark, segs).map((s) => computeRow(s, segs))
  })

  const totals: ComputedRef<InterestDetailTotals> = computed(() => {
    const rows = dataRows.value
    const segs = segments.value
    const sum = (fn: (r: InterestDetailRow) => number) => rows.reduce((s, r) => s + fn(r), 0)
    return {
      openingUnadjusted: sum((r) => r.openingUnadjusted),
      openingAdjustment: sum((r) => r.openingAdjustment),
      openingAudited: sum((r) => r.openingAudited),
      debit: sum((r) => r.debit),
      credit: sum((r) => r.credit),
      closingUnadjusted: sum((r) => r.closingUnadjusted),
      closingAdjustment: sum((r) => r.closingAdjustment),
      closingAudited: sum((r) => r.closingAudited),
      faceValue: sum((r) => r.faceValue),
      accruedInterest: sum((r) => r.accruedInterest),
      netReceivable: sum((r) => r.netReceivable),
      agingPrior: sumAging(rows, 'agingPrior', segs),
      agingAudited: sumAging(rows, 'agingAudited', segs),
    }
  })

  /** 账龄合计是否等于对应审定余额 */
  function isAgingBalanced(row: InterestDetailRow, stage: 'prior' | 'audited'): boolean {
    const segs = segments.value
    const bucket = stage === 'prior' ? row.agingPrior : row.agingAudited
    const sum = segs.reduce((s, seg) => s + parseNum(bucket?.[seg.key]), 0)
    const target = stage === 'prior' ? row.openingAudited : row.closingAudited
    return Math.abs(sum - target) < 0.005
  }

  function addRow(): void {
    if (readonly.value) return
    const segs = segments.value
    const current = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark, segs)
    const nextSeq = current.length > 0 ? Math.max(...current.map((r) => r.seq)) + 1 : 1
    current.push(createEmptyStoredRow(nextSeq, segs))
    persistRows(current)
  }

  function removeRow(id: string): void {
    if (readonly.value) return
    const segs = segments.value
    const current = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark, segs)
    const filtered = current.filter((r) => r.id !== id)
    filtered.forEach((r, i) => { r.seq = i + 1 })
    persistRows(filtered)
  }

  function updateCell(rowId: string, field: string, value: string | number): void {
    if (readonly.value) return
    const segs = segments.value
    const current = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark, segs)
    const idx = current.findIndex((r) => r.id === rowId)
    if (idx === -1) return

    if (field.startsWith('agingPrior.') || field.startsWith('agingAudited.')) {
      const [period, key] = field.split('.') as ['agingPrior' | 'agingAudited', string]
      const bucket = { ...(current[idx][period] || emptyAging(segs)) }
      bucket[key] = typeof value === 'number' ? value : parseNum(value)
      current[idx][period] = bucket
    } else {
      const numericFields = [
        'openingUnadjusted', 'openingAdjustment', 'debit', 'credit', 'closingAdjustment',
        'faceValue', 'couponRate', 'receivedInterest',
      ] as const
      if ((numericFields as readonly string[]).includes(field)) {
        ;(current[idx] as any)[field] = typeof value === 'number' ? value : parseNum(value)
      } else {
        ;(current[idx] as any)[field] = value
      }
    }
    persistRows(current)
  }

  /**
   * 切换账龄口径（对齐 F1-1：3年段 / 5年段 / 自定义）
   * CUSTOM 时须传入至少 2 个段名；成功返回 true。
   */
  function setAgingPreset(preset: AgingPreset, customLabels?: string[]): boolean {
    if (readonly.value) return false

    let segs: AgingSegment[]
    if (preset === 'CUSTOM') {
      const labels = (customLabels || customSegments.value.map((s) => s.label))
        .map((l) => l.trim())
        .filter(Boolean)
      if (labels.length < 2) {
        ElMessage.warning('自定义账龄至少需要 2 段')
        return false
      }
      segs = labelsToCustomSegments(labels)
      customSegments.value = segs
      allResponses.value.set(AGING_CUSTOM_KEY, {
        item_id: AGING_CUSTOM_KEY,
        conclusion: null,
        remark: JSON.stringify(labels),
      })
    } else {
      segs = PRESET_SEGMENTS[preset] || PRESET_SEGMENTS.THREE_YEAR
      customSegments.value = []
      allResponses.value.set(AGING_CUSTOM_KEY, {
        item_id: AGING_CUSTOM_KEY,
        conclusion: null,
        remark: '[]',
      })
    }

    sheetAgingPreset.value = preset
    allResponses.value.set(AGING_PRESET_KEY, {
      item_id: AGING_PRESET_KEY,
      conclusion: null,
      remark: preset,
    })

    const current = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark, segments.value)
    const remapped = current.map((row) => {
      const next = remapRowAgingData(row, segs, false) as StoredDetailRow
      return {
        ...next,
        agingPrior: normalizeAging(next.agingPrior, segs),
        agingAudited: normalizeAging(next.agingAudited, segs),
      }
    })
    persistRows(remapped)
    debounceSavePreset()
    return true
  }

  /** 快捷分配：将审定余额整笔填入指定账龄段 */
  function allocateAging(rowId: string, stage: 'prior' | 'audited', segmentKey: string): void {
    if (readonly.value) return
    const segs = segments.value
    const current = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark, segs)
    const idx = current.findIndex((r) => r.id === rowId)
    if (idx === -1) return
    const computed = computeRow(current[idx], segs)
    const empty = emptyAging(segs)
    if (stage === 'prior') {
      empty[segmentKey] = computed.openingAudited
      current[idx].agingPrior = empty
    } else {
      empty[segmentKey] = computed.closingAudited
      current[idx].agingAudited = empty
    }
    persistRows(current)
  }

  function persistRows(rows: StoredDetailRow[]): void {
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark: JSON.stringify(rows),
    })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function debounceSavePreset(): void {
    debounceSave()
  }

  function flushSave(): void {
    try {
      const items = [
        allResponses.value.get(STORAGE_KEY),
        allResponses.value.get(AGING_PRESET_KEY),
        allResponses.value.get(AGING_CUSTOM_KEY),
      ].filter(Boolean)
      window.dispatchEvent(new CustomEvent('g2:save-items', { detail: { items } }))
    } catch { /* silent */ }
  }

  const agingConfigHandler = () => {
    // 表级已覆盖时不跟随项目刷新；CUSTOM 表级亦独立
    if (sheetAgingPreset.value === 'THREE_YEAR' || sheetAgingPreset.value === 'FIVE_YEAR') return
    if (sheetAgingPreset.value === 'CUSTOM' && customSegments.value.length >= 2) return
    if (!segments.value.length) return
    const segs = segments.value
    const current = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark, segs)
    const remapped = current.map((row) => {
      const next = remapRowAgingData(row, segs, false) as StoredDetailRow
      return {
        ...next,
        agingPrior: normalizeAging(next.agingPrior, segs),
        agingAudited: normalizeAging(next.agingAudited, segs),
      }
    })
    persistRows(remapped)
  }
  window.addEventListener('aging-config:changed', agingConfigHandler)
  eventListeners.push({ event: 'aging-config:changed', handler: agingConfigHandler })

  /** 将当前表账龄口径同步到 G2-3/6/7 */
  function syncAgingAcrossSheets(): void {
    if (readonly.value) return
    const labels =
      agingPreset.value === 'CUSTOM'
        ? customSegments.value.map((s) => s.label)
        : []
    syncG2AgingPresetToAllSheets(
      allResponses.value,
      agingPreset.value,
      labels,
      'G2-2',
    )
    ElMessage.success('已同步账龄口径至 G2-3 / G2-6 / G2-7')
  }

  const onG2AgingSync = (e: Event) => {
    const d = (e as CustomEvent<G2AgingSyncDetail>).detail
    if (!d?.preset || d.source === 'G2-2') return
    setAgingPreset(d.preset, d.customLabels)
  }
  window.addEventListener('g2:aging-preset-sync', onG2AgingSync)
  eventListeners.push({ event: 'g2:aging-preset-sync', handler: onG2AgingSync })

  onBeforeUnmount(() => {
    for (const { event, handler } of eventListeners) {
      window.removeEventListener(event, handler)
    }
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    dataRows,
    totals,
    segments,
    bands,
    agingPreset,
    customSegments,
    isAgingBalanced,
    addRow,
    removeRow,
    updateCell,
    setAgingPreset,
    allocateAging,
    syncAgingAcrossSheets,
  }
}

export default useG2Detail
