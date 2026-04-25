<template>
  <div class="gt-my-proc gt-fade-in">
    <h2 class="gt-page-title">我的审计程序</h2>
    <el-empty v-if="!tasks.length && !loading" description="暂无被委派的审计程序" />
    <div v-for="(group, cycle) in groupedTasks" :key="cycle" style="margin-bottom: 20px">
      <h3 style="font-size: 15px; color: var(--gt-color-primary)">{{ cycle }} 循环</h3>
      <el-table :data="group" border size="small">
        <el-table-column prop="procedure_code" label="编号" width="120" />
        <el-table-column prop="procedure_name" label="程序名称" min-width="250" />
        <el-table-column prop="wp_code" label="关联底稿" width="100">
          <template #default="{ row }">
            <el-button v-if="row.wp_code" link type="primary" size="small" @click="openWP(row)">{{ row.wp_code }}</el-button>
            <span v-else style="color: #ccc">—</span>
          </template>
        </el-table-column>
        <el-table-column label="执行状态" width="130" align="center">
          <template #default="{ row }">
            <el-select v-model="row.execution_status" size="small" @change="updateStatus(row)">
              <el-option label="未开始" value="not_started" />
              <el-option label="进行中" value="in_progress" />
              <el-option label="已完成" value="completed" />
            </el-select>
          </template>
        </el-table-column>
      </el-table>
    </div>
    <el-progress v-if="tasks.length" :percentage="completionRate" :stroke-width="16"
      :format="() => `${completedCount}/${tasks.length} 已完成`"
      style="margin-top: 16px" />
  </div>
</template>
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
const router = useRouter()
const loading = ref(false)
const tasks = ref<any[]>([])
const groupedTasks = computed(() => {
  const groups: Record<string, any[]> = {}
  for (const t of tasks.value) {
    const c = t.audit_cycle || 'OTHER'
    if (!groups[c]) groups[c] = []
    groups[c].push(t)
  }
  return groups
})
const completedCount = computed(() => tasks.value.filter(t => t.execution_status === 'completed').length)
const completionRate = computed(() => tasks.value.length ? Math.round(completedCount.value / tasks.value.length * 100) : 0)
function openWP(_row: any) {
  // TODO: 需要 project_id 和 wp_id 来跳转
  router.push(`/poc`)
}
async function updateStatus(_row: any) {
  // TODO: 调用后端更新 execution_status
}
onMounted(async () => {
  // TODO: 需要当前用户的 staff_id 来调用 /api/projects/{id}/procedures/my-tasks
  // 暂时加载空数据
})
</script>
<style scoped>
.gt-my-proc { padding: var(--gt-space-4); }
</style>
