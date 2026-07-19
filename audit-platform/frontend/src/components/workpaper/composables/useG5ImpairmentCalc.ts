/**
 * useG5ImpairmentCalc — G5-10 长期应收款坏账准备测算表
 *
 * 对齐源模板结构（致同 Excel G5-10）：
 *   (一) 单项计提坏账准备
 *   (二) 按组合计提 — 信用期（可删不适用行；支持自定义段）
 *   (三) 其他组合计提 — 账龄（多组合 × 动态账龄段：3年段/5年段/自定义）
 *
 * 公式（源模板）：
 *   应计提③ = 审定余额① × 损失率②
 *   差异⑤ = 应计提③ − 账面准备④
 *
 * 兼容：
 *   - 旧版 Stage 公式链行数组 → 迁移为单项行
 *   - G5-9「同步阶段至 G5-10」写入单项行的 stageGroup
 */
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import type { AgingSegment, AgingPreset } from '@/composables/useAgingConfig'
import { parseNum } from '@/composables/useG5FormulaEngine'
import { createEmptyEntry, type AdjustmentEntry } from './useG5Adjustment'
import { normalizeStoredLeaves, computeMovement } from './useG5BadDebtDetail'
import { readCanonicalRaw } from './g5StorageContract'
import type { ChecklistResponse } from './useF1FormData'

// ─── 类型 ────────────────────────────────────────────────────────────────────

export type G5AgingPreset = AgingPreset
export type G5CreditPreset = 'DEFAULT' | 'CUSTOM'

export interface G5EclLineRow {
  rowId: string
  /** 单项：债务人；信用期/账龄：段名 */
  label: string
  segmentKey: string
  auditedBalance: number
  lossRate: number
  expectedProvision: number
  bookProvision: number
  difference: number
  basis: string
  indexRef: string
  /** 仅单项：来自 G5-9 */
  stageGroup?: 'Stage1' | 'Stage2' | 'Stage3'
  archived?: boolean
}

export interface G5EclGroup {
  groupId: string
  groupName: string
  rows: G5EclLineRow[]
}

export interface G5ImpairmentPayloadV2 {
  version: 2
  singleRows: G5EclLineRow[]
  creditGroups: G5EclGroup[]
  agingGroups: G5EclGroup[]
  agingPreset: G5AgingPreset
  customAgingLabels: string[]
  creditPreset: G5CreditPreset
  customCreditLabels: string[]
}

/** @deprecated 旧版 Stage 公式链行，仅用于迁移 / G5-9 兼容读取 */
export interface G5ImpairmentCalcRow {
  id: string
  seq: number
  debtor: string
  stageGroup: 'Stage1' | 'Stage2' | 'Stage3'
  bookBalance: number
  pvFutureCashFlow: number
  creditLossRate: number
  impairmentProvision: number
  bookValue: number
  balanceAdjustment: number
  adjustedCreditLossRate: number
  impairmentAdjustment: number
  adjBookBalance: number
  adjImpairment: number
  adjBookValue: number
  priorImpairment: number
  currentProvision: number
  currentReversal: number
  differenceNote: string
}

// ─── 预设段 ──────────────────────────────────────────────────────────────────

/** 源模板（二）信用期默认段 */
export const G5_CREDIT_TERM_SEGMENTS: AgingSegment[] = [
  { key: 'in_term', label: '合同期内', dayFrom: 0, dayTo: 0 },
  { key: 'od_0_30', label: '逾期30天以内', dayFrom: 1, dayTo: 30 },
  { key: 'od_30_90', label: '逾期30-90天', dayFrom: 31, dayTo: 90 },
  { key: 'od_90_plus', label: '逾期90天以上', dayFrom: 91, dayTo: null },
]

/** 源模板（三）5 年段双标签（账龄 / 逾期） */
export const G5_AGING_FIVE_YEAR: AgingSegment[] = [
  { key: 'within1', label: '1年以内/未逾期', dayFrom: 0, dayTo: 365 },
  { key: 'y1to2', label: '1-2年/逾期30天以内', dayFrom: 366, dayTo: 730 },
  { key: 'y2to3', label: '2-3年/逾期31-90天', dayFrom: 731, dayTo: 1095 },
  { key: 'y3to4', label: '3-4年/逾期91天-1年', dayFrom: 1096, dayTo: 1460 },
  { key: 'y4to5', label: '4-5年/逾期1-2年', dayFrom: 1461, dayTo: 1825 },
  { key: 'over5', label: '5年以上/逾期2年以上', dayFrom: 1826, dayTo: null },
]

