/**
 * useI1Disclosure — I1 无形资产附注披露 composable
 *
 * Variant 双版本（上市公司64×22 / 国有企业67×14），根据 projectContext.business_category 自动选择。
 * - 从审定表/明细表/摊销表自动取数填入对应附注位置 (Req 14.2)
 * - AI 辅助生成文字描述 (Req 14.3)
 * - EventBus 发布 'disclosure:note-text-updated' (Req 14.4)
 * - Persistence: "I1-disc-listed-*" / "I1-disc-soe-*" item_ids
 *
 * Spec: .kiro/specs/i1-intangible-assets/
 * Task: 3.7
 * Requirements: 14.1-14.4
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { calcSubtotal } from './useI1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type I1DisclosureVariant = 'listed' | 'soe'

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** 附注子节定义 */
export interface I1DisclosureSection {
  key: string
  title: string
  hasTable: boolean
  hasDynamicRows: boolean
  hasNoteText: boolean          // 是否含文字描述区域（AI可生成）
}

/** 附注矩阵行（无形资产原值/摊销/减值变动） */
export interface I1DisclosureMatrixRow {
  rowId: string
  category: string              // 资产分类（专利/商标/著作权/土地使用权/软件等）
  beginBalance: number          // 期初余额
  increase: number              // 本期增加
  decrease: number              // 本期减少
  endBalance: number            // 期末余额
  isAutoFilled: boolean         // 是否跨sheet自动取数
}

