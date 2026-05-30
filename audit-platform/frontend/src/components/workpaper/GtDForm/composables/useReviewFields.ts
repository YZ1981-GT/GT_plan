/**
 * useReviewFields — 步骤字段联动 composable
 *
 * 包含：setStepField / onChecklistChange / stepsData / computedFields / dirty tracking / onContextChange / debounce save
 * 参数：props (schema fields/steps, htmlData) + emit + readonly ref
 * 返回：stepsData / contextData / setStepField() / onChecklistChange() / onContextChange() / debounceSave()
 */
import { ref, computed, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

interface FieldDef {
  name: string
  label: string
  type?: string
  cell?: string
  enum?: string[]
  readonly?: boolean
  required?: boolean
  hint?: string
  max_length?: number
  min?: number
  max?: number
  default?: any
  source?: string
}

interface ChecklistItem {
  id: string
  label: string
  cell?: string
  required?: boolean
  render?: string
}

interface CommentFieldDef {
  name: string
  label?: string
  type?: string
  cell?: string
  max_length?: number
}

interface ReviewStepDef {
  step: number
  id?: string
  title?: string
  description?: string
  checklist?: ChecklistItem[]
  comment_field?: CommentFieldDef
  fields?: FieldDef[]
  linked_workpapers?: any[]
  signature?: any[]
  is_terminal?: boolean
}

interface ConclusionDef {
  mode?: 'single' | string
  cell?: string
  options?: any[]
  mutual_exclusive?: boolean
  required?: boolean
}

interface StepBucket {
  checklist: Record<string, boolean>
  comment: string
  fields: Record<string, any>
}

interface FieldChangePayload {
  field_name: string
  old_value?: any
  new_value?: any
  cell?: string
}

interface SignatureRecord {
  signed_by: string
  signed_at: string
  cell?: string
}

interface AuditLogEntry {
  from: string
  to: string
  trigger: string
  user?: string
  timestamp: string
  reason?: string
}

interface ReviewData {
  context?: Record<string, any>
  steps?: Record<string, StepBucket>
  active_step?: number
  state?: string
  signatures?: Record<string, SignatureRecord>
  audit_log?: AuditLogEntry[]
  conclusion?: string
  [key: string]: any
}

interface UseReviewFieldsParams {
  getContextFields: () => FieldDef[]
  getReviewSteps: () => ReviewStepDef[]
  getConclusionDef: () => ConclusionDef | null
  getHtmlData: () => ReviewData
  getCurrentState: () => string
  getSignatures: () => Record<string, SignatureRecord>
  getAuditLog: () => AuditLogEntry[]
  isReadonly: () => boolean
  emit: {
    fieldChange: (payload: FieldChangePayload) => void
    save: (data: ReviewData) => void
  }
}

export interface UseReviewFieldsReturn {
  contextData: Ref<Record<string, any>>
  stepsData: Ref<Record<string, StepBucket>>
  activeStepIdx: Ref<number>
  conclusionValue: Ref<string>
  contextFields: ComputedRef<FieldDef[]>
  reviewSteps: ComputedRef<ReviewStepDef[]>
  currentStep: ComputedRef<ReviewStepDef | null>
  hasConclusion: ComputedRef<boolean>
  conclusionOptions: ComputedRef<any[]>
  setStepField: (step: ReviewStepDef, field: FieldDef, value: any) => void
  onChecklistChange: (step: ReviewStepDef, item: ChecklistItem, value: boolean | unknown) => void
  setStepComment: (step: ReviewStepDef, value: string) => void
  onContextChange: (field: FieldDef, value: any) => void
  onConclusionChange: (value: string | number | boolean | undefined) => void
  goToStep: (idx: number) => void
  stepKey: (step: ReviewStepDef) => string
  stepShortTitle: (step: ReviewStepDef) => string
  stepShortDesc: (step: ReviewStepDef) => string
  stepStatus: (idx: number) => 'wait' | 'process' | 'finish' | 'success' | 'error'
  stepFieldsBucket: (step: ReviewStepDef) => Record<string, any>
  stepFieldValue: (step: ReviewStepDef, field: FieldDef) => any
  checklistValue: (step: ReviewStepDef, item: ChecklistItem) => boolean
  commentValue: (step: ReviewStepDef) => string
  debounceSave: () => void
  buildSavePayload: () => ReviewData
  initFields: () => void
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useReviewFields(params: UseReviewFieldsParams): UseReviewFieldsReturn {
  const { getContextFields, getReviewSteps, getConclusionDef, getHtmlData, getCurrentState, getSignatures, getAuditLog, isReadonly, emit } = params

  // ─── Refs ──────────────────────────────────────────────────────────────────
  const contextData = ref<Record<string, any>>({})
  const stepsData = ref<Record<string, StepBucket>>({})
  const activeStepIdx = ref<number>(0)
  const conclusionValue = ref<string>('')

  let saveTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Computed ──────────────────────────────────────────────────────────────

  const contextFields = computed<FieldDef[]>(() => getContextFields())
  const reviewSteps = computed<ReviewStepDef[]>(() => getReviewSteps())

  const currentStep = computed<ReviewStepDef | null>(
    () => reviewSteps.value[activeStepIdx.value] ?? null
  )

  const conclusionDef = computed<ConclusionDef | null>(() => getConclusionDef())

  const hasConclusion = computed(
    () => conclusionDef.value?.mode === 'single' && !!(conclusionDef.value?.options?.length)
  )

  const conclusionOptions = computed<any[]>(
    () => conclusionDef.value?.options || []
  )

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function stepKey(step: ReviewStepDef): string {
    return `step_${step.step}`
  }

  function stepShortTitle(step: ReviewStepDef): string {
    const title = step.title || `步骤 ${step.step}`
    const m = title.match(/^步骤\s*\d+\s*[:：]\s*(.+)$/)
    return m ? m[1] : title
  }

  function stepShortDesc(step: ReviewStepDef): string {
    const desc = step.description || ''
    if (desc.length <= 24) return desc
    return desc.slice(0, 22) + '…'
  }

  function stepStatus(idx: number): 'wait' | 'process' | 'finish' | 'success' | 'error' {
    if (idx < activeStepIdx.value) return 'finish'
    if (idx === activeStepIdx.value) return 'process'
    return 'wait'
  }

  function stepFieldsBucket(step: ReviewStepDef): Record<string, any> {
    return stepsData.value[stepKey(step)]?.fields || {}
  }

  function stepFieldValue(step: ReviewStepDef, field: FieldDef): any {
    return stepsData.value[stepKey(step)]?.fields?.[field.name]
  }

  function checklistValue(step: ReviewStepDef, item: ChecklistItem): boolean {
    return !!stepsData.value[stepKey(step)]?.checklist?.[item.id]
  }

  function commentValue(step: ReviewStepDef): string {
    return stepsData.value[stepKey(step)]?.comment ?? ''
  }

  // ─── Field handlers ────────────────────────────────────────────────────────

  function setStepField(step: ReviewStepDef, field: FieldDef, value: any) {
    const key = stepKey(step)
    if (!stepsData.value[key]) {
      stepsData.value[key] = { checklist: {}, comment: '', fields: {} }
    }
    const oldValue = stepsData.value[key].fields[field.name]
    stepsData.value[key].fields[field.name] = value
    emit.fieldChange({
      field_name: `${key}.${field.name}`,
      old_value: oldValue,
      new_value: value,
      cell: field.cell,
    })
    debounceSave()
  }

  function onChecklistChange(step: ReviewStepDef, item: ChecklistItem, value: boolean | unknown) {
    const key = stepKey(step)
    if (!stepsData.value[key]) {
      stepsData.value[key] = { checklist: {}, comment: '', fields: {} }
    }
    const oldValue = !!stepsData.value[key].checklist[item.id]
    const newValue = !!value
    stepsData.value[key].checklist[item.id] = newValue
    emit.fieldChange({
      field_name: `${key}.checklist.${item.id}`,
      old_value: oldValue,
      new_value: newValue,
      cell: item.cell,
    })
    debounceSave()
  }

  function setStepComment(step: ReviewStepDef, value: string) {
    const key = stepKey(step)
    if (!stepsData.value[key]) {
      stepsData.value[key] = { checklist: {}, comment: '', fields: {} }
    }
    const oldValue = stepsData.value[key].comment
    stepsData.value[key].comment = value
    emit.fieldChange({
      field_name: `${key}.comment`,
      old_value: oldValue,
      new_value: value,
      cell: step.comment_field?.cell,
    })
    debounceSave()
  }

  function onContextChange(field: FieldDef, value: any) {
    const oldValue = contextData.value[field.name]
    contextData.value[field.name] = value
    emit.fieldChange({
      field_name: `context.${field.name}`,
      old_value: oldValue,
      new_value: value,
      cell: field.cell,
    })
    debounceSave()
  }

  function goToStep(idx: number) {
    if (idx < 0 || idx >= reviewSteps.value.length) return
    activeStepIdx.value = idx
    debounceSave()
  }

  function onConclusionChange(value: string | number | boolean | undefined) {
    const v = typeof value === 'string' ? value : String(value ?? '')
    const oldValue = conclusionValue.value
    conclusionValue.value = v
    emit.fieldChange({
      field_name: 'conclusion',
      old_value: oldValue,
      new_value: v,
      cell: conclusionDef.value?.cell,
    })
    debounceSave()
  }

  // ─── Save payload + debounce ───────────────────────────────────────────────

  function buildSavePayload(): ReviewData {
    return {
      ...(getHtmlData() || {}),
      context: { ...contextData.value },
      steps: JSON.parse(JSON.stringify(stepsData.value)),
      active_step: activeStepIdx.value,
      state: getCurrentState(),
      signatures: { ...getSignatures() },
      audit_log: [...getAuditLog()],
      conclusion: conclusionValue.value,
    }
  }

  function debounceSave() {
    if (isReadonly()) return
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      emit.save(buildSavePayload())
    }, 1500)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  function initFields() {
    const data = (getHtmlData() ?? {}) as ReviewData

    // 上下文
    const ctxIn = data.context && typeof data.context === 'object' ? data.context : {}
    const ctxOut: Record<string, any> = {}
    for (const f of getContextFields()) {
      ctxOut[f.name] = (ctxIn as Record<string, any>)[f.name] ?? (f.default ?? '')
    }
    contextData.value = ctxOut

    // 步骤数据
    const stepsIn = data.steps && typeof data.steps === 'object' ? data.steps : {}
    const stepsOut: Record<string, StepBucket> = {}
    for (const step of getReviewSteps()) {
      const key = stepKey(step)
      const bucketIn = (stepsIn as Record<string, any>)[key] || {}
      const checklistOut: Record<string, boolean> = {}
      for (const item of step.checklist || []) {
        checklistOut[item.id] = !!bucketIn?.checklist?.[item.id]
      }
      const fieldsOut: Record<string, any> = {}
      for (const f of step.fields || []) {
        fieldsOut[f.name] = bucketIn?.fields?.[f.name] ?? (f.default ?? (f.type === 'number' ? null : ''))
      }
      stepsOut[key] = {
        checklist: checklistOut,
        comment: typeof bucketIn?.comment === 'string' ? bucketIn.comment : '',
        fields: fieldsOut,
      }
    }
    stepsData.value = stepsOut

    // 激活步骤
    if (typeof data.active_step === 'number' && data.active_step >= 0 && data.active_step < getReviewSteps().length) {
      activeStepIdx.value = data.active_step
    } else {
      activeStepIdx.value = 0
    }

    // 结论
    conclusionValue.value = typeof data.conclusion === 'string' ? data.conclusion : ''
  }

  // ─── Cleanup ───────────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
  })

  return {
    contextData,
    stepsData,
    activeStepIdx,
    conclusionValue,
    contextFields,
    reviewSteps,
    currentStep,
    hasConclusion,
    conclusionOptions,
    setStepField,
    onChecklistChange,
    setStepComment,
    onContextChange,
    onConclusionChange,
    goToStep,
    stepKey,
    stepShortTitle,
    stepShortDesc,
    stepStatus,
    stepFieldsBucket,
    stepFieldValue,
    checklistValue,
    commentValue,
    debounceSave,
    buildSavePayload,
    initFields,
  }
}
