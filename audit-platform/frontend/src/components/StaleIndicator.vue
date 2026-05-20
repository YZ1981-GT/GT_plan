<script setup lang="ts">
/**
 * StaleIndicator — 统一 stale badge 组件（黄色圆点 + tooltip）
 *
 * Sprint 4 Task 4.4
 * 用于 WorkpaperList / ReportView / DisclosureEditor / TrialBalance / Adjustments
 * 显示数据过期状态的视觉指示器。
 */
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  stale: boolean
  tooltip?: string
  size?: 'small' | 'default'
}>(), {
  tooltip: '数据可能已过期，建议刷新',
  size: 'default',
})

const dotSize = computed(() => props.size === 'small' ? '6px' : '8px')
</script>

<template>
  <el-tooltip
    v-if="stale"
    :content="tooltip"
    placement="top"
    :show-after="300"
  >
    <span
      class="gt-stale-indicator"
      :class="[`gt-stale-indicator--${size}`]"
      aria-label="数据过期"
    >
      <span
        class="gt-stale-indicator__dot"
        :style="{ width: dotSize, height: dotSize }"
      />
    </span>
  </el-tooltip>
</template>

<style scoped>
.gt-stale-indicator {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: help;
  padding: 2px;
}

.gt-stale-indicator__dot {
  display: inline-block;
  border-radius: 50%;
  background-color: var(--gt-color-warning, #e6a23c);
  flex-shrink: 0;
  animation: gt-stale-pulse 2s ease-in-out infinite;
}

.gt-stale-indicator--small .gt-stale-indicator__dot {
  width: 6px;
  height: 6px;
}

@keyframes gt-stale-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>
