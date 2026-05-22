<!--
  统一空状态组件 (G-5)

  三态统一：loading（骨架屏）/ empty（空状态）/ error（错误+重试）
  替代裸 el-empty 使用，确保全平台空状态体验一致。

  使用方式（推荐 status 模式）：
    <LoadingState status="loading" />
    <LoadingState status="empty" message="暂无审计底稿" />
    <LoadingState status="error" message="网络异常" :on-retry="handleRetry" />

  也兼容旧的 boolean props 模式（向后兼容）：
    <LoadingState :loading="true" :skeleton="true" />
    <LoadingState :empty="true" empty-text="暂无数据" />
-->
<template>
  <div class="loading-state">
    <!-- Status 模式 -->
    <template v-if="status">
      <el-skeleton v-if="status === 'loading'" :rows="rows" animated />
      <el-empty v-else-if="status === 'empty'" :description="message || emptyText">
        <slot name="empty-extra" />
      </el-empty>
      <div v-else-if="status === 'error'" class="error-wrap">
        <el-alert type="error" :title="message || errorText" show-icon :closable="false" />
        <el-button v-if="onRetry" type="primary" size="small" class="retry-btn" @click="onRetry">
          重试
        </el-button>
      </div>
    </template>
    <!-- 兼容旧 boolean props 模式 -->
    <template v-else>
      <el-skeleton v-if="loading && skeleton" :rows="rows" animated />
      <div v-else-if="loading" class="spinner-wrap">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <span v-if="text" class="loading-text">{{ text }}</span>
      </div>
      <el-empty v-else-if="empty" :description="emptyText" />
      <el-alert v-else-if="error" type="error" :title="errorText" show-icon :closable="false" />
      <slot v-else />
    </template>
  </div>
</template>

<script setup lang="ts">
import { Loading } from '@element-plus/icons-vue'

withDefaults(defineProps<{
  // 新 status 模式（推荐）
  status?: 'loading' | 'empty' | 'error' | null
  message?: string
  onRetry?: (() => void) | null
  // 兼容旧 boolean props 模式
  loading?: boolean
  skeleton?: boolean
  rows?: number
  text?: string
  empty?: boolean
  emptyText?: string
  error?: boolean
  errorText?: string
}>(), {
  status: null,
  message: '',
  onRetry: null,
  loading: false,
  skeleton: true,
  rows: 3,
  text: '',
  empty: false,
  emptyText: '暂无数据',
  error: false,
  errorText: '加载失败',
})
</script>

<style scoped>
.spinner-wrap { display: flex; flex-direction: column; align-items: center; padding: 32px; gap: 8px; }
.loading-text { color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-sm); }
.error-wrap { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 24px; }
.retry-btn { margin-top: 4px; }
</style>
