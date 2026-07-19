/**
 * useG2OverdueCheck — G2-6 长期未收回款项检查表（对齐致同 Excel）
 *
 * 列：债务人 | 期初 | 借方 | 贷方 | 期末(公式) | 账龄(枚举) | 业务说明 |
 *     未收回原因 | 是否无法收回 | 处理计划 | 审定余额 | 期后收款 | 备注
 *
 * 公式：期末余额 = 期初余额 + 本期借方 − 本期贷方
 * 账龄：3年段 / 5年段 / 自定义（表级覆盖 + 项目配置）
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
import { loadG2DetailPartials, filterLongTermFromDetail } from './g2CrossHelpers'
import { syncG2AgingPresetToAllSheets, type G2AgingSyncDetail } from './g2AgingSync'
import type { ChecklistResponse } from './useF1FormData'

export type UncollectibleFlag = '' | '是' | '否' | '部分'

export interface OverdueCheckRow {
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
  isUncollectible: UncollectibleFlag
  actionPlan: string
  auditedBalance: number
  postPeriodCollection: number
  remark: string
  /** @deprecated 兼容旧字段 */
  investTarget?: string
  receivableAmount?: number
  overdueDays?: number
}

interface StoredOverdueRow {
  id: string
  seq: number
  debtorName: string
  openingBalance: number
  periodDebit: number
  periodCredit: number
  aging: string
  businessDesc: string
  unrecoveredReason: string
  isUncollectible: UncollectibleFlag
  actionPlan: string
  auditedBalance: number
  postPeriodCollection: number
  remark: string
}

export interface OverdueCheckSummary {
  openingBalance: number
  periodDebit: number
  periodCredit: number
  closingBalance: number
  auditedBalance: number
  postPeriodCollection: number
  longTermCount: number
  uncollectibleCount: number
  /** 兼容旧汇总字段 */
  overdueCount: number
  overdueTotalAmount: number
  highRiskCount: number
}

const STORAGE_KEY = 'G2-6-overdue-rows'
const AGING_PRESET_KEY = 'G2-6-aging-preset'
const AGING_CUSTOM_KEY = 'G2-6-aging-custom-segments'

export const UNCOLLECTIBLE_OPTIONS: { value: UncollectibleFlag; label: string }[] = [
  { value: '', label: '（未选）' },
  { value: '是', label: '是' },
  { value: '否', label: '否' },
  { value: '部分', label: '部分' },
]

/** @deprecated 保留兼容旧 UI 引用 */
export const RECOVERABILITY_OPTIONS = [
  { value: 'full', label: '全额可收回' },
  { value: 'partial', label: '部分可收回' },
  { value: 'unlikely', label: '很可能无法收回' },
  { value: 'irrecoverable', label: '无法收回' },
]
export const RISK_LEVEL_OPTIONS = [
  { value: 'low', label: '低' },
  { value: 'medium', label: '中' },
  { value: 'high', label: '高' },
  { value: 'extreme', label: '极高' },
]

