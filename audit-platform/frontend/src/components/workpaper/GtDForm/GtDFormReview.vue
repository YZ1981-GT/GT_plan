<!--
  GtDFormReview.vue — D 类复核记录子组件（Shell）
  拆分为 3 composable：useReviewStateMachine / useReviewSignature / useReviewFields
-->

<template>
  <div class="gt-d-form-review">
    <!-- 顶部头部信息 -->
    <header v-if="hasHeaderInfo" class="gt-dfr__header">
      <div class="gt-dfr__header-meta">
        <span v-if="entityName" class="gt-dfr__entity">{{ entityName }}</span>
        <span v-if="periodEnd" class="gt-dfr__period">{{ periodEnd }}</span>
      </div>
      <div class="gt-dfr__header-right">
        <el-tag v-if="reviewRoleLabel" size="small" type="primary" effect="plain">{{ reviewRoleLabel }}</el-tag>
        <span v-if="indexNo" class="gt-dfr__index">索引号：<strong>{{ indexNo }}</strong></span>
      </div>
    </header>

    <!-- 状态机区 -->
    <section v-if="hasStateMachine" class="gt-dfr__state">
      <div class="gt-dfr__state-row">
        <div class="gt-dfr__state-current">
          <span class="gt-dfr__state-label">复核状态：</span>
          <el-tag :type="currentStateTagType" effect="dark" size="default">{{ currentStateLabel }}</el-tag>
          <span v-if="isFinalState" class="gt-dfr__state-final">（终态）</span>
        </div>
        <div v-if="availableTransitions.length && !props.readonly" class="gt-dfr__state-actions">
          <el-button v-for="t in availableTransitions" :key="`${t.from}->${t.to}`" size="small" :type="transitionButtonType(t)" :disabled="props.readonly" @click="onTransitionClick(t)">{{ transitionButtonLabel(t) }}</el-button>
        </div>
      </div>
      <el-collapse v-if="auditLogEnabled && auditLog.length" class="gt-dfr__audit-log">
        <el-collapse-item :title="`状态变更日志（${auditLog.length} 条）`" name="audit-log">
          <el-timeline>
            <el-timeline-item v-for="(log, idx) in auditLog" :key="idx" :timestamp="formatTimestamp(log.timestamp)" :type="auditLogItemType(log)" placement="top">
              <div class="gt-dfr__log-item">
                <div class="gt-dfr__log-line">
                  <span>{{ stateLabelOf(log.from) || '—' }}</span>
                  <el-icon><Right /></el-icon>
                  <span>{{ stateLabelOf(log.to) }}</span>
                  <el-tag size="small" type="info" effect="plain">{{ log.trigger }}</el-tag>
                </div>
                <div class="gt-dfr__log-meta">
                  <el-icon><User /></el-icon><span>{{ log.user || '系统' }}</span>
                  <template v-if="log.reason"><span>·</span><span>{{ log.reason }}</span></template>
                </div>
              </div>
            </el-timeline-item>
          </el-timeline>
        </el-collapse-item>
      </el-collapse>
    </section>

    <!-- 上下文字段区 -->
    <section v-if="contextFields.length" class="gt-dfr__context">
      <h3 class="gt-dfr__title">复核上下文</h3>
      <el-form :model="contextData" label-position="top" :disabled="props.readonly">
        <el-form-item v-for="field in contextFields" :key="field.name" :label="field.label" :required="!!field.required">
          <el-input v-if="field.type === 'textarea'" :model-value="contextData[field.name]" :disabled="props.readonly || !!field.readonly" type="textarea" :rows="3" @update:model-value="(v: any) => onContextChange(field, v)" />
          <el-input v-else :model-value="contextData[field.name]" :disabled="props.readonly || !!field.readonly" @update:model-value="(v: any) => onContextChange(field, v)" />
        </el-form-item>
      </el-form>
    </section>

    <!-- 复核步骤 -->
    <section v-if="reviewSteps.length" class="gt-dfr__steps">
      <h3 class="gt-dfr__title">复核步骤</h3>
      <el-steps :active="activeStepIdx" finish-status="success" align-center>
        <el-step v-for="(step, idx) in reviewSteps" :key="step.step || idx" :title="stepShortTitle(step)" :description="stepShortDesc(step)" :status="stepStatus(idx)" @click="goToStep(idx)" />
      </el-steps>
      <div v-if="currentStep" class="gt-dfr__step-panel">
        <header>
          <h4>{{ currentStep.title || `步骤 ${currentStep.step}` }}</h4>
          <p v-if="currentStep.description">{{ currentStep.description }}</p>
        </header>
        <!-- checklist -->
        <div v-if="(currentStep.checklist || []).length" class="gt-dfr__checklist">
          <div v-for="item in currentStep.checklist || []" :key="item.id">
            <el-checkbox :model-value="checklistValue(currentStep, item)" :disabled="props.readonly" @update:model-value="(v: any) => onChecklistChange(currentStep!, item, v)">
              {{ item.label }}
              <el-tag v-if="item.required" size="small" type="danger" effect="plain">必填</el-tag>
            </el-checkbox>
          </div>
        </div>
        <!-- step fields -->
        <el-form v-if="(currentStep.fields || []).length" :model="stepFieldsBucket(currentStep)" label-position="top" :disabled="props.readonly">
          <el-form-item v-for="field in currentStep.fields || []" :key="field.name" :label="field.label" :required="!!field.required">
            <el-input :model-value="stepFieldValue(currentStep, field)" :disabled="props.readonly || !!field.readonly" :type="field.type === 'textarea' ? 'textarea' : undefined" @update:model-value="(v: any) => setStepField(currentStep!, field, v)" />
          </el-form-item>
        </el-form>
        <!-- linked workpapers -->
        <div v-if="(currentStep.linked_workpapers || []).length">
          <span>关联底稿：</span>
          <div v-for="lw in currentStep.linked_workpapers || []" :key="lw.ref">
            <GtIndexChip :value="lw.ref" :validate="true" @click="onLinkedWorkpaperClick(lw.ref)" />
            <span v-if="lw.label">{{ lw.label }}</span>
          </div>
        </div>
        <!-- signatures -->
        <div v-if="(currentStep.signature || []).length" class="gt-dfr__signatures">
          <h5>电子签</h5>
          <div v-for="sig in currentStep.signature || []" :key="sig.role" :class="{ 'is-signed': isSigned(sig) }">
            <div>
              <el-icon><User /></el-icon><span>{{ sig.label || sig.role }}</span>
              <el-tag v-if="sig.required" size="small" type="danger" effect="plain">必签</el-tag>
              <div v-if="isSigned(sig)"><span>{{ signaturesData[sig.role]?.signed_by }}</span><span><el-icon><Clock /></el-icon>{{ formatTimestamp(signaturesData[sig.role]?.signed_at) }}</span></div>
              <div v-else>尚未签字</div>
            </div>
            <div>
              <el-button v-if="!isSigned(sig)" type="primary" size="small" :icon="EditPen" :disabled="props.readonly" @click="onSignClick(sig)">签字</el-button>
              <el-button v-else size="small" :icon="RefreshLeft" :disabled="props.readonly || !canUnsign(sig)" @click="onUnsignClick(sig)">撤销</el-button>
            </div>
          </div>
        </div>
        <!-- step comment -->
        <div v-if="currentStep.comment_field">
          <el-form-item :label="currentStep.comment_field.label || '复核意见'">
            <el-input :model-value="commentValue(currentStep)" type="textarea" :rows="4" :disabled="props.readonly" @update:model-value="(v: any) => setStepComment(currentStep!, v)" />
          </el-form-item>
        </div>
        <!-- step nav -->
        <div class="gt-dfr__step-nav">
          <el-button :disabled="activeStepIdx === 0" @click="goToStep(activeStepIdx - 1)">上一步</el-button>
          <el-button type="primary" :disabled="activeStepIdx >= reviewSteps.length - 1" @click="goToStep(activeStepIdx + 1)">下一步</el-button>
        </div>
      </div>
    </section>

    <!-- 整体复核结论 -->
    <section v-if="hasConclusion" class="gt-dfr__conclusion">
      <h3 class="gt-dfr__title">最终复核结论</h3>
      <el-radio-group :model-value="conclusionValue" :disabled="props.readonly" @update:model-value="(v: any) => onConclusionChange(v)">
        <el-radio v-for="opt in conclusionOptions" :key="opt.value" :value="opt.value">
          <el-icon v-if="opt.icon && conclusionIcons[opt.icon]"><component :is="conclusionIcons[opt.icon]" /></el-icon>
          <span>{{ opt.label }}</span>
        </el-radio>
      </el-radio-group>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import {
  InfoFilled,
  CircleCheck,
  CircleCheckFilled,
  WarningFilled,
  CircleCloseFilled,
  EditPen,
  RefreshLeft,
  User,
  Clock,
  Right,
} from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import type { DFormSchema, DFormData, FieldChangePayload, SignaturePayload } from './GtDForm.vue'
import { useReviewStateMachine } from './composables/useReviewStateMachine'
import { useReviewSignature } from './composables/useReviewSignature'
import { useReviewFields } from './composables/useReviewFields'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = withDefaults(defineProps<{
  wpId: string
  sheetName: string
  schema: DFormSchema
  htmlData: DFormData
  readonly?: boolean
}>(), { readonly: false })

