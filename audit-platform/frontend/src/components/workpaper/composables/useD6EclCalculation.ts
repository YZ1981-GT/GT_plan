/**
 * useD6EclCalculation — D6-8 ECL减值测算（双组合58公式）
 *
 * 结构：
 *   (一) 单项计提（EclSingleRow[]）
 *   (二) 账龄组合（EclAgingGroup[]，每组合含N账龄段+小计，N由项目账龄配置决定）
 *
 * 公式：
 *   - 应计提③ = 审定余额① × 损失率②
 *   - 差异⑤ = 应计提③ - 账面余额④
 *
 * 联动 aging-config:changed：
 *   - 已有段保留 lossRate/bookBalance
 *   - 新增段零初始化
 *   - 移除段标记归档（archived: true）
 *
 * Spec: .kiro/specs/d6-contract-assets/ + .kiro/specs/aging-config-enhancement/
 * Task: 11.1, 13.1
 * Requirements: 9.1, 9.2, 9.3, 13.1-13.12, 27.1, 27.4
 */
import { ref, computed, watch, onUnmounted, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcExpectedProvision,
  calcEclDifference,
  calcSubtotal,
} from './useD6FormulaEngine'
import type { ChecklistResponse } from './useD6FormData'
import { useAgingConfig, type AgingSegment } from '@/composables/useAgingConfig'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface EclSingleRow {
  rowId: string
  debtorName: string         // 债务人名称
  auditedBalance: number     // 审定账面余额①
  lossRate: number           // 预期信用损失率②
  expectedProvision: number  // 期末应计提③ = ①×②（自动）
  bookBalance: number        // 期末坏账准备账面余额④
  difference: number         // 差异⑤ = ③-④（自动）
  basis: string              // 计提依据及文件
  indexRef: string           // 索引号
}

export interface EclAgingRow {
  rowId: string
  segmentKey: string           // 账龄段 key (与 AgingSegment.key 对应)
  agingBand: string            // 账龄段显示名
  auditedBalance: number       // 审定账面余额①
  lossRate: number             // 预期信用损失率②
  expectedProvision: number    // 期末应计提③ = ①×②（自动）
  bookBalance: number          // 期末坏账准备账面余额④
  difference: number           // 差异⑤ = ③-④（自动）
  archived?: boolean           // 配置变更移除段时标记归档（保留历史数据）
}

export interface EclAgingGroup {
  groupId: string
  groupName: string          // 组合名称
  rows: EclAgingRow[]        // N账龄段（由项目配置决定）+ 可能的归档行
}

export interface UseD6EclCalculationOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_SINGLE_ROWS = 'D6-8-single-rows'
const ITEM_ID_GROUPS = 'D6-8-groups'

/** 默认6账龄段 */
export const DEFAULT_AGING_BANDS = [
  '1年以内',
  '1-2年',
  '2-3年',
  '3-4年',
  '4-5年',
  '5年以上',
] as const

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

