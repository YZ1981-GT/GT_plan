<!--
  QcDueProjects — 本月应抽查项目列表 [R7-S3-03 Task 15]
  后端端点：GET /api/qc/rotation/due-this-month（Task 18 新建）
-->
<template>
  <div class="qc-due-projects">
    <div class="qc-due-header">
      <span>本月应抽查项目（{{ projects.length }} 个）</span>
      <el-button size="small" @click="loadDue" :loading="loading">刷新</el-button>
    </div>
    <el-table :data="projects" v-loading="loading" stripe size="small" empty-text="本月无待抽查项目">
      <el-table-column prop="project_name" label="项目名称" min-width="200" />
      <el-table-column prop="client_name" label="客户" width="160" />
      <el-table-column prop="last_inspected_at" label="上次抽查" width="120">
        <template #default="{ row }">{{ row.last_inspected_at?.slice(0, 10) || '从未' }}</template>
      </el-table-column>
      <el-table-column prop="priority" label="优先级" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.priority === 'high' ? 'danger' : row.priority === 'medium' ? 'warning' : 'info'" size="small">
            {{ row.priority === 'high' ? '高' : row.priority === 'medium' ? '中' : '低' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" align="center">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="$emit('start-inspection', row)">开始抽查</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/services/apiProxy'

defineEmits<{ (e: 'start-inspection', project: any): void }>()

const projects = ref<any[]>([])
const loading = ref(false)

async function loadDue() {
  loading.value = true
  try {
    // 后端端点 Task 18 新建后可用；当前降级为空数组
    const data = await api.get('/api/qc/rotation/due-this-month').catch(() => ({ items: [] }))
    projects.value = Array.isArray(data) ? data : data?.items || []
  } catch { projects.value = [] }
  finally { loading.value = false }
}

onMounted(loadDue)
</script>

<style scoped>
.qc-due-projects { padding: var(--gt-space-2) 0; }
.qc-due-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-3); font-weight: 600; }
</style>
