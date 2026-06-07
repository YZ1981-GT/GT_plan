<!--
  AttachmentActionBar — 附件统一动作栏 (P0-4)
  ==============================================================================
  统一展示预览、编辑、下载、引用四类动作。
  根据文件类型和 OnlyOffice/WOPI 健康状态决定可用动作。

  Props:
    attachment: { id, file_name, file_type, file_path }
    projectId: string
    onlyofficeHealth: 'healthy' | 'degraded' | 'unavailable'
    readOnly: boolean — 强制只读模式

  Emits:
    preview: 预览
    edit: 在线编辑
    download: 下载
    cite: 引用（创建 EvidenceRef）
-->
<template>
  <div class="gt-attachment-action-bar">
    <!-- 健康状态指示 -->
    <div class="gt-attachment-action-bar__status">
      <span
        class="gt-attachment-action-bar__health-dot"
        :class="`gt-attachment-action-bar__health-dot--${onlyofficeHealth}`"
      />
      <span class="gt-attachment-action-bar__health-text">
        {{ healthLabel }}
      </span>
      <el-tag v-if="readOnly" size="small" type="info">只读</el-tag>
    </div>

    <!-- 动作按钮组 -->
    <div class="gt-attachment-action-bar__actions">
      <el-button
        size="small"
        :icon="ViewIcon"
        @click="$emit('preview')"
      >
        预览
      </el-button>

      <el-button
        v-if="canEdit"
        size="small"
        :icon="EditIcon"
        :disabled="readOnly"
        @click="$emit('edit')"
      >
        编辑
      </el-button>

      <el-button
        size="small"
        :icon="DownloadIcon"
        @click="$emit('download')"
      >
        下载
      </el-button>

      <el-button
        size="small"
        :icon="LinkIcon"
        @click="$emit('cite')"
      >
        引用
      </el-button>
    </div>

    <!-- 文件信息 -->
    <div class="gt-attachment-action-bar__info">
      <span class="gt-attachment-action-bar__filename">{{ attachment.file_name }}</span>
      <span class="gt-attachment-action-bar__type">{{ fileTypeLabel }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { View as ViewIcon, Edit as EditIcon, Download as DownloadIcon, Link as LinkIcon } from '@element-plus/icons-vue'

export interface AttachmentInfo {
  id: string
  file_name: string
  file_type: string
  file_path?: string
}

export type OnlyOfficeHealth = 'healthy' | 'degraded' | 'unavailable'

const props = withDefaults(
  defineProps<{
    attachment: AttachmentInfo
    projectId: string
    onlyofficeHealth?: OnlyOfficeHealth
    readOnly?: boolean
  }>(),
  {
    onlyofficeHealth: 'unavailable',
    readOnly: false,
  }
)

defineEmits<{
  (e: 'preview'): void
  (e: 'edit'): void
  (e: 'download'): void
  (e: 'cite'): void
}>()

/** 可在线编辑的文件类型 */
const EDITABLE_TYPES = ['docx', 'xlsx', 'pptx', 'doc', 'xls', 'ppt']

const canEdit = computed(() => {
  if (props.readOnly) return false
  if (props.onlyofficeHealth === 'unavailable') return false
  const ext = getFileExtension(props.attachment.file_type || props.attachment.file_name)
  return EDITABLE_TYPES.includes(ext)
})

const healthLabel = computed(() => {
  switch (props.onlyofficeHealth) {
    case 'healthy':
      return '在线编辑可用'
    case 'degraded':
      return '编辑服务降级'
    case 'unavailable':
      return '仅支持预览'
    default:
      return '状态未知'
  }
})

const fileTypeLabel = computed(() => {
  const ext = getFileExtension(props.attachment.file_type || props.attachment.file_name)
  const labels: Record<string, string> = {
    docx: 'Word 文档',
    xlsx: 'Excel 表格',
    pptx: 'PPT 演示',
    pdf: 'PDF 文档',
    doc: 'Word 文档',
    xls: 'Excel 表格',
    ppt: 'PPT 演示',
  }
  return labels[ext] || ext.toUpperCase()
})

function getFileExtension(nameOrType: string): string {
  const parts = nameOrType.split('.')
  return (parts.length > 1 ? parts.pop() : nameOrType)?.toLowerCase() || ''
}
</script>

<style scoped>
.gt-attachment-action-bar {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 16px;
  background: var(--gt-color-primary-bg, #f4f0fa);
  border: 1px solid var(--gt-color-border-purple-light, #d8b8ee);
  border-radius: 6px;
}

.gt-attachment-action-bar__status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #606266;
}

.gt-attachment-action-bar__health-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.gt-attachment-action-bar__health-dot--healthy {
  background: #67c23a;
}

.gt-attachment-action-bar__health-dot--degraded {
  background: #e6a23c;
}

.gt-attachment-action-bar__health-dot--unavailable {
  background: #909399;
}

.gt-attachment-action-bar__health-text {
  font-size: 12px;
}

.gt-attachment-action-bar__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.gt-attachment-action-bar__info {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #909399;
}

.gt-attachment-action-bar__filename {
  font-weight: 500;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
}

.gt-attachment-action-bar__type {
  padding: 1px 6px;
  background: #f0f0f0;
  border-radius: 3px;
}
</style>
