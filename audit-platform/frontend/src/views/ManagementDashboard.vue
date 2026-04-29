<template>
  <div class="gt-dashboard gt-fade-in">
    <!-- 顶部横幅 -->
    <div class="gt-mgmt-banner">
      <div class="gt-mgmt-banner-text">
        <h2 class="gt-mgmt-title">管理看板</h2>
        <p class="gt-mgmt-subtitle">实时掌握项目进度、人员负荷与风险预警</p>
      </div>
      <div class="gt-mgmt-banner-actions">
        <el-button size="default" @click="refreshAll" :loading="loading" :icon="Refresh" round>刷新数据</el-button>
      </div>
      <div class="gt-mgmt-banner-deco"></div>
    </div>

    <!-- ── KPI 指标卡片 ── -->
    <div class="kpi-grid">
      <div v-for="card in kpiCards" :key="card.label" class="kpi-card" :style="{ borderLeftColor: card.color, '--kpi-accent': card.color }">
        <div class="kpi-top">
          <div class="kpi-icon" :style="{ background: card.bg, color: card.color }">
            <el-icon :size="22"><component :is="card.icon" /></el-icon>
          </div>
          <div v-if="card.trend !== 0" class="kpi-trend" :class="card.trendDir">
            {{ card.trend > 0 ? '↑' : '↓' }} {{ Math.abs(card.trend) }}%
          </div>
        </div>
        <div class="kpi-value">{{ card.value }}<span v-if="card.suffix" class="kpi-suffix">{{ card.suffix }}</span></div>
        <div class="kpi-label">{{ card.label }}</div>
      </div>
    </div>

    <!-- ── 项目进度 + 人员负荷 ── -->
    <el-row :gutter="16" class="chart-row gt-stagger">
      <el-col :span="12">
        <div class="chart-card">
          <h3 class="chart-title">项目进度 Top 10</h3>
          <GTChart v-if="progressOption" :option="progressOption" :height="340" :loading="loading" />
        </div>
      </el-col>
      <el-col :span="12">
        <div class="chart-card">
          <h3 class="chart-title">人员负荷排行（本周工时）</h3>
          <GTChart v-if="workloadOption" :option="workloadOption" :height="340" :loading="loading" />
        </div>
      </el-col>
    </el-row>

    <!-- ── 风险预警 + 集团审计 ── -->
    <el-row :gutter="16" class="chart-row gt-stagger">
      <el-col :span="8">
        <div class="chart-card risk-card">
          <h3 class="chart-title">
            <el-icon style="color: var(--gt-color-coral); margin-right: 6px"><WarningFilled /></el-icon>
            风险预警
          </h3>
          <div v-if="riskAlerts.length === 0" class="chart-empty">
            <el-icon :size="32" style="color: var(--gt-color-success)"><CircleCheckFilled /></el-icon>
            <span style="margin-top: 8px; color: var(--gt-color-text-secondary)">暂无风险预警</span>
          </div>
          <div v-else class="risk-list">
            <div v-for="a in riskAlerts" :key="a.type" class="risk-item">
              <el-tag :type="riskSeverity(a.type)" size="small" effect="dark" round>{{ a.count }}</el-tag>
              <span class="risk-msg">{{ a.message }}</span>
            </div>
          </div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="chart-card">
          <h3 class="chart-title">集团审计进度</h3>
          <GTChart v-if="groupOption" :option="groupOption" :height="260" :loading="loading" />
          <div v-else-if="!loading" class="chart-empty">
            <span style="color: var(--gt-color-text-tertiary)">无合并项目</span>
          </div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="chart-card">
          <h3 class="chart-title">工时热力图（近30天）</h3>
          <GTChart v-if="heatmapOption" :option="heatmapOption" :height="260" :loading="loading" />
          <div v-else-if="!loading" class="chart-empty">
            <span style="color: var(--gt-color-text-tertiary)">暂无工时数据</span>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- ── 查询面板：按项目/按人员/可用人员 ── -->
    <el-row :gutter="16" class="chart-row">
      <el-col :span="24">
        <div class="chart-card query-panel">
          <h3 class="chart-title" style="margin-bottom: 16px">
            <el-icon style="color: var(--gt-color-primary); margin-right: 6px"><Search /></el-icon>
            人员工时查询
          </h3>
          <el-segmented v-model="queryTab" :options="queryTabOptions" size="default" style="margin-bottom: 20px" />

          <!-- 按项目查 -->
          <div v-if="queryTab === 'by-project'" class="query-content">
            <div class="query-toolbar">
              <el-select v-model="queryProjectId" placeholder="选择项目查看人员工时" filterable clearable size="large" style="width: 400px" @change="loadProjectStaff">
                <el-option v-for="p in allProjects" :key="p.id" :label="`${p.client_name || p.name} (${p.audit_year || ''})`" :value="p.id" />
              </el-select>
            </div>
            <el-table :data="projectStaffData" stripe size="default" v-loading="queryLoading" :empty-text="queryProjectId ? '该项目暂无委派人员' : '请先选择项目'" class="query-table">
              <el-table-column prop="staff_name" label="姓名" width="120">
                <template #default="{ row }">
                  <span style="font-weight: 600; color: var(--gt-color-primary)">{{ row.staff_name }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="title" label="职级" width="100" />
              <el-table-column prop="role" label="角色" width="120">
                <template #default="{ row }">
                  <el-tag size="small" effect="plain" round>{{ row.role }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="week_hours" label="本周工时" width="120" align="right">
                <template #default="{ row }">
                  <span :style="{ color: row.week_hours > 40 ? '#FF5149' : row.week_hours > 20 ? '#e6a23c' : '#333', fontWeight: 600 }">{{ row.week_hours }}h</span>
                </template>
              </el-table-column>
              <el-table-column prop="total_hours" label="累计工时" width="120" align="right">
                <template #default="{ row }"><span style="font-weight: 500">{{ row.total_hours }}h</span></template>
              </el-table-column>
            </el-table>
          </div>

          <!-- 按人员查 -->
          <div v-if="queryTab === 'by-staff'" class="query-content">
            <div class="query-toolbar">
              <el-select v-model="queryStaffId" placeholder="搜索人员姓名或工号" filterable remote :remote-method="searchStaffForQuery" clearable size="large" style="width: 400px" @change="loadStaffDetail" :loading="staffSearching">
                <el-option v-for="s in staffSearchResults" :key="s.id" :label="`${s.name} (${s.employee_no || ''}) ${s.title || ''}`" :value="s.id" />
              </el-select>
            </div>
            <div v-if="staffDetail" class="staff-detail-panel">
              <div class="staff-info-bar">
                <div class="staff-avatar">{{ staffDetail.staff.name?.charAt(0) }}</div>
                <div class="staff-info-text">
                  <div class="staff-info-name">{{ staffDetail.staff.name }}</div>
                  <div class="staff-info-meta">{{ staffDetail.staff.title || '—' }} · {{ staffDetail.staff.department || '—' }}</div>
                </div>
                <div class="staff-info-stat">
                  <div class="staff-info-stat-value">{{ staffDetail.week_total }}h</div>
                  <div class="staff-info-stat-label">本周工时</div>
                </div>
                <div class="staff-info-stat">
                  <div class="staff-info-stat-value">{{ staffDetail.projects?.length || 0 }}</div>
                  <div class="staff-info-stat-label">参与项目</div>
                </div>
                <div class="staff-info-stat">
                  <div class="staff-info-stat-value">{{ staffDetail.next_week_projects?.length || 0 }}</div>
                  <div class="staff-info-stat-label">下周安排</div>
                </div>
              </div>
              <el-row :gutter="16" style="margin-top: 16px">
                <el-col :span="12">
                  <div class="sub-card">
                    <h4 class="sub-card-title">📋 参与项目</h4>
                    <el-table :data="staffDetail.projects" stripe size="small" max-height="220">
                      <el-table-column prop="project_name" label="项目" min-width="150" />
                      <el-table-column prop="role" label="角色" width="100">
                        <template #default="{ row }"><el-tag size="small" effect="plain" round>{{ row.role }}</el-tag></template>
                      </el-table-column>
                      <el-table-column prop="status" label="状态" width="80">
                        <template #default="{ row }"><el-tag size="small" :type="row.status === 'execution' ? '' : 'info'" effect="light" round>{{ row.status }}</el-tag></template>
                      </el-table-column>
                    </el-table>
                  </div>
                </el-col>
                <el-col :span="12">
                  <div class="sub-card">
                    <h4 class="sub-card-title">📅 未来一周安排</h4>
                    <div v-if="staffDetail.next_week_projects.length === 0" style="color: #ccc; text-align: center; padding: 40px 0">暂无安排，可委派新任务</div>
                    <div v-for="(np, i) in staffDetail.next_week_projects" :key="i" class="schedule-item">
                      <div class="schedule-dot" :style="{ background: ['#4b2d77','#0094B3','#FF5149','#F5A623','#28a745'][i % 5] }" />
                      <div class="schedule-text">
                        <span class="schedule-project">{{ np.project_name }}</span>
                        <el-tag size="small" effect="plain" round style="margin-left: 8px">{{ np.role }}</el-tag>
                      </div>
                    </div>
                  </div>
                </el-col>
              </el-row>
            </div>
            <el-empty v-else-if="!queryLoading" description="搜索人员查看详情" :image-size="60" />
          </div>

          <!-- 可用人员 -->
          <div v-if="queryTab === 'available'" class="query-content">
            <div class="query-toolbar">
              <span class="query-hint">本周工时低于</span>
              <el-input-number v-model="maxHoursThreshold" :min="10" :max="60" :step="5" size="default" style="width: 140px" />
              <span class="query-hint">小时的人员</span>
              <el-button type="primary" @click="loadAvailableStaff" :loading="queryLoading">查询可用人员</el-button>
            </div>
            <el-table :data="availableStaffData" stripe size="default" v-loading="queryLoading" empty-text="点击查询按钮获取数据" class="query-table">
              <el-table-column prop="name" label="姓名" width="120">
                <template #default="{ row }"><span style="font-weight: 600">{{ row.name }}</span></template>
              </el-table-column>
              <el-table-column prop="title" label="职级" width="100" />
              <el-table-column prop="department" label="部门" width="120" />
              <el-table-column prop="project_count" label="在手项目" width="100" align="center">
                <template #default="{ row }">
                  <el-tag :type="row.project_count > 3 ? 'warning' : ''" size="small" round>{{ row.project_count }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="week_hours" label="本周工时" width="120" align="right">
                <template #default="{ row }">{{ row.week_hours }}h</template>
              </el-table-column>
              <el-table-column prop="available_hours" label="可用工时" width="120" align="right">
                <template #default="{ row }">
                  <span style="color: var(--gt-color-success, #28a745); font-weight: 700; font-size: 15px">{{ row.available_hours }}h</span>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import {
  getDashboardOverview, getDashboardProjectProgress, getDashboardStaffWorkload,
  getDashboardRiskAlerts, getDashboardGroupProgress, getDashboardHoursHeatmap,
  // @ts-ignore unused for future
getDashboardProjectStaffHours, getDashboardStaffDetail, getDashboardAvailableStaff,
} from '@/services/commonApi'
import api from '@/services/apiProxy'
import GTChart from '@/components/GTChart.vue'
import {
  Refresh, FolderOpened, Timer, User, WarningFilled, CircleCheckFilled, Search,
} from '@element-plus/icons-vue'

const loading = ref(false)

// ── 数字动画 ──
function useAnimNum(target: () => number, dur = 800) {
  const d = ref(0)
  let raf = 0
  watch(target, (to) => {
    cancelAnimationFrame(raf)
    const from = d.value; const start = performance.now()
    function step(now: number) {
      const t = Math.min((now - start) / dur, 1)
      d.value = Math.round(from + (to - from) * (1 - Math.pow(1 - t, 3)))
      if (t < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
  }, { immediate: true })
  return d
}

// ── KPI 数据 ──
const overview = ref<any>({})
const projectProgress = ref<any[]>([])
const staffWorkload = ref<any[]>([])
const riskAlerts = ref<any[]>([])
const groupProgress = ref<any[]>([])
const heatmapData = ref<any[]>([])

const animActive = useAnimNum(() => overview.value.active_projects ?? 0)
const animWeekHours = useAnimNum(() => overview.value.week_hours ?? 0)
const animStaff = useAnimNum(() => overview.value.staff_count ?? 0)
const animOverdue = useAnimNum(() => overview.value.overdue_projects ?? 0)

const kpiCards = computed(() => [
  {
    label: '在审项目', value: animActive.value, suffix: '',
    icon: FolderOpened, color: '#4b2d77', bg: '#f4f0fa', trend: 5, trendDir: 'trend-up',
  },
  {
    label: '本周工时', value: animWeekHours.value, suffix: 'h',
    icon: Timer, color: '#0094B3', bg: '#e6f7fa', trend: 12, trendDir: 'trend-up',
  },
  {
    label: '人员总数', value: animStaff.value, suffix: '',
    icon: User, color: '#28A745', bg: '#edf7ef', trend: 0, trendDir: '',
  },
  {
    label: '超期项目', value: animOverdue.value, suffix: '',
    icon: WarningFilled, color: '#FF5149', bg: '#fff0ef',
    trend: overview.value.overdue_projects > 0 ? 0 : 0, trendDir: '',
  },
])

// ── 项目进度图 ──
const progressOption = computed(() => {
  if (!projectProgress.value.length) return null
  const top10 = projectProgress.value.slice(0, 10).reverse()
  return {
    tooltip: { trigger: 'axis' as const, formatter: (params: any) => {
      const p = params[0]
      return `${p.name}<br/>进度: <b>${p.value}%</b>`
    }},
    grid: { left: 120, right: 40, top: 10, bottom: 10 },
    xAxis: { type: 'value' as const, max: 100, axisLabel: { formatter: '{value}%' }, splitLine: { lineStyle: { type: 'dashed' as const, color: '#f0f0f5' } } },
    yAxis: { type: 'category' as const, data: top10.map((p: any) => p.project_name), axisLabel: { fontSize: 12, width: 100, overflow: 'truncate' as const } },
    series: [{
      type: 'bar' as const,
      data: top10.map((p: any) => ({
        value: p.progress,
        itemStyle: { color: progressColor(p.progress), borderRadius: [0, 4, 4, 0] },
      })),
      barWidth: 16,
      label: { show: true, position: 'right' as const, formatter: '{c}%', fontSize: 11, color: '#666' },
    }],
  }
})

function progressColor(pct: number): any {
  if (pct < 30) return { type: 'linear' as const, x: 0, y: 0, x2: 1, y2: 0, colorStops: [{ offset: 0, color: '#FF5149' }, { offset: 1, color: '#ff7b74' }] }
  if (pct < 70) return { type: 'linear' as const, x: 0, y: 0, x2: 1, y2: 0, colorStops: [{ offset: 0, color: '#e6a817' }, { offset: 1, color: '#FFC23D' }] }
  return { type: 'linear' as const, x: 0, y: 0, x2: 1, y2: 0, colorStops: [{ offset: 0, color: '#1e8a38' }, { offset: 1, color: '#28A745' }] }
}

// ── 人员负荷图 ──
const workloadOption = computed(() => {
  if (!staffWorkload.value.length) return null
  const top10 = staffWorkload.value.slice(0, 10).reverse()
  return {
    tooltip: { trigger: 'axis' as const, formatter: (params: any) => {
      const p = params[0]
      return `${p.name}<br/>本周工时: <b>${p.value}h</b>`
    }},
    grid: { left: 80, right: 40, top: 10, bottom: 10 },
    xAxis: { type: 'value' as const, name: '工时(h)', splitLine: { lineStyle: { type: 'dashed' as const, color: '#f0f0f5' } } },
    yAxis: { type: 'category' as const, data: top10.map((s: any) => s.name), axisLabel: { fontSize: 12 } },
    series: [{
      type: 'bar' as const,
      data: top10.map((s: any) => ({
        value: s.week_hours,
        itemStyle: {
          color: { type: 'linear' as const, x: 0, y: 0, x2: 1, y2: 0, colorStops: [{ offset: 0, color: '#4b2d77' }, { offset: 1, color: '#A06DFF' }] },
          borderRadius: [0, 6, 6, 0],
        },
      })),
      barWidth: 18,
      label: { show: true, position: 'right' as const, formatter: '{c}h', fontSize: 11, color: '#666', fontWeight: 600 },
    }],
  }
})

// ── 集团审计进度图 ──
const groupOption = computed(() => {
  if (!groupProgress.value.length) return null
  const items = groupProgress.value.slice(0, 10).reverse()
  return {
    tooltip: { trigger: 'axis' as const },
    grid: { left: 100, right: 40, top: 10, bottom: 10 },
    xAxis: { type: 'value' as const, max: 100, axisLabel: { formatter: '{value}%' }, splitLine: { lineStyle: { type: 'dashed' as const, color: '#f0f0f5' } } },
    yAxis: { type: 'category' as const, data: items.map((g: any) => g.name), axisLabel: { fontSize: 11 } },
    series: [{
      type: 'bar' as const,
      data: items.map((g: any) => ({
        value: g.progress,
        itemStyle: {
          color: { type: 'linear' as const, x: 0, y: 0, x2: 1, y2: 0, colorStops: [{ offset: 0, color: '#007a94' }, { offset: 1, color: '#0094B3' }] },
          borderRadius: [0, 6, 6, 0],
        },
      })),
      barWidth: 16,
      label: { show: true, position: 'right' as const, formatter: '{c}%', fontSize: 11, color: '#666' },
    }],
  }
})

// ── 工时热力图 ──
const heatmapOption = computed(() => {
  if (!heatmapData.value.length) return null
  // Calendar heatmap for last 30 days
  const dates = [...new Set(heatmapData.value.map((d: any) => d.date))].sort()
  if (dates.length === 0) return null
  const rangeStart = dates[0]
  const rangeEnd = dates[dates.length - 1]
  // Aggregate hours per date
  const dateMap: Record<string, number> = {}
  heatmapData.value.forEach((d: any) => {
    dateMap[d.date] = (dateMap[d.date] || 0) + d.hours
  })
  const calData = Object.entries(dateMap).map(([date, hours]) => [date, hours])
  const maxHours = Math.max(...Object.values(dateMap), 1)

  return {
    tooltip: { formatter: (p: any) => `${p.value[0]}<br/>工时: <b>${p.value[1]}h</b>` },
    visualMap: {
      min: 0, max: maxHours, calculable: false, orient: 'horizontal' as const,
      left: 'center', bottom: 0, itemWidth: 12, itemHeight: 12,
      inRange: { color: ['#f8f6fb', '#c4a8e8', '#8b5ec7', '#4b2d77'] },
      textStyle: { fontSize: 10 },
    },
    calendar: {
      top: 10, left: 30, right: 30, bottom: 40,
      range: [rangeStart, rangeEnd],
      cellSize: ['auto', 16],
      splitLine: { show: false },
      itemStyle: { borderWidth: 2, borderColor: '#fff', borderRadius: 3 },
      dayLabel: { fontSize: 10, nameMap: 'ZH' },
      monthLabel: { fontSize: 10, nameMap: 'ZH' },
      yearLabel: { show: false },
    },
    series: [{
      type: 'heatmap' as const,
      coordinateSystem: 'calendar' as const,
      data: calData,
    }],
  }
})

// ── 风险等级 ──
function riskSeverity(type: string): 'danger' | 'warning' | 'info' {
  if (type.includes('overdue')) return 'danger'
  if (type.includes('warning')) return 'warning'
  return 'info'
}

// ── 数据加载 ──
async function refreshAll() {
  loading.value = true
  try {
    const [ov, progress, workload, alerts, group, heatmap] = await Promise.all([
      getDashboardOverview().catch(() => ({})),
      getDashboardProjectProgress().catch(() => []),
      getDashboardStaffWorkload().catch(() => []),
      getDashboardRiskAlerts().catch(() => []),
      getDashboardGroupProgress().catch(() => []),
      getDashboardHoursHeatmap().catch(() => []),
    ])
    overview.value = ov && typeof ov === 'object' ? ov : {}
    projectProgress.value = Array.isArray(progress) ? progress : []
    staffWorkload.value = Array.isArray(workload) ? workload : []
    riskAlerts.value = Array.isArray(alerts) ? alerts : []
    groupProgress.value = Array.isArray(group) ? group : []
    heatmapData.value = Array.isArray(heatmap) ? heatmap : []
  } catch (e) {
    console.warn('Dashboard load error:', e)
  } finally {
    loading.value = false
  }
}

let timer: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  refreshAll()
  loadAllProjects()
  timer = setInterval(refreshAll, 30000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })

// ── 查询面板 ──
const queryTab = ref('by-project')
const queryTabOptions = [
  { label: '📁 按项目查人员工时', value: 'by-project' },
  { label: '👤 按人员查项目工时', value: 'by-staff' },
  { label: '🟢 可用人员', value: 'available' },
]
const queryLoading = ref(false)
const queryProjectId = ref('')
const queryStaffId = ref('')
const maxHoursThreshold = ref(30)
const allProjects = ref<any[]>([])
const projectStaffData = ref<any[]>([])
const staffDetail = ref<any>(null)
const availableStaffData = ref<any[]>([])
const staffSearchResults = ref<any[]>([])
const staffSearching = ref(false)

async function loadAllProjects() {
  try {
    const data = await api.get('/api/projects')
    allProjects.value = Array.isArray(data) ? data : data?.items || []
  } catch { allProjects.value = [] }
}

async function loadProjectStaff() {
  if (!queryProjectId.value) { projectStaffData.value = []; return }
  queryLoading.value = true
  try {
    const data = await api.get('/api/dashboard/project-staff-hours', {
      params: { project_id: queryProjectId.value },
    })
    projectStaffData.value = Array.isArray(data) ? data : []
  } catch { projectStaffData.value = [] }
  finally { queryLoading.value = false }
}

async function searchStaffForQuery(query: string) {
  if (!query || query.length < 1) { staffSearchResults.value = []; return }
  staffSearching.value = true
  try {
    const data = await api.get('/api/staff', { params: { search: query, limit: 20 } })
    staffSearchResults.value = data?.items || (Array.isArray(data) ? data : [])
  } catch { staffSearchResults.value = [] }
  finally { staffSearching.value = false }
}

async function loadStaffDetail() {
  if (!queryStaffId.value) { staffDetail.value = null; return }
  queryLoading.value = true
  try {
    const data = await api.get('/api/dashboard/staff-detail', {
      params: { staff_id: queryStaffId.value },
    })
    staffDetail.value = data
  } catch { staffDetail.value = null }
  finally { queryLoading.value = false }
}

async function loadAvailableStaff() {
  queryLoading.value = true
  try {
    const data = await api.get('/api/dashboard/available-staff', {
      params: { max_hours: maxHoursThreshold.value },
    })
    availableStaffData.value = Array.isArray(data) ? data : []
  } catch { availableStaffData.value = [] }
  finally { queryLoading.value = false }
}
</script>

<style scoped>
.gt-dashboard { padding: var(--gt-space-6); max-width: 1400px; margin: 0 auto; }

/* ── 管理看板横幅 ── */
.gt-mgmt-banner {
  display: flex; justify-content: space-between; align-items: center;
  background: var(--gt-gradient-primary);
  border-radius: var(--gt-radius-lg);
  padding: 28px 36px;
  margin-bottom: var(--gt-space-6);
  color: #fff;
  position: relative; overflow: hidden;
  box-shadow: 0 8px 32px rgba(75, 45, 119, 0.25);
  /* 网格纹理 */
  background-image:
    var(--gt-gradient-primary),
    linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
  background-size: 100% 100%, 20px 20px, 20px 20px;
}
.gt-mgmt-banner::before {
  content: '';
  position: absolute; top: -40%; right: -10%;
  width: 50%; height: 180%;
  background: radial-gradient(ellipse, rgba(255,255,255,0.08) 0%, transparent 70%);
  pointer-events: none;
  animation: bannerGlow 8s ease-in-out infinite;
}
@keyframes bannerGlow {
  0%, 100% { opacity: 0.6; transform: translate(0, 0); }
  50% { opacity: 1; transform: translate(-15px, 8px); }
}
.gt-mgmt-banner-deco {
  position: absolute; bottom: -20px; right: 40px;
  width: 80px; height: 80px; border-radius: 50%;
  background: rgba(255,255,255,0.06);
  animation: floatBannerDeco 5s ease-in-out infinite;
}
.gt-mgmt-banner-deco::after {
  content: '';
  position: absolute; top: -40px; left: -60px;
  width: 50px; height: 50px; border-radius: 50%;
  background: rgba(255,255,255,0.04);
}
@keyframes floatBannerDeco {
  0%, 100% { transform: translateY(0) scale(1); }
  50% { transform: translateY(-12px) scale(1.05); }
}
.gt-mgmt-title { font-size: 22px; font-weight: 700; margin: 0 0 4px; text-shadow: 0 2px 8px rgba(0,0,0,0.15); }
.gt-mgmt-subtitle { font-size: 13px; opacity: 0.8; margin: 0; }
.gt-mgmt-banner-actions { position: relative; z-index: 1; }
.gt-mgmt-banner-actions .el-button { background: rgba(255,255,255,0.2); border: 1px solid rgba(255,255,255,0.3); color: #fff; }
.gt-mgmt-banner-actions .el-button:hover { background: rgba(255,255,255,0.3); }

/* ── KPI 卡片 ── */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--gt-space-4);
  margin-bottom: var(--gt-space-5);
}
.kpi-card {
  background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md);
  padding: var(--gt-space-5);
  box-shadow: var(--gt-shadow-sm);
  border-left: 3px solid transparent;
  transition: all var(--gt-transition-base);
  cursor: default;
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(75, 45, 119, 0.04);
  border-left-width: 3px;
}
.kpi-card:hover { transform: translateY(-3px); box-shadow: var(--gt-shadow-lg); }
.kpi-card::after {
  content: '';
  position: absolute;
  top: -25px; right: -25px;
  width: 70px; height: 70px;
  border-radius: 50%;
  background: var(--kpi-accent, #4b2d77);
  opacity: 0.06;
  transition: all var(--gt-transition-base);
}
.kpi-card:hover::after { transform: scale(1.4); opacity: 0.12; }
.kpi-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-3); }
.kpi-icon {
  width: 44px; height: 44px; border-radius: var(--gt-radius-lg);
  display: flex; align-items: center; justify-content: center;
}
.kpi-trend {
  font-size: 11px; font-weight: 600; padding: 3px 8px;
  border-radius: var(--gt-radius-full);
}
.trend-up { color: var(--gt-color-success); background: var(--gt-color-success-light); }
.trend-down { color: var(--gt-color-coral); background: var(--gt-color-coral-light); }
.kpi-value {
  font-size: 32px; font-weight: 800; line-height: 1.1; letter-spacing: -1px;
  color: var(--kpi-accent, var(--gt-color-text));
  font-variant-numeric: tabular-nums;
}
.kpi-suffix { font-size: 16px; font-weight: 500; color: var(--gt-color-text-secondary); margin-left: 2px; }
.kpi-label { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); margin-top: 4px; font-weight: 500; }

