<template>
  <div class="version-timeline">
    <h4>版本链</h4>
    <el-timeline v-if="stamps.length">
      <el-timeline-item
        v-for="s in stamps" :key="s.id"
        :timestamp="formatTime(s.created_at)"
        :type="objectTypeColor(s.object_type)"
        placement="top"
      >
        <div class="stamp-card">
          <span class="stamp-icon">{{ objectTypeIcon(s.object_type) }}</span>
          <span class="stamp-type">{{ s.object_type }}</span>
          <el-tag size="small">v{{ s.version_no }}</el-tag>
          <span class="stamp-id" :title="s.object_id">{{ s.object_id?.substring(0, 8) }}...</span>
        </div>
        <div class="stamp-trace" v-if="s.trace_id">
          <span>trace: {{ s.trace_id }}</span>
        </div>
      </el-timeline-item>
    </el-timeline>
    <el-empty v-else description="暂无版本记录" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import { queryVersionLine } from '@/services/governanceApi'

const props = defineProps<{
  projectId: string
  objectType?: string
  objectId?: string
}>()

const stamps = ref<any[]>([])

async function loadData() {
  try {
    const result = await queryVersionLine(props.projectId, props.objectType, props.objectId)
    stamps.value = result.items || []
  } catch (e) { handleApiError(e, '加载版本链失败') }
}

function objectTypeIcon(t: string) {
  const m: Record<string, string> = { report: '📊', note: '📝', workpaper: '📋', procedure: '📌' }
  return m[t] || '📄'
}
function objectTypeColor(t: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const m: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = { report: 'primary', note: 'success', workpaper: 'warning', procedure: 'danger' }
  return m[t] || ''
}
function formatTime(t: string) {
  if (!t) return ''
  return new Date(t).toLocaleString('zh-CN')
}

onMounted(loadData)
watch(() => [props.projectId, props.objectType, props.objectId], loadData)
</script>

<style scoped>
.version-timeline { padding: 16px; }
.stamp-card { display: flex; align-items: center; gap: 8px; }
.stamp-icon { font-size: 16px; }
.stamp-type { font-size: 13px; color: #666; }
.stamp-id { font-size: 12px; color: #999; font-family: monospace; }
.stamp-trace { font-size: 11px; color: #bbb; margin-top: 2px; }
</style>
