<template>
  <div class="gt-projects-page">
    <!-- Page Header -->
    <div class="page-header">
      <h2 class="page-title gt-text-primary">项目列表</h2>
      <div class="header-actions">
        <el-button type="primary" @click="onNewProject">新建项目</el-button>
      </div>
    </div>

    <!-- Stats Row -->
    <div class="stats-row">
      <div class="stat-card gt-card">
        <span class="stat-num gt-text-primary">{{ projects.length }}</span>
        <span class="stat-label">项目总数</span>
      </div>
      <div class="stat-card gt-card">
        <span class="stat-num gt-text-teal">{{ activeCount }}</span>
        <span class="stat-label">进行中</span>
      </div>
      <div class="stat-card gt-card">
        <span class="stat-num gt-text-coral">{{ reviewCount }}</span>
        <span class="stat-label">待复核</span>
      </div>
    </div>

    <!-- Project Table -->
    <div class="gt-card table-card" v-loading="loading">
      <el-table
        :data="projects"
        border
        stripe
        style="width: 100%"
        row-key="id"
        :expand-row-keys="expandedRows"
        @row-click="onRowClick"
        default-expand-all
      >
        <!-- Expandable Details -->
        <el-table-column type="expand" width="50">
          <template #default="{ row }">
            <div class="expand-content">
              <div class="expand-grid">
                <div class="expand-item">
                  <span class="expand-label">项目ID</span>
                  <span class="expand-value">{{ row.id }}</span>
                </div>
                <div class="expand-item">
                  <span class="expand-label">客户名称</span>
                  <span class="expand-value">{{ row.client_name }}</span>
                </div>
                <div class="expand-item">
                  <span class="expand-label">审计年度</span>
                  <span class="expand-value">{{ row.year }} 年</span>
                </div>
                <div class="expand-item">
                  <span class="expand-label">项目类型</span>
                  <span class="expand-value">{{ row.is_group ? '集团项目' : '单体项目' }}</span>
                </div>
                <div class="expand-item">
                  <span class="expand-label">审计经理</span>
                  <span class="expand-value">{{ row.manager || '—' }}</span>
                </div>
                <div class="expand-item">
                  <span class="expand-label">合伙人</span>
                  <span class="expand-value">{{ row.partner || '—' }}</span>
                </div>
              </div>
              <div class="expand-actions" v-if="row.is_group">
                <el-button
                  type="primary"
                  size="small"
                  @click.stop="goConsolidation(row)"
                >
                  进入集团合并
                </el-button>
              </div>
            </div>
          </template>
        </el-table-column>

        <!-- Project Name -->
        <el-table-column label="项目名称" min-width="200">
          <template #default="{ row }">
            <div class="project-name-cell">
              <span class="project-name">{{ row.name }}</span>
              <el-tag v-if="row.is_group" type="warning" size="small" class="group-tag">集团</el-tag>
            </div>
          </template>
        </el-table-column>

        <!-- Client Name -->
        <el-table-column prop="client_name" label="客户名称" min-width="160" />

        <!-- Status -->
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <!-- Year -->
        <el-table-column prop="year" label="年度" width="90" align="center" />

        <!-- Consolidation Action -->
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-tooltip
              v-if="row.is_group"
              content="集团合并"
              placement="top"
              :show-after="300"
            >
              <router-link
                :to="`/projects/${row.id}/consolidation?year=${row.year}`"
                custom
                #default="{ navigate }"
              >
                <el-button
                  type="primary"
                  size="small"
                  :icon="Connection"
                  circle
                  @click.stop="navigate"
                />
              </router-link>
            </el-tooltip>
            <span v-else class="no-action">—</span>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && projects.length === 0" description="暂无项目，请先创建" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Connection } from '@element-plus/icons-vue'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface Project {
  id: string
  name: string
  client_name: string
  status: 'draft' | 'active' | 'review' | 'completed' | 'archived'
  year: number
  is_group: boolean
  manager?: string
  partner?: string
}

// ─── Mock Data ────────────────────────────────────────────────────────────────

const MOCK_PROJECTS: Project[] = [
  {
    id: 'proj-001',
    name: '致同科技集团 2024 年度审计',
    client_name: '致同科技集团有限公司',
    status: 'active',
    year: 2024,
    is_group: true,
    manager: '张明',
    partner: '李华',
  },
  {
    id: 'proj-002',
    name: '华兴制造 2024 年度审计',
    client_name: '华兴制造有限公司',
    status: 'review',
    year: 2024,
    is_group: false,
    manager: '王芳',
    partner: '李华',
  },
  {
    id: 'proj-003',
    name: '中金股份集团 2023 年度审计',
    client_name: '中金股份有限公司',
    status: 'completed',
    year: 2023,
    is_group: true,
    manager: '赵强',
    partner: '陈红',
  },
  {
    id: 'proj-004',
    name: '东方物流 2024 年度审计',
    client_name: '东方物流有限公司',
    status: 'draft',
    year: 2024,
    is_group: false,
    manager: '孙丽',
    partner: '李华',
  },
  {
    id: 'proj-005',
    name: '北方能源集团 2024 年度审计',
    client_name: '北方能源集团有限公司',
    status: 'active',
    year: 2024,
    is_group: true,
    manager: '周杰',
    partner: '陈红',
  },
]

