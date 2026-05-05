<template>
  <div class="gt-sync-indicator">
    <!-- 状态图标按钮 -->
    <el-tooltip :content="tooltipText" placement="bottom">
      <div
        class="gt-topbar-btn gt-sync-btn"
        :class="statusClass"
        @click="onIndicatorClick"
      >
        <el-icon v-if="status === 'syncing'" :size="18" class="is-loading"><Loading /></el-icon>
        <el-icon v-else-if="status === 'failed'" :size="18"><WarningFilled /></el-icon>
        <el-icon v-else :size="18"><CircleCheckFilled /></el-icon>
        <el-badge
          v-if="failedEvents.length > 0"
          :value="failedEvents.length"
          :max="99"
          class="gt-sync-badge"
        />
      </div>
    </el-tooltip>

    <!-- 失败详情面板 -->
    <el-drawer
      v-model="drawerVisible"
      title="同步状态详情"
      direction="rtl"
      size="420px"
      :append-to-body="true"
    >
      <div v-if="failedEvents.length === 0" class="gt-sync-empty">
        <el-icon :size="48" color="#67c23a"><CircleCheckFilled /></el-icon>
        <p>所有事件同步正常</p>
      </div>
      <div v-else class="gt-sync-list">
        <div
          v-for="(evt, idx) in failedEvents"
          :key="idx"
          class="gt-sync-item gt-sync-item--failed"
        >
          <div class="gt-sync-item-header">
            <el-icon color="#f56c6c"><WarningFilled /></el-icon>
            <span class="gt-sync-item-title">{{ formatEventType(evt.extra?.source_event) }}</span>
            <span class="gt-sync-item-time">{{ evt.timestamp }}</span>
          </div>
          <div class="gt-sync-item-body">
            <div class="gt-sync-detail-row">
              <span class="gt-sync-label">处理器</span>
              <span class="gt-sync-value">{{ evt.extra?.handler || '未知' }}</span>
            </div>
            <div class="gt-sync-detail-row">
              <span class="gt-sync-label">错误信息</span>
              <span class="gt-sync-value gt-sync-error">{{ evt.extra?.error || '未知错误' }}</span>
            </div>
            <div v-if="evt.account_codes?.length" class="gt-sync-detail-row">
              <span class="gt-sync-label">影响科目</span>
              <span class="gt-sync-value">{{ evt.account_codes.join(', ') }}</span>
            </div>
            <!-- 重试按钮（extra.retry_endpoint 存在时显示） -->
            <div v-if="evt.extra?.retry_endpoint" class="gt-sync-detail-row" style="margin-top:4px">
              <el-button
                size="small"
                type="warning"
                plain
                :loading="retryingIdx === idx"
                @click="onRetry(evt, idx)"
              >
                🔄 重试
              </el-button>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button v-if="failedEvents.length > 0" type="danger" plain @click="clearFailed">
          清除所有失败记录
        </el-button>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Loading, WarningFilled, CircleCheckFilled } from '@element-plus/icons-vue'
import { eventBus, type SyncEventPayload } from '@/utils/eventBus'

// ── 状态 ──
type SyncStatus = 'synced' | 'syncing' | 'failed'
const status = ref<SyncStatus>('synced')
const drawerVisible = ref(false)
const retryingIdx = ref<number | null>(null)

interface FailedEvent extends SyncEventPayload {
  timestamp: string
}
const failedEvents = ref<FailedEvent[]>([])

// 同步中计数器（收到普通事件 +1，收到对应完成事件 -1）
let syncingCount = 0
let syncResetTimer: ReturnType<typeof setTimeout> | null = null

// ── 计算属性 ──
const tooltipText = computed(() => {
  if (status.value === 'failed') return `同步失败 (${failedEvents.value.length} 条)`
  if (status.value === 'syncing') return '同步中...'
  return '同步正常'
})

const statusClass = computed(() => ({
  'gt-sync-btn--synced': status.value === 'synced',
  'gt-sync-btn--syncing': status.value === 'syncing',
  'gt-sync-btn--failed': status.value === 'failed',
}))

