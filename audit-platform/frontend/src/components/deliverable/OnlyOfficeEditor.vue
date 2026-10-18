<template>
  <el-dialog v-model="visible" :title="displayTitle" width="95%" top="2vh" :show-close="false" :close-on-press-escape="false" @close="cleanup" destroy-on-close>
    <!-- 全屏按钮：调用 OnlyOffice 编辑器容器的浏览器原生全屏 -->
    <template #header="{ close, titleId, titleClass }">
      <div class="onlyoffice-editor__header">
        <span :id="titleId" :class="titleClass" class="onlyoffice-editor__title">{{ displayTitle }}</span>
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
          :supports-section-refresh="supportsSectionRefresh"
          :supports-lineage="supportsLineage"
          :editor-has-unsaved-edits="sessionModified"
          @refreshed="onDeliverableRefreshed"
        />
        <!--
          回填面板按后端能力标志门控（需求 6.1）：
          xlsx 财务报表 / 报告正文（Wave 3 前）不支持回填 → 不渲染面板，
          避免「点了提示成功但 DB 没变」的假成功。
        -->
        <WritebackResultPanel
          v-if="supportsWriteback"
          :project-id="projectId"
          :word-export-task-id="taskId"
          :year="year"
          :deliverable-status="deliverableStatus"
          @open-conflict-dialog="onOpenConflictDialog"
          @writeback-complete="onWritebackComplete"
        />
        <el-alert
          v-else
          type="info"
          :closable="false"
          show-icon
          class="onlyoffice-editor__no-writeback"
          :title="writebackUnsupportedTitle"
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
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { Close } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import {
  deliverableDownloadUrl,
  fetchOnlyOfficeConfig,
  fetchOnlyOfficeHealth,
  fetchSectionStates,
} from '@/services/deliverableApi'
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
  /** 交付件类型（doc_type），用于入口门控展示 */
  docType?: string
  /**
   * 能力标志（需求 6.1/6.2）：由后端 `deliverable_capabilities` 单一真源下发。
   * 前端只消费不判断 —— 禁止在此写 doc_type 白名单。
   * 缺省 false：xlsx 报表等不支持回填的类型不再出现「回填到附注模块」按钮。
   */
  supportsWriteback?: boolean
  supportsSectionRefresh?: boolean
  /**
   * 溯源能力（US-8）：财务报表恒 false。false 时溯源面板不请求 /section-states，
   * 改显「报表按行取数、去报表页穿透」说明，避免空下拉 + 「请重新生成」误导。
   */
  supportsLineage?: boolean
}>()

const emit = defineEmits<{
  close: []
  /** 章节刷新落了新版本（交付中心据此重取列表：否则再次打开编辑的是旧版本，保存会盖掉刷新结果） */
  'version-changed': [versionNo: number]
}>()

/** 编辑器当前打开的版本（章节刷新后切到新版本，不再等于 props.versionNo） */
const currentVersionNo = ref(props.versionNo)
/** 标题是打开时那一版的文件名；刷新切到新版本后注明，免得标题与内容版本对不上 */
const displayTitle = computed(() =>
  currentVersionNo.value === props.versionNo
    ? props.title
    : `${props.title}（已切换到第 ${currentVersionNo.value} 版）`,
)
/**
 * 本次编辑会话是否已有修改（OnlyOffice onDocumentStateChange data=true）。修改要等关闭编辑器后才回存为新版本 ⇒
 * 有修改时溯源面板拒绝章节刷新（否则刷新以修改前的版本为底，之后回存的版本又会盖掉刷新结果）。
 */
const sessionModified = ref(false)

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

/**
 * 不支持回填时的说明文案（需求 6.3）：必须说明**为什么**不支持 + 正确做法，
 * 不能只把按钮藏掉让审计师以为功能坏了。财务报表是派生结果，改数字必须走
 * 调整分录（AJE/RJE），否则等于绕过审计逻辑。
 */
const writebackUnsupportedTitle = computed(() => {
  const dt = props.docType || ''
  if (dt.startsWith('financial_report')) {
    return '财务报表数字来源于试算表与调整分录，不支持从出品物回填；如需修改金额请回底稿录入 AJE/RJE 后重新生成报表。'
  }
  if (dt === 'disclosure_notes') {
    // 附注回填已下线（方向裁定）：附注是底稿单项推送的只读下游，交付中心不回写附注。
    return '附注内容来源于底稿披露表的推送（底稿 → 附注），交付中心不支持回填。请回对应底稿修改并点「同步到附注」，再从交付中心重新导出附注。'
  }
  return '该类型交付件不支持回填到上游模块，编辑结果仅保存为交付件新版本。'
})

let editorInstance: any = null
// 真·光标跟随溯源句柄（默认关闭 AUTO_FOLLOW_ENABLED，P0 live 验证通过后开启）
let lineageFollow: LineageAutoFollow | null = null

/** 销毁当前 DocEditor（destroyEditor 会把占位 div 原样放回，同一容器 id 可再建编辑器） */
function disposeEditor() {
  if (lineageFollow) {
    try { lineageFollow.dispose() } catch { /* ignore */ }
    lineageFollow = null
  }
  if (editorInstance) {
    try { editorInstance.destroyEditor() } catch { /* ignore */ }
    editorInstance = null
  }
}

