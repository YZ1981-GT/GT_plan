<template>
  <div class="gt-workflow-dashboard">
    <!-- 6-step progress bar -->
    <div class="gt-wf-steps">
      <div
        v-for="(step, idx) in steps"
        :key="step.key"
        class="gt-wf-step"
        :class="`gt-wf-step--${step.status}`"
      >
        <div class="gt-wf-step__icon">
          <span v-if="step.status === 'not_started'">○</span>
          <span v-else-if="step.status === 'in_progress'" class="gt-wf-step__spinner">◌</span>
          <span v-else-if="step.status === 'completed'">✓</span>
          <span v-else-if="step.status === 'needs_refresh'">⟳</span>
        </div>
        <div class="gt-wf-step__label">{{ step.label }}</div>
        <div v-if="idx < steps.length - 1" class="gt-wf-step__connector" :class="`gt-wf-step__connector--${step.status}`" />
      </div>
    </div>

    <!-- Action buttons -->
    <div class="gt-wf-actions">
      <el-button
        type="primary"
        size="small"
        :loading="chain.executing.value"
        @click="onRefreshAll"
      >
        🔄 一键刷新全部
      </el-button>
      <el-dropdown size="small" trigger="click" @command="onExportCommand">
        <el-button size="small">
          📤 导出 <el-icon style="margin-left:4px"><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="excel">仅报表 Excel</el-dropdown-item>
            <el-dropdown-item command="word">仅附注 Word</el-dropdown-item>
            <el-dropdown-item command="package">完整导出包</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- Execution summary (after completion) -->
    <div v-if="chain.isAllDone.value && chain.executionStatus.value" class="gt-wf-summary">
      <el-alert
        :type="chain.failedCount.value === 0 ? 'success' : 'warning'"
        :closable="true"
        show-icon
      >
        <template #title>
          执行完成：{{ chain.completedCount.value }} 步成功
          <template v-if="chain.failedCount.value > 0">，{{ chain.failedCount.value }} 步失败</template>
          <template v-if="chain.totalDurationMs.value">
            （耗时 {{ (chain.totalDurationMs.value / 1000).toFixed(1) }}s）
          </template>
        </template>
      </el-alert>
    </div>

    <!-- Export dialog -->
    <ExportDialog
      v-if="showExportDialog"
      :project-id="projectId"
      :year="year"
      @close="showExportDialog = false"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * WorkflowDashboard — 工作流状态仪表盘
 *
 * 6 步进度条：导入账套 → 科目映射 → 试算表 → 报表 → 底稿 → 附注
 * 每步状态图标：未开始/进行中/已完成/需刷新
 * "一键刷新全部"按钮 + "导出"下拉按钮
 *
 * Requirements: 7.1-7.8
 */
import { ref, computed, onMounted, watch } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { useChainExecution } from '@/composables/useChainExecution'
import { useProjectStore } from '@/stores/project'
import { handleApiError } from '@/utils/errorHandler'
import ExportDialog from '@/components/ExportDialog.vue'

const props = defineProps<{
  projectId: string
  year: number
}>()

const emit = defineEmits<{
  (e: 'step-action', step: string): void
}>()

const projectIdRef = computed(() => props.projectId)
const chain = useChainExecution(projectIdRef)

type StepStatus = 'not_started' | 'in_progress' | 'completed' | 'needs_refresh'

interface WorkflowStep {
  key: string
  label: string
  status: StepStatus
}

const steps = ref<WorkflowStep[]>([
  { key: 'import', label: '导入账套', status: 'not_started' },
  { key: 'mapping', label: '科目映射', status: 'not_started' },
  { key: 'trial_balance', label: '试算表', status: 'not_started' },
  { key: 'reports', label: '报表', status: 'not_started' },
  { key: 'workpapers', label: '底稿', status: 'not_started' },
  { key: 'notes', label: '附注', status: 'not_started' },
])

const showExportDialog = ref(false)

// Load workflow status from backend
async function loadStatus() {
  if (!props.projectId || !props.year) return
  try {
    const data: any = await api.get(
      `/api/projects/${props.projectId}/workflow/status`,
      { params: { year: props.year } }
    )
    if (data?.steps) {
      for (const step of steps.value) {
        const backendStep = data.steps[step.key]
        if (backendStep) {
          step.status = backendStep.status || 'not_started'
        }
      }
    }
  } catch {
    // Silent - workflow status endpoint may not exist yet
  }
}

function onRefreshAll() {
  chain.executeFullChain(props.year, undefined, false)
}

function onExportCommand(command: string) {
  showExportDialog.value = true
}

onMounted(() => loadStatus())
watch(() => [props.projectId, props.year], () => loadStatus())

// After chain execution completes, reload status
watch(() => chain.isAllDone.value, (done) => {
  if (done) {
    setTimeout(() => loadStatus(), 1000)
  }
})
</script>

<style scoped>
.gt-workflow-dashboard {
  padding: 12px 16px;
  background: var(--gt-color-primary-bg);
  border-radius: 8px;
  margin-bottom: 12px;
}

.gt-wf-steps {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
  margin-bottom: 12px;
}

.gt-wf-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  position: relative;
  min-width: 72px;
}

.gt-wf-step__icon {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  border: 2px solid #dcdfe6;
  background: var(--gt-color-bg-white);
  margin-bottom: 4px;
}

.gt-wf-step--completed .gt-wf-step__icon {
  border-color: #67c23a;
  background: var(--gt-bg-success);
  color: var(--gt-color-success);
}

.gt-wf-step--in_progress .gt-wf-step__icon {
  border-color: #409eff;
  background: var(--gt-bg-info);
  color: var(--gt-color-teal);
}

.gt-wf-step--needs_refresh .gt-wf-step__icon {
  border-color: #e6a23c;
  background: var(--gt-bg-warning);
  color: var(--gt-color-wheat);
}

.gt-wf-step__label {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-regular);
  white-space: nowrap;
}

.gt-wf-step--completed .gt-wf-step__label {
  color: var(--gt-color-success);
}

.gt-wf-step--needs_refresh .gt-wf-step__label {
  color: var(--gt-color-wheat);
}

.gt-wf-step__connector {
  position: absolute;
  top: 14px;
  left: calc(50% + 14px);
  width: calc(100% - 28px);
  height: 2px;
  background: var(--gt-color-border);
}

.gt-wf-step__connector--completed {
  background: var(--gt-color-success);
}

.gt-wf-step__connector--in_progress {
  background: var(--gt-color-teal);
}

.gt-wf-step__spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.gt-wf-actions {
  display: flex;
  justify-content: center;
  gap: 8px;
}

.gt-wf-summary {
  margin-top: 12px;
}
</style>
