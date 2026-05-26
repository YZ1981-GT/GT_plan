<!--
  GtDFormReview.vue — D 类复核记录子组件（实现版）

  适用范围：~27 sheet（A22 项目经理复核 / A23 合伙人复核 / EQCR 抽查 / 质控复核）
  样本 schema：D-A22-review.yaml（项目负责经理复核 财报审计）

  核心交互：
  - review_steps[] 6 步骤渲染（el-steps 横向 stepper + 当前步骤面板）
    每步：title + description + checklist[]（checkbox + cell） + comment_field（textarea）
    Step 5 含 fields[]（opinion_type enum / opinion_basis textarea / kam_count number）
    Step 6 终结步骤含 signature[]（电子签 + auto_timestamp + emit 'sign'）
  - state_machine：当前状态 el-tag + 可用 transitions[] 按钮
    点击 transition → ElMessageBox.prompt 询问 reason → emit 'state-change'
    audit_log 折叠区记录所有状态变更（user / timestamp / reason）
  - 电子签：signature 行有「签字」按钮 + ElMessageBox.confirm 二次确认
    设置 signed_by = current user.full_name / username，signed_at = now()
    emit 'sign' { role, signed_by, signed_at, cell, state_transition? }
  - linked_workpapers[] → GtIndexChip 渲染（A13/A14 跳转）
  - conclusion mode=single radio + 4 options（icon + class）
  - debounce 1.5s 自动保存（emit 'save' 全量 payload）
  - 字段变更 emit 'field-change' 带 step 前缀

  锚定 spec workpaper-html-renderer Task 8.7
  Validates: Requirements 3.5（D 子模式 5）

  cross-ref:updated 订阅由 `useWpRenderer.ts` 集中处理（Task 13.2），本组件不直接订阅。
-->

