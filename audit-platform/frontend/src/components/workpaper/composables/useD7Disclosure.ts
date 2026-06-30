/**
 * useD7Disclosure — 附注披露（上市3子节 / 国企2子节）
 *
 * 上市公司版3子节：
 *   (1) 按性质分类（固定行+减：非流动负债+合计，从crossSheet.adjudicationForDisclosure取数）
 *   (2) 账龄超过1年的重要合同负债（动态行+合计，从D7-5取数）
 *   (3) 本期合同负债账面价值的重大变动（动态行+合计）
 *
 * 国企版2子节：
 *   (1) 按性质分类（固定行+合计）
 *   (2) 本期账面价值的重大变动（动态行+合计）
 *
 * Spec: .kiro/specs/d7-contract-liabilities/
 * Task: 13.1
 * Requirements: 13.1-13.8, 14.1-14.6, 15.1-15.6
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useD7FormulaEngine'
import type { ChecklistResponse } from './useD7FormData'
import type useD7CrossSheet from './useD7CrossSheet'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface DisclosureRow {
  rowId: string
  label: string
  prior: number
  current: number
  [key: string]: any
}

export interface DisclosureSection {
  sectionKey: string
  label: string
  rows: DisclosureRow[]
  totalRow?: DisclosureRow
  isDynamic: boolean
}

export interface UseD7DisclosureOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  crossSheet: ReturnType<typeof useD7CrossSheet>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `disc-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

function safeParseArray(jsonStr: string | null | undefined): any[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function buildTotalRow(rows: DisclosureRow[], label: string): DisclosureRow {
  return {
    rowId: `__total_${label}__`,
    label,
    prior: calcSubtotal(rows.map(r => r.prior)),
    current: calcSubtotal(rows.map(r => r.current)),
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD7Disclosure(options: UseD7DisclosureOptions) {
  const { allResponses, crossSheet, debouncedSave } = options

  // ─── Variant (上市/国企) ──────────────────────────────────────────────

  const activeVariant = ref<'listed' | 'soe'>('listed')

  const showListed: ComputedRef<boolean> = computed(() => {
    const standards = allResponses.value.get('applicable_standards')?.remark || ''
    return !standards.includes('仅国企')
  })

  const showSoe: ComputedRef<boolean> = computed(() => {
    const standards = allResponses.value.get('applicable_standards')?.remark || ''
    return standards.includes('国企') || standards.includes('SOE')
  })

  // ─── Listed Section 1: 按性质分类 (固定行, from crossSheet) ──────────

  const listedSection1: ComputedRef<DisclosureSection> = computed(() => {
    const discData = crossSheet.adjudicationForDisclosure.value

    const natureRows: DisclosureRow[] = discData.natureRows.map((r: any, idx: number) => ({
      rowId: `listed-s1-${idx}`,
      label: r.label,
      prior: r.prior,
      current: r.current,
    }))

    // 减：非流动负债扣减行
    const deductionRow: DisclosureRow = {
      rowId: 'listed-s1-deduction',
      label: '减：计入其他非流动负债的合同负债',
      prior: discData.nonCurrentDeduction.prior,
      current: discData.nonCurrentDeduction.current,
    }

    // 合同负债合计行
    const totalRow: DisclosureRow = {
      rowId: 'listed-s1-total',
      label: '合计',
      prior: discData.contractLiabilityTotal.prior,
      current: discData.contractLiabilityTotal.current,
    }

    return {
      sectionKey: 'listed-1',
      label: '(一) 按性质分类',
      rows: [...natureRows, deductionRow],
      totalRow,
      isDynamic: false,
    }
  })

  // ─── Listed Section 2: 超1年重要合同负债 (动态行, from D7-5) ─────────

  const listedSection2Rows = ref<DisclosureRow[]>([])

  watch(
    () => allResponses.value.get('D7-note-listed-section2-rows')?.remark,
    (jsonStr) => {
      const parsed = safeParseArray(jsonStr)
      if (parsed.length > 0) {
        listedSection2Rows.value = parsed.map((r: any) => ({
          rowId: r.rowId || generateRowId(),
          label: r.label || r.customerName || '',
          prior: parseNum(r.prior),
          current: parseNum(r.current),
          reason: r.reason || '',
        }))
      } else {
        // Auto-populate from D7-5 rows
        const d75Json = allResponses.value.get('D7-5-rows')?.remark
        const d75Rows = safeParseArray(d75Json)
        listedSection2Rows.value = d75Rows.map((r: any) => ({
          rowId: generateRowId(),
          label: r.customerName || '',
          prior: 0,
          current: parseNum(r.endBalance),
          reason: r.reason || '',
        }))
      }
    },
    { immediate: true },
  )

  const listedSection2: ComputedRef<DisclosureSection> = computed(() => {
    const rows = listedSection2Rows.value
    return {
      sectionKey: 'listed-2',
      label: '(二) 账龄超过1年的重要合同负债',
      rows,
      totalRow: buildTotalRow(rows, '合计'),
      isDynamic: true,
    }
  })

  // ─── Listed Section 3: 本期重大变动 (动态行) ─────────────────────────

  const listedSection3Rows = ref<DisclosureRow[]>([])

  watch(
    () => allResponses.value.get('D7-note-listed-section3-rows')?.remark,
    (jsonStr) => {
      listedSection3Rows.value = safeParseArray(jsonStr).map((r: any) => ({
        rowId: r.rowId || generateRowId(),
        label: r.label || '',
        prior: parseNum(r.prior),
        current: parseNum(r.current),
      }))
    },
    { immediate: true },
  )

  const listedSection3: ComputedRef<DisclosureSection> = computed(() => {
    const rows = listedSection3Rows.value
    return {
      sectionKey: 'listed-3',
      label: '(三) 本期合同负债账面价值的重大变动',
      rows,
      totalRow: buildTotalRow(rows, '合计'),
      isDynamic: true,
    }
  })

  // ─── Listed Sections Combined ────────────────────────────────────────

  const listedSections: ComputedRef<DisclosureSection[]> = computed(() => [
    listedSection1.value,
    listedSection2.value,
    listedSection3.value,
  ])

  // ─── SOE Section 1: 按性质分类 (固定行) ──────────────────────────────

  const soeSection1: ComputedRef<DisclosureSection> = computed(() => {
    const discData = crossSheet.adjudicationForDisclosure.value

    const natureRows: DisclosureRow[] = discData.natureRows.map((r: any, idx: number) => ({
      rowId: `soe-s1-${idx}`,
      label: r.label,
      prior: r.prior,
      current: r.current,
    }))

    const totalRow: DisclosureRow = {
      rowId: 'soe-s1-total',
      label: '合计',
      prior: discData.natureTotals.prior,
      current: discData.natureTotals.current,
    }

    return {
      sectionKey: 'soe-1',
      label: '(一) 按性质分类',
      rows: natureRows,
      totalRow,
      isDynamic: false,
    }
  })

  // ─── SOE Section 2: 本期重大变动 (动态行) ───────────────────────────

  const soeSection2Rows = ref<DisclosureRow[]>([])

  watch(
    () => allResponses.value.get('D7-note-soe-section2-rows')?.remark,
    (jsonStr) => {
      soeSection2Rows.value = safeParseArray(jsonStr).map((r: any) => ({
        rowId: r.rowId || generateRowId(),
        label: r.label || '',
        prior: parseNum(r.prior),
        current: parseNum(r.current),
      }))
    },
    { immediate: true },
  )

  const soeSection2: ComputedRef<DisclosureSection> = computed(() => {
    const rows = soeSection2Rows.value
    return {
      sectionKey: 'soe-2',
      label: '(二) 本期账面价值的重大变动',
      rows,
      totalRow: buildTotalRow(rows, '合计'),
      isDynamic: true,
    }
  })

  // ─── SOE Sections Combined ───────────────────────────────────────────

  const soeSections: ComputedRef<DisclosureSection[]> = computed(() => [
    soeSection1.value,
    soeSection2.value,
  ])

  // ─── Dynamic Row Operations ──────────────────────────────────────────

  function addDynamicRow(sectionKey: string): void {
    const newRow: DisclosureRow = { rowId: generateRowId(), label: '', prior: 0, current: 0 }

    if (sectionKey === 'listed-2') {
      listedSection2Rows.value = [...listedSection2Rows.value, newRow]
      debouncedSave('D7-note-listed-section2-rows', { remark: JSON.stringify(listedSection2Rows.value) })
    } else if (sectionKey === 'listed-3') {
      listedSection3Rows.value = [...listedSection3Rows.value, newRow]
      debouncedSave('D7-note-listed-section3-rows', { remark: JSON.stringify(listedSection3Rows.value) })
    } else if (sectionKey === 'soe-2') {
      soeSection2Rows.value = [...soeSection2Rows.value, newRow]
      debouncedSave('D7-note-soe-section2-rows', { remark: JSON.stringify(soeSection2Rows.value) })
    }
  }

  function removeDynamicRow(sectionKey: string, rowId: string): void {
    if (sectionKey === 'listed-2') {
      listedSection2Rows.value = listedSection2Rows.value.filter(r => r.rowId !== rowId)
      debouncedSave('D7-note-listed-section2-rows', { remark: JSON.stringify(listedSection2Rows.value) })
    } else if (sectionKey === 'listed-3') {
      listedSection3Rows.value = listedSection3Rows.value.filter(r => r.rowId !== rowId)
      debouncedSave('D7-note-listed-section3-rows', { remark: JSON.stringify(listedSection3Rows.value) })
    } else if (sectionKey === 'soe-2') {
      soeSection2Rows.value = soeSection2Rows.value.filter(r => r.rowId !== rowId)
      debouncedSave('D7-note-soe-section2-rows', { remark: JSON.stringify(soeSection2Rows.value) })
    }
  }

  // ─── Note Texts + EventBus ───────────────────────────────────────────

  const NOTE_TEXT_KEYS = [
    'D7-note-listed-text-1',
    'D7-note-listed-text-2',
    'D7-note-listed-text-3',
    'D7-note-soe-text-1',
    'D7-note-soe-text-2',
  ]

  const noteTexts = ref<Record<string, string>>({})

  watch(allResponses, (map) => {
    const texts: Record<string, string> = {}
    for (const key of NOTE_TEXT_KEYS) {
      texts[key] = map.get(key)?.remark || ''
    }
    noteTexts.value = texts
  }, { immediate: true })

  watch(noteTexts, (newTexts, oldTexts) => {
    for (const key of NOTE_TEXT_KEYS) {
      if (newTexts[key] !== (oldTexts?.[key] || '')) {
        debouncedSave(key, { remark: newTexts[key] })
        // Emit EventBus for disclosure note text update
        try {
          window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
            detail: { wpCode: 'D7', section: key, text: newTexts[key] },
          }))
        } catch { /* non-blocking */ }
      }
    }
  }, { deep: true })

  // Listen for external note updates (last-write-wins)
  function _handleNoteSectionUpdated(event: Event): void {
    const detail = (event as CustomEvent).detail
    if (!detail || detail.wpCode !== 'D7') return
    const key = detail.section
    if (NOTE_TEXT_KEYS.includes(key) && detail.text != null) {
      noteTexts.value = { ...noteTexts.value, [key]: detail.text }
    }
  }

  if (typeof window !== 'undefined') {
    window.addEventListener('note:section-updated', _handleNoteSectionUpdated)
  }

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    listedSections,
    soeSections,
    showListed,
    showSoe,
    activeVariant,
    addDynamicRow,
    removeDynamicRow,
    noteTexts,
  }
}

export default useD7Disclosure
