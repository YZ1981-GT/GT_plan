/**
 * useEControlPersist — 数据初始化 + debounce save for GtEControlTest shell
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import type { StepDef, HintBlock, EControlTestSchema, SummaryRow, EControlTestData } from '../../GtEControlTest.types'

export function useEControlPersist(opts: {
  props: { schema: EControlTestSchema; htmlData: EControlTestData; readonly?: boolean }
  testType: ComputedRef<string>
  steps: ComputedRef<StepDef[]>
  hints: ComputedRef<HintBlock[]>
  summaryRows: Ref<SummaryRow[]>
  singleData: Ref<Record<string, any>>
  evalData: Ref<Record<string, any>>
  activeStepNo: Ref<number>
  conclusionValue: Ref<string>
  activeHintIds: Ref<string[]>
  assistedFieldsList: ComputedRef<string[]>
  emit: (e: 'save', data: EControlTestData) => void
}) {
  const { props: p, testType, steps, hints, summaryRows, singleData, evalData, activeStepNo, conclusionValue, activeHintIds, assistedFieldsList, emit } = opts
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  function initData() {
    const data = p.htmlData ?? {}
    summaryRows.value = Array.isArray(data.rows) ? JSON.parse(JSON.stringify(data.rows)) : []
    const fieldsData: Record<string, any> = data.fields && typeof data.fields === 'object' ? { ...data.fields } : {}
    singleData.value = { ...fieldsData }
    const stepsData = data.steps && typeof data.steps === 'object' ? data.steps : {}
    const merged: Record<string, any> = { ...fieldsData }
    for (const stepKey of Object.keys(stepsData)) {
      const stepFields = stepsData[stepKey]
      if (stepFields && typeof stepFields === 'object') Object.assign(merged, stepFields)
    }
    evalData.value = merged
    activeStepNo.value = typeof data.active_step === 'number' ? data.active_step : (steps.value[0]?.step ?? 1)
    conclusionValue.value = typeof data.conclusion === 'string' ? data.conclusion : ''
    const activeIds = new Set<string>(Array.isArray(data.active_hint_ids) ? data.active_hint_ids : [])
    for (const h of hints.value) { if (h.default_collapsed === false) activeIds.add(h.id) }
    activeHintIds.value = Array.from(activeIds)
  }

  function buildSavePayload(): EControlTestData {
    const payload: EControlTestData = {
      active_step: activeStepNo.value,
      active_hint_ids: [...activeHintIds.value],
      conclusion: conclusionValue.value,
      ai_assisted_fields: assistedFieldsList.value.length > 0 ? assistedFieldsList.value : undefined,
    }
    if (testType.value === 'summary') {
      payload.rows = JSON.parse(JSON.stringify(summaryRows.value))
    } else if (testType.value === 'single') {
      payload.fields = JSON.parse(JSON.stringify(singleData.value))
    } else if (testType.value === 'evaluation_step') {
      const stepsBucket: Record<string, Record<string, any>> = {}
      const topFieldNames = new Set((p.schema.fields ?? []).map(f => f.name))
      const topFields: Record<string, any> = {}
      const allEval = JSON.parse(JSON.stringify(evalData.value))
      for (const step of steps.value) {
        stepsBucket[String(step.step)] = {}
        for (const f of (step.fields || [])) { if (f.name in allEval) stepsBucket[String(step.step)][f.name] = allEval[f.name] }
      }
      for (const name of Object.keys(allEval)) { if (topFieldNames.has(name)) topFields[name] = allEval[name] }
      payload.fields = topFields
      payload.steps = stepsBucket
    }
    return payload
  }

  function debounceSave() {
    if (p.readonly) return
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => { emit('save', buildSavePayload()) }, 1500)
  }

  onBeforeUnmount(() => { if (saveTimer) { clearTimeout(saveTimer); saveTimer = null } })

  return { initData, buildSavePayload, debounceSave }
}
