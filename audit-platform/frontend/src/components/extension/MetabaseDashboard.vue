<template>
  <div class="gt-metabase">
    <div class="gt-mb-header" v-if="showHeader">
      <el-select v-model="selectedDashboard" size="small" placeholder="选择仪表板" style="width: 200px" @change="loadDashboard">
        <el-option v-for="d in dashboards" :key="d.id" :label="d.name" :value="d.id" />
      </el-select>
      <el-button size="small" @click="refresh" :loading="loading">刷新</el-button>
    </div>
    <div class="gt-mb-body" v-loading="loading">
      <iframe
        v-if="embedUrl"
        :src="embedUrl"
        class="gt-mb-iframe"
        frameborder="0"
        allowfullscreen
      />
      <el-empty v-else description="请选择仪表板或配置 Metabase 连接" :image-size="80" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/services/apiProxy'

const props = withDefaults(defineProps<{
  projectId?: string
  year?: number
  showHeader?: boolean
  defaultDashboard?: string
}>(), { showHeader: true })

const loading = ref(false)
const dashboards = ref<any[]>([])
const selectedDashboard = ref('')
const embedUrl = ref('')

async function loadDashboards() {
  try {
    const data = await api.get('/api/metabase/dashboards')
    dashboards.value = data ?? []
    if (props.defaultDashboard) {
      selectedDashboard.value = props.defaultDashboard
      await loadDashboard()
    }
  } catch { dashboards.value = [] }
}

async function loadDashboard() {
  if (!selectedDashboard.value) return
  loading.value = true
  try {
    const config = dashboards.value.find(d => d.id === selectedDashboard.value)
    const params: any = { resource_type: 'dashboard', resource_id: config?.metabase_dashboard_id || 1 }
    if (props.projectId) params.project_id = props.projectId
    if (props.year) params.year = props.year
    const data = await api.get('/api/metabase/embed-url', { params })
    const result = data
    embedUrl.value = result.embed_url || ''
  } catch { embedUrl.value = '' }
  finally { loading.value = false }
}

function refresh() { loadDashboard() }

onMounted(loadDashboards)
</script>

<style scoped>
.gt-metabase { height: 100%; display: flex; flex-direction: column; }
.gt-mb-header {
  display: flex; gap: var(--gt-space-2); align-items: center;
  padding: var(--gt-space-2) var(--gt-space-3);
  border-bottom: 1px solid var(--gt-color-border-light); flex-shrink: 0;
}
.gt-mb-body { flex: 1; min-height: 0; }
.gt-mb-iframe { width: 100%; height: 100%; border: none; border-radius: var(--gt-radius-md); }
</style>
