<!--
  WorkpaperWordEditor.vue — Word 模板底稿编辑器（A16 声明书等）

  通过 OnlyOffice 打开 docx 模板编辑，降级时提供下载/上传链路。
  嵌入到底稿渲染器（htmlRendererRegistry componentType='word-template'）。
-->
<template>
  <div class="gt-wp-word-editor">
    <!-- 操作栏 -->
    <div class="gt-wp-word-editor__toolbar">
      <el-button type="primary" size="small" @click="openEditor" :loading="loading">
        {{ onlyofficeAvailable ? '📝 在线编辑' : '📝 编辑（降级）' }}
      </el-button>
      <el-button size="small" @click="downloadTemplate">⬇️ 下载模板</el-button>
      <el-button v-if="!onlyofficeAvailable" size="small" @click="showUpload = true">⬆️ 上传编辑后文件</el-button>
      <el-tag v-if="signStatus" :type="signStatusType" size="small" style="margin-left: 12px">
        {{ signStatusLabel }}
      </el-tag>
    </div>

    <!-- OnlyOffice 编辑弹窗 -->
    <OnlyOfficeEditor
      v-if="editorVisible"
      v-model:visible="editorVisible"
      :document-url="documentUrl"
      :document-key="documentKey"
      :title="title"
      :mode="readonly ? 'view' : 'edit'"
      @saved="onSaved"
    />

    <!-- 降级提示 -->
    <div v-if="!onlyofficeAvailable" class="gt-wp-word-editor__degraded">
      <el-alert type="info" :closable="false" show-icon>
        OnlyOffice 不可用，请下载模板到本地编辑后上传。
      </el-alert>
    </div>

    <!-- 文件信息 -->
    <div class="gt-wp-word-editor__info">
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="模板文件">{{ fileName || '—' }}</el-descriptions-item>
        <el-descriptions-item label="签回状态">{{ signStatusLabel }}</el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- 上传弹窗 -->
    <el-dialog v-model="showUpload" title="上传编辑后文件" width="480px">
      <el-upload
        :action="`/api/workpapers/${wpId}/upload-offline`"
        :headers="uploadHeaders"
        :on-success="onUploadSuccess"
        accept=".docx,.doc"
        :limit="1"
        drag
      >
        <div style="padding: 20px; text-align: center">
          <p>拖拽或点击上传编辑完成的声明书文件（.docx）</p>
        </div>
      </el-upload>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import OnlyOfficeEditor from '@/components/deliverable/OnlyOfficeEditor.vue'

const props = defineProps<{
  wpId: string
  sheetName?: string
  htmlData?: any
  schema?: any
  readonly?: boolean
}>()

const route = useRoute()
const projectId = computed(() => (route.params.projectId as string) || '')

const loading = ref(false)
const editorVisible = ref(false)
const showUpload = ref(false)
const onlyofficeAvailable = ref(false)
const documentUrl = ref('')
const documentKey = ref('')
const title = ref('管理层声明书')
const fileName = ref('')
const signStatus = ref<string | null>(null) // 'pending'/'sent'/'signed'

const signStatusType = computed(() => {
  if (signStatus.value === 'signed') return 'success'
  if (signStatus.value === 'sent') return 'warning'
  return 'info'
})

const signStatusLabel = computed(() => {
  const m: Record<string, string> = { pending: '待发送', sent: '已发送', signed: '已签回' }
  return m[signStatus.value || ''] || '待编辑'
})

const uploadHeaders = computed(() => {
  const token = sessionStorage.getItem('token') || ''
  return { Authorization: `Bearer ${token}` }
})

async function checkHealth() {
  try {
    const r = await api.get<{ available: boolean }>('/api/deliverables/onlyoffice/health')
    onlyofficeAvailable.value = r?.available ?? false
  } catch {
    onlyofficeAvailable.value = false
  }
}

async function loadDocInfo() {
  try {
    const info = await api.get<any>(`/api/workpapers/${props.wpId}/file-info`)
    fileName.value = info?.file_name || info?.file_path || '声明书模板.docx'
    signStatus.value = info?.sign_status || null
  } catch { /* ignore */ }
}

async function openEditor() {
  if (!onlyofficeAvailable.value) {
    ElMessage.info('OnlyOffice 不可用，请使用下载编辑方式')
    return
  }
  loading.value = true
  try {
    const config = await api.get<any>(`/api/workpapers/${props.wpId}/onlyoffice-config`)
    documentUrl.value = config.document_url || ''
    documentKey.value = config.document_key || `wp-${props.wpId}-${Date.now()}`
    title.value = config.title || fileName.value || '声明书'
    editorVisible.value = true
  } catch (e: any) {
    ElMessage.error('打开编辑器失败：' + (e?.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

async function downloadTemplate() {
  try {
    const token = sessionStorage.getItem('token') || ''
    const r = await fetch(`/api/workpapers/${props.wpId}/download`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!r.ok) throw new Error('下载失败')
    const blob = await r.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = fileName.value || '声明书模板.docx'
    a.click()
    URL.revokeObjectURL(url)
  } catch (e: any) {
    ElMessage.error(e?.message || '下载失败')
  }
}

function onSaved() {
  ElMessage.success('文件已保存')
  loadDocInfo()
}

function onUploadSuccess() {
  showUpload.value = false
  ElMessage.success('上传成功')
  loadDocInfo()
}

onMounted(() => {
  checkHealth()
  loadDocInfo()
})
</script>

<style scoped>
.gt-wp-word-editor {
  padding: 16px;
}
.gt-wp-word-editor__toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}
.gt-wp-word-editor__degraded {
  margin-bottom: 12px;
}
.gt-wp-word-editor__info {
  margin-top: 16px;
}
</style>