const emit = defineEmits<{
  'field-change': [payload: FieldChangePayload]
  'jump-to-reference': [refCode: string]
  'save': [data: DFormData]
  'sign': [payload: SignaturePayload]
  'state-change': [payload: any]
}>()

// ─── Static maps ─────────────────────────────────────────────────────────────

const REVIEW_ROLE_LABELS: Record<string, string> = {
  project_manager: '项目经理复核',
  partner: '合伙人复核',
  eqcr: 'EQCR 抽查',
  quality_control: '质控部门复核',
  senior_manager: '高级经理复核',
}

const conclusionIcons: Record<string, any> = {
  CircleCheck, CircleCheckFilled, WarningFilled, CircleCloseFilled,
}

// ─── Header computed ─────────────────────────────────────────────────────────

const fixedCells = computed(() => (props.schema as any)?.fixed_cells ?? {})
const entityName = computed(() => fixedCells.value?.A3 || '')
const periodEnd = computed(() => fixedCells.value?.A4 || '')
const indexNo = computed(() => fixedCells.value?.H3 || fixedCells.value?.L3 || fixedCells.value?.J3 || '')
const reviewRole = computed(() => (props.schema as any)?.review_role || '')
const reviewRoleLabel = computed(() => REVIEW_ROLE_LABELS[reviewRole.value] || '')
const hasHeaderInfo = computed(() => !!(entityName.value || periodEnd.value || indexNo.value || reviewRoleLabel.value))