// ─── State ───────────────────────────────────────────────────────────────────

const loading = ref(false)
const projects = ref<Project[]>([])
const expandedRows = ref<string[]>([])

// ─── Computed ───────────────────────────────────────────────────────────────

const activeCount = computed(() => projects.value.filter(p => p.status === 'active').length)
const reviewCount = computed(() => projects.value.filter(p => p.status === 'review').length)

// ─── Status Helpers ──────────────────────────────────────────────────────────

const STATUS_TAG_MAP: Record<string, string> = {
  draft: 'info',
  active: 'success',
  review: 'warning',
  completed: '',
  archived: 'info',
}

const STATUS_LABEL_MAP: Record<string, string> = {
  draft: '草稿',
  active: '进行中',
  review: '待复核',
  completed: '已完成',
  archived: '已归档',
}

function statusTagType(status: string): string {
  return STATUS_TAG_MAP[status] || 'info'
}

function statusLabel(status: string): string {
  return STATUS_LABEL_MAP[status] || status
}

// ─── Row Expansion ───────────────────────────────────────────────────────────

function onRowClick(row: Project) {
  const idx = expandedRows.value.indexOf(row.id)
  if (idx >= 0) {
    expandedRows.value.splice(idx, 1)
  } else {
    expandedRows.value.push(row.id)
  }
}

// ─── Navigation ──────────────────────────────────────────────────────────────

const router = useRouter()

function goConsolidation(project: Project) {
  router.push(`/projects/${project.id}/consolidation?year=${project.year}`)
}

function onNewProject() {
  router.push('/projects/new')
}

// ─── Init ────────────────────────────────────────────────────────────────────

async function fetchProjects() {
  loading.value = true
  try {
    // TODO: replace with API call when backend /api/projects endpoint is ready
    // const data = await getProjects()
    // projects.value = data
    await new Promise(resolve => setTimeout(resolve, 600)) // simulate async
    projects.value = MOCK_PROJECTS
  } finally {
    loading.value = false
  }
}

onMounted(fetchProjects)
</script>

<style scoped>
/* ─── Page Layout ─────────────────────────────────────────────────────────── */

.gt-projects-page {
  display: flex;
  flex-direction: column;
  gap: var(--gt-space-4);
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.page-title {
  margin: 0;
  font-size: 20px;
  color: var(--gt-color-primary-dark);
}

.header-actions {
  display: flex;
  gap: var(--gt-space-2);
}

/* ─── Stats ────────────────────────────────────────────────────────────────── */

.stats-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--gt-space-4);
}

.stat-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--gt-space-4) 0;
  gap: var(--gt-space-1);
}

.stat-num {
  font-size: 28px;
  font-weight: bold;
  line-height: 1;
}

.stat-label {
  font-size: 13px;
  color: #666;
}

/* ─── Table Card ───────────────────────────────────────────────────────────── */

.table-card {
  padding: var(--gt-space-4);
}

/* ─── Project Name Cell ────────────────────────────────────────────────────── */

.project-name-cell {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
}

.project-name {
  font-weight: 500;
  color: var(--gt-color-primary-dark);
}

.group-tag {
  flex-shrink: 0;
}

/* ─── No Action Placeholder ───────────────────────────────────────────────── */

.no-action {
  color: #ccc;
}

/* ─── Expand Panel ─────────────────────────────────────────────────────────── */

.expand-content {
  padding: var(--gt-space-4) var(--gt-space-6);
  background-color: #fafafa;
}

.expand-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--gt-space-3) var(--gt-space-6);
}

.expand-item {
  display: flex;
  gap: var(--gt-space-2);
  font-size: 13px;
  line-height: 1.6;
}

.expand-label {
  color: #888;
  flex-shrink: 0;
  min-width: 70px;
}

.expand-value {
  color: #333;
  word-break: break-all;
}

.expand-actions {
  margin-top: var(--gt-space-3);
  padding-top: var(--gt-space-3);
  border-top: 1px solid #eee;
  display: flex;
  gap: var(--gt-space-2);
}

/* ─── Responsive ──────────────────────────────────────────────────────────── */

@media (max-width: 768px) {
  .stats-row {
    grid-template-columns: 1fr;
  }

  .expand-grid {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
