<template>
  <el-card v-if="taskId" class="approval-panel" shadow="never">
    <template #header>
      <span>审批状态</span>
      <el-tag size="small" :type="statusTag">{{ statusLabel }}</el-tag>
    </template>
    <p v-if="approvalBy" class="approval-panel__meta">审批人：{{ approvalBy }}</p>
    <p v-if="rejectReason" class="approval-panel__reject">驳回原因：{{ rejectReason }}</p>
    <div class="approval-panel__actions">
      <el-button
        v-if="canSubmit"
        type="primary"
        size="small"
        :loading="loading"
        @click="emit('submit')"
      >
        提交审批
      </el-button>
      <el-button
        v-if="canApprove"
        type="success"
        size="small"
        :loading="loading"
        @click="emit('approve')"
      >
        批准
      </el-button>
      <el-button
        v-if="canApprove"
        type="danger"
        size="small"
        :loading="loading"
        @click="emit('reject')"
      >
        驳回
      </el-button>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  taskId: string | null
  status: string
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
  editing: '编辑中',
  pending_approval: '待审批',
  confirmed: '已确认',
  signed: '已签章',
  archived: '已归档',
}

const statusLabel = computed(() => STATUS_MAP[props.status] || props.status)

const statusTag = computed(() => {
  if (props.status === 'confirmed' || props.status === 'signed') return 'success'
  if (props.status === 'pending_approval') return 'warning'
  if (props.status === 'archived') return 'info'
  return ''
})
</script>

<style scoped>
.approval-panel {
  margin-bottom: 12px;
}
.approval-panel__meta,
.approval-panel__reject {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.approval-panel__reject {
  color: var(--el-color-danger);
}
.approval-panel__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
