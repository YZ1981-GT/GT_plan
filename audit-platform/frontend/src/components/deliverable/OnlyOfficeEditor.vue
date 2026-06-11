<template>
  <el-dialog v-model="visible" :title="title" :width="maximized ? '100%' : '95%'" :top="maximized ? '0' : '2vh'" :fullscreen="maximized" @close="cleanup" destroy-on-close>
    <!-- 最大化按钮 -->
    <template #header="{ close, titleId, titleClass }">
      <div class="onlyoffice-editor__header">
        <span :id="titleId" :class="titleClass">{{ title }}</span>
        <div class="onlyoffice-editor__header-actions">
          <el-button size="small" text @click="maximized = !maximized" :title="maximized ? '还原' : '最大化'">
            <template #icon><svg v-if="!maximized" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 1024 1024"><path fill="currentColor" d="M160 96h320v64H198.4l256 256H160V96zm704 832H544v-64h281.6l-256-256H864v320z"/></svg><svg v-else xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 1024 1024"><path fill="currentColor" d="M512 544H192v-64h281.6L217.6 224H160V160h352v384zm0-64h320v64H550.4L806.4 800H864v64H512V480z"/></svg></template>
          </el-button>
          <el-button size="small" text @click="close" title="关闭">✕</el-button>
        </div>
      </div>
    </template>
    <el-alert
      v-if="degraded"
      type="warning"
      :closable="false"
      title="OnlyOffice 不可用"
      description="已降级为只读预览，请下载到本地编辑"
      class="onlyoffice-editor__alert"
    />
    <!-- 正常编辑模式：split layout -->
    <div v-if="!degraded && editorReady" class="onlyoffice-editor__layout">
      <!-- 左侧：编辑器主体 -->
      <div class="onlyoffice-editor__main">
        <div :id="editorContainerId" class="onlyoffice-editor__container" />
      </div>
      <!-- 右侧：溯源面板（可折叠） -->
      <div v-if="showLineagePanel" class="onlyoffice-editor__sidebar">
        <LineagePanel
          ref="lineagePanelRef"
          :project-id="projectId"
          :word-export-task-id="taskId"
          :year="year"
          :deliverable-status="deliverableStatus"
          :has-no-anchors="hasNoAnchors"
        />
        <WritebackResultPanel
          :project-id="projectId"
          :word-export-task-id="taskId"
          :year="year"
          :deliverable-status="deliverableStatus"
          @open-conflict-dialog="onOpenConflictDialog"
          @writeback-complete="onWritebackComplete"
        />
      </div>
    </div>
    <!-- 降级预览 -->
    <div v-else-if="degraded && previewUrl" class="onlyoffice-editor__fallback">
      <DeliverablePreview
        :title="title + '（只读预览）'"
        :preview-type="previewType"
        :url="previewUrl"
        :show-watermark="showWatermark"
        @close="emit('close')"
      />
    </div>
    <div v-else-if="degraded && !previewUrl" class="onlyoffice-editor__fallback">
      <p>OnlyOffice 不可用，请下载文件到本地编辑。</p>
    </div>
    <el-skeleton v-else :rows="8" animated />
    <template #footer>
      <div class="onlyoffice-editor__footer">
        <div class="onlyoffice-editor__footer-left">
          <el-button
            v-if="!degraded && editorReady"
            :type="showLineagePanel ? 'primary' : 'default'"
            plain
            size="small"
            class="onlyoffice-editor__lineage-toggle"
            @click="toggleLineagePanel"
          >
            {{ showLineagePanel ? '隐藏溯源' : '查看溯源' }}
          </el-button>
          <el-button
            v-if="!degraded && editorReady"
            size="small"
            class="onlyoffice-editor__trace-btn"
            @click="onTraceCurrentSection"
          >
            溯源当前章节
          </el-button>
        </div>
        <div class="onlyoffice-editor__footer-right">
          <el-button v-if="previewUrl" type="primary" @click="doDownload">下载</el-button>
          <el-button @click="cleanup">关闭</el-button>
        </div>
      </div>
    </template>

    <!-- 冲突裁决弹窗 -->
    <WritebackConflictDialog
      v-model:visible="conflictDialogVisible"
      :conflicts="currentConflicts"
      :project-id="projectId"
      :word-export-task-id="taskId"
      :year="year"
      @resolved="onConflictResolved"
    />
  </el-dialog>