/* ── 图表卡片 ── */
.chart-row { margin-bottom: var(--gt-space-5); }
.chart-card {
  background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md);
  padding: var(--gt-space-5);
  box-shadow: var(--gt-shadow-sm);
  min-height: 300px;
  border: 1px solid rgba(75, 45, 119, 0.04);
  transition: all var(--gt-transition-base);
  position: relative;
}
.chart-card:hover { box-shadow: var(--gt-shadow-md); }
.chart-card::before {
  content: '';
  position: absolute; top: 0; left: 12px; right: 12px;
  height: 3px; border-radius: 0 0 3px 3px;
  background: var(--gt-gradient-primary);
  opacity: 0;
  transition: opacity var(--gt-transition-base);
}
.chart-card:hover::before { opacity: 1; }
.chart-title {
  font-size: var(--gt-font-size-md); font-weight: 600; color: var(--gt-color-text);
  margin: 0 0 var(--gt-space-3); display: flex; align-items: center;
}
.chart-title::before {
  content: '';
  width: 3px; height: 14px;
  background: var(--gt-gradient-primary);
  border-radius: 2px;
  margin-right: 8px;
  flex-shrink: 0;
}
.chart-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  min-height: 200px; color: var(--gt-color-text-tertiary);
  gap: 8px;
}
.chart-empty .el-icon { opacity: 0.4; }

