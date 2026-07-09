/**
 * useI6Disclosure — I6 研发费用附注披露 composable
 *
 * Variant 双版本（上市公司 19行×7列 / 国有企业 16行×6列）
 * - 行自动从明细表I6-2聚合（SUMIF按类别列X分组）
 * - 自动获取I2资本化金额用于"资本化"行
 * - EventBus: subscribe 'substantive:adjudicated' 刷新 + publish 'disclosure:note-text-updated'
 * - Persistence: "I6-disc-listed-*" / "I6-disc-soe-*" item_ids
 *
 * 研发费用附注特殊：损益类取发生额，行=SUMIF(明细表.类别列X, 类别值, 金额列Q/W)
 *   上市: 19行×7列 24公式
 *   国企: 16行×6列 24公式
 *
 * Spec: .kiro/specs/i6-research-development-expense/
 * Task: 3.6
 * Requirements: 7.1-7.2
 */
import { ref, computed, watch, onMounted, onUnmounted, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { calcSubtotal } from './useI6FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type I6DisclosureVariant = 'listed' | 'soe'

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** 附注披露行（SUMIF聚合行） */
export interface I6DisclosureRow {
  rowId: string
  /** 项目名称（类别，来自I6-2 col X） */
  item: string
  /** 本期发生额 B（SUMIF明细表col Q by category） */
  currentAmount: number
  /** 上期发生额 C（SUMIF明细表col W by category） */
  priorAmount: number
  /** 是否跨sheet自动取数 */
  isAutoFilled: boolean
  /** 备注 */
  remark: string
}

/** 合计行 */
export interface I6DisclosureTotalRow {
  currentAmount: number   // SUM(B7:B_last)
  priorAmount: number     // SUM(C7:C_last)
}

/** 附注子节定义 */
export interface I6DisclosureSection {
  key: string
  title: string
  hasTable: boolean
  hasNoteText: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX_LISTED = 'I6-disc-listed'
const ITEM_PREFIX_SOE = 'I6-disc-soe'

/** 上市公司版本子节（19×7，24公式） */
export const LISTED_SECTIONS: I6DisclosureSection[] = [
  { key: 'expense_breakdown', title: '(1) 研发费用明细', hasTable: true, hasNoteText: false },
  { key: 'capitalized', title: '(2) 研发资本化情况', hasTable: true, hasNoteText: true },
  { key: 'expense_nature', title: '(3) 费用性质分类', hasTable: true, hasNoteText: false },
  { key: 'other_disclosure', title: '(4) 其他说明', hasTable: false, hasNoteText: true },
]

/** 国企版本子节（16×6，24公式） */
export const SOE_SECTIONS: I6DisclosureSection[] = [
  { key: 'expense_breakdown', title: '(一) 研发费用明细', hasTable: true, hasNoteText: false },
  { key: 'capitalized', title: '(二) 研发资本化情况', hasTable: true, hasNoteText: true },
  { key: 'expense_nature', title: '(三) 费用性质分类', hasTable: true, hasNoteText: false },
  { key: 'other_disclosure', title: '(四) 其他说明', hasTable: false, hasNoteText: true },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI6Disclosure(options: {
  variant: 'listed' | 'soe'
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { variant: variantValue, allResponses, onSave } = options

  // ─── State ─────────────────────────────────────────────────────────────────

  const variant = ref<I6DisclosureVariant>(variantValue)
  const itemPrefix = computed(() => variant.value === 'listed' ? ITEM_PREFIX_LISTED : ITEM_PREFIX_SOE)
  const isAiGenerating = ref(false)

  /** SUMIF聚合行（按类别从I6-2取数） */
  const rows = ref<I6DisclosureRow[]>([])

  /** 各子节说明文本（AI生成/手工填写） */
  const noteText = ref<Record<string, string>>({})

  // ─── Computed: 子节列表 ────────────────────────────────────────────────────

  const sections = computed(() =>
    variant.value === 'listed' ? LISTED_SECTIONS : SOE_SECTIONS,
  )

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const totalRow = computed<I6DisclosureTotalRow>(() => ({
    currentAmount: calcSubtotal(rows.value.map((r) => r.currentAmount)),
    priorAmount: calcSubtotal(rows.value.map((r) => r.priorAmount)),
  }))

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadData(): void {
    const prefix = itemPrefix.value

    // 聚合行
    const rowsItem = allResponses.value.get(`${prefix}-rows`)
    if (rowsItem?.remark) {
      try {
        const parsed = JSON.parse(rowsItem.remark)
        rows.value = Array.isArray(parsed) ? parsed : []
      } catch { rows.value = [] }
    } else {
      rows.value = []
    }

    // 说明文本
    for (const sect of sections.value) {
      if (sect.hasNoteText) {
        const noteItem = allResponses.value.get(`${prefix}-${sect.key}-note`)
        noteText.value[sect.key] = (noteItem?.remark ?? '') as string
      }
    }
  }

  // ─── SUMIF逻辑: 从I6-2明细表聚合 ─────────────────────────────────────────

  /**
   * 从allResponses中获取I6-2明细表数据，按类别列X执行SUMIF
   * A = category from I6-2 col X
   * B = SUMIF by category on col Q (本期发生额)
   * C = SUMIF by category on col W (上期发生额)
   */
  function aggregateFromDetail(): void {
    // 从allResponses读取I6-2明细数据（JSON打包存储）
    const detailItem = allResponses.value.get('I6-2-detail-rows')
    if (!detailItem?.remark) return

    let detailRows: any[] = []
    try {
      detailRows = JSON.parse(detailItem.remark)
      if (!Array.isArray(detailRows)) return
    } catch { return }

    // SUMIF: 按category(col X)分组，汇总currentAmount(col Q) + priorAmount(col W)
    const categoryMap = new Map<string, { current: number; prior: number }>()

    for (const row of detailRows) {
      const category = String(row.category || row.col_x || '').trim()
      if (!category) continue

      const existing = categoryMap.get(category) || { current: 0, prior: 0 }
      existing.current += Number(row.currentAmount || row.col_q || 0) || 0
      existing.prior += Number(row.priorAmount || row.col_w || 0) || 0
      categoryMap.set(category, existing)
    }

    // 转换为附注行
    const aggregated: I6DisclosureRow[] = []
    let idx = 0
    for (const [category, amounts] of categoryMap.entries()) {
      aggregated.push({
        rowId: `i6disc-sumif-${idx++}`,
        item: category,
        currentAmount: amounts.current,
        priorAmount: amounts.prior,
        isAutoFilled: true,
        remark: '',
      })
    }

    if (aggregated.length > 0) {
      rows.value = aggregated
      _persistRows()
    }
  }

  // ─── Auto-fetch I2 资本化金额 ─────────────────────────────────────────────

  /**
   * 从allResponses或EventBus获取I2资本化金额
   * 用于附注"资本化"行
   */
  function getI2CapitalizedAmount(): number {
    // 优先从allResponses读取I2联动数据
    const i2Item = allResponses.value.get('I6-cross-i2-capitalized')
    if (i2Item?.remark) {
      const val = Number(i2Item.remark)
      if (Number.isFinite(val)) return val
    }
    return 0
  }

  // ─── CRUD ──────────────────────────────────────────────────────────────────

  function updateRow(rowId: string, field: keyof I6DisclosureRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    row.isAutoFilled = false
    _persistRows()
  }

  function addRow(item: string): void {
    rows.value.push({
      rowId: `i6disc-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      item,
      currentAmount: 0,
      priorAmount: 0,
      isAutoFilled: false,
      remark: '',
    })
    _persistRows()
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      rows.value.splice(idx, 1)
      _persistRows()
    }
  }

  // ─── Save Note ─────────────────────────────────────────────────────────────

  function saveNote(sectionKey: string, text: string): void {
    noteText.value[sectionKey] = text
    const prefix = itemPrefix.value
    onSave?.(`${prefix}-${sectionKey}-note`, text)
    _publishNoteEvent(sectionKey)
  }

  // ─── AI辅助生成文字描述 ───────────────────────────────────────────────────

  async function generateNoteText(sectionKey: string, wpId: string): Promise<string | null> {
    if (!wpId) return null
    isAiGenerating.value = true
    try {
      const context = _buildAiContext(sectionKey)
      const res = await api.post(`/api/workpapers/${wpId}/ai/generate-text`, {
        section: `i6-disclosure-${variant.value}-${sectionKey}`,
        prompt: `请为研发费用附注"${_getSectionTitle(sectionKey)}"生成披露文字描述`,
        context,
        existingContent: noteText.value[sectionKey] || '',
      })

      const data = res?.data ?? res
      const generated = data?.content ?? data?.text ?? ''
      if (generated) return generated
      ElMessage.warning('AI未返回内容，请手工编写')
      return null
    } catch (err: any) {
      const msg = err?.response?.data?.message || err?.message || 'AI生成失败'
      ElMessage.error(msg)
      return null
    } finally {
      isAiGenerating.value = false
    }
  }

  // ─── EventBus 订阅 + 发布 ─────────────────────────────────────────────────

  let publishTimer: ReturnType<typeof setTimeout> | null = null
  const changedSections = ref<Set<string>>(new Set())

  function _publishNoteEvent(sectionKey: string): void {
    changedSections.value.add(sectionKey)

    // 防抖：300ms内的多次变更合并为一次事件
    if (publishTimer) clearTimeout(publishTimer)
    publishTimer = setTimeout(() => {
      const sectionsArr = Array.from(changedSections.value)
      changedSections.value.clear()

      const payload = {
        wpCode: 'I6',
        variant: variant.value,
        sections: sectionsArr,
      }

      // 全局 CustomEvent（标准D~N附注EventBus模式）
      window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
        detail: payload,
      }))
    }, 300)
  }

  /**
   * 订阅 'substantive:adjudicated' 事件，审定表确认后刷新附注数据
   */
  function _onSubstantiveAdjudicated(event: Event): void {
    const detail = (event as CustomEvent).detail
    // 仅响应 I6 相关事件（科目6602研发费用）
    if (detail?.wpCode === 'I6' || detail?.accountCode === '6602') {
      aggregateFromDetail()
    }
  }

  /**
   * 订阅 I2 资本化变更事件
   */
  function _onI2CapitalizedUpdated(event: Event): void {
    const detail = (event as CustomEvent).detail
    if (detail?.capitalizedAmount != null) {
      // 更新存储的I2资本化金额
      onSave?.('I6-cross-i2-capitalized', String(detail.capitalizedAmount))
    }
  }

  onMounted(() => {
    window.addEventListener('substantive:adjudicated', _onSubstantiveAdjudicated)
    window.addEventListener('development:capitalized-updated', _onI2CapitalizedUpdated)
  })

  onUnmounted(() => {
    window.removeEventListener('substantive:adjudicated', _onSubstantiveAdjudicated)
    window.removeEventListener('development:capitalized-updated', _onI2CapitalizedUpdated)
    if (publishTimer) {
      clearTimeout(publishTimer)
      publishTimer = null
    }
  })

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _buildAiContext(sectionKey: string): string {
    const parts: string[] = [
      `科目: 研发费用(6602)，损益类借方科目，取发生额非余额`,
      `版本: ${variant.value === 'listed' ? '上市公司(19×7)' : '国有企业(16×6)'}`,
      `特点: 费用化(I6)+资本化(I2)=研发总额`,
      `合计行: 本期发生额=${totalRow.value.currentAmount}, 上期发生额=${totalRow.value.priorAmount}`,
    ]
    const i2Cap = getI2CapitalizedAmount()
    if (i2Cap !== 0) parts.push(`I2资本化金额: ${i2Cap}`)
    if (rows.value.length > 0) {
      parts.push(`披露类别: ${rows.value.map((r) => r.item).join('/')}`)
    }
    return parts.join('; ')
  }

  function _getSectionTitle(sectionKey: string): string {
    const sect = sections.value.find((s) => s.key === sectionKey)
    return sect?.title ?? sectionKey
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persistRows(): void {
    const prefix = itemPrefix.value
    onSave?.(`${prefix}-rows`, JSON.stringify(rows.value))
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadData(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    rows,
    totalRow,
    noteText,
    // Computed
    sections,
    variant,
    isAiGenerating,
    // Actions
    saveNote,
    aggregateFromDetail,
    getI2CapitalizedAmount,
    updateRow,
    addRow,
    removeRow,
    generateNoteText,
  }
}

export default useI6Disclosure
