<template>
  <div class="collab-index">
    <div class="collab-header">
      <h1>协作与质控</h1>
      <div class="header-actions">
        <el-badge :value="unreadCount" :hidden="unreadCount === 0">
          <el-button @click="showNotifications = true">通知</el-button>
        </el-badge>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="collab-tabs">
      <el-tab-pane label="项目团队" name="team">
        <ProjectTeam />
      </el-tab-pane>
      <el-tab-pane label="复核管理" name="review">
        <ReviewManagement />
      </el-tab-pane>
      <el-tab-pane label="工作底稿" name="workpaper">
        <WorkpaperReview />
      </el-tab-pane>
      <el-tab-pane label="同步管理" name="sync">
        <SyncManagement />
      </el-tab-pane>
      <el-tab-pane label="归档管理" name="archive">
        <ArchiveManagement />
      </el-tab-pane>
      <el-tab-pane label="审计日志" name="audit">
        <AuditLogView />
      </el-tab-pane>
    </el-tabs>

    <el-drawer v-model="showNotifications" title="通知" size="400px">
      <NotificationList />
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useCollaborationStore } from '@/stores/collaboration'
import ProjectTeam from '@/components/collaboration/ProjectTeam.vue'
import ReviewManagement from '@/components/collaboration/ReviewManagement.vue'
import WorkpaperReview from '@/components/collaboration/WorkpaperReview.vue'
import SyncManagement from '@/components/collaboration/SyncManagement.vue'
import ArchiveManagement from '@/components/collaboration/ArchiveManagement.vue'
import AuditLogView from '@/components/collaboration/AuditLogView.vue'
import NotificationList from '@/components/collaboration/NotificationList.vue'

const store = useCollaborationStore()
const activeTab = ref('team')
const showNotifications = ref(false)
const unreadCount = computed(() => store.unreadCount)

onMounted(() => {
  store.fetchNotifications()
})
</script>

<style scoped>
.collab-index { padding: 24px; }
.collab-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.collab-tabs :deep(.el-tabs__content) { padding-top: 16px; }
</style>
