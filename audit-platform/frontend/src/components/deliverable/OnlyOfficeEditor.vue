<template>
  <el-dialog v-model="visible" :title="title" width="90%" top="3vh" @close="cleanup" destroy-on-close>
    <el-alert
      v-if="degraded"
      type="warning"
      :closable="false"
      title="OnlyOffice 不可用"
      description="已降级为只读预览，请下载到本地编辑"
      class="onlyoffice-editor__alert"
    />
    <div v-if="!degraded && editorReady" class="onlyoffice-editor__frame">
      <div :id="editorContainerId" class="onlyoffice-editor__container" />
    </div>
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
      <el-button v-if="previewUrl" type="primary" @click="doDownload">下载</el-button>
      <el-button @click="cleanup">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { fetchOnlyOfficeConfig, fetchOnlyOfficeHealth } from '@/services/deliverableApi'
import { downloadFile } from '@/utils/http'
import DeliverablePreview from './DeliverablePreview.vue'

const props = defineProps<{
  projectId: string
  taskId: string
  versionNo: number
  year: number
  title: string
  previewType: 'docx' | 'pdf' | 'html' | 'unsupported'
  previewUrl?: string
  showWatermark?: boolean
}>()

const emit = defineEmits<{ close: [] }>()

const visible = ref(true)
const degraded = ref(false)
const editorReady = ref(false)
const editorContainerId = `oo-editor-${Date.now()}`

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
.onlyoffice-editor__frame {
  height: 75vh;
}
.onlyoffice-editor__container {
  width: 100%;
  height: 100%;
}
.onlyoffice-editor__fallback {
  min-height: 200px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
</style>
