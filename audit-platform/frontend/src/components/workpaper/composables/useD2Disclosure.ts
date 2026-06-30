/**
 * useD2Disclosure — 附注披露4版本核心逻辑 composable
 *
 * Spec: .kiro/specs/d2-accounts-receivable-refactor/
 * Task: 17.1
 *
 * 职责：
 * - DisclosureVersion 类型（4种版本切换）
 * - DisclosureSection / DisclosureRow 类型
 * - activeVersion ref, switchVersion(version)
 * - sections computed（按版本动态生成）
 * - Ratio 自动计算（amount/total×100%），net amount（amount-badDebt）
 * - Cross-sheet refs from D2-1 adjudication + D2-3 bad debt
 * - inconsistencyWarnings computed
 * - updateCell + debounce save
 *
 * Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum } from './useD2FormulaEngine'
import type { UseD2BaseOptions } from './useD2Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

export type DisclosureVersion = 'listed-d2-1' | 'soe-d2-1' | 'listed-aging' | 'soe-aging'

export interface DisclosureRow {
  rowId: string
  label: string                // 行标签
  amount: number               // 金额
  badDebt: number              // 坏账准备
  netAmount: number            // 账面价值 = amount - badDebt
  ratio: number                // 占比 = amount / total × 100%
  remark: string               // 备注
  isEditable: boolean          // 是否可编辑（合计行不可）
}

export interface DisclosureSection {
  sectionId: string
  title: string                // 区块标题
  rows: DisclosureRow[]
  totalRow: DisclosureRow      // 合计行
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_PREFIX = 'D2-disclosure'

/** 上市公司D2-1版本区块配置 */
const LISTED_D2_1_SECTIONS = [
  { sectionId: 'by-category', title: '按类别披露' },
  { sectionId: 'by-bad-debt', title: '按坏账计提方法披露' },
  { sectionId: 'top5', title: '按欠款方归集的期末余额前五名' },
]

/** 国企D2-1版本区块配置 */
const SOE_D2_1_SECTIONS = [
  { sectionId: 'by-category', title: '按类别披露' },
  { sectionId: 'by-bad-debt', title: '按坏账计提方法披露' },
  { sectionId: 'by-nature', title: '按款项性质披露' },
  { sectionId: 'top5', title: '按欠款方归集的期末余额前五名' },
]

/** 上市公司账龄版本区块 */
const LISTED_AGING_SECTIONS = [
  { sectionId: 'aging-detail', title: '账龄分析' },
]

