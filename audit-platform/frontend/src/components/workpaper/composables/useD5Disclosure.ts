/**
 * useD5Disclosure — D5 应收款项融资附注披露逻辑 composable
 *
 * Spec: .kiro/specs/d5-receivables-financing/
 * Task: 10.1
 *
 * 职责：
 * - 上市公司版：3子节（分类/减值准备变动/说明）+ 从crossSheet取数 + 动态行(减值)
 * - 国企版：1子节（分类）+ 从crossSheet取数
 * - 实现 impairmentRows（减值准备变动动态行：上年末/计提/转回/核销/期末=公式）
 * - 实现 applicable_standards 适用性判断（listed/soe显示控制）
 * - 实现 activeVariant（el-segmented切换）
 * - 实现 noteTexts 双向绑定 + EventBus disclosure:note-text-updated
 *
 * Requirements: 8.1-8.8
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { calcImpairmentEnd, parseNum, calcSubtotal } from './useD5FormulaEngine'
import type { ChecklistResponse } from './useD5FormData'
import type { D5DisclosureSourceData } from './useD5CrossSheet'
import { eventBus } from '@/utils/eventBus'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface DisclosureRow {
  rowId: string
  label: string
  endAmount: number
  priorAmount: number
}

export interface DisclosureSection {
  sectionKey: string
  label: string
  rows: DisclosureRow[]
  totalRow?: DisclosureRow
}

export interface ImpairmentRow {
  rowId: string
  itemName: string
  priorEnd: number
  provision: number
  reversal: number
  writeOff: number
  endBalance: number  // auto: = priorEnd + provision - reversal - writeOff
}

export type DebouncedSaveFn = (itemId: string, data: Partial<ChecklistResponse>) => void

export interface UseD5DisclosureOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  debouncedSave: DebouncedSaveFn
  isReadonly: Ref<boolean>
  crossSheet: {
    adjudicationForDisclosure: ComputedRef<D5DisclosureSourceData>
  }
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_IMPAIRMENT_ROWS = 'D5-note-listed-impairment-rows'
const ITEM_LISTED_TEXT_1 = 'D5-note-listed-text-1'
const ITEM_LISTED_TEXT_2 = 'D5-note-listed-text-2'
const ITEM_LISTED_TEXT_3 = 'D5-note-listed-text-3'
const ITEM_SOE_TEXT_1 = 'D5-note-soe-text-1'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2)}`
}

function safeParseImpairmentRows(jsonStr: string | null | undefined): ImpairmentRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function createEmptyImpairmentRow(): ImpairmentRow {
  return {
    rowId: generateRowId(),
    itemName: '',
    priorEnd: 0,
    provision: 0,
    reversal: 0,
    writeOff: 0,
    endBalance: 0,
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD5Disclosure(options: UseD5DisclosureOptions) {
  const { allResponses, debouncedSave, isReadonly, crossSheet } = options
  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []

  // ─── Applicable Standards 适用性判断（Req 8.6）───────────────────────

  /**
   * 从 allResponses 或项目配置读取适用标准
   * listed_standalone / listed_consolidated → 显示上市公司版
   * soe_standalone / soe_consolidated → 显示国企版
   */
  const applicableStandards = computed<string[]>(() => {
    const resp = allResponses.value.get('D5-applicable-standards')
    if (resp?.remark) {
      try {
        const parsed = JSON.parse(resp.remark)
        if (Array.isArray(parsed)) return parsed
      } catch { /* fallback */ }
      // 单字符串模式
      return resp.remark.split(',').map(s => s.trim()).filter(Boolean)
    }
    // 默认都显示
    return ['listed_standalone', 'soe_standalone']
  })

  const showListed: ComputedRef<boolean> = computed(() => {
    return applicableStandards.value.some(s =>
      s === 'listed_standalone' || s === 'listed_consolidated' || s === 'listed',
    )
  })

  const showSoe: ComputedRef<boolean> = computed(() => {
    return applicableStandards.value.some(s =>
      s === 'soe_standalone' || s === 'soe_consolidated' || s === 'soe',
    )
  })

  // ─── Active Variant（el-segmented切换，Req 8.7）──────────────────────

  const activeVariant = ref<'listed' | 'soe'>(showListed.value ? 'listed' : 'soe')

  // 当适用性变化时，确保activeVariant有效
  watch([showListed, showSoe], () => {
    if (activeVariant.value === 'listed' && !showListed.value) {
      activeVariant.value = 'soe'
    } else if (activeVariant.value === 'soe' && !showSoe.value) {
      activeVariant.value = 'listed'
    }
  })

  // ─── CrossSheet 数据源 ─────────────────────────────────────────────────

  const disclosureSource = computed<D5DisclosureSourceData>(() => {
    return crossSheet.adjudicationForDisclosure.value
  })

  // ─── 上市公司版 Section 1: 分类（Req 8.1）──────────────────────────────

  const listedSection1Rows: ComputedRef<DisclosureRow[]> = computed(() => {
    const src = disclosureSource.value
    return [
      {
        rowId: 'listed-cls-notes',
        label: '应收票据',
        endAmount: src.notesReceivable.current,
        priorAmount: src.notesReceivable.prior,
      },
      {
        rowId: 'listed-cls-accounts',
        label: '应收账款',
        endAmount: src.accountsReceivable.current,
        priorAmount: src.accountsReceivable.prior,
      },
      {
        rowId: 'listed-cls-subtotal',
        label: '小计',
        endAmount: src.subtotal.current,
        priorAmount: src.subtotal.prior,
      },
      {
        rowId: 'listed-cls-oci',
        label: '减：其他综合收益-公允价值变动',
        endAmount: src.ociChange.current,
        priorAmount: src.ociChange.prior,
      },
      {
        rowId: 'listed-cls-fv',
        label: '应收款项融资公允价值合计',
        endAmount: src.fairValueTotal.current,
        priorAmount: src.fairValueTotal.prior,
      },
    ]
  })

  const listedSection1: ComputedRef<DisclosureSection> = computed(() => ({
    sectionKey: 'listed-classification',
    label: '应收款项融资分项目列示',
    rows: listedSection1Rows.value,
  }))

  // ─── 上市公司版 Section 2: 减值准备变动（Req 8.5）──────────────────────

  const impairmentRows = ref<ImpairmentRow[]>([])

  // 从 allResponses 加载减值行 JSON
  watch(
    () => allResponses.value.get(ITEM_IMPAIRMENT_ROWS)?.remark,
    (jsonStr) => {
      impairmentRows.value = safeParseImpairmentRows(jsonStr)
    },
    { immediate: true },
  )

  // 自动重算每行的 endBalance
  watch(
    impairmentRows,
    (rows) => {
      let changed = false
      for (const row of rows) {
        const calculated = calcImpairmentEnd(
          parseNum(row.priorEnd),
          parseNum(row.provision),
          parseNum(row.reversal),
          parseNum(row.writeOff),
        )
        if (row.endBalance !== calculated) {
          row.endBalance = calculated
          changed = true
        }
      }
      if (changed) {
        // 触发保存
        _persistImpairmentRows()
      }
    },
    { deep: true },
  )

  function _persistImpairmentRows(): void {
    debouncedSave(ITEM_IMPAIRMENT_ROWS, { remark: JSON.stringify(impairmentRows.value) })
  }

  function impairmentAddRow(): void {
    if (isReadonly.value) return
    const row = createEmptyImpairmentRow()
    impairmentRows.value = [...impairmentRows.value, row]
    _persistImpairmentRows()
  }

  function impairmentRemoveRow(rowId: string): void {
    if (isReadonly.value) return
    impairmentRows.value = impairmentRows.value.filter(r => r.rowId !== rowId)
    _persistImpairmentRows()
  }

  // 减值准备变动 Section computed
  const listedSection2Rows: ComputedRef<DisclosureRow[]> = computed(() => {
    return impairmentRows.value.map(row => ({
      rowId: row.rowId,
      label: row.itemName || '（未命名）',
      endAmount: row.endBalance,
      priorAmount: row.priorEnd,
    }))
  })

  const listedSection2TotalRow: ComputedRef<DisclosureRow> = computed(() => ({
    rowId: '__impairment-total__',
    label: '合计',
    endAmount: calcSubtotal(impairmentRows.value.map(r => r.endBalance)),
    priorAmount: calcSubtotal(impairmentRows.value.map(r => r.priorEnd)),
  }))

  const listedSection2: ComputedRef<DisclosureSection> = computed(() => ({
    sectionKey: 'listed-impairment',
    label: '(1) 本期计提、收回或转回的减值准备情况',
    rows: listedSection2Rows.value,
    totalRow: listedSection2TotalRow.value,
  }))

  // ─── 上市公司版 Section 3: 说明（Req 8.8）────────────────────────────

  const listedSection3: ComputedRef<DisclosureSection> = computed(() => ({
    sectionKey: 'listed-notes',
    label: '',
    rows: [],
  }))

  // ─── 上市公司版 Sections 汇总 ──────────────────────────────────────────

  const listedSections: ComputedRef<DisclosureSection[]> = computed(() => [
    listedSection1.value,
    listedSection2.value,
    listedSection3.value,
  ])

  // ─── 国企版 Section 1: 分类（Req 8.2）──────────────────────────────────

  const soeSection1Rows: ComputedRef<DisclosureRow[]> = computed(() => {
    const src = disclosureSource.value
    return [
      {
        rowId: 'soe-cls-notes',
        label: '应收票据',
        endAmount: src.notesReceivable.current,
        priorAmount: src.notesReceivable.prior,
      },
      {
        rowId: 'soe-cls-accounts',
        label: '应收账款',
        endAmount: src.accountsReceivable.current,
        priorAmount: src.accountsReceivable.prior,
      },
    ]
  })

  const soeSection1TotalRow: ComputedRef<DisclosureRow> = computed(() => ({
    rowId: '__soe-total__',
    label: '合计',
    endAmount: calcSubtotal(soeSection1Rows.value.map(r => r.endAmount)),
    priorAmount: calcSubtotal(soeSection1Rows.value.map(r => r.priorAmount)),
  }))

  const soeSection1: ComputedRef<DisclosureSection> = computed(() => ({
    sectionKey: 'soe-classification',
    label: '(1) 应收款项融资分类',
    rows: soeSection1Rows.value,
    totalRow: soeSection1TotalRow.value,
  }))

  const soeSections: ComputedRef<DisclosureSection[]> = computed(() => [
    soeSection1.value,
  ])

  // ─── noteTexts 双向绑定（Req 8.8）──────────────────────────────────────

  const noteTexts = ref<Record<string, string>>({
    'listed-1': '',
    'listed-2': '',
    'listed-3': '',
    'soe-1': '',
  })

  // 从 allResponses 初始化
  watch(
    () => allResponses.value.get(ITEM_LISTED_TEXT_1)?.remark,
    (v) => { noteTexts.value['listed-1'] = v || '' },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get(ITEM_LISTED_TEXT_2)?.remark,
    (v) => { noteTexts.value['listed-2'] = v || '' },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get(ITEM_LISTED_TEXT_3)?.remark,
    (v) => { noteTexts.value['listed-3'] = v || '' },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get(ITEM_SOE_TEXT_1)?.remark,
    (v) => { noteTexts.value['soe-1'] = v || '' },
    { immediate: true },
  )

  // debounce保存 + EventBus双向回写
  watch(
    () => noteTexts.value['listed-1'],
    (val) => {
      debouncedSave(ITEM_LISTED_TEXT_1, { remark: val })
      _dispatchNoteEvent('listed-1', val)
    },
  )
  watch(
    () => noteTexts.value['listed-2'],
    (val) => {
      debouncedSave(ITEM_LISTED_TEXT_2, { remark: val })
      _dispatchNoteEvent('listed-2', val)
    },
  )
  watch(
    () => noteTexts.value['listed-3'],
    (val) => {
      debouncedSave(ITEM_LISTED_TEXT_3, { remark: val })
      _dispatchNoteEvent('listed-3', val)
    },
  )
  watch(
    () => noteTexts.value['soe-1'],
    (val) => {
      debouncedSave(ITEM_SOE_TEXT_1, { remark: val })
      _dispatchNoteEvent('soe-1', val)
    },
  )

  function _dispatchNoteEvent(section: string, text: string): void {
    // 统一 eventBus (crossWpEventBridge 双向桥接 window)
    eventBus.emit('disclosure:note-text-updated', {
      wpCode: 'D5',
      accountCode: '1124',
      projectId: options.projectId.value,
      section,
      sectionIds: [section.startsWith('soe') ? '八、6' : '五、6'],
      text,
      timestamp: Date.now(),
    })
  }

  // ─── EventBus: 监听审定表发布 + 附注模块更新（双向同步）────────────

  // 订阅审定表发布事件（crossSheet computed 自动响应 allResponses 变化）
  eventBus.on('substantive:adjudicated', (payload: any) => {
    if (payload?.wpCode === 'D5') {
      // crossSheet 是 computed，allResponses 变化时自动重算
      // 此处可用于触发 stale 检查或附注一致性提示
    }
  })

  const noteUpdateHandler = (e: Event) => {
    const detail = (e as CustomEvent).detail
    if (detail?.wpCode === 'D5') {
      const section = detail.section as string
      if (section && noteTexts.value[section] !== undefined) {
        noteTexts.value[section] = detail.text || ''
      }
    }
  }
  window.addEventListener('note:section-updated', noteUpdateHandler)
  eventListeners.push({ event: 'note:section-updated', handler: noteUpdateHandler })

  // ─── Lifecycle ───────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    for (const { event, handler } of eventListeners) {
      window.removeEventListener(event, handler)
    }
    eventBus.off('substantive:adjudicated')
  })

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    // 上市公司版
    listedSections,
    // 国企版
    soeSections,
    // 适用性
    showListed,
    showSoe,
    activeVariant,
    // 减值准备变动（上市公司版）
    impairmentRows,
    impairmentAddRow,
    impairmentRemoveRow,
    // 说明
    noteTexts,
  }
}

export default useD5Disclosure
