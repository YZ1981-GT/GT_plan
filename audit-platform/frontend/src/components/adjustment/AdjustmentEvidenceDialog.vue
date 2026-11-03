<template>
  <el-dialog v-model="visible" title="调整证据" width="min(720px, 94vw)" append-to-body destroy-on-close>
    <el-alert type="info" :closable="false" show-icon
      title="重大或高风险调整批准前必须关联有效附件版本或凭证；引用会固定证据版本。" />
    <el-form label-position="top" class="gt-adj-evidence__form">
      <el-form-item label="证据类型">
        <el-radio-group v-model="targetType">
          <el-radio-button value="attachment_version">附件版本</el-radio-button>
          <el-radio-button value="voucher">凭证</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="targetType === 'attachment_version'" label="项目附件">
        <el-select v-model="selectedVersionId" filterable placeholder="选择已有附件" style="width: 100%">
          <el-option v-for="item in attachmentOptions" :key="item.current_version_id"
            :label="item.file_name" :value="item.current_version_id" />
        </el-select>
        <span v-if="attachments.length && !attachmentOptions.length" class="gt-adj-evidence__hint">
          这些附件尚无可引用的治理版本，请从附件管理重新上传或生成版本。
        </span>
      </el-form-item>
      <el-form-item v-else label="凭证证据 ID">
        <el-input v-model="voucherId" placeholder="从序时账凭证详情复制凭证证据 ID" />
      </el-form-item>
      <el-form-item label="证据说明">
        <el-input v-model="label" maxlength="200" placeholder="例如：客户确认函、调整测算底表" />
      </el-form-item>
      <el-button type="primary" :loading="loading" :disabled="!canAdd" @click="addRef">关联证据</el-button>
    </el-form>

    <el-divider content-position="left">已关联证据</el-divider>
    <el-alert v-if="error" type="error" :closable="false" show-icon :title="error" />
    <el-empty v-else-if="!loading && refs.length === 0" description="暂无有效证据引用" :image-size="64" />
    <el-table v-else :data="refs" size="small" border v-loading="loading">
      <el-table-column prop="label" label="说明" min-width="160" />
      <el-table-column label="类型" width="110">
        <template #default="{ row: item }">{{ item.evidence_type === 'voucher' ? '凭证' : '附件版本' }}</template>
      </el-table-column>
      <el-table-column prop="target_version" label="版本" width="72" />
      <el-table-column label="操作" width="86">
        <template #default="{ row: item }"><el-button link type="danger" @click="removeRef(item.id)">解除</el-button></template>
      </el-table-column>
    </el-table>
    <template #footer><el-button @click="visible = false">关闭</el-button></template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listAttachments } from '@/services/commonApi'
import { useEvidenceRefs } from '@/composables/useEvidenceRefs'
import { newUuid } from '@/utils/uuid'

const props = defineProps<{ projectId: string; year: number | null }>()
const projectRef = computed(() => props.projectId)
const yearRef = computed(() => props.year || 0)
const { loading, error, refs, queryRefs, createRef, deactivateRef } = useEvidenceRefs(projectRef, yearRef)
const visible = ref(false)
const groupId = ref('')
const revision = ref(1)
const attachments = ref<any[]>([])
const targetType = ref<'attachment_version' | 'voucher'>('attachment_version')
const selectedVersionId = ref('')
const voucherId = ref('')
const label = ref('')

const attachmentOptions = computed(() => attachments.value.filter((item) => item.current_version_id))
const canAdd = computed(() => props.year != null && !!groupId.value
  && (targetType.value === 'attachment_version' ? !!selectedVersionId.value : !!voucherId.value.trim()))

async function reload(): Promise<void> {
  if (!groupId.value || props.year == null) return
  await Promise.all([
    queryRefs({ direction: 'source', source_type: 'adjustment', source_id: groupId.value, status: 'active', limit: 100 }),
    listAttachments(props.projectId).then((items) => { attachments.value = items }),
  ])
}

async function open(row: { entry_group_id: string; content_revision?: number }): Promise<void> {
  groupId.value = row.entry_group_id
  revision.value = Number(row.content_revision) || 1
  selectedVersionId.value = ''
  voucherId.value = ''
  label.value = ''
  visible.value = true
  await reload()
}

async function addRef(): Promise<void> {
  if (!canAdd.value) return
  const isAttachment = targetType.value === 'attachment_version'
  const evidenceId = isAttachment ? selectedVersionId.value : voucherId.value.trim()
  const selected = attachmentOptions.value.find((item) => item.current_version_id === selectedVersionId.value)
  const result = await createRef({
    source_type: 'adjustment',
    source_id: groupId.value,
    source_version: revision.value,
    evidence_type: targetType.value,
    evidence_id: evidenceId,
    attachment_version_id: isAttachment ? evidenceId : undefined,
    label: label.value.trim() || selected?.file_name || (isAttachment ? '调整支持附件' : '调整支持凭证'),
    context: JSON.stringify({ purpose: 'adjustment_review_evidence' }),
  }, newUuid())
  if (!result) return
  ElMessage.success(result.created ? '证据已关联' : '该证据已关联')
  selectedVersionId.value = ''
  voucherId.value = ''
  label.value = ''
  await reload()
}

async function removeRef(refId: string): Promise<void> {
  try {
    await ElMessageBox.confirm('解除后，该证据不再支持本调整。历史引用仍保留。', '解除证据', {
      type: 'warning', confirmButtonText: '确认解除', cancelButtonText: '取消',
    })
  } catch { return }
  const result = await deactivateRef(refId, '用户从调整分录解除关联', newUuid())
  if (!result) return
  ElMessage.success('已解除证据关联')
  await reload()
}

defineExpose({ open })
</script>

<style scoped>
.gt-adj-evidence__form { margin-top: 14px; }
.gt-adj-evidence__hint { display: block; margin-top: 4px; color: var(--gt-color-warning); font-size: var(--gt-font-size-xs); }
</style>
