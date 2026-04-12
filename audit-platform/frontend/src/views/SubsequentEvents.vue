<template>
  <div class="subsequent-events-view">
    <div class="page-header">
      <h2>期后事项管理</h2>
      <el-select v-model="currentProjectId" placeholder="选择项目" filterable style="width: 300px" @change="loadEvents">
        <el-option v-for="p in projects" :key="p.id" :label="p.project_name" :value="p.id" />
      </el-select>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="期后事项记录" name="events">
        <SubsequentEventsPanel :project-id="currentProjectId" />
      </el-tab-pane>
      <el-tab-pane label="审阅程序清单" name="checklist">
        <SEChecklistPanel :project-id="currentProjectId" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import SubsequentEventsPanel from '@/components/collaboration/SubsequentEventsPanel.vue'
import SEChecklistPanel from '@/components/collaboration/SEChecklistPanel.vue'
import { auditPlatformApi } from '@/services/auditPlatformApi'

const activeTab = ref('events')
const currentProjectId = ref('')
const projects = ref<any[]>([])

const loadProjects = async () => {
  try {
    const res = await auditPlatformApi.getProjects()
    projects.value = res.data
    if (projects.value.length && !currentProjectId.value) {
      currentProjectId.value = projects.value[0].id
    }
  } catch {}
}

const loadEvents = () => {}

onMounted(loadProjects)
</script>

<style scoped>
.subsequent-events-view { padding: 16px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { margin: 0; }
</style>
