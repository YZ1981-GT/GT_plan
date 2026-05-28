<template>
  <!-- Task 2.4: Review mark dialog -->
  <el-dialog :model-value="visible" title="✓ 标记复核" width="400" append-to-body @update:model-value="$emit('update:visible', $event)">
    <el-form ref="reviewMarkFormRef" :model="reviewMarkFormModel" :rules="reviewMarkRules" label-width="70px">
      <el-form-item label="单元格">
        <span>{{ cell.sheet }}!{{ cell.cellRef }}</span>
      </el-form-item>
      <el-form-item label="状态" prop="status">
        <el-radio-group v-model="reviewDialogStatus">
          <el-radio value="reviewed">已复核</el-radio>
          <el-radio value="pending">待确认</el-radio>
          <el-radio value="questioned">有疑问</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="备注" prop="comment">
        <el-input v-model="reviewDialogComment" type="textarea" :rows="3" placeholder="可选：输入复核意见，有疑问时必填" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <el-button type="primary" @click="onMarkReview" :loading="reviewMarkSubmitting">确认标记</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, toRef } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { useReviewMarks, type ReviewStatus } from '@/composables/useReviewMarks'
import { useFormSubmit } from '@/composables/useFormSubmit'
import { eventBus } from '@/utils/eventBus'

const props = defineProps<{
  projectId: string
  wpId: string
  visible: boolean
  cell: { sheet: string; cellRef: string }
}>()

const emit = defineEmits<{
  'update:visible': [val: boolean]
  'marked': []
}>()

// ─── Review dialog state ─────────────────────────────────────────────────────
const reviewDialogComment = ref('')
const reviewDialogStatus = ref<ReviewStatus>('reviewed')

// ─── Form validation ─────────────────────────────────────────────────────────
const reviewMarkFormRef = ref<FormInstance>()
const reviewMarkFormModel = computed(() => ({
  status: reviewDialogStatus.value,
  comment: reviewDialogComment.value,
}))
const reviewMarkRules = computed<FormRules>(() => ({
  status: [{ required: true, message: '请选择复核状态', trigger: 'change' }],
  comment: [
    {
      validator: (_rule: unknown, value: string | undefined, callback: (err?: Error) => void) => {
        if (reviewDialogStatus.value === 'questioned' && !(value && value.trim())) {
          callback(new Error('「有疑问」状态下必须填写备注'))
          return
        }
        callback()
      },
      trigger: 'blur',
    },
  ],
}))
const { submit: submitReviewMark, submitting: reviewMarkSubmitting } = useFormSubmit(reviewMarkFormRef)

// ─── Review marks composable ─────────────────────────────────────────────────
const reviewMarksComposable = useReviewMarks(toRef(props, 'projectId'))

// ─── Submit handler ──────────────────────────────────────────────────────────
async function onMarkReview() {
  if (!props.visible) return
  const { sheet, cellRef } = props.cell
  if (!sheet || !cellRef || !props.wpId) return

  await submitReviewMark(async () => {
    const mark = await reviewMarksComposable.createReviewMark(
      props.wpId,
      sheet,
      cellRef,
      reviewDialogStatus.value,
      reviewDialogComment.value,
    )
    if (mark) {
      ElMessage.success('复核标记已保存')
      eventBus.emit('review-mark:changed', { projectId: props.projectId, wpId: props.wpId })
    }
    emit('update:visible', false)
    emit('marked')
    reviewDialogComment.value = ''
  })
}
</script>
