/**
 * useG2ECLCalc — G2-7 坏账准备测算（对齐致同 Excel）
 *
 * 结构：
 *   (一) 单项计提坏账准备
 *   (二) 账龄组合计提（多组合 × 动态账龄段：3年段/5年段/自定义）
 *   (三) 其他组合计提
 *
 * 公式：
 *   应计提③ = 审定余额① × 损失率②
 *   差异⑤ = 应计提③ − 账面坏账准备④
 *
 * 差异可推送至 G2-4 调整分录汇总。
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import {
  parseNum,
  calcSubtotal,
  calcExpectedProvision,
  calcEclDifference,
} from './useG2IntRecFormulaEngine'
import {
  useAgingConfig,
  PRESET_SEGMENTS,
  type AgingSegment,
  type AgingPreset,
} from '@/composables/useAgingConfig'
import type { ChecklistResponse } from './useF1FormData'
import { createEmptyG2AdjustmentRow, type G2AdjustmentRow } from './useG2Adjustment'
import { syncG2AgingPresetToAllSheets, type G2AgingSyncDetail } from './g2AgingSync'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface G2EclSingleRow {
  rowId: string
  investTarget: string
  auditedBalance: number
  lossRate: number
  expectedProvision: number
  bookBalance: number
  difference: number
  basis: string
  indexRef: string
}

export interface G2EclAgingRow {
  rowId: string
  segmentKey: string
  agingBand: string
  auditedBalance: number
  lossRate: number
  expectedProvision: number
  bookBalance: number
  difference: number
  basis: string
  indexRef: string
  archived?: boolean
}

export interface G2EclAgingGroup {
  groupId: string
  groupName: string
  rows: G2EclAgingRow[]
}

export interface G2EclOtherRow {
  rowId: string
  groupName: string
  auditedBalance: number
  lossRate: number
  expectedProvision: number
  bookBalance: number
  difference: number
  basis: string
  indexRef: string
}

const ITEM_SINGLE = 'G2-7-single-rows'
const ITEM_GROUPS = 'G2-7-aging-groups'
const ITEM_OTHER = 'G2-7-other-rows'
const ITEM_PRESET = 'G2-7-aging-preset'
const ITEM_CUSTOM = 'G2-7-aging-custom-segments'
const ITEM_LEGACY = 'G2-7-ecl-calc-rows'
const ITEM_FLAT = 'G2-7-flat-export'
const ADJ_STORAGE = 'G2-4-rows'
const BAD_DEBT_STORAGE = 'G2-3-bad-debt-rows'

function generateId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
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

function recalcSingle(row: G2EclSingleRow): G2EclSingleRow {
  const expectedProvision = calcExpectedProvision(row.auditedBalance, row.lossRate)
  return { ...row, expectedProvision, difference: calcEclDifference(expectedProvision, row.bookBalance) }
}

function recalcAging(row: G2EclAgingRow): G2EclAgingRow {
  const expectedProvision = calcExpectedProvision(row.auditedBalance, row.lossRate)
  return { ...row, expectedProvision, difference: calcEclDifference(expectedProvision, row.bookBalance) }
}

function recalcOther(row: G2EclOtherRow): G2EclOtherRow {
  const expectedProvision = calcExpectedProvision(row.auditedBalance, row.lossRate)
  return { ...row, expectedProvision, difference: calcEclDifference(expectedProvision, row.bookBalance) }
}

function createAgingRowsFromSegments(segments: AgingSegment[]): G2EclAgingRow[] {
  return segments.map((seg) => ({
    rowId: generateId('ar'),
    segmentKey: seg.key,
    agingBand: seg.label,
    auditedBalance: 0,
    lossRate: 0,
    expectedProvision: 0,
    bookBalance: 0,
    difference: 0,
    basis: '',
    indexRef: '',
  }))
}

export function syncAgingGroupRows(
  existingRows: G2EclAgingRow[],
  newSegments: AgingSegment[],
): G2EclAgingRow[] {
  const newKeys = new Set(newSegments.map((s) => s.key))
  const byKey = new Map<string, G2EclAgingRow>()
  const byLabel = new Map<string, G2EclAgingRow>()
  for (const row of existingRows) {
    if (row.segmentKey) byKey.set(row.segmentKey, row)
    if (row.agingBand) byLabel.set(row.agingBand, row)
  }

  const result: G2EclAgingRow[] = newSegments.map((seg) => {
    const existing = byKey.get(seg.key) || byLabel.get(seg.label)
    if (existing) {
      return recalcAging({
        ...existing,
        segmentKey: seg.key,
        agingBand: seg.label,
        archived: undefined,
      })
    }
    return {
      rowId: generateId('ar'),
      segmentKey: seg.key,
      agingBand: seg.label,
      auditedBalance: 0,
      lossRate: 0,
      expectedProvision: 0,
      bookBalance: 0,
      difference: 0,
      basis: '',
      indexRef: '',
    }
  })

  for (const row of existingRows) {
    const key = row.segmentKey || ''
    if (key && !newKeys.has(key) && !row.archived) {
      const hasData = row.lossRate !== 0 || row.bookBalance !== 0 || row.auditedBalance !== 0
      if (hasData) result.push({ ...row, archived: true })
    }
  }
  return result
}

function createEmptySingle(): G2EclSingleRow {
  return {
    rowId: generateId('si'),
    investTarget: '',
    auditedBalance: 0,
    lossRate: 0,
    expectedProvision: 0,
    bookBalance: 0,
    difference: 0,
    basis: '',
    indexRef: 'G2-7',
  }
}

function createEmptyOther(): G2EclOtherRow {
  return {
    rowId: generateId('ot'),
    groupName: '',
    auditedBalance: 0,
    lossRate: 0,
    expectedProvision: 0,
    bookBalance: 0,
    difference: 0,
    basis: '',
    indexRef: 'G2-7',
  }
}

function createEmptyGroup(segs: AgingSegment[], name = ''): G2EclAgingGroup {
  return {
    groupId: generateId('grp'),
    groupName: name,
    rows: createAgingRowsFromSegments(segs),
  }
}

function safeParseArray<T>(json: string | null | undefined, mapFn: (r: any) => T): T[] {
  if (!json) return []
  try {
    const parsed = JSON.parse(json)
    return Array.isArray(parsed) ? parsed.map(mapFn) : []
  } catch {
    return []
  }
}

function normalizeSingle(raw: any): G2EclSingleRow {
  return recalcSingle({
    rowId: raw.rowId || raw.id || generateId('si'),
    investTarget: String(raw.investTarget || raw.debtorName || ''),
    auditedBalance: parseNum(raw.auditedBalance ?? raw.closingBalance),
    lossRate: parseNum(raw.lossRate),
    expectedProvision: parseNum(raw.expectedProvision ?? raw.eclAmount),
    bookBalance: parseNum(raw.bookBalance ?? raw.companyProvision),
    difference: parseNum(raw.difference ?? raw.eclVariance),
    basis: String(raw.basis || raw.conclusion || ''),
    indexRef: String(raw.indexRef || 'G2-7'),
  })
}

function normalizeAgingRow(raw: any): G2EclAgingRow {
  return recalcAging({
    rowId: raw.rowId || generateId('ar'),
    segmentKey: String(raw.segmentKey || ''),
    agingBand: String(raw.agingBand || raw.label || ''),
    auditedBalance: parseNum(raw.auditedBalance),
    lossRate: parseNum(raw.lossRate),
    expectedProvision: parseNum(raw.expectedProvision),
    bookBalance: parseNum(raw.bookBalance),
    difference: parseNum(raw.difference),
    basis: String(raw.basis || ''),
    indexRef: String(raw.indexRef || ''),
    ...(raw.archived ? { archived: true } : {}),
  })
}

function normalizeGroup(raw: any): G2EclAgingGroup {
  return {
    groupId: raw.groupId || generateId('grp'),
    groupName: String(raw.groupName || ''),
    rows: Array.isArray(raw.rows) ? raw.rows.map(normalizeAgingRow) : [],
  }
}

function normalizeOther(raw: any): G2EclOtherRow {
  return recalcOther({
    rowId: raw.rowId || generateId('ot'),
    groupName: String(raw.groupName || raw.investTarget || ''),
    auditedBalance: parseNum(raw.auditedBalance),
    lossRate: parseNum(raw.lossRate),
    expectedProvision: parseNum(raw.expectedProvision),
    bookBalance: parseNum(raw.bookBalance),
    difference: parseNum(raw.difference),
    basis: String(raw.basis || ''),
    indexRef: String(raw.indexRef || 'G2-7'),
  })
}

export interface UseG2ECLCalcOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly?: Ref<boolean>
}

export function useG2ECLCalc(options: UseG2ECLCalcOptions) {
  const { allResponses, projectId, debouncedSave, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  const { segments: projectSegments, preset: projectPreset } = useAgingConfig(projectId, 'G2')
  const sheetAgingPreset = ref<'' | AgingPreset>('')
  const customSegments = ref<AgingSegment[]>([])
  const singleRows = ref<G2EclSingleRow[]>([])
  const agingGroups = ref<G2EclAgingGroup[]>([])
  const otherRows = ref<G2EclOtherRow[]>([])
  let migratedLegacy = false

  watch(
    () => allResponses.value.get(ITEM_PRESET)?.remark,
    (v) => {
      const raw = String(v || '').trim().toUpperCase()
      sheetAgingPreset.value =
        raw === 'THREE_YEAR' || raw === 'FIVE_YEAR' || raw === 'CUSTOM' ? raw : ''
    },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get(ITEM_CUSTOM)?.remark,
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
    return 'FIVE_YEAR' // Excel 模板默认 5 年段
  })

  const segments: ComputedRef<AgingSegment[]> = computed(() => {
    if (sheetAgingPreset.value === 'CUSTOM') {
      if (customSegments.value.length >= 2) return customSegments.value
      if (projectPreset.value === 'CUSTOM' && projectSegments.value.length >= 2) {
        return projectSegments.value
      }
      return PRESET_SEGMENTS.FIVE_YEAR
    }
    if (sheetAgingPreset.value === 'THREE_YEAR' || sheetAgingPreset.value === 'FIVE_YEAR') {
      return PRESET_SEGMENTS[sheetAgingPreset.value]
    }
    if (projectSegments.value.length) return projectSegments.value
    return PRESET_SEGMENTS.FIVE_YEAR
  })

  // Load data
  watch(
    () => allResponses.value.get(ITEM_SINGLE)?.remark,
    (json) => {
      if (json) {
        singleRows.value = safeParseArray(json, normalizeSingle)
        return
      }
      // 兼容旧版逐笔 PD/LGD 行 → 迁入单项
      if (!migratedLegacy) {
        const legacy = safeParseArray(allResponses.value.get(ITEM_LEGACY)?.remark, (r) => r)
        if (legacy.length) {
          migratedLegacy = true
          singleRows.value = legacy.map((r: any) => normalizeSingle(r))
          persistSingle()
        }
      }
    },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get(ITEM_GROUPS)?.remark,
    (json) => {
      const groups = safeParseArray(json, normalizeGroup)
      if (groups.length) {
        agingGroups.value = groups.map((g) => ({
          ...g,
          rows: (g.rows.length ? g.rows : createAgingRowsFromSegments(segments.value)).map(recalcAging),
        }))
      } else if (agingGroups.value.length === 0) {
        // 默认两个组合（对齐 Excel 组合1/组合2）
        agingGroups.value = [
          createEmptyGroup(segments.value, '组合1'),
          createEmptyGroup(segments.value, '组合2'),
        ]
        persistGroups()
      }
    },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get(ITEM_OTHER)?.remark,
    (json) => {
      otherRows.value = safeParseArray(json, normalizeOther)
    },
    { immediate: true },
  )

  function persistSingle() {
    if (readonly.value) return
    debouncedSave(ITEM_SINGLE, { item_id: ITEM_SINGLE, conclusion: null, remark: JSON.stringify(singleRows.value) })
    persistFlat()
  }
  function persistGroups() {
    if (readonly.value) return
    debouncedSave(ITEM_GROUPS, { item_id: ITEM_GROUPS, conclusion: null, remark: JSON.stringify(agingGroups.value) })
    persistFlat()
  }
  function persistOther() {
    if (readonly.value) return
    debouncedSave(ITEM_OTHER, { item_id: ITEM_OTHER, conclusion: null, remark: JSON.stringify(otherRows.value) })
    persistFlat()
  }

  /** 扁平化供导入导出 round-trip */
  function persistFlat() {
    if (readonly.value) return
    const flat: any[] = []
    for (const r of singleRows.value) {
      flat.push({
        section: 'individual',
        groupName: '',
        segmentKey: '',
        label: r.investTarget,
        auditedBalance: r.auditedBalance,
        lossRate: r.lossRate,
        expectedProvision: r.expectedProvision,
        bookBalance: r.bookBalance,
        difference: r.difference,
        basis: r.basis,
        indexRef: r.indexRef,
      })
    }
    for (const g of agingGroups.value) {
      for (const r of g.rows) {
        if (r.archived) continue
        flat.push({
          section: 'aging',
          groupName: g.groupName,
          segmentKey: r.segmentKey,
          label: r.agingBand,
          auditedBalance: r.auditedBalance,
          lossRate: r.lossRate,
          expectedProvision: r.expectedProvision,
          bookBalance: r.bookBalance,
          difference: r.difference,
          basis: r.basis,
          indexRef: r.indexRef,
        })
      }
    }
    for (const r of otherRows.value) {
      flat.push({
        section: 'other',
        groupName: r.groupName,
        segmentKey: '',
        label: r.groupName,
        auditedBalance: r.auditedBalance,
        lossRate: r.lossRate,
        expectedProvision: r.expectedProvision,
        bookBalance: r.bookBalance,
        difference: r.difference,
        basis: r.basis,
        indexRef: r.indexRef,
      })
    }
    debouncedSave(ITEM_FLAT, { item_id: ITEM_FLAT, conclusion: null, remark: JSON.stringify(flat) })
  }

  /** 从扁平导入还原三区段（导入导出后调用） */
  function hydrateFromFlat(flatRaw: string | null | undefined): boolean {
    if (!flatRaw) return false
    try {
      const flat = JSON.parse(flatRaw)
      if (!Array.isArray(flat) || !flat.length) return false
      const singles: G2EclSingleRow[] = []
      const other: G2EclOtherRow[] = []
      const groupMap = new Map<string, G2EclAgingGroup>()

      for (const row of flat) {
        const section = String(row.section || '')
        if (section === 'individual') {
          singles.push(normalizeSingle({
            investTarget: row.label,
            auditedBalance: row.auditedBalance,
            lossRate: row.lossRate,
            bookBalance: row.bookBalance,
            basis: row.basis,
            indexRef: row.indexRef,
          }))
        } else if (section === 'other') {
          other.push(normalizeOther({
            groupName: row.groupName || row.label,
            auditedBalance: row.auditedBalance,
            lossRate: row.lossRate,
            bookBalance: row.bookBalance,
            basis: row.basis,
            indexRef: row.indexRef,
          }))
        } else if (section === 'aging') {
          const gName = String(row.groupName || '组合1')
          if (!groupMap.has(gName)) {
            groupMap.set(gName, { groupId: generateId('grp'), groupName: gName, rows: [] })
          }
          groupMap.get(gName)!.rows.push(normalizeAgingRow({
            segmentKey: row.segmentKey,
            agingBand: row.label,
            auditedBalance: row.auditedBalance,
            lossRate: row.lossRate,
            bookBalance: row.bookBalance,
            basis: row.basis,
            indexRef: row.indexRef,
          }))
        }
      }

      if (singles.length) singleRows.value = singles
      if (other.length) otherRows.value = other
      if (groupMap.size) {
        agingGroups.value = [...groupMap.values()].map((g) => ({
          ...g,
          rows: g.rows.length ? g.rows : createAgingRowsFromSegments(segments.value),
        }))
      }
      persistSingle()
      persistGroups()
      persistOther()
      return true
    } catch {
      return false
    }
  }

  const singleTotal = computed(() => ({
    balance: calcSubtotal(singleRows.value.map((r) => r.auditedBalance)),
    provision: calcSubtotal(singleRows.value.map((r) => r.expectedProvision)),
    book: calcSubtotal(singleRows.value.map((r) => r.bookBalance)),
    diff: calcSubtotal(singleRows.value.map((r) => r.difference)),
  }))

  const agingGroupTotals = computed(() =>
    agingGroups.value.map((g) => {
      const active = g.rows.filter((r) => !r.archived)
      return {
        groupId: g.groupId,
        groupName: g.groupName,
        balance: calcSubtotal(active.map((r) => r.auditedBalance)),
        provision: calcSubtotal(active.map((r) => r.expectedProvision)),
        book: calcSubtotal(active.map((r) => r.bookBalance)),
        diff: calcSubtotal(active.map((r) => r.difference)),
      }
    }),
  )

  const otherTotal = computed(() => ({
    balance: calcSubtotal(otherRows.value.map((r) => r.auditedBalance)),
    provision: calcSubtotal(otherRows.value.map((r) => r.expectedProvision)),
    book: calcSubtotal(otherRows.value.map((r) => r.bookBalance)),
    diff: calcSubtotal(otherRows.value.map((r) => r.difference)),
  }))

  const grandTotal = computed(() => {
    const gProv = calcSubtotal(agingGroupTotals.value.map((g) => g.provision))
    const gBook = calcSubtotal(agingGroupTotals.value.map((g) => g.book))
    const gDiff = calcSubtotal(agingGroupTotals.value.map((g) => g.diff))
    return {
      expectedProvision: singleTotal.value.provision + gProv + otherTotal.value.provision,
      bookBalance: singleTotal.value.book + gBook + otherTotal.value.book,
      totalDiff: singleTotal.value.diff + gDiff + otherTotal.value.diff,
    }
  })

  const diffAlert = computed(() => {
    if (Math.abs(grandTotal.value.totalDiff) < 0.01) return null
    const sign = grandTotal.value.totalDiff > 0 ? '少提' : '多提'
    return `应计提与账面准备存在差异（${sign}${Math.abs(grandTotal.value.totalDiff).toFixed(2)}元），可推送至 G2-4 调整分录。`
  })

  // ─── Aging preset ───────────────────────────────────────────────────────

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
      if (labels.length > 10) {
        ElMessage.warning('自定义账龄最多 10 段')
        return false
      }
      segs = labelsToCustomSegments(labels)
      customSegments.value = segs
      debouncedSave(ITEM_CUSTOM, { item_id: ITEM_CUSTOM, conclusion: null, remark: JSON.stringify(labels) })
    } else {
      segs = PRESET_SEGMENTS[preset] || PRESET_SEGMENTS.FIVE_YEAR
      customSegments.value = []
      debouncedSave(ITEM_CUSTOM, { item_id: ITEM_CUSTOM, conclusion: null, remark: '[]' })
    }
    sheetAgingPreset.value = preset
    debouncedSave(ITEM_PRESET, { item_id: ITEM_PRESET, conclusion: null, remark: preset })
    agingGroups.value = agingGroups.value.map((g) => ({
      ...g,
      rows: syncAgingGroupRows(g.rows, segs),
    }))
    persistGroups()
    return true
  }

  // ─── Single actions ─────────────────────────────────────────────────────

  function addSingleRow() {
    if (readonly.value) return
    singleRows.value = [...singleRows.value, createEmptySingle()]
    persistSingle()
  }
  function removeSingleRow(rowId: string) {
    if (readonly.value) return
    singleRows.value = singleRows.value.filter((r) => r.rowId !== rowId)
    persistSingle()
  }
  function updateSingleCell(rowId: string, field: keyof G2EclSingleRow, value: unknown) {
    if (readonly.value) return
    const nums = ['auditedBalance', 'lossRate', 'bookBalance']
    singleRows.value = singleRows.value.map((r) => {
      if (r.rowId !== rowId) return r
      const next = { ...r }
      ;(next as any)[field] = nums.includes(field) ? parseNum(value) : String(value ?? '')
      return recalcSingle(next)
    })
    persistSingle()
  }

  // ─── Aging group actions ────────────────────────────────────────────────

  function addAgingGroup() {
    if (readonly.value) return
    const n = agingGroups.value.length + 1
    agingGroups.value = [...agingGroups.value, createEmptyGroup(segments.value, `组合${n}`)]
    persistGroups()
  }
  function removeAgingGroup(groupId: string) {
    if (readonly.value) return
    agingGroups.value = agingGroups.value.filter((g) => g.groupId !== groupId)
    persistGroups()
  }
  function updateGroupName(groupId: string, name: string) {
    if (readonly.value) return
    agingGroups.value = agingGroups.value.map((g) =>
      g.groupId === groupId ? { ...g, groupName: name } : g,
    )
    persistGroups()
  }
  function updateAgingCell(
    groupId: string,
    rowId: string,
    field: keyof G2EclAgingRow,
    value: unknown,
  ) {
    if (readonly.value) return
    const nums = ['auditedBalance', 'lossRate', 'bookBalance']
    agingGroups.value = agingGroups.value.map((g) => {
      if (g.groupId !== groupId) return g
      return {
        ...g,
        rows: g.rows.map((r) => {
          if (r.rowId !== rowId) return r
          const next = { ...r }
          ;(next as any)[field] = nums.includes(field) ? parseNum(value) : String(value ?? '')
          return recalcAging(next)
        }),
      }
    })
    persistGroups()
  }

  // ─── Other actions ──────────────────────────────────────────────────────

  function addOtherRow() {
    if (readonly.value) return
    otherRows.value = [...otherRows.value, createEmptyOther()]
    persistOther()
  }
  function removeOtherRow(rowId: string) {
    if (readonly.value) return
    otherRows.value = otherRows.value.filter((r) => r.rowId !== rowId)
    persistOther()
  }
  function updateOtherCell(rowId: string, field: keyof G2EclOtherRow, value: unknown) {
    if (readonly.value) return
    const nums = ['auditedBalance', 'lossRate', 'bookBalance']
    otherRows.value = otherRows.value.map((r) => {
      if (r.rowId !== rowId) return r
      const next = { ...r }
      ;(next as any)[field] = nums.includes(field) ? parseNum(value) : String(value ?? '')
      return recalcOther(next)
    })
    persistOther()
  }

  // ─── Push diffs to G2-4 ─────────────────────────────────────────────────

  function collectDiffItems(): Array<{ desc: string; amount: number }> {
    const items: Array<{ desc: string; amount: number }> = []
    for (const r of singleRows.value) {
      if (Math.abs(r.difference) < 0.01) continue
      items.push({
        desc: `单项计提差异：${r.investTarget || '未命名'}（G2-7）`,
        amount: r.difference,
      })
    }
    for (const g of agingGroups.value) {
      for (const r of g.rows) {
        if (r.archived || Math.abs(r.difference) < 0.01) continue
        items.push({
          desc: `账龄组合差异：${g.groupName || '组合'}·${r.agingBand}（G2-7）`,
          amount: r.difference,
        })
      }
    }
    for (const r of otherRows.value) {
      if (Math.abs(r.difference) < 0.01) continue
      items.push({
        desc: `其他组合差异：${r.groupName || '其他'}（G2-7）`,
        amount: r.difference,
      })
    }
    return items
  }

  /**
   * 将测算结果回填 G2-3 本期计提：
   * - mode=difference（默认）：回填差异（应计提−账面），避免覆盖滚动态期初
   * - mode=expected：回填应计提全额
   * - 单项 / 其他组合 → 单项明细（按名称合并）
   * - 账龄组合 → 组合账龄段（按 segmentKey 合计）
   */
  function pushProvisionToG23(
    mode: 'difference' | 'expected' = 'difference',
  ): { individual: number; portfolio: number } {
    if (readonly.value) return { individual: 0, portfolio: 0 }

    const pickAmt = (expected: number, difference: number) =>
      mode === 'expected' ? expected : difference

    const indProv = new Map<string, number>()
    for (const r of singleRows.value) {
      const name = String(r.investTarget || '').trim()
      const amt = pickAmt(r.expectedProvision, r.difference)
      if (!name || Math.abs(amt) < 0.005) continue
      indProv.set(name, (indProv.get(name) || 0) + amt)
    }
    for (const r of otherRows.value) {
      const name = String(r.groupName || '').trim()
      const amt = pickAmt(r.expectedProvision, r.difference)
      if (!name || Math.abs(amt) < 0.005) continue
      indProv.set(name, (indProv.get(name) || 0) + amt)
    }

    const portProv = new Map<string, number>()
    for (const g of agingGroups.value) {
      for (const r of g.rows) {
        if (r.archived) continue
        const key = String(r.segmentKey || '').trim()
        const amt = pickAmt(r.expectedProvision, r.difference)
        if (!key || Math.abs(amt) < 0.005) continue
        portProv.set(key, (portProv.get(key) || 0) + amt)
      }
    }

    if (!indProv.size && !portProv.size) {
      ElMessage.info(mode === 'difference' ? '无可回填的差异金额' : '无可回填的应计提金额')
      return { individual: 0, portfolio: 0 }
    }

    type Leaf = {
      id: string
      seq: number
      category: 'individual' | 'portfolio'
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

    const emptyLeaf = (
      category: 'individual' | 'portfolio',
      seq: number,
      item: string,
      agingKey?: string,
    ): Leaf => ({
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
    })

    const normalize = (r: any, category: 'individual' | 'portfolio', seq: number): Leaf => ({
      id: String(r.id || generateId(category === 'portfolio' ? 'port' : 'ind')),
      seq: Number(r.seq) || seq,
      category,
      item: String(r.item || r.investTarget || ''),
      agingKey: r.agingKey ? String(r.agingKey) : undefined,
      openingUnadjusted: parseNum(r.openingUnadjusted),
      openingAdjustment: parseNum(r.openingAdjustment),
      provisionIncrease: parseNum(r.provisionIncrease),
      otherIncrease: parseNum(r.otherIncrease),
      reversal: parseNum(r.reversal),
      writeOff: parseNum(r.writeOff),
      otherDecrease: parseNum(r.otherDecrease),
      closingAdjustment: parseNum(r.closingAdjustment),
      reason: String(r.reason || r.remark || ''),
    })

    let individual: Leaf[] = []
    let portfolio: Leaf[] = []
    const raw = allResponses.value.get(BAD_DEBT_STORAGE)?.remark
    try {
      const parsed = raw ? JSON.parse(raw) : null
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed) && parsed.version === 2) {
        individual = (Array.isArray(parsed.individual) ? parsed.individual : []).map(
          (r: any, i: number) => normalize(r, 'individual', i + 1),
        )
        portfolio = (Array.isArray(parsed.portfolio) ? parsed.portfolio : []).map(
          (r: any, i: number) => normalize(r, 'portfolio', i + 1),
        )
      } else if (Array.isArray(parsed)) {
        individual = parsed
          .filter((r: any) => r && r.category !== 'portfolio')
          .map((r: any, i: number) => normalize(r, 'individual', i + 1))
        portfolio = parsed
          .filter((r: any) => r && r.category === 'portfolio')
          .map((r: any, i: number) => normalize(r, 'portfolio', i + 1))
      }
    } catch {
      /* empty */
    }

    let indUpdated = 0
    const byName = new Map(
      individual
        .filter((r) => r.item.trim())
        .map((r) => [r.item.trim(), r] as const),
    )
    for (const [name, amt] of indProv) {
      const hit = byName.get(name)
      if (hit) {
        hit.provisionIncrease = amt
        if (!hit.reason.includes('来自G2-7')) {
          hit.reason = hit.reason ? `${hit.reason}；来自G2-7测算` : '来自G2-7测算'
        }
        indUpdated += 1
      } else {
        const blank = individual.find((r) => !r.item.trim())
        if (blank) {
          blank.item = name
          blank.provisionIncrease = amt
          blank.reason = '来自G2-7测算'
          byName.set(name, blank)
          indUpdated += 1
        } else {
          const row = emptyLeaf('individual', individual.length + 1, name)
          row.provisionIncrease = amt
          row.reason = '来自G2-7测算'
          individual.push(row)
          byName.set(name, row)
          indUpdated += 1
        }
      }
    }
    if (!individual.length) individual = [emptyLeaf('individual', 1, '')]
    individual.forEach((r, i) => { r.seq = i + 1 })

    let portUpdated = 0
    const byKey = new Map(
      portfolio.filter((r) => r.agingKey).map((r) => [r.agingKey!, r] as const),
    )
    for (const seg of segments.value) {
      let row = byKey.get(seg.key)
      if (!row) {
        row = emptyLeaf('portfolio', portfolio.length + 1, seg.label, seg.key)
        portfolio.push(row)
        byKey.set(seg.key, row)
      } else {
        row.item = seg.label
        row.agingKey = seg.key
      }
      if (portProv.has(seg.key)) {
        row.provisionIncrease = portProv.get(seg.key)!
        if (!row.reason.includes('来自G2-7')) {
          row.reason = row.reason ? `${row.reason}；来自G2-7测算` : '来自G2-7测算'
        }
        portUpdated += 1
      }
    }
    portfolio = segments.value.map((seg, i) => {
      const row = byKey.get(seg.key) || emptyLeaf('portfolio', i + 1, seg.label, seg.key)
      return { ...row, seq: i + 1, item: seg.label, agingKey: seg.key, category: 'portfolio' as const }
    })

    const next = [...individual, ...portfolio]
    debouncedSave(BAD_DEBT_STORAGE, {
      item_id: BAD_DEBT_STORAGE,
      conclusion: null,
      remark: JSON.stringify(next),
    })
    allResponses.value.set(BAD_DEBT_STORAGE, {
      item_id: BAD_DEBT_STORAGE,
      conclusion: null,
      remark: JSON.stringify(next),
    })

    try {
      window.dispatchEvent(
        new CustomEvent('g2:ecl-provision-pushed', {
          detail: { individual: indUpdated, portfolio: portUpdated },
        }),
      )
    } catch { /* silent */ }

    return { individual: indUpdated, portfolio: portUpdated }
  }

  /** 将测算差异推送为 G2-4 调整分录行（账项调整，影响坏账准备） */
  function pushDiffsToG24(): number {
    if (readonly.value) return 0
    const diffs = collectDiffItems()
    if (!diffs.length) {
      ElMessage.info('无显著差异可推送')
      return 0
    }

    const existingRaw = allResponses.value.get(ADJ_STORAGE)?.remark
    let existing: G2AdjustmentRow[] = []
    try {
      const parsed = existingRaw ? JSON.parse(existingRaw) : []
      existing = Array.isArray(parsed) ? parsed : []
    } catch {
      existing = []
    }

    // 移除此前由 G2-7 推送的行，再追加最新差异
    const kept = existing.filter((r: any) => !String(r.remark || '').includes('来自G2-7测算'))
    const added: G2AdjustmentRow[] = []
    for (const d of diffs) {
      const row = createEmptyG2AdjustmentRow()
      row.description = d.desc
      row.category = '账项调整'
      row.reportItem = '应收利息'
      row.accountName = '坏账准备-应收利息'
      row.accountCode = '1231'
      row.indexRef = 'G2-7'
      row.remark = '来自G2-7测算'
      // 少提(差异>0)→借：信用减值损失 / 贷：坏账准备 → 本表推送坏账准备贷方
      // 简化：在 G2-4 记一笔坏账准备侧（贷方=少提金额，借方=多提金额）
      if (d.amount > 0) {
        row.creditAmount = d.amount
        row.debitAmount = 0
      } else {
        row.debitAmount = Math.abs(d.amount)
        row.creditAmount = 0
      }
      added.push(row)
    }

    const next = [...kept, ...added]
    debouncedSave(ADJ_STORAGE, {
      item_id: ADJ_STORAGE,
      conclusion: JSON.stringify(next),
      remark: JSON.stringify(next),
    })

    try {
      window.dispatchEvent(
        new CustomEvent('g2:ecl-diff-pushed', {
          detail: { count: added.length, totalDiff: grandTotal.value.totalDiff },
        }),
      )
    } catch { /* silent */ }

    return added.length
  }

  function onAgingConfigChanged() {
    if (sheetAgingPreset.value === 'THREE_YEAR' || sheetAgingPreset.value === 'FIVE_YEAR') return
    if (sheetAgingPreset.value === 'CUSTOM' && customSegments.value.length >= 2) return
    if (!segments.value.length || !agingGroups.value.length) return
    agingGroups.value = agingGroups.value.map((g) => ({
      ...g,
      rows: syncAgingGroupRows(g.rows, segments.value),
    }))
    persistGroups()
  }
  window.addEventListener('aging-config:changed', onAgingConfigChanged)

  const onG2AgingSync = (e: Event) => {
    const d = (e as CustomEvent<G2AgingSyncDetail>).detail
    if (!d?.preset || d.source === 'G2-7') return
    setAgingPreset(d.preset, d.customLabels)
  }
  window.addEventListener('g2:aging-preset-sync', onG2AgingSync)

  function syncAgingAcrossSheets(): void {
    if (readonly.value) return
    const labels =
      agingPreset.value === 'CUSTOM'
        ? customSegments.value.map((s) => s.label)
        : []
    syncG2AgingPresetToAllSheets(allResponses.value, agingPreset.value, labels, 'G2-7')
    ElMessage.success('已同步账龄口径至 G2-2 / G2-3 / G2-6')
  }

  onBeforeUnmount(() => {
    window.removeEventListener('aging-config:changed', onAgingConfigChanged)
    window.removeEventListener('g2:aging-preset-sync', onG2AgingSync)
  })

  // 兼容旧 API（阶段 Tab 已移除，保留空壳避免调用方报错）
  const dataRows = computed(() => [] as any[])
  const totals = computed(() => ({
    closingBalance: grandTotal.value.bookBalance,
    ead: 0,
    eclAmount: grandTotal.value.expectedProvision,
    companyProvision: grandTotal.value.bookBalance,
    eclVariance: grandTotal.value.totalDiff,
  }))

  return {
    agingPreset,
    segments,
    customSegments,
    setAgingPreset,
    syncAgingAcrossSheets,
    singleRows,
    singleTotal,
    addSingleRow,
    removeSingleRow,
    updateSingleCell,
    agingGroups,
    agingGroupTotals,
    addAgingGroup,
    removeAgingGroup,
    updateGroupName,
    updateAgingCell,
    otherRows,
    otherTotal,
    addOtherRow,
    removeOtherRow,
    updateOtherCell,
    grandTotal,
    diffAlert,
    pushDiffsToG24,
    pushProvisionToG23,
    hydrateFromFlat,
    // legacy aliases
    dataRows,
    totals,
    addRow: addSingleRow,
    removeRow: removeSingleRow,
    updateCell: () => {},
    isVarianceWarning: (row: { difference?: number }) => Math.abs(row.difference || 0) >= 0.01,
  }
}

export default useG2ECLCalc
