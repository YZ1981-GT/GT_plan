<template>
  <div class="gt-project-wizard gt-fade-in">
    <!-- Content Area -->
    <div v-loading="wizardStore.loading" class="gt-wizard-content">
      <BasicInfoStep ref="basicInfoRef" />
    </div>

    <!-- Navigation Buttons -->
    <div class="gt-wizard-footer">
      <div class="gt-wizard-footer-spacer" />
      <el-button
        v-if="wizardStore.projectId"
        :loading="wizardStore.loading"
        @click="handleSave"
      >
        保存
      </el-button>
      <el-button
        type="primary"
        :loading="wizardStore.loading"
        @click="handleConfirm"
      >
        {{ wizardStore.projectId ? '确认' : '确认创建' }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useWizardStore } from '@/stores/wizard'
import BasicInfoStep from '@/components/wizard/BasicInfoStep.vue'

const route = useRoute()
const router = useRouter()
const wizardStore = useWizardStore()

type DataStepRef = {
  validate: () => Promise<Record<string, unknown> | null>
}

const basicInfoRef = ref<DataStepRef | null>(null)

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

async function validateAndPersistCurrentStep(): Promise<boolean> {
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

async function handleSave() {
  if (!wizardStore.projectId) {
    ElMessage.warning('请先创建项目')
    return
  }
  const ok = await validateAndPersistCurrentStep()
  if (!ok) return
  ElMessage.success('保存成功')
}

async function handleConfirm() {
  const ok = await validateAndPersistCurrentStep()
  if (!ok) return

  if (!wizardStore.projectId) {
    // 新建项目，createProject 已在 validate 中完成
    ElMessage.success('项目创建成功')
    wizardStore.reset()
    router.push('/projects')
    return
  }

  // 已有项目，确认保存
  try {
    await wizardStore.confirmProject()
    ElMessage.success('项目保存成功')
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
