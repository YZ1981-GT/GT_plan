/**
 * useD6EclCalculation — D6-8 ECL减值测算（双组合58公式）
 *
 * 结构：
 *   (一) 单项计提（EclSingleRow[]）
 *   (二) 账龄组合（EclAgingGroup[]，每组合含6账龄段+小计）
 *
 * 公式：
 *   - 应计提③ = 审定余额① × 损失率②
 *   - 差异⑤ = 应计提③ - 账面余额④
 *
 * Spec: .kiro/specs/d6-contract-assets/
 * Task: 11.1
 * Requirements: 13.1-13.12, 27.1, 27.4
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcExpectedProvision,
  calcEclDifference,
  calcSubtotal,
} from './useD6FormulaEngine'
import type { ChecklistResponse } from './useD6FormData'

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
  agingBand: string          // 账龄段
  auditedBalance: number     // 审定账面余额①
  lossRate: number           // 预期信用损失率②
  expectedProvision: number  // 期末应计提③ = ①×②（自动）
  bookBalance: number        // 期末坏账准备账面余额④
  difference: number         // 差异⑤ = ③-④（自动）
}

export interface EclAgingGroup {
  groupId: string
  groupName: string          // 组合名称
  rows: EclAgingRow[]        // 固定6账龄段 + 小计
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
    agingBand: raw.agingBand || '',
    auditedBalance: parseNum(raw.auditedBalance),
    lossRate: parseNum(raw.lossRate),
    expectedProvision: parseNum(raw.expectedProvision),
    bookBalance: parseNum(raw.bookBalance),
    difference: parseNum(raw.difference),
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

function createDefaultAgingRows(): EclAgingRow[] {
  return DEFAULT_AGING_BANDS.map(band => ({
    rowId: generateRowId(),
    agingBand: band,
    auditedBalance: 0,
    lossRate: 0,
    expectedProvision: 0,
    bookBalance: 0,
    difference: 0,
  }))
}

function createEmptyGroup(): EclAgingGroup {
  return {
    groupId: generateGroupId(),
    groupName: '',
    rows: createDefaultAgingRows(),
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD6EclCalculation(options: UseD6EclCalculationOptions) {
  const { allResponses, debouncedSave } = options

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
    agingGroups.value = [...agingGroups.value, createEmptyGroup()]
    persistGroups()
  }

  function removeAgingGroup(groupId: string): void {
    agingGroups.value = agingGroups.value.filter(g => g.groupId !== groupId)
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
    updateAgingCell,
    grandTotal,
    diffAlert,
    auditNotes,
  }
}

export default useD6EclCalculation
