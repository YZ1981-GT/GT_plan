/**
 * useH1Disclosure — 附注披露 composable（历史实现）
 *
 * @deprecated 上市/国企附注 UI 已分别迁至 H1TabDisclosureListed / H1TabDisclosureSoe
 * 与 h1ListedDisclosureModel / h1SoeDisclosureModel。请勿在新代码中调用本 composable。
 * 子节常量请从 `h1DisclosureSections` 导入。
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import { calcSubtotal } from './useH1FormulaEngine'
import {
  LISTED_SECTIONS,
  SOE_SECTIONS,
  type DisclosureVariant,
  type DisclosureSection,
} from './h1DisclosureSections'

export type { DisclosureVariant, DisclosureSection }
export { LISTED_SECTIONS, SOE_SECTIONS }

/** 附注矩阵行（历史） */
export interface DisclosureMatrixRow {
  rowId: string
  category: string
  beginBalance: number
  increase: number
  decrease: number
  endBalance: number
  isAutoFilled: boolean
}

/** 附注动态行（历史） */
export interface DisclosureDynamicRow {
  rowId: string
  name: string
  amount: number
  description: string
  remark: string
}

const ITEM_PREFIX_LISTED = 'H1-disc-listed'
const ITEM_PREFIX_SOE = 'H1-disc-soe'

