<!--
  WorkpaperWordEditor.vue — Word 模板底稿编辑器（A16 声明书等）

  功能：
  1. 版本智能推荐（按 business_category + project_type 高亮推荐模板版本）
  2. 占位符自动替换（客户名/审计期间/未更正错报摘要 预填）
  3. 签发状态追踪（待编辑→待发送→已发送→已签回）
  4. A13 联动（未更正错报段落自动引用）
  5. OnlyOffice 在线编辑 + 降级下载上传
-->
<template>
  <div class="gt-wp-word-editor">
    <!-- 1. 版本选择器（智能推荐） -->
    <div class="gt-wp-word-editor__version-select">
      <span class="gt-wp-word-editor__label">声明书版本：</span>
      <el-radio-group v-model="selectedVersion" size="small" @change="onVersionChange">
        <el-radio-button
          v-for="v in templateVersions"
          :key="v.code"
          :value="v.code"
          :class="{ 'is-recommended': v.recommended }"
        >
          {{ v.label }}
          <el-tag v-if="v.recommended" type="success" size="small" effect="plain" style="margin-left: 4px">推荐</el-tag>
        </el-radio-button>
      </el-radio-group>
    </div>

    <!-- 操作栏 -->
    <div class="gt-wp-word-editor__toolbar">
      <el-button type="primary" size="small" @click="openEditor" :loading="loading">
        {{ onlyofficeAvailable ? '📝 在线编辑' : '📝 编辑（降级）' }}
      </el-button>
      <el-button size="small" @click="downloadTemplate">⬇️ 下载模板</el-button>
      <el-button v-if="!onlyofficeAvailable" size="small" @click="showUpload = true">⬆️ 上传编辑后文件</el-button>
      <el-divider direction="vertical" />
      <!-- 3. 签发状态按钮组 -->
      <el-button-group>
        <el-button size="small" :type="signStatus === 'sent' ? 'warning' : 'default'" @click="updateSignStatus('sent')" :disabled="signStatus === 'signed'">
          📤 标记已发送
        </el-button>
        <el-button size="small" :type="signStatus === 'signed' ? 'success' : 'default'" @click="updateSignStatus('signed')">
          ✅ 标记已签回
        </el-button>
      </el-button-group>
      <el-tag :type="signStatusType" size="small" style="margin-left: 8px">{{ signStatusLabel }}</el-tag>
    </div>

    <!-- 4. A13 未更正错报联动提示 -->
    <el-alert
      v-if="misstatementSummary"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 12px"
    >
      <template #title>声明书"未更正错报"段落内容（自动引用 A13）</template>
      <p style="margin: 4px 0 0; font-size: 12px; white-space: pre-wrap">{{ misstatementSummary }}</p>
    </el-alert>
    <el-alert
      v-else-if="misstatementLoaded"
      type="success"
      :closable="false"
      show-icon
      style="margin-bottom: 12px"
      title="无未更正错报，声明书中"未更正错报"段落可填写"无""
    />

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

    <!-- 文件信息 + 占位符预填预览 -->
    <div class="gt-wp-word-editor__info">
      <el-descriptions :column="2" border size="small" title="编制信息（自动预填占位符）">
        <el-descriptions-item label="客户名称">{{ placeholders.client_name || '—' }}</el-descriptions-item>
        <el-descriptions-item label="审计期间">{{ placeholders.audit_period || '—' }}</el-descriptions-item>
        <el-descriptions-item label="签字合伙人">{{ placeholders.partner_name || '—' }}</el-descriptions-item>
        <el-descriptions-item label="选用版本">{{ selectedVersionLabel }}</el-descriptions-item>
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

// ─── State ───
const loading = ref(false)
const editorVisible = ref(false)
const showUpload = ref(false)
const onlyofficeAvailable = ref(false)
const documentUrl = ref('')
const documentKey = ref('')
const title = ref('管理层声明书')
const signStatus = ref<string>('pending')
const misstatementSummary = ref('')
const misstatementLoaded = ref(false)
const selectedVersion = ref('A16-1')

// 2. 占位符数据（从项目信息预填）
const placeholders = ref<Record<string, string>>({
  client_name: '',
  audit_period: '',
  partner_name: '',
  uncorrected_misstatements: '',
})

// 1. 版本列表（按 business_category 推荐）
interface TemplateVersion { code: string; label: string; recommended: boolean; forCategory: string[] }
const templateVersions = ref<TemplateVersion[]>([
  { code: 'A16-1', label: '一般财报', recommended: false, forCategory: ['C', 'B'] },
  { code: 'A16-2', label: '整合审计', recommended: false, forCategory: ['A', 'B'] },
  { code: 'A16-3', label: 'IPO申报', recommended: false, forCategory: ['A'] },
  { code: 'A16-4', label: 'IPO季度', recommended: false, forCategory: ['A'] },
  { code: 'A16-5', label: '新三板', recommended: false, forCategory: ['B'] },
  { code: 'A16-6', label: '企业债', recommended: false, forCategory: ['B'] },
  { code: 'A16-7', label: '关联交易', recommended: false, forCategory: ['A', 'B', 'C'] },
])

const selectedVersionLabel = computed(() =>
  templateVersions.value.find(v => v.code === selectedVersion.value)?.label || selectedVersion.value
)

