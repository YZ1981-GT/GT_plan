<template>
  <div v-if="taskId" class="approval-panel">
    <div class="approval-panel__left">
      <el-icon class="approval-panel__icon" :style="{ color: iconColor }"><Stamp /></el-icon>
      <div class="approval-panel__info">
        <div class="approval-panel__title-row">
          <span class="approval-panel__label">审批状态</span>
          <el-tag :type="statusTag" size="small" effect="light" round>{{ statusLabel }}</el-tag>
          <span v-if="fileName" class="approval-panel__file" :title="fileName">{{ fileName }}</span>
        </div>
        <div class="approval-panel__meta-row">
          <span v-if="approvalBy" class="approval-panel__meta">审批人：{{ approvalBy }}</span>
          <span v-if="rejectReason" class="approval-panel__reject">驳回原因：{{ rejectReason }}</span>
          <span v-if="!approvalBy && !rejectReason" class="approval-panel__hint">{{ hintText }}</span>
        </div>
      </div>
    </div>
    <div class="approval-panel__actions">
      <template v-if="canSubmit || canApprove">
        <el-button
          v-if="canSubmit"
          type="primary"
          size="small"
          :icon="Promotion"
          :loading="loading"
          @click="emit('submit')"
        >
          提交审批
        </el-button>
        <el-button
          v-if="canApprove"
          type="success"
          size="small"
          :icon="Select"
          :loading="loading"
          @click="emit('approve')"
        >
          批准
        </el-button>
        <el-button
          v-if="canApprove"
          type="danger"
          plain
          size="small"
          :icon="CloseBold"
          :loading="loading"
          @click="emit('reject')"
        >
          驳回
        </el-button>
      </template>
      <span v-else class="approval-panel__no-action">{{ noActionText }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CloseBold, Promotion, Select, Stamp } from '@element-plus/icons-vue'

const props = defineProps<{
  taskId: string | null
  status: string
  fileName?: string | null
  approvalBy?: string | null
  rejectReason?: string | null
  canSubmit?: boolean
  canApprove?: boolean
  loading?: boolean
}>()

const emit = defineEmits<{
  submit: []
  approve: []
  reject: []
}>()

const STATUS_MAP: Record<string, string> = {
  draft: '草稿',
  generated: '已生成',
  editing: '编辑中',
  pending_approval: '待审批',
  confirmed: '已确认',
  signed: '已签章',
  archived: '已归档',
}

const statusLabel = computed(() => STATUS_MAP[props.status] || props.status)

const statusTag = computed(() => {
  if (props.status === 'confirmed' || props.status === 'signed') return 'success'
  if (props.status === 'pending_approval' || props.status === 'editing') return 'warning'
  if (props.status === 'archived') return 'info'
  if (props.status === 'generated') return 'primary'
  return 'info'
})

const iconColor = computed(() => {
  const t = statusTag.value
  if (t === 'success') return 'var(--el-color-success)'
  if (t === 'warning') return 'var(--el-color-warning)'
  if (t === 'primary') return 'var(--el-color-primary)'
  return 'var(--el-text-color-secondary)'
})

// 无操作时的引导文案（填补空白，避免空洞面板）
const HINT_MAP: Record<string, string> = {
  draft: '当前为草稿版本，编辑后可提交审批',
  generated: '已生成待编辑，进入编辑后可提交审批',
  editing: '编辑完成后点击右侧「提交审批」',
  pending_approval: '已提交，等待审批人批准或驳回',
  confirmed: '已通过审批确认，可继续打包或签章',
  signed: '已签章，进入归档流程',
  archived: '已归档，交付流程结束',
}
const hintText = computed(() => HINT_MAP[props.status] || '选中一个交付物以查看审批流程')

const noActionText = computed(() => {
  if (props.status === 'pending_approval') return '等待审批人处理'
  if (props.status === 'confirmed') return '已确认'
  if (props.status === 'signed') return '已签章'
  if (props.status === 'archived') return '已归档'
  return '暂无可执行的审批操作'
})
</script>

<style scoped>
.approval-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
  padding: 12px 16px;
  background: var(--el-fill-color-lighter);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
}
.approval-panel__left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.approval-panel__icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  font-size: 18px;
  background: var(--el-bg-color);
  border-radius: 8px;
}
.approval-panel__info {
  min-width: 0;
}
.approval-panel__title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.approval-panel__label {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.approval-panel__file {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 260px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.approval-panel__meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 3px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.approval-panel__reject {
  color: var(--el-color-danger);
}
.approval-panel__hint {
  color: var(--el-text-color-secondary);
}
.approval-panel__actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}
.approval-panel__no-action {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
</style>
