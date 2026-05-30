// ─── useEControlConclusion.ts ─────────────────────────────────────────────────
// Extracted from GtEControlTest.vue: conclusion derivation + ProcedureTrimming suggestion
// Requirements: 12, 13

import { computed, type Ref } from 'vue'
import type {
  ConclusionBlock,
  ConclusionOption,
  EControlTestSchema,
  SuggestionPayload,
} from '../../GtEControlTest.types'

export interface UseEControlConclusionOpts {
  props: { wpId: string; sheetName: string }
  testType: Ref<string>
  conclusionValue: Ref<string>
  schema: Ref<EControlTestSchema>
  evalData: Ref<Record<string, any>>
  singleData: Ref<Record<string, any>>
  emit: {
    (e: 'conclusion-change', conclusion: string): void
    (e: 'trigger-procedure-trimming-suggestion', payload: SuggestionPayload): void
  }
  debounceSave: () => void
}

export function useEControlConclusion(opts: UseEControlConclusionOpts) {
  const { props, testType, conclusionValue, schema, evalData, singleData, emit, debounceSave } = opts

  const conclusionBlock = computed<ConclusionBlock | null>(() => schema.value?.conclusion ?? null)

  const conclusionOptions = computed<ConclusionOption[]>(() => conclusionBlock.value?.options ?? [])

  function deriveSuggestion(conclusion: string): SuggestionPayload['suggestion_type'] {
    if (conclusion === 'control_effective' || conclusion === 'extended_effective' || conclusion === 'effective') {
      return 'reduce'
    }
    if (conclusion === 'deviation_remains' || conclusion === 'ineffective') {
      return 'increase'
    }
    if (conclusion === 'systemic_deviation') {
      return 'full'
    }
    return 'none'
  }

  function deriveConfidence(conclusion: string): SuggestionPayload['confidence'] {
    if (conclusion === 'systemic_deviation') return 'required'
    if (conclusion === 'control_effective' || conclusion === 'extended_effective') return 'high'
    if (conclusion === 'deviation_remains') return 'high'
    return 'medium'
  }

  function onConclusionChange(value: string | number | boolean | undefined) {
    const conclusion = String(value ?? '')
    conclusionValue.value = conclusion
    emit('conclusion-change', conclusion)

    // 控制有效 / 扩大有效 / 仍有偏差 / 系统性偏差 全部触发 ProcedureTrimming 建议
    // （差异由 suggestion_type + confidence 体现）
    const suggestion_type = deriveSuggestion(conclusion)
    if (suggestion_type !== 'none') {
      const payload: SuggestionPayload = {
        wp_id: props.wpId,
        sheet_name: props.sheetName,
        conclusion,
        suggestion_type,
        confidence: deriveConfidence(conclusion),
        source: 'e-control-test',
      }
      emit('trigger-procedure-trimming-suggestion', payload)
    }

    // 同步回 evalData 的 final_conclusion 字段（双向）
    if (testType.value === 'evaluation_step') {
      evalData.value.final_conclusion = conclusion
    } else if (testType.value === 'single') {
      singleData.value.conclusion = conclusion
    }
    debounceSave()
  }

  return { conclusionBlock, conclusionOptions, deriveSuggestion, deriveConfidence, onConclusionChange }
}
