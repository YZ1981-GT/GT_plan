/**
 * useG2BadDebtDetail — G2-3 坏账准备明细表（对齐致同 Excel 滚动态）
 *
 * 结构：按单项评估计提（动态行）+ 信用风险组合计提（账龄段展开）+ 合计
 * 账龄枚举：3年段 / 5年段 / 自定义（跟随项目配置）
 *
 * 公式：
 *   期初审定 = 期初未审 + 期初账项调整
 *   期末未审 = 期初审定 + 计提 + 其他增加 − 转回 − 转销 − 其他减少
 *   期末审定 = 期末未审 + 期末账项调整
 *
 * 存储：扁平 leaf 数组（含 category），导入导出可 round-trip。
 * ECL 三阶段测算保留在 G2-7。
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { parseNum, calcSubtotal } from './useG2IntRecFormulaEngine'
import {
  useAgingConfig,
  PRESET_SEGMENTS,
  type AgingSegment,
  type AgingPreset,
} from '@/composables/useAgingConfig'
import { syncG2AgingPresetToAllSheets } from './g2AgingSync'
import type { ChecklistResponse } from './useF1FormData'

export type G2BadDebtCategory = 'individual' | 'portfolio'
export type G2BadDebtRowKind = 'section_header' | 'leaf' | 'footer'
export type G2AgingPresetChoice = '' | 'THREE_YEAR' | 'FIVE_YEAR' | 'CUSTOM'

export interface BadDebtDetailRow {
  id: string
  seq: number
  category: G2BadDebtCategory
  kind: G2BadDebtRowKind
  item: string
  agingKey?: string
  editable: boolean
  openingUnadjusted: number
  openingAdjustment: number
  openingAudited: number
  provisionIncrease: number
  otherIncrease: number
  reversal: number
  writeOff: number
  otherDecrease: number
  closingUnadjusted: number
  closingAdjustment: number
  closingAudited: number
  reason: string
  /** 兼容旧字段 */
  investTarget?: string
  closingBalance?: number
  eclAmount?: number
  companyProvision?: number
  variance?: number
  periodChange?: number
}

export interface StoredLeafRow {
  id: string
  seq: number
  category: G2BadDebtCategory
  item: string
  agingKey?: string
  openingUnadjusted: number
  openingAdjustment: number
  provisionIncrease: number
  otherIncrease: number
  reversal: number
  writeOff: number
  otherDecrease: number
  closingAdjustment: number
  reason: string
}

export interface BadDebtTotals {
  openingUnadjusted: number
  openingAdjustment: number
  openingAudited: number
  provisionIncrease: number
  otherIncrease: number
  reversal: number
  writeOff: number
  otherDecrease: number
  closingUnadjusted: number
  closingAdjustment: number
  closingAudited: number
  closingBalance: number
  eclAmount: number
  companyProvision: number
  variance: number
  periodChange: number
}

const STORAGE_KEY = 'G2-3-bad-debt-rows'
const AGING_PRESET_KEY = 'G2-3-aging-preset'
const AGING_CUSTOM_KEY = 'G2-3-aging-custom-segments'

function generateId(prefix = 'bdebt'): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function emptyLeaf(
  category: G2BadDebtCategory,
  seq: number,
  item: string,
  agingKey?: string,
): StoredLeafRow {
  return {
    id: generateId(category === 'portfolio' ? 'port' : 'ind'),
    seq,
    category,
    item,
    agingKey,
    openingUnadjusted: 0,
    openingAdjustment: 0,
    provisionIncrease: 0,
    otherIncrease: 0,
    reversal: 0,
    writeOff: 0,
    otherDecrease: 0,
    closingAdjustment: 0,
    reason: '',
  }
}

