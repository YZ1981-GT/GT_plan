<!--
  AttachmentImpactDialog — 删除/替换附件前弹窗展示影响范围 (P0-3.7)
  ==============================================================================
  在用户删除或替换关键附件前，展示影响范围并要求确认。

  Props:
    visible: boolean (v-model)
    impact: AttachmentImpactResult
  Emits:
    confirm: 用户确认删除
    cancel: 用户取消
-->
<template>
  <el-dialog
    :model-value="visible"
    title="附件影响范围确认"
    width="520px"
    :close-on-click-modal="false"
    @update:model-value="onVisibleChange"
  >
    <div class="gt-impact-dialog">
      <div class="gt-impact-dialog__header">
        <el-icon class="gt-impact-dialog__warning-icon"><WarningFilled /></el-icon>
        <span v-if="impact.is_key_evidence" class="gt-impact-dialog__badge">关键证据</span>
        <span class="gt-impact-dialog__filename">{{ impact.file_name || '未知文件' }}</span>
      </div>

      <el-alert
        v-if="impact.requires_confirmation"
        type="warning"
        :closable="false"
        show-icon
      >
        该附件为关键证据且被 {{ impact.references_count }} 处引用，删除后相关模块将丢失证据链。
      </el-alert>

      <div v-if="impact.references_count > 0" class="gt-impact-dialog__refs">
        <p class="gt-impact-dialog__refs-title">被以下模块引用：</p>
        <el-table :data="impact.referenced_by" size="small" max-height="240">
          <el-table-column prop="module" label="模块" width="100" />
          <el-table-column prop="module_label" label="引用位置" />
        </el-table>
      </div>

      <div v-else class="gt-impact-dialog__empty">
        该附件当前无已知引用，可安全删除。
      </div>
    </div>

    <template #footer>
      <el-button @click="onCancel">取消</el-button>
      <el-button
        type="danger"
        :disabled="!canConfirm"
        @click="onConfirm"
      >
        确认删除
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'

export interface AttachmentImpactItem {
  module: string
  module_id: string
  module_label: string
  route?: string | null
}

export interface AttachmentImpactResult {
  project_id: string
  attachment_id: string
  file_name?: string | null
  is_key_evidence: boolean
  references_count: number
  referenced_by: AttachmentImpactItem[]
  requires_confirmation: boolean
}

const props = defineProps<{
  visible: boolean
  impact: AttachmentImpactResult
}>()

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
  (e: 'confirm'): void
  (e: 'cancel'): void
}>()

const canConfirm = computed(() => true) // P0: 始终允许确认（后续可增加二次输入）

function onVisibleChange(val: boolean) {
  emit('update:visible', val)
}

function onConfirm() {
  emit('confirm')
  emit('update:visible', false)
}

function onCancel() {
  emit('cancel')
  emit('update:visible', false)
}
</script>

<style scoped>
.gt-impact-dialog__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  font-size: 14px;
}

.gt-impact-dialog__warning-icon {
  color: #e6a23c;
  font-size: 20px;
}

.gt-impact-dialog__badge {
  background: var(--gt-color-primary-bg, #f4f0fa);
  color: var(--gt-color-primary, #4b2d77);
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.gt-impact-dialog__filename {
  font-weight: 500;
}

.gt-impact-dialog__refs {
  margin-top: 12px;
}

.gt-impact-dialog__refs-title {
  font-size: 13px;
  color: #606266;
  margin-bottom: 8px;
}

.gt-impact-dialog__empty {
  margin-top: 12px;
  color: #909399;
  font-size: 13px;
}
</style>
