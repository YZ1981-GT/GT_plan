/**
 * useH3PolicyCheck — H3-4 会计政策检查 composable
 *
 * CAS3五段落结构 + 计量模式突出显示 + 各段conclusion(Y/N/NA)
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.9
 * Requirements: 5.1-5.5
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface PolicySection {
  id: string
  title: string
  regulation: string          // 准则条款引用
  actualPolicy: string        // 实际政策(textarea)
  auditorComment: string      // 审计师评价
  conclusion: 'Y' | 'N' | 'NA' | ''
}

// ─── Constants ───────────────────────────────────────────────────────────────

const SECTIONS: { id: string; title: string; regulation: string }[] = [
  { id: 'recognition', title: '(1) 投资性房地产确认条件', regulation: 'CAS3第3-5条' },
  { id: 'measurement', title: '(2) 计量模式选择(成本/公允价值)', regulation: 'CAS3第9-11条' },
  { id: 'subsequent', title: '(3) 后续计量政策', regulation: 'CAS3第11-12条' },
  { id: 'transfer', title: '(4) 转换政策', regulation: 'CAS3第12-15条' },
  { id: 'disposal', title: '(5) 处置政策', regulation: 'CAS3第16-18条' },
]

const ITEM_PREFIX = 'H3-4-policy'

export function useH3PolicyCheck(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
  measurementModel: Ref<string>
}) {
  const { allResponses, getValue, setValue, measurementModel } = params
  const sections = ref<PolicySection[]>([])

  function loadSections(): void {
    sections.value = SECTIONS.map((s) => {
      const raw = getValue(`${ITEM_PREFIX}-${s.id}`)
      const data = typeof raw === 'object' && raw ? raw : {}
      return {
        id: s.id,
        title: s.title,
        regulation: s.regulation,
        actualPolicy: data.actualPolicy ?? '',
        auditorComment: data.auditorComment ?? '',
        conclusion: data.conclusion ?? '',
      }
    })
  }

  function updateSection(sectionId: string, field: keyof PolicySection, value: string): void {
    const section = sections.value.find((s) => s.id === sectionId)
    if (!section) return
    ;(section as any)[field] = value
    setValue(`${ITEM_PREFIX}-${sectionId}`, {
      actualPolicy: section.actualPolicy,
      auditorComment: section.auditorComment,
      conclusion: section.conclusion,
    })
  }

  /** 当前计量模式标签（用于突出显示） */
  const currentModelLabel = computed(() =>
    measurementModel.value === 'cost' ? '成本模式' : '公允价值模式',
  )

  /** 整体进度（已填结论数/总数） */
  const progress = computed(() => {
    const filled = sections.value.filter((s) => s.conclusion !== '').length
    return { filled, total: sections.value.length, percent: Math.round(filled / sections.value.length * 100) }
  })

  /** 整体结论：全部Y=通过, 有N=不通过, 否则未完成 */
  const overallConclusion = computed(() => {
    if (sections.value.some((s) => s.conclusion === 'N')) return 'N'
    if (sections.value.every((s) => s.conclusion === 'Y' || s.conclusion === 'NA')) return 'Y'
    return ''
  })

  watch(allResponses, () => loadSections(), { immediate: true })

  return { sections, currentModelLabel, progress, overallConclusion, updateSection, loadSections }
}

export default useH3PolicyCheck
