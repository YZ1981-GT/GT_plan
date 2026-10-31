<template>
  <div class="gt-item-attach">
    <div class="gt-item-attach-list">
      <div
        v-for="row in rows"
        :key="row.id"
        class="gt-item-attach-row"
      >
        <el-icon><Document /></el-icon>
        <!-- 点文件名即预览（原先直接下载）；预览抽屉里也能下载 -->
        <a
          href="#"
          class="gt-item-attach-link"
          :title="`预览 ${row.attachment.file_name}`"
          @click.prevent="openPreview(row)"
        >{{ row.attachment.file_name }}</a>
        <span class="gt-item-attach-size">{{ formatSize(row.attachment.file_size) }}</span>
        <AttachmentEyeButton
          :ref="(el: unknown) => setEye(row.id, el)"
          :attachment-id="row.attachment_id"
          :file-name="row.attachment.file_name"
          :file-type="row.attachment.file_type"
          :ocr-status="row.attachment.ocr_status"
        />
        <el-button
          text
          size="small"
          :aria-label="`下载 ${row.attachment.file_name}`"
          title="下载"
          @click="downloadAttachment(row.attachment_id, row.attachment.file_name)"
        ><el-icon><Download /></el-icon></el-button>
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
 * 位置键：表页 = sheetKey，单元格 = `item:{itemIndex}`（spec attachment-evidence-intake ADR-AEI-08），
 * 或调用方直接给 `cellRef`（行有稳定 id 的表用 `row:{行 id}`，spec attachment-confirmation-evidence-loop 需求 4）。
 * - 上传走底稿证据入口，只写行级证据链接（不再按 title 打标、不再挂整稿关联）；
 * - 列表读本底稿共享链接仓（同一底稿的所有实例只发一次请求），按位置过滤；
 * - 移除 = 删除本行的证据链接（附件本身保留在项目附件里）；
 * - 每份文件有小眼睛预览，点文件名也是预览，另有下载按钮（spec attachment-inline-preview）。
 */
import { computed, ref } from 'vue'
import { Document, Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import AttachmentEyeButton from '@/components/attachment/AttachmentEyeButton.vue'
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
  /** 槽位序号 ⇒ 位置 `item:{序号}`；行有稳定 id 时改传 `cellRef`（如 `row:{行 id}`），两者给一个即可 */
  itemIndex?: number | string
  cellRef?: string
  accept?: string
  /** 证据类型；不传由后端按底稿编码的证据声明取缺省（带凭证键时缺省记凭证 / 原始单据） */
  evidenceType?: string
  /** 凭证检查行的凭证键（`_gt.vk`）：上传时带上，按凭证身份挂（spec attachment-voucher-evidence-binding 需求 4.3） */
  voucherKey?: string | null
  /** 只读：隐藏上传与移除 */
  readonly?: boolean
}
const props = withDefaults(defineProps<Props>(), {
  itemIndex: undefined,
  cellRef: undefined,
  accept: undefined,
  evidenceType: undefined,
  voucherKey: null,
  readonly: false,
})

const uploading = ref(false)
const removingId = ref('')

const store = useWpEvidenceLinks(() => props.projectId, () => props.wpId)
const cellRef = computed(() => props.cellRef || itemCellRef(props.itemIndex ?? 0))
const rows = computed(() => store.linksAt(props.sheetKey, cellRef.value))

/** 每行一个小眼睛；点文件名复用同一个（spec attachment-inline-preview ADR-AIP-04） */
const eyes = new Map<string, { open: () => Promise<void> }>()
function setEye(id: string, el: unknown) {
  if (el && typeof (el as { open?: unknown }).open === 'function') eyes.set(id, el as { open: () => Promise<void> })
  else eyes.delete(id)
}
function openPreview(row: WpEvidenceLink) {
  void eyes.get(row.id)?.open()
}

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
      voucherKey: props.voucherKey,
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
