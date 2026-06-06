<template>
  <el-dialog v-model="visible" :title="title" width="90%" top="3vh" @close="emit('close')">
    <el-alert
      v-if="degraded"
      type="warning"
      :closable="false"
      title="OnlyOffice 不可用"
      description="已降级为只读预览，请下载到本地编辑"
      class="onlyoffice-editor__alert"
    />
    <div v-if="!degraded && editorUrl" class="onlyoffice-editor__frame">
      <iframe :src="editorUrl" class="onlyoffice-editor__iframe" title="OnlyOffice Editor" />
    </div>
    <div v-else-if="degraded && previewUrl" class="onlyoffice-editor__fallback">
      <p>请使用下方链接下载文件到本地编辑。</p>
      <el-button type="primary" :href="previewUrl" target="_blank">下载文件</el-button>
    </div>
    <el-skeleton v-else :rows="8" animated />
  </el-dialog>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchOnlyOfficeConfig, fetchOnlyOfficeHealth } from '@/services/deliverableApi'

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
const editorUrl = ref('')

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
    const base = import.meta.env.VITE_ONLYOFFICE_URL || 'http://localhost:8080'
    const token = encodeURIComponent(cfg.token)
    editorUrl.value = `${base}/web-apps/apps/${cfg.documentType === 'cell' ? 'spreadsheet' : 'document'}editor/main/index.html?config=${token}`
  } catch {
    degraded.value = true
  }
})
</script>

<style scoped>
.onlyoffice-editor__alert {
  margin-bottom: 12px;
}
.onlyoffice-editor__frame {
  height: 75vh;
}
.onlyoffice-editor__iframe {
  width: 100%;
  height: 100%;
  border: none;
}
</style>
