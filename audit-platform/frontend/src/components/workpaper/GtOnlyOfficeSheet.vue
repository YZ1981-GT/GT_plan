<!--
  GtOnlyOfficeSheet.vue — OnlyOffice DocEditor iframe 嵌入组件

  动态加载 OnlyOffice JS API + 创建 DocEditor iframe，用于渲染非 HTML 白名单的
  表格型可编辑底稿（函证检查表、替代程序表、测算表等）。

  锚定 spec d0-onlyoffice-migration Task 2.1
  Validates: Requirements R2, R3, R5, R6
-->
<template>
  <div ref="rootEl" :class="['gt-onlyoffice-sheet', { 'gt-onlyoffice-sheet--fullscreen': isFullscreen }]">
    <!-- 全屏切换按钮 -->
    <div class="gt-onlyoffice-sheet__toolbar">
      <el-button
        size="small"
        :icon="isFullscreen ? 'Close' : 'FullScreen'"
        @click="toggleFullscreen"
      >
        {{ isFullscreen ? '退出全屏' : '全屏编辑' }}
      </el-button>
    </div>
    <div v-if="loading" class="gt-onlyoffice-sheet__loading">
      <el-icon class="gt-onlyoffice-sheet__spinner" :size="24"><Loading /></el-icon>
      <span>加载中...</span>
    </div>
    <div v-else-if="error" class="gt-onlyoffice-sheet__error">
      <el-alert type="warning" :closable="false">
        OnlyOffice 不可用，已降级为只读模式
      </el-alert>
    </div>
    <div ref="editorContainer" :id="containerId" class="gt-onlyoffice-sheet__editor-container" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import http from '@/utils/http'

// ─── Props / Emits ───
const props = withDefaults(defineProps<{
  wpId: string
  sheetName: string
  projectId?: string
  wholeWorkbook?: boolean
  readonly?: boolean
}>(), {
  projectId: '',
  wholeWorkbook: false,
  readonly: false,
})

const emit = defineEmits<{
  'fallback': []
}>()

// ─── State ───
const loading = ref(true)
const error = ref(false)
const rootEl = ref<HTMLElement | null>(null)
const editorContainer = ref<HTMLElement | null>(null)
const isFullscreen = ref(false)
let editorInstance: any = null

function toggleFullscreen(): void {
  if (!isFullscreen.value) {
    // 进入全屏：优先用浏览器原生 Fullscreen API
    const el = rootEl.value
    if (el?.requestFullscreen) {
      el.requestFullscreen().catch(() => { /* fallback to CSS */ })
    } else if ((el as any)?.webkitRequestFullscreen) {
      (el as any).webkitRequestFullscreen()
    }
    isFullscreen.value = true
    document.addEventListener('keydown', handleEscFullscreen)
    document.addEventListener('fullscreenchange', handleFullscreenChange)
  } else {
    // 退出全屏
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {})
    }
    isFullscreen.value = false
    document.removeEventListener('keydown', handleEscFullscreen)
    document.removeEventListener('fullscreenchange', handleFullscreenChange)
  }
}

function handleFullscreenChange(): void {
  // 用户按 ESC 退出浏览器全屏时同步状态
  if (!document.fullscreenElement && isFullscreen.value) {
    isFullscreen.value = false
    document.removeEventListener('fullscreenchange', handleFullscreenChange)
  }
}

function handleEscFullscreen(e: KeyboardEvent): void {
  if (e.key === 'Escape' && isFullscreen.value) {
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {})
    }
    isFullscreen.value = false
    document.removeEventListener('keydown', handleEscFullscreen)
    document.removeEventListener('fullscreenchange', handleFullscreenChange)
  }
}

// 唯一容器 ID（避免多实例冲突）——一次性生成，禁止用 computed+Date.now()
// （computed 每次求值返回不同 ID，导致 DocEditor 找不到容器 → 降级 bug）
const containerId = ref(
  `onlyoffice-editor-${props.sheetName.replace(/[^a-zA-Z0-9_-]/g, '_')}-${Date.now()}-${Math.floor(Math.random() * 100000)}`
)

// ─── OnlyOffice JS API 脚本加载 ───
function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    // 检查是否已加载
    const existing = document.querySelector(`script[src="${src}"]`)
    if (existing) {
      // 已存在的 script 标签，检查 DocsAPI 是否可用
      if ((window as any).DocsAPI) {
        resolve()
        return
      }
      // 等待加载完成
      existing.addEventListener('load', () => resolve())
      existing.addEventListener('error', () => reject(new Error('OnlyOffice script load failed')))
      return
    }

    const script = document.createElement('script')
    script.src = src
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('OnlyOffice script load failed'))
    document.head.appendChild(script)
  })
}

