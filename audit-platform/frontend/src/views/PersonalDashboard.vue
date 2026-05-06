<template>
  <div class="gt-personal gt-fade-in">
    <h2 class="gt-page-title">我的工作台</h2>
    <el-row :gutter="16">
      <el-col :span="8">
        <div class="gt-p-card">
          <h4>我参与的项目</h4>
          <div v-for="p in myProjects" :key="p.project_id" class="gt-p-project-item"
            @click="$router.push(`/projects/${p.project_id}/ledger`)">
            <div>
              <span class="gt-p-proj-name">{{ p.project_name }}</span>
              <el-tag v-if="isNewAssignment(p.assigned_at)" type="danger" size="small" style="margin-left: 4px">新</el-tag>
            </div>
            <div style="display: flex; gap: 4px; align-items: center">
              <el-tag size="small" type="info">{{ roleLabel(p.role) }}</el-tag>
              <span v-if="p.assigned_cycles?.length" style="font-size: 11px; color: #999">{{ p.assigned_cycles.join('/') }}</span>
            </div>
          </div>
          <el-empty v-if="!myProjects.length" :image-size="50" description="暂无委派项目" />
        </div>
      </el-col>
      <el-col :span="8">
        <div class="gt-p-card">
          <h4>我的待办</h4>
          <div v-for="t in todos" :key="t.id" class="gt-p-todo-item">
            <span>{{ t.label }}</span>
            <el-tag :type="t.urgent ? 'danger' : 'info'" size="small">{{ t.type }}</el-tag>
          </div>
          <el-empty v-if="!todos.length" :image-size="50" description="暂无待办" />
        </div>
      </el-col>
      <el-col :span="8">
        <div class="gt-p-card">
          <h4>本周工时</h4>
          <div v-for="h in weekHours" :key="h.work_date" class="gt-p-hour-item">
            <span>{{ h.work_date }}</span>
            <span>{{ h.project_name }}</span>
            <span style="font-weight: 600">{{ h.hours }}h</span>
          </div>
          <el-empty v-if="!weekHours.length" :image-size="50" description="本周暂无工时" />
          <el-button size="small" style="margin-top: 8px" @click="$router.push('/work-hours')">填报工时</el-button>
        </div>
      </el-col>
    </el-row>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getMyAssignments, listWorkHours } from '@/services/staffApi'
import { getMyTodos, getMyStaffId } from '@/services/commonApi'

const myProjects = ref<any[]>([])
const todos = ref<any[]>([])
const weekHours = ref<any[]>([])

const ROLE_MAP: Record<string, string> = { signing_partner: '签字合伙人', manager: '项目经理', auditor: '审计员', qc: '质控人员', eqcr: '独立复核合伙人' }
function roleLabel(role: string) { return ROLE_MAP[role] || role }
function isNewAssignment(assignedAt: string | null) {
  if (!assignedAt) return false
  const diff = Date.now() - new Date(assignedAt).getTime()
  return diff < 7 * 24 * 60 * 60 * 1000 // 7天内
}

onMounted(async () => {
  try { myProjects.value = await getMyAssignments() } catch { myProjects.value = [] }

  // 加载待办事项
  try {
    const todosRes = await getMyTodos()
    todos.value = Array.isArray(todosRes) ? todosRes : ((todosRes as any)?.items ?? [])
  } catch {
    todos.value = []
  }

  // 加载本周工时
  try {
    const today = new Date()
    const weekStart = new Date(today)
    weekStart.setDate(today.getDate() - today.getDay() + 1)
    const startDate = weekStart.toISOString().slice(0, 10)
    const endDate = today.toISOString().slice(0, 10)

    const staffId = await getMyStaffId()
    if (staffId) {
      const hoursRes = await listWorkHours(staffId, { start_date: startDate, end_date: endDate })
      weekHours.value = Array.isArray(hoursRes) ? hoursRes : ((hoursRes as any)?.items ?? [])
    }
  } catch {
    weekHours.value = []
  }
})
</script>
<style scoped>
.gt-personal { padding: var(--gt-space-4); }
.gt-p-card { background: white; border-radius: var(--gt-radius-md); padding: 16px; box-shadow: var(--gt-shadow-sm); min-height: 280px; }
.gt-p-card h4 { margin: 0 0 12px; font-size: 14px; color: var(--gt-color-primary, #4b2d77); }
.gt-p-project-item { display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px solid #f0f0f0; cursor: pointer; }
.gt-p-project-item:hover { background: #f8f6fb; }
.gt-p-proj-name { font-size: 13px; }
.gt-p-todo-item { display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px solid #f0f0f0; font-size: 13px; }
.gt-p-hour-item { display: flex; justify-content: space-between; padding: 4px 0; font-size: 13px; }
</style>
