<!--
  OnlyOfficeWordDialog.vue — 简单 OnlyOffice docx 编辑弹窗（word-template 底稿专用）

  Props: documentUrl, documentKey, title, mode, callbackUrl
  Emit: saved, update:visible
-->
<template>
  <el-dialog
    :model-value="visible"
    :title="title"
    width="95%"
    top="2vh"
    :close-on-click-modal="false"
    destroy-on-close
    @update:model-value="emit('update:visible', $event)"
    @close="cleanup"
  >
    <div v-if="editorReady" :id="containerId" class="oo-word-dialog__container" />
    <el-skeleton v-else :rows="8" animated />
    <template #footer>
      <el-button @click="emit('update:visible', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'

const props = defineProps<{
  visible: boolean
  documentUrl: string
  documentKey: string
  title: string
  mode?: 'edit' | 'view'
  callbackUrl?: string
}>()

const emit = defineEmits<{
  'update:visible': [val: boolean]
  saved: []
}>()

const containerId = `oo-word-dlg-${Date.now()}`
const editorReady = ref(false)
let editorInstance: any = null

function cleanup() {
  if (editorInstance) {
    try { editorInstance.destroyEditor() } catch { /* ignore */ }
    editorInstance = null
  }
}

onMounted(async () => {
  const base = (import.meta as any).env?.VITE_ONLYOFFICE_URL || 'http://localhost:8080'
  await loadScript(base)
  editorReady.value = true
  await nextTick()

  const DocsAPI = (window as any).DocsAPI
  if (!DocsAPI) return

  const config: any = {
    document: {
      fileType: 'docx',
      key: props.documentKey,
      title: props.title,
      url: props.documentUrl,
    },
    documentType: 'word',
    editorConfig: {
      mode: props.mode || 'edit',
      callbackUrl: props.callbackUrl || '',
      lang: 'zh',
      customization: { autosave: true, forcesave: true },
    },
    events: {
      onDocumentStateChange(event: any) {
        if (!event?.data) emit('saved')
      },
    },
  }
  editorInstance = new DocsAPI.DocEditor(containerId, config)
})

onUnmounted(cleanup)

function loadScript(baseUrl: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if ((window as any).DocsAPI) { resolve(); return }
    const s = document.createElement('script')
    s.src = `${baseUrl}/web-apps/apps/api/documents/api.js`
    s.onload = () => resolve()
    s.onerror = () => reject(new Error('OnlyOffice API load failed'))
    document.head.appendChild(s)
  })
}
</script>

<style scoped>
.oo-word-dialog__container {
  width: 100%;
  height: 75vh;
}
</style>
