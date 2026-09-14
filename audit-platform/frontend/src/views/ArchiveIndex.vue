<template>
  <div class="archive-index">
    <div class="page-header">
      <div class="page-header-left">
        <h2>归档管理</h2>
        <span class="page-header-count" v-if="projects.length">共 {{ projects.length }} 个项目</span>
      </div>
      <div class="page-header-right">
        <el-radio-group v-model="statusFilter" size="small">
          <el-radio-button label="all">全部</el-radio-button>
          <el-radio-button label="active">进行中</el-radio-button>
          <el-radio-button label="archived">已归档</el-radio-button>
        </el-radio-group>
        <el-input
          v-model="searchText"
          placeholder="搜索项目"
          prefix-icon="Search"
          clearable
          style="width: 200px"
        />
      </div>
    </div>

    <div v-loading="loading" class="page-body">
      <GtEmpty v-if="!loading && filteredProjects.length === 0" preset="no-data" title="暂无项目" />

      <div v-else class="archive-grid">
        <div
          v-for="p in filteredProjects"
          :key="p.id"
          class="archive-card"
          :class="{ 'is-archived': isArchived(p) }"
          @click="goToProject(p)"
        >
          <div class="archive-card-head">
            <div class="archive-card-icon">
              <el-icon :size="20"><Box /></el-icon>
            </div>
            <GtStatusTag dict-key="project_status" :value="p.status" />
          </div>

          <div class="archive-card-name" :title="p.client_name || p.name">
            {{ p.client_name || p.name }}
          </div>

          <div class="archive-card-meta">
            <span class="meta-item">{{ p.audit_year || '—' }} 年度</span>
            <span class="meta-dot">·</span>
            <span class="meta-item">{{ typeLabel(p.project_type) }}</span>
          </div>

          <div class="archive-card-progress">
            <el-progress
              :percentage="progressOf(p)"
              :stroke-width="6"
              :color="progressColor(p)"
              :show-text="false"
            />
            <span class="progress-label">归档进度 {{ progressOf(p) }}%</span>
          </div>

          <div class="archive-card-footer">
            <span class="footer-person" v-if="p.manager_name">
              <el-icon :size="13"><User /></el-icon>
              {{ p.manager_name }}
            </span>
            <span class="footer-action">进入归档 →</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Box, User } from '@element-plus/icons-vue'
import { listProjectsWithProgress, listProjects } from '@/services/commonApi'
import GtEmpty from '@/components/common/GtEmpty.vue'
import GtStatusTag from '@/components/common/GtStatusTag.vue'

const router = useRouter()
const loading = ref(false)
const projects = ref<any[]>([])
const searchText = ref('')
const statusFilter = ref<'all' | 'active' | 'archived'>('all')

const TYPE_MAP: Record<string, string> = {
  annual: '年度审计',
  interim: '中期审计',
  special: '专项审计',
  ipo: 'IPO审计',
  internal_control: '内控审计',
}

const ARCHIVED_STATUSES = ['archived', 'completed', 'closed']

function isArchived(p: any): boolean {
  return ARCHIVED_STATUSES.includes(p.status)
}

const filteredProjects = computed(() => {
  let list = projects.value
  if (statusFilter.value === 'active') {
    list = list.filter(p => !isArchived(p))
  } else if (statusFilter.value === 'archived') {
    list = list.filter(p => isArchived(p))
  }
  if (searchText.value) {
    const kw = searchText.value.toLowerCase()
    list = list.filter(p =>
      (p.client_name || '').toLowerCase().includes(kw) ||
      (p.name || '').toLowerCase().includes(kw)
    )
  }
  return list
})

function typeLabel(type: string) {
  return TYPE_MAP[type] || type || '—'
}

function progressOf(p: any): number {
  const v = p.overall_progress ?? p.progress ?? 0
  return Math.round(Math.max(0, Math.min(100, v)))
}

function progressColor(p: any): string {
  const v = progressOf(p)
  if (v >= 100) return '#67c23a'
  if (v >= 60) return '#4b2d77'
  if (v >= 30) return '#e6a23c'
  return '#c0c0c0'
}

function goToProject(p: any) {
  router.push(`/projects/${p.id}/archive`)
}

onMounted(async () => {
  loading.value = true
  try {
    projects.value = await listProjectsWithProgress()
    if (!projects.value.length) {
      projects.value = await listProjects()
    }
  } catch {
    try { projects.value = await listProjects() } catch { /* silent */ }
  }
  loading.value = false
})
</script>

<style scoped>
.archive-index {
  padding: 24px 32px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  flex-wrap: wrap;
  gap: 12px;
}
.page-header-left {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.page-header-left h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--gt-color-text-primary, #1a1a1a);
}
.page-header-count {
  font-size: 13px;
  color: var(--gt-color-text-tertiary, #999);
}
.page-header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-body {
  min-height: 200px;
}

.archive-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.archive-card {
  background: var(--gt-color-bg-white, #fff);
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  border-radius: 12px;
  padding: 18px;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.archive-card:hover {
  border-color: var(--gt-purple, #4b2d77);
  box-shadow: 0 6px 20px rgba(75, 45, 119, 0.12);
  transform: translateY(-3px);
}
.archive-card.is-archived {
  background: var(--gt-color-bg-page, #fafafa);
}

.archive-card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.archive-card-icon {
  width: 36px;
  height: 36px;
  border-radius: 9px;
  background: var(--gt-purple-light, #f4f0fa);
  color: var(--gt-purple, #4b2d77);
  display: flex;
  align-items: center;
  justify-content: center;
}

.archive-card-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--gt-color-text-primary, #1a1a1a);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.archive-card-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #999);
}
.meta-dot { color: var(--gt-color-border, #ddd); }

.archive-card-progress {
  margin-top: 4px;
}
.progress-label {
  display: block;
  font-size: 12px;
  color: var(--gt-color-text-secondary, #666);
  margin-top: 6px;
}

.archive-card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 6px;
  padding-top: 10px;
  border-top: 1px solid var(--gt-color-border-lighter, #f0f0f0);
}
.footer-person {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #999);
}
.footer-action {
  font-size: 12px;
  font-weight: 600;
  color: var(--gt-purple, #4b2d77);
}
</style>
