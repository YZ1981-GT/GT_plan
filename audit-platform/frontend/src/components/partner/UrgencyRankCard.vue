<template>
  <div class="gt-urgency-rank">
    <div class="gt-urgency-header">
      <span class="gt-urgency-title">项目紧急度排行</span>
      <el-button size="small" text @click="loadData">
        <el-icon><span>↻</span></el-icon>
      </el-button>
    </div>

    <div v-if="loading" v-loading="true" style="min-height: 120px;" />
    <div v-else-if="projects.length === 0" class="gt-urgency-empty">
      <el-empty description="暂无项目数据" :image-size="60" />
    </div>
    <div v-else class="gt-urgency-list">
      <div
        v-for="item in projects"
        :key="item.project_id"
        class="gt-urgency-item"
        @click="$emit('project-click', item.project_id)"
      >
        <div class="gt-urgency-score-badge" :class="`gt-urgency-${item.urgency_label}`">
          {{ item.urgency_score }}
        </div>
        <div class="gt-urgency-info">
          <div class="gt-urgency-name">{{ item.project_name }}</div>
          <div class="gt-urgency-client">{{ item.client_name }}</div>
          <div class="gt-urgency-metrics">{{ item.key_metrics_summary }}</div>
        </div>
        <el-tag
          size="small"
          :type="labelTagType(item.urgency_label)"
          effect="dark"
        >
          {{ labelText(item.urgency_label) }}
        </el-tag>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/services/apiProxy'

interface UrgencyItem {
  project_id: string
  project_name: string
  client_name: string
  urgency_score: number
  urgency_label: 'urgent' | 'attention' | 'normal' | 'safe'
  sla_days_remaining: number | null
  blocking_vr_count: number
  incomplete_wp_ratio: number
  key_metrics_summary: string
}

defineEmits<{
  (e: 'project-click', projectId: string): void
}>()

const loading = ref(false)
const projects = ref<UrgencyItem[]>([])

function labelTagType(label: string): 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  switch (label) {
    case 'urgent': return 'danger'
    case 'attention': return 'warning'
    case 'normal': return 'primary'
    case 'safe': return 'success'
    default: return 'info'
  }
}

function labelText(label: string) {
  switch (label) {
    case 'urgent': return '紧急'
    case 'attention': return '关注'
    case 'normal': return '一般'
    case 'safe': return '正常'
    default: return label
  }
}

async function loadData() {
  loading.value = true
  try {
    const res = await api.get('/api/partner/projects/urgency') as { projects: UrgencyItem[] }
    projects.value = res.projects || []
  } catch {
    projects.value = []
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.gt-urgency-rank {
  border: 1px solid var(--gt-color-border-light);
  border-radius: var(--gt-radius-md);
  padding: 16px;
  background: var(--gt-color-bg-white);
}
.gt-urgency-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.gt-urgency-title { font-weight: 600; font-size: 14px; }
.gt-urgency-list { display: flex; flex-direction: column; gap: 8px; }
.gt-urgency-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--gt-color-border-light);
  border-radius: var(--gt-radius-sm);
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s;
}
.gt-urgency-item:hover {
  background: var(--gt-color-bg-hover);
  border-color: var(--gt-color-primary, #4b2d77);
}
.gt-urgency-score-badge {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
}
.gt-urgency-urgent { background: #D32F2F; }
.gt-urgency-attention { background: #EF6C00; }
.gt-urgency-normal { background: #F9A825; }
.gt-urgency-safe { background: #4CAF50; }
.gt-urgency-info { flex: 1; min-width: 0; }
.gt-urgency-name { font-weight: 500; font-size: 13px; }
.gt-urgency-client { font-size: 12px; color: var(--gt-color-text-secondary); }
.gt-urgency-metrics { font-size: 11px; color: var(--gt-color-text-tertiary); margin-top: 2px; }
.gt-urgency-empty { padding: 20px; text-align: center; }
</style>
