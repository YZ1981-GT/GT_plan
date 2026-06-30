<script setup lang="ts">
/**
 * D4TabPolicyCheck — D4-5 CAS14五步法政策检查
 *
 * 5 card steps, each with: policy reference (readonly details),
 * situation textarea, evaluation textarea + AI disabled button,
 * Y/N/NA conclusion radio. Progress bar at top.
 *
 * Requirements: 7.1-7.7, 21.3
 */
import { inject, toRef, type Ref } from 'vue'
import { useD4PolicyCheck } from '../../composables/useD4PolicyCheck'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const {
  steps,
  completedSteps,
  totalSteps,
  progress,
  updateSituation,
  updateEvaluation,
  updateConclusion,
  isStepComplete,
} = useD4PolicyCheck({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

function getConclusionType(conclusion: string): '' | 'success' | 'danger' | 'warning' {
  if (conclusion === 'Y') return 'success'
  if (conclusion === 'N') return 'danger'
  if (conclusion === 'NA') return 'warning'
  return ''
}
</script>

<template>
  <div class="d4-policy-check">
    <!-- Progress Bar -->
    <el-card shadow="never" class="mb-4">
      <div class="flex items-center justify-between mb-2">
        <span class="text-sm font-medium">CAS14五步法评价进度</span>
        <span class="text-sm text-gray-500">{{ totalSteps }}步中已完成{{ completedSteps }}步</span>
      </div>
      <el-progress
        :percentage="progress"
        :stroke-width="10"
        :format="() => `${completedSteps}/${totalSteps}`"
      />
    </el-card>

    <!-- Steps Cards -->
    <div v-for="step in steps" :key="step.stepNumber" class="mb-4">
      <el-card shadow="hover" :class="{ 'step-complete': isStepComplete(step.stepNumber) }">
        <!-- Header -->
        <template #header>
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <el-tag :type="isStepComplete(step.stepNumber) ? 'success' : 'info'" size="small" round>
                {{ step.stepNumber }}
              </el-tag>
              <span class="font-medium">{{ step.title }}</span>
            </div>
            <el-button
              v-if="openReviewDialog"
              size="small"
              text
              @click="openReviewDialog(`D4-5-step${step.stepNumber}`)"
            >
              💬
            </el-button>
          </div>
        </template>

        <!-- Policy Reference (readonly collapsible) -->
        <details class="policy-reference mb-4">
          <summary class="cursor-pointer text-sm text-blue-600">📋 准则条款参考</summary>
          <div class="mt-2 p-3 bg-blue-50 border-l-4 border-blue-400 text-sm text-gray-700 whitespace-pre-wrap">
            {{ step.policyReference }}
          </div>
        </details>

        <!-- Situation -->
        <div class="mb-3">
          <label class="block text-sm font-medium text-gray-600 mb-1">实际情况描述</label>
          <el-input
            type="textarea"
            :rows="3"
            :model-value="step.situation"
            :disabled="isReadonly"
            placeholder="请描述被审计单位的实际收入确认情况..."
            @input="(val: string) => updateSituation(step.stepNumber, val)"
          />
        </div>

        <!-- Evaluation + AI -->
        <div class="mb-3">
          <div class="flex items-center justify-between mb-1">
            <label class="text-sm font-medium text-gray-600">审计师评价</label>
            <el-button size="small" disabled>
              🤖 AI辅助
            </el-button>
          </div>
          <el-input
            type="textarea"
            :rows="3"
            :model-value="step.evaluation"
            :disabled="isReadonly"
            placeholder="审计师对该步骤的专业评价..."
            @input="(val: string) => updateEvaluation(step.stepNumber, val)"
          />
        </div>

        <!-- Conclusion Radio -->
        <div class="flex items-center gap-4">
          <label class="text-sm font-medium text-gray-600">结论：</label>
          <el-radio-group
            :model-value="step.conclusion"
            :disabled="isReadonly"
            @change="(val: any) => updateConclusion(step.stepNumber, val)"
          >
            <el-radio-button value="Y">符合(Y)</el-radio-button>
            <el-radio-button value="N">不符合(N)</el-radio-button>
            <el-radio-button value="NA">不适用(NA)</el-radio-button>
          </el-radio-group>
          <el-tag v-if="step.conclusion" :type="getConclusionType(step.conclusion)" size="small">
            {{ step.conclusion === 'Y' ? '✓ 符合' : step.conclusion === 'N' ? '✗ 不符合' : '— 不适用' }}
          </el-tag>
        </div>

        <!-- Warning when N without explanation -->
        <el-alert
          v-if="step.conclusion === 'N' && !step.evaluation.trim()"
          type="warning"
          :closable="false"
          show-icon
          class="mt-3"
        >
          结论为"不符合"时，请在审计师评价中说明具体原因
        </el-alert>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.d4-policy-check {
  padding: 16px;
}
.step-complete {
  border-left: 3px solid var(--el-color-success);
}
.policy-reference summary {
  user-select: none;
}
.mb-4 {
  margin-bottom: 16px;
}
.mb-3 {
  margin-bottom: 12px;
}
.mb-2 {
  margin-bottom: 8px;
}
.mb-1 {
  margin-bottom: 4px;
}
</style>
