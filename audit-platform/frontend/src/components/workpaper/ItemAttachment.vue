<template>
  <div class="gt-item-attach">
    <div class="gt-item-attach-list">
      <div
        v-for="row in rows"
        :key="row.id"
        class="gt-item-attach-row"
      >
        <el-icon><Document /></el-icon>
        <a
          href="#"
          class="gt-item-attach-link"
          @click.prevent="downloadAttachment(row.attachment_id, row.attachment.file_name)"
        >{{ row.attachment.file_name }}</a>
        <span class="gt-item-attach-size">{{ formatSize(row.attachment.file_size) }}</span>
        <el-button
          v-if="!readonly"
          text
          size="small"
          type="danger"
          :loading="removingId === row.id"
          :aria-label="`移除本行证据 ${row.attachment.file_name}`"
          @click="onRemove(row)"
        >×</el-button>
      </div>
    </div>

    <el-upload
      v-if="!readonly"
      :auto-upload="true"
      :show-file-list="false"
      :http-request="onUpload"
      :before-upload="beforeUpload"
      :accept="accept || '.pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg'"
    >
      <el-button size="small" plain :loading="uploading">📎 上传附件</el-button>
    </el-upload>
  </div>
</template>

<script setup lang="ts">
/**
 * ItemAttachment — 逐项附件（行级证据）
 *
 * 位置键：表页 = sheetKey，单元格 = `item:{itemIndex}`（spec attachment-evidence-intake ADR-AEI-08）。
 * - 上传走底稿证据入口，只写行级证据链接（不再按 title 打标、不再挂整稿关联）；
 * - 列表读本底稿共享链接仓（同一底稿的所有实例只发一次请求），按位置过滤；
 * - 移除 = 删除本行的证据链接（附件本身保留在项目附件里）。
 */
import { computed, ref } from 'vue'
import { Document } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { confirmDelete } from '@/utils/confirm'
import { handleApiError } from '@/utils/errorHandler'
import { downloadAttachment } from '@/components/attachment/downloadAttachment'
import {
  EVIDENCE_MAX_UPLOAD_BYTES,
  itemCellRef,
  uploadWorkpaperEvidence,
} from '@/components/attachment/workpaperEvidence'
import {
  removeWpEvidenceLink,
  useWpEvidenceLinks,
  type WpEvidenceLink,
} from '@/composables/useWpEvidenceLinks'

interface Props {
  projectId: string
  wpId: string
  sheetKey: string
  itemIndex: number | string
  accept?: string
  /** 证据类型；不传由后端按底稿编码的证据声明取缺省 */
  evidenceType?: string
  /** 只读：隐藏上传与移除 */
  readonly?: boolean
}
const props = withDefaults(defineProps<Props>(), {
  accept: undefined,
  evidenceType: undefined,
  readonly: false,
})

const uploading = ref(false)
const removingId = ref('')

const store = useWpEvidenceLinks(() => props.projectId, () => props.wpId)
const cellRef = computed(() => itemCellRef(props.itemIndex))
const rows = computed(() => store.linksAt(props.sheetKey, cellRef.value))

function beforeUpload(file: File): boolean {
  if (file.size > EVIDENCE_MAX_UPLOAD_BYTES) {
    ElMessage.error('文件大小不能超过 50MB')
    return false
  }
  return true
}

async function onUpload(req: { file: File }) {
  uploading.value = true
  try {
    await uploadWorkpaperEvidence({
      projectId: props.projectId,
      wpId: props.wpId,
      file: req.file,
      evidenceType: props.evidenceType,
      sheetName: props.sheetKey,
      cellRef: cellRef.value,
    })
    ElMessage.success('附件已上传')
  } catch (err: unknown) {
    handleApiError(err, '上传附件')
  } finally {
    uploading.value = false
  }
}

async function onRemove(row: WpEvidenceLink) {
  try {
    await confirmDelete({
      name: `本行证据「${row.attachment.file_name}」的链接`,
      impact: '只移除与本行的链接，附件本身仍保留在项目附件中',
    })
  } catch {
    return
  }
  removingId.value = row.id
  try {
    await removeWpEvidenceLink(props.projectId, props.wpId, row.id)
    ElMessage.success('已移除本行证据')
  } catch (err: unknown) {
    handleApiError(err, '移除本行证据')
  } finally {
    removingId.value = ''
  }
}

function formatSize(bytes: number | null | undefined): string {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + 'B'
  if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + 'KB'
  return (bytes / 1024 / 1024).toFixed(1) + 'MB'
}
</script>

<style scoped>
.gt-item-attach {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.gt-item-attach-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.gt-item-attach-row {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 3px 6px;
  font-size: 12px;
  background: var(--gt-color-bg-page, #f8f7fc);
  border-radius: 3px;
}
.gt-item-attach-link {
  flex: 1;
  color: var(--gt-color-primary, #4b2d77);
  text-decoration: none;
}
.gt-item-attach-link:hover {
  text-decoration: underline;
}
.gt-item-attach-size {
  font-size: 11px;
  color: var(--gt-color-text-tertiary, #909399);
}
</style>
