<template>
  <div class="project-wizard">
    <!-- Step Bar -->
    <div class="wizard-header">
      <el-steps :active="wizardStore.currentStepIndex" finish-status="success" align-center>
        <el-step
          v-for="(key, idx) in stepKeys"
          :key="key"
          :title="STEP_LABELS[key]"
          :status="getStepStatus(idx)"
          @click="onStepClick(idx)"
        />
      </el-steps>
    </div>

    <!-- Content Area -->
    <div v-loading="wizardStore.loading" class="wizard-content">
      <BasicInfoStep v-if="wizardStore.currentStepKey === 'basic_info'" ref="basicInfoRef" />
      <AccountImportStep v-else-if="wizardStore.currentStepKey === 'account_import'" />
      <AccountMappingStep v-else-if="wizardStore.currentStepKey === 'account_mapping'" />
      <MaterialityStep v-else-if="wizardStore.currentStepKey === 'materiality'" />
      <TeamAssignmentStep v-else-if="wizardStore.currentStepKey === 'team_assignment'" />
      <ConfirmationStep v-else-if="wizardStore.currentStepKey === 'confirmation'" />
    </div>

    <!-- Navigation Buttons -->
    <div class="wizard-footer">
      <el-button v-if="!wizardStore.isFirstStep" @click="handlePrev">
        上一步
      </el-button>
      <el-button
        v-if="wizardStore.projectId"
        :loading="wizardStore.loading"
        @click="handleSave"
      >
        保存
      </el-button>
      <div class="footer-spacer" />
      <el-button
        v-if="!wizardStore.isLastStep"
        type="primary"
        :loading="wizardStore.loading"
        @click="handleNext"
      >
        下一步
      </el-button>
      <el-button
        v-if="wizardStore.isLastStep"
        type="primary"
        :loading="wizardStore.loading"
        @click="handleConfirm"
      >
        确认创建
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useWizardStore, STEP_LABELS, type StepKey } from '@/stores/wizard'
import BasicInfoStep from '@/components/wizard/BasicInfoStep.vue'
import AccountImportStep from '@/components/wizard/AccountImportStep.vue'
import AccountMappingStep from '@/components/wizard/AccountMappingStep.vue'
import MaterialityStep from '@/components/wizard/MaterialityStep.vue'
import TeamAssignmentStep from '@/components/wizard/TeamAssignmentStep.vue'
import ConfirmationStep from '@/components/wizard/ConfirmationStep.vue'

const route = useRoute()
const router = useRouter()
const wizardStore = useWizardStore()

const basicInfoRef = ref<InstanceType<typeof BasicInfoStep> | null>(null)

const stepKeys: StepKey[] = [
  'basic_info',
  'account_import',
  'account_mapping',
  'materiality',
  'team_assignment',
  'confirmation',
]

onMounted(async () => {
  // If editing an existing project, load wizard state
  const projectId = route.query.projectId as string | undefined
  if (projectId) {
    await wizardStore.loadWizardState(projectId)
  }
})

onUnmounted(() => {
  // Don't reset — allow resuming if user navigates back
})

function getStepStatus(idx: number): string | undefined {
  if (idx < wizardStore.currentStepIndex) return 'success'
  if (idx === wizardStore.currentStepIndex) return 'process'
  return 'wait'
}

function onStepClick(idx: number) {
  // Allow navigating to any step
  wizardStore.goToStep(idx)
}

async function handleNext() {
  const currentStep = wizardStore.currentStepKey

  // Step-specific validation
  if (currentStep === 'basic_info') {
    if (!basicInfoRef.value) return
    const data = await basicInfoRef.value.validate()
    if (!data) return

    // Create project if not yet created, otherwise save step
    if (!wizardStore.projectId) {
      await wizardStore.createProject(data)
    } else {
      await wizardStore.saveStep('basic_info', data as unknown as Record<string, unknown>)
    }
  }

  wizardStore.goNext()
}

async function handleSave() {
  const currentStep = wizardStore.currentStepKey

  if (!wizardStore.projectId) {
    ElMessage.warning('请先创建项目')
    return
  }

  // Step-specific validation and save
  if (currentStep === 'basic_info') {
    if (!basicInfoRef.value) return
    const data = await basicInfoRef.value.validate()
    if (!data) return

    await wizardStore.saveStep('basic_info', data as unknown as Record<string, unknown>)
    ElMessage.success('保存成功')
  } else {
    // For other steps, save current step data from store
    const stepData = wizardStore.stepData[currentStep]
    if (stepData) {
      await wizardStore.saveStep(currentStep, stepData)
      ElMessage.success('保存成功')
    } else {
      ElMessage.warning('当前步骤无数据可保存')
    }
  }
}

function handlePrev() {
  wizardStore.goPrev()
}

async function handleConfirm() {
  try {
    await ElMessageBox.confirm('确认创建项目？项目将进入计划阶段。', '确认', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      type: 'info',
    })
  } catch {
    return // User cancelled
  }

  try {
    await wizardStore.confirmProject()
    ElMessage.success('项目创建成功')
    wizardStore.reset()
    router.push('/projects')
  } catch {
    // Error already handled by http interceptor
  }
}
</script>

<style scoped>
.project-wizard {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: calc(100vh - 120px);
  background: #fff;
  border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm);
}

.wizard-header {
  padding: var(--gt-space-6) var(--gt-space-8);
  border-bottom: 1px solid #eee;
}

.wizard-content {
  flex: 1;
  padding: var(--gt-space-6) var(--gt-space-8);
  overflow-y: auto;
}

.wizard-footer {
  display: flex;
  align-items: center;
  padding: var(--gt-space-4) var(--gt-space-8);
  border-top: 1px solid #eee;
}

.footer-spacer {
  flex: 1;
}
</style>