<template>
  <div class="gt-d-form-review">
    <!-- ─── 顶部头部信息（只读展示） ─── -->
    <header v-if="hasHeaderInfo" class="gt-dfr__header">
      <div class="gt-dfr__header-meta">
        <span v-if="entityName" class="gt-dfr__entity">{{ entityName }}</span>
        <span v-if="periodEnd" class="gt-dfr__period">{{ periodEnd }}</span>
      </div>
      <div class="gt-dfr__header-right">
        <el-tag
          v-if="reviewRoleLabel"
          size="small"
          type="primary"
          effect="plain"
        >{{ reviewRoleLabel }}</el-tag>
        <span v-if="indexNo" class="gt-dfr__index">
          索引号：<strong>{{ indexNo }}</strong>
        </span>
      </div>
    </header>

    <!-- ─── 状态机区（当前状态 + 可用 transitions + audit_log） ─── -->
    <section v-if="hasStateMachine" class="gt-dfr__state">
      <div class="gt-dfr__state-row">
        <div class="gt-dfr__state-current">
          <span class="gt-dfr__state-label">复核状态：</span>
          <el-tag
            :type="currentStateTagType"
            effect="dark"
            size="default"
            class="gt-dfr__state-tag"
          >{{ currentStateLabel }}</el-tag>
          <span v-if="isFinalState" class="gt-dfr__state-final">（终态）</span>
        </div>
        <div v-if="availableTransitions.length && !readonly" class="gt-dfr__state-actions">
          <el-button
            v-for="t in availableTransitions"
            :key="`${t.from}->${t.to}:${t.trigger}`"
            size="small"
            :type="transitionButtonType(t)"
            :disabled="readonly"
            @click="onTransitionClick(t)"
          >{{ transitionButtonLabel(t) }}</el-button>
        </div>
      </div>

      <!-- 状态变更日志（折叠） -->
      <el-collapse
        v-if="auditLogEnabled && auditLog.length"
        class="gt-dfr__audit-log"
      >
        <el-collapse-item :title="`状态变更日志（${auditLog.length} 条）`" name="audit-log">
          <el-timeline>
            <el-timeline-item
              v-for="(log, idx) in auditLog"
              :key="idx"
              :timestamp="formatTimestamp(log.timestamp)"
              :type="auditLogItemType(log)"
              placement="top"
            >
              <div class="gt-dfr__log-item">
                <div class="gt-dfr__log-line">
                  <span class="gt-dfr__log-from">{{ stateLabelOf(log.from) || '—' }}</span>
                  <el-icon class="gt-dfr__log-arrow"><Right /></el-icon>
                  <span class="gt-dfr__log-to">{{ stateLabelOf(log.to) }}</span>
                  <el-tag size="small" type="info" effect="plain">{{ log.trigger }}</el-tag>
                </div>
                <div class="gt-dfr__log-meta">
                  <el-icon><User /></el-icon>
                  <span>{{ log.user || '系统' }}</span>
                  <template v-if="log.reason">
                    <span class="gt-dfr__log-sep">·</span>
                    <span class="gt-dfr__log-reason">{{ log.reason }}</span>
                  </template>
                </div>
              </div>
            </el-timeline-item>
          </el-timeline>
        </el-collapse-item>
      </el-collapse>
    </section>

    <!-- ─── 上下文字段区 ─── -->
    <section v-if="contextFields.length" class="gt-dfr__context">
      <h3 class="gt-dfr__title">复核上下文</h3>
      <el-form
        :model="contextData"
        label-position="top"
        :disabled="readonly"
        class="gt-dfr__context-form"
      >
        <el-form-item
          v-for="field in contextFields"
          :key="field.name"
          :label="field.label"
          :required="!!field.required"
          class="gt-dfr__context-item"
        >
          <el-input
            v-if="field.type === 'textarea'"
            :model-value="contextData[field.name]"
            :disabled="readonly || !!field.readonly"
            type="textarea"
            :rows="3"
            :maxlength="field.max_length"
            :show-word-limit="!!field.max_length"
            :placeholder="field.hint || field.label"
            @update:model-value="(v: any) => onContextChange(field, v)"
          />
          <el-input
            v-else
            :model-value="contextData[field.name]"
            :disabled="readonly || !!field.readonly"
            :maxlength="field.max_length"
            :placeholder="field.hint || field.label"
            @update:model-value="(v: any) => onContextChange(field, v)"
          />
          <div v-if="field.hint" class="gt-dfr__field-hint">
            <el-icon><InfoFilled /></el-icon>
            <span>{{ field.hint }}</span>
          </div>
        </el-form-item>
      </el-form>
    </section>

    <!-- ─── 复核步骤（review_steps，6 步骤 stepper） ─── -->
    <section v-if="reviewSteps.length" class="gt-dfr__steps">
      <h3 class="gt-dfr__title">复核步骤</h3>
      <el-steps
        :active="activeStepIdx"
        finish-status="success"
        align-center
        class="gt-dfr__stepper"
      >
        <el-step
          v-for="(step, idx) in reviewSteps"
          :key="step.id || step.step || idx"
          :title="stepShortTitle(step)"
          :description="stepShortDesc(step)"
          :status="stepStatus(idx)"
          @click="goToStep(idx)"
        />
      </el-steps>

      <div v-if="currentStep" class="gt-dfr__step-panel">
        <header class="gt-dfr__step-header">
          <h4 class="gt-dfr__step-title">{{ currentStep.title || `步骤 ${currentStep.step}` }}</h4>
          <p
            v-if="currentStep.description"
            class="gt-dfr__step-desc"
          >{{ currentStep.description }}</p>
        </header>

        <!-- checklist 复核要点 -->
        <div
          v-if="(currentStep.checklist || []).length"
          class="gt-dfr__checklist"
        >
          <div
            v-for="item in currentStep.checklist || []"
            :key="item.id"
            class="gt-dfr__check-row"
          >
            <el-checkbox
              :model-value="checklistValue(currentStep, item)"
              :disabled="readonly"
              @update:model-value="(v: any) => onChecklistChange(currentStep!, item, v)"
            >
              <span class="gt-dfr__check-label">{{ item.label }}</span>
              <el-tag
                v-if="item.required"
                size="small"
                type="danger"
                effect="plain"
                class="gt-dfr__required-tag"
              >必填</el-tag>
            </el-checkbox>
          </div>
        </div>

        <!-- 步骤 5 专属 fields -->
        <el-form
          v-if="(currentStep.fields || []).length"
          :model="stepFieldsBucket(currentStep)"
          label-position="top"
          :disabled="readonly"
          class="gt-dfr__step-form"
        >
          <el-form-item
            v-for="field in currentStep.fields || []"
            :key="field.name"
            :label="field.label"
            :required="!!field.required"
            class="gt-dfr__step-item"
          >
            <el-select
              v-if="field.type === 'enum'"
              :model-value="stepFieldValue(currentStep, field)"
              :disabled="readonly || !!field.readonly"
              clearable
              :placeholder="field.label"
              class="gt-dfr__step-select"
              @update:model-value="(v: any) => setStepField(currentStep!, field, v)"
            >
              <el-option
                v-for="opt in field.enum || []"
                :key="opt"
                :label="opt"
                :value="opt"
              />
            </el-select>
            <el-input-number
              v-else-if="field.type === 'number'"
              :model-value="stepFieldValue(currentStep, field)"
              :disabled="readonly || !!field.readonly"
              :min="field.min"
              :max="field.max"
              controls-position="right"
              class="gt-dfr__step-number"
              @update:model-value="(v: any) => setStepField(currentStep!, field, v)"
            />
            <el-input
              v-else-if="field.type === 'textarea'"
              :model-value="stepFieldValue(currentStep, field)"
              :disabled="readonly || !!field.readonly"
              type="textarea"
              :rows="4"
              :maxlength="field.max_length"
              :show-word-limit="!!field.max_length"
              :placeholder="field.hint || field.label"
              @update:model-value="(v: any) => setStepField(currentStep!, field, v)"
            />
            <el-input
              v-else
              :model-value="stepFieldValue(currentStep, field)"
              :disabled="readonly || !!field.readonly"
              :maxlength="field.max_length"
              :placeholder="field.hint || field.label"
              @update:model-value="(v: any) => setStepField(currentStep!, field, v)"
            />
            <div v-if="field.hint" class="gt-dfr__field-hint">
              <el-icon><InfoFilled /></el-icon>
              <span>{{ field.hint }}</span>
            </div>
          </el-form-item>
        </el-form>

        <!-- linked_workpapers（A13/A14 等关联底稿） -->
        <div
          v-if="(currentStep.linked_workpapers || []).length"
          class="gt-dfr__linked"
        >
          <span class="gt-dfr__linked-label">关联底稿：</span>
          <div class="gt-dfr__linked-chips">
            <div
              v-for="lw in currentStep.linked_workpapers || []"
              :key="lw.ref"
              class="gt-dfr__linked-chip-row"
            >
              <GtIndexChip
                :value="lw.ref"
                :validate="true"
                @click="onLinkedWorkpaperClick(lw.ref)"
              />
              <span v-if="lw.label" class="gt-dfr__linked-text">{{ lw.label }}</span>
            </div>
          </div>
        </div>

        <!-- 步骤 6 电子签 -->
        <div
          v-if="(currentStep.signature || []).length"
          class="gt-dfr__signatures"
        >
          <h5 class="gt-dfr__sig-title">电子签</h5>
          <div
            v-for="sig in currentStep.signature || []"
            :key="sig.role"
            :class="['gt-dfr__sig-row', { 'is-signed': isSigned(sig) }]"
          >
            <div class="gt-dfr__sig-info">
              <div class="gt-dfr__sig-label">
                <el-icon><User /></el-icon>
                <span>{{ sig.label || sig.role }}</span>
                <el-tag
                  v-if="sig.required"
                  size="small"
                  type="danger"
                  effect="plain"
                  class="gt-dfr__required-tag"
                >必签</el-tag>
              </div>
              <div v-if="isSigned(sig)" class="gt-dfr__sig-detail">
                <span class="gt-dfr__sig-name">{{ signaturesData[sig.role]?.signed_by }}</span>
                <span class="gt-dfr__sig-time">
                  <el-icon><Clock /></el-icon>
                  {{ formatTimestamp(signaturesData[sig.role]?.signed_at) }}
                </span>
              </div>
              <div v-else class="gt-dfr__sig-empty">尚未签字</div>
            </div>
            <div class="gt-dfr__sig-actions">
              <el-button
                v-if="!isSigned(sig)"
                type="primary"
                size="small"
                :icon="EditPen"
                :disabled="readonly"
                @click="onSignClick(sig)"
              >签字</el-button>
              <el-button
                v-else
                size="small"
                :icon="RefreshLeft"
                :disabled="readonly || !canUnsign(sig)"
                @click="onUnsignClick(sig)"
              >撤销</el-button>
            </div>
          </div>
        </div>

        <!-- 步骤评论 -->
        <div v-if="currentStep.comment_field" class="gt-dfr__step-comment">
          <el-form-item
            :label="currentStep.comment_field.label || '复核意见'"
            class="gt-dfr__step-item"
          >
            <el-input
              :model-value="commentValue(currentStep)"
              type="textarea"
              :rows="4"
              :disabled="readonly"
              :maxlength="currentStep.comment_field.max_length"
              :show-word-limit="!!currentStep.comment_field.max_length"
              :placeholder="`请填写${currentStep.title || '本步骤'}的复核意见`"
              @update:model-value="(v: any) => setStepComment(currentStep!, v)"
            />
          </el-form-item>
        </div>

        <!-- 步骤导航 -->
        <div class="gt-dfr__step-nav">
          <el-button
            :disabled="activeStepIdx === 0"
            @click="goToStep(activeStepIdx - 1)"
          >上一步</el-button>
          <el-button
            type="primary"
            :disabled="activeStepIdx >= reviewSteps.length - 1"
            @click="goToStep(activeStepIdx + 1)"
          >下一步</el-button>
        </div>
      </div>
    </section>

    <!-- ─── 整体复核结论 ─── -->
    <section v-if="hasConclusion" class="gt-dfr__conclusion">
      <h3 class="gt-dfr__title">最终复核结论</h3>
      <el-radio-group
        :model-value="conclusionValue"
        :disabled="readonly"
        class="gt-dfr__concl-group"
        @update:model-value="(v: any) => onConclusionChange(v)"
      >
        <el-radio
          v-for="opt in conclusionOptions"
          :key="opt.value"
          :value="opt.value"
          :class="['gt-dfr__concl-option', `is-${opt.class || 'info'}`]"
        >
          <div class="gt-dfr__concl-label">
            <el-icon
              v-if="opt.icon && conclusionIcons[opt.icon]"
              class="gt-dfr__concl-icon"
            >
              <component :is="conclusionIcons[opt.icon]" />
            </el-icon>
            <div class="gt-dfr__concl-text">
              <span class="gt-dfr__concl-name">{{ opt.label }}</span>
              <span
                v-if="opt.description"
                class="gt-dfr__concl-desc"
              >{{ opt.description }}</span>
            </div>
          </div>
        </el-radio>
      </el-radio-group>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
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
import { useAuthStore } from '@/stores/auth'
import type {
  DFormSchema,
  DFormData,
  FieldChangePayload,
  SignaturePayload,
} from './GtDForm.vue'