/** 附注动态行（通用） */
export interface I1DisclosureDynamicRow {
  rowId: string
  name: string
  amount: number
  description: string
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX_LISTED = 'I1-disc-listed'
const ITEM_PREFIX_SOE = 'I1-disc-soe'

/** 上市公司版本子节（64×22） */
export const LISTED_SECTIONS: I1DisclosureSection[] = [
  { key: 'cost_overview', title: '(1) 无形资产情况—原值', hasTable: true, hasDynamicRows: false, hasNoteText: false },
  { key: 'amort_overview', title: '(2) 无形资产情况—累计摊销', hasTable: true, hasDynamicRows: false, hasNoteText: false },
  { key: 'impairment_overview', title: '(3) 无形资产情况—减值准备', hasTable: true, hasDynamicRows: false, hasNoteText: false },
  { key: 'net_value', title: '(4) 无形资产账面价值', hasTable: true, hasDynamicRows: false, hasNoteText: false },
  { key: 'indefinite_life', title: '(5) 使用寿命不确定的无形资产', hasTable: true, hasDynamicRows: true, hasNoteText: true },
  { key: 'rd_expenditure', title: '(6) 研究阶段支出说明', hasTable: false, hasDynamicRows: false, hasNoteText: true },
  { key: 'restricted', title: '(7) 所有权受限的无形资产', hasTable: true, hasDynamicRows: true, hasNoteText: true },
  { key: 'amort_expense', title: '(8) 本期摊销费用', hasTable: true, hasDynamicRows: false, hasNoteText: false },
]

/** 国企版本子节（67×14） */
export const SOE_SECTIONS: I1DisclosureSection[] = [
  { key: 'cost_overview', title: '(一) 无形资产情况—原值', hasTable: true, hasDynamicRows: false, hasNoteText: false },
  { key: 'amort_overview', title: '(二) 无形资产情况—累计摊销', hasTable: true, hasDynamicRows: false, hasNoteText: false },
  { key: 'impairment_overview', title: '(三) 无形资产情况—减值准备', hasTable: true, hasDynamicRows: false, hasNoteText: false },
  { key: 'net_value', title: '(四) 无形资产账面价值', hasTable: true, hasDynamicRows: false, hasNoteText: false },
  { key: 'indefinite_life', title: '(五) 使用寿命不确定的无形资产', hasTable: true, hasDynamicRows: true, hasNoteText: true },
  { key: 'restricted', title: '(六) 所有权受限的无形资产', hasTable: true, hasDynamicRows: true, hasNoteText: true },
  { key: 'amort_expense', title: '(七) 本期摊销费用分配', hasTable: true, hasDynamicRows: false, hasNoteText: false },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI1Disclosure(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    variant?: Ref<I1DisclosureVariant>
    crossSheetAutoFill?: Ref<Record<string, number>>
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const variant = computed<I1DisclosureVariant>(() => options?.variant?.value ?? 'listed')
  const itemPrefix = computed(() => variant.value === 'listed' ? ITEM_PREFIX_LISTED : ITEM_PREFIX_SOE)
  const isAiGenerating = ref(false)

  /** 子节1~3: 无形资产原值/摊销/减值矩阵 */
  const costMatrixRows = ref<I1DisclosureMatrixRow[]>([])
  const amortMatrixRows = ref<I1DisclosureMatrixRow[]>([])
  const impairmentMatrixRows = ref<I1DisclosureMatrixRow[]>([])

  /** 动态行子节 */
  const sectionRows = ref<Record<string, I1DisclosureDynamicRow[]>>({
    indefinite_life: [],
    restricted: [],
  })

  /** 各子节说明文本（AI生成/手工填写） */
  const sectionNotes = ref<Record<string, string>>({})

  // ─── Computed: 子节列表 ────────────────────────────────────────────────────

  const sections = computed(() =>
    variant.value === 'listed' ? LISTED_SECTIONS : SOE_SECTIONS,
  )

  // ─── Computed: 跨sheet自动取数 (Req 14.2) ─────────────────────────────────

  const autoFilledData = computed(() => options?.crossSheetAutoFill?.value ?? {})

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const costTotal = computed(() => ({
    beginBalance: calcSubtotal(costMatrixRows.value.map((r) => r.beginBalance)),
    increase: calcSubtotal(costMatrixRows.value.map((r) => r.increase)),
    decrease: calcSubtotal(costMatrixRows.value.map((r) => r.decrease)),
    endBalance: calcSubtotal(costMatrixRows.value.map((r) => r.endBalance)),
  }))

  const amortTotal = computed(() => ({
    beginBalance: calcSubtotal(amortMatrixRows.value.map((r) => r.beginBalance)),
    increase: calcSubtotal(amortMatrixRows.value.map((r) => r.increase)),
    decrease: calcSubtotal(amortMatrixRows.value.map((r) => r.decrease)),
    endBalance: calcSubtotal(amortMatrixRows.value.map((r) => r.endBalance)),
  }))

  const impairmentTotal = computed(() => ({
    beginBalance: calcSubtotal(impairmentMatrixRows.value.map((r) => r.beginBalance)),
    increase: calcSubtotal(impairmentMatrixRows.value.map((r) => r.increase)),
    decrease: calcSubtotal(impairmentMatrixRows.value.map((r) => r.decrease)),
    endBalance: calcSubtotal(impairmentMatrixRows.value.map((r) => r.endBalance)),
  }))

  /** 净值合计 = 原值期末 - 摊销期末 - 减值期末 */
  const netValueTotal = computed(() =>
    costTotal.value.endBalance - amortTotal.value.endBalance - impairmentTotal.value.endBalance,
  )

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadData(): void {
    const prefix = itemPrefix.value

    // 矩阵行
    costMatrixRows.value = _loadMatrixRows(`${prefix}-cost-matrix`)
    amortMatrixRows.value = _loadMatrixRows(`${prefix}-amort-matrix`)
    impairmentMatrixRows.value = _loadMatrixRows(`${prefix}-impairment-matrix`)

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

  function _loadMatrixRows(itemId: string): I1DisclosureMatrixRow[] {
    const item = allResponses.value.get(itemId)
    if (!item?.remark) return []
    try {
      const parsed = JSON.parse(item.remark)
      return Array.isArray(parsed) ? parsed : []
    } catch { return [] }
  }

  // ─── Auto-fill from cross-sheet (Req 14.2) ────────────────────────────────

  /**
   * 从审定表/明细表/摊销表自动取数填入附注对应位置。
   * 用户可手工覆盖自动值。
   */
  function applyAutoFill(): void {
    const data = autoFilledData.value
    if (!data || Object.keys(data).length === 0) return

    // 如果矩阵行为空，根据自动数据初始化默认行
    if (costMatrixRows.value.length === 0 && data['disc_cost_end'] != null) {
      costMatrixRows.value = [{
        rowId: 'auto-cost-total',
        category: '合计',
        beginBalance: data['disc_cost_begin'] ?? 0,
        increase: data['disc_cost_increase'] ?? 0,
        decrease: data['disc_cost_decrease'] ?? 0,
        endBalance: data['disc_cost_end'] ?? 0,
        isAutoFilled: true,
      }]
    }

    if (amortMatrixRows.value.length === 0 && data['disc_amort_end'] != null) {
      amortMatrixRows.value = [{
        rowId: 'auto-amort-total',
        category: '合计',
        beginBalance: data['disc_amort_begin'] ?? 0,
        increase: data['disc_amort_provision'] ?? 0,
        decrease: data['disc_amort_transfer'] ?? 0,
        endBalance: data['disc_amort_end'] ?? 0,
        isAutoFilled: true,
      }]
    }

    if (impairmentMatrixRows.value.length === 0 && data['disc_impair_end'] != null) {
      impairmentMatrixRows.value = [{
        rowId: 'auto-impair-total',
        category: '合计',
        beginBalance: data['disc_impair_begin'] ?? 0,
        increase: data['disc_impair_provision'] ?? 0,
        decrease: data['disc_impair_reversal'] ?? 0,
        endBalance: data['disc_impair_end'] ?? 0,
        isAutoFilled: true,
      }]
    }
  }

  // ─── CRUD: 动态行 ─────────────────────────────────────────────────────────

  function addDynamicRow(sectionKey: string, name: string): void {
    const rows = sectionRows.value[sectionKey]
    if (!rows) return
    rows.push({
      rowId: `i1disc-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
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

  function updateDynamicRow(sectionKey: string, rowId: string, field: keyof I1DisclosureDynamicRow, value: any): void {
    const rows = sectionRows.value[sectionKey]
    if (!rows) return
    const row = rows.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _persistSection(sectionKey)
  }

  // ─── Update: 矩阵行 ───────────────────────────────────────────────────────

  function updateMatrixCell(
    layer: 'cost' | 'amort' | 'impairment',
    rowId: string,
    field: keyof I1DisclosureMatrixRow,
    value: any,
  ): void {
    const target = layer === 'cost'
      ? costMatrixRows
      : layer === 'amort'
        ? amortMatrixRows
        : impairmentMatrixRows
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

    // EventBus发布 'disclosure:note-text-updated' (Req 14.4)
    _publishNoteEvent(sectionKey, note)
  }

  // ─── AI辅助生成文字描述 (Req 14.3) ────────────────────────────────────────

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
        section: `i1-disclosure-${variant.value}-${sectionKey}`,
        prompt: `请为无形资产附注"${_getSectionTitle(sectionKey)}"生成披露文字描述`,
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
   * AI生成并确认后写入（弹确认预览再填入模式）
   */
  async function applyAiGeneratedNote(sectionKey: string, text: string): Promise<void> {
    sectionNotes.value[sectionKey] = text
    const prefix = itemPrefix.value
    options?.onSave?.(`${prefix}-${sectionKey}-note`, text)
    _publishNoteEvent(sectionKey, text)
  }

  // ─── EventBus 发布 (Req 14.4) ─────────────────────────────────────────────

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
        wpCode: 'I1',
        variant: variant.value,
        sections: sectionsArr,
      }

      // 全局 CustomEvent（标准D~N附注EventBus模式）
      window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
        detail: payload,
      }))
    }, 300)
  }

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _buildAiContext(sectionKey: string): string {
    const data = autoFilledData.value
    const parts: string[] = [
      `科目: 无形资产(1701)+累计摊销(1702)+减值准备(1703)`,
      `版本: ${variant.value === 'listed' ? '上市公司' : '国有企业'}`,
    ]
    if (data['disc_cost_end'] != null) parts.push(`原值期末: ${data['disc_cost_end']}`)
    if (data['disc_amort_end'] != null) parts.push(`摊销期末: ${data['disc_amort_end']}`)
    if (data['disc_impair_end'] != null) parts.push(`减值期末: ${data['disc_impair_end']}`)
    if (data['disc_net_value'] != null) parts.push(`净值: ${data['disc_net_value']}`)
    if (data['disc_amort_total'] != null) parts.push(`本期摊销总额: ${data['disc_amort_total']}`)
    if (data['disc_asset_count'] != null) parts.push(`资产数: ${data['disc_asset_count']}`)
    if (data['disc_indefinite_count'] != null) parts.push(`使用寿命不确定: ${data['disc_indefinite_count']}`)
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
    const target = layer === 'cost'
      ? costMatrixRows
      : layer === 'amort'
        ? amortMatrixRows
        : impairmentMatrixRows
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
    costMatrixRows,
    amortMatrixRows,
    impairmentMatrixRows,
    sectionRows,
    sectionNotes,
    // Computed
    sections,
    autoFilledData,
    costTotal,
    amortTotal,
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

export default useI1Disclosure
