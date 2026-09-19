<script setup lang="ts">
/**
 * ReviewEvidenceTab — 复核证据展示 + 绑定/关闭/重开 + 完成阻断（useReviewGovernance）
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening (R9/R10)
 */
import { ref, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useReviewGovernance } from '@/composables/useReviewGovernance'

const props = defineProps<{ projectId: string; year: number }>()
const projectIdRef = toRef(props, 'projectId') as any
const yearRef = toRef(props, 'year') as any
const {
  loading, error, reviewState, completion, hasStaleEvidence,
  getReview, bindEvidence, closeReview, reopenReview, checkCompletionBlock,
} = useReviewGovernance(projectIdRef, yearRef)

const reviewId = ref('')
const bindRefId = ref('')

async function loadReview() {
  if (!reviewId.value) return
  await getReview(reviewId.value)
  if (error.value) ElMessage.error(error.value)
}

async function onBind() {
  if (!reviewId.value || !bindRefId.value) {
    ElMessage.warning('请填写复核 ID 与 EvidenceRef ID')
    return
  }
  const res = await bindEvidence(reviewId.value, { evidence_ref_id: bindRefId.value })
  if (res) { ElMessage.success('证据已绑定并冻结快照'); bindRefId.value = ''; await loadReview() }
  else if (error.value) ElMessage.error(error.value)
}

async function onClose() {
  try {
    const { value } = await ElMessageBox.prompt('输入关闭说明（需充分且需至少一个非 stale 证据）', '关闭复核', { inputType: 'textarea' })
    if (!value) return
    const res = await closeReview(reviewId.value, value)
    if (res) { ElMessage.success('复核已关闭'); await loadReview() }
    else if (error.value) ElMessage.error(error.value)
  } catch { /* cancelled */ }
}

async function onReopen() {
  const res = await reopenReview(reviewId.value)
  if (res) { ElMessage.success('复核已置为待重新复核'); await loadReview() }
  else if (error.value) ElMessage.error(error.value)
}

async function loadCompletion() {
  await checkCompletionBlock()
  if (error.value) ElMessage.error(error.value)
}

const statusMeta: Record<string, { type: string; label: string }> = {
  open: { type: 'warning', label: '未关闭' },
  closed: { type: 'success', label: '已关闭' },
  re_review_required: { type: 'danger', label: '待重新复核' },
}

function truncate(h: string | null): string {
  if (!h) return '-'
  return h.length <= 16 ? h : h.slice(0, 8) + '…' + h.slice(-8)
}
</script>

<template>
  <div class="evgov-tab">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="复核意见关联当前有效证据并冻结版本快照；证据失效自动重开并阻断 QC/EQCR/合伙人完成。"
      style="margin-bottom: 12px"
    />

    <el-card shadow="never" header="完成阻断状态（QC/EQCR/合伙人）" style="margin-bottom: 16px">
      <el-button size="small" :loading="loading" @click="loadCompletion">检查阻断状态</el-button>
      <el-tag :type="completion.blocked ? 'danger' : 'success'" style="margin-left: 12px">
        {{ completion.blocked ? `被阻断（${completion.re_review_required_reviews.length} 条待重新复核）` : '未被阻断' }}
      </el-tag>
    </el-card>

    <el-card shadow="never" header="复核意见证据">
      <el-form :inline="true" size="default">
        <el-form-item label="复核 ID">
          <el-input v-model="reviewId" placeholder="review_id" style="width: 260px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="loadReview">加载</el-button>
          <el-button type="danger" plain :disabled="!reviewState" @click="onClose">关闭复核</el-button>
          <el-button :disabled="!reviewState" @click="onReopen">重开</el-button>
        </el-form-item>
      </el-form>

      <el-alert v-if="error" type="error" :title="error" show-icon :closable="true" style="margin: 8px 0" />

      <template v-if="reviewState">
        <div class="review-header">
          <el-tag :type="statusMeta[reviewState.status]?.type || 'info'">
            {{ statusMeta[reviewState.status]?.label || reviewState.status }}
          </el-tag>
          <el-tag v-if="hasStaleEvidence" type="danger" style="margin-left: 8px">含失效证据</el-tag>
          <span v-if="reviewState.close_note" class="close-note">关闭说明：{{ reviewState.close_note }}</span>
        </div>

        <el-form :inline="true" size="small" style="margin: 10px 0">
          <el-form-item label="绑定 EvidenceRef">
            <el-input v-model="bindRefId" placeholder="evidence_ref_id" style="width: 260px" />
          </el-form-item>
          <el-form-item>
            <el-button size="small" @click="onBind">绑定证据</el-button>
          </el-form-item>
        </el-form>

        <el-table :data="reviewState.evidence" size="small" border stripe empty-text="暂无绑定证据">
          <el-table-column prop="evidence_type" label="证据类型" width="150" />
          <el-table-column label="版本" width="80">
            <template #default="{ row }">v{{ row.target_version ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="Hash" min-width="160">
            <template #default="{ row }"><span class="mono">{{ truncate(row.content_hash) }}</span></template>
          </el-table-column>
          <el-table-column label="失效" width="90" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.is_stale ? 'danger' : 'success'">
                {{ row.is_stale ? 'stale' : '有效' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="定位器" min-width="160">
            <template #default="{ row }">
              <span class="mono">{{ row.locator ? JSON.stringify(row.locator) : '-' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </el-card>
  </div>
</template>

<style scoped>
.evgov-tab { padding: 4px 0; }
.mono { font-family: 'Courier New', monospace; font-size: 12px; }
.review-header { display: flex; align-items: center; gap: 8px; }
.close-note { font-size: 12px; color: #606266; }
</style>
