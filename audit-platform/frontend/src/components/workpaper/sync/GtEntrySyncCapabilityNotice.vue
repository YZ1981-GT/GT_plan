<template>
  <span
    v-if="props.entryId && presentation.noticeKind !== 'none'"
    class="entry-sync-notice"
    :data-entry-sync-notice="props.entryId"
    :data-entry-sync-state="loadState"
  >
    <el-tag size="small" :type="tagType" effect="plain">
      {{ presentation.noticeLabel }}
    </el-tag>
    <span class="entry-sync-notice__summary">{{ presentation.noticeSummary }}</span>
    <el-tooltip placement="bottom-start" effect="dark" :show-after="120">
      <template #content>
        <div class="entry-sync-notice__reason">{{ presentation.noticeReason }}</div>
      </template>
      <span class="entry-sync-notice__detail" tabindex="0">查看原因</span>
    </el-tooltip>
    <el-button
      v-if="loadState === 'error'"
      size="small"
      text
      type="primary"
      @click="() => refresh()"
    >
      重试
    </el-button>
  </span>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import { WorkpaperRuntimeContextKey } from '../composables/useWorkpaperScaffold'
import { useEntrySyncReadiness } from './useEntrySyncReadiness'

const props = defineProps<{
  entryId: string
  projectId?: string
  wpId?: string
}>()

const runtime = inject(WorkpaperRuntimeContextKey, null)
const projectId = computed(() => props.projectId || runtime?.projectId.value || '')
const wpId = computed(() => props.wpId || runtime?.wpId.value || '')
const entryId = computed(() => props.entryId)
const { presentation, loadState, refresh } = useEntrySyncReadiness({
  projectId,
  wpId,
  entryId,
})

const tagType = computed(() => {
  if (presentation.value.noticeKind === 'danger') return 'danger'
  if (presentation.value.noticeKind === 'warning') return 'warning'
  return 'info'
})
</script>

<style scoped>
.entry-sync-notice {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  flex-wrap: wrap;
}
.entry-sync-notice__summary {
  font-size: 12px;
  color: var(--el-color-warning-dark-2);
}
.entry-sync-notice__detail {
  cursor: help;
  font-size: 12px;
  color: var(--el-color-primary);
  border-bottom: 1px dashed currentColor;
}
.entry-sync-notice__reason {
  max-width: min(420px, 80vw);
  line-height: 1.6;
}
</style>
