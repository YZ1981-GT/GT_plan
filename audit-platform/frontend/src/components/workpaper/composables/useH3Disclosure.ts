/**
 * useH3Disclosure — 附注披露 composable（variant双版本：listed/soe）
 *
 * variant参数（listed/soe）双版本 + 含计量模式说明 + 跨sheet取数 + EventBus
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.19
 * Requirements: 15.1-15.7
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem } from './useH3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export type DisclosureVariant = 'listed' | 'soe'

export interface DisclosureSection {
  id: string
  title: string
  content: string             // textarea内容
  autoData: Record<string, number>  // 跨sheet自动取数
}

// ─── Constants ───────────────────────────────────────────────────────────────

const LISTED_SECTIONS = [
  { id: 'measurement', title: '(一) 计量模式说明' },
  { id: 'category', title: '(二) 投资性房地产分类及变动' },
  { id: 'transfer', title: '(三) 投资性房地产转换' },
  { id: 'rental', title: '(四) 租金收入' },
  { id: 'fairChange', title: '(五) 公允价值变动损益' },
  { id: 'pledge', title: '(六) 受限情况' },
]

const SOE_SECTIONS = [
  { id: 'measurement', title: '(一) 计量模式说明' },
  { id: 'category', title: '(二) 投资性房地产分类及变动' },
  { id: 'depreciation', title: '(三) 折旧/摊销' },
  { id: 'transfer', title: '(四) 投资性房地产转换' },
  { id: 'impairment', title: '(五) 减值准备' },
  { id: 'rental', title: '(六) 租金收入' },
  { id: 'pledge', title: '(七) 受限情况' },
]

const ITEM_PREFIX = 'H3-disc'

export function useH3Disclosure(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
  measurementModel: Ref<string>
  variant: Ref<DisclosureVariant>
  /** 跨sheet自动取数（来自useH3CrossSheet.disclosureAutoFill） */
  disclosureAutoFill?: ComputedRef<Record<string, number>>
}) {
  const { allResponses, getValue, setValue, measurementModel, variant, disclosureAutoFill } = params

  const sections = ref<DisclosureSection[]>([])

  /** 根据variant选择段落结构 */
  const sectionDefs = computed(() =>
    variant.value === 'listed' ? LISTED_SECTIONS : SOE_SECTIONS,
  )

  function loadSections(): void {
    sections.value = sectionDefs.value.map((def) => {
      const raw = getValue(`${ITEM_PREFIX}-${variant.value}-${def.id}`)
      const data = typeof raw === 'object' && raw ? raw : {}
      return {
        id: def.id,
        title: def.title,
        content: data.content ?? '',
        autoData: disclosureAutoFill?.value ?? {},
      }
    })
  }

  function updateSection(sectionId: string, content: string): void {
    const section = sections.value.find((s) => s.id === sectionId)
    if (!section) return
    section.content = content
    setValue(`${ITEM_PREFIX}-${variant.value}-${sectionId}`, { content })
  }

  /** 计量模式描述文案 */
  const measurementDesc = computed(() => {
    if (measurementModel.value === 'cost') {
      return '本公司对投资性房地产采用成本模式进行后续计量，按其预计使用寿命及预计净残值率对投资性房地产计提折旧。'
    }
    return '本公司对投资性房地产采用公允价值模式进行后续计量，不对其计提折旧或摊销，以资产负债表日的公允价值为基础调整其账面价值。'
  })

  /** 刷新跨sheet数据 */
  function refreshAutoData(): void {
    if (disclosureAutoFill?.value) {
      sections.value.forEach((s) => { s.autoData = disclosureAutoFill!.value })
    }
  }

  /** 监听附注事件刷新 */
  function subscribeEvents(): void {
    window.addEventListener('substantive:adjudicated', refreshAutoData)
  }

  function unsubscribeEvents(): void {
    window.removeEventListener('substantive:adjudicated', refreshAutoData)
  }

  watch(allResponses, () => loadSections(), { immediate: true })
  watch(variant, () => loadSections())

  return {
    sections, sectionDefs, measurementDesc,
    updateSection, refreshAutoData, subscribeEvents, unsubscribeEvents, loadSections,
  }
}

export default useH3Disclosure
