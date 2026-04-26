<template>
  <div class="gt-snapshots gt-fade-in">
    <div class="gt-page-header">
      <h2 class="gt-page-title">合并数据快照</h2>
      <el-button type="primary" @click="onCreate">创建快照</el-button>
    </div>
    <el-table :data="snapshots" stripe>
      <el-table-column prop="year" label="年度" width="80" />
      <el-table-column prop="trigger_reason" label="触发原因" width="120">
        <template #default="{ row }">
          <el-tag size="small">{{ row.trigger_reason === 'manual' ? '手动' : row.trigger_reason === 'auto_on_generate' ? '自动(生成)' : row.trigger_reason }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间">
        <template #default="{ row }">{{ row.created_at?.slice(0, 19) }}</template>
      </el-table-column>
      <el-table-column prop="id" label="快照ID" show-overflow-tooltip />
    </el-table>
    <el-empty v-if="!snapshots.length" description="暂无快照" />
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listSnapshots, createSnapshot } from '@/services/commonApi'
const route = useRoute()
const projectId = ref(route.params.projectId as string || '')
const snapshots = ref<any[]>([])
async function fetch() { if (projectId.value) snapshots.value = await listSnapshots(projectId.value) }
async function onCreate() {
  await createSnapshot(projectId.value)
  ElMessage.success('快照已创建')
  await fetch()
}
onMounted(fetch)
</script>
<style scoped>
.gt-snapshots { padding: var(--gt-space-4); }
.gt-page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-3); }
</style>