const signStatusType = computed(() => {
  if (signStatus.value === 'signed') return 'success'
  if (signStatus.value === 'sent') return 'warning'
  return 'info'
})

const signStatusLabel = computed(() => {
  const m: Record<string, string> = { pending: '待编辑', sent: '已发送', signed: '已签回' }
  return m[signStatus.value] || '待编辑'
})

const uploadHeaders = computed(() => {
  const token = sessionStorage.getItem('token') || ''
  return { Authorization: `Bearer ${token}` }
})

// ─── Methods ───
async function loadProjectInfo() {
  try {
    const info = await api.get<any>(`/api/projects/${projectId.value}`)
    const d = info?.data || info
    placeholders.value.client_name = d?.client_name || d?.name || ''
    placeholders.value.audit_period = d?.audit_period_end ? `${d.audit_year || ''}年度` : ''
    placeholders.value.partner_name = d?.partner_name || ''

    // 根据 business_category 推荐版本
    const cat = (d?.business_category || 'C').charAt(0).toUpperCase()
    for (const v of templateVersions.value) {
      v.recommended = v.forCategory.includes(cat)
    }
    // 自动选中第一个推荐版本
    const rec = templateVersions.value.find(v => v.recommended)
    if (rec) selectedVersion.value = rec.code
  } catch { /* ignore */ }
}

async function loadMisstatementSummary() {
  try {
    const year = parseInt(route.query.year as string) || new Date().getFullYear()
    const r = await api.get<any>(
      `/api/projects/${projectId.value}/misstatements/for-letter`,
      { params: { year } },
    )
    const text = r?.summary || r?.data?.summary || ''
    misstatementSummary.value = (text === '无未更正错报。') ? '' : text
    misstatementLoaded.value = true
    placeholders.value.uncorrected_misstatements = misstatementSummary.value || '无'
  } catch {
    misstatementLoaded.value = true
  }
}

async function checkHealth() {
  try {
    const r = await api.get<{ available: boolean }>('/api/deliverables/onlyoffice/health')
    onlyofficeAvailable.value = r?.available ?? false
  } catch {
    onlyofficeAvailable.value = false
  }
}

async function loadSignStatus() {
  try {
    const info = await api.get<any>(`/api/workpapers/${props.wpId}/file-info`)
    signStatus.value = info?.sign_status || 'pending'
  } catch { /* ignore */ }
}

async function updateSignStatus(status: string) {
  try {
    await api.post(`/api/workpapers/${props.wpId}/sign-status`, { status })
    signStatus.value = status
    ElMessage.success(status === 'signed' ? '已标记签回' : '已标记发送')
  } catch {
    // 端点可能不存在，降级到 field-override 存储
    try {
      await api.post('/api/workpapers/field-overrides', {
        project_id: projectId.value,
        year: new Date().getFullYear(),
        scope: 'word_template:A16',
        item_key: 'sign_status',
        field: 'value',
        value: status,
      })
      signStatus.value = status
      ElMessage.success(status === 'signed' ? '已标记签回' : '已标记发送')
    } catch (e: any) {
      ElMessage.error('更新状态失败')
    }
  }
}

function onVersionChange(code: string) {
  selectedVersion.value = code
  title.value = `管理层声明书 (${selectedVersionLabel.value})`
}

async function openEditor() {
  if (!onlyofficeAvailable.value) {
    ElMessage.info('OnlyOffice 不可用，请使用下载编辑方式')
    return
  }
  loading.value = true
  try {
    const config = await api.get<any>(`/api/workpapers/${props.wpId}/onlyoffice-config`, {
      params: { version: selectedVersion.value },
    })
    documentUrl.value = config.document_url || ''
    documentKey.value = config.document_key || `wp-${props.wpId}-${Date.now()}`
    title.value = config.title || `声明书 (${selectedVersionLabel.value})`
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
    const r = await fetch(
      `/api/workpapers/${props.wpId}/download?version=${selectedVersion.value}`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    if (!r.ok) throw new Error('下载失败')
    const blob = await r.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${selectedVersion.value} 管理层声明书.docx`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e: any) {
    ElMessage.error(e?.message || '下载失败')
  }
}

function onSaved() {
  ElMessage.success('文件已保存')
  loadSignStatus()
}

function onUploadSuccess() {
  showUpload.value = false
  ElMessage.success('上传成功')
  loadSignStatus()
}

onMounted(() => {
  checkHealth()
  loadProjectInfo()
  loadMisstatementSummary()
  loadSignStatus()
})
</script>

<style scoped>
.gt-wp-word-editor {
  padding: 16px;
}
.gt-wp-word-editor__version-select {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.gt-wp-word-editor__label {
  font-size: 13px;
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
  white-space: nowrap;
}
/* 推荐版本高亮 */
.gt-wp-word-editor__version-select :deep(.is-recommended .el-radio-button__inner) {
  border-color: var(--gt-color-primary, #4b2d77);
  color: var(--gt-color-primary, #4b2d77);
}
.gt-wp-word-editor__toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.gt-wp-word-editor__degraded {
  margin-bottom: 12px;
}
.gt-wp-word-editor__info {
  margin-top: 16px;
}
</style>