export const G5_AGING_THREE_YEAR: AgingSegment[] = [
  { key: 'within1', label: '1年以内(含1年)', dayFrom: 0, dayTo: 365 },
  { key: 'y1to2', label: '1-2年(含2年)', dayFrom: 366, dayTo: 730 },
  { key: 'y2to3', label: '2-3年(含3年)', dayFrom: 731, dayTo: 1095 },
  { key: 'over3', label: '3年以上', dayFrom: 1096, dayTo: null },
]

const STORAGE_KEY = 'G5-10-rows'
const G5_2_KEY = 'G5-2-rows'
const G5_3_KEY = 'G5-3-rows'
const G5_4_KEY = 'G5-4-rows'
const PUSH_MARK = '来自G5-10测算'

export interface G5EclDiffItem {
  desc: string
  amount: number
  section: 'single' | 'credit' | 'aging'
}

export interface G5PullResult {
  singles: number
  agingBands: number
  bookIndividual: number
  bookPortfolio: number
}

function uid(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function round2(n: number): number {
  return Math.round(parseNum(n) * 100) / 100
}

function calcExpected(balance: number, rate: number): number {
  return round2(parseNum(balance) * parseNum(rate))
}

function calcDiff(expected: number, book: number): number {
  return round2(parseNum(expected) - parseNum(book))
}

function recalcLine(row: G5EclLineRow): G5EclLineRow {
  const expectedProvision = calcExpected(row.auditedBalance, row.lossRate)
  return {
    ...row,
    expectedProvision,
    difference: calcDiff(expectedProvision, row.bookProvision),
  }
}

function labelsToSegments(labels: string[]): AgingSegment[] {
  return labels.map((label, i) => ({
    key: `custom-${i}`,
    label,
    dayFrom: 0,
    dayTo: null,
  }))
}

export function resolveAgingSegments(
  preset: G5AgingPreset,
  customLabels: string[] = [],
): AgingSegment[] {
  if (preset === 'CUSTOM' && customLabels.length >= 2) return labelsToSegments(customLabels)
  if (preset === 'THREE_YEAR') return G5_AGING_THREE_YEAR.map((s) => ({ ...s }))
  return G5_AGING_FIVE_YEAR.map((s) => ({ ...s }))
}

export function resolveCreditSegments(
  preset: G5CreditPreset,
  customLabels: string[] = [],
): AgingSegment[] {
  if (preset === 'CUSTOM' && customLabels.length >= 2) return labelsToSegments(customLabels)
  return G5_CREDIT_TERM_SEGMENTS.map((s) => ({ ...s }))
}

function createLineFromSegment(seg: AgingSegment): G5EclLineRow {
  return recalcLine({
    rowId: uid('ln'),
    label: seg.label,
    segmentKey: seg.key,
    auditedBalance: 0,
    lossRate: 0,
    expectedProvision: 0,
    bookProvision: 0,
    difference: 0,
    basis: '',
    indexRef: '',
  })
}

function createEmptySingle(debtor = '', stage: 'Stage1' | 'Stage2' | 'Stage3' = 'Stage1'): G5EclLineRow {
  return recalcLine({
    rowId: uid('si'),
    label: debtor,
    segmentKey: '',
    auditedBalance: 0,
    lossRate: 0,
    expectedProvision: 0,
    bookProvision: 0,
    difference: 0,
    basis: '',
    indexRef: '',
    stageGroup: stage,
  })
}

function createGroup(name: string, segs: AgingSegment[]): G5EclGroup {
  return {
    groupId: uid('grp'),
    groupName: name,
    rows: segs.map(createLineFromSegment),
  }
}

/** 切换段定义时保留同 key / 同名已填数；有数据的旧段归档 */
export function syncGroupRows(
  existingRows: G5EclLineRow[],
  newSegments: AgingSegment[],
): G5EclLineRow[] {
  const newKeys = new Set(newSegments.map((s) => s.key))
  const byKey = new Map<string, G5EclLineRow>()
  const byLabel = new Map<string, G5EclLineRow>()
  for (const row of existingRows) {
    if (row.segmentKey) byKey.set(row.segmentKey, row)
    if (row.label) byLabel.set(row.label, row)
  }
  const result = newSegments.map((seg) => {
    const hit = byKey.get(seg.key) || byLabel.get(seg.label)
    if (hit) {
      return recalcLine({
        ...hit,
        segmentKey: seg.key,
        label: seg.label,
        archived: undefined,
      })
    }
    return createLineFromSegment(seg)
  })
  for (const row of existingRows) {
    const key = row.segmentKey || ''
    if (key && !newKeys.has(key) && !row.archived) {
      const hasData =
        parseNum(row.lossRate) !== 0
        || parseNum(row.bookProvision) !== 0
        || parseNum(row.auditedBalance) !== 0
      if (hasData) result.push({ ...row, archived: true })
    }
  }
  return result
}

function sumLines(rows: G5EclLineRow[]) {
  const active = rows.filter((r) => !r.archived)
  return {
    balance: round2(active.reduce((s, r) => s + parseNum(r.auditedBalance), 0)),
    expected: round2(active.reduce((s, r) => s + parseNum(r.expectedProvision), 0)),
    book: round2(active.reduce((s, r) => s + parseNum(r.bookProvision), 0)),
    diff: round2(active.reduce((s, r) => s + parseNum(r.difference), 0)),
  }
}

function emptyPayload(): G5ImpairmentPayloadV2 {
  const agingSegs = resolveAgingSegments('FIVE_YEAR')
  const creditSegs = resolveCreditSegments('DEFAULT')
  return {
    version: 2,
    singleRows: [],
    creditGroups: [createGroup('信用期组合', creditSegs)],
    agingGroups: [
      createGroup('组合1', agingSegs),
      createGroup('组合2', agingSegs.map((s) => ({ ...s }))),
    ],
    agingPreset: 'FIVE_YEAR',
    customAgingLabels: [],
    creditPreset: 'DEFAULT',
    customCreditLabels: [],
  }
}

/** 旧 Stage 行 → 单项行 */
export function migrateLegacyStageRows(rows: G5ImpairmentCalcRow[]): G5EclLineRow[] {
  return rows
    .filter((r) => String(r.debtor || '').trim())
    .map((r) =>
      recalcLine({
        rowId: r.id || uid('si'),
        label: String(r.debtor).trim(),
        segmentKey: '',
        auditedBalance: parseNum(r.adjBookBalance || r.bookBalance),
        lossRate: parseNum(r.adjustedCreditLossRate || r.creditLossRate),
        expectedProvision: 0,
        bookProvision: parseNum(r.adjImpairment || r.impairmentProvision),
        difference: 0,
        basis: r.differenceNote || '',
        indexRef: '',
        stageGroup: r.stageGroup || 'Stage1',
      }),
    )
}

export function parseG510Payload(raw: unknown): G5ImpairmentPayloadV2 {
  const base = emptyPayload()
  if (raw == null || raw === '') return base
  let parsed: any = raw
  if (typeof raw === 'string') {
    try {
      parsed = JSON.parse(raw)
    } catch {
      return base
    }
  }
  // 旧版：直接数组
  if (Array.isArray(parsed)) {
    return {
      ...base,
      singleRows: migrateLegacyStageRows(parsed as G5ImpairmentCalcRow[]),
    }
  }
  if (parsed && typeof parsed === 'object' && parsed.version === 2) {
    const p = parsed as Partial<G5ImpairmentPayloadV2>
    const agingPreset = (p.agingPreset as G5AgingPreset) || 'FIVE_YEAR'
    const customAging = Array.isArray(p.customAgingLabels) ? p.customAgingLabels.map(String) : []
    const creditPreset = (p.creditPreset as G5CreditPreset) || 'DEFAULT'
    const customCredit = Array.isArray(p.customCreditLabels) ? p.customCreditLabels.map(String) : []
    const agingSegs = resolveAgingSegments(agingPreset, customAging)
    const creditSegs = resolveCreditSegments(creditPreset, customCredit)
    return {
      version: 2,
      singleRows: Array.isArray(p.singleRows)
        ? p.singleRows.map((r) => recalcLine({ ...createEmptySingle(), ...r }))
        : [],
      creditGroups:
        Array.isArray(p.creditGroups) && p.creditGroups.length
          ? p.creditGroups.map((g) => ({
              groupId: g.groupId || uid('grp'),
              groupName: g.groupName || '信用期组合',
              rows: syncGroupRows(g.rows || [], creditSegs),
            }))
          : [createGroup('信用期组合', creditSegs)],
      agingGroups:
        Array.isArray(p.agingGroups) && p.agingGroups.length
          ? p.agingGroups.map((g, i) => ({
              groupId: g.groupId || uid('grp'),
              groupName: g.groupName || `组合${i + 1}`,
              rows: syncGroupRows(g.rows || [], agingSegs),
            }))
          : [createGroup('组合1', agingSegs), createGroup('组合2', agingSegs.map((s) => ({ ...s })))],
      agingPreset,
      customAgingLabels: customAging,
      creditPreset,
      customCreditLabels: customCredit,
    }
  }
  return base
}

/**
 * G5-9 同步阶段：写入单项行（兼容旧数组与 V2 payload）
 */
export function applyStageUpdatesToRows(
  existing: G5ImpairmentCalcRow[] | G5ImpairmentPayloadV2 | unknown,
  updates: Array<{ debtor: string; auditStage: 'Stage1' | 'Stage2' | 'Stage3' }>,
  _recalc?: (row: G5ImpairmentCalcRow) => void,
): { rows: G5ImpairmentCalcRow[]; count: number; payload: G5ImpairmentPayloadV2 } {
  const payload = parseG510Payload(existing)
  let count = 0
  for (const u of updates) {
    const name = String(u.debtor || '').trim()
    if (!name) continue
    let row = payload.singleRows.find((r) => r.label === name)
    if (!row) {
      row = createEmptySingle(name, u.auditStage)
      payload.singleRows.push(row)
    } else {
      row.stageGroup = u.auditStage
    }
    count += 1
  }
  // 兼容旧调用方仍读 rows：用单项行投影为旧结构
  const rows: G5ImpairmentCalcRow[] = payload.singleRows.map((r, i) => ({
    id: r.rowId,
    seq: i + 1,
    debtor: r.label,
    stageGroup: r.stageGroup || 'Stage1',
    bookBalance: r.auditedBalance,
    pvFutureCashFlow: 0,
    creditLossRate: r.lossRate,
    impairmentProvision: r.expectedProvision,
    bookValue: round2(r.auditedBalance - r.expectedProvision),
    balanceAdjustment: 0,
    adjustedCreditLossRate: r.lossRate,
    impairmentAdjustment: 0,
    adjBookBalance: r.auditedBalance,
    adjImpairment: r.bookProvision || r.expectedProvision,
    adjBookValue: round2(r.auditedBalance - (r.bookProvision || r.expectedProvision)),
    priorImpairment: 0,
    currentProvision: 0,
    currentReversal: 0,
    differenceNote: r.basis || '',
  }))
  return { rows, count, payload }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG5ImpairmentCalc() {
  const payload = ref<G5ImpairmentPayloadV2>(emptyPayload())

  const singleRows = computed(() => payload.value.singleRows)
  const creditGroups = computed(() => payload.value.creditGroups)
  const agingGroups = computed(() => payload.value.agingGroups)
  const agingPreset = computed(() => payload.value.agingPreset)
  const creditPreset = computed(() => payload.value.creditPreset)
  const agingSegments = computed(() =>
    resolveAgingSegments(payload.value.agingPreset, payload.value.customAgingLabels),
  )
  const creditSegments = computed(() =>
    resolveCreditSegments(payload.value.creditPreset, payload.value.customCreditLabels),
  )

  const singleTotal = computed(() => sumLines(payload.value.singleRows))
  const creditTotal = computed(() =>
    sumLines(payload.value.creditGroups.flatMap((g) => g.rows)),
  )
  const agingTotal = computed(() =>
    sumLines(payload.value.agingGroups.flatMap((g) => g.rows)),
  )
  const grandTotal = computed(() => ({
    balance: round2(singleTotal.value.balance + creditTotal.value.balance + agingTotal.value.balance),
    expected: round2(singleTotal.value.expected + creditTotal.value.expected + agingTotal.value.expected),
    book: round2(singleTotal.value.book + creditTotal.value.book + agingTotal.value.book),
    diff: round2(singleTotal.value.diff + creditTotal.value.diff + agingTotal.value.diff),
  }))

  const diffAlert = computed(() => {
    const d = grandTotal.value.diff
    if (Math.abs(d) < 0.01) return ''
    return `测算应计提与账面准备合计差异 ${d.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}，请核对后考虑推送调整。`
  })

  function touch() {
    payload.value = { ...payload.value }
  }

  function loadFromRaw(raw: string | null | undefined) {
    payload.value = parseG510Payload(raw)
  }

  function loadRows(data: G5ImpairmentCalcRow[] | G5ImpairmentPayloadV2) {
    payload.value = parseG510Payload(data)
  }

  function serialize(): string {
    return JSON.stringify(payload.value)
  }

  function toJSON(): G5ImpairmentPayloadV2 {
    return JSON.parse(serialize()) as G5ImpairmentPayloadV2
  }

  // ─── 单项 ──────────────────────────────────────────────────────────────────

  function addSingleRow(debtor = '') {
    payload.value.singleRows.push(createEmptySingle(debtor))
    touch()
  }

  function removeSingleRow(rowId: string) {
    payload.value.singleRows = payload.value.singleRows.filter((r) => r.rowId !== rowId)
    touch()
  }

  function updateSingleCell(
    rowId: string,
    field: keyof G5EclLineRow,
    value: string | number,
  ) {
    const row = payload.value.singleRows.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    Object.assign(row, recalcLine(row))
    touch()
  }

  // ─── 信用期 ────────────────────────────────────────────────────────────────

  function setCreditPreset(preset: G5CreditPreset, customLabels?: string[]): boolean {
    if (preset === 'CUSTOM') {
      const labels = (customLabels || []).map((l) => l.trim()).filter(Boolean)
      if (labels.length < 2) {
        ElMessage.warning('自定义信用期至少需要 2 段')
        return false
      }
      if (labels.length > 10) {
        ElMessage.warning('自定义信用期最多 10 段')
        return false
      }
      payload.value.customCreditLabels = labels
    }
    payload.value.creditPreset = preset
    const segs = resolveCreditSegments(preset, payload.value.customCreditLabels)
    payload.value.creditGroups = payload.value.creditGroups.map((g) => ({
      ...g,
      rows: syncGroupRows(g.rows, segs),
    }))
    if (!payload.value.creditGroups.length) {
      payload.value.creditGroups = [createGroup('信用期组合', segs)]
    }
    touch()
    return true
  }

  function updateCreditCell(
    groupId: string,
    rowId: string,
    field: keyof G5EclLineRow,
    value: string | number,
  ) {
    const g = payload.value.creditGroups.find((x) => x.groupId === groupId)
    const row = g?.rows.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    Object.assign(row, recalcLine(row))
    touch()
  }

  function removeCreditRow(groupId: string, rowId: string) {
    const g = payload.value.creditGroups.find((x) => x.groupId === groupId)
    if (!g || g.rows.filter((r) => !r.archived).length <= 1) {
      ElMessage.warning('至少保留一段信用期')
      return
    }
    g.rows = g.rows.filter((r) => r.rowId !== rowId)
    touch()
  }

  // ─── 账龄组合 ──────────────────────────────────────────────────────────────

  function setAgingPreset(preset: G5AgingPreset, customLabels?: string[]): boolean {
    if (preset === 'CUSTOM') {
      const labels = (customLabels || []).map((l) => l.trim()).filter(Boolean)
      if (labels.length < 2) {
        ElMessage.warning('自定义账龄至少需要 2 段')
        return false
      }
      if (labels.length > 10) {
        ElMessage.warning('自定义账龄最多 10 段')
        return false
      }
      payload.value.customAgingLabels = labels
    }
    payload.value.agingPreset = preset
    const segs = resolveAgingSegments(preset, payload.value.customAgingLabels)
    payload.value.agingGroups = payload.value.agingGroups.map((g) => ({
      ...g,
      rows: syncGroupRows(g.rows, segs),
    }))
    if (!payload.value.agingGroups.length) {
      payload.value.agingGroups = [createGroup('组合1', segs)]
    }
    touch()
    return true
  }

  function addAgingGroup() {
    const segs = resolveAgingSegments(payload.value.agingPreset, payload.value.customAgingLabels)
    const n = payload.value.agingGroups.length + 1
    payload.value.agingGroups.push(createGroup(`组合${n}`, segs))
    touch()
  }

  function removeAgingGroup(groupId: string) {
    if (payload.value.agingGroups.length <= 1) {
      ElMessage.warning('至少保留一个账龄组合')
      return
    }
    payload.value.agingGroups = payload.value.agingGroups.filter((g) => g.groupId !== groupId)
    touch()
  }

  function updateGroupName(groupId: string, name: string) {
    const g = payload.value.agingGroups.find((x) => x.groupId === groupId)
    if (g) g.groupName = name
    touch()
  }

  function updateAgingCell(
    groupId: string,
    rowId: string,
    field: keyof G5EclLineRow,
    value: string | number,
  ) {
    const g = payload.value.agingGroups.find((x) => x.groupId === groupId)
    const row = g?.rows.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    Object.assign(row, recalcLine(row))
    touch()
  }

  /** G5-9 同步 */
  function applyStageUpdates(
    updates: Array<{ debtor: string; auditStage: 'Stage1' | 'Stage2' | 'Stage3' }>,
  ): number {
    const applied = applyStageUpdatesToRows(payload.value, updates)
    payload.value = applied.payload
    return applied.count
  }

  // ─── 差异收集 / 推送 G5-4 / 从 G5-2·G5-3 灌数 ─────────────────────────────

  function collectDiffItems(threshold = 0.01): G5EclDiffItem[] {
    const items: G5EclDiffItem[] = []
    for (const r of payload.value.singleRows) {
      if (Math.abs(parseNum(r.difference)) < threshold) continue
      const name = String(r.label || '').trim() || '未命名'
      items.push({
        section: 'single',
        amount: parseNum(r.difference),
        desc: `坏账准备测算差异（单项）${name}`,
      })
    }
    for (const g of payload.value.creditGroups) {
      for (const r of g.rows) {
        if (r.archived || Math.abs(parseNum(r.difference)) < threshold) continue
        items.push({
          section: 'credit',
          amount: parseNum(r.difference),
          desc: `坏账准备测算差异（信用期）${r.label || g.groupName}`,
        })
      }
    }
    for (const g of payload.value.agingGroups) {
      for (const r of g.rows) {
        if (r.archived || Math.abs(parseNum(r.difference)) < threshold) continue
        items.push({
          section: 'aging',
          amount: parseNum(r.difference),
          desc: `坏账准备测算差异（${g.groupName || '账龄组合'}·${r.label}）`,
        })
      }
    }
    return items
  }

  function pushDiffsToG54(
    allResponses: Map<string, ChecklistResponse>,
    save: (itemId: string, data: Partial<ChecklistResponse>) => void,
  ): number {
    const diffs = collectDiffItems()
    if (!diffs.length) {
      ElMessage.info('无显著差异可推送')
      return 0
    }
    let existing: AdjustmentEntry[] = []
    try {
      const raw = readCanonicalRaw(allResponses.get(G5_4_KEY))
      const parsed = raw ? JSON.parse(raw) : []
      existing = Array.isArray(parsed) ? parsed : []
    } catch {
      existing = []
    }
    const kept = existing.filter((r) => !String(r.remark || '').includes(PUSH_MARK))
    const added: AdjustmentEntry[] = []
    for (const d of diffs) {
      const row = createEmptyEntry(kept.length + added.length + 1, d.desc)
      row.category = '账项调整'
      row.reportItem = '长期应收款'
      row.accountCode = '1231'
      row.accountName = '坏账准备'
      row.indexRef = 'G5-10'
      row.remark = PUSH_MARK
      // 少提(差异>0)→贷：坏账准备；多提(差异<0)→借：坏账准备
      if (d.amount > 0) {
        row.creditAmount = round2(d.amount)
        row.debitAmount = 0
      } else {
        row.debitAmount = round2(Math.abs(d.amount))
        row.creditAmount = 0
      }
      added.push(row)
    }
    const next = [...kept, ...added]
    const json = JSON.stringify(next)
    save(G5_4_KEY, { remark: json, conclusion: json })
    try {
      window.dispatchEvent(
        new CustomEvent('g5:ecl-diff-pushed', {
          detail: { count: added.length, totalDiff: grandTotal.value.diff },
        }),
      )
    } catch { /* silent */ }
    ElMessage.success(`已推送 ${added.length} 条差异至 G5-4`)
    return added.length
  }

  function parseG52Rows(allResponses: Map<string, ChecklistResponse>): any[] {
    const raw = readCanonicalRaw(allResponses.get(G5_2_KEY))
    if (!raw) return []
    try {
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed : (parsed?.rows ?? [])
    } catch {
      return []
    }
  }

  /** 从 G5-2 灌审定余额：单项按债务人；账龄按 agingAudited 汇总入第一组合（或新建匹配段） */
  function pullBalancesFromG52(allResponses: Map<string, ChecklistResponse>): Pick<G5PullResult, 'singles' | 'agingBands'> {
    const detail = parseG52Rows(allResponses)
    if (!detail.length) {
      ElMessage.warning('未找到 G5-2 余额明细，请先编制余额明细表')
      return { singles: 0, agingBands: 0 }
    }

    let singles = 0
    const agingSum = new Map<string, number>()

    for (const raw of detail) {
      const name = String(raw.debtorName || '').trim()
      const bal = parseNum(raw.netAmount != null && raw.netAmount !== '' ? raw.netAmount : raw.closingBalance)
      if (name && Math.abs(bal) >= 0.005) {
        let row = payload.value.singleRows.find((r) => r.label === name)
        if (!row) {
          row = createEmptySingle(name)
          payload.value.singleRows.push(row)
        }
        row.auditedBalance = round2(bal)
        Object.assign(row, recalcLine(row))
        singles += 1
      }
      const audited = raw.agingAudited && typeof raw.agingAudited === 'object' ? raw.agingAudited : null
      if (audited) {
        for (const [key, val] of Object.entries(audited)) {
          const n = parseNum(val)
          if (Math.abs(n) < 0.005) continue
          agingSum.set(key, round2((agingSum.get(key) || 0) + n))
        }
      }
    }

    let agingBands = 0
    if (agingSum.size) {
      if (!payload.value.agingGroups.length) {
        const segs = resolveAgingSegments(payload.value.agingPreset, payload.value.customAgingLabels)
        payload.value.agingGroups = [createGroup('组合1', segs)]
      }
      const g = payload.value.agingGroups[0]
      for (const row of g.rows) {
        if (row.archived) continue
        const key = row.segmentKey
        if (!agingSum.has(key)) continue
        row.auditedBalance = agingSum.get(key)!
        Object.assign(row, recalcLine(row))
        agingBands += 1
        agingSum.delete(key)
      }
      // 余下未知段：追加到组合（避免丢数）
      for (const [key, amount] of agingSum) {
        const line = recalcLine({
          rowId: uid('ln'),
          label: key,
          segmentKey: key,
          auditedBalance: amount,
          lossRate: 0,
          expectedProvision: 0,
          bookProvision: 0,
          difference: 0,
          basis: '来自G5-2账龄汇总',
          indexRef: 'G5-2',
        })
        g.rows.push(line)
        agingBands += 1
      }
    }

    touch()
    return { singles, agingBands }
  }

  function distributeBookToGroup(group: G5EclGroup, bookTotal: number) {
    const active = group.rows.filter((r) => !r.archived)
    if (!active.length) return 0
    const sumBal = active.reduce((s, r) => s + parseNum(r.auditedBalance), 0)
    if (Math.abs(sumBal) < 0.005) {
      for (const r of active) {
        r.bookProvision = 0
        Object.assign(r, recalcLine(r))
      }
      active[0].bookProvision = round2(bookTotal)
      Object.assign(active[0], recalcLine(active[0]))
      return 1
    }
    let assigned = 0
    active.forEach((r, i) => {
      const share =
        i === active.length - 1
          ? round2(bookTotal - assigned)
          : round2((parseNum(r.auditedBalance) / sumBal) * bookTotal)
      r.bookProvision = share
      assigned = round2(assigned + share)
      Object.assign(r, recalcLine(r))
    })
    return active.length
  }

  /** 从 G5-3 灌账面准备：单项匹配债务人；组合匹配账龄组合名（可新建） */
  function pullBookFromG53(allResponses: Map<string, ChecklistResponse>): Pick<G5PullResult, 'bookIndividual' | 'bookPortfolio'> {
    const leaves = normalizeStoredLeaves(readCanonicalRaw(allResponses.get(G5_3_KEY)))
    if (!leaves.length) {
      ElMessage.warning('未找到 G5-3 坏账准备明细，请先编制坏账准备明细表')
      return { bookIndividual: 0, bookPortfolio: 0 }
    }

    let bookIndividual = 0
    let bookPortfolio = 0
    const segs = resolveAgingSegments(payload.value.agingPreset, payload.value.customAgingLabels)

    for (const leaf of leaves) {
      const name = String(leaf.item || '').trim()
      if (!name) continue
      const { closingAudited } = computeMovement(leaf)
      if (leaf.category === 'individual') {
        let row = payload.value.singleRows.find((r) => r.label === name)
        if (!row) {
          row = createEmptySingle(name)
          payload.value.singleRows.push(row)
        }
        row.bookProvision = closingAudited
        Object.assign(row, recalcLine(row))
        bookIndividual += 1
      } else {
        let group = payload.value.agingGroups.find((g) => g.groupName === name)
        if (!group) {
          group = createGroup(name, segs)
          payload.value.agingGroups.push(group)
        }
        bookPortfolio += distributeBookToGroup(group, closingAudited)
      }
    }

    touch()
    return { bookIndividual, bookPortfolio }
  }

  function pullFromG52AndG53(allResponses: Map<string, ChecklistResponse>): G5PullResult {
    const a = pullBalancesFromG52(allResponses)
    const b = pullBookFromG53(allResponses)
    const result = { ...a, ...b }
    const total = result.singles + result.agingBands + result.bookIndividual + result.bookPortfolio
    if (total > 0) {
      ElMessage.success(
        `已灌入：单项余额 ${result.singles}、账龄段 ${result.agingBands}、单项账面 ${result.bookIndividual}、组合账面 ${result.bookPortfolio}`,
      )
    }
    return result
  }

  // 兼容旧 API 名
  const rows = computed({
    get: () => payload.value.singleRows.map((r, i) => ({
      id: r.rowId,
      seq: i + 1,
      debtor: r.label,
      stageGroup: r.stageGroup || 'Stage1' as const,
      bookBalance: r.auditedBalance,
      pvFutureCashFlow: 0,
      creditLossRate: r.lossRate,
      impairmentProvision: r.expectedProvision,
      bookValue: round2(r.auditedBalance - r.expectedProvision),
      balanceAdjustment: 0,
      adjustedCreditLossRate: r.lossRate,
      impairmentAdjustment: 0,
      adjBookBalance: r.auditedBalance,
      adjImpairment: r.bookProvision,
      adjBookValue: round2(r.auditedBalance - r.bookProvision),
      priorImpairment: 0,
      currentProvision: 0,
      currentReversal: 0,
      differenceNote: r.basis,
    })) as G5ImpairmentCalcRow[],
    set: () => { /* no-op */ },
  })

  return {
    STORAGE_KEY,
    payload,
    singleRows,
    creditGroups,
    agingGroups,
    agingPreset,
    creditPreset,
    agingSegments,
    creditSegments,
    customAgingLabels: computed(() => payload.value.customAgingLabels),
    customCreditLabels: computed(() => payload.value.customCreditLabels),
    singleTotal,
    creditTotal,
    agingTotal,
    grandTotal,
    diffAlert,
    rows,
    activeTab: ref<'tab1' | 'tab2'>('tab1'),
    activeRowIndex: ref(0),
    loadFromRaw,
    loadRows,
    serialize,
    toJSON,
    addSingleRow,
    removeSingleRow,
    updateSingleCell,
    setCreditPreset,
    updateCreditCell,
    removeCreditRow,
    setAgingPreset,
    addAgingGroup,
    removeAgingGroup,
    updateGroupName,
    updateAgingCell,
    applyStageUpdates,
    collectDiffItems,
    pushDiffsToG54,
    pullBalancesFromG52,
    pullBookFromG53,
    pullFromG52AndG53,
    // legacy stubs（避免旧调用崩）
    addRow: async (stage: 'Stage1' | 'Stage2' | 'Stage3' = 'Stage1') => {
      addSingleRow()
      const last = payload.value.singleRows[payload.value.singleRows.length - 1]
      if (last) last.stageGroup = stage
      touch()
    },
    removeRow: (id: string) => removeSingleRow(id),
    recalcRow: () => {},
    groupedRows: computed(() => ({
      stage1: { rows: [], subtotal: emptySub() },
      stage2: { rows: [], subtotal: emptySub() },
      stage3: { rows: [], subtotal: emptySub() },
      grandTotal: emptySub(),
    })),
  }
}

function emptySub() {
  return {
    bookBalance: 0,
    impairmentProvision: 0,
    bookValue: 0,
    balanceAdjustment: 0,
    impairmentAdjustment: 0,
    adjBookBalance: 0,
    adjImpairment: 0,
    adjBookValue: 0,
  }
}

// re-export for stage sheet / tests
export default useG5ImpairmentCalc