/** @deprecated 见文件头说明 */
export function useH1Disclosure(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    variant?: Ref<DisclosureVariant>
    applicableStandards?: Ref<string[]>
    crossSheetAutoFill?: Ref<Record<string, number>>
    onSave?: (itemId: string, value: any) => void
    onPublishEvent?: (event: string, payload: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const variant = computed<DisclosureVariant>(() => options?.variant?.value ?? 'listed')
  const itemPrefix = computed(() => variant.value === 'listed' ? ITEM_PREFIX_LISTED : ITEM_PREFIX_SOE)

  /** 子节1: 固定资产原值矩阵（3层：原值/折旧/减值） */
  const costMatrixRows = ref<DisclosureMatrixRow[]>([])
  const depMatrixRows = ref<DisclosureMatrixRow[]>([])
  const impairmentMatrixRows = ref<DisclosureMatrixRow[]>([])

  /** 子节2~6: 动态行（SOE + 历史 listed 兼容键） */
  const sectionRows = ref<Record<string, DisclosureDynamicRow[]>>({
    idle: [],
    finance_lease_in: [],
    operating_lease_out: [],
    restricted: [],
    fully_depreciated: [],
    clearing: [],
  })

  /** 各子节说明文本 */
  const sectionNotes = ref<Record<string, string>>({})

  // ─── Computed: 是否显示 ────────────────────────────────────────────────────

  const isVisible = computed(() => {
    const standards = options?.applicableStandards?.value ?? []
    if (variant.value === 'listed') {
      return standards.some((s) => s.startsWith('listed_'))
    }
    return standards.some((s) => s.startsWith('soe_'))
  })

  const sections = computed(() =>
    variant.value === 'listed' ? LISTED_SECTIONS : SOE_SECTIONS,
  )

  // ─── Computed: 跨sheet自动取数 ────────────────────────────────────────────

  const autoFilledData = computed(() => options?.crossSheetAutoFill?.value ?? {})

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const costTotal = computed(() => ({
    beginBalance: calcSubtotal(costMatrixRows.value.map((r) => r.beginBalance)),
    increase: calcSubtotal(costMatrixRows.value.map((r) => r.increase)),
    decrease: calcSubtotal(costMatrixRows.value.map((r) => r.decrease)),
    endBalance: calcSubtotal(costMatrixRows.value.map((r) => r.endBalance)),
  }))

  const depTotal = computed(() => ({
    beginBalance: calcSubtotal(depMatrixRows.value.map((r) => r.beginBalance)),
    increase: calcSubtotal(depMatrixRows.value.map((r) => r.increase)),
    decrease: calcSubtotal(depMatrixRows.value.map((r) => r.decrease)),
    endBalance: calcSubtotal(depMatrixRows.value.map((r) => r.endBalance)),
  }))

  const netValueTotal = computed(() =>
    costTotal.value.endBalance - depTotal.value.endBalance
    - calcSubtotal(impairmentMatrixRows.value.map((r) => r.endBalance)),
  )

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadData(): void {
    const prefix = itemPrefix.value

    // 原值矩阵
    costMatrixRows.value = _loadMatrixRows(`${prefix}-cost-matrix`)
    depMatrixRows.value = _loadMatrixRows(`${prefix}-dep-matrix`)
    impairmentMatrixRows.value = _loadMatrixRows(`${prefix}-impairment-matrix`)

    // 动态行
    for (const key of Object.keys(sectionRows.value)) {
      const item = allResponses.value.get(`${prefix}-${key}-rows`)
      if (item?.remark) {
        try {
          const parsed = JSON.parse(item.remark)
          sectionRows.value[key] = Array.isArray(parsed) ? parsed : []
        } catch { sectionRows.value[key] = [] }
      }
    }

    // 说明文本
    for (const sect of sections.value) {
      const noteItem = allResponses.value.get(`${prefix}-${sect.key}-note`)
      sectionNotes.value[sect.key] = (noteItem?.remark ?? '') as string
    }
  }

  function _loadMatrixRows(itemId: string): DisclosureMatrixRow[] {
    const item = allResponses.value.get(itemId)
    if (!item?.remark) return []
    try {
      const parsed = JSON.parse(item.remark)
      return Array.isArray(parsed) ? parsed : []
    } catch { return [] }
  }

  // ─── CRUD: 动态行 ─────────────────────────────────────────────────────────

  function addDynamicRow(sectionKey: string, name = ''): void {
    const rows = sectionRows.value[sectionKey]
    if (!rows) return
    rows.push({
      rowId: `disc-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      name,
      amount: 0,
      description: '',
      remark: '',
    })
    _persistSection(sectionKey)
  }

  function removeDynamicRow(sectionKey: string, rowId: string): void {
    const rows = sectionRows.value[sectionKey]
    if (!rows) return
    const idx = rows.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      rows.splice(idx, 1)
      _persistSection(sectionKey)
    }
  }

  function updateDynamicRow(sectionKey: string, rowId: string, field: keyof DisclosureDynamicRow, value: any): void {
    const rows = sectionRows.value[sectionKey]
    if (!rows) return
    const row = rows.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _persistSection(sectionKey)
  }

  // ─── Update: 矩阵行 ───────────────────────────────────────────────────────

  function updateMatrixCell(
    layer: 'cost' | 'dep' | 'impairment',
    rowId: string,
    field: keyof DisclosureMatrixRow,
    value: any,
  ): void {
    const target = layer === 'cost' ? costMatrixRows : layer === 'dep' ? depMatrixRows : impairmentMatrixRows
    const row = target.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _persistMatrix(layer)
  }

  // ─── Section Note ──────────────────────────────────────────────────────────

  function saveSectionNote(sectionKey: string, note: string): void {
    sectionNotes.value[sectionKey] = note
    const prefix = itemPrefix.value
    options?.onSave?.(`${prefix}-${sectionKey}-note`, note)

    // 发布EventBus
    options?.onPublishEvent?.('disclosure:note-text-updated', {
      wp_code: 'H1',
      variant: variant.value,
      section: sectionKey,
      text: note,
    })
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persistSection(sectionKey: string): void {
    const prefix = itemPrefix.value
    options?.onSave?.(`${prefix}-${sectionKey}-rows`, sectionRows.value[sectionKey])
  }

  function _persistMatrix(layer: string): void {
    const prefix = itemPrefix.value
    const target = layer === 'cost' ? costMatrixRows : layer === 'dep' ? depMatrixRows : impairmentMatrixRows
    options?.onSave?.(`${prefix}-${layer}-matrix`, target.value)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadData(), { immediate: true })
  watch(variant, () => _loadData())

  // ─── Return ────────────────────────────────────────────────────────────────

  /** @deprecated 上市 UI 已迁至 h1ListedDisclosureModel；仅 SOE / 历史测试保留 */
  return {
    // State
    variant,
    costMatrixRows,
    depMatrixRows,
    impairmentMatrixRows,
    sectionRows,
    sectionNotes,
    // Computed
    isVisible,
    sections,
    autoFilledData,
    costTotal,
    depTotal,
    netValueTotal,
    // Actions
    addDynamicRow,
    removeDynamicRow,
    updateDynamicRow,
    updateMatrixCell,
    saveSectionNote,
  }
}

export default useH1Disclosure
