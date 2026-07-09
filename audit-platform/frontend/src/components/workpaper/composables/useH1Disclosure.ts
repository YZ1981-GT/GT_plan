/**
 * useH1Disclosure — 附注披露 composable
 *
 * variant参数（listed/soe）双版本共用
 * 多子节结构 + 跨sheet自动取数 + 动态行
 * applicable_standards判断显隐
 * EventBus 'disclosure:note-text-updated'
 *
 * Spec: .kiro/specs/h1-fixed-assets/
 * Task: 3.17
 * Requirements: 16.1-16.10
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import { calcSubtotal } from './useH1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type DisclosureVariant = 'listed' | 'soe'

/** 附注子节定义 */
export interface DisclosureSection {
  key: string
  title: string
  hasTable: boolean             // 是否含表格数据
  hasDynamicRows: boolean       // 是否支持动态行
}

/** 附注矩阵行（子节1: 固定资产情况） */
export interface DisclosureMatrixRow {
  rowId: string
  category: string              // 资产分类
  beginBalance: number          // 期初余额
  increase: number              // 本期增加
  decrease: number              // 本期减少
  endBalance: number            // 期末余额
  isAutoFilled: boolean         // 是否跨sheet自动取数
}

/** 附注动态行（子节2~6通用） */
export interface DisclosureDynamicRow {
  rowId: string
  name: string                  // 资产名称/项目名
  amount: number                // 金额
  description: string           // 说明
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX_LISTED = 'H1-disc-listed'
const ITEM_PREFIX_SOE = 'H1-disc-soe'

/** 附注子节定义（上市版6子节） */
export const LISTED_SECTIONS: DisclosureSection[] = [
  { key: 'overview', title: '(1) 固定资产情况', hasTable: true, hasDynamicRows: false },
  { key: 'idle', title: '(2) 暂时闲置的固定资产', hasTable: true, hasDynamicRows: true },
  { key: 'finance_lease_in', title: '(3) 通过融资租赁租入的固定资产', hasTable: true, hasDynamicRows: true },
  { key: 'operating_lease_out', title: '(4) 通过经营租赁租出的固定资产', hasTable: true, hasDynamicRows: true },
  { key: 'restricted', title: '(5) 没有办妥产权证书的固定资产/抵押担保受限资产', hasTable: true, hasDynamicRows: true },
  { key: 'fully_depreciated', title: '(6) 已提足折旧仍继续使用的固定资产', hasTable: true, hasDynamicRows: true },
]

/** 附注子节定义（国企版） */
export const SOE_SECTIONS: DisclosureSection[] = [
  { key: 'overview', title: '(一) 固定资产情况', hasTable: true, hasDynamicRows: false },
  { key: 'idle', title: '(二) 暂时闲置的固定资产', hasTable: true, hasDynamicRows: true },
  { key: 'finance_lease_in', title: '(三) 通过融资租赁租入的固定资产', hasTable: true, hasDynamicRows: true },
  { key: 'operating_lease_out', title: '(四) 通过经营租赁租出的固定资产', hasTable: true, hasDynamicRows: true },
  { key: 'restricted', title: '(五) 产权受限/担保抵押的固定资产', hasTable: true, hasDynamicRows: true },
  { key: 'fully_depreciated', title: '(六) 已提足折旧仍继续使用的固定资产', hasTable: true, hasDynamicRows: true },
]

// ─── Composable ──────────────────────────────────────────────────────────────

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

  /** 子节2~6: 动态行 */
  const sectionRows = ref<Record<string, DisclosureDynamicRow[]>>({
    idle: [],
    finance_lease_in: [],
    operating_lease_out: [],
    restricted: [],
    fully_depreciated: [],
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

  function addDynamicRow(sectionKey: string, name: string): void {
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
