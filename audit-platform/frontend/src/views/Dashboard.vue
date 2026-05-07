<template>
  <div class="gt-dashboard gt-fade-in">
    <!-- ── 欢迎横幅 ── -->
    <div class="welcome-banner">
      <div class="welcome-text">
        <h1 class="welcome-title">{{ greeting }}，{{ displayName }}</h1>
        <p class="welcome-date">{{ todayStr }}</p>
        <p class="welcome-motto">{{ motto }}</p>
      </div>
      <div class="welcome-deco">
        <svg width="120" height="120" viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="60" cy="60" r="50" stroke="rgba(255,255,255,0.15)" stroke-width="2"/>
          <circle cx="60" cy="60" r="35" stroke="rgba(255,255,255,0.1)" stroke-width="2"/>
          <circle cx="60" cy="60" r="20" fill="rgba(255,255,255,0.08)"/>
        </svg>
      </div>
    </div>

    <!-- ── 统计卡片 ── -->
    <div class="stat-grid gt-stagger">
      <div v-for="card in statCards" :key="card.label" class="stat-card" :class="card.cls">
        <div class="stat-top">
          <div class="stat-icon-wrap">
            <el-icon :size="24"><component :is="card.icon" /></el-icon>
          </div>
          <div v-if="card.trend !== 0" class="stat-trend" :class="card.trend > 0 ? 'trend-up' : 'trend-down'">
            {{ card.trend > 0 ? '↑' : '↓' }} {{ Math.abs(card.trend) }}%
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
          <el-tag :type="wp.status === 'draft' ? 'info' : 'warning'" size="small">
            {{ wp.status === 'draft' ? '编制中' : '待修改' }}
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
            <el-table-column prop="name" label="项目名称" min-width="160">
              <template #default="{ row }">
                <span class="project-link" @click="$router.push(`/projects/${row.id}/ledger`)">{{ row.name }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="client_name" label="客户" min-width="120" />
            <el-table-column prop="status" label="状态" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="(statusType(row.status)) || undefined" size="small" effect="light" round>{{ statusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>
      <el-col :span="10">
        <div class="section-card schedule-card">
          <div class="section-header">
            <h2 class="section-title">今日日程</h2>
          </div>
          <el-skeleton v-if="loadingSchedule" :rows="3" animated />
          <div v-else-if="todaySchedule.length === 0" class="empty-schedule">
            <el-empty description="今日暂无安排" :image-size="48" />
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
import { useAuthStore } from '@/stores/auth'
import { listProjects, getMyAssignments } from '@/services/commonApi'
import { api as httpApi } from '@/services/apiProxy'
import { dashboard as P_dash } from '@/services/apiPaths'
import GTChart from '@/components/GTChart.vue'
import {
  FolderOpened, Loading, Warning, CircleCheck,
  Plus, Timer, DataBoard, Reading, Setting,
} from '@element-plus/icons-vue'

const authStore = useAuthStore()

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
    cls: 'stat-card--primary', trend: 8,
    sparkOpt: makeSparkline(sparkSeries.value.review_passed, '#4b2d77'),
  },
  {
    label: '进行中', value: stats.inProgress, icon: Loading,
    cls: 'stat-card--teal', trend: 12,
    sparkOpt: makeSparkline(sparkSeries.value.in_progress, '#0094B3'),
  },
  {
    label: '待复核', value: stats.pendingReview, icon: Warning,
    cls: 'stat-card--coral', trend: -5,
    sparkOpt: makeSparkline(sparkSeries.value.edit_complete, '#FF5149'),
  },
  {
    label: '已完成', value: stats.completed, icon: CircleCheck,
    cls: 'stat-card--success', trend: 15,
    sparkOpt: makeSparkline(sparkSeries.value.review_passed, '#28A745'),
  },
])

// ── 快捷操作 ──
const quickActions = [
  { label: '新建项目', path: '/projects/new', icon: Plus, bg: 'var(--gt-color-primary-bg)', color: 'var(--gt-color-primary)' },
  { label: '项目列表', path: '/projects', icon: FolderOpened, bg: 'var(--gt-color-teal-light)', color: 'var(--gt-color-teal)' },
  { label: '工时填报', path: '/work-hours', icon: Timer, bg: 'var(--gt-color-wheat-light)', color: '#e6a817' },
  { label: '管理看板', path: '/dashboard/management', icon: DataBoard, bg: '#f0ebf8', color: 'var(--gt-color-primary)' },
  { label: '知识库', path: '/knowledge', icon: Reading, bg: 'var(--gt-color-success-light)', color: 'var(--gt-color-success)' },
  { label: '系统设置', path: '/settings', icon: Setting, bg: '#f5f5f7', color: '#6e6e73' },
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
    stats.completed = list.filter((p: any) => p.status === 'archived').length
    recentProjects.value = list.slice(0, 3)
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
        const data = await httpApi.get(`/api/projects/${proj.project_id}/working-papers`, {
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
.my-wp-code { font-size: 12px; color: #909399; font-family: monospace; }
.my-wp-name { font-size: 13px; font-weight: 500; margin: 4px 0 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ── 欢迎横幅 ── */
.welcome-banner {
  background: linear-gradient(135deg, #4b2d77 0%, #6b42a8 50%, #A06DFF 100%);
  border-radius: var(--gt-radius-lg);
  padding: var(--gt-space-8) var(--gt-space-8);
  color: #fff;
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--gt-space-6);
  position: relative;
  overflow: hidden;
}
.welcome-text { position: relative; z-index: 1; }
.welcome-title { font-size: 24px; font-weight: 700; margin: 0 0 6px; }
.welcome-date { font-size: 14px; opacity: 0.85; margin: 0 0 4px; }
.welcome-motto { font-size: 13px; opacity: 0.7; margin: 0; font-style: italic; }
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
  font-size: 12px; font-weight: 600; padding: 2px 6px;
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
.gt-compact-table :deep(.el-table__body .cell) { font-size: 13px !important; }
.gt-compact-table :deep(.el-table__header .cell) { font-size: 13px !important; }

/* ── 今日日程 ── */
.schedule-card { min-height: 240px; }
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
  grid-template-columns: repeat(6, 1fr);
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
@media (max-width: 640px) {
  .stat-grid { grid-template-columns: 1fr; }
  .action-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
