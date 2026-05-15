<script setup lang="ts">
/**
 * EvidenceLinkPanel — 证据清单 + 关联操作
 *
 * Sprint 6 Task 6.3: 展示底稿所有证据链接，支持新增/删除/批量关联
 */
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Paperclip, Delete, Plus } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'

interface EvidenceLink {
  id: string
  wp_id: string
  sheet_name: string | null
  cell_ref: string | null
  attachment_id: string
  page_ref: string | null
  evidence_type: string | null
  check_conclusion: string | null
  created_by: string
  created_at: string | null
}

const props = defineProps<{
  projectId: string
  wpId: string
}>()

const links = ref<EvidenceLink[]>([])
const loading = ref(false)
const showAddDialog = ref(false)

// 新增表单
const form = ref({
  attachment_id: '',
  sheet_name: '',
  cell_ref: '',
  page_ref: '',
  evidence_type: '',
})

const basePath = () => `/api/projects/${props.projectId}/workpapers/${props.wpId}/evidence`

async function fetchLinks() {
  loading.value = true
  try {
    const data = await api.get(basePath())
    links.value = data.items || []
  } catch (e: unknown) {
    handleApiError(e, '证据链')
  } finally {
    loading.value = false
  }
}

async function createLink() {
  if (!form.value.attachment_id) {
    ElMessage.warning('请选择附件')
    return
  }
  try {
    await api.post(`${basePath()}/link`, {
      attachment_id: form.value.attachment_id,
      sheet_name: form.value.sheet_name || null,
      cell_ref: form.value.cell_ref || null,
      page_ref: form.value.page_ref || null,
      evidence_type: form.value.evidence_type || null,
    })
    ElMessage.success('证据链接已创建')
    showAddDialog.value = false
    form.value = { attachment_id: '', sheet_name: '', cell_ref: '', page_ref: '', evidence_type: '' }
    await fetchLinks()
  } catch (e: unknown) {
    handleApiError(e, '证据链')
  }
}

async function deleteLink(linkId: string) {
  try {
    await ElMessageBox.confirm('确定删除该证据链接？', '确认')
    await api.delete(`${basePath()}/${linkId}`)
    ElMessage.success('已删除')
    await fetchLinks()
  } catch (e: unknown) {
    if ((e as { toString: () => string }).toString().includes('cancel')) return
    handleApiError(e, '证据链')
  }
}

onMounted(fetchLinks)
</script>

<template>
  <div class="evidence-link-panel">
    <div class="panel-header">
      <span class="title">
        <el-icon><Paperclip /></el-icon>
        证据链接
      </span>
      <el-button :icon="Plus" size="small" type="primary" @click="showAddDialog = true">
        关联附件
      </el-button>
    </div>

    <el-table :data="links" v-loading="loading" size="small" max-height="300" stripe>
      <el-table-column prop="cell_ref" label="单元格" width="80" />
      <el-table-column prop="sheet_name" label="Sheet" width="100" show-overflow-tooltip />
      <el-table-column prop="evidence_type" label="类型" width="80" />
      <el-table-column prop="page_ref" label="页码" width="60" />
      <el-table-column prop="created_at" label="创建时间" width="140" show-overflow-tooltip />
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button :icon="Delete" size="small" type="danger" link @click="deleteLink(row.id)" />
        </template>
      </el-table-column>
    </el-table>

    <!-- 新增对话框 -->
    <el-dialog v-model="showAddDialog" title="关联附件" width="420px">
      <el-form label-width="80px" size="small">
        <el-form-item label="附件ID">
          <el-input v-model="form.attachment_id" placeholder="附件 UUID" />
        </el-form-item>
        <el-form-item label="Sheet">
          <el-input v-model="form.sheet_name" placeholder="可选" />
        </el-form-item>
        <el-form-item label="单元格">
          <el-input v-model="form.cell_ref" placeholder="如 B5" />
        </el-form-item>
        <el-form-item label="页码">
          <el-input v-model="form.page_ref" placeholder="如 P3-P5" />
        </el-form-item>
        <el-form-item label="证据类型">
          <el-select v-model="form.evidence_type" placeholder="选择类型" clearable>
            <el-option label="原始凭证" value="voucher" />
            <el-option label="合同" value="contract" />
            <el-option label="对账单" value="statement" />
            <el-option label="函证" value="confirmation" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="createLink">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.evidence-link-panel {
  padding: 8px;
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.panel-header .title {
  font-weight: 600;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
