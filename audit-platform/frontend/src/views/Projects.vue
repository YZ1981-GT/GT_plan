<template>
  <div class="gt-projects gt-fade-in">
    <!-- 紧凑头部 -->
    <div class="gt-projects-header">
      <h2 class="gt-projects-title">项目列表</h2>
      <div class="gt-projects-actions">
        <el-button type="primary" size="small" @click="goToCreateProject">
          <el-icon><Plus /></el-icon> 新建项目
        </el-button>
        <el-button size="small" plain @click="showBatchImport = true">
          <el-icon><Upload /></el-icon> 批量建项
        </el-button>
        <el-button size="small" text @click="$router.push('/projects')">
          返回三栏
        </el-button>
      </div>
    </div>

    <!-- 筛选栏 -->
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
      <span style="margin-left: auto; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary)">共 {{ projects.length }} 个项目</span>
    </div>

    <!-- 列表视图 -->
    <el-table
      v-if="viewMode === 'list'"
      :data="projects"
      v-loading="loading"
      stripe
      border
      size="small"
      :header-cell-style="{ fontWeight: 600, background: 'var(--gt-color-primary-bg, #f4f0fa)' }"
      empty-text="暂无项目，点击上方「新建项目」开始"
      style="width: 100%"
      @row-click="(row) => openProject(row.id)"
      :row-style="{ cursor: 'pointer' }"
    >
      <el-table-column prop="name" label="项目名称" min-width="220">
        <template #default="{ row }">
          <div style="display: flex; align-items: center; gap: 6px">
            <span class="project-dot" :class="'dot-' + (row.status || 'created')"></span>
            <span style="font-weight: 500">{{ getProjectDisplayName(row, projects, consolidatedKeys) || '—' }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="short_name" label="简称" width="120">
        <template #default="{ row }">
          <span style="color: var(--gt-color-primary)">{{ row.short_name || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="client_name" label="客户名称" min-width="180">
        <template #default="{ row }">
          <span class="gt-text-secondary">{{ row.client_name || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="project_type" label="项目类型" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="getProjectTypeTag(row.project_type)" size="small" effect="light" round>
            {{ getProjectTypeLabel(row.project_type) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="getStatusTag(row.status)" size="small" effect="plain" round>
            {{ getStatusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="120" align="center">
        <template #default="{ row }">
          <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary)">{{ formatDate(row.created_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" align="center" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" size="small" text @click.stop="openImport(row.id)">账套导入</el-button>
          <el-button type="primary" size="small" text @click.stop="openProject(row.id)">进入</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 按客户分组视图 -->
    <div v-else-if="viewMode === 'client'" v-loading="loading">
      <el-collapse v-if="clientGroups.length > 0">
        <el-collapse-item v-for="group in clientGroups" :key="group.client" :name="group.client">
          <template #title>
            <span style="font-weight: 600; color: var(--gt-color-primary)">{{ group.client }}</span>
            <el-tag size="small" style="margin-left: 8px">{{ group.projects.length }} 个项目</el-tag>
          </template>
          <div v-for="p in group.projects" :key="p.id" class="gt-client-project-item" @click="openProject(p.id)">
            <span class="project-dot" :class="'dot-' + (p.status || 'created')"></span>
            <span style="flex: 1; font-weight: 500">{{ p.short_name || p.name }}</span>
            <el-tag :type="getStatusTag(p.status)" size="small" effect="plain" round>{{ getStatusLabel(p.status) }}</el-tag>
            <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-left: 12px">{{ formatDate(p.created_at) }}</span>
            <el-button type="primary" size="small" text style="margin-left: 8px" @click.stop="openProject(p.id)">进入</el-button>
          </div>
        </el-collapse-item>
      </el-collapse>
      <el-empty v-else description="暂无项目" />
    </div>

    <!-- 批量建项弹窗 -->
    <BatchImportDialog
      v-model="showBatchImport"
      @success="loadProjectList"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { listProjects } from '@/services/commonApi'
import { FolderOpened, Plus, Upload } from '@element-plus/icons-vue'
import { getProjectDisplayName, buildConsolidatedKeySet } from '@/utils/project_display'
import BatchImportDialog from '@/components/wizard/BatchImportDialog.vue'

const router = useRouter()
const loading = ref(false)
const projects = ref<any[]>([])
const showBatchImport = ref(false)

// 预计算合并项目 key 集合，避免每行 O(N) 扫描
const consolidatedKeys = computed(() => buildConsolidatedKeySet(projects.value))

// R7-S3-06 Task 33：筛选状态
const viewMode = ref<'list' | 'client'>('list')
const filterStatus = ref('')
const filterTag = ref('')
const searchText = ref('')
const availableTags = ref(['年审', '季审', '上市准备', '内审', '专项', '税审', '国企', '上市公司'])

// 按客户分组
const clientGroups = computed(() => {
  const map = new Map<string, any[]>()
  for (const p of projects.value) {
    const key = p.client_name || '未归类'
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(p)
  }
  return [...map.entries()].map(([client, items]) => ({ client, projects: items }))
})

onMounted(() => loadProjectList())

async function loadProjectList() {
  loading.value = true
  try {
    projects.value = await listProjects()
  } catch { /* ignore */ }
  finally { loading.value = false }
}

function goToCreateProject() { router.push('/projects/new') }
function openProject(id: string) { router.push({ name: 'ProjectEntry', params: { projectId: id } }) }
function openImport(id: string) {
  router.push({ path: `/projects/${id}/ledger-import` })
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
  max-width: 1400px;
  margin: 0 auto;
  padding: 16px 24px;
}
.gt-projects-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.gt-projects-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--gt-color-primary, #4b2d77);
  margin: 0;
}
.gt-projects-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gt-projects-filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: var(--gt-color-primary-bg, #f4f0fa);
  border-radius: 8px;
}

/* 状态圆点 */
.project-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
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

/* 按客户分组 - 项目行 */
.gt-client-project-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  cursor: pointer;
  border-bottom: 1px solid var(--gt-color-border-light, #f0f0f0);
  transition: background 0.15s;
}
.gt-client-project-item:hover {
  background: var(--gt-color-primary-bg, #f4f0fa);
}
.gt-client-project-item:last-child {
  border-bottom: none;
}
</style>
