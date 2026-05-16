<template>
  <div class="gt-my-proc gt-fade-in">
    <GtPageHeader title="我的审计程序" variant="banner" icon="📋" :show-back="false">
      <template #subtitle>
        <span v-if="tasks.length">
          {{ completedCount }}/{{ tasks.length }} 已完成 · {{ inProgressCount }} 进行中
        </span>
      </template>
    </GtPageHeader>

    <el-empty v-if="!tasks.length && !loading" description="暂无被委派的审计程序，请联系项目经理分配" />

    <div v-for="(group, cycle) in groupedTasks" :key="cycle" style="margin-bottom: 20px">
      <h3 style="font-size: var(--gt-font-size-base); color: var(--gt-color-primary); margin-bottom: 8px">
        {{ cycleName(cycle as string) }}
        <el-tag size="small" style="margin-left: 8px">{{ group.length }} 项</el-tag>
      </h3>
      <el-table :data="group" border size="small" stripe>
        <el-table-column prop="procedure_code" label="编号" width="110" />
        <el-table-column prop="procedure_name" label="程序名称" min-width="250" />
        <el-table-column prop="wp_code" label="关联底稿" width="110">
          <template #default="{ row }">
            <el-button v-if="row.wp_code && row.project_id" link type="primary" size="small"
              @click="openWP(row)">{{ row.wp_code }}</el-button>
            <span v-else style="color: var(--gt-color-text-placeholder)">—</span>
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
      :color="completionRate >= 80 ? '#67c23a' : completionRate >= 50 ? '#e6a23c' : '#409eff'"
      :format="() => `${completedCount}/${tasks.length} 已完成`"
      style="margin-top: 16px" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import { getMyStaffId, getMyProcedureTasks, updateProcedureTrim } from '@/services/commonApi'
import { handleApiError } from '@/utils/errorHandler'

const router = useRouter()
const loading = ref(false)
const tasks = ref<any[]>([])

const CYCLE_NAMES: Record<string, string> = {
  B: 'B 计划阶段', C: 'C 风险评估', D: 'D 销售循环', E: 'E 货币资金',
  F: 'F 存货循环', G: 'G 投资循环', H: 'H 固定资产', I: 'I 无形资产',
  J: 'J 薪酬循环', K: 'K 管理费用', L: 'L 债务循环', M: 'M 权益循环',
  N: 'N 税金循环', A: 'A 完成阶段', S: 'S 特殊事项', Q: 'Q 关联方',
}

function cycleName(c: string) { return CYCLE_NAMES[c] || `${c} 循环` }

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
const inProgressCount = computed(() => tasks.value.filter(t => t.execution_status === 'in_progress').length)
const completionRate = computed(() => tasks.value.length ? Math.round(completedCount.value / tasks.value.length * 100) : 0)

function openWP(row: any) {
  if (row.project_id && row.wp_code) {
    router.push({ path: `/projects/${row.project_id}/workpapers`, query: { highlight: row.wp_code } })
  }
}

async function updateStatus(row: any) {
  try {
    await updateProcedureTrim(row.project_id, row.audit_cycle, [
      { id: row.id, status: row.status || 'execute', skip_reason: row.skip_reason },
    ])
    ElMessage.success('状态已更新')
  } catch (e: any) {
    handleApiError(e, '更新')
  }
}

async function loadMyTasks() {
  loading.value = true
  try {
    const staffId = await getMyStaffId()
    if (!staffId) return
    tasks.value = await getMyProcedureTasks(staffId)
  } catch (e: any) {
    handleApiError(e, '加载')
  } finally {
    loading.value = false
  }
}

onMounted(loadMyTasks)
</script>

<style scoped>
.gt-my-proc { padding: 0; }
.gt-page-banner {
  display: flex; justify-content: space-between; align-items: center;
  padding: 20px 24px; margin-bottom: 16px;
  background: linear-gradient(135deg, var(--gt-color-primary, #4b2d77) 0%, #6b4d97 100%);
  border-radius: 8px; color: var(--gt-color-text-inverse);
}
.gt-page-banner h2 { margin: 0; font-size: var(--gt-font-size-xl); font-weight: 600; }
.gt-banner-sub { font-size: var(--gt-font-size-sm); opacity: 0.85; margin-top: 4px; display: block; }
</style>