function computeAmounts(stored: StoredLeafRow) {
  const openingAudited = stored.openingUnadjusted + stored.openingAdjustment
  const closingUnadjusted =
    openingAudited +
    stored.provisionIncrease +
    stored.otherIncrease -
    stored.reversal -
    stored.writeOff -
    stored.otherDecrease
  const closingAudited = closingUnadjusted + stored.closingAdjustment
  return { openingAudited, closingUnadjusted, closingAudited }
}

function toDisplayLeaf(stored: StoredLeafRow): BadDebtDetailRow {
  const d = computeAmounts(stored)
  return {
    id: stored.id,
    seq: stored.seq,
    category: stored.category,
    kind: 'leaf',
    item: stored.item,
    agingKey: stored.agingKey,
    editable: true,
    openingUnadjusted: stored.openingUnadjusted,
    openingAdjustment: stored.openingAdjustment,
    openingAudited: d.openingAudited,
    provisionIncrease: stored.provisionIncrease,
    otherIncrease: stored.otherIncrease,
    reversal: stored.reversal,
    writeOff: stored.writeOff,
    otherDecrease: stored.otherDecrease,
    closingUnadjusted: d.closingUnadjusted,
    closingAdjustment: stored.closingAdjustment,
    closingAudited: d.closingAudited,
    reason: stored.reason,
    investTarget: stored.item,
    closingBalance: d.closingAudited,
    eclAmount: d.closingAudited,
    companyProvision: d.closingAudited,
    variance: 0,
    periodChange:
      stored.provisionIncrease +
      stored.otherIncrease -
      stored.reversal -
      stored.writeOff -
      stored.otherDecrease,
  }
}

function sumLeaves(rows: StoredLeafRow[]): BadDebtTotals {
  const openingUnadjusted = calcSubtotal(rows.map((r) => r.openingUnadjusted))
  const openingAdjustment = calcSubtotal(rows.map((r) => r.openingAdjustment))
  const provisionIncrease = calcSubtotal(rows.map((r) => r.provisionIncrease))
  const otherIncrease = calcSubtotal(rows.map((r) => r.otherIncrease))
  const reversal = calcSubtotal(rows.map((r) => r.reversal))
  const writeOff = calcSubtotal(rows.map((r) => r.writeOff))
  const otherDecrease = calcSubtotal(rows.map((r) => r.otherDecrease))
  const closingAdjustment = calcSubtotal(rows.map((r) => r.closingAdjustment))
  const openingAudited = openingUnadjusted + openingAdjustment
  const closingUnadjusted =
    openingAudited + provisionIncrease + otherIncrease - reversal - writeOff - otherDecrease
  const closingAudited = closingUnadjusted + closingAdjustment
  const periodChange =
    provisionIncrease + otherIncrease - reversal - writeOff - otherDecrease
  return {
    openingUnadjusted,
    openingAdjustment,
    openingAudited,
    provisionIncrease,
    otherIncrease,
    reversal,
    writeOff,
    otherDecrease,
    closingUnadjusted,
    closingAdjustment,
    closingAudited,
    closingBalance: closingAudited,
    eclAmount: closingAudited,
    companyProvision: closingAudited,
    variance: 0,
    periodChange,
  }
}

function normalizeLeaf(r: any, fallbackCategory: G2BadDebtCategory, seq: number): StoredLeafRow {
  const category: G2BadDebtCategory =
    r.category === 'portfolio' || r.category === 'individual'
      ? r.category
      : fallbackCategory
  return {
    id: String(r.id || generateId(category === 'portfolio' ? 'port' : 'ind')),
    seq: Number(r.seq) || seq,
    category,
    item: String(r.item || r.investTarget || ''),
    agingKey: r.agingKey ? String(r.agingKey) : undefined,
    openingUnadjusted: parseNum(r.openingUnadjusted),
    openingAdjustment: parseNum(r.openingAdjustment),
    provisionIncrease: parseNum(r.provisionIncrease ?? r.companyProvision),
    otherIncrease: parseNum(r.otherIncrease ?? r.transferIn),
    reversal: parseNum(r.reversal ?? r.recovery),
    writeOff: parseNum(r.writeOff),
    otherDecrease: parseNum(r.otherDecrease ?? r.transferOut),
    closingAdjustment: parseNum(r.closingAdjustment),
    reason: String(r.reason || r.remark || ''),
  }
}

