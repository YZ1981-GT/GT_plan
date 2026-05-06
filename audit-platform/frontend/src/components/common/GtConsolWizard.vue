<template>
  <div class="gt-consol-wizard">
    <el-steps :active="activeStep" finish-status="success" align-center size="small">
      <el-step
        v-for="(step, idx) in steps"
        :key="idx"
        :title="step.title"
        :description="step.description"
        :icon="step.icon"
        :status="getStepStatus(idx)"
        @click="onStepClick(idx)"
        style="cursor: pointer"
      />
    </el-steps>
  </div>
</template>

<script setup lang="ts">
/**
 * GtConsolWizard — 合并模块向导式步骤条 [R9.1]
 *
 * 引导用户按正确顺序完成合并报表编制流程：
 * 1. 配置合并范围 → 2. 导入子公司数据 → 3. 合并试算表 →
 * 4. 编制抵消分录 → 5. 生成合并报表 → 6. 编制附注
 */
import { computed } from 'vue'

export interface WizardStep {
  title: string
  description?: string
  icon?: any
  completed?: boolean
  tabName?: string
}

const props = withDefaults(defineProps<{
  /** 当前激活步骤（0-based） */
  activeStep?: number
  /** 步骤定义 */
  steps?: WizardStep[]
  /** 各步骤完成状态 */
  completedSteps?: boolean[]
}>(), {
  activeStep: 0,
  steps: () => [
    { title: '合并范围', description: '配置子公司', tabName: 'structure' },
    { title: '导入数据', description: '子公司余额表', tabName: 'worksheets' },
    { title: '合并试算', description: '汇总重算', tabName: 'worksheets' },
    { title: '抵消分录', description: '编制抵消', tabName: 'worksheets' },
    { title: '合并报表', description: '生成报表', tabName: 'worksheets' },
    { title: '合并附注', description: '编制附注', tabName: 'worksheets' },
  ],
  completedSteps: () => [],
})

const emit = defineEmits<{
  (e: 'step-click', stepIndex: number, step: WizardStep): void
}>()

function getStepStatus(idx: number): '' | 'wait' | 'process' | 'finish' | 'error' | 'success' {
  if (props.completedSteps[idx]) return 'success'
  if (idx === props.activeStep) return 'process'
  if (idx < props.activeStep) return 'finish'
  return 'wait'
}

function onStepClick(idx: number) {
  emit('step-click', idx, props.steps[idx])
}
</script>

<style scoped>
.gt-consol-wizard {
  padding: 12px 20px;
  background: linear-gradient(135deg, #f8f6fc 0%, #f0edf5 100%);
  border-radius: 8px;
  margin-bottom: 12px;
}

.gt-consol-wizard :deep(.el-step__title) {
  font-size: 13px;
}

.gt-consol-wizard :deep(.el-step__description) {
  font-size: 11px;
}

.gt-consol-wizard :deep(.el-step__head.is-success) {
  color: #4b2d77;
  border-color: #4b2d77;
}

.gt-consol-wizard :deep(.el-step__title.is-success) {
  color: #4b2d77;
}

.gt-consol-wizard :deep(.el-step__head.is-process) {
  color: #4b2d77;
  border-color: #4b2d77;
}

.gt-consol-wizard :deep(.el-step__title.is-process) {
  color: #4b2d77;
  font-weight: 600;
}
</style>