// ─── Types ───────────────────────────────────────────────────────────────────

type FieldType = 'text' | 'textarea' | 'number' | 'enum'

interface FieldDef {
  name: string
  label: string
  type?: FieldType
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

interface LinkedWorkpaper {
  ref: string
  label?: string
  render?: string
}

interface SignatureDef {
  role: string
  label?: string
  cell?: string
  source?: string
  auto_timestamp?: boolean
  timestamp_cell?: string
  required?: boolean
}

interface ReviewStepDef {
  step: number
  id?: string
  title?: string
  description?: string
  start_row?: number
  end_row?: number | string
  checklist?: ChecklistItem[]
  comment_field?: CommentFieldDef
  fields?: FieldDef[]
  linked_workpapers?: LinkedWorkpaper[]
  signature?: SignatureDef[]
  is_terminal?: boolean
}

interface StateDef {
  id: string
  label: string
  class?: 'info' | 'warning' | 'success' | 'danger'
}

interface TransitionDef {
  from: string
  to: string
  trigger: string
  description?: string
}

interface StateMachineDef {
  states?: StateDef[]
  transitions?: TransitionDef[]
  initial?: string
  final?: string[]
  cell?: string
  audit_log?: boolean
}

interface ConclusionOption {
  value: string
  label: string
  class?: 'success' | 'warning' | 'danger' | 'info'
  icon?: string
  description?: string
}

interface ConclusionDef {
  mode?: 'single' | string
  cell?: string
  options?: ConclusionOption[]
  mutual_exclusive?: boolean
  required?: boolean
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

interface ReviewData extends DFormData {
  context?: Record<string, any>
  steps?: Record<string, {
    checklist?: Record<string, boolean>
    comment?: string
    fields?: Record<string, any>
  }>
  active_step?: number
  state?: string
  signatures?: Record<string, SignatureRecord>
  audit_log?: AuditLogEntry[]
  conclusion?: string
}

interface StateChangePayload {
  from: string
  to: string
  trigger: string
  reason?: string
  user?: string
  timestamp: string
}

// ─── Role label map ──────────────────────────────────────────────────────────

const REVIEW_ROLE_LABELS: Record<string, string> = {
  project_manager: '项目经理复核',
  partner: '合伙人复核',
  eqcr: 'EQCR 抽查',
  quality_control: '质控部门复核',
  senior_manager: '高级经理复核',
}

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = withDefaults(defineProps<{
  wpId: string
  sheetName: string
  schema: DFormSchema
  htmlData: DFormData
  readonly?: boolean
}>(), {
  readonly: false,
})

const emit = defineEmits<{
  'field-change': [payload: FieldChangePayload]
  'jump-to-reference': [refCode: string]
  'save': [data: DFormData]
  'sign': [payload: SignaturePayload]
  'state-change': [payload: StateChangePayload]
}>()

// ─── Refs（按 setup const 顺序铁律放最前） ────────────────────────────────────

const contextData = ref<Record<string, any>>({})
const stepsData = ref<Record<string, {
  checklist: Record<string, boolean>
  comment: string
  fields: Record<string, any>
}>>({})
const activeStepIdx = ref<number>(0)
const currentState = ref<string>('')
const signaturesData = ref<Record<string, SignatureRecord>>({})
const auditLog = ref<AuditLogEntry[]>([])
const conclusionValue = ref<string>('')

let saveTimer: ReturnType<typeof setTimeout> | null = null

// ─── Static maps / store ────────────────────────────────────────────────────

const conclusionIcons: Record<string, any> = {
  CircleCheck,
  CircleCheckFilled,
  WarningFilled,
  CircleCloseFilled,
}

const authStore = useAuthStore()

// ─── Computed ────────────────────────────────────────────────────────────────

const fixedCells = computed(() => (props.schema as any)?.fixed_cells ?? {})

const entityName = computed(() => fixedCells.value?.A3 || '')
const periodEnd = computed(() => fixedCells.value?.A4 || '')
const indexNo = computed(
  () => fixedCells.value?.H3 || fixedCells.value?.L3 || fixedCells.value?.J3 || ''
)

const reviewRole = computed(() => (props.schema as any)?.review_role || '')
const reviewRoleLabel = computed(() => REVIEW_ROLE_LABELS[reviewRole.value] || '')

const hasHeaderInfo = computed(
  () => !!(entityName.value || periodEnd.value || indexNo.value || reviewRoleLabel.value)
)

const contextFields = computed<FieldDef[]>(() => {
  const arr = (props.schema as any)?.fields
  return Array.isArray(arr) ? (arr as FieldDef[]) : []
})

const reviewSteps = computed<ReviewStepDef[]>(() => {
  const arr = (props.schema as any)?.review_steps
  return Array.isArray(arr) ? (arr as ReviewStepDef[]) : []
})

const currentStep = computed<ReviewStepDef | null>(
  () => reviewSteps.value[activeStepIdx.value] ?? null
)

const stateMachine = computed<StateMachineDef | null>(() => {
  const sm = (props.schema as any)?.state_machine
  return sm && typeof sm === 'object' ? sm : null
})

const hasStateMachine = computed(
  () => !!(stateMachine.value && (stateMachine.value.states?.length || 0) > 0)
)

const auditLogEnabled = computed(() => !!stateMachine.value?.audit_log)

const currentStateDef = computed<StateDef | null>(() => {
  const states = stateMachine.value?.states || []
  return states.find(s => s.id === currentState.value) ?? null
})

const currentStateLabel = computed(
  () => currentStateDef.value?.label || currentState.value || '—'
)

const currentStateTagType = computed<'info' | 'warning' | 'success' | 'danger' | 'primary'>(() => {
  const cls = currentStateDef.value?.class
  if (cls === 'info' || cls === 'warning' || cls === 'success' || cls === 'danger') return cls
  return 'info'
})

const isFinalState = computed(() => {
  const finals = stateMachine.value?.final || []
  return finals.includes(currentState.value)
})

const availableTransitions = computed<TransitionDef[]>(() => {
  const trans = stateMachine.value?.transitions || []
  return trans.filter(t => t.from === currentState.value)
})

const conclusionDef = computed<ConclusionDef | null>(() => {
  const c = (props.schema as any)?.conclusion
  return c && typeof c === 'object' ? c : null
})

const hasConclusion = computed(
  () => conclusionDef.value?.mode === 'single' && !!(conclusionDef.value?.options?.length)
)

const conclusionOptions = computed<ConclusionOption[]>(
  () => conclusionDef.value?.options || []
)

// ─── Helpers ─────────────────────────────────────────────────────────────────

function stepKey(step: ReviewStepDef): string {
  return `step_${step.step}`
}

function stepShortTitle(step: ReviewStepDef): string {
  const title = step.title || `步骤 ${step.step}`
  // 截短：「步骤 1：审计完成度检查」→「审计完成度检查」
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

function stateLabelOf(stateId: string): string {
  if (!stateId) return ''
  const states = stateMachine.value?.states || []
  return states.find(s => s.id === stateId)?.label || stateId
}

function transitionButtonType(t: TransitionDef): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  const states = stateMachine.value?.states || []
  const target = states.find(s => s.id === t.to)
  const cls = target?.class
  if (cls === 'success') return 'success'
  if (cls === 'warning') return 'warning'
  if (cls === 'danger') return 'danger'
  if (cls === 'info') return 'info'
  return 'primary'
}

function transitionButtonLabel(t: TransitionDef): string {
  if (t.description) {
    const m = t.description.match(/→\s*(.+)$/)
    if (m) return m[1].trim()
    return t.description
  }
  return t.trigger
}

function auditLogItemType(log: AuditLogEntry): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  const states = stateMachine.value?.states || []
  const target = states.find(s => s.id === log.to)
  const cls = target?.class
  if (cls === 'success') return 'success'
  if (cls === 'warning') return 'warning'
  if (cls === 'danger') return 'danger'
  if (cls === 'info') return 'info'
  return 'primary'
}

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

function currentUserName(): string {
  const u = authStore.user
  if (!u) return '审计员'
  return u.full_name || u.username || '审计员'
}

function isSigned(sig: SignatureDef): boolean {
  const rec = signaturesData.value[sig.role]
  return !!(rec && rec.signed_by && rec.signed_at)
}

function canUnsign(_sig: SignatureDef): boolean {
  // 撤销规则：仅在 pending_signature 或 in_progress 状态下允许
  return currentState.value === 'pending_signature' || currentState.value === 'in_progress'
}

// ─── Field handlers ────────────────────────────────────────────────────────

function setStepField(step: ReviewStepDef, field: FieldDef, value: any) {
  const key = stepKey(step)
  if (!stepsData.value[key]) {
    stepsData.value[key] = { checklist: {}, comment: '', fields: {} }
  }
  const oldValue = stepsData.value[key].fields[field.name]
  stepsData.value[key].fields[field.name] = value
  emit('field-change', {
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
  emit('field-change', {
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
  emit('field-change', {
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
  emit('field-change', {
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

function onLinkedWorkpaperClick(refCode: string) {
  emit('jump-to-reference', refCode)
}

function onConclusionChange(value: string | number | boolean | undefined) {
  const v = typeof value === 'string' ? value : String(value ?? '')
  const oldValue = conclusionValue.value
  conclusionValue.value = v
  emit('field-change', {
    field_name: 'conclusion',
    old_value: oldValue,
    new_value: v,
    cell: conclusionDef.value?.cell,
  })
  debounceSave()
}

// ─── State machine handlers ────────────────────────────────────────────────

async function onTransitionClick(t: TransitionDef) {
  if (props.readonly) return
  const requireReason =
    t.to === 'review_returned' ||
    t.trigger === 'unsign' ||
    t.to === 'pending_response'
  let reason = ''
  if (requireReason) {
    try {
      const result = await ElMessageBox.prompt(
        `${t.description || t.trigger}\n\n请输入触发原因：`,
        '状态变更',
        {
          confirmButtonText: '确认',
          cancelButtonText: '取消',
          inputType: 'textarea',
          inputValidator: (v: string) => (v && v.trim().length >= 4) || '原因至少 4 个字',
        }
      )
      reason = (result as { value: string }).value || ''
    } catch {
      return
    }
  } else {
    try {
      await ElMessageBox.confirm(
        t.description || `确认推进至「${stateLabelOf(t.to)}」？`,
        '状态变更',
        {
          confirmButtonText: '确认',
          cancelButtonText: '取消',
          type: 'warning',
        }
      )
    } catch {
      return
    }
  }

  const ts = new Date().toISOString()
  const logEntry: AuditLogEntry = {
    from: t.from,
    to: t.to,
    trigger: t.trigger,
    user: currentUserName(),
    timestamp: ts,
    reason: reason || undefined,
  }
  auditLog.value.push(logEntry)
  currentState.value = t.to

  emit('state-change', {
    from: t.from,
    to: t.to,
    trigger: t.trigger,
    reason: reason || undefined,
    user: currentUserName(),
    timestamp: ts,
  })
  emit('field-change', {
    field_name: 'state_machine',
    old_value: t.from,
    new_value: t.to,
    cell: stateMachine.value?.cell,
  })
  ElMessage.success(`已推进至「${stateLabelOf(t.to)}」`)
  debounceSave()
}

// ─── Signature handlers ────────────────────────────────────────────────────

async function onSignClick(sig: SignatureDef) {
  if (props.readonly) return
  try {
    await ElMessageBox.confirm(
      `确认以「${currentUserName()}」身份完成「${sig.label || sig.role}」电子签字？\n\n签字后将自动写入时间戳，并可能触发状态机推进。`,
      '电子签字确认',
      {
        confirmButtonText: '确认签字',
        cancelButtonText: '取消',
        type: 'info',
      }
    )
  } catch {
    return
  }

  const ts = new Date().toISOString()
  const signedBy = currentUserName()
  signaturesData.value[sig.role] = {
    signed_by: signedBy,
    signed_at: ts,
    cell: sig.cell,
  }

  // 如果签字触发状态机推进（pending_signature → review_passed），自动入栈
  let stateTransition: { from: string; to: string } | undefined
  if (sig.required && currentState.value === 'pending_signature') {
    const allRequiredSigned = (currentStep.value?.signature || [])
      .filter(s => s.required)
      .every(s => isSigned(s))
    if (allRequiredSigned) {
      const signTrans = (stateMachine.value?.transitions || [])
        .find(t => t.from === 'pending_signature' && t.trigger === 'signature_completed')
      if (signTrans) {
        const fromState = currentState.value
        currentState.value = signTrans.to
        auditLog.value.push({
          from: fromState,
          to: signTrans.to,
          trigger: signTrans.trigger,
          user: signedBy,
          timestamp: ts,
          reason: `${sig.label || sig.role} 完成签字`,
        })
        stateTransition = { from: fromState, to: signTrans.to }
        emit('state-change', {
          from: fromState,
          to: signTrans.to,
          trigger: signTrans.trigger,
          user: signedBy,
          timestamp: ts,
          reason: `${sig.label || sig.role} 完成签字`,
        })
      }
    }
  }

  emit('sign', {
    role: sig.role,
    signed_by: signedBy,
    signed_at: ts,
    cell: sig.cell,
    state_transition: stateTransition,
  })
  emit('field-change', {
    field_name: `signatures.${sig.role}`,
    old_value: undefined,
    new_value: { signed_by: signedBy, signed_at: ts },
    cell: sig.cell,
  })
  ElMessage.success(`${sig.label || sig.role} 签字成功`)
  debounceSave()
}

async function onUnsignClick(sig: SignatureDef) {
  if (props.readonly) return
  if (!canUnsign(sig)) {
    ElMessage.warning('当前状态不允许撤销签字')
    return
  }
  try {
    const result = await ElMessageBox.prompt(
      `确认撤销「${sig.label || sig.role}」的电子签字？\n请说明撤销原因：`,
      '撤销签字',
      {
        confirmButtonText: '确认撤销',
        cancelButtonText: '取消',
        inputType: 'textarea',
        inputValidator: (v: string) => (v && v.trim().length >= 4) || '原因至少 4 个字',
      }
    )
    const reason = (result as { value: string }).value || ''
    const oldRec = signaturesData.value[sig.role]
    delete signaturesData.value[sig.role]
    auditLog.value.push({
      from: currentState.value,
      to: currentState.value,
      trigger: 'unsign',
      user: currentUserName(),
      timestamp: new Date().toISOString(),
      reason: `撤销 ${sig.label || sig.role} 签字：${reason}`,
    })
    emit('field-change', {
      field_name: `signatures.${sig.role}`,
      old_value: oldRec,
      new_value: undefined,
      cell: sig.cell,
    })
    ElMessage.success('签字已撤销')
    debounceSave()
  } catch {
    return
  }
}

// ─── Init / Sync ────────────────────────────────────────────────────────────

function initData() {
  const data = (props.htmlData ?? {}) as ReviewData

  // 上下文
  const ctxIn = data.context && typeof data.context === 'object' ? data.context : {}
  const ctxOut: Record<string, any> = {}
  for (const f of contextFields.value) {
    ctxOut[f.name] = (ctxIn as Record<string, any>)[f.name] ?? (f.default ?? '')
  }
  contextData.value = ctxOut

  // 步骤数据
  const stepsIn = data.steps && typeof data.steps === 'object' ? data.steps : {}
  const stepsOut: Record<string, { checklist: Record<string, boolean>; comment: string; fields: Record<string, any> }> = {}
  for (const step of reviewSteps.value) {
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
  if (typeof data.active_step === 'number' && data.active_step >= 0 && data.active_step < reviewSteps.value.length) {
    activeStepIdx.value = data.active_step
  } else {
    activeStepIdx.value = 0
  }

  // 状态机初始状态
  const initial = stateMachine.value?.initial || (stateMachine.value?.states?.[0]?.id ?? '')
  currentState.value = typeof data.state === 'string' && data.state ? data.state : initial

  // 电子签
  signaturesData.value =
    data.signatures && typeof data.signatures === 'object'
      ? { ...data.signatures }
      : {}

  // 审计日志
  auditLog.value = Array.isArray(data.audit_log) ? [...data.audit_log] : []

  // 结论
  conclusionValue.value = typeof data.conclusion === 'string' ? data.conclusion : ''
}

initData()

watch(
  () => props.htmlData,
  () => {
    initData()
  },
  { deep: true }
)

watch(
  () => props.schema,
  () => {
    initData()
  },
  { deep: true }
)

// ─── Save payload + debounce ─────────────────────────────────────────────────

function buildSavePayload(): ReviewData {
  return {
    ...(props.htmlData || {}),
    context: { ...contextData.value },
    steps: JSON.parse(JSON.stringify(stepsData.value)),
    active_step: activeStepIdx.value,
    state: currentState.value,
    signatures: { ...signaturesData.value },
    audit_log: [...auditLog.value],
    conclusion: conclusionValue.value,
  }
}

function debounceSave() {
  if (props.readonly) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    emit('save', buildSavePayload())
  }, 1500)
}

// ─── Cleanup ────────────────────────────────────────────────────────────────

onBeforeUnmount(() => {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
})
</script>

<style scoped>
.gt-d-form-review {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
}

/* ── Header ── */
.gt-dfr__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 10px 14px;
  background: var(--gt-color-bg-soft, #f5f7fa);
  border-radius: 6px;
  font-size: 13px;
}
.gt-dfr__header-meta {
  display: flex;
  align-items: center;
  gap: 16px;
}
.gt-dfr__header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.gt-dfr__entity {
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.gt-dfr__period {
  color: var(--el-text-color-regular);
}
.gt-dfr__index {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gt-dfr__index strong {
  color: var(--el-color-primary);
  margin-left: 4px;
}

/* ── Common ── */
.gt-dfr__title {
  margin: 0 0 8px 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

/* ── State machine ── */
.gt-dfr__state {
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 12px 16px;
  background: var(--gt-color-bg-white, #fff);
}
.gt-dfr__state-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
.gt-dfr__state-current {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gt-dfr__state-label {
  font-weight: 500;
  color: var(--el-text-color-regular);
}
.gt-dfr__state-tag {
  font-weight: 500;
}
.gt-dfr__state-final {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gt-dfr__state-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* ── Audit log ── */
.gt-dfr__audit-log {
  margin-top: 12px;
}
.gt-dfr__audit-log :deep(.el-collapse-item__header) {
  font-size: 13px;
  font-weight: 500;
}
.gt-dfr__log-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.gt-dfr__log-line {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--el-text-color-primary);
}
.gt-dfr__log-arrow {
  color: var(--el-text-color-secondary);
}
.gt-dfr__log-from {
  color: var(--el-text-color-secondary);
}
.gt-dfr__log-to {
  font-weight: 500;
  color: var(--el-color-primary);
}
.gt-dfr__log-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gt-dfr__log-sep {
  color: var(--el-text-color-disabled);
}
.gt-dfr__log-reason {
  font-style: italic;
  color: var(--el-text-color-regular);
}

/* ── Context ── */
.gt-dfr__context {
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 12px 16px;
  background: var(--gt-color-bg-white, #fff);
}
.gt-dfr__context-form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: 12px 16px;
}
.gt-dfr__context-item {
  margin-bottom: 0;
}

/* ── Steps ── */
.gt-dfr__steps {
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 16px;
  background: var(--gt-color-bg-white, #fff);
}
.gt-dfr__stepper {
  margin-bottom: 16px;
  cursor: pointer;
}
.gt-dfr__stepper :deep(.el-step__head) {
  cursor: pointer;
}
.gt-dfr__stepper :deep(.el-step__title) {
  cursor: pointer;
  font-size: 13px;
}
.gt-dfr__stepper :deep(.el-step__description) {
  font-size: 11px;
}
.gt-dfr__step-panel {
  padding: 12px 16px;
  border-radius: 4px;
  background: var(--el-color-primary-light-9);
}
.gt-dfr__step-header {
  margin-bottom: 12px;
}
.gt-dfr__step-title {
  margin: 0 0 4px 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-color-primary);
}
.gt-dfr__step-desc {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

/* ── Checklist ── */
.gt-dfr__checklist {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
  padding: 12px;
  background: var(--gt-color-bg-white, #fff);
  border-radius: 4px;
}
.gt-dfr__check-row {
  display: flex;
  align-items: center;
}
.gt-dfr__check-row :deep(.el-checkbox) {
  white-space: normal;
  align-items: flex-start;
}
.gt-dfr__check-row :deep(.el-checkbox__label) {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  line-height: 1.5;
}
.gt-dfr__check-label {
  color: var(--el-text-color-primary);
}
.gt-dfr__required-tag {
  margin-left: 4px;
}

/* ── Step form ── */
.gt-dfr__step-form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px 16px;
  margin-bottom: 12px;
  padding: 12px;
  background: var(--gt-color-bg-white, #fff);
  border-radius: 4px;
}
.gt-dfr__step-item {
  margin-bottom: 0;
}
.gt-dfr__step-select,
.gt-dfr__step-number {
  width: 100%;
}

/* ── Linked workpapers ── */
.gt-dfr__linked {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 12px;
  padding: 10px 12px;
  background: var(--el-color-info-light-9);
  border-radius: 4px;
}
.gt-dfr__linked-label {
  font-size: 13px;
  color: var(--el-text-color-regular);
  flex-shrink: 0;
  margin-top: 2px;
}
.gt-dfr__linked-chips {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.gt-dfr__linked-chip-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gt-dfr__linked-text {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

/* ── Signatures ── */
.gt-dfr__signatures {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
  padding: 12px 16px;
  background: var(--gt-color-bg-white, #fff);
  border: 1px dashed var(--el-color-primary-light-5);
  border-radius: 6px;
}
.gt-dfr__sig-title {
  margin: 0 0 4px 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-color-primary);
}

.gt-dfr__sig-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 4px;
  background: var(--el-fill-color-blank);
  transition: background 0.15s, border-color 0.15s;
}
.gt-dfr__sig-row.is-signed {
  background: var(--el-color-success-light-9);
  border-color: var(--el-color-success-light-5);
}
.gt-dfr__sig-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 0;
}
.gt-dfr__sig-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}
.gt-dfr__sig-detail {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.gt-dfr__sig-name {
  font-weight: 500;
  color: var(--el-color-success);
}
.gt-dfr__sig-time {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--el-text-color-secondary);
}
.gt-dfr__sig-empty {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-style: italic;
}
.gt-dfr__sig-actions {
  flex-shrink: 0;
}

/* ── Step comment + nav ── */
.gt-dfr__step-comment {
  margin-bottom: 12px;
  padding: 12px;
  background: var(--gt-color-bg-white, #fff);
  border-radius: 4px;
}
.gt-dfr__step-nav {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--el-border-color-lighter);
}

/* ── Field hint ── */
.gt-dfr__field-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gt-dfr__field-hint .el-icon {
  color: var(--el-color-info);
}

/* ── Conclusion ── */
.gt-dfr__conclusion {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  background: var(--el-color-primary-light-9);
}
.gt-dfr__concl-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.gt-dfr__concl-group :deep(.el-radio) {
  height: auto;
  padding: 10px 12px;
  margin-right: 0;
  align-items: flex-start;
  border: 1px solid transparent;
  border-radius: 4px;
  transition: background 0.15s, border-color 0.15s;
}
.gt-dfr__concl-group :deep(.el-radio:hover) {
  background: var(--el-color-primary-light-8);
}
.gt-dfr__concl-group :deep(.el-radio.is-checked) {
  background: var(--el-color-primary-light-8);
  border-color: var(--el-color-primary-light-5);
}
.gt-dfr__concl-option.is-success :deep(.el-radio.is-checked) {
  border-color: var(--el-color-success);
  background: var(--el-color-success-light-8);
}
.gt-dfr__concl-option.is-warning :deep(.el-radio.is-checked) {
  border-color: var(--el-color-warning);
  background: var(--el-color-warning-light-8);
}
.gt-dfr__concl-option.is-danger :deep(.el-radio.is-checked) {
  border-color: var(--el-color-danger);
  background: var(--el-color-danger-light-8);
}
.gt-dfr__concl-label {
  display: inline-flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 14px;
  color: var(--el-text-color-primary);
}
.gt-dfr__concl-icon {
  font-size: 18px;
  margin-top: 1px;
}
.gt-dfr__concl-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.gt-dfr__concl-name {
  font-weight: 500;
}
.gt-dfr__concl-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gt-dfr__concl-option.is-success .gt-dfr__concl-icon {
  color: var(--el-color-success);
}
.gt-dfr__concl-option.is-warning .gt-dfr__concl-icon {
  color: var(--el-color-warning);
}
.gt-dfr__concl-option.is-danger .gt-dfr__concl-icon {
  color: var(--el-color-danger);
}
.gt-dfr__concl-option.is-info .gt-dfr__concl-icon {
  color: var(--el-color-info);
}
</style>
