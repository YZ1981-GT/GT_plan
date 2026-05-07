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
        <el-button size="small" text @click="markAllRead" style="font-size:11px;color:#4b2d77">全部已读</el-button>
      </div>

      <div v-if="notifications.length === 0" class="notif-empty">
        <el-empty description="暂无通知" :image-size="60" />
      </div>
      <div v-else class="notif-list">
        <div
          v-for="n in notifications"
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
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Bell, Warning, CircleCheckFilled, InfoFilled } from '@element-plus/icons-vue'
import { notificationApi } from '@/services/collaborationApi'
import { useCollaborationStore } from '@/stores/collaboration'

const collaborationStore = useCollaborationStore()

const popoverVisible = ref(false)
const notifications = ref<any[]>([])
const unreadCount = ref(0)

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
})

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
  color: #fff !important;
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
.notif-title { font-weight: 600; font-size: 13px; color: #303133; }
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
.notif-item:hover { background: #f5f3f8; }
.notif-item.unread { background: #f0ecf7; }
.notif-icon-wrap { padding-top: 1px; flex-shrink: 0; }
.notif-body { flex: 1; min-width: 0; }
.notif-item-title { font-size: 12px; font-weight: 500; color: #303133; line-height: 1.4; }
.notif-item-content {
  font-size: 11px;
  color: #909399;
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.notif-time { font-size: 10px; color: #c0c4cc; margin-top: 3px; }
.unread-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #4b2d77;
  flex-shrink: 0;
  margin-top: 4px;
}
.notif-footer {
  text-align: center;
  padding-top: 8px;
  margin-top: 4px;
  border-top: 1px solid #f0edf5;
}
</style>
