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
        <el-tab-pane label="程序任务" name="procedure" />
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
          @click="handleClick(n)"
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
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Bell, Warning, CircleCheckFilled, InfoFilled } from '@element-plus/icons-vue'
import { notificationApi } from '@/services/collaborationApi'
import { useCollaborationStore } from '@/stores/collaboration'
import { getNotificationJumpRoute } from '@/services/notificationTypes'
import { handleApiError } from '@/utils/errorHandler'
import { useAdaptivePoll } from '@/composables/useAdaptivePoll'

const collaborationStore = useCollaborationStore()
const router = useRouter()

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

/** 程序行任务通知：类型以 procedure_task. 前缀或 procedure_review_message（Task 11）。 */
function isProcedureNotif(type: string): boolean {
  return !!type && (type.startsWith('procedure_task.') || type === 'procedure_review_message')
}

/** 按分类过滤通知 */
const filteredNotifications = computed(() => {
  if (activeTab.value === 'all') return notifications.value
  if (activeTab.value === 'procedure') {
    return notifications.value.filter(n => isProcedureNotif(n.notification_type))
  }
  const types = CATEGORY_MAP[activeTab.value] || []
  return notifications.value.filter(n => types.includes(n.notification_type))
})

function onTabChange() {
  // Tab 切换时无需额外操作，computed 自动过滤
}

/** 列表是否已取过（首次打开才取；铃铛上的红点只需要未读数）。 */
const listLoaded = ref(false)

/**
 * 未读数轮询（spec runtime-performance-and-reload-hardening-followup R6.3）。
 *
 * 🔴 改动三点：
 * ① 挂载只取未读数 —— 列表原来在首屏就取，而它只在 popover 打开后才显示；
 * ② 列表首次打开才取（之后靠 SSE / 手动操作刷新）；
 * ③ 固定 `setInterval(30s)` 换成 `useAdaptivePoll`：页面隐藏时停、重新可见立即校准一次，
 *    且同一时刻只有一条链（原实现的 interval 在请求慢于 30 秒时会重叠发请求）。
 * 这里不接 SSE 通知（项目流不带全局通知事件），所以轮询不能删，只能收敛。
 */
const unreadPoll = useAdaptivePoll(async () => {
  await fetchUnreadCount()
  // 通知未读数没有「进行中 / 空闲」之分，固定按 idle 节奏（30 秒）续链。
  return false
}, { idleMs: 30000 })

onMounted(() => {
  unreadPoll.start()
})

onUnmounted(() => {
  unreadPoll.dispose()
})

// popover 首次打开才取列表；之后打开复用已有数据（标记已读 / 跳转仍各自刷新）。
// 取失败不置 listLoaded，下次打开重试；连续开关不重叠发请求。
let listLoading = false
watch(popoverVisible, async (open) => {
  if (!open || listLoaded.value || listLoading) return
  listLoading = true
  try {
    listLoaded.value = await fetchNotifications()
  } finally {
    listLoading = false
  }
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

/** 返回是否取成功：失败与「真的没有通知」都会把列表置空，调用方只能靠返回值区分。 */
async function fetchNotifications(): Promise<boolean> {
  try {
    const { data } = await notificationApi.list({ unread_only: false, limit: 20 })
    notifications.value = data?.items ?? data ?? []
    return true
  } catch {
    notifications.value = []
    return false
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

/**
 * 点击通知：未读则标记已读，随后按 metadata 驱动跳转（Task 11 / Req 10.8）。
 * 已读与未读点击 **均可跳转**（深链由 metadata 决定，不解析中文 content）。
 */
async function handleClick(n: any) {
  if (!n.is_read) {
    try {
      await notificationApi.markRead(n.id)
      n.is_read = true
      unreadCount.value = Math.max(0, unreadCount.value - 1)
    } catch (e) {
      handleApiError(e, '标记已读')
    }
  }
  const route = getNotificationJumpRoute(n.notification_type, n.metadata)
  if (route) {
    popoverVisible.value = false
    try {
      await router.push(route)
    } catch { /* 导航被取消（重复路由等）忽略 */ }
  }
}

async function markAllRead() {
  try {
    await notificationApi.markAllRead()
    notifications.value.forEach((n) => { n.is_read = true })
    unreadCount.value = 0
    ElMessage.success('已全部标为已读')
  } catch (e) {
    handleApiError(e, '全部已读')
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