// ─── 初始化流程 ───
async function initialize() {
  loading.value = true
  error.value = false

  try {
    // Step 0: 主动健康预检 — 不健康直接降级，不加载 api.js
    const health = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    const healthData = health.data?.data ?? health.data
    if (!healthData?.healthy) {
      throw new Error('OnlyOffice unhealthy (preflight)')
    }

    // Step 1: 获取 OnlyOffice 配置（project_id 必传，端点经 require_project_access 校验）
    const configUrl = `/api/workpapers/${props.wpId}/sheets/${encodeURIComponent(props.sheetName)}/onlyoffice-config`
    const configParams: Record<string, any> = {}
    if (props.projectId) configParams.project_id = props.projectId
    // 完整Excel 模式：whole_workbook=true，后端不加 actionLink（打开整本显示全部 sheet tab）
    if (props.wholeWorkbook) configParams.whole_workbook = true
    const response = await http.get(configUrl, {
      params: configParams,
      _silent: true,
    } as any)
    const configPayload = response.data?.data ?? response.data
    const { config, token, onlyoffice_url } = configPayload

    // 确定 OnlyOffice 服务 URL（API 响应优先，VITE 环境变量兜底）
    const baseUrl = onlyoffice_url || import.meta.env.VITE_ONLYOFFICE_URL || ''
    if (!baseUrl) {
      throw new Error('OnlyOffice URL not configured')
    }

    // Step 2: 动态加载 OnlyOffice JS API
    const apiScriptUrl = `${baseUrl.replace(/\/$/, '')}/web-apps/apps/api/documents/api.js`
    await loadScript(apiScriptUrl)

    // Step 3: 等待 DOM 就绪后创建 DocEditor
    if (!editorContainer.value) {
      throw new Error('Editor container not found')
    }

    const DocsAPI = (window as any).DocsAPI
    if (!DocsAPI || !DocsAPI.DocEditor) {
      throw new Error('DocsAPI not available after script load')
    }

    // 合并 config + token（仅当 token 非空时才注入——容器 JWT_ENABLED=false 时
    // 传入空/无效 token 会触发 errorCode -20 "文档安全令牌格式不正确"）
    const editorConfig: any = {
      ...config,
      ...(token ? { token } : {}),
    }

    // 只读模式用 type:embedded（更轻、无工具栏）；编辑模式保持 desktop 保留公式/数据 Tab
    if (props.readonly || config?.editorConfig?.mode === 'view') {
      editorConfig.type = 'embedded'
      if (editorConfig.editorConfig) {
        editorConfig.editorConfig.mode = 'view'
      }
    } else {
      editorConfig.type = 'desktop'
    }

    // 确保 iframe 占满容器
    editorConfig.height = '100%'
    editorConfig.width = '100%'

    // 注册 DocEditor 事件回调（捕获 iframe 内部错误，R8）
    editorConfig.events = {
      onError: (e: any) => {
        console.warn('[GtOnlyOfficeSheet] DocEditor onError:', e?.data)
        handleFallback('doceditor-error')
      },
      onWarning: (e: any) => {
        console.warn('[GtOnlyOfficeSheet] DocEditor onWarning:', e?.data)
      },
      onDocumentReady: () => {
        loading.value = false
      },
    }

    // loading 由 onDocumentReady 关闭（不再在 new 之后立即关）
    editorInstance = new DocsAPI.DocEditor(containerId.value, editorConfig)
  } catch (err: any) {
    console.warn('[GtOnlyOfficeSheet] initialization failed:', err?.message || err)
    handleFallback(err?.message)
  }
}

// ─── 降级处理 ───
function handleFallback(reason?: string) {
  loading.value = false
  error.value = true
  console.warn('[GtOnlyOfficeSheet] fallback triggered, reason:', reason)
  emit('fallback')
}

// ─── 生命周期 ───
onMounted(() => {
  initialize()
})

onBeforeUnmount(() => {
  // 清理 editor 实例
  if (editorInstance) {
    try {
      editorInstance.destroyEditor()
    } catch {
      // ignore cleanup errors
    }
    editorInstance = null
  }
  document.removeEventListener('keydown', handleEscFullscreen)
  document.removeEventListener('fullscreenchange', handleFullscreenChange)
})
</script>

<style scoped>
.gt-onlyoffice-sheet {
  width: 100%;
  height: 100%;
  min-height: 500px;
  display: flex;
  flex-direction: column;
  position: relative;
}

/* 全屏模式 */
.gt-onlyoffice-sheet--fullscreen {
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: #fff;
  min-height: 100vh;
  height: 100vh;
  border-radius: 0;
  overflow: hidden;
}

.gt-onlyoffice-sheet__toolbar {
  display: flex;
  justify-content: flex-end;
  padding: 4px 8px;
  background: #f5f7fa;
  border-bottom: 1px solid #ebeef5;
  flex-shrink: 0;
}

.gt-onlyoffice-sheet--fullscreen .gt-onlyoffice-sheet__toolbar {
  padding: 8px 16px;
  background: #fff;
  border-bottom: 1px solid #dcdfe6;
}

.gt-onlyoffice-sheet__loading {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: #fff;
  z-index: 10;
  color: #606266;
  font-size: 14px;
}

.gt-onlyoffice-sheet__spinner {
  animation: gt-oo-spin 1.2s linear infinite;
}

@keyframes gt-oo-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.gt-onlyoffice-sheet__error {
  padding: 16px;
}

.gt-onlyoffice-sheet__editor-container {
  flex: 1;
  width: 100%;
  min-height: 0;
}

.gt-onlyoffice-sheet__editor-container :deep(iframe) {
  width: 100% !important;
  height: 100% !important;
}

.gt-onlyoffice-sheet--fullscreen .gt-onlyoffice-sheet__editor-container {
  height: calc(100vh - 44px);
  min-height: calc(100vh - 44px);
}
</style>
