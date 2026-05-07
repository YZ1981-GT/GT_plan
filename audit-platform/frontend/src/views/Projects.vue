<template>
  <div class="gt-projects gt-fade-in">
    <!-- 页头 [R7-S3-01] -->
    <GtPageHeader title="项目列表" :show-back="false">
      <template #actions>
        <el-button type="primary" size="small" @click="goToCreateProject">
          <el-icon><Plus /></el-icon> 新建项目
        </el-button>
      </template>
    </GtPageHeader>

    <!-- 筛选栏 [R7-S3-06 Task 33] -->
    <div class="gt-projects-filter-bar">
      <el-radio-group v-model="viewMode" size="small" style="margin-right: 12px">
        <el-radio-button value="list">列表</el-radio-button>
        <el-radio-button value="client">按客户</el-radio-button>
      </el-radio-group>
      <el-select v-model="filterStatus" placeholder="状态" clearable size="small" style="width: 120px">
        <el-option label="活跃" value="active" />
        <el-option label="已归档" value="archived" />
        <el-option label="全部" value="" />
      </el-select>
      <el-select v-model="filterTag" placeholder="标签" clearable size="small" style="width: 120px; margin-left: 8px">
        <el-option v-for="t in availableTags" :key="t" :label="t" :value="t" />
      </el-select>
      <el-input v-model="searchText" placeholder="搜索项目/客户..." clearable size="small" style="width: 200px; margin-left: 8px" />
    </div>

    <!-- 表格卡片 -->
    <el-card class="gt-scale-in" shadow="never">
      <el-table
        :data="projects"
        v-loading="loading"
        stripe
        size="default"
        :header-cell-style="{ fontWeight: 600 }"
        empty-text="暂无项目，点击右上角「新建项目」开始"
        style="width: 100%"
      >
        <el-table-column prop="name" label="项目名称" min-width="200">
          <template #default="{ row }">
            <div class="project-name-cell">
              <div class="project-dot" :class="'dot-' + (row.status || 'created')"></div>
              <span class="project-name-text">{{ row.name || '—' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="client_name" label="客户名称" min-width="150">
          <template #default="{ row }">
            <span class="gt-text-secondary">{{ row.client_name || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="project_type" label="项目类型" width="130" align="center">
          <template #default="{ row }">
            <el-tag
              :type="getProjectTypeTag(row.project_type)"
              size="small"
              effect="light"
              round
            >
              {{ getProjectTypeLabel(row.project_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag
              :type="getStatusTag(row.status)"
              size="small"
              effect="plain"
              round
            >
              <span class="status-dot" :class="'dot-' + (row.status || 'created')"></span>
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="140" align="center">
          <template #default="{ row }">
            <span class="gt-text-secondary" style="font-size: 13px">{{ formatDate(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" align="center" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" text @click="openImport(row.id)">
              <el-icon><Upload /></el-icon>
              账套导入
            </el-button>
            <el-button type="primary" size="small" text @click="openProject(row.id)">
              <el-icon><Right /></el-icon>
              进入
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { listProjects } from '@/services/commonApi'
import { FolderOpened, Plus, Right, Upload } from '@element-plus/icons-vue'
import GtPageHeader from '@/components/common/GtPageHeader.vue'

const router = useRouter()
const loading = ref(false)
const projects = ref<any[]>([])

// R7-S3-06 Task 33：筛选状态
const viewMode = ref<'list' | 'client'>('list')
const filterStatus = ref('')
const filterTag = ref('')
const searchText = ref('')
const availableTags = ref(['年审', '季审', '上市准备', '内审', '专项', '税审', '国企', '上市公司'])

onMounted(() => loadProjectList())

async function loadProjectList() {
  loading.value = true
  try {
    projects.value = await listProjects()
  } catch { /* ignore */ }
  finally { loading.value = false }
}

function goToCreateProject() { router.push('/projects/new') }
function openProject(id: string) { router.push(`/projects/${id}/trial-balance`) }
function openImport(id: string) {
  router.push({ path: `/projects/${id}/ledger`, query: { import: '1' } })
}

function formatDate(d: string) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

function getProjectTypeTag(t: string) {
  return ({ annual: '', special: 'warning', ipo: 'success', internal_control: 'info' } as any)[t] || ''
}
function getProjectTypeLabel(t: string) {
  return ({ annual: '年度审计', special: '专项审计', ipo: 'IPO审计', internal_control: '内控审计' } as any)[t] || t || '—'
}
function getStatusTag(s: string) {
  return ({ created: 'info', planning: 'warning', execution: '', completion: 'success', archived: 'info' } as any)[s] || ''
}
function getStatusLabel(s: string) {
  return ({ created: '已创建', planning: '计划中', execution: '执行中', completion: '已完成', archived: '已归档' } as any)[s] || s || '—'
}
</script>

<style scoped>
.gt-projects {
  max-width: 1200px;
}

.projects-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--gt-space-5);
}

/* 项目名称单元格 */
.project-name-cell {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
}

.project-name-text {
  font-weight: 500;
  color: var(--gt-color-text);
}

/* 状态圆点 */
.project-dot,
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  display: inline-block;
}

.status-dot {
  width: 6px;
  height: 6px;
  margin-right: 4px;
}

.dot-created { background: var(--gt-color-text-tertiary); }
.dot-planning { background: var(--gt-color-wheat); }
.dot-execution { background: var(--gt-color-primary); animation: gtPulse 2s ease-in-out infinite; }
.dot-completion { background: var(--gt-color-success); }
.dot-archived { background: var(--gt-color-border); }

@keyframes gtPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>
