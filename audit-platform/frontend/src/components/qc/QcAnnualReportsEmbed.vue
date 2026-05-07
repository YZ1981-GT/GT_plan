<!--
  QcAnnualReportsEmbed — QC 年报嵌入组件 [R7-S3-03]
-->
<template>
  <div class="qc-embed-panel">
    <div class="qc-embed-header">
      <span>质控年报</span>
      <el-button size="small" text type="primary" @click="$router.push('/qc/annual-reports')">前往完整页面 →</el-button>
    </div>
    <el-empty v-if="!loading && !reports.length" description="暂无年报" />
    <el-table v-else :data="reports" v-loading="loading" stripe size="small" max-height="500">
      <el-table-column prop="year" label="年度" width="80" />
      <el-table-column prop="title" label="标题" min-width="200" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'published' ? 'success' : 'info'" size="small">
            {{ row.status === 'published' ? '已发布' : '草稿' }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/services/apiProxy'
import { qcAnnualReports } from '@/services/apiPaths'

const reports = ref<any[]>([])
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    const data = await api.get(qcAnnualReports.list)
    reports.value = Array.isArray(data) ? data : data?.items || []
  } catch { /* ignore */ }
  finally { loading.value = false }
})
</script>

<style scoped>
.qc-embed-panel { padding: var(--gt-space-2) 0; }
.qc-embed-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-3); font-weight: 600; }
</style>
