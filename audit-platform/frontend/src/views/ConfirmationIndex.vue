<template>
  <div class="confirmation-index">
    <div class="page-header">
      <div class="page-header-left">
        <h2>函证管理</h2>
        <span class="page-header-count" v-if="projects.length">共 {{ projects.length }} 个项目</span>
      </div>
      <el-input
        v-model="searchText"
        placeholder="搜索项目名称"
        prefix-icon="Search"
        clearable
        style="width: 240px"
      />
    </div>

    <div v-loading="loading" class="page-body">
      <GtEmpty v-if="!loading && filteredProjects.length === 0" preset="no-data" title="暂无项目" />

      <el-table
        v-else
        :data="filteredProjects"
        class="gt-compact-table confirmation-table"
        @row-click="goToProject"
        highlight-current-row
        stripe
      >
        <el-table-column label="项目" min-width="280">
          <template #default="{ row }">
            <div class="project-cell">
              <div class="project-avatar">
                <el-icon :size="18"><Stamp /></el-icon>
              </div>
              <div class="project-info">
                <div class="project-name">{{ row.client_name || row.name }}</div>
                <div class="project-sub" v-if="showSub(row)">{{ subText(row) }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="年度" width="90" align="center">
          <template #default="{ row }">
            <span class="year-badge">{{ row.audit_year || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="120" align="center">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" class="type-tag">{{ typeLabel(row.project_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <GtStatusTag dict-key="project_status" :value="row.status" />
          </template>
        </el-table-column>
        <el-table-column label="" width="80" align="center">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click.stop="goToProject(row)">
              进入 →
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Stamp } from '@element-plus/icons-vue'
import { listProjects } from '@/services/commonApi'
import GtEmpty from '@/components/common/GtEmpty.vue'
import GtStatusTag from '@/components/common/GtStatusTag.vue'

const router = useRouter()
const loading = ref(false)
const projects = ref<any[]>([])
const searchText = ref('')

const TYPE_MAP: Record<string, string> = {
  annual: '年度审计',
  interim: '中期审计',
  special: '专项审计',
  ipo: 'IPO审计',
  internal_control: '内控审计',
}

const filteredProjects = computed(() => {
  if (!searchText.value) return projects.value
  const kw = searchText.value.toLowerCase()
  return projects.value.filter(p =>
    (p.client_name || '').toLowerCase().includes(kw) ||
    (p.name || '').toLowerCase().includes(kw)
  )
})

function typeLabel(type: string) {
  return TYPE_MAP[type] || type || '—'
}

function showSub(row: any): boolean {
  // 如果 name 和 client_name 实质相同（含年份后缀），不显示子标题
  const name = (row.name || '').replace(/_\d{4}$/, '').trim()
  const client = (row.client_name || '').trim()
  return name !== client && !!row.name && row.name !== row.client_name
}

function subText(row: any): string {
  // 显示项目负责人或项目编号（如果有）
  if (row.manager_name) return `负责人：${row.manager_name}`
  if (row.project_code) return row.project_code
  // fallback: 显示 name 中不重复的部分
  return row.name || ''
}

function goToProject(row: any) {
  router.push(`/projects/${row.id}/confirmation`)
}

onMounted(async () => {
  loading.value = true
  try {
    projects.value = await listProjects()
  } catch { /* silent */ }
  loading.value = false
})
</script>

<style scoped>
.confirmation-index {
  padding: 24px 32px;
  max-width: 1200px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.page-header-left {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.page-header-left h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--gt-color-text-primary, #1a1a1a);
}
.page-header-count {
  font-size: 13px;
  color: var(--gt-color-text-tertiary, #999);
}

.page-body {
  min-height: 200px;
}

.confirmation-table {
  border-radius: 8px;
  overflow: hidden;
}
.confirmation-table :deep(tr) {
  cursor: pointer;
}
.confirmation-table :deep(th .cell) {
  font-weight: 600;
  color: var(--gt-color-text-secondary, #666);
  font-size: 13px;
}

.project-cell {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 0;
}
.project-avatar {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: var(--gt-purple-light, #f4f0fa);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--gt-purple, #4b2d77);
}
.project-info {
  min-width: 0;
}
.project-name {
  font-weight: 600;
  font-size: 13px;
  color: var(--gt-color-text-primary, #1a1a1a);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.project-sub {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #aaa);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.year-badge {
  font-weight: 600;
  color: var(--gt-color-text-primary, #333);
}

.type-tag {
  border-color: var(--gt-purple-border, #d8b8ee);
  color: var(--gt-purple, #4b2d77);
  background: var(--gt-purple-light, #f4f0fa);
}
</style>
