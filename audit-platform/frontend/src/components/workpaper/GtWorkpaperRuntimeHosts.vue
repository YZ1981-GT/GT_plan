<script setup lang="ts">
/**
 * Runtime Boundary 的无布局 Host 集合。
 *
 * 只消费 Scaffold 已提供的能力：复核 Host 读取 REVIEW_DIALOG_KEY；版本 Host
 * 回填 versionToolbar.versionTrailRef，使任意后代调用 openVersionHistory 都能
 * 打开当前底稿的真实版本抽屉。
 *
 * Requirements: 2.2, 7.1, 7.3
 */
import { inject, onUnmounted, shallowRef, watch } from 'vue'
import GtWpReviewDialogHost from './GtWpReviewDialogHost.vue'
import GtWpVersionTrail from './version-trail/GtWpVersionTrail.vue'
import type { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'

type VersionToolbar = ReturnType<typeof useWorkpaperVersionToolbar>
type VersionTrailHost = { openDrawer: () => void }

const props = defineProps<{
  wpId: string
  projectId: string
}>()

const emit = defineEmits<{
  'rollback-completed': []
}>()

const versionToolbar = inject<VersionToolbar | null>('versionToolbar', null)
const versionTrailHost = shallowRef<VersionTrailHost | null>(null)

watch(versionTrailHost, (host) => {
  if (versionToolbar) versionToolbar.versionTrailRef.value = host
}, { flush: 'sync' })

onUnmounted(() => {
  if (versionToolbar) versionToolbar.versionTrailRef.value = null
})
</script>

<template>
  <GtWpVersionTrail
    v-if="versionToolbar && props.wpId && props.projectId"
    ref="versionTrailHost"
    :workpaper-id="props.wpId"
    :project-id="props.projectId"
    @rollback-completed="emit('rollback-completed')"
  />
  <GtWpReviewDialogHost />
</template>
