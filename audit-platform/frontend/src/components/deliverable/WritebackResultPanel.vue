<!--
  WritebackResultPanel.vue — 回填结果分组展示

  Spec:    deliverable-lineage-and-writeback Task 16.1
  Design:  前端设计「OnlyOffice 集成点」+ 需求 7.1/11.4
  Reqs:    7.1, 11.4

  功能：
    - "回填到附注模块"按钮（显式触发回填）
    - WritebackResult 分组展示（written/rejected/conflicts/skipped）
    - rejected 项显示中文 AJE 指引
    - 终态出品物只读：signed/confirmed/archived 禁用按钮 + tooltip
    - 全中文化 + GT 紫令牌
-->
<template>
  <div class="writeback-panel">
    <!-- 回填按钮 -->
    <div class="writeback-panel__trigger">
      <el-tooltip
        :content="terminalStateTooltip"
        :disabled="!isTerminalState"
        placement="top"
      >
        <span class="writeback-panel__btn-wrapper">
          <el-button
            type="primary"
            :disabled="isTerminalState || loading"
            :loading="loading"
            class="writeback-panel__btn"
            @click="onWriteback"
          >
            回填到附注模块
          </el-button>
        </span>
      </el-tooltip>
    </div>

    <!-- 回填结果展示 -->
    <div v-if="result" class="writeback-panel__result">
      <!-- 成功回填 -->
      <div v-if="result.written.length > 0" class="writeback-panel__group writeback-panel__group--success">
        <div class="writeback-panel__group-header">
          <el-icon class="writeback-panel__group-icon"><CircleCheck /></el-icon>
          <span>已回填（{{ result.written.length }}）</span>
        </div>
        <div
          v-for="item in result.written"
          :key="item"
          class="writeback-panel__item"
        >
          {{ item }}
        </div>
      </div>

      <!-- 被拒绝（含 AJE 指引） -->
      <div v-if="result.rejected.length > 0" class="writeback-panel__group writeback-panel__group--rejected">
        <div class="writeback-panel__group-header">
          <el-icon class="writeback-panel__group-icon"><CircleClose /></el-icon>
          <span>已拒绝（{{ result.rejected.length }}）</span>
        </div>
        <div
          v-for="item in result.rejected"
          :key="item.section_code"
          class="writeback-panel__item writeback-panel__item--rejected"
        >
          <span class="writeback-panel__item-code">{{ item.section_code }}</span>
          <span class="writeback-panel__item-reason">{{ item.reason }}</span>
          <span class="writeback-panel__item-guide">
            金额变更须通过调整分录（AJE/RJE）修正，不可从出品物回填
          </span>
        </div>
      </div>

      <!-- 冲突待裁决 -->
      <div v-if="result.conflicts.length > 0" class="writeback-panel__group writeback-panel__group--conflict">
        <div class="writeback-panel__group-header">
          <el-icon class="writeback-panel__group-icon"><Warning /></el-icon>
          <span>冲突待裁决（{{ result.conflicts.length }}）</span>
        </div>
        <el-button
          size="small"
          type="warning"
          plain
          class="writeback-panel__resolve-btn"
          @click="onOpenConflictDialog"
        >
          查看冲突并裁决
        </el-button>
      </div>

      <!-- 跳过（锚点丢失） -->
      <div v-if="result.skipped.length > 0" class="writeback-panel__group writeback-panel__group--skipped">
        <div class="writeback-panel__group-header">
          <el-icon class="writeback-panel__group-icon"><InfoFilled /></el-icon>
          <span>已跳过（{{ result.skipped.length }}）</span>
        </div>
        <div
          v-for="item in result.skipped"
          :key="item"
          class="writeback-panel__item"
        >
          {{ item }}（无法定位锚点，未回填）
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { CircleCheck, CircleClose, Warning, InfoFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

export interface WritebackResultItem {
  section_code: string
  reason?: string
  kind?: string
}

export interface WritebackConflict {
  section_code: string
  deliverable_value: string
  upstream_value: string
  baseline_value: string
}

export interface WritebackResult {
  written: string[]
  rejected: WritebackResultItem[]
  conflicts: WritebackConflict[]
  skipped: string[]
  trace_id: string | null
  message?: string
}

const TERMINAL_STATUSES = ['signed', 'confirmed', 'archived'] as const

const props = defineProps<{
  projectId: string
  wordExportTaskId: string
  year?: number
  deliverableStatus?: string
}>()

const emit = defineEmits<{
  (e: 'open-conflict-dialog', conflicts: WritebackConflict[]): void
  (e: 'writeback-complete', result: WritebackResult): void
}>()

const loading = ref(false)
const result = ref<WritebackResult | null>(null)

const isTerminalState = computed(() => {
  if (!props.deliverableStatus) return false
  return TERMINAL_STATUSES.includes(props.deliverableStatus as any)
})

const terminalStateTooltip = '该出品物已签字/确认/归档，不可回填或刷新'

async function onWriteback(): Promise<void> {
  if (isTerminalState.value) return

  loading.value = true
  result.value = null

  try {
    const url = `/api/projects/${props.projectId}/deliverables/${props.wordExportTaskId}/writeback`
    const data = await api.post<any>(url, { year: props.year || new Date().getFullYear() })

    // 异步 job 返回
    if (data.job_id) {
      ElMessage.info('章节数较多，已提交后台任务处理')
      return
    }

    result.value = data as WritebackResult
    emit('writeback-complete', result.value)

    if (result.value.written.length > 0) {
      ElMessage.success(`已成功回填 ${result.value.written.length} 个章节`)
    }
    if (result.value.conflicts.length > 0) {
      ElMessage.warning(`${result.value.conflicts.length} 个章节存在冲突，需要裁决`)
    }
  } catch (e: any) {
    if (e?.response?.status === 403) {
      ElMessage.error('权限不足：需要编辑权限才能执行回填')
    } else if (e?.response?.status === 409) {
      ElMessage.warning(e?.response?.data?.detail || e?.response?.data?.message || '该出品物已终态，不可回填')
    } else {
      ElMessage.error(e?.response?.data?.message || e?.message || '回填失败')
    }
  } finally {
    loading.value = false
  }
}

function onOpenConflictDialog(): void {
  if (result.value?.conflicts) {
    emit('open-conflict-dialog', result.value.conflicts)
  }
}

defineExpose({
  onWriteback,
  result,
  loading,
  isTerminalState,
})
</script>

<style scoped>
.writeback-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.writeback-panel__trigger {
  display: flex;
  align-items: center;
}

.writeback-panel__btn-wrapper {
  display: inline-flex;
}

.writeback-panel__btn {
  font-size: 13px;
  --el-button-text-color: #fff;
  --el-button-bg-color: var(--gt-color-primary, #4b2d77);
  --el-button-border-color: var(--gt-color-primary, #4b2d77);
}

.writeback-panel__btn:not(.is-disabled):hover {
  --el-button-hover-bg-color: #5e3a94;
  --el-button-hover-border-color: #5e3a94;
}

.writeback-panel__result {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.writeback-panel__group {
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter);
}

.writeback-panel__group--success {
  border-color: var(--el-color-success-light-5);
  background: var(--el-color-success-light-9);
}

.writeback-panel__group--rejected {
  border-color: var(--el-color-danger-light-5);
  background: var(--el-color-danger-light-9);
}

.writeback-panel__group--conflict {
  border-color: var(--el-color-warning-light-5);
  background: var(--el-color-warning-light-9);
}

.writeback-panel__group--skipped {
  border-color: var(--el-border-color-lighter);
  background: var(--el-fill-color-lighter);
}

.writeback-panel__group-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 6px;
}

.writeback-panel__group-icon {
  font-size: 15px;
}

.writeback-panel__group--success .writeback-panel__group-icon {
  color: var(--el-color-success);
}

.writeback-panel__group--rejected .writeback-panel__group-icon {
  color: var(--el-color-danger);
}

.writeback-panel__group--conflict .writeback-panel__group-icon {
  color: var(--el-color-warning);
}

.writeback-panel__group--skipped .writeback-panel__group-icon {
  color: var(--el-text-color-secondary);
}

.writeback-panel__item {
  font-size: 12px;
  padding: 4px 0;
  color: var(--el-text-color-primary);
}

.writeback-panel__item--rejected {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.writeback-panel__item-code {
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
}

.writeback-panel__item-reason {
  color: var(--el-color-danger);
  font-size: 11px;
}

.writeback-panel__item-guide {
  color: var(--el-text-color-secondary);
  font-size: 11px;
  font-style: italic;
}

.writeback-panel__resolve-btn {
  margin-top: 6px;
  font-size: 12px;
}
</style>
