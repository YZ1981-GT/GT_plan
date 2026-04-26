<template>
  <slot v-if="!hasError" />
  <div v-else class="gt-error-boundary">
    <div class="gt-error-icon">⚠️</div>
    <h3>页面渲染出错</h3>
    <p class="gt-error-msg">{{ errorMessage }}</p>
    <div class="gt-error-actions">
      <el-button type="primary" size="small" @click="retry">重试</el-button>
      <el-button size="small" @click="goHome">返回首页</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const hasError = ref(false)
const errorMessage = ref('')

onErrorCaptured((err: Error) => {
  hasError.value = true
  errorMessage.value = err.message || '未知错误'
  console.error('[ErrorBoundary]', err)
  return false // 阻止错误继续传播
})

function retry() {
  hasError.value = false
  errorMessage.value = ''
}

function goHome() {
  hasError.value = false
  router.push('/')
}
</script>

<style scoped>
.gt-error-boundary {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  min-height: 300px; padding: var(--gt-space-10); text-align: center;
}
.gt-error-icon { font-size: 48px; margin-bottom: var(--gt-space-4); }
.gt-error-boundary h3 { font-size: var(--gt-font-size-xl); color: var(--gt-color-text); margin-bottom: var(--gt-space-2); }
.gt-error-msg { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-tertiary); margin-bottom: var(--gt-space-5); max-width: 400px; }
.gt-error-actions { display: flex; gap: var(--gt-space-2); }
</style>
