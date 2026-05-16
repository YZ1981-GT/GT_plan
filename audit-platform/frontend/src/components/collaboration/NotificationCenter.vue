<template>
  <div class="gt-notification-center">
    <el-popover
      :visible="popoverVisible"
      placement="bottom-end"
      :width="300"
      trigger="click"
      @update:visible="popoverVisible = $event"
    >
      <template #reference>
        <el-tooltip content="通知中心" placement="bottom">
          <el-badge :value="unreadCount" :hidden="unreadCount === 0" :max="99">
            <el-icon class="bell-icon" :size="18" @click="popoverVisible = true">
              <Bell />
            </el-icon>
          </el-badge>
        </el-tooltip>
      </template>

      <div class="notif-header">
        <span class="notif-title">通知中心</span>
        <el-button size="small" text @click="markAllRead" style="font-size: var(--gt-font-size-xs);color: var(--gt-color-primary)">全部已读</el-button>
      </div>

      <!-- 分类 Tab -->
      <el-tabs v-model="activeTab" class="notif-tabs" @tab-change="onTabChange">
        <el-tab-pane label="全部" name="all" />
        <el-tab-pane label="复核" name="review" />
        <el-tab-pane label="导入" name="import" />
        <el-tab-pane label="系统" name="system" />
      </el-tabs>

      <div v-if="filteredNotifications.length === 0" class="notif-empty">
        <el-empty description="暂无通知" :image-size="60" />
      </div>
      <div v-else class="notif-list">
        <div
          v-for="n in filteredNotifications"
          :key="n.id"
          class="notif-item"
          :class="{ unread: !n.is_read }"
          @click="handleRead(n)"
        >
          <div class="notif-icon-wrap">
            <el-icon :color="iconColor(n.notification_type)" :size="16">
              <component :is="iconComponent(n.notification_type)" />
            </el-icon>
          </div>
          <div class="notif-body">
            <div class="notif-item-title">{{ n.title }}</div>
            <div v-if="n.content" class="notif-item-content">{{ n.content }}</div>
            <div class="notif-time">{{ formatTime(n.created_at) }}</div>
          </div>
          <div v-if="!n.is_read" class="unread-dot" />
        </div>
      </div>

      <div class="notif-footer">
        <el-button size="small" text @click="popoverVisible = false">关闭</el-button>
      </div>
    </el-popover>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Bell, Warning, CircleCheckFilled, InfoFilled } from '@element-plus/icons-vue'
import { notificationApi } from '@/services/collaborationApi'
import { useCollaborationStore } from '@/stores/collaboration'

const collaborationStore = useCollaborationStore()

const popoverVisible = ref(false)
const notifications = ref<any[]>([])
const unreadCount = ref(0)
const activeTab = ref('all')

/** 通知分类映射 */
const CATEGORY_MAP: Record<string, string[]> = {
  review: ['REVIEW', 'APPROVAL', 'COMMENT'],
  import: ['IMPORT', 'LEDGER', 'DATASET'],
  system: ['SYSTEM', 'AUDIT', 'DEFAULT'],
}

/** 按分类过滤通知 */
const filteredNotifications = computed(() => {
  if (activeTab.value === 'all') return notifications.value
  const types = CATEGORY_MAP[activeTab.value] || []
  return notifications.value.filter(n => types.includes(n.notification_type))
})

function onTabChange() {
  // Tab 切换时无需额外操作，computed 自动过滤
}

