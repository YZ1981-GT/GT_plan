<template>
  <el-dialog v-model="visible" title="提交复核" width="560px" append-to-body :close-on-click-modal="false">
    <div class="gt-adj-submit-list">
      <div class="gt-adj-submit-caption">将以下 {{ entries.length }} 笔分录提交复核（提交后不能修改，可撤回提交）：</div>
      <div v-for="e in entries.slice(0, 8)" :key="e.entry_group_id" class="gt-adj-submit-item">
        <span class="gt-adj-submit-no">{{ e.adjustment_no || '—' }}</span>
        <span class="gt-adj-submit-desc">{{ e.description || '（无摘要）' }}</span>
      </div>
      <div v-if="entries.length > 8" class="gt-adj-submit-more">… 另 {{ entries.length - 8 }} 笔</div>
    </div>

    <el-form ref="formRef" :model="formState" :rules="formRules" label-width="84px" @submit.prevent>
      <el-form-item label="通知复核人" prop="reviewerIds">
        <el-select v-model="formState.reviewerIds" multiple filterable collapse-tags collapse-tags-tooltip style="width: 100%"
          :loading="loading" :placeholder="reviewers.length ? '选择要通知的复核人' : '本项目没有可选的复核人'"
          :disabled="!reviewers.length">
          <el-option v-for="r in reviewers" :key="r.user_id" :value="r.user_id" :label="reviewerLabel(r)" />
        </el-select>
        <div v-if="loadError" class="gt-adj-submit-hint is-warn">复核人列表读取失败（{{ loadError }}），提交后将通知全部有复核权限的成员</div>
        <div v-else-if="!loading && !reviewers.length" class="gt-adj-submit-hint is-warn">
          本项目没有其他可复核调整分录的成员，提交后不会通知任何人；可在项目团队中委派项目经理或合伙人。
        </div>
        <div v-else-if="!loading" class="gt-adj-submit-hint">站内通知所选人员，点通知可直接定位到这些分录</div>
      </el-form-item>
      <el-form-item label="备注" prop="note">
        <el-input v-model="formState.note" type="textarea" :rows="2" maxlength="500" show-word-limit placeholder="可选，如：坏账测算见 D2-3" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" :disabled="!entries.length" @click="submit">提交复核</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * 提交复核弹窗（spec adjustment-hall-entry-review-closure 需求 4.1）：选择通知哪些复核人（默认全选）、填备注，
 * 批量逐笔提交，返回逐笔结果。大厅经 ref 调 open(分录)，完成后 emit done 由大厅刷新。
 */
import { nextTick, reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import {
  listAdjustmentReviewers, submitAdjustmentsForReview, type AdjustmentFlowResult, type AdjustmentReviewer,
} from '@/services/auditPlatformApi'
import { adjustmentErrorMessage, reportAdjustmentError, showFlowResult } from '@/composables/useAdjustmentHallActions'

interface SubmitEntry {
  entry_group_id: string
  adjustment_no?: string | null
  description?: string | null
}

const props = defineProps<{ projectId: string }>()
const emit = defineEmits<{ done: [result: AdjustmentFlowResult] }>()

const visible = ref(false)
const entries = ref<SubmitEntry[]>([])
const reviewers = ref<AdjustmentReviewer[]>([])
const formState = reactive({ reviewerIds: [] as string[], note: '' })
const loading = ref(false)
const loadError = ref('')
const submitting = ref(false)

const formRef = ref<FormInstance>()
/** 有可选复核人时至少选一位（不选 = 后端通知全部候选，与「我取消了所有人」的意图相反） */
const formRules: FormRules = {
  reviewerIds: [{
    trigger: 'change',
    validator: (_rule, value: string[], callback) =>
      (reviewers.value.length && !value?.length ? callback(new Error('请至少选择一位复核人')) : callback()),
  }],
  note: [{ max: 500, message: '备注不超过 500 字', trigger: 'blur' }],
}

const ROLE_LABELS: Record<string, string> = {
  partner: '合伙人', signing_partner: '签字合伙人', manager: '项目经理', qc: '质控', eqcr: 'EQCR',
  auditor: '审计员', assistant: '审计助理', admin: '管理员',
}

function reviewerLabel(r: AdjustmentReviewer): string {
  const role = ROLE_LABELS[r.project_role || ''] || ROLE_LABELS[r.system_role] || ''
  return role ? `${r.name}（${role}）` : r.name
}

async function open(rows: SubmitEntry[]) {
  entries.value = rows.map((r) => ({ entry_group_id: r.entry_group_id, adjustment_no: r.adjustment_no, description: r.description }))
  formState.note = ''
  formState.reviewerIds = []
  loadError.value = ''
  visible.value = true
  loading.value = true
  try {
    reviewers.value = await listAdjustmentReviewers(props.projectId)
  } catch (err) {
    reviewers.value = []
    loadError.value = adjustmentErrorMessage(err)
  } finally {
    loading.value = false
  }
  formState.reviewerIds = reviewers.value.map((r) => r.user_id)
  await nextTick()
  formRef.value?.clearValidate()
}

async function submit() {
  const ok = await (formRef.value?.validate().then(() => true, () => false) ?? Promise.resolve(true))
  if (!ok) return
  submitting.value = true
  try {
    const result = await submitAdjustmentsForReview(props.projectId, {
      entry_group_ids: entries.value.map((e) => e.entry_group_id),
      // 列表没读到时不传 ⇒ 后端通知全部候选
      reviewer_ids: reviewers.value.length ? formState.reviewerIds : undefined,
      note: formState.note.trim() || undefined,
    })
    showFlowResult(result, '提交复核')
    visible.value = false
    emit('done', result)
  } catch (err) {
    reportAdjustmentError(err, '提交复核')
  } finally {
    submitting.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
.gt-adj-submit-list {
  max-height: 200px; overflow-y: auto;
  padding: 8px 12px; margin-bottom: 14px;
  border-radius: var(--gt-radius-sm);
  background: var(--gt-color-primary-bg);
}
.gt-adj-submit-caption { font-size: var(--gt-font-size-sm); margin-bottom: 6px; color: var(--gt-color-text-regular); }
.gt-adj-submit-item { display: flex; gap: 10px; font-size: var(--gt-font-size-sm); line-height: 1.8; }
.gt-adj-submit-no { flex-shrink: 0; min-width: 72px; font-weight: 600; color: var(--gt-color-primary); }
.gt-adj-submit-desc { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--gt-color-text); }
.gt-adj-submit-more { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-adj-submit-hint { font-size: var(--gt-font-size-xs); line-height: 1.6; margin-top: 4px; color: var(--gt-color-text-tertiary); }
.gt-adj-submit-hint.is-warn { color: var(--el-color-warning-dark-2); }
</style>