function migrateLegacyEcl(arr: any[]): StoredLeafRow[] {
  return arr.map((r, i) => {
    const closing = parseNum(r.companyProvision ?? r.closingBalance ?? r.eclAmount)
    const opening = parseNum(r.previousECL)
    return {
      id: String(r.id || generateId('ind')),
      seq: Number(r.seq) || i + 1,
      category: 'individual' as const,
      item: String(r.investTarget || r.item || `单项明细${i + 1}`),
      openingUnadjusted: opening,
      openingAdjustment: 0,
      provisionIncrease: Math.max(0, closing - opening + parseNum(r.writeOff) + parseNum(r.recovery)),
      otherIncrease: parseNum(r.transferIn),
      reversal: parseNum(r.recovery),
      writeOff: parseNum(r.writeOff),
      otherDecrease: parseNum(r.transferOut),
      closingAdjustment: 0,
      reason: String(r.remark || ''),
    }
  })
}

function syncPortfolio(existing: StoredLeafRow[], segs: AgingSegment[]): StoredLeafRow[] {
  const byKey = new Map<string, StoredLeafRow>()
  for (const row of existing.filter((r) => r.category === 'portfolio')) {
    if (row.agingKey) byKey.set(row.agingKey, row)
  }
  return segs.map((seg, i) => {
    const prev = byKey.get(seg.key)
    if (prev) {
      return { ...prev, seq: i + 1, item: seg.label, agingKey: seg.key, category: 'portfolio' as const }
    }
    return emptyLeaf('portfolio', i + 1, seg.label, seg.key)
  })
}

function parseLeaves(raw: string | null | undefined, segs: AgingSegment[]): StoredLeafRow[] {
  const defaultPortfolio = segs.map((s, i) => emptyLeaf('portfolio', i + 1, s.label, s.key))
  if (!raw) {
    return [emptyLeaf('individual', 1, ''), ...defaultPortfolio]
  }
  try {
    const parsed = JSON.parse(raw)
    // version:2 object
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed) && parsed.version === 2) {
      const individual = (Array.isArray(parsed.individual) ? parsed.individual : []).map(
        (r: any, i: number) => normalizeLeaf(r, 'individual', i + 1),
      )
      const portfolio = syncPortfolio(
        (Array.isArray(parsed.portfolio) ? parsed.portfolio : []).map((r: any, i: number) =>
          normalizeLeaf(r, 'portfolio', i + 1),
        ),
        segs,
      )
      return [
        ...(individual.length ? individual : [emptyLeaf('individual', 1, '')]),
        ...portfolio,
      ]
    }
    if (Array.isArray(parsed)) {
      const looksLikeRollForward = parsed.some(
        (r) => r && (r.category === 'individual' || r.category === 'portfolio' || 'openingUnadjusted' in r),
      )
      if (!looksLikeRollForward && parsed.some((r) => r && ('eclStage' in r || 'pd12Month' in r))) {
        return [...migrateLegacyEcl(parsed), ...defaultPortfolio]
      }
      const individual = parsed
        .filter((r) => r && r.category !== 'portfolio')
        .map((r, i) => normalizeLeaf(r, 'individual', i + 1))
      const portfolioRaw = parsed
        .filter((r) => r && r.category === 'portfolio')
        .map((r, i) => normalizeLeaf(r, 'portfolio', i + 1))
      return [
        ...(individual.length ? individual : [emptyLeaf('individual', 1, '')]),
        ...syncPortfolio(portfolioRaw, segs),
      ]
    }
  } catch {
    /* ignore */
  }
  return [emptyLeaf('individual', 1, ''), ...defaultPortfolio]
}

