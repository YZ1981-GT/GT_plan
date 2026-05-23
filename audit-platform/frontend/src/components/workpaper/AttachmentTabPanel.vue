<!--
  AttachmentTabPanel — 底稿右栏「附件」Tab 内容容器 [AT-2 实时预览接入]

  职责：
    - 列出当前底稿关联的附件（process_record.attachments 端点）
    - 行内点击 → AttachmentPreviewDrawer（PDF/图片/Office 转 PDF iframe）
    - 顶部 AttachmentDropZone 包装一层，支持拖拽上传
    - link-created 事件触发后刷新列表

  接入：WorkpaperSidePanel 附件 Tab。
-->
<template>
  <div class="gt-attach-tab">
    <AttachmentDropZone
      :project-id="projectId"
      :wp-id="wpId"
      @link-created="onLinkCreated"
    >
      <div class="gt-attach-tab__hint">
        <el-icon><Paperclip /></el-icon>
        <span>拖拽文件到此处上传，或点击行预览</span>
      </div>

      <div v-if="loading" v-loading="true" class="gt-attach-tab__loading" />
      <div v-else-if="!list.length" class="gt-attach-tab__empty">暂无关联附件</div>
      <ul v-else class="gt-attach-tab__list">
        <li
          v-for="att in list"
          :key="att.id"
          class="gt-attach-tab__item"
          @click="onPreview(att)"
        >
          <span class="gt-attach-tab__icon">{{ iconFor(att.file_name) }}</span>
          <div class="gt-attach-tab__body">
            <div class="gt-attach-tab__name" :title="att.file_name">{{ att.file_name }}</div>
            <div class="gt-attach-tab__meta">
              {{ humanSize(att.file_size) }} · {{ shortTime(att.created_at) }}
            </div>
          </div>
          <el-tag v-if="isOffice(att.file_name)" size="small" type="info" round>Office</el-tag>
        </li>
      </ul>
    </AttachmentDropZone>

    <AttachmentPreviewDrawer v-model="drawerOpen" :attachment="selected" />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Paperclip } from '@element-plus/icons-vue'
import AttachmentDropZone from '@/components/workpaper/AttachmentDropZone.vue'
import AttachmentPreviewDrawer, {
  type AttachmentForPreview,
} from '@/components/common/AttachmentPreviewDrawer.vue'
import { api as httpApi } from '@/services/apiProxy'
import { processRecord as P_pr, attachments as P_att } from '@/services/apiPaths'

interface AttachmentRow {
  id: string
  file_name: string
  file_size: number | null
  file_type: string | null
  created_at: string | null
}

const props = defineProps<{
  projectId: string
  wpId: string
}>()

const list = ref<AttachmentRow[]>([])
const loading = ref(false)
const drawerOpen = ref(false)
const selected = ref<AttachmentForPreview | null>(null)

const OFFICE_EXTS = ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']

function getExt(name: string): string {
  const idx = name.lastIndexOf('.')
  return idx < 0 ? '' : name.slice(idx).toLowerCase()
}

function isOffice(name: string): boolean {
  return OFFICE_EXTS.includes(getExt(name))
}

function iconFor(name: string): string {
  const ext = getExt(name)
  if (ext === '.pdf') return '📄'
  if (['.png', '.jpg', '.jpeg', '.gif'].includes(ext)) return '🖼️'
  if (['.doc', '.docx'].includes(ext)) return '📝'
  if (['.xls', '.xlsx'].includes(ext)) return '📊'
  if (['.ppt', '.pptx'].includes(ext)) return '📽️'
  return '📎'
}

function humanSize(bytes: number | null): string {
  if (!bytes || bytes <= 0) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function shortTime(iso: string | null): string {
  if (!iso) return ''
  return iso.slice(0, 16).replace('T', ' ')
}

async function loadList() {
  if (!props.projectId || !props.wpId) {
    list.value = []
    return
  }
  loading.value = true
  try {
    const data: any = await httpApi.get(P_pr.attachments(props.projectId, props.wpId))
    list.value = Array.isArray(data) ? data : data?.items || []
  } catch {
    list.value = []
  } finally {
    loading.value = false
  }
}

function onPreview(att: AttachmentRow) {
  selected.value = {
    id: att.id,
    name: att.file_name,
    mime_type: att.file_type || '',
    preview_url: P_att.preview(att.id),
    download_url: P_att.download(att.id),
  }
  drawerOpen.value = true
}

function onLinkCreated() {
  loadList()
}

watch(
  () => [props.projectId, props.wpId],
  () => loadList(),
  { immediate: true },
)
</script>

<style scoped>
.gt-attach-tab { display: flex; flex-direction: column; height: 100%; }
.gt-attach-tab__hint {
  display: flex; align-items: center; gap: 6px;
  padding: var(--gt-space-2) var(--gt-space-3);
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
  border-bottom: 1px dashed var(--gt-color-border-light);
}
.gt-attach-tab__loading { min-height: 80px; }
.gt-attach-tab__empty {
  padding: var(--gt-space-6);
  text-align: center;
  color: var(--gt-color-text-tertiary);
  font-size: var(--gt-font-size-sm);
}
.gt-attach-tab__list { list-style: none; margin: 0; padding: 0; }
.gt-attach-tab__item {
  display: flex; align-items: center; gap: var(--gt-space-2);
  padding: var(--gt-space-2) var(--gt-space-3);
  border-bottom: 1px solid var(--gt-color-border-light);
  cursor: pointer;
  transition: background 0.15s;
}
.gt-attach-tab__item:hover { background: var(--gt-color-primary-bg); }
.gt-attach-tab__icon { font-size: 18px; flex-shrink: 0; }
.gt-attach-tab__body { flex: 1; min-width: 0; }
.gt-attach-tab__name {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.gt-attach-tab__meta {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
}
</style>