// ─── Composable 1: State Machine (topological first) ─────────────────────────

const {
  currentState,
  auditLog,
  availableTransitions,
  isFinalState,
  hasStateMachine,
  auditLogEnabled,
  currentStateLabel,
  currentStateTagType,
  stateLabelOf,
  transitionButtonType,
  transitionButtonLabel,
  auditLogItemType,
  onTransitionClick,
  initStateMachine,
} = useReviewStateMachine({
  getStateMachine: () => {
    const sm = (props.schema as any)?.state_machine
    return sm && typeof sm === 'object' ? sm : null
  },
  getInitialState: () => {
    const data = (props.htmlData ?? {}) as any
    const sm = (props.schema as any)?.state_machine
    const initial = sm?.initial || (sm?.states?.[0]?.id ?? '')
    return (typeof data.state === 'string' && data.state) ? data.state : initial
  },
  getInitialAuditLog: () => {
    const data = (props.htmlData ?? {}) as any
    return Array.isArray(data.audit_log) ? [...data.audit_log] : []
  },
  isReadonly: () => props.readonly,
  emit: {
    stateChange: (payload) => emit('state-change', payload),
    fieldChange: (payload) => emit('field-change', payload),
  },
})

// ─── Composable 2: Signature (depends on currentState) ───────────────────────

const {
  signaturesData,
  onSignClick,
  onUnsignClick,
  canUnsign,
  isSigned,
  initSignatures,
} = useReviewSignature({
  currentState,
  auditLog,
  getInitialSignatures: () => {
    const data = (props.htmlData ?? {}) as any
    return data.signatures && typeof data.signatures === 'object' ? { ...data.signatures } : {}
  },
  getCurrentStepSignatures: () => {
    const steps = (props.schema as any)?.review_steps
    if (!Array.isArray(steps)) return []
    const step = steps[activeStepIdx.value]
    return step?.signature || []
  },
  getTransitions: () => {
    const sm = (props.schema as any)?.state_machine
    return sm?.transitions || []
  },
  isReadonly: () => props.readonly,
  emit: {
    sign: (payload) => emit('sign', payload),
    fieldChange: (payload) => emit('field-change', payload),
    stateChange: (payload) => emit('state-change', payload),
  },
})

