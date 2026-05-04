<template>
  <!-- 批注 hover 气泡：鼠标悬停在有批注的单元格上时自动显示 -->
  <el-tooltip
    v-if="comment"
    :content="tooltipContent"
    placement="top"
    :show-after="300"
    :hide-after="0"
    effect="light"
    popper-class="gt-comment-tooltip"
  >
    <slot />
  </el-tooltip>
  <slot v-else />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { CellComment } from '@/composables/useCellComments'

const props = defineProps<{
  comment?: CellComment | null
}>()

const tooltipContent = computed(() => {
  if (!props.comment) return ''
  const parts: string[] = []
  if (props.comment.comment) parts.push(props.comment.comment)
  if (props.comment.comment_type === 'review' && props.comment.status === 'reviewed') {
    parts.push('✓ 已复核')
  }
  if (props.comment.created_at) {
    const d = new Date(props.comment.created_at)
    if (!isNaN(d.getTime())) parts.push(d.toLocaleString('zh-CN'))
  }
  return parts.join(' · ')
})
</script>

<style>
/* 非 scoped，因为 popper 渲染在 body 上 */
.gt-comment-tooltip {
  max-width: 300px !important;
  font-size: 12px !important;
  line-height: 1.6 !important;
  border: 1px solid #FFC23D !important;
  background: #FFFDF5 !important;
}
.gt-comment-tooltip .el-tooltip__arrow::before {
  border-color: #FFC23D !important;
  background: #FFFDF5 !important;
}
</style>
