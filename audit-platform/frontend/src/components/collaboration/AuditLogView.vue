<template>
  <div class="gt-audit-log-view">
    <div class="log-header">
      <h3>审计日志</h3>
    </div>
    <el-table :data="logs" stripe size="small">
      <el-table-column prop="created_at" label="时间" width="180" />
      <el-table-column prop="user_id" label="操作人" width="120" />
      <el-table-column prop="operation_type" label="操作" width="100" />
      <el-table-column prop="object_type" label="对象类型" />
      <el-table-column prop="object_id" label="对象ID" width="200" />
      <el-table-column label="详情" width="100">
        <template #default="{ row }">
          <el-button size="small" @click="viewDetail(row)">查看</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination
      v-model:current-page="page"
      :page-size="50"
      layout="prev, pager, next"
      :total="total"
      @current-change="fetchLogs"
      style="margin-top: 16px"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { auditLogApi } from '@/services/collaborationApi'

const logs = ref<any[]>([])
const total = ref(0)
const page = ref(1)

onMounted(() => fetchLogs())

async function fetchLogs() {
  try {
    const { data } = await auditLogApi.list({ skip: (page.value - 1) * 50, limit: 50 })
    logs.value = data
  } catch (e) {
    console.error(e)
  }
}

function viewDetail(row: any) {
  console.log('detail', row)
}
</script>

<style scoped>
.gt-audit-log-view {}
.log-header { margin-bottom: 16px; }
</style>
