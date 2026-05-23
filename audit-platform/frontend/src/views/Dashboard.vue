<template>
  <div class="gt-dashboard gt-fade-in">
    <!-- ── 欢迎横幅 + 角色视图切换（多维视图）── -->
    <GtPageHeader title="工作台" variant="banner" icon="🏠" :show-back="false">
      <template #subtitle>{{ todayStr }}</template>
      <template #actions>
        <div class="dashboard-view-switcher" v-if="availableViews.length > 1">
          <el-radio-group v-model="activeView" size="small" @change="onViewChange">
            <el-radio-button v-for="v in availableViews" :key="v.key" :value="v.key">
              <el-icon style="margin-right: 3px"><component :is="v.icon" /></el-icon>{{ v.label }}
            </el-radio-button>
          </el-radio-group>
        </div>
      </template>
    </GtPageHeader>

    <!-- ── 统计卡片 ── -->
    <div class="stat-grid gt-stagger">
      <div v-for="card in statCards" :key="card.label" class="stat-card" :class="card.cls">
        <div class="stat-top">
          <div class="stat-icon-wrap">
            <el-icon :size="24"><component :is="card.icon" /></el-icon>
          </div>
        </div>
        <div class="stat-body">
          <span class="stat-value">{{ card.value }}</span>
          <span class="stat-label">{{ card.label }}</span>
        </div>
        <div class="stat-sparkline">
          <el-empty v-if="trendLoadError" description="趋势数据加载失败" :image-size="60" />
          <GTChart v-else :option="card.sparkOpt" :height="36" />
        </div>
      </div>
    </div>

    <!-- ── 我的待办底稿（快速入口） ── -->
    <div v-if="myWorkpapers.length > 0" class="my-wp-section gt-stagger">
      <div class="section-header" style="margin-bottom: 8px">
        <h2 class="section-title">📋 我的待办底稿</h2>
        <el-tag size="small" type="warning">{{ myWorkpapers.length }} 项</el-tag>
      </div>
      <div class="my-wp-grid">
        <div
          v-for="wp in myWorkpapers.slice(0, 6)"
          :key="wp.id"
          class="my-wp-card"
          @click="$router.push(`/projects/${wp.project_id}/workpapers/${wp.id}/edit`)"
        >
          <div class="my-wp-code">{{ wp.wp_code }}</div>
          <div class="my-wp-name">{{ wp.wp_name }}</div>
          <el-tag :type="wp.status === WP_STATUS.DRAFT ? 'info' : 'warning'" size="small">
            {{ wp.status === WP_STATUS.DRAFT ? '编制中' : '待修改' }}
          </el-tag>
        </div>
      </div>
    </div>

    <!-- ── 中间区域：最近项目 + 今日日程 ── -->
    <el-row :gutter="16" class="mid-row">
      <el-col :span="14">
        <div class="section-card">
          <div class="section-header">
            <h2 class="section-title">最近项目</h2>
            <el-button text size="small" @click="$router.push('/projects')">查看全部</el-button>
          </div>
          <el-skeleton v-if="loadingProjects" :rows="4" animated />
          <el-table v-else :data="recentProjects" size="small" class="gt-compact-table" :show-header="true" stripe>
            <el-table-column prop="name" label="项目名称" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="project-link" @click="$router.push(`/projects/${row.id}/ledger`)">{{ row.name }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="audit_year" label="年度" width="80" align="center">
              <template #default="{ row }">
                <span class="gt-amt">{{ row.audit_year || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="类型" width="90" align="center">
              <template #default="{ row }">
                <el-tag size="small" effect="plain" round>{{ projectTypeLabel(row.project_type) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="status" label="阶段" width="90" align="center">
              <template #default="{ row }">
                <el-tag :type="(statusType(row.status)) || undefined" size="small" effect="light" round>{{ statusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="创建" width="100" align="center">
              <template #default="{ row }">
                <span class="gt-mono">{{ shortDate(row.created_at) }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>
      <el-col :span="10">
        <div class="section-card schedule-card" :class="{ 'schedule-card--collapsed': !loadingSchedule && todaySchedule.length === 0 }">
          <div class="section-header">
            <h2 class="section-title">今日日程</h2>
          </div>
          <el-skeleton v-if="loadingSchedule" :rows="3" animated />
          <div v-else-if="todaySchedule.length === 0" class="empty-schedule-mini">
            <span>📅 今日暂无日程</span>
          </div>
          <div v-else class="timeline-list">
            <div v-for="(item, i) in todaySchedule" :key="i" class="timeline-item">
              <div class="timeline-dot" :style="{ background: timelineColor(i) }" />
              <div class="timeline-content">
                <span class="timeline-project">{{ item.project_name }}</span>
                <span class="timeline-role">{{ item.role }}</span>
              </div>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- ── 快捷操作 ── -->
    <div class="section-card">
      <div class="section-header">
        <h2 class="section-title">快捷操作</h2>
      </div>
      <div class="action-grid">
        <div v-for="act in quickActions" :key="act.label" class="action-card" @click="$router.push(act.path)">
          <div class="action-icon" :style="{ background: act.bg, color: act.color }">
            <el-icon :size="22"><component :is="act.icon" /></el-icon>
          </div>
          <span class="action-label">{{ act.label }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useRoleContextStore } from '@/stores/roleContext'
import { listProjects, getMyAssignments } from '@/services/commonApi'
import { api as httpApi } from '@/services/apiProxy'
import { dashboard as P_dash, workpapers as P_wp } from '@/services/apiPaths'
import { WP_STATUS, PROJECT_STATUS } from '@/constants/statusEnum'
import GTChart from '@/components/GTChart.vue'
import {
  FolderOpened, Loading, Warning, CircleCheck,
  Plus, Timer, Reading, Search,
  User, UserFilled, Avatar, Lock,
} from '@element-plus/icons-vue'

const authStore = useAuthStore()
const roleStore = useRoleContextStore()
const router = useRouter()

// ── 角色视图切换（多维视图）──
type ViewKey = 'me' | 'team' | 'project' | 'eqcr'
const ALL_VIEWS: { key: ViewKey; label: string; icon: any; roles: string[] }[] = [
  { key: 'me',      label: '我的视图', icon: User,        roles: ['auditor', 'reviewer', 'manager', 'partner', 'eqcr', 'admin'] },
  { key: 'team',    label: '团队视图', icon: UserFilled,  roles: ['manager', 'partner', 'admin'] },
  { key: 'project', label: '项目视图', icon: Avatar,      roles: ['partner', 'admin'] },
  { key: 'eqcr',    label: 'EQCR',     icon: Lock,        roles: ['eqcr', 'partner', 'admin'] },
]
const activeView = ref<ViewKey>('me')
const availableViews = computed(() => {
  const role = roleStore.effectiveRole || authStore.user?.role || 'auditor'
  return ALL_VIEWS.filter(v => v.roles.includes(role))
})
function onViewChange(val: ViewKey) {
  // team / project / eqcr 直接路由到对应页面（复用现有实现）
  if (val === 'team') router.push('/dashboard/manager')
  else if (val === 'project') router.push('/dashboard/partner')
  else if (val === 'eqcr') router.push('/eqcr/metrics')
  // me 视图保留在当前页
}

// ── 欢迎区 ──
const displayName = computed(() => authStore.user?.username || '用户')
const now = new Date()
const hour = now.getHours()
const greeting = computed(() => hour < 12 ? '早上好' : hour < 18 ? '下午好' : '晚上好')
const todayStr = computed(() => {
  const d = new Date()
  const weekdays = ['日', '一', '二', '三', '四', '五', '六']
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 星期${weekdays[d.getDay()]}`
})
const mottos = [
  '审计之道，在于细节。',
  '每一份底稿，都是专业的证明。',
  '严谨求实，追求卓越。',
  '今天也是高效工作的一天。',
]
const motto = mottos[Math.floor(Math.random() * mottos.length)]

// ── 统计卡片 ──
const stats = reactive({ total: 0, inProgress: 0, pendingReview: 0, completed: 0 })
const loadingProjects = ref(true)
const loadingSchedule = ref(true)
const recentProjects = ref<any[]>([])
const todaySchedule = ref<any[]>([])

function makeSparkline(data: number[], color: string) {
  return {
    grid: { top: 0, bottom: 0, left: 0, right: 0 },
    xAxis: { show: false, type: 'category' as const, data: data.map((_, i) => i) },
    yAxis: { show: false, type: 'value' as const, min: Math.min(...data) * 0.8 },
    series: [{
      type: 'line' as const,
      data,
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2, color },
      areaStyle: { color: { type: 'linear' as const, x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: color + '30' }, { offset: 1, color: color + '05' }] } },
    }],
  }
}

// 趋势数据（接入真实 API）
const trendData = ref<Record<string, Record<string, number>>>({})
const trendLoadError = ref(false)

async function loadTrendData() {
  trendLoadError.value = false
  try {
    const res = await httpApi.get(P_dash.statsTrend, {
      params: { days: 7 }
    })
    trendData.value = res.trend || {}
  } catch {
    trendLoadError.value = true
  }
}

const sparkSeries = computed(() => {
  const days = Object.keys(trendData.value).sort()
  return {
    review_passed: days.map(d => trendData.value[d]?.review_passed ?? 0),
    in_progress: days.map(d => trendData.value[d]?.in_progress ?? 0),
    edit_complete: days.map(d => trendData.value[d]?.edit_complete ?? 0),
  }
})

const statCards = computed(() => [
  {
    label: '项目总数', value: stats.total, icon: FolderOpened,
    cls: 'stat-card--primary',
    sparkOpt: makeSparkline(sparkSeries.value.review_passed, '#4b2d77'),
  },
  {
    label: '进行中', value: stats.inProgress, icon: Loading,
    cls: 'stat-card--teal',
    sparkOpt: makeSparkline(sparkSeries.value.in_progress, '#0094B3'),
  },
  {
    label: '待复核', value: stats.pendingReview, icon: Warning,
    cls: 'stat-card--coral',
    sparkOpt: makeSparkline(sparkSeries.value.edit_complete, '#FF5149'),
  },
  {
    label: '已完成', value: stats.completed, icon: CircleCheck,
    cls: 'stat-card--success',
    sparkOpt: makeSparkline(sparkSeries.value.review_passed, '#28A745'),
  },
])

// ── 快捷操作（精简到 4 个真高频任务，与左侧导航解耦）──
const quickActions = [
  { label: '新建项目', path: '/projects/new', icon: Plus, bg: 'var(--gt-color-primary-bg)', color: 'var(--gt-color-primary)' },
  { label: '工时填报', path: '/work-hours', icon: Timer, bg: 'var(--gt-color-wheat-light)', color: '#e6a817' },
  { label: '复核收件箱', path: '/review-inbox', icon: Reading, bg: 'var(--gt-color-coral-light)', color: '#FF5149' },
  { label: '高级查询', path: '/advanced-query', icon: Search, bg: '#e0f2fe', color: '#0284c7' },
]

// ── 状态映射 ──
function statusLabel(s: string) {
  const m: Record<string, string> = { created: '已创建', planning: '计划中', execution: '执行中', completion: '完工', reporting: '报告', archived: '归档' }
  return m[s] || s
}
function statusType(s: string): '' | 'success' | 'warning' | 'danger' | 'info' {
  const m: Record<string, '' | 'success' | 'warning' | 'danger' | 'info'> = { execution: '', planning: 'warning', completion: 'success', archived: 'info', created: 'info' }
  return m[s] ?? ''
}
function projectTypeLabel(t?: string): string {
  const m: Record<string, string> = { annual: '年报', interim: '中报', special: '专项', other: '其他' }
  return t ? (m[t] || t) : '—'
}
function shortDate(s?: string): string {
  if (!s) return '—'
  return s.slice(5, 10)
}
const timelineColors = ['#4b2d77', '#0094B3', '#FF5149', '#F5A623', '#28a745']
function timelineColor(i: number) { return timelineColors[i % timelineColors.length] }

// ── 数据加载 ──
// ── 我的待办底稿 ──
const myWorkpapers = ref<any[]>([])

onMounted(async () => {
  // 确保用户信息
  if (!authStore.user && authStore.token) {
    try { await authStore.fetchUserProfile() } catch { /* ignore */ }
  }

  // 加载趋势数据
  loadTrendData()

  // 加载项目统计
  try {
    const list = await listProjects()
    stats.total = list.length
    stats.inProgress = list.filter((p: any) => ['execution', 'planning'].includes(p.status)).length
    stats.pendingReview = list.filter((p: any) => p.status === 'completion').length
    stats.completed = list.filter((p: any) => p.status === PROJECT_STATUS.ARCHIVED).length
    recentProjects.value = list.slice(0, 5)
  } catch { /* ignore */ }
  loadingProjects.value = false

  // 加载今日日程
  try {
    todaySchedule.value = (await getMyAssignments()).slice(0, 6)
  } catch { /* ignore */ }
  loadingSchedule.value = false

  // 加载我的待办底稿（draft 或被退回的）
  try {
    const assignments = await getMyAssignments()
    const wpList: any[] = []
    for (const proj of assignments.slice(0, 5)) {
      try {
        const data = await httpApi.get(P_wp.list(proj.project_id), {
          params: { assigned_to_me: true, status: 'draft,rejected' },
          validateStatus: (s: number) => s < 600,
        })
        const items = Array.isArray(data) ? data : data?.items || []
        for (const wp of items.slice(0, 3)) {
          wpList.push({ ...wp, project_id: proj.project_id })
        }
      } catch { /* ignore */ }
    }
    myWorkpapers.value = wpList.slice(0, 6)
  } catch { /* ignore */ }
})
</script>

<style scoped>
.gt-dashboard {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--gt-space-6);
}

/* ── 我的待办底稿 ── */
.my-wp-section { margin-bottom: 20px; }
.my-wp-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
.my-wp-card { background: white; border-radius: 8px; padding: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); cursor: pointer; transition: box-shadow 0.2s; }
.my-wp-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.12); }
.my-wp-code { font-size: var(--gt-font-size-xs); color: var(--gt-color-info); font-family: monospace; }
.my-wp-name { font-size: var(--gt-font-size-sm); font-weight: 500; margin: 4px 0 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ── 欢迎横幅 ── */
.welcome-banner {
  background: linear-gradient(135deg, #4b2d77 0%, #6b42a8 50%, #A06DFF 100%);
  border-radius: var(--gt-radius-lg);
  padding: var(--gt-space-8) var(--gt-space-8);
  color: var(--gt-color-text-inverse);
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--gt-space-6);
  position: relative;
  overflow: hidden;
}
.welcome-text { position: relative; z-index: 1; }
.welcome-title { font-size: 24px /* allow-px: special */; font-weight: 700; margin: 0 0 6px; }
.welcome-date { font-size: var(--gt-font-size-sm); opacity: 0.85; margin: 0 0 4px; }
.welcome-motto { font-size: var(--gt-font-size-sm); opacity: 0.7; margin: 0; font-style: italic; }
.welcome-deco { opacity: 0.5; flex-shrink: 0; }

/* ── 统计卡片 ── */
.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--gt-space-4);
  margin-bottom: var(--gt-space-6);
}
.stat-card {
  background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md);
  padding: var(--gt-space-4) var(--gt-space-5);
  box-shadow: var(--gt-shadow-sm);
  transition: all var(--gt-transition-base);
  cursor: default;
  position: relative;
  overflow: hidden;
  border-left: 3px solid transparent;
}
.stat-card:hover { transform: translateY(-2px); box-shadow: var(--gt-shadow-md); }
.stat-card--primary { border-left-color: var(--gt-color-primary); }
.stat-card--teal { border-left-color: var(--gt-color-teal); }
.stat-card--coral { border-left-color: var(--gt-color-coral); }
.stat-card--success { border-left-color: var(--gt-color-success); }

.stat-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-2); }
.stat-icon-wrap {
  width: 36px; height: 36px; border-radius: var(--gt-radius-md);
  display: flex; align-items: center; justify-content: center;
}
.stat-card--primary .stat-icon-wrap { background: var(--gt-color-primary-bg); color: var(--gt-color-primary); }
.stat-card--teal .stat-icon-wrap { background: var(--gt-color-teal-light); color: var(--gt-color-teal); }
.stat-card--coral .stat-icon-wrap { background: var(--gt-color-coral-light); color: var(--gt-color-coral); }
.stat-card--success .stat-icon-wrap { background: var(--gt-color-success-light); color: var(--gt-color-success); }

.stat-trend {
  font-size: var(--gt-font-size-xs); font-weight: 600; padding: 2px 6px;
  border-radius: var(--gt-radius-full);
}
.trend-up { color: var(--gt-color-success); background: var(--gt-color-success-light); }
.trend-down { color: var(--gt-color-coral); background: var(--gt-color-coral-light); }

.stat-body { display: flex; flex-direction: column; }
.stat-value { font-size: var(--gt-font-size-3xl); font-weight: 700; color: var(--gt-color-text); line-height: 1.2; }
.stat-label { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); margin-top: 2px; }
.stat-sparkline { margin-top: var(--gt-space-2); }

/* ── 中间区域 ── */
.mid-row { margin-bottom: var(--gt-space-6); }
.section-card {
  background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md);
  padding: var(--gt-space-5);
  box-shadow: var(--gt-shadow-sm);
}
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-4); }
.section-title { font-size: var(--gt-font-size-md); font-weight: 600; color: var(--gt-color-text); margin: 0; }

.project-link { color: var(--gt-color-primary); cursor: pointer; font-weight: 500; }
.project-link:hover { text-decoration: underline; }

.gt-compact-table :deep(.el-table__row td) { padding: 8px 0; }
.gt-compact-table :deep(.el-table__body .cell) { font-size: var(--gt-font-size-sm) !important; }
.gt-compact-table :deep(.el-table__header .cell) { font-size: var(--gt-font-size-sm) !important; }

/* ── 今日日程 ── */
.schedule-card { min-height: 240px; }
.schedule-card--collapsed { min-height: auto; padding: var(--gt-space-3) var(--gt-space-5); }
.schedule-card--collapsed .section-header { margin-bottom: var(--gt-space-1); }
.empty-schedule-mini {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
  padding: 4px 0;
}
.empty-schedule { display: flex; align-items: center; justify-content: center; min-height: 160px; }
.timeline-list { display: flex; flex-direction: column; gap: var(--gt-space-3); }
.timeline-item { display: flex; align-items: center; gap: var(--gt-space-3); padding: var(--gt-space-2) 0; }
.timeline-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.timeline-content { display: flex; flex-direction: column; }
.timeline-project { font-size: var(--gt-font-size-base); font-weight: 500; color: var(--gt-color-text); }
.timeline-role { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }

/* ── 快捷操作 ── */
.action-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: var(--gt-space-4);
}
.action-card {
  display: flex; flex-direction: column; align-items: center; gap: var(--gt-space-2);
  padding: var(--gt-space-4); border-radius: var(--gt-radius-md);
  cursor: pointer; transition: all var(--gt-transition-base);
  border: 1px solid transparent;
}
.action-card:hover {
  border-color: var(--gt-color-primary-lighter);
  box-shadow: var(--gt-shadow-sm);
  transform: translateY(-2px);
}
.action-icon {
  width: 44px; height: 44px; border-radius: var(--gt-radius-md);
  display: flex; align-items: center; justify-content: center;
}
.action-label { font-size: var(--gt-font-size-sm); font-weight: 500; color: var(--gt-color-text); }

/* ── 响应式 ── */
@media (max-width: 1024px) {
  .stat-grid { grid-template-columns: repeat(2, 1fr); }
  .action-grid { grid-template-columns: repeat(3, 1fr); }
  .mid-row .el-col { max-width: 100%; flex: 0 0 100%; margin-bottom: var(--gt-space-4); }
}

/* ── 角色视图切换器（banner 内 actions slot）── */
.dashboard-view-switcher {
  margin-top: var(--gt-space-2);
  display: inline-flex;
}
.dashboard-view-switcher :deep(.el-radio-button__inner) {
  background: rgba(255, 255, 255, 0.12);
  color: var(--gt-color-text-inverse);
  border-color: rgba(255, 255, 255, 0.24);
}
.dashboard-view-switcher :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: rgba(255, 255, 255, 0.95);
  color: var(--gt-color-primary);
  border-color: rgba(255, 255, 255, 0.95);
  box-shadow: none;
}
@media (max-width: 640px) {
  .stat-grid { grid-template-columns: 1fr; }
  .action-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