// ─── Composable 3: Fields (depends on state machine + signature) ─────────────

const {
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
  stepShortTitle,
  stepShortDesc,
  stepStatus,
  stepFieldsBucket,
  stepFieldValue,
  checklistValue,
  commentValue,
  debounceSave,
  initFields,
} = useReviewFields({
  getContextFields: () => {
    const arr = (props.schema as any)?.fields
    return Array.isArray(arr) ? arr : []
  },
  getReviewSteps: () => {
    const arr = (props.schema as any)?.review_steps
    return Array.isArray(arr) ? arr : []
  },
  getConclusionDef: () => {
    const c = (props.schema as any)?.conclusion
    return c && typeof c === 'object' ? c : null
  },
  getHtmlData: () => props.htmlData,
  getCurrentState: () => currentState.value,
  getSignatures: () => signaturesData.value,
  getAuditLog: () => auditLog.value,
  isReadonly: () => props.readonly,
  emit: {
    fieldChange: (payload) => emit('field-change', payload),
    save: (data) => emit('save', data),
  },
})

// ─── Init + watch ────────────────────────────────────────────────────────────

function initAll() {
  const data = (props.htmlData ?? {}) as any
  const sm = (props.schema as any)?.state_machine
  const initial = sm?.initial || (sm?.states?.[0]?.id ?? '')
  initStateMachine(
    (typeof data.state === 'string' && data.state) ? data.state : initial,
    Array.isArray(data.audit_log) ? [...data.audit_log] : []
  )
  initSignatures(data.signatures && typeof data.signatures === 'object' ? { ...data.signatures } : {})
  initFields()
}

initAll()

watch(() => props.htmlData, () => { initAll() }, { deep: true })
watch(() => props.schema, () => { initAll() }, { deep: true })

// ─── Template helpers ────────────────────────────────────────────────────────

function formatTimestamp(ts: string | undefined): string {
  if (!ts) return ''
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ts
  const yy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  return `${yy}-${mm}-${dd} ${hh}:${mi}`
}

function onLinkedWorkpaperClick(refCode: string) {
  emit('jump-to-reference', refCode)
}
</script>

<style scoped>
.gt-d-form-review { display: flex; flex-direction: column; gap: 16px; padding: 16px; }
.gt-dfr__header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; padding: 10px 14px; background: var(--gt-color-bg-soft, #f5f7fa); border-radius: 6px; font-size: 13px; }
.gt-dfr__header-meta { display: flex; align-items: center; gap: 16px; }
.gt-dfr__header-right { display: flex; align-items: center; gap: 10px; }
.gt-dfr__entity { font-weight: 600; }
.gt-dfr__index strong { color: var(--el-color-primary); margin-left: 4px; }
.gt-dfr__title { margin: 0 0 8px 0; font-size: 15px; font-weight: 600; }
.gt-dfr__state { border: 1px solid var(--el-border-color-light); border-radius: 6px; padding: 12px 16px; }
.gt-dfr__state-row { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
.gt-dfr__state-current { display: flex; align-items: center; gap: 8px; }
.gt-dfr__state-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.gt-dfr__state-final { font-size: 12px; color: var(--el-text-color-secondary); }
.gt-dfr__audit-log { margin-top: 12px; }
.gt-dfr__log-item { display: flex; flex-direction: column; gap: 4px; }
.gt-dfr__log-line { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.gt-dfr__log-meta { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--el-text-color-secondary); }
.gt-dfr__context { border: 1px solid var(--el-border-color-light); border-radius: 6px; padding: 12px 16px; }
.gt-dfr__steps { border: 1px solid var(--el-border-color-light); border-radius: 6px; padding: 16px; }
.gt-dfr__step-panel { padding: 12px 16px; border-radius: 4px; background: var(--el-color-primary-light-9); }
.gt-dfr__checklist { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; padding: 12px; background: #fff; border-radius: 4px; }
.gt-dfr__signatures { display: flex; flex-direction: column; gap: 10px; margin-bottom: 12px; padding: 12px 16px; border: 1px dashed var(--el-color-primary-light-5); border-radius: 6px; }
.gt-dfr__step-nav { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; padding-top: 12px; border-top: 1px dashed var(--el-border-color-lighter); }
.gt-dfr__conclusion { padding: 16px; border: 1px solid var(--el-border-color-light); border-radius: 6px; }
</style>
