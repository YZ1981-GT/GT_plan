<!--
  GtPageHeader — 通用页面横幅组件 [R5.4]
  紫色渐变横幅，统一各模块的页面头部样式。
  包含返回按钮、标题、信息栏插槽（GtInfoBar）、操作按钮插槽（GtToolbar）。
  支持 showSyncStatus prop 显示数据同步状态指示器（监听 sse:sync-event / sse:sync-failed）。
  支持 backMode prop：'route'（默认，触发 back 事件）| 'history'（调用 router.back()）。

  用法：
    <GtPageHeader title="试算表" :show-sync-status="true" @back="router.push('/projects')">
      <GtInfoBar ... />
      <template #actions>
        <GtToolbar ... />
      </template>
    </GtPageHeader>
-->
<template>
  <div class="gt-page-header">
    <div class="gt-page-header__row1">
      <el-button
        v-if="showBack"
        text
        class="gt-page-header__back"
        @click="onBack"
      >← 返回</el-button>
      <h2 class="gt-page-header__title">{{ title }}</h2>
      <!-- 默认插槽：放 GtInfoBar -->
      <slot />
      <!-- 同步状态指示器 -->
      <div class="gt-page-header__sync-status" v-if="showSyncStatus">
        <el-tooltip :content="syncTooltip" placement="bottom">
          <span v-if="syncStatus === 'syncing'" class="gt-sync-dot gt-sync-dot--syncing">⏳ 同步中</span>
          <span v-else-if="syncStatus === 'stale'" class="gt-sync-dot gt-sync-dot--stale">🕐 数据可能过时</span>
          <span v-else class="gt-sync-dot gt-sync-dot--ok">✓ 已更新</span>
        </el-tooltip>
      </div>
    </div>
    <!-- actions 插槽：放 GtToolbar -->
    <slot name="actions" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { eventBus } from '@/utils/eventBus'

const props = withDefaults(defineProps<{
  /** 页面标题 */
  title: string
  /** 是否显示返回按钮 */
  showBack?: boolean
  /** 是否显示数据同步状态指示器 */
  showSyncStatus?: boolean
  /** 返回按钮模式：'route' 触发 back 事件（父组件处理），'history' 调用 router.back() */
  backMode?: 'route' | 'history'
}>(), {
  showBack: true,
  showSyncStatus: false,
  backMode: 'route',
})

const emit = defineEmits<{
  (e: 'back'): void
}>()

const router = useRouter()

function onBack() {
  if (props.backMode === 'history') {
    router.back()
  } else {
    emit('back')
  }
}

// ─── 同步状态 ─────────────────────────────────────────────────────────────────
type SyncStatus = 'ok' | 'syncing' | 'stale'
const syncStatus = ref<SyncStatus>('ok')
const lastSyncTime = ref<Date | null>(null)
// 用于驱动 syncTooltip 实时更新的时钟（每分钟 tick 一次）
const _now = ref(Date.now())
let _clockTimer: ReturnType<typeof setInterval> | null = null

/** 格式化"最后更新：X分钟前"（依赖 _now 实现实时更新） */
const syncTooltip = computed(() => {
  if (syncStatus.value === 'syncing') return '正在同步数据...'
  if (syncStatus.value === 'stale') return '数据可能过时，请刷新页面'
  if (!lastSyncTime.value) return '数据已是最新'
  const diffMs = _now.value - lastSyncTime.value.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return '最后更新：刚刚'
  if (diffMin < 60) return `最后更新：${diffMin} 分钟前`
  const diffHour = Math.floor(diffMin / 60)
  return `最后更新：${diffHour} 小时前`
})

let syncTimer: ReturnType<typeof setTimeout> | null = null

function onSyncEvent() {
  if (!props.showSyncStatus) return
  syncStatus.value = 'syncing'
  // 3 秒后自动切回 ok（SSE 事件通常很快完成）
  if (syncTimer) clearTimeout(syncTimer)
  syncTimer = setTimeout(() => {
    syncStatus.value = 'ok'
    lastSyncTime.value = new Date()
  }, 3000)
}

function onSyncFailed() {
  if (!props.showSyncStatus) return
  syncStatus.value = 'stale'
  if (syncTimer) clearTimeout(syncTimer)
}

onMounted(() => {
  if (props.showSyncStatus) {
    eventBus.on('sse:sync-event', onSyncEvent)
    eventBus.on('sse:sync-failed', onSyncFailed)
    // 每分钟更新一次时钟，驱动 syncTooltip 实时显示"X分钟前"
    _clockTimer = setInterval(() => { _now.value = Date.now() }, 60000)
  }
})

onUnmounted(() => {
  eventBus.off('sse:sync-event', onSyncEvent)
  eventBus.off('sse:sync-failed', onSyncFailed)
  if (syncTimer) clearTimeout(syncTimer)
  if (_clockTimer) clearInterval(_clockTimer)
})
</script>

<style scoped>
.gt-page-header {
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: var(--gt-gradient-primary);
  border-radius: var(--gt-radius-lg);
  padding: 16px 24px;
  margin-bottom: var(--gt-space-5);
  color: #fff;
  position: relative;
  overflow: hidden;
  box-shadow: 0 4px 20px rgba(75, 45, 119, 0.2);
  /* 网格纹理 */
  background-image:
    var(--gt-gradient-primary),
    linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px);
  background-size: 100% 100%, 20px 20px, 20px 20px;
}

/* 径向光晕装饰 */
.gt-page-header::before {
  content: '';
  position: absolute;
  top: -40%;
  right: -10%;
  width: 45%;
  height: 180%;
  background: radial-gradient(ellipse, rgba(255, 255, 255, 0.07) 0%, transparent 65%);
  pointer-events: none;
}

.gt-page-header__row1 {
  display: flex;
  align-items: center;
  gap: 16px;
  position: relative;
  z-index: 1;
  flex-wrap: wrap;
}

.gt-page-header__back {
  color: #fff !important;
  font-size: 13px;
  padding: 0;
  margin-right: 8px;
}

.gt-page-header__title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  white-space: nowrap;
  flex-shrink: 0;
}

/* 同步状态指示器 */
.gt-page-header__sync-status {
  margin-left: auto;
  flex-shrink: 0;
}

.gt-sync-dot {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 12px;
  cursor: default;
  white-space: nowrap;
}

.gt-sync-dot--ok {
  background: rgba(103, 194, 58, 0.2);
  color: #b8f0a0;
}

.gt-sync-dot--syncing {
  background: rgba(255, 255, 255, 0.15);
  color: rgba(255, 255, 255, 0.9);
  animation: gt-sync-pulse 1.2s ease-in-out infinite;
}

.gt-sync-dot--stale {
  background: rgba(230, 162, 60, 0.25);
  color: #ffd080;
}

@keyframes gt-sync-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>
