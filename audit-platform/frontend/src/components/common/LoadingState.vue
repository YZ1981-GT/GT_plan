<template>
  <div class="loading-state">
    <el-skeleton v-if="loading && skeleton" :rows="rows" animated />
    <div v-else-if="loading" class="spinner-wrap">
      <el-icon class="is-loading" :size="32"><Loading /></el-icon>
      <span v-if="text" class="loading-text">{{ text }}</span>
    </div>
    <el-empty v-else-if="empty" :description="emptyText" />
    <el-alert v-else-if="error" type="error" :title="errorText" show-icon :closable="false" />
    <slot v-else />
  </div>
</template>

<script setup lang="ts">
import { Loading } from '@element-plus/icons-vue'

withDefaults(defineProps<{
  loading?: boolean
  skeleton?: boolean
  rows?: number
  text?: string
  empty?: boolean
  emptyText?: string
  error?: boolean
  errorText?: string
}>(), {
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
</style>
