<template>
  <el-dialog v-model="visible" :title="title" width="95%" top="2vh" :show-close="false" :close-on-press-escape="false" @close="cleanup" destroy-on-close>
    <!-- 全屏按钮：调用 OnlyOffice 编辑器容器的浏览器原生全屏 -->
    <template #header="{ close, titleId, titleClass }">
      <div class="onlyoffice-editor__header">
        <span :id="titleId" :class="titleClass">{{ title }}</span>
        <div class="onlyoffice-editor__header-actions">
          <el-button
            v-if="!degraded && editorReady"
            size="small"
            text
            @click="toggleFullscreen"
            :title="isFullscreen ? '退出全屏' : '全屏'"
          >
            <template #icon><svg v-if="!isFullscreen" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 1024 1024"><path fill="currentColor" d="M160 96h320v64H198.4l256 256H160V96zm704 832H544v-64h281.6l-256-256H864v320z"/></svg><svg v-else xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 1024 1024"><path fill="currentColor" d="M512 544H192v-64h281.6L217.6 224H160V160h352v384zm0-64h320v64H550.4L806.4 800H864v64H512V480z"/></svg></template>
          </el-button>
          <el-button size="small" text :icon="Close" title="关闭" @click="close" />
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
      <!-- 左侧：编辑器主体（OnlyOffice 会替换内部占位 div，故全屏挂在此稳定容器上） -->
      <div ref="editorMainRef" class="onlyoffice-editor__main">
        <!-- 全屏内退出条：仅在原生全屏时显示，位于 iframe 上方（不被 iframe 遮挡，可点击） -->
        <div class="onlyoffice-editor__fs-bar">
          <el-button size="small" @click="toggleFullscreen">
            <template #icon>
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 1024 1024"><path fill="currentColor" d="M512 544H192v-64h281.6L217.6 224H160V160h352v384zm0-64h320v64H550.4L806.4 800H864v64H512V480z"/></svg>
            </template>
            退出全屏
          </el-button>
        </div>
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
import { Close } from '@element-plus/icons-vue'
import { fetchOnlyOfficeConfig, fetchOnlyOfficeHealth } from '@/services/deliverableApi'
import {
  AUTO_FOLLOW_ENABLED,
  createLineageAutoFollow,
  type LineageAutoFollow,
} from './useLineageAutoFollow'
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
  previewType: 'docx' | 'pdf' | 'xlsx' | 'html' | 'unsupported'
  previewUrl?: string
  showWatermark?: boolean
  /** 出品物当前状态（终态检测） */
  deliverableStatus?: string
}>()

const emit = defineEmits<{ close: [] }>()

const visible = ref(true)
const isFullscreen = ref(false)
const degraded = ref(false)
const editorMainRef = ref<HTMLElement | null>(null)
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
// 真·光标跟随溯源句柄（默认关闭 AUTO_FOLLOW_ENABLED，P0 live 验证通过后开启）
let lineageFollow: LineageAutoFollow | null = null

function cleanup() {
  if (lineageFollow) {
    try { lineageFollow.dispose() } catch { /* ignore */ }
    lineageFollow = null
  }
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

/**
 * 全屏：对 OnlyOffice 编辑器容器调用浏览器原生 Fullscreen API，
 * 让 OnlyOffice 自身铺满整个物理屏幕（而非仅撑满弹窗）。
 */
function toggleFullscreen() {
  const el = editorMainRef.value as (HTMLElement & {
    webkitRequestFullscreen?: () => Promise<void> | void
  }) | null
  if (!el) return
  const doc = document as Document & {
    webkitFullscreenElement?: Element
    webkitExitFullscreen?: () => Promise<void> | void
  }
  const active = doc.fullscreenElement || doc.webkitFullscreenElement
  if (!active) {
    (el.requestFullscreen?.() ?? el.webkitRequestFullscreen?.()) as unknown
  } else {
    (doc.exitFullscreen?.() ?? doc.webkitExitFullscreen?.()) as unknown
  }
}

function onFullscreenChange() {
  const doc = document as Document & { webkitFullscreenElement?: Element }
  isFullscreen.value = !!(doc.fullscreenElement || doc.webkitFullscreenElement)
}

/** 切换溯源面板显示 */
function toggleLineagePanel() {
  showLineagePanel.value = !showLineagePanel.value
  // 打开面板时主动查询当前光标所在章节（自动跟随启用时；需求 4.1），fail-open
  if (showLineagePanel.value && lineageFollow) {
    lineageFollow.queryCurrent()
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
  document.addEventListener('fullscreenchange', onFullscreenChange)
  document.addEventListener('webkitfullscreenchange', onFullscreenChange)
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

    // 真·光标跟随溯源（默认关闭；仅 P0 live 验证通过并开启 AUTO_FOLLOW_ENABLED 时建立连接器）
    // fail-open：连接器不可用不阻断编辑器，手动章节溯源仍可用。
    if (AUTO_FOLLOW_ENABLED) {
      lineageFollow = createLineageAutoFollow(editorInstance, (tag) => {
        lineagePanelRef.value?.onBookmarkDetected(tag)
      })
    }
  } catch (e) {
    console.error('OnlyOffice init failed:', e)
    degraded.value = true
  }
})

onUnmounted(() => {
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  document.removeEventListener('webkitfullscreenchange', onFullscreenChange)
  if (lineageFollow) {
    try { lineageFollow.dispose() } catch { /* ignore */ }
    lineageFollow = null
  }
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
  display: flex;
  flex-direction: column;
}
.onlyoffice-editor__container {
  flex: 1;
  width: 100%;
  min-height: 0;
}
/* 全屏内退出条：非全屏时隐藏（进入全屏用弹窗头部按钮） */
.onlyoffice-editor__fs-bar {
  display: none;
  flex-shrink: 0;
  justify-content: flex-end;
  align-items: center;
  padding: 8px 16px;
  background: #fff;
  border-bottom: 1px solid #dcdfe6;
}
/* 浏览器原生全屏：OnlyOffice 自身铺满整个物理屏幕 */
.onlyoffice-editor__main:fullscreen,
.onlyoffice-editor__main:-webkit-full-screen {
  width: 100vw;
  height: 100vh;
  background: #fff;
}
/* 全屏时显示退出条（位于 iframe 上方，独立元素不被 iframe 指针拦截） */
.onlyoffice-editor__main:fullscreen .onlyoffice-editor__fs-bar,
.onlyoffice-editor__main:-webkit-full-screen .onlyoffice-editor__fs-bar {
  display: flex;
}
/* OnlyOffice 会用 iframe 替换内部占位 div，直接约束 iframe 填满 */
.onlyoffice-editor__main :deep(iframe) {
  width: 100%;
  height: 100%;
  border: 0;
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
