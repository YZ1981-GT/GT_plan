<script setup lang="ts">
/**
 * ChatQuotaCountdown — AI 对话限流倒计时组件
 *
 * 当 `chatRunState.retryAfter` 不为 null 且 > 0 时显示中文倒计时横幅，
 * 倒计时结束后自动隐藏并清除限流状态。
 *
 * Feature: dsh-agent-panel-integration / Task 12
 * Validates: Requirements 13.6（限流触发后前端显示中文倒计时并保留未发送草稿）
 */
import { ref, watch, onBeforeUnmount, computed } from 'vue'
import { useChatRunStateStore } from '@/stores/chatRunState'

const runStore = useChatRunStateStore()

const countdown = ref(0)
let timer: ReturnType<typeof setInterval> | null = null

const visible = computed(() => countdown.value > 0)

function startCountdown(seconds: number) {
  stopCountdown()
  countdown.value = Math.max(1, Math.ceil(seconds))
  timer = setInterval(() => {
    countdown.value--
    if (countdown.value <= 0) {
      stopCountdown()
      // 倒计时结束，清除限流态
      runStore.retryAfter = null
      runStore.quotaRemaining = null
      if (runStore.errorCode === 'rate_limited') {
        runStore.phase = 'idle'
        runStore.errorCode = null
        runStore.errorMessage = null
      }
    }
  }, 1000)
}

function stopCountdown() {
  if (timer !== null) {
    clearInterval(timer)
    timer = null
  }
}

// 响应 retryAfter 变化
watch(
  () => runStore.retryAfter,
  (val) => {
    if (val && val > 0) {
      startCountdown(val)
    } else {
      stopCountdown()
      countdown.value = 0
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  stopCountdown()
})
</script>

<template>
  <div
    v-if="visible"
    class="chat-quota-countdown"
    role="alert"
    aria-live="polite"
  >
    <span class="countdown-icon">⏳</span>
    <span class="countdown-text">
      请求过于频繁，请等待 <strong>{{ countdown }}</strong> 秒后再试
    </span>
  </div>
</template>

<style scoped>
.chat-quota-countdown {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  margin: 8px 0;
  border-radius: 6px;
  background-color: var(--el-color-warning-light-9, #fdf6ec);
  border: 1px solid var(--el-color-warning-light-5, #f5dab1);
  color: var(--el-color-warning-dark-2, #a77730);
  font-size: 13px;
  line-height: 1.4;
}

.countdown-icon {
  flex-shrink: 0;
  font-size: 16px;
}

.countdown-text strong {
  font-variant-numeric: tabular-nums;
  min-width: 1.5em;
  display: inline-block;
  text-align: center;
}
</style>
