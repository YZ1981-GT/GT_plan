<template>
  <div class="gt-project-wizard gt-fade-in">
    <!-- Content Area -->
    <div v-loading="wizardStore.loading" class="gt-wizard-content">
      <BasicInfoStep ref="basicInfoRef" :key="wizardStore.projectId || 'new'" />
    </div>

    <!-- 合并项目创建后预览自动生成的企业树（spec consol-autotree-linkage-closure R1：不需要确认，关闭即进入合并模块） -->
    <ConsolScopeConfigDialog
      v-model="showScopeConfig"
      :project-id="scopeConfigProjectId"
      mode="created"
      @update:model-value="onScopeConfigClosed"
    />

    <!-- Navigation Buttons -->
    <div class="gt-wizard-footer">
      <div class="gt-wizard-footer-spacer" />
      <el-button
        v-if="wizardStore.projectId"
        :loading="wizardStore.loading || submitting"
        @click="handleSave"
      >
        保存
      </el-button>
      <el-button
        type="primary"
        :loading="wizardStore.loading || submitting"
        @click="handleConfirm"
        :disabled="isAlreadyConfirmed"
      >
        {{ isAlreadyConfirmed ? '已确认' : wizardStore.projectId ? '确认' : '确认创建' }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { useWizardStore } from '@/stores/wizard'
import BasicInfoStep from '@/components/wizard/BasicInfoStep.vue'
import ConsolScopeConfigDialog from '@/components/wizard/ConsolScopeConfigDialog.vue'
import { useFormSubmit } from '@/composables/useFormSubmit'

const route = useRoute()
const router = useRouter()
const wizardStore = useWizardStore()

// Phase 3 需求 5.1：配置合并范围弹窗状态
const showScopeConfig = ref(false)
const scopeConfigProjectId = ref('')

type DataStepRef = {
  validate: () => Promise<Record<string, unknown> | null>
  formRef: FormInstance | undefined | null
}

const basicInfoRef = ref<DataStepRef | null>(null)

// V3 Req 3.3：通过 BasicInfoStep 暴露的 formRef 接入统一提交拦截
const wizardFormRef = computed(() => basicInfoRef.value?.formRef ?? null)
const { submit: submitWizard, submitting } = useFormSubmit(wizardFormRef)

// 项目是否已确认（planning 及之后状态不能重复确认）
const isAlreadyConfirmed = computed(() => {
  const state = wizardStore.stepData?.basic_info
  // 如果 wizardStore 已加载且项目存在，检查状态
  return !!(wizardStore.projectId && wizardStore.currentStepIndex >= 0 && state)
})

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

async function validateAndPersistCurrentStep(): Promise<Record<string, unknown> | null> {
  if (!basicInfoRef.value) return null
  const data = await basicInfoRef.value.validate()
  if (!data) return null

  if (!wizardStore.projectId) {
    await wizardStore.createProject(data as any)
  } else {
    await wizardStore.saveStep('basic_info', data)
  }
  showGroupNotices()
  return data
}

/** 后端对集团关系做的补齐/同步要告诉用户（需求 1.8：说明同步了哪个项目） */
function showGroupNotices() {
  const notices = wizardStore.lastNotices
  if (!notices.length) return
  ElNotification({
    title: '集团关系',
    message: notices.join('；'),
    type: 'info',
    duration: 8000,
  })
}

async function handleSave() {
  await submitWizard(async () => {
    const data = await validateAndPersistCurrentStep()
    if (!data) return
    ElMessage.success('项目信息已保存')
    router.push('/projects')
  })
}

async function handleConfirm() {
  await submitWizard(async () => {
    const data = await validateAndPersistCurrentStep()
    if (!data) return

    if (!wizardStore.projectId) {
      // 新建项目引导
      const { showGuide } = await import('@/composables/useWorkflowGuide')
      const proceed = await showGuide(
        'project_create',
        '🏢 创建审计项目',
        `<div style="line-height:1.8;font-size: var(--gt-font-size-sm)">
          <p>项目创建后，建议按以下顺序开展工作：</p>
          <ol style="padding-left:18px;margin:6px 0">
            <li><b>导入账套数据</b> — 上传科目余额表和序时账</li>
            <li><b>科目映射</b> — 将客户科目对应到标准科目</li>
            <li><b>生成底稿</b> — 从模板库生成项目底稿</li>
            <li><b>生成报表</b> — 根据试算表数据生成财务报表</li>
            <li><b>编写附注</b> — 生成并编辑附注章节</li>
          </ol>
          <p style="color: var(--gt-color-info);font-size: var(--gt-font-size-xs);margin-top:6px">💡 每个步骤都有详细引导，可随时在项目详情页的快捷操作中进入</p>
        </div>`,
        '确认创建',
      )
      if (!proceed) return
      ElMessage.success('项目创建成功')
      // formula-management-ux-improvements C1：创建成功后提示订阅公式模板
      const createdId = wizardStore.projectId
      if (createdId) {
        try {
          await ElMessageBox.confirm(
            '建议为新项目订阅事务所标准公式模板，订阅后项目公式会自动对齐全局设置，后续全局更新也会提醒确认。',
            '💡 公式模板订阅建议',
            {
              confirmButtonText: '去订阅',
              cancelButtonText: '稍后设置',
              type: 'info',
            },
          )
          // 跳转到项目公式管理（全局设置页的模板 Tab）
          router.push(`/settings/formula-global?tab=templates`)
          wizardStore.reset()
          return
        } catch {
          // 用户选了「稍后设置」，正常继续
        }
      }
      // Phase 3 需求 5.1：合并项目创建后弹"配置合并范围"步骤（R3：仅 consolidated 触发，非合并项目流程不变）
      const isConsolidated = (data as any)?.report_scope === 'consolidated'
      if (isConsolidated && createdId) {
        scopeConfigProjectId.value = createdId
        showScopeConfig.value = true
        return
      }
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
  })
}

/** 关闭企业树预览后进入合并模块（原「纳入子公司」入口已随自动建树下线，attached 事件不再存在） */
function onScopeConfigClosed(visible: boolean) {
  if (!visible && scopeConfigProjectId.value) {
    const pid = scopeConfigProjectId.value
    scopeConfigProjectId.value = ''
    wizardStore.reset()
    router.push(`/projects/${pid}/consolidation`)
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
