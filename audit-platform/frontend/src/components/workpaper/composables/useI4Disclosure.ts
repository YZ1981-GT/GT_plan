/**
 * useI4Disclosure — I4 长期待摊费用附注披露 composable
 *
 * Variant 双版本（上市公司14×13 / 国有企业16×12），根据 projectContext.business_category 自动选择。
 * - 从审定表自动取数（subscribe 'substantive:adjudicated' event）(Req 7.2)
 * - AI 辅助生成文字描述 (Req 7.2)
 * - EventBus: subscribe 'substantive:adjudicated' 刷新 + publish 'disclosure:note-text-updated' (Req 7.2)
 * - Persistence: "I4-disc-listed-*" / "I4-disc-soe-*" item_ids
 *
 * 长期待摊费用附注特殊：摊销变动矩阵（期初+增加-摊销-减少=期末）
 * 上市: 14行×13列 (42公式)
 * 国企: 16行×12列 (47公式)
 *
 * Spec: .kiro/specs/i4-long-term-prepaid/
 * Task: 3.5
 * Requirements: 7.1-7.2
 */
import { ref, computed, watch, onMounted, onUnmounted, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { calcSubtotal } from './useI4FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type I4DisclosureVariant = 'listed' | 'soe'

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** 附注子节定义 */
export interface I4DisclosureSection {
  key: string
  title: string
  hasTable: boolean
  hasDynamicRows: boolean
  hasNoteText: boolean
}

/** 附注长期待摊费用变动矩阵行 */
export interface I4DisclosureMatrixRow {
  rowId: string
  item: string                  // 费用项目
  beginBalance: number          // 期初余额
  increase: number              // 本期增加
  amortization: number          // 本期摊销
  decrease: number              // 本期减少(其他)
  endBalance: number            // 期末余额
  isAutoFilled: boolean         // 是否跨sheet自动取数
}

/** 附注动态行（通用） */
export interface I4DisclosureDynamicRow {
  rowId: string
  name: string
  amount: number
  description: string
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX_LISTED = 'I4-disc-listed'
const ITEM_PREFIX_SOE = 'I4-disc-soe'

/** 上市公司版本子节（14×13，42公式） */
export const LISTED_SECTIONS: I4DisclosureSection[] = [
  { key: 'prepaid_original', title: '(1) 长期待摊费用原值变动', hasTable: true, hasDynamicRows: false, hasNoteText: false },
  { key: 'prepaid_amortization', title: '(2) 长期待摊费用累计摊销变动', hasTable: true, hasDynamicRows: false, hasNoteText: false },
  { key: 'prepaid_net_value', title: '(3) 长期待摊费用净值', hasTable: true, hasDynamicRows: false, hasNoteText: false },
  { key: 'amortization_method', title: '(4) 摊销方法说明', hasTable: false, hasDynamicRows: false, hasNoteText: true },
  { key: 'major_items', title: '(5) 重大长期待摊费用明细', hasTable: true, hasDynamicRows: true, hasNoteText: true },
  { key: 'other_disclosure', title: '(6) 其他说明', hasTable: false, hasDynamicRows: false, hasNoteText: true },
]

/** 国企版本子节（16×12，47公式） */
export const SOE_SECTIONS: I4DisclosureSection[] = [
  { key: 'prepaid_original', title: '(一) 长期待摊费用原值变动', hasTable: true, hasDynamicRows: false, hasNoteText: false },
  { key: 'prepaid_amortization', title: '(二) 长期待摊费用累计摊销变动', hasTable: true, hasDynamicRows: false, hasNoteText: false },
  { key: 'prepaid_net_value', title: '(三) 长期待摊费用净值', hasTable: true, hasDynamicRows: false, hasNoteText: false },
  { key: 'amortization_policy', title: '(四) 摊销政策', hasTable: false, hasDynamicRows: false, hasNoteText: true },
  { key: 'major_items', title: '(五) 重大长期待摊费用明细', hasTable: true, hasDynamicRows: true, hasNoteText: true },
  { key: 'benefit_period', title: '(六) 受益期间说明', hasTable: false, hasDynamicRows: false, hasNoteText: true },
  { key: 'other_disclosure', title: '(七) 其他说明', hasTable: false, hasDynamicRows: false, hasNoteText: true },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI4Disclosure(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    variant?: Ref<I4DisclosureVariant>
    crossSheetAutoFill?: Ref<Record<string, number>>
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const variant = computed<I4DisclosureVariant>(() => options?.variant?.value ?? 'listed')
  const itemPrefix = computed(() => variant.value === 'listed' ? ITEM_PREFIX_LISTED : ITEM_PREFIX_SOE)
  const isAiGenerating = ref(false)

  /** 子节1: 长期待摊费用原值变动矩阵 */
  const originalRows = ref<I4DisclosureMatrixRow[]>([])

  /** 子节2: 长期待摊费用累计摊销变动矩阵 */
  const amortizationRows = ref<I4DisclosureMatrixRow[]>([])

  /** 动态行子节（重大长期待摊费用明细） */
  const sectionRows = ref<Record<string, I4DisclosureDynamicRow[]>>({
    major_items: [],
  })

  /** 各子节说明文本（AI生成/手工填写） */
  const sectionNotes = ref<Record<string, string>>({})

  // ─── Computed: 子节列表 ────────────────────────────────────────────────────

  const sections = computed(() =>
    variant.value === 'listed' ? LISTED_SECTIONS : SOE_SECTIONS,
  )

  // ─── Computed: 跨sheet自动取数 (Req 7.2) ──────────────────────────────────

  const autoFilledData = computed(() => options?.crossSheetAutoFill?.value ?? {})

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const originalTotal = computed(() => ({
    beginBalance: calcSubtotal(originalRows.value.map((r) => r.beginBalance)),
    increase: calcSubtotal(originalRows.value.map((r) => r.increase)),
    amortization: calcSubtotal(originalRows.value.map((r) => r.amortization)),
    decrease: calcSubtotal(originalRows.value.map((r) => r.decrease)),
    endBalance: calcSubtotal(originalRows.value.map((r) => r.endBalance)),
  }))

  const amortizationTotal = computed(() => ({
    beginBalance: calcSubtotal(amortizationRows.value.map((r) => r.beginBalance)),
    increase: calcSubtotal(amortizationRows.value.map((r) => r.increase)),
    amortization: calcSubtotal(amortizationRows.value.map((r) => r.amortization)),
    decrease: calcSubtotal(amortizationRows.value.map((r) => r.decrease)),
    endBalance: calcSubtotal(amortizationRows.value.map((r) => r.endBalance)),
  }))

  /** 净值合计 = 原值期末 - 累计摊销期末 */
  const netValueTotal = computed(() =>
    originalTotal.value.endBalance - amortizationTotal.value.endBalance,
  )

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadData(): void {
    const prefix = itemPrefix.value

    // 矩阵行
    originalRows.value = _loadMatrixRows(`${prefix}-original-matrix`)
    amortizationRows.value = _loadMatrixRows(`${prefix}-amortization-matrix`)

    // 动态行
    for (const key of Object.keys(sectionRows.value)) {
      const item = allResponses.value.get(`${prefix}-${key}-rows`)
      if (item?.remark) {
        try {
          const parsed = JSON.parse(item.remark)
          sectionRows.value[key] = Array.isArray(parsed) ? parsed : []
        } catch { sectionRows.value[key] = [] }
      } else {
        sectionRows.value[key] = []
      }
    }

    // 说明文本
    for (const sect of sections.value) {
      if (sect.hasNoteText) {
        const noteItem = allResponses.value.get(`${prefix}-${sect.key}-note`)
        sectionNotes.value[sect.key] = (noteItem?.remark ?? '') as string
      }
    }
  }

  function _loadMatrixRows(itemId: string): I4DisclosureMatrixRow[] {
    const item = allResponses.value.get(itemId)
    if (!item?.remark) return []
    try {
      const parsed = JSON.parse(item.remark)
      return Array.isArray(parsed) ? parsed : []
    } catch { return [] }
  }

  // ─── Auto-fill from cross-sheet (Req 7.2) ─────────────────────────────────

  /**
   * 从审定表自动取数填入附注对应位置。
   * 长期待摊费用: 期末 = 期初 + 增加 - 摊销 - 减少
   * 用户可手工覆盖自动值。
   */
  function applyAutoFill(): void {
    const data = autoFilledData.value
    if (!data || Object.keys(data).length === 0) return

    // 如果原值矩阵为空，根据审定表数据初始化
    if (originalRows.value.length === 0 && data['disc_prepaid_begin'] != null) {
      originalRows.value = [{
        rowId: 'auto-original-total',
        item: '合计',
        beginBalance: data['disc_prepaid_begin'] ?? 0,
        increase: data['disc_prepaid_increase'] ?? 0,
        amortization: data['disc_prepaid_amortization'] ?? 0,
        decrease: data['disc_prepaid_decrease'] ?? 0,
        endBalance: data['disc_prepaid_end'] ?? 0,
        isAutoFilled: true,
      }]
    }

    // 如果累计摊销矩阵为空，根据审定表数据初始化
    if (amortizationRows.value.length === 0 && data['disc_amort_begin'] != null) {
      amortizationRows.value = [{
        rowId: 'auto-amort-total',
        item: '合计',
        beginBalance: data['disc_amort_begin'] ?? 0,
        increase: data['disc_amort_increase'] ?? 0,
        amortization: 0,
        decrease: data['disc_amort_decrease'] ?? 0,
        endBalance: data['disc_amort_end'] ?? 0,
        isAutoFilled: true,
      }]
    }
  }

  // ─── CRUD: 动态行 ─────────────────────────────────────────────────────────

  function addDynamicRow(sectionKey: string, name: string): void {
    const rows = sectionRows.value[sectionKey]
    if (!rows) return
    rows.push({
      rowId: `i4disc-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
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

  function updateDynamicRow(sectionKey: string, rowId: string, field: keyof I4DisclosureDynamicRow, value: any): void {
    const rows = sectionRows.value[sectionKey]
    if (!rows) return
    const row = rows.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _persistSection(sectionKey)
  }

  // ─── Update: 矩阵行 ───────────────────────────────────────────────────────

  function updateMatrixCell(
    layer: 'original' | 'amortization',
    rowId: string,
    field: keyof I4DisclosureMatrixRow,
    value: any,
  ): void {
    const target = layer === 'original' ? originalRows : amortizationRows
    const row = target.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    row.isAutoFilled = false // 手工修改后取消自动标记
    _persistMatrix(layer)
  }

  // ─── Section Note (手工编辑) ───────────────────────────────────────────────

  function saveSectionNote(sectionKey: string, note: string): void {
    sectionNotes.value[sectionKey] = note
    const prefix = itemPrefix.value
    options?.onSave?.(`${prefix}-${sectionKey}-note`, note)

    // EventBus发布 'disclosure:note-text-updated' (Req 7.2)
    _publishNoteEvent(sectionKey, note)
  }

  // ─── AI辅助生成文字描述 (Req 7.2) ─────────────────────────────────────────

  /**
   * 调用AI端点生成附注文字描述。
   * 后端 POST /api/workpapers/{wp_id}/ai/generate-text
   */
  async function generateNoteText(sectionKey: string, existingContent?: string): Promise<string | null> {
    if (!wpId.value) return null
    isAiGenerating.value = true
    try {
      const context = _buildAiContext(sectionKey)
      const res = await api.post(`/api/workpapers/${wpId.value}/ai/generate-text`, {
        section: `i4-disclosure-${variant.value}-${sectionKey}`,
        prompt: `请为长期待摊费用附注"${_getSectionTitle(sectionKey)}"生成披露文字描述`,
        context,
        existingContent: existingContent || sectionNotes.value[sectionKey] || '',
      })

      const data = res?.data ?? res
      const generated = data?.content ?? data?.text ?? ''
      if (generated) {
        return generated
      }
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

  /**
   * AI生成并确认后写入
   */
  async function applyAiGeneratedNote(sectionKey: string, text: string): Promise<void> {
    sectionNotes.value[sectionKey] = text
    const prefix = itemPrefix.value
    options?.onSave?.(`${prefix}-${sectionKey}-note`, text)
    _publishNoteEvent(sectionKey, text)
  }

  // ─── EventBus 订阅 + 发布 (Req 7.2) ──────────────────────────────────────

  /** 已变更的section集合（用于批量事件通知） */
  const changedSections = ref<Set<string>>(new Set())
  let publishTimer: ReturnType<typeof setTimeout> | null = null

  function _publishNoteEvent(sectionKey: string, _text: string): void {
    changedSections.value.add(sectionKey)

    // 防抖：300ms内的多次变更合并为一次事件
    if (publishTimer) clearTimeout(publishTimer)
    publishTimer = setTimeout(() => {
      const sectionsArr = Array.from(changedSections.value)
      changedSections.value.clear()

      const payload = {
        wpCode: 'I4',
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
    // 仅响应 I4 相关事件（科目1801长期待摊费用）
    if (detail?.wpCode === 'I4' || detail?.accountCode === '1801') {
      applyAutoFill()
    }
  }

  onMounted(() => {
    window.addEventListener('substantive:adjudicated', _onSubstantiveAdjudicated)
  })

  onUnmounted(() => {
    window.removeEventListener('substantive:adjudicated', _onSubstantiveAdjudicated)
  })

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _buildAiContext(sectionKey: string): string {
    const data = autoFilledData.value
    const parts: string[] = [
      `科目: 长期待摊费用(1801)，资产类借方，期末=期初+增加-摊销-减少`,
      `版本: ${variant.value === 'listed' ? '上市公司' : '国有企业'}`,
      `摊销方法: 直线法(按月平均摊销) 或 工作量法`,
    ]
    if (data['disc_prepaid_begin'] != null) parts.push(`期初余额: ${data['disc_prepaid_begin']}`)
    if (data['disc_prepaid_end'] != null) parts.push(`期末余额: ${data['disc_prepaid_end']}`)
    if (data['disc_prepaid_increase'] != null) parts.push(`本期增加: ${data['disc_prepaid_increase']}`)
    if (data['disc_prepaid_amortization'] != null) parts.push(`本期摊销: ${data['disc_prepaid_amortization']}`)
    if (data['disc_prepaid_decrease'] != null) parts.push(`本期减少(其他): ${data['disc_prepaid_decrease']}`)
    if (data['disc_prepaid_audited'] != null) parts.push(`审定数: ${data['disc_prepaid_audited']}`)
    if (data['disc_item_count'] != null) parts.push(`费用项目数: ${data['disc_item_count']}`)
    return parts.join('; ')
  }

  function _getSectionTitle(sectionKey: string): string {
    const sect = sections.value.find((s) => s.key === sectionKey)
    return sect?.title ?? sectionKey
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persistSection(sectionKey: string): void {
    const prefix = itemPrefix.value
    options?.onSave?.(`${prefix}-${sectionKey}-rows`, sectionRows.value[sectionKey])
  }

  function _persistMatrix(layer: string): void {
    const prefix = itemPrefix.value
    const target = layer === 'original' ? originalRows : amortizationRows
    options?.onSave?.(`${prefix}-${layer}-matrix`, target.value)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadData(), { immediate: true })
  watch(variant, () => _loadData())

  // ─── Cleanup ───────────────────────────────────────────────────────────────

  function dispose(): void {
    if (publishTimer) {
      clearTimeout(publishTimer)
      publishTimer = null
    }
    changedSections.value.clear()
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    variant,
    isAiGenerating,
    originalRows,
    amortizationRows,
    sectionRows,
    sectionNotes,
    // Computed
    sections,
    autoFilledData,
    originalTotal,
    amortizationTotal,
    netValueTotal,
    // Actions
    applyAutoFill,
    addDynamicRow,
    removeDynamicRow,
    updateDynamicRow,
    updateMatrixCell,
    saveSectionNote,
    // AI
    generateNoteText,
    applyAiGeneratedNote,
    // Lifecycle
    dispose,
  }
}

export default useI4Disclosure