function cleanup() {
  disposeEditor()
  visible.value = false
  emit('close')
}

function doDownload() {
  // 刷新切到新版本后下载新版本（previewUrl 是打开时那一版）；文件名同后端刷新落盘口径 {doc_type}_v{版本号}
  const switched = currentVersionNo.value !== props.versionNo
  const url = switched
    ? deliverableDownloadUrl(props.projectId, props.taskId, currentVersionNo.value)
    : props.previewUrl
  const ext = (props.title || '').match(/\.[a-z0-9]+$/i)?.[0] || '.docx'
  const fileName = switched && props.docType
    ? `${props.docType}_v${currentVersionNo.value}${ext}`
    : props.title || 'deliverable'
  if (url) {
    downloadFile(url, { fileName })
  }
}

/** 取某一版本的编辑器配置（JWT token 并入 config） */
async function fetchEditorConfig(versionNo: number): Promise<Record<string, any>> {
  const cfg = await fetchOnlyOfficeConfig(props.projectId, props.taskId, versionNo, props.year)
  const config = { ...(cfg.config as Record<string, any>) }
  if (cfg.token) {
    config.token = cfg.token
  }
  return config
}

/** 在容器里建 DocEditor（先销毁旧的）；记录会话内是否有修改 */
function mountDocEditor(config: Record<string, any>, versionNo: number): void {
  const DocsAPI = (window as any).DocsAPI
  if (!DocsAPI) throw new Error('DocsAPI 未加载')
  disposeEditor()
  currentVersionNo.value = versionNo
  sessionModified.value = false
  let documentReady = false
  const events = { ...(config.events || {}) }
  // 文档载入完成前的状态变化不算用户修改
  events.onDocumentReady = () => { documentReady = true }
  events.onDocumentStateChange = (evt: { data?: boolean }) => {
    if (documentReady && evt?.data === true) sessionModified.value = true
  }
  editorInstance = new DocsAPI.DocEditor(editorContainerId, { ...config, events })

  // 真·光标跟随溯源（默认关闭；仅 P0 live 验证通过并开启 AUTO_FOLLOW_ENABLED 时建立连接器）
  // fail-open：连接器不可用不阻断编辑器，手动章节溯源仍可用。
  if (AUTO_FOLLOW_ENABLED) {
    lineageFollow = createLineageAutoFollow(editorInstance, (tag) => {
      lineagePanelRef.value?.onBookmarkDetected(tag)
    })
  }
}

/**
 * 溯源面板刷新章节落了新版本 ⇒ 编辑器切到新版本（否则用户看不到刷新结果，接着编辑保存会盖掉它）。
 * 先取新版本配置再销毁旧编辑器：取不到时旧编辑器保留并提示重新打开。
 */
async function onDeliverableRefreshed(versionNo: number): Promise<void> {
  emit('version-changed', versionNo)
  try {
    mountDocEditor(await fetchEditorConfig(versionNo), versionNo)
  } catch (e) {
    console.error('OnlyOffice reload failed:', e)
    ElMessage.warning(`已另存为第 ${versionNo} 版，但编辑器未能切换到新版本，请关闭后从交付中心重新打开`)
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

/**
 * 探测本交付件有无章节锚点（需求 6.5）。
 *
 * 🔴 `hasNoAnchors` 曾只声明 `ref(false)` 从不赋值 → LineagePanel 的「无锚点」
 * 提示分支永不触发（旧版本交付件用户看到的是空白章节下拉，没有任何解释）。
 * 判据 = `/section-states` 返回的 sections 为空数组（该端点在 Task 4 接线后
 * 对新生成交付件必非空）。fail-open：查询异常时保持 false（不误报无锚点）。
 */
async function probeAnchors(): Promise<void> {
  try {
    // 端点返回 { sections: [...] }：原实现直接取 .length（对象上恒 undefined）⇒ 无锚点提示从未出现（类型检查才暴露）
    const states = (await fetchSectionStates(props.projectId, props.taskId))?.sections ?? []
    hasNoAnchors.value = states.length === 0
  } catch {
    hasNoAnchors.value = false
  }
}

onMounted(async () => {
  document.addEventListener('fullscreenchange', onFullscreenChange)
  document.addEventListener('webkitfullscreenchange', onFullscreenChange)
  void probeAnchors()
  try {
    const health = await fetchOnlyOfficeHealth(props.projectId)
    if (!health.enabled || !health.available) {
      degraded.value = true
      return
    }

    const config = await fetchEditorConfig(props.versionNo)

    // 加载 OnlyOffice JS API
    const base = import.meta.env.VITE_ONLYOFFICE_URL || 'http://localhost:8080'
    await loadOnlyOfficeScript(base)

    editorReady.value = true
    await nextTick()

    if (!(window as any).DocsAPI) {
      console.error('DocsAPI not loaded')
      degraded.value = true
      return
    }
    // 使用 JS API 初始化编辑器
    mountDocEditor(config, props.versionNo)
  } catch (e) {
    console.error('OnlyOffice init failed:', e)
    degraded.value = true
  }
})

onUnmounted(() => {
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  document.removeEventListener('webkitfullscreenchange', onFullscreenChange)
  disposeEditor()
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
