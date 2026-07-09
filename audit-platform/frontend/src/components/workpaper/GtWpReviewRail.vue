<script setup lang="ts">
/**
 * GtWpReviewRail — 右侧「底稿复核」竖向入口（参照 A17 复核面板 + 编制指导触发条）
 */
import { inject, computed } from 'vue'
import { ChatDotRound } from '@element-plus/icons-vue'
import GtReviewDot from './GtReviewDot.vue'
import type { WorkpaperOpenReviewFn } from './composables/useWorkpaperReviewProvide'

const props = defineProps<{
  sectionId: string
  sectionLabel?: string
  /** 相对视口垂直位置，避免与「编制指导」重叠 */
  top?: string
}>()

const openReviewDialog = inject<WorkpaperOpenReviewFn | null>('openReviewDialog', null)

const label = computed(() => props.sectionLabel ?? props.sectionId)

function onOpen(): void {
  if (!openReviewDialog) return
  openReviewDialog({
    sectionId: props.sectionId,
    sectionLabel: label.value,
  })
}
</script>

<template>
  <div
    v-if="openReviewDialog"
    class="gt-wp-review-rail"
    :style="{ top: top ?? 'calc(50% - 72px)' }"
    role="button"
    tabindex="0"
    title="打开底稿复核对话"
    @click="onOpen"
    @keydown.enter="onOpen"
  >
    <el-icon :size="16"><ChatDotRound /></el-icon>
    <span class="gt-wp-review-rail__text">底稿复核</span>
    <GtReviewDot :section-id="sectionId" />
  </div>
</template>

<style scoped>
.gt-wp-review-rail {
  position: fixed;
  right: 0;
  transform: translateY(-50%);
  writing-mode: vertical-rl;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px 6px;
  background: #fff7e6;
  border: 1px solid #ffd591;
  border-right: none;
  border-radius: 8px 0 0 8px;
  cursor: pointer;
  z-index: 110;
  transition: background 0.2s, box-shadow 0.2s;
  color: #d46b08;
  font-size: 12px;
  font-weight: 600;
  box-shadow: -2px 0 8px rgba(212, 107, 8, 0.08);
}
.gt-wp-review-rail:hover {
  background: #ffe7ba;
  box-shadow: -2px 0 12px rgba(212, 107, 8, 0.15);
}
.gt-wp-review-rail__text {
  letter-spacing: 2px;
}
.gt-wp-review-rail :deep(.gt-review-dot) {
  writing-mode: horizontal-tb;
}
</style>
