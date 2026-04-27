<template>
  <div class="gt-project-wizard gt-fade-in">
    <!-- Step Bar -->
    <div class="gt-wizard-header">
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
    <div v-loading="wizardStore.loading" class="gt-wizard-content">
      <BasicInfoStep v-if="wizardStore.currentStepKey === 'basic_info'" ref="basicInfoRef" />
      <AccountImportStep v-else-if="wizardStore.currentStepKey === 'account_import'" ref="accountImportRef" />
      <AccountMappingStep v-else-if="wizardStore.currentStepKey === 'account_mapping'" ref="accountMappingRef" />
      <MaterialityStep v-else-if="wizardStore.currentStepKey === 'materiality'" ref="materialityRef" />
      <TeamAssignmentStep v-else-if="wizardStore.currentStepKey === 'team_assignment'" ref="teamAssignmentRef" :project-id="wizardStore.projectId ?? undefined" />
      <ConfirmationStep v-else-if="wizardStore.currentStepKey === 'confirmation'" />
    </div>

    <!-- Navigation Buttons -->
    <div class="gt-wizard-footer">
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
      <div class="gt-wizard-footer-spacer" />
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

type DataStepRef = {
  validate: () => Promise<Record<string, unknown> | null>
}

type BoolStepRef = {
  validate: () => Promise<boolean> | boolean
}

const basicInfoRef = ref<DataStepRef | null>(null)
const accountImportRef = ref<BoolStepRef | null>(null)
const accountMappingRef = ref<BoolStepRef | null>(null)
const materialityRef = ref<DataStepRef | null>(null)
const teamAssignmentRef = ref<BoolStepRef | null>(null)

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
  } else {
    // New project — reset wizard state
    wizardStore.reset()
  }
})

onUnmounted(() => {
  // Don't reset — allow resuming if user navigates back
})

async function validateAndPersistCurrentStep(step: StepKey): Promise<boolean> {
  if (step === 'basic_info') {
    if (!basicInfoRef.value) return false
    const data = await basicInfoRef.value.validate()
    if (!data) return false

    if (!wizardStore.projectId) {
      await wizardStore.createProject(data as any)
    } else {
      await wizardStore.saveStep('basic_info', data)
    }
    return true
  }

  if (step === 'account_import') {
    if (!accountImportRef.value) return false
    return Boolean(await accountImportRef.value.validate())
  }

  if (step === 'account_mapping') {
    if (!accountMappingRef.value) return false
    return Boolean(await accountMappingRef.value.validate())
  }

  if (step === 'materiality') {
    if (!materialityRef.value) return false
    const data = await materialityRef.value.validate()
    if (!data) return false
    await wizardStore.saveStep('materiality', data)
    return true
  }

  if (step === 'team_assignment') {
    if (!teamAssignmentRef.value) return false
    return Boolean(await teamAssignmentRef.value.validate())
  }

  return true
}

function getStepStatus(idx: number): string | undefined {
  const step = stepKeys[idx]
  if (wizardStore.isStepCompleted(step)) return 'success'
  if (idx === wizardStore.currentStepIndex) return 'process'
  return 'wait'
}

function onStepClick(idx: number) {
  // Allow navigating to any step
  wizardStore.goToStep(idx)
}

async function handleNext() {
  const currentStep = wizardStore.currentStepKey

  const ok = await validateAndPersistCurrentStep(currentStep)
  if (!ok) return

  wizardStore.goNext()
}

async function handleSave() {
  const currentStep = wizardStore.currentStepKey

  if (!wizardStore.projectId) {
    ElMessage.warning('请先创建项目')
    return
  }

  if (currentStep === 'confirmation') {
    ElMessage.warning('当前步骤无数据可保存')
    return
  }

  const ok = await validateAndPersistCurrentStep(currentStep)
  if (!ok) return

  ElMessage.success('保存成功')
}

function handlePrev() {
  wizardStore.goPrev()
}

async function handleConfirm() {
  if (!wizardStore.projectId) {
    ElMessage.warning('请先创建项目')
    return
  }

  const validation = await wizardStore.validateStep('confirmation')
  if (!validation.valid) {
    const fieldToStep: Record<string, StepKey> = {
      basic_info: 'basic_info',
      account_import: 'account_import',
      account_mapping: 'account_mapping',
      materiality: 'materiality',
      team_assignment: 'team_assignment',
      custom_template_id: 'basic_info',
    }
    const details = validation.messages
      .map((item) => {
        const mappedStep = fieldToStep[item.field]
        if (mappedStep) return `${STEP_LABELS[mappedStep]}：${item.message}`
        return item.message
      })
      .join('\n')

    await ElMessageBox.alert(
      `当前还不能确认创建，请先处理以下项：\n\n${details}`,
      '前置步骤未完成',
      { type: 'warning', confirmButtonText: '我知道了' },
    )

    const firstBlockingStep = validation.messages
      .map(item => fieldToStep[item.field])
      .find((step): step is StepKey => Boolean(step))
    if (firstBlockingStep) {
      wizardStore.goToStep(stepKeys.indexOf(firstBlockingStep))
    }
    return
  }

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
.gt-project-wizard {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: calc(100vh - 120px);
  background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm);
}

.gt-wizard-header {
  padding: var(--gt-space-6) var(--gt-space-8);
  border-bottom: 1px solid var(--gt-color-border-light);
}

.gt-wizard-content {
  flex: 1;
  padding: var(--gt-space-6) var(--gt-space-8);
  overflow-y: auto;
}

.gt-wizard-footer {
  display: flex;
  align-items: center;
  padding: var(--gt-space-4) var(--gt-space-8);
  border-top: 1px solid var(--gt-color-border-light);
}

.gt-wizard-footer-spacer {
  flex: 1;
}
</style>
