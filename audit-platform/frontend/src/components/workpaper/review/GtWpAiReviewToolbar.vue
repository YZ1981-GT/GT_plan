<template>
  <span v-if="canStartAiReview" class="wp-ai-review-toolbar">
    <el-button
      v-if="sheetName"
      size="small"
      :loading="reviewing"
      @click="onCurrentSheetAiReview"
    >
      本页AI复核
    </el-button>
    <el-button size="small" @click="reviewDialogVisible = true">
      批量AI复核
    </el-button>

    <el-dialog
      v-model="reviewDialogVisible"
      :title="`${wpCodePrefix} ${label} AI 复核`"
      width="900px"
      :destroy-on-close="false"
      append-to-body
    >
      <ReviewPanel
        ref="reviewPanelRef"
        :project-id="projectId"
        :wp-code-prefix="wpCodePrefix"
        :year="resolvedYear"
        @navigate-sheet="onReviewNavigateSheet"
      />
    </el-dialog>
  </span>
</template>

<script setup lang="ts">
/**
 * GtWpAiReviewToolbar — 可复用 AI 底稿复核工具条（本页复核 + 批量复核）
 *
 * 参照 D2 的 AI 复核范式抽出的通用组件，供 K/N 等循环主入口一行接入。
 * 后端 review 端点已按 wp_code 注入跨底稿勾稽上下文（cycle_review_context），
 * 使 AI 对照已知勾稽数字判断，复核更准确精细。
 */
import { computed, defineAsyncComponent, nextTick, ref } from 'vue'
import { usePermissionMatrix } from '@/composables/usePermissionMatrix'

const ReviewPanel = defineAsyncComponent(() => import('./AiReviewPanel.vue'))

const props = defineProps<{
  /** 当前底稿 wp_id（用于本页复核） */
  wpId: string
  projectId: string
  /** 底稿编码前缀，如 "K9"、"N2"（用于批量复核） */
  wpCodePrefix: string
  /** 当前 sheet 名称；有值才显示「本页AI复核」 */
  sheetName?: string
  /** 审计年度 */
  year?: number
  /** 弹窗标题科目名（可选，如「管理费用」） */
  label?: string
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const { currentRole } = usePermissionMatrix()
const canStartAiReview = computed(() =>
  ['manager', 'partner', 'qc', 'admin'].includes(currentRole.value),
)

const resolvedYear = computed(() => props.year || new Date().getFullYear())

const reviewDialogVisible = ref(false)
const reviewing = ref(false)
const reviewPanelRef = ref<{
  reviewCurrentSheet: (wpId: string, sheetName: string) => Promise<unknown>
} | null>(null)

async function onCurrentSheetAiReview(): Promise<void> {
  if (!props.sheetName) return
  reviewDialogVisible.value = true
  reviewing.value = true
  try {
    await nextTick()
    await reviewPanelRef.value?.reviewCurrentSheet(props.wpId, props.sheetName)
  } finally {
    reviewing.value = false
  }
}

function onReviewNavigateSheet(sheetName: string): void {
  reviewDialogVisible.value = false
  emit('navigate-sheet', sheetName)
}
</script>

<style scoped>
.wp-ai-review-toolbar {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
</style>
