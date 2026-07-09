/**
 * useH2Disclosure — 附注 composable
 *
 * variant参数（listed/soe）双版本共用
 * 多子节结构 + 跨sheet自动取数 + 动态行
 * EventBus 'disclosure:note-text-updated'
 *
 * Spec: .kiro/specs/h2-construction-in-progress/
 * Task: 3.16
 * Requirements: 14.6
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcSubtotal } from './useH2FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type DisclosureVariant = 'listed' | 'soe'

export interface DisclosureSection {
  id: string
  title: string
  /** 自动取数字段（从crossSheet取） */
  autoFields: DisclosureAutoField[]
  /** 动态行数据 */
  rows: DisclosureRow[]
  /** 文本描述区 */
  noteText: string
}

export interface DisclosureAutoField {
  label: string
  key: string
  value: number
  source: string  // 数据来源描述
}

export interface DisclosureRow {
  rowId: string
  name: string
  beginBalance: number
  increase: number
  decrease: number
  transfer: number
  endBalance: number
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const VARIANT_KEY = 'H2-disclosure-variant'
const SECTIONS_KEY = 'H2-disclosure-sections'
const NOTE_KEY = 'H2-disclosure-note'

/** 上市公司版本子节 */
const LISTED_SECTIONS = [
  '在建工程期初期末变动',
  '重要在建工程项目',
  '借款费用资本化',
  '工程物资',
  '减值准备',
]

/** 国企版本子节 */
const SOE_SECTIONS = [
  '在建工程期初期末变动',
  '重要在建工程项目',
  '借款费用资本化',
  '超预算工程说明',
  '减值准备',
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2Disclosure(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  /** 从useH2CrossSheet.disclosureAutoFill取数 */
  disclosureAutoFill?: ComputedRef<Record<string, number>>
  /** variant参数（从projectContext.business_category推断） */
  variant?: Ref<DisclosureVariant>
  onSave?: (itemId: string, value: any) => void
  onPublishEvent?: (event: string, payload: any) => void
}) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const currentVariant = ref<DisclosureVariant>(options.variant?.value ?? 'listed')
  const sections = ref<DisclosureSection[]>([])
  const auditNote = ref('')

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = options.allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return null }
  }

  function _getString(itemId: string): string {
    const item = options.allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  /** 根据variant创建默认sections结构 */
  function _createDefaultSections(variant: DisclosureVariant): DisclosureSection[] {
    const titles = variant === 'listed' ? LISTED_SECTIONS : SOE_SECTIONS
    return titles.map((title, i) => ({
      id: `section-${i}`,
      title,
      autoFields: _buildAutoFields(title),
      rows: [],
      noteText: '',
    }))
  }

  /** 为每个section构建自动取数字段 */
  function _buildAutoFields(sectionTitle: string): DisclosureAutoField[] {
    const auto = options.disclosureAutoFill?.value ?? {}
    switch (sectionTitle) {
      case '在建工程期初期末变动':
        return [
          { label: '期初余额', key: 'disc_cip_begin', value: auto['disc_cip_begin'] ?? 0, source: 'H2-1审定表' },
          { label: '本期增加', key: 'disc_increase', value: auto['disc_increase'] ?? 0, source: 'H2-1审定表' },
          { label: '本期减少', key: 'disc_decrease', value: auto['disc_decrease'] ?? 0, source: 'H2-1审定表' },
          { label: '本期转固', key: 'disc_transfer', value: auto['disc_transfer'] ?? 0, source: 'H2-1审定表' },
          { label: '期末余额', key: 'disc_cip_end', value: auto['disc_cip_end'] ?? 0, source: 'H2-1审定表' },
        ]
      case '重要在建工程项目':
        return [
          { label: '项目数', key: 'disc_project_count', value: auto['disc_project_count'] ?? 0, source: 'H2-1审定表' },
        ]
      case '借款费用资本化':
        return [
          { label: '利息资本化金额', key: 'disc_interest_cap', value: auto['disc_interest_cap'] ?? 0, source: 'H2-10/11利息资本化' },
        ]
      case '减值准备':
        return [
          { label: '已计提减值', key: 'disc_impairment', value: auto['disc_impairment'] ?? 0, source: 'H2-1审定表' },
        ]
      default:
        return []
    }
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  function initFromAllResponses(): void {
    const variantStr = _getString(VARIANT_KEY)
    if (variantStr === 'soe' || variantStr === 'listed') {
      currentVariant.value = variantStr
    } else if (options.variant?.value) {
      currentVariant.value = options.variant.value
    }

    const savedSections = _getJson(SECTIONS_KEY)
    if (Array.isArray(savedSections) && savedSections.length > 0) {
      sections.value = savedSections.map((s: any, i: number) => ({
        id: s.id ?? `section-${i}`,
        title: s.title ?? '',
        autoFields: _buildAutoFields(s.title ?? ''),
        rows: Array.isArray(s.rows) ? s.rows.map((r: any) => ({
          rowId: r.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
          name: r.name ?? '',
          beginBalance: Number(r.beginBalance) || 0,
          increase: Number(r.increase) || 0,
          decrease: Number(r.decrease) || 0,
          transfer: Number(r.transfer) || 0,
          endBalance: Number(r.endBalance) || 0,
          remark: r.remark ?? '',
        })) : [],
        noteText: s.noteText ?? '',
      }))
    } else {
      sections.value = _createDefaultSections(currentVariant.value)
    }

    auditNote.value = _getString(NOTE_KEY)
  }

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  // 当crossSheet自动取数变化时更新autoFields
  if (options.disclosureAutoFill) {
    watch(options.disclosureAutoFill, () => {
      for (const section of sections.value) {
        section.autoFields = _buildAutoFields(section.title)
      }
    })
  }

  // ─── Computed ──────────────────────────────────────────────────────────────

  /** 子节标题列表 */
  const sectionTitles: ComputedRef<string[]> = computed(() =>
    sections.value.map(s => s.title),
  )

  /** 各section动态行合计 */
  const sectionTotals: ComputedRef<Record<string, number>> = computed(() => {
    const totals: Record<string, number> = {}
    for (const section of sections.value) {
      totals[section.id] = calcSubtotal(section.rows.map(r => r.endBalance))
    }
    return totals
  })

  // ─── Actions ───────────────────────────────────────────────────────────────

  function setVariant(v: DisclosureVariant): void {
    if (options.isReadonly.value) return
    currentVariant.value = v
    // 重建sections（保留已有数据）
    const defaultSections = _createDefaultSections(v)
    const merged = defaultSections.map(ds => {
      const existing = sections.value.find(s => s.title === ds.title)
      return existing ? { ...existing, autoFields: ds.autoFields } : ds
    })
    sections.value = merged
    options.onSave?.(VARIANT_KEY, v)
    _persistSections()
  }

  function updateSectionNote(sectionId: string, text: string): void {
    if (options.isReadonly.value) return
    const section = sections.value.find(s => s.id === sectionId)
    if (section) {
      section.noteText = text
      _persistSections()
      // 发布附注文本更新事件
      options.onPublishEvent?.('disclosure:note-text-updated', {
        wpCode: 'H2',
        sectionId,
        text,
      })
    }
  }

  function addRow(sectionId: string, name: string): void {
    if (options.isReadonly.value) return
    const section = sections.value.find(s => s.id === sectionId)
    if (!section) return
    section.rows.push({
      rowId: `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      name: name || '',
      beginBalance: 0,
      increase: 0,
      decrease: 0,
      transfer: 0,
      endBalance: 0,
      remark: '',
    })
    _persistSections()
  }

  function removeRow(sectionId: string, rowId: string): void {
    if (options.isReadonly.value) return
    const section = sections.value.find(s => s.id === sectionId)
    if (!section) return
    const idx = section.rows.findIndex(r => r.rowId === rowId)
    if (idx !== -1) {
      section.rows.splice(idx, 1)
      _persistSections()
    }
  }

  function updateRow(sectionId: string, rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return
    const section = sections.value.find(s => s.id === sectionId)
    if (!section) return
    const row = section.rows.find(r => r.rowId === rowId)
    if (!row) return

    const numFields = ['beginBalance', 'increase', 'decrease', 'transfer', 'endBalance']
    if (numFields.includes(field)) {
      ;(row as any)[field] = Number(value) || 0
    } else {
      ;(row as any)[field] = String(value ?? '')
    }
    _persistSections()
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options.onSave?.(NOTE_KEY, note)
  }

  function _persistSections(): void {
    if (!options.onSave) return
    options.onSave(SECTIONS_KEY, sections.value.map(s => ({
      id: s.id,
      title: s.title,
      rows: s.rows.map(r => ({
        rowId: r.rowId, name: r.name, beginBalance: r.beginBalance,
        increase: r.increase, decrease: r.decrease,
        transfer: r.transfer, endBalance: r.endBalance,
        remark: r.remark,
      })),
      noteText: s.noteText,
    })))
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    currentVariant, sections, auditNote,
    sectionTitles, sectionTotals,
    setVariant, updateSectionNote,
    addRow, removeRow, updateRow,
    saveNote, initFromAllResponses,
  }
}

export default useH2Disclosure
