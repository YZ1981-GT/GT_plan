<template>
  <div class="gt-notification-center">
    <el-popover
      :visible="popoverVisible"
      placement="bottom-end"
      :width="360"
      trigger="click"
      @update:visible="popoverVisible = $event"
    >
      <template #reference>
        <el-badge :value="unreadCount" :hidden="unreadCount === 0" :max="99">
          <el-icon class="bell-icon" :size="22" @click="popoverVisible = true">
            <Bell />
          </el-icon>
        </el-badge>
      </template>

      <div class="notif-header">
        <span class="notif-title">通知中心</span>
        <el-button size="small" text type="primary" @click="markAllRead">全部标为已读</el-button>
      </div>

      <el-divider class="notif-divider" />

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
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Bell, Warning, CircleCheckFilled, InfoFilled } from '@element-plus/icons-vue'
import { notificationApi } from '@/services/collaborationApi'

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
.bell-icon {
  cursor: pointer;
  color: #606266;
  padding: 4px;
  border-radius: 4px;
  transition: background 0.2s;
}
.bell-icon:hover { background: #f0f2f5; }
.notif-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 8px;
}
.notif-title { font-weight: 600; font-size: 15px; }
.notif-divider { margin: 4px 0 8px; }
.notif-empty { padding: 8px 0; }
.notif-list { max-height: 400px; overflow-y: auto; }
.notif-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
  transition: background 0.15s;
}
.notif-item:hover { background: #f9f9f9; }
.notif-item.unread { background: #f0f7ff; }
.notif-icon-wrap { padding-top: 2px; flex-shrink: 0; }
.notif-body { flex: 1; min-width: 0; }
.notif-item-title { font-size: 13px; font-weight: 600; color: #303133; line-height: 1.4; }
.notif-item-content {
  font-size: 12px;
  color: #606266;
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.notif-time { font-size: 11px; color: #999; margin-top: 4px; }
.unread-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #409EFF;
  flex-shrink: 0;
  margin-top: 5px;
}
.notif-footer {
  text-align: center;
  padding-top: 8px;
  border-top: 1px solid #f0f0f0;
}
</style>