function generateId(): string {
  return `overdue-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
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

function isLongTermAging(aging: string): boolean {
  const a = String(aging || '').trim()
  if (!a) return false
  if (/^1年以内|一年以内|within\s*1/i.test(a)) return false
  return true
}

/** 由账龄标签估算逾期天数（供 Stage 建议；无精确日期时用） */
export function estimateOverdueDaysFromAging(aging: string): number {
  const a = String(aging || '').trim()
  if (!a) return 0
  if (/5年以上|五年以上/i.test(a)) return 2000
  if (/4[-至到]5|3年以上|三年以上|over\s*3|over\s*5/i.test(a)) return 1200
  if (/2[-至到]3/i.test(a)) return 800
  if (/1[-至到]2|一年以上|1年以上/i.test(a)) return 400
  if (/^1年以内|一年以内|within\s*1|未逾期/i.test(a)) return 0
  if (isLongTermAging(a)) return 400
  return 0
}

/** 按账龄标签 / 逾期天数建议 ECL 阶段（供编制参考，不自动改数） */
export function suggestEclStageFromAging(
  aging: string,
  overdueDays = 0,
): 'Stage1' | 'Stage2' | 'Stage3' | 'none' {
  const a = String(aging || '').trim()
  // 优先账龄标签（避免「1-2年」估算天数误判为 Stage3）
  if (/3年以上|三年以上|4[-至到]5|5年以上|无法收回/i.test(a)) {
    return 'Stage3'
  }
  if (/1[-至到]2年|2[-至到]3年|一年以上|1年以上|逾期/i.test(a)) {
    return 'Stage2'
  }
  if (/^1年以内|一年以内|within\s*1|未逾期/i.test(a)) {
    return 'Stage1'
  }
  const days = overdueDays > 0 ? overdueDays : estimateOverdueDaysFromAging(a)
  if (days > 180) return 'Stage3'
  if (days > 90) return 'Stage2'
  if (days > 0 || (a && !isLongTermAging(a))) return 'Stage1'
  return 'none'
}

function computeRow(stored: StoredOverdueRow): OverdueCheckRow {
  const closingBalance =
    stored.openingBalance + stored.periodDebit - stored.periodCredit
  const overdueDays = estimateOverdueDaysFromAging(stored.aging)
  return {
    ...stored,
    closingBalance,
    investTarget: stored.debtorName,
    receivableAmount: closingBalance,
    overdueDays,
  }
}

function createEmptyRow(seq: number): StoredOverdueRow {
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
    isUncollectible: '',
    actionPlan: '',
    auditedBalance: 0,
    postPeriodCollection: 0,
    remark: '',
  }
}

function migrateLegacy(row: any, seq: number): StoredOverdueRow {
  // 旧版：investTarget / receivableAmount / overdueReason / recoverability
  if (row && ('debtorName' in row || 'openingBalance' in row || 'periodDebit' in row)) {
    return {
      id: String(row.id || generateId()),
      seq: Number(row.seq) || seq,
      debtorName: String(row.debtorName || row.investTarget || ''),
      openingBalance: parseNum(row.openingBalance),
      periodDebit: parseNum(row.periodDebit),
      periodCredit: parseNum(row.periodCredit),
      aging: String(row.aging || ''),
      businessDesc: String(row.businessDesc || ''),
      unrecoveredReason: String(row.unrecoveredReason || row.overdueReason || ''),
      isUncollectible: (['是', '否', '部分'].includes(row.isUncollectible)
        ? row.isUncollectible
        : row.recoverability === 'irrecoverable'
          ? '是'
          : row.recoverability === 'unlikely'
            ? '部分'
            : '') as UncollectibleFlag,
      actionPlan: String(row.actionPlan || row.collectionMeasures || row.auditSuggestion || ''),
      auditedBalance: parseNum(row.auditedBalance ?? row.receivableAmount),
      postPeriodCollection: parseNum(row.postPeriodCollection),
      remark: String(row.remark || ''),
    }
  }
  const amount = parseNum(row?.receivableAmount)
  return {
    id: String(row?.id || generateId()),
    seq: Number(row?.seq) || seq,
    debtorName: String(row?.investTarget || ''),
    openingBalance: amount,
    periodDebit: 0,
    periodCredit: 0,
    aging: '',
    businessDesc: '',
    unrecoveredReason: String(row?.overdueReason || ''),
    isUncollectible:
      row?.recoverability === 'irrecoverable'
        ? '是'
        : row?.recoverability === 'unlikely'
          ? '部分'
          : '',
    actionPlan: String(row?.auditSuggestion || row?.collectionMeasures || ''),
    auditedBalance: amount,
    postPeriodCollection: 0,
    remark: String(row?.remark || ''),
  }
}

function safeParseRows(jsonStr: string | null | undefined): StoredOverdueRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r, i) => migrateLegacy(r, i + 1))
  } catch {
    return []
  }
}

export interface UseG2OverdueCheckOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export function useG2OverdueCheck(options: UseG2OverdueCheckOptions) {
  const { allResponses, projectId, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const { segments: projectSegments, preset: projectPreset } = useAgingConfig(projectId, 'G2')
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

  const dataRows: ComputedRef<OverdueCheckRow[]> = computed(() => {
    const stored = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    return stored.map(computeRow)
  })

  const displayRows: ComputedRef<OverdueCheckRow[]> = computed(() => {
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
        isUncollectible: '',
        actionPlan: '',
        auditedBalance: t.auditedBalance,
        postPeriodCollection: t.postPeriodCollection,
        remark: '',
      },
    ]
  })

  const summary: ComputedRef<OverdueCheckSummary> = computed(() => {
    const rows = dataRows.value
    const openingBalance = calcSubtotal(rows.map((r) => r.openingBalance))
    const periodDebit = calcSubtotal(rows.map((r) => r.periodDebit))
    const periodCredit = calcSubtotal(rows.map((r) => r.periodCredit))
    const closingBalance = calcSubtotal(rows.map((r) => r.closingBalance))
    const auditedBalance = calcSubtotal(rows.map((r) => r.auditedBalance))
    const postPeriodCollection = calcSubtotal(rows.map((r) => r.postPeriodCollection))
    const longTermCount = rows.filter((r) => isLongTermAging(r.aging)).length
    const uncollectibleCount = rows.filter(
      (r) => r.isUncollectible === '是' || r.isUncollectible === '部分',
    ).length
    return {
      openingBalance,
      periodDebit,
      periodCredit,
      closingBalance,
      auditedBalance,
      postPeriodCollection,
      longTermCount,
      uncollectibleCount,
      overdueCount: longTermCount,
      overdueTotalAmount: calcSubtotal(
        rows.filter((r) => isLongTermAging(r.aging)).map((r) => r.closingBalance),
      ),
      highRiskCount: uncollectibleCount,
    }
  })

  function isMetaRow(row: OverdueCheckRow): boolean {
    return row.id === '__subtotal__'
  }

  function isLongTerm(row: OverdueCheckRow): boolean {
    return isLongTermAging(row.aging)
  }

  function addRow(): void {
    if (readonly.value) return
    const current = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    const nextSeq = current.length ? Math.max(...current.map((r) => r.seq)) + 1 : 1
    current.push(createEmptyRow(nextSeq))
    persistRows(current)
  }

  function removeRow(id: string): void {
    if (readonly.value) return
    const current = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    const filtered = current.filter((r) => r.id !== id)
    filtered.forEach((r, i) => { r.seq = i + 1 })
    persistRows(filtered)
  }

  function updateCell(rowId: string, field: string, value: string | number): void {
    if (readonly.value || rowId === '__subtotal__') return
    const current = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    const idx = current.findIndex((r) => r.id === rowId)
    if (idx === -1) return

    const alias: Record<string, string> = {
      investTarget: 'debtorName',
      receivableAmount: 'auditedBalance',
      overdueReason: 'unrecoveredReason',
    }
    const key = alias[field] || field
    const numeric = [
      'openingBalance',
      'periodDebit',
      'periodCredit',
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
      if (labels.length > 10) labels.length = 10
      sheetAgingPreset.value = 'CUSTOM'
      customSegments.value = labelsToCustomSegments(labels)
      allResponses.value.set(AGING_PRESET_KEY, {
        item_id: AGING_PRESET_KEY,
        conclusion: null,
        remark: 'CUSTOM',
      })
      allResponses.value.set(AGING_CUSTOM_KEY, {
        item_id: AGING_CUSTOM_KEY,
        conclusion: null,
        remark: JSON.stringify(labels),
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
    debounceSave()
    return true
  }

  /** 审定余额默认取期末余额 */
  function syncAuditedFromClosing(rowId: string): void {
    if (readonly.value) return
    const current = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    const idx = current.findIndex((r) => r.id === rowId)
    if (idx === -1) return
    const closing =
      current[idx].openingBalance + current[idx].periodDebit - current[idx].periodCredit
    current[idx].auditedBalance = closing
    persistRows(current)
  }

  /**
   * 从 G2-2 明细导入账龄超 1 年挂账：按债务人名称合并（更新金额/账龄，保留已有原因等手工字段）。
   */
  function importFromDetail(): { imported: number; updated: number } {
    if (readonly.value) return { imported: 0, updated: 0 }
    const details = loadG2DetailPartials(allResponses.value)
    const longTerm = filterLongTermFromDetail(details)
    if (!longTerm.length) return { imported: 0, updated: 0 }

    const options = agingOptions.value
    const resolveAging = (label: string): string => {
      if (!label) return options.find((o) => !/^1年以内|一年以内/.test(o)) || options[1] || label
      const hit = options.find((o) => o === label || o.includes(label) || label.includes(o))
      return hit || label
    }

    const current = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
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
        existing.auditedBalance = src.auditedBalance
        existing.aging = aging
        if (!existing.unrecoveredReason && src.unrecoveredReason) {
          existing.unrecoveredReason = src.unrecoveredReason
        }
        // 期末 = 期初 + 借 − 贷；导入时用审定作期末口径：贷方清零、借方 = 审定 − 期初
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
        row.unrecoveredReason = src.unrecoveredReason
        row.auditedBalance = src.auditedBalance
        row.remark = '来自G2-2超1年'
        current.push(row)
        byName.set(name, row)
        imported += 1
      }
    }

    persistRows(current)
    return { imported, updated }
  }

  function persistRows(rows: StoredOverdueRow[]): void {
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
    /* 跟随项目刷新即可，segments computed 会更新 */
  }
  window.addEventListener('aging-config:changed', agingConfigHandler)
  eventListeners.push({ event: 'aging-config:changed', handler: agingConfigHandler })

  const onG2AgingSync = (e: Event) => {
    const d = (e as CustomEvent<G2AgingSyncDetail>).detail
    if (!d?.preset || d.source === 'G2-6') return
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
    syncG2AgingPresetToAllSheets(allResponses.value, agingPreset.value, labels, 'G2-6')
    ElMessage.success('已同步账龄口径至 G2-2 / G2-3 / G2-7')
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
    displayRows,
    summary,
    segments,
    agingOptions,
    agingPreset,
    customSegments,
    isMetaRow,
    isLongTerm,
    addRow,
    removeRow,
    updateCell,
    setAgingPreset,
    syncAuditedFromClosing,
    importFromDetail,
    syncAgingAcrossSheets,
    getStageSuggestion: (row: OverdueCheckRow) =>
      suggestEclStageFromAging(row.aging, row.overdueDays || 0),
    getOverdueHighlight: (row: OverdueCheckRow) =>
      isLongTerm(row) ? ('orange' as const) : ('none' as const),
  }
}

export default useG2OverdueCheck
