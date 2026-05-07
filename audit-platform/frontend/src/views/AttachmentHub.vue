<template>
  <div class="gt-hub">
    <div class="gt-hub-header">
      <h2>附件管理</h2>
    </div>
    <p class="gt-hub-desc">管理项目附件文件。选择一个项目查看和管理其附件。</p>

    <div v-loading="loading">
      <el-empty v-if="!loading && projects.length === 0" description="暂无项目" />

      <div v-else class="gt-hub-grid">
        <div
          v-for="p in projects"
          :key="p.id"
          class="gt-hub-card"
          @click="$router.push(`/projects/${p.id}/attachments`)"
        >
          <div class="gt-hub-card-top">
            <el-icon :size="24" style="color: #e6a23c"><Paperclip /></el-icon>
            <el-tag :type="(statusType(p.status)) || undefined" size="small">{{ statusLabel(p.status) }}</el-tag>
          </div>
          <div class="gt-hub-card-name">{{ p.client_name || p.name }}</div>
          <div class="gt-hub-card-meta">
            <span>{{ p.audit_year || '' }}年度</span>
            <span>{{ p.project_type || '' }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Paperclip } from '@element-plus/icons-vue'
import { listProjects } from '@/services/commonApi'
import AttachmentPreviewDrawer from '@/components/common/AttachmentPreviewDrawer.vue'

// TODO: replace window.open with AttachmentPreviewDrawer when per-file preview is added to this hub view

const loading = ref(false)
const projects = ref<any[]>([])

function statusType(s: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  return ({ created: 'info', planning: '', execution: 'warning', completion: 'success', archived: 'info' } as Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'>)[s] || 'info'
}
function statusLabel(s: string) {
  return { created: '已创建', planning: '计划中', execution: '执行中', completion: '完成', archived: '已归档' }[s] || s
}

onMounted(async () => {
  loading.value = true
  try {
    projects.value = await listProjects()
  } catch { projects.value = [] }
  finally { loading.value = false }
})
</script>

<style scoped>
.gt-hub { padding: 20px; }
.gt-hub-header { margin-bottom: 8px; }
.gt-hub-header h2 { margin: 0; font-size: 20px; color: #333; }
.gt-hub-desc { color: #888; font-size: 13px; margin-bottom: 20px; }
.gt-hub-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
.gt-hub-card {
  padding: 20px; border: 1px solid #eee; border-radius: 8px; background: #fff;
  cursor: pointer; transition: all 0.2s;
}
.gt-hub-card:hover { border-color: #e6a23c; box-shadow: 0 4px 12px rgba(230,162,60,0.15); transform: translateY(-2px); }
.gt-hub-card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.gt-hub-card-name { font-size: 16px; font-weight: 600; color: #333; margin-bottom: 6px; }
.gt-hub-card-meta { font-size: 13px; color: #999; display: flex; gap: 12px; }
</style>