function generateGroupId(): string {
  return `grp-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

// ─── Single Row Helpers ──────────────────────────────────────────────────────

function safeParseSingleRows(jsonStr: string | null | undefined): EclSingleRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(normalizeSingleRow) : []
  } catch {
    return []
  }
}

function normalizeSingleRow(raw: any): EclSingleRow {
  return {
    rowId: raw.rowId || generateRowId(),
    debtorName: raw.debtorName || '',
    auditedBalance: parseNum(raw.auditedBalance),
    lossRate: parseNum(raw.lossRate),
    expectedProvision: parseNum(raw.expectedProvision),
    bookBalance: parseNum(raw.bookBalance),
    difference: parseNum(raw.difference),
    basis: raw.basis || '',
    indexRef: raw.indexRef || '',
  }
}

/**
 * 重算单项行：
 *  expectedProvision = auditedBalance × lossRate
 *  difference = expectedProvision - bookBalance
 */
export function recalcSingleRow(row: EclSingleRow): EclSingleRow {
  const expectedProvision = calcExpectedProvision(row.auditedBalance, row.lossRate)
  const difference = calcEclDifference(expectedProvision, row.bookBalance)
  return { ...row, expectedProvision, difference }
}

function createEmptySingleRow(): EclSingleRow {
  return {
    rowId: generateRowId(),
    debtorName: '',
    auditedBalance: 0,
    lossRate: 0,
    expectedProvision: 0,
    bookBalance: 0,
    difference: 0,
    basis: '',
    indexRef: '',
  }
}

// ─── Aging Group Helpers ─────────────────────────────────────────────────────

function safeParseGroups(jsonStr: string | null | undefined): EclAgingGroup[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(normalizeGroup) : []
  } catch {
    return []
  }
}

function normalizeGroup(raw: any): EclAgingGroup {
  return {
    groupId: raw.groupId || generateGroupId(),
    groupName: raw.groupName || '',
    rows: Array.isArray(raw.rows) ? raw.rows.map(normalizeAgingRow) : createDefaultAgingRows(),
  }
}

function normalizeAgingRow(raw: any): EclAgingRow {
  return {
    rowId: raw.rowId || generateRowId(),
    segmentKey: raw.segmentKey || '',
    agingBand: raw.agingBand || '',
    auditedBalance: parseNum(raw.auditedBalance),
    lossRate: parseNum(raw.lossRate),
    expectedProvision: parseNum(raw.expectedProvision),
    bookBalance: parseNum(raw.bookBalance),
    difference: parseNum(raw.difference),
    ...(raw.archived ? { archived: true } : {}),
  }
}

/**
 * 重算账龄行：
 *  expectedProvision = auditedBalance × lossRate
 *  difference = expectedProvision - bookBalance
 */
export function recalcAgingRow(row: EclAgingRow): EclAgingRow {
  const expectedProvision = calcExpectedProvision(row.auditedBalance, row.lossRate)
  const difference = calcEclDifference(expectedProvision, row.bookBalance)
  return { ...row, expectedProvision, difference }
}

/**
 * 基于项目账龄段配置创建初始行（Req 9.1: 按 segments 初始化，替代硬编码6行）
 */
function createAgingRowsFromSegments(segments: AgingSegment[]): EclAgingRow[] {
  return segments.map(seg => ({
    rowId: generateRowId(),
    segmentKey: seg.key,
    agingBand: seg.label,
    auditedBalance: 0,
    lossRate: 0,
    expectedProvision: 0,
    bookBalance: 0,
    difference: 0,
  }))
}

/**
 * 兜底：无配置时用默认6段
 */
function createDefaultAgingRows(): EclAgingRow[] {
  return DEFAULT_AGING_BANDS.map(band => ({
    rowId: generateRowId(),
    segmentKey: '',
    agingBand: band,
    auditedBalance: 0,
    lossRate: 0,
    expectedProvision: 0,
    bookBalance: 0,
    difference: 0,
  }))
}

/**
 * 配置变更时同步组合行（Req 9.2, 9.3）：
 * - 已有段保留 lossRate/bookBalance
 * - 新增段零初始化
 * - 移除段标记 archived
 */
export function syncAgingGroupRows(
  existingRows: EclAgingRow[],
  newSegments: AgingSegment[],
): EclAgingRow[] {
  const newKeys = new Set(newSegments.map(s => s.key))

  // 构建现有行的 segmentKey→row 索引（兼容旧数据用 agingBand 匹配）
  const existingByKey = new Map<string, EclAgingRow>()
  const existingByLabel = new Map<string, EclAgingRow>()
  for (const row of existingRows) {
    if (row.segmentKey) {
      existingByKey.set(row.segmentKey, row)
    }
    if (row.agingBand) {
      existingByLabel.set(row.agingBand, row)
    }
  }

  // 为新配置的每个段创建/保留行
  const result: EclAgingRow[] = newSegments.map(seg => {
    // 优先按 key 匹配，再按 label 匹配（兼容旧数据无 segmentKey 的情况）
    const existing = existingByKey.get(seg.key) || existingByLabel.get(seg.label)
    if (existing) {
      // 已有段：保留 lossRate/bookBalance，更新 label/segmentKey
      return recalcAgingRow({
        ...existing,
        segmentKey: seg.key,
        agingBand: seg.label,
        archived: undefined,  // 如果之前被归档，恢复
      } as EclAgingRow)
    }
    // 新增段：零初始化
    return {
      rowId: generateRowId(),
      segmentKey: seg.key,
      agingBand: seg.label,
      auditedBalance: 0,
      lossRate: 0,
      expectedProvision: 0,
      bookBalance: 0,
      difference: 0,
    }
  })

  // 标记移除段为归档（保留历史数据，不删除）
  for (const row of existingRows) {
    const rowKey = row.segmentKey || ''
    if (rowKey && !newKeys.has(rowKey) && !row.archived) {
      // 只有当行有实际数据时才归档，全零行直接丢弃
      const hasData = row.lossRate !== 0 || row.bookBalance !== 0 || row.auditedBalance !== 0
      if (hasData) {
        result.push({
          ...row,
          archived: true,
        })
      }
    }
  }

  return result
}

function createEmptyGroup(segments?: AgingSegment[]): EclAgingGroup {
  return {
    groupId: generateGroupId(),
    groupName: '',
    rows: segments && segments.length > 0
      ? createAgingRowsFromSegments(segments)
      : createDefaultAgingRows(),
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD6EclCalculation(options: UseD6EclCalculationOptions) {
  const { allResponses, debouncedSave, projectId } = options

  // ─── Aging Config (Req 9.1) ──────────────────────────────────────────

  const { segments } = useAgingConfig(projectId, 'D2')

  // ─── Reactive data ───────────────────────────────────────────────────

  const singleRows = ref<EclSingleRow[]>([])
  const agingGroups = ref<EclAgingGroup[]>([])

  // Load single rows
  watch(
    () => allResponses.value.get(ITEM_ID_SINGLE_ROWS)?.remark,
    (jsonStr) => {
      singleRows.value = safeParseSingleRows(jsonStr).map(recalcSingleRow)
    },
    { immediate: true },
  )

  // Load aging groups
  watch(
    () => allResponses.value.get(ITEM_ID_GROUPS)?.remark,
    (jsonStr) => {
      const groups = safeParseGroups(jsonStr)
      agingGroups.value = groups.map(g => ({
        ...g,
        rows: g.rows.map(recalcAgingRow),
      }))
    },
    { immediate: true },
  )

  // ─── Persist ─────────────────────────────────────────────────────────

  function persistSingleRows(): void {
    debouncedSave(ITEM_ID_SINGLE_ROWS, { remark: JSON.stringify(singleRows.value) })
  }

  function persistGroups(): void {
    debouncedSave(ITEM_ID_GROUPS, { remark: JSON.stringify(agingGroups.value) })
  }

  // ─── Computed: Totals ────────────────────────────────────────────────

  const singleTotal = computed(() => ({
    balance: calcSubtotal(singleRows.value.map(r => r.auditedBalance)),
    provision: calcSubtotal(singleRows.value.map(r => r.expectedProvision)),
    book: calcSubtotal(singleRows.value.map(r => r.bookBalance)),
    diff: calcSubtotal(singleRows.value.map(r => r.difference)),
  }))

  /** 每组合的小计 */
  const agingGroupTotals = computed(() => {
    return agingGroups.value.map(g => ({
      groupId: g.groupId,
      groupName: g.groupName,
      balance: calcSubtotal(g.rows.map(r => r.auditedBalance)),
      provision: calcSubtotal(g.rows.map(r => r.expectedProvision)),
      book: calcSubtotal(g.rows.map(r => r.bookBalance)),
      diff: calcSubtotal(g.rows.map(r => r.difference)),
    }))
  })

  /** 合计 = 单项 + 各组合 */
  const grandTotal = computed(() => {
    const groupProvisionSum = calcSubtotal(agingGroupTotals.value.map(g => g.provision))
    const groupBookSum = calcSubtotal(agingGroupTotals.value.map(g => g.book))
    const groupDiffSum = calcSubtotal(agingGroupTotals.value.map(g => g.diff))
    return {
      expectedProvision: singleTotal.value.provision + groupProvisionSum,
      bookBalance: singleTotal.value.book + groupBookSum,
      totalDiff: singleTotal.value.diff + groupDiffSum,
    }
  })

  /** 总差异≠0时的告警文案 */
  const diffAlert: ComputedRef<string | null> = computed(() => {
    if (Math.abs(grandTotal.value.totalDiff) < 0.01) return null
    const sign = grandTotal.value.totalDiff > 0 ? '少提' : '多提'
    return `应计提与账面准备存在差异（${sign}${Math.abs(grandTotal.value.totalDiff).toFixed(2)}元），请关注减值准备计提充分性。`
  })

  // ─── Single Row Actions ──────────────────────────────────────────────

  function addSingleRow(): void {
    singleRows.value = [...singleRows.value, createEmptySingleRow()]
    persistSingleRows()
  }

  function removeSingleRow(rowId: string): void {
    singleRows.value = singleRows.value.filter(r => r.rowId !== rowId)
    persistSingleRows()
  }

  function updateSingleCell(rowId: string, field: string, value: any): void {
    const NUMERIC_FIELDS = ['auditedBalance', 'lossRate', 'bookBalance']
    singleRows.value = singleRows.value.map(r => {
      if (r.rowId !== rowId) return r
      const updated = { ...r }
      if (NUMERIC_FIELDS.includes(field)) {
        ;(updated as any)[field] = parseNum(value)
      } else {
        ;(updated as any)[field] = value
      }
      return recalcSingleRow(updated)
    })
    persistSingleRows()
  }

  // ─── Aging Group Actions ─────────────────────────────────────────────

  function addAgingGroup(): void {
    agingGroups.value = [...agingGroups.value, createEmptyGroup(segments.value)]
    persistGroups()
  }

  function removeAgingGroup(groupId: string): void {
    agingGroups.value = agingGroups.value.filter(g => g.groupId !== groupId)
    persistGroups()
  }

  function updateGroupName(groupId: string, name: string): void {
    agingGroups.value = agingGroups.value.map(g =>
      g.groupId === groupId ? { ...g, groupName: name } : g,
    )
    persistGroups()
  }

  function updateAgingCell(groupId: string, rowId: string, field: string, value: any): void {
    const NUMERIC_FIELDS = ['auditedBalance', 'lossRate', 'bookBalance']
    agingGroups.value = agingGroups.value.map(g => {
      if (g.groupId !== groupId) return g
      return {
        ...g,
        rows: g.rows.map(r => {
          if (r.rowId !== rowId) return r
          const updated = { ...r }
          if (NUMERIC_FIELDS.includes(field)) {
            ;(updated as any)[field] = parseNum(value)
          } else {
            ;(updated as any)[field] = value
          }
          return recalcAgingRow(updated)
        }),
      }
    })
    persistGroups()
  }

  // ─── Aging Config Change Sync (Req 9.2, 9.3) ─────────────────────────

  /**
   * 监听 aging-config:changed 事件：
   * - 已有段保留 lossRate/bookBalance
   * - 新增段零初始化
   * - 移除段标记归档
   */
  function onAgingConfigChanged(): void {
    if (agingGroups.value.length === 0) return

    const newSegments = segments.value
    if (!newSegments || newSegments.length === 0) return

    agingGroups.value = agingGroups.value.map(g => ({
      ...g,
      rows: syncAgingGroupRows(g.rows, newSegments),
    }))

    persistGroups()
  }

  window.addEventListener('aging-config:changed', onAgingConfigChanged)

  onUnmounted(() => {
    window.removeEventListener('aging-config:changed', onAgingConfigChanged)
  })

  // ─── Audit Notes ─────────────────────────────────────────────────────

  const auditNotes = ref<{ explanation: string; conclusion: string }>({
    explanation: '',
    conclusion: '',
  })

  watch(
    () => allResponses.value.get('D6-8-note-explanation')?.remark,
    (v) => { if (v) auditNotes.value.explanation = v },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get('D6-8-note-conclusion')?.remark,
    (v) => { if (v) auditNotes.value.conclusion = v },
    { immediate: true },
  )
  watch(
    () => auditNotes.value.explanation,
    (v) => debouncedSave('D6-8-note-explanation', { remark: v }),
  )
  watch(
    () => auditNotes.value.conclusion,
    (v) => debouncedSave('D6-8-note-conclusion', { remark: v }),
  )

  // ─── Return ──────────────────────────────────────────────────────────

  return {
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
    grandTotal,
    diffAlert,
    auditNotes,
  }
}

export default useD6EclCalculation
