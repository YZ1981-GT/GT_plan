<template>
  <div class="archive-management">
    <div class="archive-header">
      <h3>归档管理</h3>
      <el-button type="primary" @click="initChecklist">初始化归档清单</el-button>
    </div>

    <el-table :data="checklistItems" stripe>
      <el-table-column prop="item_code" label="编号" width="100" />
      <el-table-column prop="item_name" label="检查项" />
      <el-table-column prop="category" label="类别" width="120" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.is_completed ? 'success' : 'info'">
            {{ row.is_completed ? '已完成' : '待完成' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button size="small" type="success" :disabled="row.is_completed" @click="completeItem(row)">
            标记完成
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-divider />
    <h4>归档修改申请</h4>
    <el-button type="warning" @click="showRequest = true">发起修改申请</el-button>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { archiveApi } from '@/services/collaborationApi'

const checklistItems = ref<any[]>([])
const showRequest = ref(false)
const projectId = 'current-project-id'

onMounted(async () => {
  try {
    const { data } = await archiveApi.getChecklist(projectId)
    checklistItems.value = data
  } catch (e) {
    console.error(e)
  }
})

async function initChecklist() {
  try {
    await archiveApi.initChecklist(projectId)
    ElMessage.success('清单已初始化')
    const { data } = await archiveApi.getChecklist(projectId)
    checklistItems.value = data
  } catch (e) {
    ElMessage.error('初始化失败')
  }
}

async function completeItem(row: any) {
  try {
    await archiveApi.completeItem(projectId, row.id)
    ElMessage.success('已标记完成')
    row.is_completed = true
  } catch (e) {
    ElMessage.error('操作失败')
  }
}
</script>

<style scoped>
.archive-management {}
.archive-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
</style>
