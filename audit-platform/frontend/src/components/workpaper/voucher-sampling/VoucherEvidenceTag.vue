<script setup lang="ts">
/**
 * 凭证检查行的凭证证据（spec attachment-voucher-evidence-binding 需求 3，ADR-AVE-03）
 *
 * 放在「来源」列（VoucherRowMetaCell 内）：按行上的凭证键（`_gt.vk`）显示本底稿已取得的这张凭证的证据
 * （本行识别的、同一凭证另一行上传的、凭证级上传与引用的都算），可预览、移除、上传；
 * 别的可见底稿已有这张凭证的证据而本底稿没有时提示「他稿已有 n 份」，可逐份引用（不复制文件）。
 * 只读（归档 / 编辑锁 / 复核身份）与年审阶段的预审行只能查看。
 */
import { computed, hasInjectionContext, inject, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Paperclip } from '@element-plus/icons-vue'
import http from '@/utils/http'
import { attachments as P_att } from '@/services/apiPaths'
import AttachmentEyeButton from '@/components/attachment/AttachmentEyeButton.vue'
import { rowVoucherKey } from '@/components/attachment/rowEvidence'
import {
  EVIDENCE_MAX_UPLOAD_BYTES,
  uploadWorkpaperEvidence,
  voucherKeyLabel,
  voucherKeyYear,
} from '@/components/attachment/workpaperEvidence'
import {
  invalidateWpEvidenceLinks,
  useWpEvidenceLinks,
  type VoucherEvidenceGroup,
} from '@/composables/useWpEvidenceLinks'
import {
  refreshVoucherEvidence,
  useVoucherEvidenceIndex,
  type VoucherEvidenceAttachment,
  type VoucherEvidenceEntry,
} from '@/composables/useVoucherEvidenceIndex'
import { confirmDelete } from '@/utils/confirm'
import { handleApiError } from '@/utils/errorHandler'
import { WorkpaperRuntimeContextKey } from '../composables/useWorkpaperScaffold'

const props = defineProps<{
  row: unknown
  projectId: string
  /** 年审阶段的预审行：只读 */
  locked?: boolean
}>()

const runtime = hasInjectionContext() ? inject(WorkpaperRuntimeContextKey, null) : null
const wpId = computed(() => runtime?.wpId.value ?? '')
const voucherKey = computed(() => rowVoucherKey(props.row))
/** 他稿查询按凭证键自带的年度：不少宿主给「来源」列缺省传年度 0，按传入年度查，后端会把键全部丢掉 */
const year = computed(() => voucherKeyYear(voucherKey.value))
const canWrite = computed(() => !!wpId.value && !runtime?.readonly.value && !props.locked)
const label = computed(() => voucherKeyLabel(voucherKey.value) || '本凭证')

const store = useWpEvidenceLinks(() => props.projectId, () => wpId.value)
const index = useVoucherEvidenceIndex(() => props.projectId, () => year.value, () => voucherKey.value)
const here = computed<VoucherEvidenceGroup[]>(() => store.voucherEvidenceOf(voucherKey.value))
const elsewhere = computed<VoucherEvidenceEntry[]>(() => {
  const held = new Set(here.value.map((g) => g.attachmentId))
  return index.entries.value
    .filter((e) => e.working_paper_id !== wpId.value)
    .map((e) => ({ ...e, attachments: e.attachments.filter((a) => !held.has(a.id)) }))
    .filter((e) => e.attachments.length > 0)
})
const elsewhereCount = computed(() => elsewhere.value.reduce((n, e) => n + e.attachments.length, 0))
const busy = ref('')

function beforeUpload(file: File): boolean {
  if (file.size > EVIDENCE_MAX_UPLOAD_BYTES) {
    ElMessage.error('文件大小不能超过 50MB')
    return false
  }
  return true
}

async function afterChange(): Promise<void> {
  await invalidateWpEvidenceLinks(props.projectId, wpId.value).catch(() => [])
  await refreshVoucherEvidence(props.projectId, year.value, [voucherKey.value])
}

async function onUpload(req: { file: File }): Promise<void> {
  busy.value = 'upload'
  try {
    await uploadWorkpaperEvidence({
      projectId: props.projectId, wpId: wpId.value, file: req.file, evidenceType: 'voucher', voucherKey: voucherKey.value,
    })
    ElMessage.success(`已上传凭证 ${label.value} 的证据`)
    await afterChange()
  } catch (err: unknown) {
    handleApiError(err, '上传凭证证据')
  } finally {
    busy.value = ''
  }
}

async function onReuse(att: VoucherEvidenceAttachment, entry: VoucherEvidenceEntry): Promise<void> {
  busy.value = att.id
  try {
    await http.post(P_att.evidenceVoucherReuse(props.projectId, wpId.value),
      { voucher_key: voucherKey.value, attachment_id: att.id }, { _silent: true } as any)
    ElMessage.success(`已引用 ${entry.wp_code ?? '其他底稿'} 的「${att.file_name}」`)
    await afterChange()
  } catch (err: unknown) {
    handleApiError(err, '引用凭证证据')
  } finally {
    busy.value = ''
  }
}

