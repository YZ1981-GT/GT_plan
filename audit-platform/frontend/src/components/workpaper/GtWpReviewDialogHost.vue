<script setup lang="ts">
/**
 * GtWpReviewDialogHost — 挂载右侧复核对话抽屉（与 useWorkpaperReviewProvide 配对）
 *
 * 须在调用 useWorkpaperReviewProvide / useReviewDialogProvider 的父组件子树内使用。
 */
import { defineAsyncComponent } from 'vue'
import { useReviewDialogInject } from '@/composables/useReviewDialogProvider'

const GtReviewDialog = defineAsyncComponent(
  () => import('@/components/collaboration/GtReviewDialog.vue'),
)

const { isOpen, activationParams, closeReviewDialog } = useReviewDialogInject()
</script>

<template>
  <GtReviewDialog
    v-if="isOpen && activationParams"
    :key="activationParams.sectionId"
    v-bind="activationParams"
    @closed="closeReviewDialog"
  />
</template>
