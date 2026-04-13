<template>
  <div class="gt-notification-list">
    <div class="notif-actions">
      <el-button size="small" @click="markAllRead">全部标为已读</el-button>
    </div>
    <el-empty v-if="notifications.length === 0" description="暂无通知" />
    <div v-else class="notif-items">
      <div
        v-for="n in notifications"
        :key="n.id"
        class="notif-item"
        :class="{ unread: !n.is_read }"
        @click="markRead(n)"
      >
        <div class="notif-title">{{ n.title }}</div>
        <div v-if="n.content" class="notif-content">{{ n.content }}</div>
        <div class="notif-time">{{ n.created_at }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useCollaborationStore } from '@/stores/collaboration'

const store = useCollaborationStore()
const notifications = computed(() => store.notifications)

onMounted(() => store.fetchNotifications())

async function markRead(n: any) {
  if (!n.is_read) {
    await store.markNotificationRead(n.id)
  }
}

async function markAllRead() {
  const { notificationApi } = await import('@/services/collaborationApi')
  await notificationApi.markAllRead()
  await store.fetchNotifications()
}
</script>

<style scoped>
.notif-actions { margin-bottom: 12px; }
.notif-items {}
.notif-item {
  padding: 12px;
  border-bottom: 1px solid #eee;
  cursor: pointer;
  transition: background 0.2s;
}
.notif-item:hover { background: #f9f9f9; }
.notif-item.unread { background: #f0f7ff; }
.notif-title { font-weight: 600; font-size: 14px; }
.notif-content { color: #666; font-size: 13px; margin-top: 4px; }
.notif-time { color: #999; font-size: 12px; margin-top: 4px; }
</style>
