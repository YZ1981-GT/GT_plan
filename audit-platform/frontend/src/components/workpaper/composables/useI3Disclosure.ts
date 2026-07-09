/**
 * useI3Disclosure — I3 商誉附注披露 composable
 *
 * Variant 双版本（上市公司41×8 / 国有企业31×7），根据 projectContext.business_category 自动选择。
 * - 从审定表+减值测试自动取数（via useI3CrossSheet.disclosureAutoFill）(Req 9.2)
 * - AI 辅助生成文字描述 (Req 9.3)
 * - EventBus: subscribe 'substantive:adjudicated' 刷新 + publish 'disclosure:note-text-updated' (Req 9.3)
 * - Persistence: "I3-disc-listed-*" / "I3-disc-soe-*" item_ids
 *
 * 商誉附注特殊：无摊销相关矩阵！仅原值+减值+净额+减值测试过程描述
 *
 * Spec: .kiro/specs/i3-goodwill/
 * Task: 3.6
 * Requirements: 9.1-9.3
 */
import { ref, computed, watch, onMounted, onUnmounted, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { calcSubtotal } from './useI3FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type I3DisclosureVariant = 'listed' | 'soe'

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** 附注子节定义 */
export interface I3DisclosureSection {
  key: string
  title: string
  hasTable: boolean
  hasDynamicRows: boolean
  hasNoteText: boolean
}

/** 附注商誉变动矩阵行（原值/减值） */
export interface I3DisclosureMatrixRow {
  rowId: string
  investee: string              // 被投资单位(CGU)
  beginBalance: number          // 期初余额
  increase: number              // 本期增加(新并购)
  decrease: number              // 本期减少(减值)
  endBalance: number            // 期末余额
  isAutoFilled: boolean         // 是否跨sheet自动取数
}

/** 附注动态行（通用） */
export interface I3DisclosureDynamicRow {
  rowId: string
  name: string
  amount: number
  description: string
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX_LISTED = 'I3-disc-listed'
const ITEM_PREFIX_SOE = 'I3-disc-soe'

/** 上市公司版本子节（41×8） */
export const LISTED_SECTIONS: I3DisclosureSection[] = [
  { key: 'goodwill_book_value', title: '(1) 商誉账面价值', hasTable: true, hasDynamicRows: false, hasNoteText: false },
  { key: 'goodwill_impairment', title: '(2) 商誉减值准备', hasTable: true, hasDynamicRows: false, hasNoteText: false },
  { key: 'impairment_test_process', title: '(3) 商誉减值测试过程及方法', hasTable: false, hasDynamicRows: false, hasNoteText: true },
  { key: 'cgu_allocation', title: '(4) 商誉分摊至资产组(组合)情况', hasTable: true, hasDynamicRows: true, hasNoteText: true },
  { key: 'key_assumptions', title: '(5) 减值测试关键假设', hasTable: false, hasDynamicRows: false, hasNoteText: true },
  { key: 'sensitivity_analysis', title: '(6) 敏感性分析', hasTable: true, hasDynamicRows: false, hasNoteText: true },
  { key: 'impairment_result', title: '(7) 减值测试结论', hasTable: true, hasDynamicRows: false, hasNoteText: true },
  { key: 'other_disclosure', title: '(8) 其他说明', hasTable: false, hasDynamicRows: false, hasNoteText: true },
]

/** 国企版本子节（31×7） */
export const SOE_SECTIONS: I3DisclosureSection[] = [
  { key: 'goodwill_book_value', title: '(一) 商誉账面价值', hasTable: true, hasDynamicRows: false, hasNoteText: false },
  { key: 'goodwill_impairment', title: '(二) 商誉减值准备', hasTable: true, hasDynamicRows: false, hasNoteText: false },
  { key: 'impairment_test_process', title: '(三) 商誉减值测试过程', hasTable: false, hasDynamicRows: false, hasNoteText: true },
  { key: 'cgu_allocation', title: '(四) 商誉分摊至资产组情况', hasTable: true, hasDynamicRows: true, hasNoteText: true },
  { key: 'key_assumptions', title: '(五) 减值测试关键假设及敏感性', hasTable: false, hasDynamicRows: false, hasNoteText: true },
  { key: 'impairment_result', title: '(六) 减值测试结论', hasTable: true, hasDynamicRows: false, hasNoteText: true },
  { key: 'other_disclosure', title: '(七) 其他说明', hasTable: false, hasDynamicRows: false, hasNoteText: true },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI3Disclosure(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    variant?: Ref<I3DisclosureVariant>
    crossSheetAutoFill?: Ref<Record<string, number>>
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const variant = computed<I3DisclosureVariant>(() => options?.variant?.value ?? 'listed')
  const itemPrefix = computed(() => variant.value === 'listed' ? ITEM_PREFIX_LISTED : ITEM_PREFIX_SOE)
  const isAiGenerating = ref(false)

  /** 子节1: 商誉账面价值矩阵（原值-减值=净额） */
  const bookValueRows = ref<I3DisclosureMatrixRow[]>([])

  /** 子节2: 商誉减值准备变动矩阵 */
  const impairmentRows = ref<I3DisclosureMatrixRow[]>([])

  /** 动态行子节（CGU分摊） */
  const sectionRows = ref<Record<string, I3DisclosureDynamicRow[]>>({
    cgu_allocation: [],
  })

  /** 各子节说明文本（AI生成/手工填写） */
  const sectionNotes = ref<Record<string, string>>({})

  // ─── Computed: 子节列表 ────────────────────────────────────────────────────

  const sections = computed(() =>
    variant.value === 'listed' ? LISTED_SECTIONS : SOE_SECTIONS,
  )

  // ─── Computed: 跨sheet自动取数 (Req 9.2) ──────────────────────────────────

  const autoFilledData = computed(() => options?.crossSheetAutoFill?.value ?? {})

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const bookValueTotal = computed(() => ({
    beginBalance: calcSubtotal(bookValueRows.value.map((r) => r.beginBalance)),
    increase: calcSubtotal(bookValueRows.value.map((r) => r.increase)),
    decrease: calcSubtotal(bookValueRows.value.map((r) => r.decrease)),
    endBalance: calcSubtotal(bookValueRows.value.map((r) => r.endBalance)),
  }))

  const impairmentTotal = computed(() => ({
    beginBalance: calcSubtotal(impairmentRows.value.map((r) => r.beginBalance)),
    increase: calcSubtotal(impairmentRows.value.map((r) => r.increase)),
    decrease: calcSubtotal(impairmentRows.value.map((r) => r.decrease)),
    endBalance: calcSubtotal(impairmentRows.value.map((r) => r.endBalance)),
  }))

  /** 净值合计 = 商誉原值期末 - 减值准备期末（商誉无摊销！） */
  const netValueTotal = computed(() =>
    bookValueTotal.value.endBalance - impairmentTotal.value.endBalance,
  )

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadData(): void {
    const prefix = itemPrefix.value

    // 矩阵行
    bookValueRows.value = _loadMatrixRows(`${prefix}-book-value-matrix`)
    impairmentRows.value = _loadMatrixRows(`${prefix}-impairment-matrix`)

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

  function _loadMatrixRows(itemId: string): I3DisclosureMatrixRow[] {
    const item = allResponses.value.get(itemId)
    if (!item?.remark) return []
    try {
      const parsed = JSON.parse(item.remark)
      return Array.isArray(parsed) ? parsed : []
    } catch { return [] }
  }

  // ─── Auto-fill from cross-sheet (Req 9.2) ─────────────────────────────────

  /**
   * 从审定表+减值测试自动取数填入附注对应位置。
   * 用户可手工覆盖自动值。
   */
  function applyAutoFill(): void {
    const data = autoFilledData.value
    if (!data || Object.keys(data).length === 0) return

    // 如果账面价值矩阵为空，根据自动数据初始化
    if (bookValueRows.value.length === 0 && data['disc_goodwill_original'] != null) {
      bookValueRows.value = [{
        rowId: 'auto-goodwill-total',
        investee: '合计',
        beginBalance: (data['disc_goodwill_original'] ?? 0) - (data['disc_goodwill_current_impairment'] ?? 0),
        increase: 0,   // 新并购（通常为0）
        decrease: data['disc_goodwill_current_impairment'] ?? 0,
        endBalance: data['disc_goodwill_original'] ?? 0,
        isAutoFilled: true,
      }]
    }

    // 如果减值准备矩阵为空，根据自动数据初始化
    if (impairmentRows.value.length === 0 && data['disc_goodwill_impairment'] != null) {
      impairmentRows.value = [{
        rowId: 'auto-impairment-total',
        investee: '合计',
        beginBalance: (data['disc_goodwill_impairment'] ?? 0) - (data['disc_goodwill_current_impairment'] ?? 0),
        increase: data['disc_goodwill_current_impairment'] ?? 0,
        decrease: 0,  // 商誉减值不可转回！
        endBalance: data['disc_goodwill_impairment'] ?? 0,
        isAutoFilled: true,
      }]
    }
  }

  // ─── CRUD: 动态行 ─────────────────────────────────────────────────────────

  function addDynamicRow(sectionKey: string, name: string): void {
    const rows = sectionRows.value[sectionKey]
    if (!rows) return
    rows.push({
      rowId: `i3disc-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
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

  function updateDynamicRow(sectionKey: string, rowId: string, field: keyof I3DisclosureDynamicRow, value: any): void {
    const rows = sectionRows.value[sectionKey]
    if (!rows) return
    const row = rows.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _persistSection(sectionKey)
  }

  // ─── Update: 矩阵行 ───────────────────────────────────────────────────────

  function updateMatrixCell(
    layer: 'bookValue' | 'impairment',
    rowId: string,
    field: keyof I3DisclosureMatrixRow,
    value: any,
  ): void {
    const target = layer === 'bookValue' ? bookValueRows : impairmentRows
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

    // EventBus发布 'disclosure:note-text-updated' (Req 9.3)
    _publishNoteEvent(sectionKey, note)
  }

  // ─── AI辅助生成文字描述 (Req 9.3) ─────────────────────────────────────────

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
        section: `i3-disclosure-${variant.value}-${sectionKey}`,
        prompt: `请为商誉附注"${_getSectionTitle(sectionKey)}"生成披露文字描述`,
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

  // ─── EventBus 订阅 + 发布 (Req 9.3) ──────────────────────────────────────

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
        wpCode: 'I3',
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
    // 仅响应 I3 相关事件
    if (detail?.wpCode === 'I3' || detail?.accountCode === '1711') {
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
      `科目: 商誉(1711)，商誉不摊销！仅年度减值测试`,
      `版本: ${variant.value === 'listed' ? '上市公司' : '国有企业'}`,
    ]
    if (data['disc_goodwill_original'] != null) parts.push(`商誉原值合计: ${data['disc_goodwill_original']}`)
    if (data['disc_goodwill_impairment'] != null) parts.push(`累计减值合计: ${data['disc_goodwill_impairment']}`)
    if (data['disc_goodwill_net'] != null) parts.push(`净额合计: ${data['disc_goodwill_net']}`)
    if (data['disc_goodwill_current_impairment'] != null) parts.push(`本期减值: ${data['disc_goodwill_current_impairment']}`)
    if (data['disc_cgu_count'] != null) parts.push(`资产组(CGU)数量: ${data['disc_cgu_count']}`)
    if (data['disc_total_impairment'] != null) parts.push(`商誉减值总额: ${data['disc_total_impairment']}`)
    if (data['disc_total_recoverable'] != null) parts.push(`可收回金额合计: ${data['disc_total_recoverable']}`)
    if (data['disc_investee_count'] != null) parts.push(`被投资单位数: ${data['disc_investee_count']}`)
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
    const target = layer === 'bookValue' ? bookValueRows : impairmentRows
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
    bookValueRows,
    impairmentRows,
    sectionRows,
    sectionNotes,
    // Computed
    sections,
    autoFilledData,
    bookValueTotal,
    impairmentTotal,
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

export default useI3Disclosure
