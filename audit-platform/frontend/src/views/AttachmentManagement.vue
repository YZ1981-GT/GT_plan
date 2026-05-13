<template>
  <div class="gt-attachment-page">
    <div class="gt-att-header">
      <GtPageHeader title="附件管理" :show-back="false">
        <template #actions>
          <el-input v-model="searchQuery" placeholder="搜索附件..." size="small" clearable
            :prefix-icon="Search" style="width: 200px" @keyup.enter="onSearch" />
          <el-select v-model="filterType" placeholder="文件类型" size="small" clearable style="width: 120px" @change="loadAttachments">
            <el-option label="PDF" value="pdf" />
            <el-option label="Word" value="word" />
            <el-option label="Excel" value="excel" />
            <el-option label="图片" value="image" />
          </el-select>
          <el-upload
            :show-file-list="false"
            :before-upload="beforeUpload"
            :http-request="uploadAttachment"
          >
            <el-button type="primary" size="small"><el-icon><Upload /></el-icon> 上传附件</el-button>
          </el-upload>
        </template>
      </GtPageHeader>
    </div>

    <!-- 附件列表 -->
    <el-table :data="attachments" v-loading="loading" stripe size="small" style="width: 100%">
      <el-table-column prop="file_name" label="文件名" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">
          <span class="gt-file-name" @click="preview(row)">
            <el-icon :size="16" class="gt-file-icon"><Document /></el-icon>
            {{ row.file_name }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="file_type" label="类型" width="80" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="(typeTagType(row.file_type)) || undefined">{{ row.file_type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="大小" width="100" align="right">
        <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
      </el-table-column>
      <el-table-column prop="ocr_status" label="OCR" width="120" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="(ocrTagType(row.ocr_status)) || undefined">{{ ocrLabel(row.ocr_status) }}</el-tag>
          <el-button v-if="row.ocr_status === 'failed'" link type="warning" size="small" @click="retryOCR(row)" style="margin-left:4px">重试</el-button>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="上传时间" width="140">
        <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="preview(row)">预览</el-button>
          <el-button link type="primary" size="small" @click="associateDialog(row)">关联底稿</el-button>
          <el-button link size="small" @click="download(row)">下载</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 附件预览弹窗 -->
    <AttachmentPreview
      v-model="previewVisible"
      :file-url="previewUrl"
      :file-name="previewName"
      :file-type="previewType"
      @close="previewVisible = false"
    />

    <!-- 关联底稿弹窗 -->
    <el-dialog append-to-body v-model="associateVisible" title="关联到底稿" width="480px">
      <el-form label-width="80px" size="small">
        <el-form-item label="搜索底稿">
          <el-select
            v-model="associateWpId"
            filterable
            remote
            :remote-method="searchWorkpapers"
            :loading="wpSearchLoading"
            placeholder="输入底稿编号或名称搜索"
            style="width: 100%"
            value-key="id"
          >
            <el-option
              v-for="wp in wpSearchResults"
              :key="wp.id"
              :label="`${wp.wp_code} ${wp.wp_name}`"
              :value="wp.id"
            >
              <span style="float: left">{{ wp.wp_code }}</span>
              <span style="float: right; color: var(--gt-color-text-secondary); font-size: 12px">{{ wp.wp_name }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="关联类型">
          <el-select v-model="associateType" style="width: 100%">
            <el-option label="审计证据" value="evidence" />
            <el-option label="支持文件" value="support" />
            <el-option label="函证回函" value="confirmation" />
            <el-option label="合同" value="contract" />
            <el-option label="银行对账单" value="bank_statement" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="associateNotes" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="associateVisible = false">取消</el-button>
        <el-button type="primary" size="small" @click="submitAssociate" :disabled="!associateWpId">确认关联</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Search, Upload, Document } from '@element-plus/icons-vue'
import AttachmentPreview from '@/components/extension/AttachmentPreview.vue'
import AttachmentPreviewDrawer from '@/components/common/AttachmentPreviewDrawer.vue'
import { downloadFile } from '@/utils/http'
import { api } from '@/services/apiProxy'
import { workpapers as P_wp, attachments as P_att } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)

const loading = ref(false)
const attachments = ref<any[]>([])
const searchQuery = ref('')
const filterType = ref('')

// 预览
const previewVisible = ref(false)
const previewUrl = ref('')
const previewName = ref('')
const previewType = ref('')

// 关联
const associateVisible = ref(false)
const associateAttachmentId = ref('')
const associateWpId = ref('')
const associateType = ref('evidence')
const associateNotes = ref('')
const wpSearchLoading = ref(false)
const wpSearchResults = ref<any[]>([])

async function searchWorkpapers(query: string) {
  if (!query || query.length < 1) { wpSearchResults.value = []; return }
  wpSearchLoading.value = true
  try {
    const data = await api.get(P_wp.wpIndex(projectId.value))
    const items = Array.isArray(data) ? data : data ?? []
    // 按编号或名称模糊过滤
    const q = query.toLowerCase()
    wpSearchResults.value = items.filter((w: any) =>
      (w.wp_code || '').toLowerCase().includes(q) ||
      (w.wp_name || '').toLowerCase().includes(q)
    ).slice(0, 20)
  } catch { wpSearchResults.value = [] }
  finally { wpSearchLoading.value = false }
}

async function loadAttachments() {
  loading.value = true
  try {
    const params: any = {}
    if (filterType.value) params.file_type = filterType.value
    const data = await api.get(P_att.list(projectId.value), { params })
    attachments.value = data ?? []
  } catch { attachments.value = [] }
  finally { loading.value = false }
}

async function onSearch() {
  if (!searchQuery.value) { loadAttachments(); return }
  loading.value = true
  try {
    const data = await api.get(P_att.search, {
      params: { project_id: projectId.value, q: searchQuery.value },
    })
    attachments.value = data ?? []
  } catch { attachments.value = [] }
  finally { loading.value = false }
}

function preview(row: any) {
  // TODO: replace AttachmentPreview dialog with AttachmentPreviewDrawer for unified drawer-based preview
  // 使用统一预览代理端点
  previewUrl.value = P_att.preview(row.id)
  previewName.value = row.file_name
  previewType.value = row.file_type
  previewVisible.value = true
}

async function download(row: any) {
  try {
    await downloadFile(P_att.download(row.id))
  } catch (e: any) {
    handleApiError(e, '下载')
  }
}

function associateDialog(row: any) {
  associateAttachmentId.value = row.id
  associateWpId.value = ''
  associateNotes.value = ''
  associateVisible.value = true
}

async function submitAssociate() {
  if (!associateWpId.value) { ElMessage.warning('请选择底稿'); return }
  try {
    await api.post(P_att.associate(associateAttachmentId.value), {
      wp_id: associateWpId.value,
      association_type: associateType.value,
      notes: associateNotes.value || undefined,
    })
    ElMessage.success('关联成功')
    associateVisible.value = false
  } catch (e: any) { handleApiError(e, '关联') }
}

function beforeUpload(file: File) {
  const maxSize = 50 * 1024 * 1024 // 50MB
  if (file.size > maxSize) {
    ElMessage.warning('文件大小不能超过 50MB')
    return false
  }
  return true
}

async function uploadAttachment(options: any) {
  const formData = new FormData()
  formData.append('file', options.file)
  try {
    const response = await api.post(
      P_att.upload(projectId.value),
      formData,
    )
    options.onSuccess?.(response.data)
    onUploadSuccess()
  } catch (error) {
    options.onError?.(error)
    handleApiError(error, '上传')
  }
}

function onUploadSuccess() {
  ElMessage.success('上传成功')
  loadAttachments()
}

async function retryOCR(row: any) {
  try {
    await api.put(P_att.ocrStatus(row.id), { status: 'pending' })
    ElMessage.success('已重新提交 OCR 识别')
    await loadAttachments()
  } catch (e: any) { handleApiError(e, '重试') }
}

function formatSize(bytes: number): string {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

function formatDate(d: string): string {
  if (!d) return '-'
  return new Date(d).toLocaleDateString('zh-CN')
}

function typeTagType(t: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const m: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = { pdf: 'danger', docx: '', xlsx: 'success', image: 'warning' }
  return m[t] || 'info'
}

function ocrTagType(s: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const m: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = { pending: 'info', processing: 'warning', completed: 'success', failed: 'danger' }
  return m[s] || 'info'
}

function ocrLabel(s: string): string {
  const m: Record<string, string> = { pending: '待识别', processing: '识别中', completed: '已完成', failed: '失败' }
  return m[s] || s
}

onMounted(loadAttachments)
</script>

<style scoped>
.gt-attachment-page { padding: var(--gt-space-4); }
.gt-att-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: var(--gt-space-4);
}
.gt-att-actions { display: flex; gap: var(--gt-space-2); align-items: center; }
.gt-file-name {
  display: flex; align-items: center; gap: 4px;
  cursor: pointer; color: var(--gt-color-primary);
}
.gt-file-name:hover { text-decoration: underline; }
.gt-file-icon { color: var(--gt-color-text-secondary); }
</style>