let pollTimer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  await fetchNotifications()
  await fetchUnreadCount()
  // Auto-poll every 30 seconds
  pollTimer = setInterval(async () => {
    await fetchUnreadCount()
  }, 30000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

// 监听 collaboration store 的 unreadCount 变化（SSE 触发时实时刷新）
watch(() => collaborationStore.unreadCount, (newCount) => {
  unreadCount.value = newCount
  // 免打扰时段（22:00-08:00）不弹 toast，仅更新列表
  if (!isDoNotDisturbTime()) {
    // 可在此处触发 toast 通知（如有新增）
  }
})

/** 判断当前是否处于免打扰时段（22:00-08:00） */
function isDoNotDisturbTime(): boolean {
  const hour = new Date().getHours()
  return hour >= 22 || hour < 8
}

async function fetchNotifications() {
  try {
    const { data } = await notificationApi.list({ unread_only: false, limit: 20 })
    notifications.value = data?.items ?? data ?? []
  } catch {
    notifications.value = []
  }
}

async function fetchUnreadCount() {
  try {
    const { data } = await notificationApi.unreadCount()
    unreadCount.value = data?.count ?? data ?? 0
  } catch {
    unreadCount.value = 0
  }
}

async function handleRead(n: any) {
  if (n.is_read) return
  try {
    await notificationApi.markRead(n.id)
    n.is_read = true
    unreadCount.value = Math.max(0, unreadCount.value - 1)
  } catch {
    ElMessage.error('操作失败')
  }
}

async function markAllRead() {
  try {
    await notificationApi.markAllRead()
    notifications.value.forEach((n) => { n.is_read = true })
    unreadCount.value = 0
    ElMessage.success('已全部标为已读')
  } catch {
    ElMessage.error('操作失败')
  }
}

function iconComponent(type: string) {
  const map: Record<string, any> = {
    REVIEW: Warning,
    AUDIT: InfoFilled,
    COMMENT: Bell,
    APPROVAL: CircleCheckFilled,
    DEFAULT: CircleCheckFilled,
  }
  return map[type] || Bell
}

function iconColor(type: string) {
  const map: Record<string, string> = {
    REVIEW: '#E6A23C',
    AUDIT: '#409EFF',
    COMMENT: '#909399',
    APPROVAL: '#67C23A',
  }
  return map[type] || '#909399'
}

function formatTime(iso: string) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
.gt-notification-center { display: inline-flex; align-items: center; }
.gt-notification-center :deep(.el-badge) { display: inline-flex; align-items: center; }
.gt-notification-center :deep(.el-popover.el-popper) { padding: 12px 16px !important; border-radius: 10px; box-shadow: 0 8px 24px rgba(0,0,0,0.12); }
.bell-icon {
  cursor: pointer;
  width: 34px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--gt-color-text-inverse) !important;
  border-radius: 8px;
  transition: background 0.15s;
}
.bell-icon:hover { background: rgba(255, 255, 255, 0.12); }

.notif-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.notif-title { font-weight: 600; font-size: var(--gt-font-size-sm); color: var(--gt-color-text-primary); }
.notif-divider { margin: 0 0 8px; }
.notif-empty { padding: 16px 0; text-align: center; }
.notif-list { max-height: 320px; overflow-y: auto; }
.notif-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 4px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
  margin-bottom: 2px;
}
.notif-item:hover { background: var(--gt-color-primary-bg); }
.notif-item.unread { background: var(--gt-color-primary-bg); }
.notif-icon-wrap { padding-top: 1px; flex-shrink: 0; }
.notif-body { flex: 1; min-width: 0; }
.notif-item-title { font-size: var(--gt-font-size-xs); font-weight: 500; color: var(--gt-color-text-primary); line-height: 1.4; }
.notif-item-content {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-info);
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.notif-time { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-placeholder); margin-top: 3px; }
.unread-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--gt-color-primary);
  flex-shrink: 0;
  margin-top: 4px;
}
.notif-footer {
  text-align: center;
  padding-top: 8px;
  margin-top: 4px;
  border-top: 1px solid var(--gt-color-border-purple);
}
.notif-tabs :deep(.el-tabs__header) { margin-bottom: 8px; }
.notif-tabs :deep(.el-tabs__item) { font-size: var(--gt-font-size-xs); padding: 0 10px; height: 28px; line-height: 28px; }
.notif-tabs :deep(.el-tabs__nav-wrap::after) { height: 1px; }
</style>
