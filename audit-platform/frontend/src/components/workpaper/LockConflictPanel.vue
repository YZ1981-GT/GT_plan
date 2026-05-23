<template>
  <div class="lock-conflict-overlay">
    <div class="lock-conflict-panel">
      <div class="lock-conflict-icon">🔒</div>
      <h3 class="lock-conflict-title">底稿正在被编辑</h3>
      <p class="lock-conflict-desc">
        <strong>{{ info.locked_by_name }}</strong> 正在编辑此底稿
        <span class="lock-conflict-time">（{{ relativeTime }}）</span>
      </p>
      <div class="lock-conflict-actions">
        <el-button @click="$emit('view-readonly')" plain>
          👁️ 只读查看
        </el-button>
        <el-button @click="$emit('force-acquire')" type="warning" plain>
          ✋ 请求接管
        </el-button>
        <el-button @click="$emit('go-back')">
          ↩️ 稍后再来
        </el-button>
      </div>
      <p class="lock-conflict-hint">
        接管后对方将收到通知，其未保存的修改会自动保存
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { LockConflictInfo } from '@/composables/useEditingLock'

const props = defineProps<{
  info: LockConflictInfo
}>()

defineEmits<{
  'view-readonly': []
  'force-acquire': []
  'go-back': []
}>()

const relativeTime = computed(() => {
  if (!props.info.acquired_at) return '刚刚'
  const diff = Date.now() - new Date(props.info.acquired_at).getTime()
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return '刚刚开始编辑'
  if (minutes < 60) return `${minutes} 分钟前开始编辑`
  const hours = Math.floor(minutes / 60)
  return `${hours} 小时前开始编辑`
})
</script>

<style scoped>
.lock-conflict-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.lock-conflict-panel {
  background: #fff;
  border-radius: 12px;
  padding: 32px 40px;
  text-align: center;
  max-width: 420px;
  box-shadow: 0 8px 32px rgba(75, 45, 119, 0.15);
}

.lock-conflict-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.lock-conflict-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
  margin: 0 0 8px;
}

.lock-conflict-desc {
  font-size: 14px;
  color: var(--gt-color-text-regular, #606266);
  margin: 0 0 24px;
}

.lock-conflict-time {
  color: var(--gt-color-text-secondary, #909399);
  font-size: 12px;
}

.lock-conflict-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  margin-bottom: 16px;
}

.lock-conflict-hint {
  font-size: 12px;
  color: var(--gt-color-text-secondary, #909399);
  margin: 0;
}
</style>