/** 国企账龄版本区块 */
const SOE_AGING_SECTIONS = [
  { sectionId: 'aging-detail', title: '账龄分析' },
  { sectionId: 'aging-comparison', title: '账龄与上年比较' },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `dis-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function createRow(label: string, isEditable = true): DisclosureRow {
  return {
    rowId: generateRowId(),
    label,
    amount: 0,
    badDebt: 0,
    netAmount: 0,
    ratio: 0,
    remark: '',
    isEditable,
  }
}

function recalcRow(row: DisclosureRow, totalAmount: number): DisclosureRow {
  row.netAmount = row.amount - row.badDebt
  row.ratio = totalAmount === 0 ? 0 : (row.amount / totalAmount) * 100
  return row
}

function buildTotalRow(rows: DisclosureRow[]): DisclosureRow {
  const total: DisclosureRow = {
    rowId: '__total__',
    label: '合计',
    amount: rows.reduce((s, r) => s + r.amount, 0),
    badDebt: rows.reduce((s, r) => s + r.badDebt, 0),
    netAmount: 0,
    ratio: 100,
    remark: '',
    isEditable: false,
  }
  total.netAmount = total.amount - total.badDebt
  return total
}

function getSectionConfig(version: DisclosureVersion): Array<{ sectionId: string; title: string }> {
  switch (version) {
    case 'listed-d2-1': return LISTED_D2_1_SECTIONS
    case 'soe-d2-1': return SOE_D2_1_SECTIONS
    case 'listed-aging': return LISTED_AGING_SECTIONS
    case 'soe-aging': return SOE_AGING_SECTIONS
  }
}

function parseDisclosureData(jsonStr: string | null | undefined): Map<string, DisclosureRow[]> {
  if (!jsonStr) return new Map()
  try {
    const parsed = JSON.parse(jsonStr)
    if (typeof parsed !== 'object' || parsed === null) return new Map()
    const map = new Map<string, DisclosureRow[]>()
    for (const [key, val] of Object.entries(parsed)) {
      if (Array.isArray(val)) {
        map.set(key, (val as any[]).map((raw: any) => ({
          rowId: raw.rowId || generateRowId(),
          label: raw.label || '',
          amount: parseNum(raw.amount),
          badDebt: parseNum(raw.badDebt),
          netAmount: parseNum(raw.netAmount),
          ratio: parseNum(raw.ratio),
          remark: raw.remark || '',
          isEditable: raw.isEditable !== false,
        })))
      }
    }
    return map
  } catch {
    return new Map()
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2Disclosure(options: UseD2BaseOptions) {
  const { allResponses, isReadonly } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const activeVersion = ref<DisclosureVersion>('listed-d2-1')
  const sectionData = ref<Map<string, DisclosureRow[]>>(new Map())
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Load from allResponses ────────────────────────────────────────────

  function getStorageKey(): string {
    return `${STORAGE_PREFIX}-${activeVersion.value}`
  }

  function loadData(): void {
    const versionResp = allResponses.value.get(`${STORAGE_PREFIX}-active-version`)
    if (versionResp?.remark) {
      const v = versionResp.remark as DisclosureVersion
      if (['listed-d2-1', 'soe-d2-1', 'listed-aging', 'soe-aging'].includes(v)) {
        activeVersion.value = v
      }
    }

    const dataResp = allResponses.value.get(getStorageKey())
    sectionData.value = parseDisclosureData(dataResp?.remark)
  }

  watch(
    () => [
      allResponses.value.get(`${STORAGE_PREFIX}-active-version`)?.remark,
      allResponses.value.get(getStorageKey())?.remark,
    ],
    () => {
      if (sectionData.value.size === 0) {
        loadData()
      }
    },
    { immediate: true }
  )

  // ─── Switch Version ────────────────────────────────────────────────────

  function switchVersion(version: DisclosureVersion): void {
    if (isReadonly.value) return
    activeVersion.value = version

    // Persist active version
    allResponses.value.set(`${STORAGE_PREFIX}-active-version`, {
      item_id: `${STORAGE_PREFIX}-active-version`,
      conclusion: null,
      remark: version,
    })

    // Load data for new version
    const dataResp = allResponses.value.get(getStorageKey())
    sectionData.value = parseDisclosureData(dataResp?.remark)

    debounceSave()
  }

  // ─── Sections Computed ─────────────────────────────────────────────────

  /**
   * 按当前版本动态生成 sections
   * 每个 section 包含行数据 + 合计行 + ratio自动计算
   */
  const sections: ComputedRef<DisclosureSection[]> = computed(() => {
    const config = getSectionConfig(activeVersion.value)
    return config.map(cfg => {
      const rows = sectionData.value.get(cfg.sectionId) || [createRow('')]
      const totalRow = buildTotalRow(rows)

      // Recalc ratios
      for (const row of rows) {
        recalcRow(row, totalRow.amount)
      }

      return {
        sectionId: cfg.sectionId,
        title: cfg.title,
        rows,
        totalRow,
      }
    })
  })

  // ─── Cross-Sheet References ────────────────────────────────────────────

  /**
   * 从D2-1审定表和D2-3坏账准备读取参考数据
   */
  const crossSheetRefs = computed(() => {
    // D2-1 审定总额
    const adjTotal = parseNum(allResponses.value.get('D2-adj-total-audited')?.remark)

    // D2-3 坏账准备总额
    let bdTotal = 0
    for (const key of ['D2-bd-individual-rows', 'D2-bd-aging-rows', 'D2-bd-customer-rows']) {
      const json = allResponses.value.get(key)?.remark
      if (!json) continue
      try {
        const rows = JSON.parse(json)
        if (Array.isArray(rows)) {
          const fixedRow = rows.find((r: any) => r.isFixed)
          if (fixedRow) {
            bdTotal += parseNum(fixedRow.currentAudited)
          }
        }
      } catch { /* silent */ }
    }

    return { adjTotal, bdTotal }
  })

  // ─── Inconsistency Warnings ────────────────────────────────────────────

  /**
   * 不一致性警告：披露表金额 vs 审定表/坏账表
   */
  const inconsistencyWarnings: ComputedRef<string[]> = computed(() => {
    const warnings: string[] = []
    const refs = crossSheetRefs.value

    // Check if total amount in first section matches adjudication total
    if (sections.value.length > 0) {
      const firstSection = sections.value[0]
      const disclosureTotal = firstSection.totalRow.amount
      if (refs.adjTotal > 0 && Math.abs(disclosureTotal - refs.adjTotal) > 0.005) {
        warnings.push(
          `附注披露合计(${disclosureTotal.toFixed(2)})与D2-1审定表(${refs.adjTotal.toFixed(2)})不一致`
        )
      }

      const disclosureBdTotal = firstSection.totalRow.badDebt
      if (refs.bdTotal > 0 && Math.abs(disclosureBdTotal - refs.bdTotal) > 0.005) {
        warnings.push(
          `附注坏账合计(${disclosureBdTotal.toFixed(2)})与D2-3坏账表(${refs.bdTotal.toFixed(2)})不一致`
        )
      }
    }

    return warnings
  })

  // ─── Update Cell ───────────────────────────────────────────────────────

  function updateCell(sectionId: string, rowId: string, field: string, value: any): void {
    if (isReadonly.value) return

    const rows = sectionData.value.get(sectionId)
    if (!rows) return

    const row = rows.find(r => r.rowId === rowId)
    if (!row || !row.isEditable) return

    const key = field as keyof DisclosureRow
    if (key === 'rowId' || key === 'isEditable' || key === 'netAmount' || key === 'ratio') return

    if (key === 'amount' || key === 'badDebt') {
      ;(row as any)[key] = parseNum(value)
      // Recalc
      const totalAmount = rows.reduce((s, r) => s + r.amount, 0)
      recalcRow(row, totalAmount)
    } else if (key === 'label' || key === 'remark') {
      ;(row as any)[key] = String(value)
    }

    debounceSave()
  }

  /**
   * 添加行到指定 section
   */
  function addRow(sectionId: string): void {
    if (isReadonly.value) return
    let rows = sectionData.value.get(sectionId)
    if (!rows) {
      rows = []
      sectionData.value.set(sectionId, rows)
    }
    rows.push(createRow(''))
    debounceSave()
  }

  /**
   * 删除行
   */
  function removeRow(sectionId: string, rowId: string): void {
    if (isReadonly.value) return
    const rows = sectionData.value.get(sectionId)
    if (!rows) return
    const idx = rows.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    if (!rows[idx].isEditable) return
    rows.splice(idx, 1)
    debounceSave()
  }

  // ─── Serialization & Save ──────────────────────────────────────────────

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function flushSave(): void {
    // Serialize sectionData map to object
    const dataObj: Record<string, DisclosureRow[]> = {}
    for (const [key, rows] of sectionData.value.entries()) {
      dataObj[key] = rows
    }
    const json = JSON.stringify(dataObj)

    const items = [
      { item_id: `${STORAGE_PREFIX}-active-version`, conclusion: null, remark: activeVersion.value },
      { item_id: getStorageKey(), conclusion: null, remark: json },
    ]
    for (const item of items) {
      allResponses.value.set(item.item_id, item)
    }
    dispatchSaveEvent(items)
  }

  function dispatchSaveEvent(items: any[]): void {
    try {
      window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items } }))
    } catch {
      // silent
    }
  }

  // ─── Lifecycle ─────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    activeVersion,
    sections,
    crossSheetRefs,
    inconsistencyWarnings,
    switchVersion,
    updateCell,
    addRow,
    removeRow,
  }
}

export default useD2Disclosure
