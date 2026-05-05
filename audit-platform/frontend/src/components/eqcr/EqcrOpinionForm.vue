<template>
  <div class="eqcr-opinion-form">
    <!-- 当前意见展示（只读） -->
    <div v-if="!editing" class="eqcr-opinion-current">
      <template v-if="currentOpinion">
        <div class="eqcr-opinion-current__header">
          <el-tag
            :type="verdictTagType(currentOpinion.verdict)"
            size="small"
            effect="dark"
          >
            {{ verdictLabel(currentOpinion.verdict) }}
          </el-tag>
          <span class="eqcr-opinion-current__meta">
            更新于
            {{ formatDateTime(currentOpinion.updated_at || currentOpinion.created_at) }}
          </span>
          <el-button
            type="primary"
            size="small"
            :disabled="effectiveDisabled"
            text
            @click="startEdit"
          >
            修改意见
          </el-button>
        </div>
        <div v-if="currentOpinion.comment" class="eqcr-opinion-current__comment">
          {{ currentOpinion.comment }}
        </div>
        <div v-else class="eqcr-opinion-current__empty">（未填写说明）</div>
      </template>
      <template v-else>
        <div class="eqcr-opinion-current__none">
          <span class="eqcr-opinion-current__tip">尚未录入 EQCR 意见</span>
          <el-button
            type="primary"
            size="small"
            :disabled="effectiveDisabled"
            @click="startEdit"
          >
            录入意见
          </el-button>
        </div>
      </template>
    </div>

    <!-- 编辑表单 -->
    <el-form
      v-else
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="96px"
      class="eqcr-opinion-form__form"
    >
      <el-form-item label="评议结论" prop="verdict" required>
        <el-radio-group v-model="form.verdict">
          <el-radio value="agree">同意</el-radio>
          <el-radio value="disagree">有异议</el-radio>
          <el-radio value="need_more_evidence">需更多证据</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item
        label="意见说明"
        prop="comment"
        :required="form.verdict === 'disagree'"
      >
        <el-input
          v-model="form.comment"
          type="textarea"
          :rows="3"
          :placeholder="commentPlaceholder"
          maxlength="2000"
          show-word-limit
        />
        <div v-if="form.verdict === 'disagree'" class="eqcr-opinion-hint">
          有异议时必须填写说明，供合议留痕。
        </div>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="saving" @click="onSubmit">
          保存
        </el-button>
        <el-button :disabled="saving" @click="cancelEdit">取消</el-button>
      </el-form-item>
    </el-form>

    <!-- 历史意见（折叠） -->
    <el-collapse v-if="historyOpinions.length > 0" class="eqcr-opinion-history">
      <el-collapse-item :name="1">
        <template #title>
          <span class="eqcr-opinion-history__title">
            历史意见
            <el-tag size="small" type="info" effect="plain">
              {{ historyOpinions.length }}
            </el-tag>
          </span>
        </template>
        <ul class="eqcr-opinion-history__list">
          <li
            v-for="h in historyOpinionsDesc"
            :key="h.id"
            class="eqcr-opinion-history__item"
          >
            <div class="eqcr-opinion-history__row">
              <el-tag :type="verdictTagType(h.verdict)" size="small" effect="light">
                {{ verdictLabel(h.verdict) }}
              </el-tag>
              <span class="eqcr-opinion-history__time">
                {{ formatDateTime(h.updated_at || h.created_at) }}
              </span>
            </div>
            <div v-if="h.comment" class="eqcr-opinion-history__comment">
              {{ h.comment }}
            </div>
          </li>
        </ul>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, reactive, ref, watch, type ComputedRef, type Ref } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import {
  eqcrApi,
  type EqcrOpinion,
  type EqcrOpinionDomain,
  type EqcrVerdict,
} from '@/services/eqcrService'

interface Props {
  projectId: string
  domain: EqcrOpinionDomain
  currentOpinion?: EqcrOpinion | null
  historyOpinions?: EqcrOpinion[]
  /** 置灰按钮（如 overview 返回 my_role_confirmed=false） */
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  currentOpinion: null,
  historyOpinions: () => [],
  disabled: false,
})

const emit = defineEmits<{
  (e: 'saved', opinion: EqcrOpinion): void
}>()

/** 父级 EqcrProjectView 注入的只读标志，优先级低于 props.disabled 显式传入。 */
const injectedDisabled = inject<Ref<boolean> | ComputedRef<boolean> | boolean | null>(
  'eqcrOpinionFormDisabled',
  null,
)
const effectiveDisabled = computed<boolean>(() => {
  if (props.disabled) return true
  if (injectedDisabled === null) return false
  if (typeof injectedDisabled === 'boolean') return injectedDisabled
  return !!injectedDisabled.value
})

const editing = ref(false)
const saving = ref(false)
const formRef = ref<FormInstance>()

interface FormState {
  verdict: EqcrVerdict
  comment: string
}

const form = reactive<FormState>({
  verdict: 'agree',
  comment: '',
})

const historyOpinionsDesc = computed<EqcrOpinion[]>(() => {
  return [...props.historyOpinions].reverse()
})

