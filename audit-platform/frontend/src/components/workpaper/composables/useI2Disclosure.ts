/**
 * useI2Disclosure — I2 开发支出附注披露 composable
 *
 * Variant 双版本（上市公司58×7 / 国有企业17×8），根据 projectContext.business_category 自动选择。
 * - 从审定表+明细表自动取数填入对应附注位置 (Req 12.2)
 * - AI辅助生成文字描述 (Req 12.3)
 * - EventBus: subscribe 'substantive:adjudicated' → refresh;
 *             publish 'disclosure:note-text-updated' (Req 12.3)
 *
 * 持久化：
 * - "I2-disc-listed" / "I2-disc-soe" item_ids
 *
 * Spec: .kiro/specs/i2-development-expenditure/
 * Task: 3.7
 * Requirements: 12.1-12.3
 */
import { ref, computed, watch, onMounted, onUnmounted, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export type I2DisclosureVariant = 'listed' | 'soe'

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** 上市公司附注行（58行×7列） */
export interface I2DisclosureListedRow {
  rowId: string
  /** 项目名称 */
  name: string
  /** 期初余额 */
  beginBalance: number
  /** 本期增加 */
  increase: number
  /** 本期减少(转无形/转费用) */
  decrease: number
  /** 期末余额 */
  endBalance: number
  /** 摊销/减值 */
  impairment: number
  /** 备注 */
  remark: string
  /** 是否自动取数 */
  isAutoFilled: boolean
}

/** 国企附注行（17行×8列） */
export interface I2DisclosureSoeRow {
  rowId: string
  /** 项目名称 */
  name: string
  /** 期初余额 */
  beginBalance: number
  /** 本期增加-资本化 */
  increaseCapitalized: number
  /** 本期增加-费用化转入 */
  increaseExpensed: number
  /** 本期减少-转无形 */
  decreaseToIntangible: number
  /** 本期减少-转费用 */
  decreaseToExpense: number
  /** 期末余额 */
  endBalance: number
  /** 备注 */
  remark: string
  /** 是否自动取数 */
  isAutoFilled: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX_LISTED = 'I2-disc-listed'
const ITEM_PREFIX_SOE = 'I2-disc-soe'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI2Disclosure(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    variant?: Ref<I2DisclosureVariant>
    crossSheetAutoFill?: Ref<Record<string, number>>
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const variant = computed<I2DisclosureVariant>(() => options?.variant?.value ?? 'listed')
  const itemPrefix = computed(() => variant.value === 'listed' ? ITEM_PREFIX_LISTED : ITEM_PREFIX_SOE)
  const isAiGenerating = ref(false)

  /** 上市公司版本行（58行×7列） */
  const listedRows = ref<I2DisclosureListedRow[]>([])

  /** 国企版本行（17行×8列） */
  const soeRows = ref<I2DisclosureSoeRow[]>([])

  /** 附注文字说明 */
  const noteText = ref('')

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadData(): void {
    // 上市公司行
    const listedItem = allResponses.value.get(`${ITEM_PREFIX_LISTED}-rows`)
    if (listedItem?.remark) {
      try {
        const parsed = JSON.parse(listedItem.remark)
        listedRows.value = Array.isArray(parsed) ? parsed : []
      } catch { listedRows.value = [] }
    } else { listedRows.value = [] }

    // 国企行
    const soeItem = allResponses.value.get(`${ITEM_PREFIX_SOE}-rows`)
    if (soeItem?.remark) {
      try {
        const parsed = JSON.parse(soeItem.remark)
        soeRows.value = Array.isArray(parsed) ? parsed : []
      } catch { soeRows.value = [] }
    } else { soeRows.value = [] }

    // 说明文本
    const noteItem = allResponses.value.get(`${itemPrefix.value}-note`)
    noteText.value = (noteItem?.remark ?? '') as string
  }

  // ─── Refresh from Adjudication (Req 12.2) ─────────────────────────────────

  /**
   * 从审定表+明细表自动取数刷新附注。
   * 当收到 'substantive:adjudicated' 事件时自动调用。
   */
  function refreshFromAdjudication(): void {
    const data = options?.crossSheetAutoFill?.value
    if (!data || Object.keys(data).length === 0) return

    // 如上市公司附注行为空，根据自动数据初始化
    if (variant.value === 'listed' && listedRows.value.length === 0 && data['disc_end_total'] != null) {
      listedRows.value = [{
        rowId: 'auto-listed-total',
        name: '开发支出合计',
        beginBalance: data['disc_begin_total'] ?? 0,
        increase: data['disc_increase_total'] ?? 0,
        decrease: data['disc_decrease_total'] ?? 0,
        endBalance: data['disc_end_total'] ?? 0,
        impairment: data['disc_impairment_total'] ?? 0,
        remark: '',
        isAutoFilled: true,
      }]
    }

    if (variant.value === 'soe' && soeRows.value.length === 0 && data['disc_end_total'] != null) {
      soeRows.value = [{
        rowId: 'auto-soe-total',
        name: '开发支出合计',
        beginBalance: data['disc_begin_total'] ?? 0,
        increaseCapitalized: data['disc_increase_capitalized'] ?? 0,
        increaseExpensed: data['disc_increase_expensed'] ?? 0,
        decreaseToIntangible: data['disc_decrease_intangible'] ?? 0,
        decreaseToExpense: data['disc_decrease_expense'] ?? 0,
        endBalance: data['disc_end_total'] ?? 0,
        remark: '',
        isAutoFilled: true,
      }]
    }
  }

  // ─── AI 辅助 (Req 12.3) ───────────────────────────────────────────────────

  /**
   * AI辅助生成附注文字描述。
   * 调用 POST /api/workpapers/{wp_id}/ai/generate-text
   */
  async function generateWithAI(existingContent?: string): Promise<string | null> {
    if (!wpId.value) return null
    isAiGenerating.value = true
    try {
      const context = _buildAiContext()
      const res = await api.post(`/api/workpapers/${wpId.value}/ai/generate-text`, {
        section: `i2-disclosure-${variant.value}`,
        prompt: `请为开发支出附注（${variant.value === 'listed' ? '上市公司' : '国有企业'}版本）生成披露文字描述`,
        context,
        existingContent: existingContent || noteText.value || '',
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

  // ─── Save ──────────────────────────────────────────────────────────────────

  function save(): void {
    options?.onSave?.(`${ITEM_PREFIX_LISTED}-rows`, listedRows.value)
    options?.onSave?.(`${ITEM_PREFIX_SOE}-rows`, soeRows.value)
    options?.onSave?.(`${itemPrefix.value}-note`, noteText.value)
    _publishNoteEvent()
  }

  function saveNoteText(text: string): void {
    noteText.value = text
    options?.onSave?.(`${itemPrefix.value}-note`, text)
    _publishNoteEvent()
  }

  // ─── EventBus: publish (Req 12.3) ─────────────────────────────────────────

  function _publishNoteEvent(): void {
    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
      detail: {
        wpCode: 'I2',
        variant: variant.value,
        sections: ['development-expenditure'],
      },
    }))
  }

  // ─── EventBus: subscribe 'substantive:adjudicated' ─────────────────────────

  function _onAdjudicated(e: Event): void {
    const detail = (e as CustomEvent)?.detail
    if (!detail) return
    // 只处理I2相关的审定事件
    const wpCode = detail?.wpCode ?? detail?.wp_code ?? ''
    if (wpCode && !String(wpCode).startsWith('I2')) return
    refreshFromAdjudication()
  }

  onMounted(() => {
    window.addEventListener('substantive:adjudicated', _onAdjudicated)
  })

  onUnmounted(() => {
    window.removeEventListener('substantive:adjudicated', _onAdjudicated)
  })

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _buildAiContext(): string {
    const data = options?.crossSheetAutoFill?.value ?? {}
    const parts: string[] = [
      '科目: 开发支出(1717)',
      `版本: ${variant.value === 'listed' ? '上市公司(58行×7列)' : '国有企业(17行×8列)'}`,
    ]
    if (data['disc_end_total'] != null) parts.push(`期末合计: ${data['disc_end_total']}`)
    if (data['disc_begin_total'] != null) parts.push(`期初合计: ${data['disc_begin_total']}`)
    if (data['disc_increase_total'] != null) parts.push(`本期增加: ${data['disc_increase_total']}`)
    if (data['disc_decrease_total'] != null) parts.push(`本期减少: ${data['disc_decrease_total']}`)
    if (data['disc_project_count'] != null) parts.push(`研发项目数: ${data['disc_project_count']}`)
    return parts.join('; ')
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadData(), { immediate: true })
  watch(variant, () => _loadData())

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    variant,
    isAiGenerating,
    listedRows,
    soeRows,
    noteText,
    // Actions
    refreshFromAdjudication,
    generateWithAI,
    save,
    saveNoteText,
  }
}

export default useI2Disclosure
