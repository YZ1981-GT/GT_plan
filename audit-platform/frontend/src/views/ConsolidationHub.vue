<template>
  <div class="gt-hub">
    <div class="gt-hub-header">
      <h2>合并项目</h2>
    </div>
    <p class="gt-hub-desc">管理集团合并报表项目。选择一个合并项目查看合并范围、抵消分录、合并试算等。</p>

    <div v-loading="loading">
      <el-empty v-if="!loading && projects.length === 0" description="暂无合并项目">
        <el-button type="primary" @click="$router.push('/projects/new')">新建合并项目</el-button>
      </el-empty>

      <div v-else class="gt-hub-grid">
        <div
          v-for="p in projects"
          :key="p.id"
          class="gt-hub-card"
          @click="$router.push(`/projects/${p.id}/consolidation`)"
        >
          <div class="gt-hub-card-top">
            <el-icon :size="24" style="color: var(--gt-color-primary)"><Connection /></el-icon>
            <el-tag :type="statusType(p.status)" size="small">{{ statusLabel(p.status) }}</el-tag>
          </div>
          <div class="gt-hub-card-name">{{ p.client_name || p.name }}</div>
          <div class="gt-hub-card-meta">
            <span>{{ p.audit_year || '' }}年度</span>
            <span v-if="p.consol_level">{{ p.consol_level }}级</span>
          </div>
          <div class="gt-hub-card-sub" v-if="p.child_count">
            包含 {{ p.child_count }} 个子公司
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Connection } from '@element-plus/icons-vue'
import http from '@/utils/http'

const loading = ref(false)
const projects = ref<any[]>([])

function statusType(s: string) {
  return { created: 'info', planning: '', execution: 'warning', completion: 'success', archived: 'info' }[s] || 'info'
}
function statusLabel(s: string) {
  return { created: '已创建', planning: '计划中', execution: '执行中', completion: '完成', archived: '已归档' }[s] || s
}

onMounted(async () => {
  loading.value = true
  try {
    const { data } = await http.get('/api/projects')
    const all = Array.isArray(data) ? data : data?.items || []
    // 筛选合并项目（report_scope=consolidated 或有子项目）
    projects.value = all.filter((p: any) =>
      p.report_scope === 'consolidated' || p.parent_project_id === null && p.consol_level > 0
    )
    // 如果没有合并项目，显示所有项目供选择
    if (projects.value.length === 0) projects.value = all
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
.gt-hub-card:hover { border-color: var(--gt-color-primary, #4b2d77); box-shadow: 0 4px 12px rgba(75,45,119,0.1); transform: translateY(-2px); }
.gt-hub-card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.gt-hub-card-name { font-size: 16px; font-weight: 600; color: #333; margin-bottom: 6px; }
.gt-hub-card-meta { font-size: 13px; color: #999; display: flex; gap: 12px; }
.gt-hub-card-sub { font-size: 12px; color: var(--gt-color-primary); margin-top: 8px; }
</style>