/* ── 风险预警 ── */
.risk-card { min-height: 300px; }
.risk-list { display: flex; flex-direction: column; gap: var(--gt-space-3); }
.risk-item {
  display: flex; align-items: center; gap: var(--gt-space-3);
  padding: var(--gt-space-3); border-radius: var(--gt-radius-md);
  background: var(--gt-color-bg);
  transition: all var(--gt-transition-fast);
  border: 1px solid transparent;
}
.risk-item:hover { background: var(--gt-color-coral-light); border-color: rgba(255, 81, 73, 0.15); }
.risk-msg { font-size: var(--gt-font-size-sm); color: var(--gt-color-text); }

/* ── 查询面板 ── */
.query-panel { padding: var(--gt-space-6); }
.query-content { min-height: 200px; }
.query-toolbar {
  display: flex; align-items: center; gap: 12px; margin-bottom: 16px;
  padding: 14px 18px; background: linear-gradient(135deg, #faf9fd 0%, #f4f0fa 100%); border-radius: var(--gt-radius-md);
  border: 1px solid rgba(75, 45, 119, 0.06);
}
.query-hint { font-size: 14px; color: #666; }
.query-table { border-radius: 8px; overflow: hidden; }
.query-table :deep(.el-table__header th) { background: #f8f6fb !important; color: #4b2d77; font-weight: 600; }

/* 人员详情面板 */
.staff-detail-panel { animation: fadeIn 0.3s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

.staff-info-bar {
  display: flex; align-items: center; gap: 20px;
  padding: 18px 22px; background: linear-gradient(135deg, #f8f6fb 0%, #f0ebf8 100%);
  border-radius: var(--gt-radius-lg); border: 1px solid rgba(75, 45, 119, 0.08);
  box-shadow: 0 2px 12px rgba(75, 45, 119, 0.06);
}
.staff-avatar {
  width: 52px; height: 52px; border-radius: 50%;
  background: var(--gt-gradient-primary);
  color: #fff; font-size: 22px; font-weight: 700;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  box-shadow: 0 4px 12px rgba(75, 45, 119, 0.25);
}
.staff-info-text { flex: 1; }
.staff-info-name { font-size: 18px; font-weight: 700; color: #333; }
.staff-info-meta { font-size: 13px; color: #888; margin-top: 2px; }
.staff-info-stat { text-align: center; padding: 0 16px; border-left: 1px solid #e0d8ec; }
.staff-info-stat-value { font-size: 24px; font-weight: 800; color: var(--gt-color-primary, #4b2d77); letter-spacing: -0.5px; }
.staff-info-stat-label { font-size: 12px; color: #999; margin-top: 2px; }

.sub-card {
  background: #fafbfc; border-radius: 8px; padding: 14px;
  border: 1px solid #f0f0f5; min-height: 240px;
}
.sub-card-title { margin: 0 0 10px; font-size: 14px; font-weight: 600; color: #333; }

.schedule-item {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 0; border-bottom: 1px solid #f0f0f5;
}
.schedule-item:last-child { border-bottom: none; }
.schedule-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.schedule-project { font-size: 14px; font-weight: 500; color: #333; }

/* ── 响应式 ── */
@media (max-width: 1200px) {
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
  .chart-row .el-col { max-width: 100%; flex: 0 0 100%; margin-bottom: var(--gt-space-4); }
}
@media (max-width: 768px) {
  .kpi-grid { grid-template-columns: 1fr; }
}
</style>