async function onRemove(group: VoucherEvidenceGroup): Promise<void> {
  try {
    await confirmDelete({
      name: `凭证 ${label.value} 的证据「${group.attachment.file_name}」`,
      impact: '只移除本底稿与它的链接（含本行识别留下的），附件本身与其他底稿的引用不受影响',
    })
  } catch {
    return
  }
  busy.value = group.attachmentId
  try {
    for (const link of group.links) {
      await http.delete(P_att.evidenceLink(props.projectId, wpId.value, link.id), { _silent: true } as any)
    }
    ElMessage.success('已移除')
  } catch (err: unknown) {
    handleApiError(err, '移除凭证证据')
  } finally {
    busy.value = ''
    await afterChange()
  }
}
</script>

<template>
  <!-- persistent=false：弹出内容点开才渲染、收起即销毁（凭证检查表可能有上千行，每行常驻一份面板太重） -->
  <el-popover
    v-if="voucherKey && wpId && (here.length || elsewhereCount || canWrite)"
    placement="bottom-start"
    trigger="click"
    :width="320"
    :persistent="false"
  >
    <template #reference>
      <el-button
        class="gt-voucher-evidence__ref"
        link
        size="small"
        :type="here.length ? 'primary' : elsewhereCount ? 'warning' : 'info'"
        data-testid="voucher-evidence-tag"
        :aria-label="here.length ? `凭证 ${label} 已有证据 ${here.length} 份` : elsewhereCount ? `凭证 ${label} 他稿已有证据 ${elsewhereCount} 份` : `上传凭证 ${label} 的证据`"
        @click.stop
      >
        <el-icon><Paperclip /></el-icon>
        <span v-if="here.length">{{ here.length }}</span>
        <span v-else-if="elsewhereCount">他稿 {{ elsewhereCount }}</span>
      </el-button>
    </template>
    <div class="gt-voucher-evidence" data-testid="voucher-evidence-panel">
      <div class="gt-voucher-evidence__title">凭证 {{ label }} 的证据</div>
      <ul v-if="here.length" class="gt-voucher-evidence__list">
        <li v-for="g in here" :key="g.attachmentId" class="gt-voucher-evidence__item">
          <span class="gt-voucher-evidence__name" :title="g.attachment.file_name">{{ g.attachment.file_name }}</span>
          <AttachmentEyeButton
            :attachment-id="g.attachmentId"
            :file-name="g.attachment.file_name"
            :file-type="g.attachment.file_type"
            :ocr-status="g.attachment.ocr_status"
          />
          <el-button
            v-if="canWrite"
            link
            type="danger"
            size="small"
            :loading="busy === g.attachmentId"
            data-testid="voucher-evidence-remove"
            @click="onRemove(g)"
          >移除</el-button>
        </li>
      </ul>
      <div v-else class="gt-voucher-evidence__empty">本底稿还没有这张凭证的证据</div>
      <el-upload
        v-if="canWrite"
        :show-file-list="false"
        :before-upload="beforeUpload"
        :http-request="onUpload"
        accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.ofd,.doc,.docx,.xls,.xlsx"
      >
        <el-button size="small" :loading="busy === 'upload'" data-testid="voucher-evidence-upload">上传凭证 / 原始单据</el-button>
      </el-upload>
      <template v-if="elsewhere.length">
        <div class="gt-voucher-evidence__title">其他底稿已有</div>
        <ul class="gt-voucher-evidence__list">
          <template v-for="e in elsewhere" :key="e.working_paper_id">
            <li v-for="a in e.attachments" :key="`${e.working_paper_id}:${a.id}`" class="gt-voucher-evidence__item">
              <span class="gt-voucher-evidence__wp">{{ e.wp_code ?? '其他底稿' }}</span>
              <span class="gt-voucher-evidence__name" :title="a.file_name">{{ a.file_name }}</span>
              <AttachmentEyeButton :attachment-id="a.id" :file-name="a.file_name" :file-type="a.file_type" :ocr-status="a.ocr_status" />
              <el-button
                v-if="canWrite"
                link
                type="primary"
                size="small"
                :loading="busy === a.id"
                data-testid="voucher-evidence-reuse"
                @click="onReuse(a, e)"
              >引用到本底稿</el-button>
            </li>
          </template>
        </ul>
      </template>
      <div v-if="!canWrite" class="gt-voucher-evidence__hint">{{ locked ? '年审阶段的预审行只读' : '只读：可查看，不能上传或移除' }}</div>
    </div>
  </el-popover>
</template>

<style scoped>
.el-button.gt-voucher-evidence__ref {
  padding: 0 2px;
  min-height: auto;
  gap: 1px;
}
.gt-voucher-evidence__title {
  margin: 4px 0;
  font-weight: 600;
  font-size: var(--gt-font-size-xs, 12px);
}
.gt-voucher-evidence__list {
  list-style: none;
  margin: 0 0 6px;
  padding: 0;
  max-height: 220px;
  overflow-y: auto;
}
.gt-voucher-evidence__item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 0;
  font-size: var(--gt-font-size-xs, 12px);
}
.gt-voucher-evidence__name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.gt-voucher-evidence__wp {
  color: var(--gt-color-text-tertiary, #909399);
}
.gt-voucher-evidence__empty,
.gt-voucher-evidence__hint {
  margin: 4px 0;
  color: var(--gt-color-text-tertiary, #909399);
  font-size: var(--gt-font-size-xs, 12px);
}
</style>
