<script setup lang="ts">
/**
 * EvidenceLinkPanel — 本底稿证据链接清单 + 把已有附件链接到表页 / 单元格
 *
 * spec attachment-evidence-intake 需求 3、5.3：
 * - 清单显示文件名与位置（后端列表已带附件元数据，附件软删的不返回）；
 * - 新增链接从本底稿已有附件里选（统一视图），不再手填附件 UUID；后端只接受本底稿已有的附件；
 * - 证据类型选项与上传入口同一份（`EVIDENCE_TYPE_OPTIONS`）；
 * - 列表走共享链接仓，与行级附件组件同一份数据。
 */
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Paperclip, Delete, Plus } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { attachments as P_att } from '@/services/apiPaths'
import { confirmDelete } from '@/utils/confirm'
import { handleApiError } from '@/utils/errorHandler'
import {
  EVIDENCE_TYPE_LABEL,
  EVIDENCE_TYPE_OPTIONS,
  evidencePositionLabel,
} from '@/components/attachment/workpaperEvidence'
import AttachmentEyeButton from '@/components/attachment/AttachmentEyeButton.vue'
import {
  invalidateWpEvidenceLinks,
  removeWpEvidenceLink,
  useWpEvidenceLinks,
  type WpEvidenceLink,
} from '@/composables/useWpEvidenceLinks'

const props = defineProps<{
  projectId: string
  wpId: string
}>()

const store = useWpEvidenceLinks(() => props.projectId, () => props.wpId)
const links = computed(() => store.links.value)
const loading = computed(() => store.loading.value)

const showAddDialog = ref(false)
const saving = ref(false)
const candidates = ref<Array<{ id: string; file_name: string }>>([])
const candidatesLoading = ref(false)

const emptyForm = () => ({ attachment_id: '', sheet_name: '', cell_ref: '', page_ref: '', evidence_type: '' })
const form = ref(emptyForm())

async function openAddDialog() {
  form.value = emptyForm()
  showAddDialog.value = true
  candidatesLoading.value = true
  try {
    const data: any = await api.get(P_att.wpView(props.wpId))
    const items: any[] = Array.isArray(data) ? data : data?.items || []
    candidates.value = items.map((it) => ({ id: String(it.id), file_name: String(it.file_name || '附件') }))
  } catch (e: unknown) {
    candidates.value = []
    handleApiError(e, '本底稿附件')
  } finally {
    candidatesLoading.value = false
  }
}

async function createLink() {
  if (!form.value.attachment_id) {
    ElMessage.warning('请选择附件')
    return
  }
  saving.value = true
  try {
    await api.post(P_att.evidenceLinkCreate(props.projectId, props.wpId), {
      attachment_id: form.value.attachment_id,
      sheet_name: form.value.sheet_name || null,
      cell_ref: form.value.cell_ref || null,
      page_ref: form.value.page_ref || null,
      evidence_type: form.value.evidence_type || null,
    })
    ElMessage.success('证据链接已创建')
    showAddDialog.value = false
    await invalidateWpEvidenceLinks(props.projectId, props.wpId)
  } catch (e: unknown) {
    handleApiError(e, '证据链接')
  } finally {
    saving.value = false
  }
}

async function deleteLink(row: WpEvidenceLink) {
  try {
    await confirmDelete({
      name: `「${row.attachment.file_name}」在 ${evidencePositionLabel(row)} 的证据链接`,
      impact: '只删除链接，附件本身保留',
    })
  } catch {
    return
  }
  try {
    await removeWpEvidenceLink(props.projectId, props.wpId, row.id)
    ElMessage.success('已删除')
  } catch (e: unknown) {
    handleApiError(e, '证据链接')
  }
}

function typeLabel(value: string | null): string {
  return value ? EVIDENCE_TYPE_LABEL[value] || value : '—'
}
</script>

<template>
  <div class="evidence-link-panel">
    <div class="panel-header">
      <span class="title">
        <el-icon><Paperclip /></el-icon>
        证据链接
      </span>
      <el-button :icon="Plus" size="small" type="primary" data-testid="evidence-link-add" @click="openAddDialog">
        关联附件
      </el-button>
    </div>

    <el-table :data="links" v-loading="loading" size="small" max-height="300" stripe>
      <el-table-column label="文件" min-width="120" show-overflow-tooltip>
        <template #default="{ row }">
          <span>{{ row.attachment?.file_name }}</span>
          <AttachmentEyeButton
            :attachment-id="row.attachment_id"
            :file-name="row.attachment?.file_name"
            :file-type="row.attachment?.file_type"
            :ocr-status="row.attachment?.ocr_status"
          />
        </template>
      </el-table-column>
      <el-table-column label="位置" min-width="110" show-overflow-tooltip>
        <template #default="{ row }">{{ evidencePositionLabel(row) }}</template>
      </el-table-column>
      <el-table-column label="类型" width="90">
        <template #default="{ row }">{{ typeLabel(row.evidence_type) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button
            :icon="Delete"
            size="small"
            type="danger"
            link
            :aria-label="`删除证据链接 ${row.attachment?.file_name || ''}`"
            @click="deleteLink(row)"
          />
        </template>
      </el-table-column>
    </el-table>

    <!-- 新增对话框 -->
    <el-dialog v-model="showAddDialog" title="关联附件" width="440px">
      <el-form label-width="80px" size="small">
        <el-form-item label="附件">
          <el-select
            v-model="form.attachment_id"
            filterable
            :loading="candidatesLoading"
            placeholder="选择本底稿已有附件"
            no-data-text="本底稿暂无附件，请先在附件面板上传"
            data-testid="evidence-link-attachment"
          >
            <el-option v-for="att in candidates" :key="att.id" :label="att.file_name" :value="att.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="表页">
          <el-input v-model="form.sheet_name" placeholder="可选，如 D2-3" maxlength="100" />
        </el-form-item>
        <el-form-item label="单元格">
          <el-input v-model="form.cell_ref" placeholder="可选，如 B5" maxlength="100" />
        </el-form-item>
        <el-form-item label="页码">
          <el-input v-model="form.page_ref" placeholder="可选，如 P3-P5" maxlength="50" />
        </el-form-item>
        <el-form-item label="证据类型">
          <el-select v-model="form.evidence_type" placeholder="选择类型" clearable>
            <el-option v-for="opt in EVIDENCE_TYPE_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" data-testid="evidence-link-submit" @click="createLink">确定</el-button>
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
  font-size: var(--gt-font-size-sm);
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
