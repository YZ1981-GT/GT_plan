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
          <GTChart :option="card.sparkOpt" :height="36" />
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
                <el-tag :type="statusType(row.status)" size="small" effect="light" round>{{ statusLabel(row.status) }}</el-tag>
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
import http from '@/utils/http'
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

// Mock sparkline data (7 days trend)
const sparkData = {
  total: [8, 9, 9, 10, 10, 11, 12],
  inProgress: [3, 4, 3, 5, 4, 5, 5],
  pendingReview: [2, 1, 2, 2, 3, 2, 3],
  completed: [3, 4, 4, 3, 3, 4, 4],
}

const statCards = computed(() => [
  {
    label: '项目总数', value: stats.total, icon: FolderOpened,
    cls: 'stat-card--primary', trend: 8,
    sparkOpt: makeSparkline(sparkData.total, '#4b2d77'),
  },
  {
    label: '进行中', value: stats.inProgress, icon: Loading,
    cls: 'stat-card--teal', trend: 12,
    sparkOpt: makeSparkline(sparkData.inProgress, '#0094B3'),
  },
  {
    label: '待复核', value: stats.pendingReview, icon: Warning,
    cls: 'stat-card--coral', trend: -5,
    sparkOpt: makeSparkline(sparkData.pendingReview, '#FF5149'),
  },
  {
    label: '已完成', value: stats.completed, icon: CircleCheck,
    cls: 'stat-card--success', trend: 15,
    sparkOpt: makeSparkline(sparkData.completed, '#28A745'),
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
onMounted(async () => {
  // 确保用户信息
  if (!authStore.user && authStore.token) {
    try { await authStore.fetchUserProfile() } catch { /* ignore */ }
  }

  // 加载项目统计
  try {
    const { data } = await http.get('/api/projects')
    const list = Array.isArray(data) ? data : data?.items || []
    stats.total = list.length
    stats.inProgress = list.filter((p: any) => ['execution', 'planning'].includes(p.status)).length
    stats.pendingReview = list.filter((p: any) => p.status === 'completion').length
    stats.completed = list.filter((p: any) => p.status === 'archived').length
    recentProjects.value = list.slice(0, 5)
  } catch { /* ignore */ }
  loadingProjects.value = false

  // 加载今日日程
  try {
    const { data } = await http.get('/api/projects/my/assignments')
    todaySchedule.value = Array.isArray(data) ? data.slice(0, 6) : []
  } catch { /* ignore */ }
  loadingSchedule.value = false
})
</script>

<style scoped>
.gt-dashboard {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--gt-space-6);
}

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
