<template>
  <div class="gt-plh">
    <!-- 标题栏：项目列表 + 计数 + 操作按钮 -->
    <div class="gt-plh-header">
      <div class="gt-plh-title">
        <h2>项目列表</h2>
        <span class="gt-plh-count">共 {{ projects.length }} 个项目</span>
      </div>
      <div class="gt-plh-actions">
        <!-- 项目导入 / 导出尚未开放，按钮置灰 -->
        <el-button size="small" disabled>项目导入</el-button>
        <el-button size="small" disabled>项目导出</el-button>
        <!-- 删除 / 修改已挪到每张卡片上（见下）：单击卡片即进入项目，
             不再有「选中」状态，顶栏按钮无对象可操作。 -->
        <el-button size="small" type="primary" @click="router.push('/projects/new')">新建项目</el-button>
      </div>
    </div>

    <!-- 项目卡片：单击即进入项目。
         🔴 原为「单击选中 / 双击进入」—— 用户反馈要点两下才能进。
         修改 / 删除改为卡片右侧的按钮，必须 @click.stop，否则会冒泡成「进入项目」。 -->
    <div v-loading="loading" class="gt-plh-list">
      <div
        v-for="p in projects"
        :key="p.id"
        class="gt-plh-card"
        role="link"
        tabindex="0"
        :data-testid="`plh-card-${p.id}`"
        @click="enter(p)"
        @keydown.enter="enter(p)"
      >
        <div class="gt-plh-card-main">
          <div class="gt-plh-card-title">
            <span class="gt-plh-card-name">{{ p.short_name || p.name || p.client_name || '未命名项目' }}</span>
            <el-tag v-if="typeLabel(p.project_type)" size="small" class="gt-plh-tag">{{ typeLabel(p.project_type) }}</el-tag>
          </div>
          <div class="gt-plh-card-meta">
            <span>客户：{{ p.client_name || '-' }}</span>
            <span>鉴证期间：{{ p.audit_year || '—' }}</span>
          </div>
        </div>
        <div class="gt-plh-card-side">
          <span class="gt-plh-card-date">{{ fmtDateTime(p.created_at) }}</span>
          <!-- .stop 不可省：否则点按钮会冒泡到卡片，先跳进项目 -->
          <el-button
            class="gt-plh-card-op"
            size="small"
            text
            :data-testid="`plh-edit-${p.id}`"
            @click.stop="onEdit(p)"
            @keydown.enter.stop
          >修改</el-button>
          <el-button
            class="gt-plh-card-op gt-plh-card-op--danger"
            size="small"
            text
            :data-testid="`plh-delete-${p.id}`"
            @click.stop="onDelete(p)"
            @keydown.enter.stop
          >删除</el-button>
        </div>
      </div>
      <el-empty v-if="!loading && !loadError && projects.length === 0" description="暂无项目" :image-size="80" />
      <el-empty v-if="!loading && loadError" description="项目列表加载失败" :image-size="80">
        <el-button type="primary" @click="loadProjects">重试</el-button>
      </el-empty>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import * as P from '@/services/apiPaths'
import { confirmDelete } from '@/utils/confirm'
import { getStatusLabel } from '@/constants/statusEnum'

interface ProjectItem {
  id: string
  name: string | null
  client_name: string
  short_name?: string
  project_type?: string | null
  audit_year?: number | null
  created_at?: string | null
}

const router = useRouter()
const loading = ref(false)
const loadError = ref(false)
const projects = ref<ProjectItem[]>([])

/** 项目类型中文标签；未知值不显示（不露英文枚举） */
function typeLabel(t?: string | null): string {
  if (!t) return ''
  const label = getStatusLabel('project_type', t)
  return label === t ? '' : label
}

/** 创建时间：YYYY-MM-DD HH:mm（本地时区）；无值或非法时不显示 */
function fmtDateTime(d?: string | null): string {
  if (!d) return ''
  const date = new Date(d)
  if (isNaN(date.getTime())) return ''
  const p = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())} ${p(date.getHours())}:${p(date.getMinutes())}`
}

function enter(p: ProjectItem) {
  router.push({ name: 'ProjectEntry', params: { projectId: p.id } })
}

function onEdit(p: ProjectItem) {
  router.push(`/projects/new?projectId=${p.id}`)
}

async function onDelete(p: ProjectItem) {
  try {
    await confirmDelete(p.short_name || p.name || p.client_name || '未命名')
  } catch { return /* 用户取消 */ }
  try {
    await api.delete(`/api/projects/${p.id}`)
    ElMessage.success('项目已删除')
    projects.value = projects.value.filter(x => x.id !== p.id)
  } catch {
    /* 错误提示由全局拦截器给出 */
  }
}

async function loadProjects() {
  loading.value = true
  loadError.value = false
  try {
    const data = await api.get(P.projects.list)
    projects.value = data ?? []
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

onMounted(loadProjects)
</script>

<style scoped>
/* 抵消外层 .gt-detail-content 的内边距，让灰底铺满内容区 */
.gt-plh {
  margin: calc(var(--gt-space-4) * -1);
  padding: 16px 16px 24px;
  min-height: calc(100% + var(--gt-space-4) * 2);
  box-sizing: border-box;
  background: var(--gt-color-bg, #f5f6fa);
}
.gt-plh-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.gt-plh-title { display: flex; align-items: baseline; gap: 10px; }
.gt-plh-title h2 { margin: 0; font-size: 18px; font-weight: 700; color: var(--gt-color-primary, #4b2d77); }
.gt-plh-count { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary, #909399); }
.gt-plh-actions { display: flex; gap: 8px; }
.gt-plh-actions :deep(.el-button + .el-button) { margin-left: 0; }

.gt-plh-list { display: flex; flex-direction: column; gap: 8px; min-height: 120px; }
.gt-plh-card {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 14px;
  background: var(--gt-color-bg-white, #fff);
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  border-left: 3px solid var(--gt-color-primary-light, #8b6bb8);
  border-radius: 6px;
  cursor: pointer;
  user-select: none;
  transition: box-shadow .15s, border-color .15s;
}
/* 单击即进入 ⇒ 用 hover 提示「可点」（原 --active 选中态已随选中逻辑删除） */
.gt-plh-card:hover {
  box-shadow: 0 2px 8px rgba(75, 45, 119, 0.08);
  border-color: var(--gt-color-primary, #4b2d77);
  background: var(--gt-color-primary-bg, #f4f0fa);
}
.gt-plh-card:focus-visible { outline: 2px solid var(--gt-color-primary, #4b2d77); outline-offset: 1px; }
.gt-plh-card-main { min-width: 0; }
.gt-plh-card-title { display: flex; align-items: center; gap: 8px; }
.gt-plh-card-name { font-size: var(--gt-font-size-sm); font-weight: 700; color: var(--gt-color-text, #303133); }
.gt-plh-card-meta { margin-top: 6px; display: flex; gap: 16px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary, #606266); }
.gt-plh-card-side { flex-shrink: 0; padding-left: 16px; display: flex; align-items: center; gap: 4px; }
.gt-plh-card-date { margin-right: 8px; }
.gt-plh-card-op { padding: 2px 6px !important; height: auto !important; }
.gt-plh-card-op--danger { color: var(--el-color-danger, #f56c6c) !important; }
.gt-plh-card-date { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary, #909399); }
</style>
