<!--
  QcCaseLibraryEmbed — QC 案例库嵌入组件 [R7-S3-03]
-->
<template>
  <div class="qc-embed-panel">
    <div class="qc-embed-header">
      <span>案例库</span>
      <el-button size="small" text type="primary" @click="$router.push('/qc/cases')">前往完整页面 →</el-button>
    </div>
    <el-empty v-if="!loading && !cases.length" description="暂无案例" />
    <el-table v-else :data="cases" v-loading="loading" stripe size="small" max-height="500">
      <el-table-column prop="title" label="标题" min-width="200" />
      <el-table-column prop="category" label="分类" width="120" />
      <el-table-column prop="created_at" label="时间" width="120">
        <template #default="{ row }">{{ row.created_at?.slice(0, 10) }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/services/apiProxy'
import { qcCases } from '@/services/apiPaths'

const cases = ref<any[]>([])
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    const data = await api.get(qcCases.list)
    cases.value = Array.isArray(data) ? data : data?.items || []
  } catch { /* ignore */ }
  finally { loading.value = false }
})
</script>

<style scoped>
.qc-embed-panel { padding: var(--gt-space-2) 0; }
.qc-embed-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-3); font-weight: 600; }
</style>
