<script setup lang="ts">
/**
 * 复核对话触发按钮 + 蓝/红点
 */
import { inject } from 'vue'
import GtReviewDot from './GtReviewDot.vue'

const props = defineProps<{
  sectionId: string
  label?: string
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

function onClick(): void {
  openReviewDialog?.(props.sectionId)
}
</script>

<template>
  <el-button v-if="openReviewDialog" size="small" text @click="onClick">
    {{ label ?? '💬' }}<GtReviewDot :section-id="sectionId" />
  </el-button>
</template>
