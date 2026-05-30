import { describe, it, expect, vi } from 'vitest'
import { ref, computed, nextTick } from 'vue'
import { useEControlConclusion } from './useEControlConclusion'
import type { EControlTestSchema } from '../../GtEControlTest.types'

function buildSchema(options?: { value: string; label: string }[]): EControlTestSchema {
  return {
    test_type: 'evaluation_step',
    conclusion: {
      mode: 'single',
      options: options ?? [
        { value: 'control_effective', label: '控制有效' },
        { value: 'extended_effective', label: '扩大有效' },
        { value: 'deviation_remains', label: '仍有偏差' },
        { value: 'systemic_deviation', label: '系统性偏差' },
      ],
    },
  }
}

function setup(overrides?: { testType?: string; schemaOverride?: EControlTestSchema }) {
  const conclusionValue = ref('')
  const testType = ref(overrides?.testType ?? 'evaluation_step')
  const schema = ref<EControlTestSchema>(overrides?.schemaOverride ?? buildSchema())
  const evalData = ref<Record<string, any>>({})
  const singleData = ref<Record<string, any>>({})
  const emitFn = vi.fn()
  const debounceSave = vi.fn()

  const result = useEControlConclusion({
    props: { wpId: 'wp-001', sheetName: '评价控制偏差' },
    testType,
    conclusionValue,
    schema: computed(() => schema.value),
    evalData,
    singleData,
    emit: emitFn as any,
    debounceSave,
  })

  return { ...result, conclusionValue, testType, schema, evalData, singleData, emitFn, debounceSave }
}

describe('useEControlConclusion', () => {
  describe('deriveSuggestion', () => {
    it('control_effective → reduce', () => {
      const { deriveSuggestion } = setup()
      expect(deriveSuggestion('control_effective')).toBe('reduce')
    })

    it('extended_effective → reduce', () => {
      const { deriveSuggestion } = setup()
      expect(deriveSuggestion('extended_effective')).toBe('reduce')
    })

    it('effective → reduce', () => {
      const { deriveSuggestion } = setup()
      expect(deriveSuggestion('effective')).toBe('reduce')
    })

    it('deviation_remains → increase', () => {
      const { deriveSuggestion } = setup()
      expect(deriveSuggestion('deviation_remains')).toBe('increase')
    })

    it('ineffective → increase', () => {
      const { deriveSuggestion } = setup()
      expect(deriveSuggestion('ineffective')).toBe('increase')
    })

    it('systemic_deviation → full', () => {
      const { deriveSuggestion } = setup()
      expect(deriveSuggestion('systemic_deviation')).toBe('full')
    })

    it('unknown value → none', () => {
      const { deriveSuggestion } = setup()
      expect(deriveSuggestion('some_unknown')).toBe('none')
    })

    it('empty string → none', () => {
      const { deriveSuggestion } = setup()
      expect(deriveSuggestion('')).toBe('none')
    })
  })

  describe('deriveConfidence', () => {
    it('systemic_deviation → required', () => {
      const { deriveConfidence } = setup()
      expect(deriveConfidence('systemic_deviation')).toBe('required')
    })

    it('control_effective → high', () => {
      const { deriveConfidence } = setup()
      expect(deriveConfidence('control_effective')).toBe('high')
    })

    it('extended_effective → high', () => {
      const { deriveConfidence } = setup()
      expect(deriveConfidence('extended_effective')).toBe('high')
    })

    it('deviation_remains → high', () => {
      const { deriveConfidence } = setup()
      expect(deriveConfidence('deviation_remains')).toBe('high')
    })

    it('unknown value → medium', () => {
      const { deriveConfidence } = setup()
      expect(deriveConfidence('some_other')).toBe('medium')
    })
  })

  describe('onConclusionChange', () => {
    it('emits conclusion-change with string value', () => {
      const { onConclusionChange, emitFn } = setup()
      onConclusionChange('control_effective')
      expect(emitFn).toHaveBeenCalledWith('conclusion-change', 'control_effective')
    })

    it('emits trigger-procedure-trimming-suggestion for control_effective', () => {
      const { onConclusionChange, emitFn } = setup()
      onConclusionChange('control_effective')
      expect(emitFn).toHaveBeenCalledWith('trigger-procedure-trimming-suggestion', {
        wp_id: 'wp-001',
        sheet_name: '评价控制偏差',
        conclusion: 'control_effective',
        suggestion_type: 'reduce',
        confidence: 'high',
        source: 'e-control-test',
      })
    })

    it('does NOT emit trigger-procedure-trimming-suggestion for empty conclusion', () => {
      const { onConclusionChange, emitFn } = setup()
      onConclusionChange('')
      expect(emitFn).toHaveBeenCalledWith('conclusion-change', '')
      expect(emitFn).not.toHaveBeenCalledWith(
        'trigger-procedure-trimming-suggestion',
        expect.anything(),
      )
    })

    it('syncs conclusion to evalData.final_conclusion for evaluation_step', () => {
      const { onConclusionChange, evalData } = setup({ testType: 'evaluation_step' })
      onConclusionChange('deviation_remains')
      expect(evalData.value.final_conclusion).toBe('deviation_remains')
    })

    it('syncs conclusion to singleData.conclusion for single mode', () => {
      const { onConclusionChange, singleData } = setup({ testType: 'single' })
      onConclusionChange('control_effective')
      expect(singleData.value.conclusion).toBe('control_effective')
    })

    it('calls debounceSave after conclusion change', () => {
      const { onConclusionChange, debounceSave } = setup()
      onConclusionChange('systemic_deviation')
      expect(debounceSave).toHaveBeenCalledTimes(1)
    })

    it('handles undefined value gracefully (coerces to empty string)', () => {
      const { onConclusionChange, conclusionValue, emitFn } = setup()
      onConclusionChange(undefined)
      expect(conclusionValue.value).toBe('')
      expect(emitFn).toHaveBeenCalledWith('conclusion-change', '')
    })
  })

  describe('conclusionOptions', () => {
    it('returns options from schema.conclusion.options', () => {
      const { conclusionOptions } = setup()
      expect(conclusionOptions.value).toHaveLength(4)
      expect(conclusionOptions.value.map(o => o.value)).toEqual([
        'control_effective',
        'extended_effective',
        'deviation_remains',
        'systemic_deviation',
      ])
    })

    it('returns empty array when schema has no conclusion', () => {
      const { conclusionOptions } = setup({ schemaOverride: { test_type: 'single' } })
      expect(conclusionOptions.value).toEqual([])
    })
  })
})
