<script setup lang="ts">
/**
 * GtWpReviewRail — legacy host mount.
 *
 * Task 12: when WorkpaperCapabilityShell is active, this component renders
 * nothing (shell owns review trigger/placement). Placement CSS is shell-owned.
 */
import { inject, computed, type Ref } from 'vue'
import { ChatDotRound } from '@element-plus/icons-vue'
import GtReviewDot from './GtReviewDot.vue'
import type { WorkpaperOpenReviewFn } from './composables/useWorkpaperReviewProvide'
import { WORKPAPER_SHELL_ACTIVE_KEY } from '@/shell/formula/dshAssistBridge'

const props = defineProps<{
  sectionId: string
  sectionLabel?: string
  /** @deprecated Task 12 — shell owns vertical placement; ignored. */
  top?: string
}>()

const openReviewDialog = inject<WorkpaperOpenReviewFn | null>('openReviewDialog', null)
const shellActive = inject<Ref<boolean> | undefined>(WORKPAPER_SHELL_ACTIVE_KEY, undefined)

const suppressedByShell = computed(() => shellActive?.value === true)
const label = computed(() => props.sectionLabel ?? props.sectionId)
const visible = computed(() => Boolean(openReviewDialog) && !suppressedByShell.value)

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
    v-if="visible"
    class="gt-wp-review-rail"
    role="button"
    tabindex="0"
    aria-label="底稿复核"
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
/* Task 12: flow-only styles for pre-shell hosts; shell owns absolute placement. */
.gt-wp-review-rail {
  writing-mode: vertical-rl;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 12px 6px;
  background: #fff7e6;
  border: 1px solid #ffd591;
  border-right: none;
  border-radius: 8px 0 0 8px;
  cursor: pointer;
  color: #d46b08;
  font-size: 12px;
  font-weight: 600;
}
.gt-wp-review-rail:hover {
  background: #ffe7ba;
}
.gt-wp-review-rail:focus-visible {
  outline: 2px solid #d46b08;
  outline-offset: 2px;
}
.gt-wp-review-rail__text {
  letter-spacing: 2px;
}
.gt-wp-review-rail :deep(.gt-review-dot) {
  writing-mode: horizontal-tb;
}
</style>