</template>

<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchOnlyOfficeConfig, fetchOnlyOfficeHealth } from '@/services/deliverableApi'
import { downloadFile } from '@/utils/http'
import DeliverablePreview from './DeliverablePreview.vue'
import LineagePanel from './LineagePanel.vue'
import WritebackResultPanel from './WritebackResultPanel.vue'
import WritebackConflictDialog from './WritebackConflictDialog.vue'
import type { WritebackConflict, WritebackResult } from './WritebackResultPanel.vue'

const props = defineProps<{
  projectId: string
  taskId: string
  versionNo: number
  year: number
  title: string
  previewType: 'docx' | 'pdf' | 'html' | 'unsupported'
  previewUrl?: string
  showWatermark?: boolean
  /** 出品物当前状态（终态检测） */
  deliverableStatus?: string
}>()

const emit = defineEmits<{ close: [] }>()

const visible = ref(true)
const maximized = ref(false)
const degraded = ref(false)
const editorReady = ref(false)
const editorContainerId = `oo-editor-${Date.now()}`

// 溯源面板状态
const showLineagePanel = ref(false)
const lineagePanelRef = ref<InstanceType<typeof LineagePanel> | null>(null)
const hasNoAnchors = ref(false)

// 冲突弹窗状态
const conflictDialogVisible = ref(false)
const currentConflicts = ref<WritebackConflict[]>([])

let editorInstance: any = null

function cleanup() {
  if (editorInstance) {
    try { editorInstance.destroyEditor() } catch { /* ignore */ }
    editorInstance = null
  }
  visible.value = false
  emit('close')
}

function doDownload() {
  if (props.previewUrl) {
    downloadFile(props.previewUrl, { fileName: props.title || 'deliverable' })
  }
}

/** 切换溯源面板显示 */
function toggleLineagePanel() {
  showLineagePanel.value = !showLineagePanel.value
}

/**
 * "溯源当前章节"按钮：
 * 尝试通过 OnlyOffice JS API 获取书签信息。
 * 若 API 不支持细粒度书签检测，则显示全文档概览。
 */
async function onTraceCurrentSection() {
  if (!showLineagePanel.value) {
    showLineagePanel.value = true
    await nextTick()
  }

  if (!editorInstance) {
    lineagePanelRef.value?.setNoAnchors()
    return
  }

  // 尝试 OnlyOffice Plugin/Macro API 获取当前书签
  try {
    editorInstance.executeMethod('GetAllBookmarks', [], (bookmarks: any) => {
      if (!bookmarks || (Array.isArray(bookmarks) && bookmarks.length === 0)) {
        hasNoAnchors.value = true
        lineagePanelRef.value?.setNoAnchors()
        return
      }

      hasNoAnchors.value = false

      // 筛选 sec_ 前缀书签
      const secBookmarks = Array.isArray(bookmarks)
        ? bookmarks.filter((bm: any) => {
            const name = typeof bm === 'string' ? bm : bm?.Name || bm?.name || ''
            return name.startsWith('sec_')
          })
        : []

      if (secBookmarks.length === 0) {
        hasNoAnchors.value = true
        lineagePanelRef.value?.setNoAnchors()
        return
      }

      // 取第一个 sec_ 书签作为当前章节（简化 MVP）
      const firstAnchor = typeof secBookmarks[0] === 'string'
        ? secBookmarks[0]
        : secBookmarks[0]?.Name || secBookmarks[0]?.name || ''

      if (firstAnchor) {
        lineagePanelRef.value?.onBookmarkDetected(firstAnchor)
      }
    })
  } catch {
    ElMessage.info('暂无法检测当前章节，请查看全文档溯源状态')
  }
}