export function buildBadDebtDisplayRows(leaves: StoredLeafRow[]): BadDebtDetailRow[] {
  const individual = leaves.filter((r) => r.category === 'individual')
  const portfolio = leaves.filter((r) => r.category === 'portfolio')
  const header = (id: string, item: string, category: G2BadDebtCategory): BadDebtDetailRow => ({
    id,
    seq: 0,
    category,
    kind: 'section_header',
    item,
    editable: false,
    openingUnadjusted: 0,
    openingAdjustment: 0,
    openingAudited: 0,
    provisionIncrease: 0,
    otherIncrease: 0,
    reversal: 0,
    writeOff: 0,
    otherDecrease: 0,
    closingUnadjusted: 0,
    closingAdjustment: 0,
    closingAudited: 0,
    reason: '',
  })
  const t = sumLeaves(leaves)
  return [
    header('__header_individual__', '按单项评估计提', 'individual'),
    ...individual.map(toDisplayLeaf),
    header('__header_portfolio__', '信用风险组合计提', 'portfolio'),
    ...portfolio.map(toDisplayLeaf),
    {
      id: '__footer_total__',
      seq: 0,
      category: 'individual',
      kind: 'footer',
      item: '合计',
      editable: false,
      ...t,
      reason: '',
    },
  ]
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

export interface UseG2BadDebtDetailOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export function useG2BadDebtDetail(options: UseG2BadDebtDetailOptions) {
  const { allResponses, projectId, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const { segments: projectSegments, preset: projectPreset } = useAgingConfig(projectId, 'G2')
  const sheetAgingPreset = ref<G2AgingPresetChoice>('')
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
    if (sheetAgingPreset.value === 'THREE_YEAR' || sheetAgingPreset.value === 'FIVE_YEAR') {
      return sheetAgingPreset.value
    }
    if (sheetAgingPreset.value === 'CUSTOM') return 'CUSTOM'
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

  const storedLeaves = computed(() =>
    parseLeaves(allResponses.value.get(STORAGE_KEY)?.remark, segments.value),
  )

  const dataRows: ComputedRef<BadDebtDetailRow[]> = computed(() =>
    buildBadDebtDisplayRows(storedLeaves.value),
  )

  const totals: ComputedRef<BadDebtTotals> = computed(() => sumLeaves(storedLeaves.value))

  function persistLeaves(leaves: StoredLeafRow[]): void {
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark: JSON.stringify(leaves),
    })
    debounceSave()
  }

  function addRow(_category: G2BadDebtCategory = 'individual'): void {
    if (readonly.value) return
    const leaves = parseLeaves(allResponses.value.get(STORAGE_KEY)?.remark, segments.value)
    const individual = leaves.filter((r) => r.category === 'individual')
    const portfolio = leaves.filter((r) => r.category === 'portfolio')
    const nextSeq = individual.length ? Math.max(...individual.map((r) => r.seq)) + 1 : 1
    individual.push(emptyLeaf('individual', nextSeq, ''))
    persistLeaves([...individual, ...portfolio])
  }

  function removeRow(id: string): void {
    if (readonly.value) return
    const leaves = parseLeaves(allResponses.value.get(STORAGE_KEY)?.remark, segments.value)
    let individual = leaves.filter((r) => r.category === 'individual' && r.id !== id)
    const portfolio = leaves.filter((r) => r.category === 'portfolio')
    if (individual.length === leaves.filter((r) => r.category === 'individual').length) return
    if (!individual.length) individual = [emptyLeaf('individual', 1, '')]
    else individual.forEach((r, i) => { r.seq = i + 1 })
    persistLeaves([...individual, ...portfolio])
  }

  function updateCell(rowId: string, field: string, value: string | number): void {
    if (readonly.value) return
    const leaves = parseLeaves(allResponses.value.get(STORAGE_KEY)?.remark, segments.value)
    const row = leaves.find((r) => r.id === rowId)
    if (!row) return

    const numeric = [
      'openingUnadjusted',
      'openingAdjustment',
      'provisionIncrease',
      'otherIncrease',
      'reversal',
      'writeOff',
      'otherDecrease',
      'closingAdjustment',
    ]
    if (field === 'item' || field === 'investTarget') {
      if (row.category === 'portfolio') return
      row.item = String(value ?? '')
    } else if (field === 'reason' || field === 'remark') {
      row.reason = String(value ?? '')
    } else if (numeric.includes(field)) {
      ;(row as any)[field] = typeof value === 'number' ? value : parseNum(value)
    } else {
      return
    }
    persistLeaves(leaves)
  }

  function setAgingPreset(
    preset: 'THREE_YEAR' | 'FIVE_YEAR' | 'CUSTOM',
    customLabels?: string[],
  ): boolean {
    if (readonly.value) return false
    let segs: AgingSegment[]
    if (preset === 'CUSTOM') {
      const labels = (customLabels || customSegments.value.map((s) => s.label))
        .map((x) => String(x || '').trim())
        .filter(Boolean)
      if (labels.length < 2) return false
      if (labels.length > 10) labels.length = 10
      segs = labelsToCustomSegments(labels)
      customSegments.value = segs
      sheetAgingPreset.value = 'CUSTOM'
      allResponses.value.set(AGING_CUSTOM_KEY, {
        item_id: AGING_CUSTOM_KEY,
        conclusion: null,
        remark: JSON.stringify(labels),
      })
    } else {
      segs = PRESET_SEGMENTS[preset]
      customSegments.value = []
      sheetAgingPreset.value = preset
      allResponses.value.set(AGING_CUSTOM_KEY, {
        item_id: AGING_CUSTOM_KEY,
        conclusion: null,
        remark: '[]',
      })
    }
    allResponses.value.set(AGING_PRESET_KEY, {
      item_id: AGING_PRESET_KEY,
      conclusion: null,
      remark: preset,
    })
    const leaves = parseLeaves(allResponses.value.get(STORAGE_KEY)?.remark, segments.value)
    const individual = leaves.filter((r) => r.category === 'individual')
    const portfolio = syncPortfolio(leaves, segs)
    persistLeaves([...individual, ...portfolio])
    return true
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
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
    if (sheetAgingPreset.value === 'THREE_YEAR' || sheetAgingPreset.value === 'FIVE_YEAR') return
    if (sheetAgingPreset.value === 'CUSTOM' && customSegments.value.length >= 2) return
    const leaves = parseLeaves(allResponses.value.get(STORAGE_KEY)?.remark, segments.value)
    const individual = leaves.filter((r) => r.category === 'individual')
    persistLeaves([...individual, ...syncPortfolio(leaves, segments.value)])
  }
  window.addEventListener('aging-config:changed', agingConfigHandler)
  eventListeners.push({ event: 'aging-config:changed', handler: agingConfigHandler })

  const onG2AgingSync = (e: Event) => {
    const d = (e as CustomEvent<{ preset?: AgingPreset; customLabels?: string[]; source?: string }>).detail
    if (!d?.preset || d.source === 'G2-3') return
    setAgingPreset(d.preset, d.customLabels)
  }
  window.addEventListener('g2:aging-preset-sync', onG2AgingSync)
  eventListeners.push({ event: 'g2:aging-preset-sync', handler: onG2AgingSync })

  function syncAgingAcrossSheets(): void {
    if (readonly.value) return
    const labels =
      agingPreset.value === 'CUSTOM'
        ? customSegments.value.map((s) => s.label)
        : []
    syncG2AgingPresetToAllSheets(allResponses.value, agingPreset.value, labels, 'G2-3')
    ElMessage.success('已同步账龄口径至 G2-2 / G2-6 / G2-7')
  }

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
    agingPreset,
    customSegments,
    addRow,
    removeRow,
    updateCell,
    setAgingPreset,
    syncAgingAcrossSheets,
  }
}

export default useG2BadDebtDetail