const commentPlaceholder = computed(() => {
  if (form.verdict === 'disagree') {
    return '必填：请说明异议原因，将留痕用于后续合议。'
  }
  if (form.verdict === 'need_more_evidence') {
    return '建议写明所需证据类型，便于项目组补充。'
  }
  return '可选：补充说明。'
})

const rules = computed<FormRules>(() => ({
  verdict: [
    { required: true, message: '请选择评议结论', trigger: 'change' },
  ],
  comment: [
    {
      validator: (_rule, value, callback) => {
        if (form.verdict === 'disagree' && !value?.trim()) {
          callback(new Error('有异议时必须填写说明'))
        } else {
          callback()
        }
      },
      trigger: 'blur',
    },
  ],
}))

watch(
  () => props.currentOpinion,
  () => {
    // 外部数据变化后若正在编辑不打断，只有非编辑态才同步回初值
    if (!editing.value) {
      resetForm()
    }
  },
)

function resetForm() {
  if (props.currentOpinion) {
    form.verdict = props.currentOpinion.verdict
    form.comment = props.currentOpinion.comment ?? ''
  } else {
    form.verdict = 'agree'
    form.comment = ''
  }
}

function startEdit() {
  if (effectiveDisabled.value) return
  resetForm()
  editing.value = true
}

function cancelEdit() {
  editing.value = false
  resetForm()
}

async function onSubmit() {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  saving.value = true
  try {
    const trimmedComment = form.comment.trim()
    const commentPayload = trimmedComment.length > 0 ? trimmedComment : null
    let saved: EqcrOpinion
    if (props.currentOpinion?.id) {
      saved = await eqcrApi.updateOpinion(props.currentOpinion.id, {
        verdict: form.verdict,
        comment: commentPayload,
      })
    } else {
      saved = await eqcrApi.createOpinion({
        project_id: props.projectId,
        domain: props.domain,
        verdict: form.verdict,
        comment: commentPayload,
      })
    }
    ElMessage.success('EQCR 意见已保存')
    editing.value = false
    emit('saved', saved)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

// ─── 辅助 ──────────────────────────────────────────────────────────────────

const VERDICT_META: Record<
  EqcrVerdict,
  { label: string; type: 'success' | 'danger' | 'warning' }
> = {
  agree: { label: '同意', type: 'success' },
  disagree: { label: '有异议', type: 'danger' },
  need_more_evidence: { label: '需更多证据', type: 'warning' },
}

function verdictLabel(v: EqcrVerdict): string {
  return VERDICT_META[v]?.label ?? v
}
function verdictTagType(v: EqcrVerdict): 'success' | 'danger' | 'warning' {
  return VERDICT_META[v]?.type ?? 'warning'
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}
</script>

<style scoped>
.eqcr-opinion-form {
  padding: 12px 0 4px;
}

.eqcr-opinion-current {
  padding: 12px 14px;
  background: var(--gt-color-bg-soft, #f5f7fa);
  border-radius: var(--gt-radius-sm, 4px);
}
.eqcr-opinion-current__header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.eqcr-opinion-current__meta {
  color: var(--gt-color-text-tertiary, #909399);
  font-size: var(--gt-font-size-xs, 12px);
}
.eqcr-opinion-current__header .el-button {
  margin-left: auto;
}
.eqcr-opinion-current__comment {
  margin-top: 8px;
  white-space: pre-wrap;
  color: var(--gt-color-text, #303133);
  line-height: 1.55;
}
.eqcr-opinion-current__empty {
  margin-top: 8px;
  color: var(--gt-color-text-tertiary, #909399);
  font-size: var(--gt-font-size-xs, 12px);
}
.eqcr-opinion-current__none {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.eqcr-opinion-current__tip {
  color: var(--gt-color-text-secondary, #606266);
}

.eqcr-opinion-form__form {
  padding: 8px 0;
}
.eqcr-opinion-hint {
  color: var(--el-color-danger, #f56c6c);
  font-size: var(--gt-font-size-xs, 12px);
  margin-top: 4px;
}

.eqcr-opinion-history {
  margin-top: 12px;
  border-top: 1px dashed var(--gt-color-border-light, #ebeef5);
  padding-top: 4px;
}
.eqcr-opinion-history__title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--gt-color-text-secondary, #606266);
}
.eqcr-opinion-history__list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.eqcr-opinion-history__item {
  padding: 8px 0;
  border-bottom: 1px dashed var(--gt-color-border-light, #ebeef5);
}
.eqcr-opinion-history__item:last-child {
  border-bottom: none;
}
.eqcr-opinion-history__row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.eqcr-opinion-history__time {
  color: var(--gt-color-text-tertiary, #909399);
  font-size: var(--gt-font-size-xs, 12px);
}
.eqcr-opinion-history__comment {
  margin-top: 4px;
  color: var(--gt-color-text, #303133);
  white-space: pre-wrap;
  line-height: 1.5;
  font-size: var(--gt-font-size-sm, 13px);
}
</style>