/** 冲突弹窗打开 */
function onOpenConflictDialog(conflicts: WritebackConflict[]) {
  currentConflicts.value = conflicts
  conflictDialogVisible.value = true
}

/** 冲突裁决完成 */
function onConflictResolved(_resolutions: Record<string, string>) {
  conflictDialogVisible.value = false
  lineagePanelRef.value?.refresh()
}

/** 回填完成回调 */
function onWritebackComplete(_result: WritebackResult) {
  lineagePanelRef.value?.refresh()
}

onMounted(async () => {
  try {
    const health = await fetchOnlyOfficeHealth(props.projectId)
    if (!health.enabled || !health.available) {
      degraded.value = true
      return
    }

    const cfg = await fetchOnlyOfficeConfig(
      props.projectId,
      props.taskId,
      props.versionNo,
      props.year,
    )

    // 加载 OnlyOffice JS API
    const base = import.meta.env.VITE_ONLYOFFICE_URL || 'http://localhost:8080'
    await loadOnlyOfficeScript(base)

    editorReady.value = true
    await nextTick()

    // 使用 JS API 初始化编辑器
    const config = cfg.config as any
    if (cfg.token) {
      config.token = cfg.token
    }

    const DocsAPI = (window as any).DocsAPI
    if (!DocsAPI) {
      console.error('DocsAPI not loaded')
      degraded.value = true
      return
    }

    editorInstance = new DocsAPI.DocEditor(editorContainerId, config)
  } catch (e) {
    console.error('OnlyOffice init failed:', e)
    degraded.value = true
  }
})

onUnmounted(() => {
  if (editorInstance) {
    try { editorInstance.destroyEditor() } catch { /* ignore */ }
    editorInstance = null
  }
})

/** 动态加载 OnlyOffice api.js（仅首次） */
function loadOnlyOfficeScript(baseUrl: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if ((window as any).DocsAPI) {
      resolve()
      return
    }
    const script = document.createElement('script')
    script.src = `${baseUrl}/web-apps/apps/api/documents/api.js`
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Failed to load OnlyOffice API script'))
    document.head.appendChild(script)
  })
}
</script>

<style scoped>
.onlyoffice-editor__alert {
  margin-bottom: 12px;
}
.onlyoffice-editor__layout {
  display: flex;
  height: 78vh;
  gap: 0;
}
.onlyoffice-editor__main {
  flex: 1;
  min-width: 0;
  height: 100%;
}
.onlyoffice-editor__container {
  width: 100%;
  height: 100%;
}
.onlyoffice-editor__sidebar {
  width: 320px;
  flex-shrink: 0;
  border-left: 1px solid var(--gt-color-border-purple-light, #d8b8ee);
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
  padding: 0 0 12px;
}
.onlyoffice-editor__fallback {
  min-height: 200px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.onlyoffice-editor__footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}
.onlyoffice-editor__footer-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.onlyoffice-editor__footer-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.onlyoffice-editor__lineage-toggle {
  --el-button-text-color: var(--gt-color-primary, #4b2d77);
  --el-button-border-color: var(--gt-color-border-purple-light, #d8b8ee);
}
.onlyoffice-editor__lineage-toggle.el-button--primary {
  --el-button-text-color: #fff;
  --el-button-bg-color: var(--gt-color-primary, #4b2d77);
  --el-button-border-color: var(--gt-color-primary, #4b2d77);
}
.onlyoffice-editor__trace-btn {
  --el-button-text-color: var(--gt-color-primary, #4b2d77);
  --el-button-border-color: var(--gt-color-border-purple-light, #d8b8ee);
}
.onlyoffice-editor__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.onlyoffice-editor__header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