// ── 事件处理 ──
function onSyncEvent(_payload: SyncEventPayload) {
  // 收到普通同步事件 → 短暂显示 syncing 状态
  syncingCount++
  status.value = 'syncing'
  if (syncResetTimer) clearTimeout(syncResetTimer)
  syncResetTimer = setTimeout(() => {
    syncingCount = Math.max(0, syncingCount - 1)
    if (syncingCount === 0 && failedEvents.value.length === 0) {
      status.value = 'synced'
    }
  }, 2000)
}

function onSyncFailed(payload: SyncEventPayload) {
  status.value = 'failed'
  failedEvents.value.unshift({
    ...payload,
    timestamp: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
  })
  // 最多保留 50 条
  if (failedEvents.value.length > 50) {
    failedEvents.value = failedEvents.value.slice(0, 50)
  }
}

function onIndicatorClick() {
  if (status.value === 'failed' || failedEvents.value.length > 0) {
    drawerVisible.value = true
  }
}

function clearFailed() {
  failedEvents.value = []
  status.value = syncingCount > 0 ? 'syncing' : 'synced'
  drawerVisible.value = false
}

async function onRetry(evt: FailedEvent, idx: number) {
  const endpoint = evt.extra?.retry_endpoint
  if (!endpoint) return
  retryingIdx.value = idx
  try {
    const { api } = await import('@/services/apiProxy')
    await api.post(endpoint, {}, { validateStatus: (s: number) => s < 600 })
    // 重试成功，移除该条失败记录
    failedEvents.value.splice(idx, 1)
    if (failedEvents.value.length === 0) {
      status.value = syncingCount > 0 ? 'syncing' : 'synced'
    }
  } catch {
    // 重试失败，保留记录
  } finally {
    retryingIdx.value = null
  }
}

function formatEventType(eventType?: string): string {
  if (!eventType) return '未知事件'
  const map: Record<string, string> = {
    'adjustment.created': '调整分录创建',
    'adjustment.updated': '调整分录更新',
    'adjustment.deleted': '调整分录删除',
    'mapping.changed': '科目映射变更',
    'data.imported': '数据导入',
    'import.rolled_back': '导入回滚',
    'materiality.changed': '重要性水平变更',
    'trial_balance.updated': '试算表更新',
    'reports.updated': '报表更新',
    'workpaper.saved': '底稿保存',
    'note.updated': '附注更新',
    'ledger.import_submitted': '序时账导入提交',
    'ledger.dataset_activated': '数据集激活',
    'ledger.dataset_rolled_back': '数据集回滚',
  }
  return map[eventType] || eventType
}

// ── 监听 eventBus ──
eventBus.on('sse:sync-event', onSyncEvent)
eventBus.on('sse:sync-failed', onSyncFailed)
</script>

<style scoped>
.gt-sync-indicator {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.gt-sync-btn {
  position: relative;
  transition: all 0.2s;
}
.gt-sync-btn--synced {
  color: var(--gt-color-text-tertiary, #909399);
}
.gt-sync-btn--syncing {
  color: var(--gt-color-primary, #4b2d77);
  background: var(--gt-color-primary-bg, #f3eef8);
}
.gt-sync-btn--failed {
  color: #f56c6c;
  background: #fef0f0;
}
.gt-sync-btn--failed:hover {
  background: #fde2e2;
}

.gt-sync-badge {
  position: absolute;
  top: -4px;
  right: -6px;
}
.gt-sync-badge :deep(.el-badge__content) {
  font-size: 10px;
  height: 16px;
  line-height: 16px;
  padding: 0 4px;
}

/* ── 抽屉内容 ── */
.gt-sync-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 0;
  color: #909399;
}
.gt-sync-empty p {
  margin-top: 12px;
  font-size: 14px;
}

.gt-sync-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.gt-sync-item {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 12px;
}
.gt-sync-item--failed {
  border-color: #fbc4c4;
  background: #fef0f0;
}

.gt-sync-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.gt-sync-item-title {
  font-weight: 600;
  font-size: 13px;
  flex: 1;
}
.gt-sync-item-time {
  font-size: 11px;
  color: #909399;
}

.gt-sync-item-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.gt-sync-detail-row {
  display: flex;
  gap: 8px;
  font-size: 12px;
}
.gt-sync-label {
  color: #909399;
  min-width: 56px;
  flex-shrink: 0;
}
.gt-sync-value {
  color: #303133;
  word-break: break-all;
}
.gt-sync-error {
  color: #f56c6c;
}
</style>
