<template>
  <div class="sync-management">
    <div class="sync-header">
      <h3>同步管理</h3>
      <el-button type="primary" @click="syncNow">立即同步</el-button>
    </div>

    <el-descriptions :column="2" border>
      <el-descriptions-item label="全局版本">{{ syncStatus?.global_version }}</el-descriptions-item>
      <el-descriptions-item label="同步状态">{{ syncStatus?.sync_status }}</el-descriptions-item>
      <el-descriptions-item label="是否锁定">{{ syncStatus?.is_locked ? '是' : '否' }}</el-descriptions-item>
      <el-descriptions-item label="最后同步">{{ syncStatus?.last_synced_at }}</el-descriptions-item>
    </el-descriptions>

    <el-divider />

    <h4>同步历史</h4>
    <el-table :data="syncLogs" stripe size="small">
      <el-table-column prop="created_at" label="时间" />
      <el-table-column prop="sync_type" label="类型" />
      <el-table-column prop="user_id" label="操作人" />
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { syncApi } from '@/services/collaborationApi'

const syncStatus = ref<any>(null)
const syncLogs = ref<any[]>([])

const projectId = 'current-project-id' // should come from route/store

onMounted(async () => {
  try {
    const { data } = await syncApi.status(projectId)
    syncStatus.value = data
  } catch (e) {
    console.error(e)
  }
})

async function syncNow() {
  try {
    await syncApi.sync(projectId)
    ElMessage.success('同步完成')
    const { data } = await syncApi.status(projectId)
    syncStatus.value = data
  } catch (e) {
    ElMessage.error('同步失败')
  }
}
</script>

<style scoped>
.sync-management {}
.sync-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
</style>
