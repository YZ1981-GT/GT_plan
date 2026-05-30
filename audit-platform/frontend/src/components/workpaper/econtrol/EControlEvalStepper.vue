<!--
  EControlEvalStepper.vue — evaluation_step 子模式渲染组件

  纯渲染 + emit，不持有步骤状态机。
  状态机（activeStepNo / advanceStep / goToStep / currentStep / isTerminalStep）
  保留在 shell 顶层（ADR D4），本组件通过 props 接收 + emit 通知 shell 改值。

  渲染：el-steps stepper + 当前步骤表单（FieldInput）+ 上/下一步导航 + visibleStepFields
  Validates: Requirements 11, 13
-->

<template>
  <section class="gt-e__eval">
    <!-- el-steps stepper -->
    <el-steps
      :active="activeStepIdx"
      :process-status="stepProcessStatus"
      finish-status="success"
      align-center
      class="gt-e__stepper"
    >
      <el-step
        v-for="step in steps"
        :key="step.step"
        :title="`步骤${stepLabel(step.step)}`"
        :description="stepShortTitle(step)"
      />
    </el-steps>

    <!-- 当前步骤内容 -->
    <div v-if="currentStep" class="gt-e__step-content">
      <header class="gt-e__step-header">
        <h3 class="gt-e__step-title">{{ currentStep.title }}</h3>
        <p
          v-if="currentStep.description"
          class="gt-e__step-desc"
        >{{ currentStep.description }}</p>
      </header>

      <el-form
        :model="data"
        label-position="top"
        :disabled="readonly"
      >
        <el-form-item
          v-for="field in visibleStepFields"
          :key="field.name"
          :label="field.label"
          :required="!!field.required"
        >
          <FieldInput
            :field="field"
            :model-value="data[field.name]"
            :readonly="readonly"
            @update:model-value="(v: any) => onFieldUpdate(field.name, v)"
          />
          <div v-if="field.hint" class="gt-e__field-hint">
            <el-icon><InfoFilled /></el-icon>
            <span>{{ field.hint }}</span>
          </div>
        </el-form-item>
      </el-form>

      <!-- 步骤导航 -->
      <div class="gt-e__step-nav">
        <el-button
          :disabled="activeStepIdx === 0"
          @click="emit('go-to-step', activeStepIdx - 1)"
        >
          上一步
        </el-button>
        <el-button
          v-if="!isTerminalStep"
          type="primary"
          @click="emit('step-advance', activeStepNo)"
        >
          下一步
        </el-button>
        <el-tag v-else type="success" size="large">已到达终结步骤</el-tag>
        <el-button
          text
          size="small"
          class="gt-e__attach-btn"
          @click="emit('open-attachment', `step_${currentStep.step}`)"
        >📎 附件</el-button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import FieldInput from './FieldInput.vue'
import type { FieldDef, StepDef, EControlTestSchema } from '../GtEControlTest.types'
import { safeEvaluate, stepLabel, stepShortTitle } from './econtrolHelpers'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  schema: EControlTestSchema
  data: Record<string, any>
  activeStepNo: number
  currentStep: StepDef | null
  isTerminalStep: boolean
  readonly?: boolean
}>()

const emit = defineEmits<{
  'field-change': [name: string]
  'step-advance': [step: number]
  'go-to-step': [index: number]
  'open-attachment': [rowRef: string]
}>()

// ─── Computed (rendering only) ───────────────────────────────────────────────

const steps = computed<StepDef[]>(() => {
  const arr = props.schema?.steps ?? []
  return [...arr].sort((a, b) => (a.step ?? 0) - (b.step ?? 0))
})

const activeStepIdx = computed(() => {
  const idx = steps.value.findIndex(s => s.step === props.activeStepNo)
  return idx >= 0 ? idx : 0
})

const stepProcessStatus = computed<'wait' | 'process' | 'finish' | 'error' | 'success'>(() => {
  if (props.isTerminalStep) return 'success'
  return 'process'
})

const visibleStepFields = computed<FieldDef[]>(() => {
  if (!props.currentStep) return []
  return (props.currentStep.fields || []).filter(f => {
    if (!f.conditional) return true
    return safeEvaluate(f.conditional, props.data)
  })
})

// ─── Handlers ────────────────────────────────────────────────────────────────

function onFieldUpdate(name: string, value: any) {
  // Mutate the data object (passed by reference from shell's evalData ref)
  props.data[name] = value
  emit('field-change', name)
}
</script>

<style scoped>
.gt-e__eval {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.gt-e__stepper {
  padding: 8px 0 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.gt-e__step-content {
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 16px 20px;
  background: var(--gt-color-bg-white, #fff);
}
.gt-e__step-header { margin-bottom: 16px; }
.gt-e__step-title {
  margin: 0 0 6px;
  font-size: 16px;
  font-weight: 600;
  color: var(--el-color-primary);
}
.gt-e__step-desc {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
  white-space: pre-line;
}
.gt-e__step-nav {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px dashed var(--el-border-color-lighter);
}
.gt-e__attach-btn { font-size: 14px; }
.gt-e__field-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gt-e__field-hint .el-icon { color: var(--el-color-info); }
</style>
