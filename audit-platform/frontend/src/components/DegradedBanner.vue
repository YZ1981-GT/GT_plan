<script setup lang="ts">
/**
 * DegradedBanner — 级联 degraded 状态黄色横幅 [enterprise-linkage 4.8]
 *
 * 订阅 SSE `linkage.cascade_degraded` 事件，
 * 显示 el-alert type="warning" 提示"数据可能未同步"。
 *
 * Validates: Requirements 7.5
 */
import { ref, onMounted, onUnmounted } from 'vue'
import { eventBus, type SyncEventPayload } from '@/utils/eventBus'

const isDegraded = ref(false)
let dismissTimer: ReturnType<typeof setTimeout> | null = null

function handleSSE(payload: SyncEventPayload) {
  if (payload.event_type === 'linkage.cascade_degraded') {
    isDegraded.value = true
    // Auto-dismiss after 60 seconds
    if (dismissTimer) clearTimeout(dismissTimer)
    dismissTimer = setTimeout(() => {
      isDegraded.value = false
    }, 60_000)
  }
  // Clear degraded state when cascade completes successfully
  if (
    payload.event_type === 'trial_balance.updated' ||
    payload.event_type === 'adjustment.batch_committed'
  ) {
    isDegraded.value = false
    if (dismissTimer) {
      clearTimeout(dismissTimer)
      dismissTimer = null
    }
  }
}

function handleClose() {
  isDegraded.value = false
  if (dismissTimer) {
    clearTimeout(dismissTimer)
    dismissTimer = null
  }
}

onMounted(() => {
  eventBus.on('sse:sync-event', handleSSE)
})

onUnmounted(() => {
  eventBus.off('sse:sync-event', handleSSE)
  if (dismissTimer) {
    clearTimeout(dismissTimer)
    dismissTimer = null
  }
})
</script>

<template>
  <el-alert
    v-if="isDegraded"
    type="warning"
    :closable="true"
    show-icon
    class="degraded-banner"
    @close="handleClose"
  >
    <template #title>
      数据可能未同步
    </template>
    <template #default>
      级联更新过程中出现异常，部分数据可能未及时更新。请稍后刷新页面确认最新状态。
    </template>
  </el-alert>
</template>

<style scoped>
.degraded-banner {
  position: sticky;
  top: 0;
  z-index: 100;
  border-radius: 0;
}
</style>
