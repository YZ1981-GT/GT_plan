<template>
  <div class="gt-personal gt-fade-in">
    <h2 class="gt-page-title">我的工作台</h2>
    <el-row :gutter="16">
      <el-col :span="8">
        <div class="gt-p-card">
          <h4>我参与的项目</h4>
          <div v-for="p in myProjects" :key="p.project_id" class="gt-p-project-item"
            @click="$router.push(`/projects/${p.project_id}/ledger`)">
            <span class="gt-p-proj-name">{{ p.project_name }}</span>
            <el-tag size="small" type="info">{{ p.role }}</el-tag>
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
import { getMyAssignments } from '@/services/staffApi'
const myProjects = ref<any[]>([])
const todos = ref<any[]>([])
const weekHours = ref<any[]>([])
onMounted(async () => {
  try { myProjects.value = await getMyAssignments() } catch { myProjects.value = [] }
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
