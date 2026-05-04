<template>
  <Transition name="gt-slide-up">
    <div v-if="stats && stats.count > 0" class="gt-selection-bar">
      <div class="gt-selection-bar-item">
        <span class="gt-selection-bar-label">选中</span>
        <span class="gt-selection-bar-value">{{ stats.count }} 格</span>
      </div>
      <template v-if="stats.numCount > 0">
        <div class="gt-selection-bar-item">
          <span class="gt-selection-bar-label">求和</span>
          <span class="gt-selection-bar-value">{{ fmtAmount(stats.sum) }}</span>
        </div>
        <div class="gt-selection-bar-item">
          <span class="gt-selection-bar-label">平均</span>
          <span class="gt-selection-bar-value">{{ fmtAmount(stats.avg) }}</span>
        </div>
        <div v-if="stats.numCount > 1" class="gt-selection-bar-item">
          <span class="gt-selection-bar-label">最大</span>
          <span class="gt-selection-bar-value">{{ fmtAmount(stats.max) }}</span>
        </div>
        <div v-if="stats.numCount > 1" class="gt-selection-bar-item">
          <span class="gt-selection-bar-label">最小</span>
          <span class="gt-selection-bar-value">{{ fmtAmount(stats.min) }}</span>
        </div>
        <div v-if="stats.numCount !== stats.count" class="gt-selection-bar-item">
          <span class="gt-selection-bar-label">数值</span>
          <span class="gt-selection-bar-value">{{ stats.numCount }} 格</span>
        </div>
      </template>
      <span class="gt-selection-bar-hint">右键可复制选中区域 · Shift+点击范围选 · Ctrl+F 搜索</span>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { fmtAmount } from '@/utils/formatters'

defineProps<{
  stats: { count: number; numCount: number; sum: number; avg: number; max: number; min: number } | null
}>()
</script>

<style scoped>
.gt-slide-up-enter-active { transition: all 0.2s ease; }
.gt-slide-up-leave-active { transition: all 0.15s ease; }
.gt-slide-up-enter-from { opacity: 0; transform: translateY(8px); }
.gt-slide-up-leave-to { opacity: 0; transform: translateY(4px); }
.gt-selection-bar-hint {
  margin-left: auto;
  font-size: 11px;
  color: #b0a4c8;
  white-space: nowrap;
}
</style>
