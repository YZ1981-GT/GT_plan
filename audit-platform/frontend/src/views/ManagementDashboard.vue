<template>
  <div class="gt-dashboard gt-fade-in">
    <div class="gt-dash-header">
      <h2 class="gt-page-title">管理看板</h2>
      <el-button size="small" @click="refreshAll" :loading="loading">刷新</el-button>
    </div>

    <!-- 关键指标卡片 -->
    <el-row :gutter="16" class="gt-stat-row">
      <el-col :span="6" v-for="card in statCards" :key="card.label">
        <div class="gt-stat-card">
          <div class="gt-stat-value">{{ card.value }}</div>
          <div class="gt-stat-label">{{ card.label }}</div>
        </div>
      </el-col>
    </el-row>

    <!-- 项目进度 + 人员负荷 -->
    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="12">
        <div class="gt-chart-card">
          <h3 class="gt-chart-title">项目进度总览</h3>
          <div v-if="projectProgress.length === 0" class="gt-chart-empty">暂无数据</div>
          <div v-else class="gt-progress-list">
            <div v-for="p in projectProgress" :key="p.project_id" class="gt-progress-item">
              <span class="gt-progress-name">{{ p.project_name }}</span>
              <el-progress :percentage="p.progress" :stroke-width="14" :text-inside="true"
                :color="p.progress >= 90 ? '#28a745' : p.progress >= 50 ? '#4b2d77' : '#F5A623'" />
            </div>
          </div>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="gt-chart-card">
          <h3 class="gt-chart-title">人员负荷排行（本周工时 Top10）</h3>
          <GTChart v-if="workloadOption" :option="workloadOption" :height="280" />
          <div v-else-if="staffWorkload.length === 0" class="gt-chart-empty">暂无数据</div>
        </div>
      </el-col>
    </el-row>

    <!-- 风险预警 + 审计质量 -->
    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="8">
        <div class="gt-chart-card">
          <h3 class="gt-chart-title">风险预警</h3>
          <div v-if="riskAlerts.length === 0" class="gt-chart-empty">无风险预警</div>
          <div v-for="a in riskAlerts" :key="a.type" style="padding: 6px 0; border-bottom: 1px solid #f0f0f0">
            <el-tag type="danger" size="small">{{ a.count }}</el-tag>
            <span style="margin-left: 8px; font-size: 13px">{{ a.message }}</span>
          </div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="gt-chart-card">
          <h3 class="gt-chart-title">集团审计总览</h3>
          <GTChart v-if="groupOption" :option="groupOption" :height="220" />
          <div v-else class="gt-chart-empty">无合并项目</div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="gt-chart-card">
          <h3 class="gt-chart-title">工时热力图</h3>
          <GTChart v-if="heatmapOption" :option="heatmapOption" :height="220" />
          <div v-else class="gt-chart-empty">暂无工时数据</div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import http from '@/utils/http'
import GTChart from '@/components/GTChart.vue'

const loading = ref(false)
const statCards = ref([
  { label: '在审项目', value: 0 },
  { label: '本周工时', value: '0h' },
  { label: '人员总数', value: 0 },
  { label: '超期项目', value: 0 },
])
const projectProgress = ref<any[]>([])
const staffWorkload = ref<any[]>([])
const riskAlerts = ref<any[]>([])
const groupProgress = ref<any[]>([])
const heatmapData = ref<any[]>([])

const workloadOption = computed(() => {
  if (!staffWorkload.value.length) return null
  const top10 = staffWorkload.value.slice(0, 10)
  return {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: top10.map((s: any) => s.name), axisLabel: { rotate: 30, fontSize: 11 } },
    yAxis: { type: 'value', name: '工时(h)' },
    series: [{ type: 'bar', data: top10.map((s: any) => s.week_hours), itemStyle: { color: '#4b2d77' } }],
  }
})

const groupOption = computed(() => {
  if (!groupProgress.value.length) return null
  return {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'value', max: 100 },
    yAxis: { type: 'category', data: groupProgress.value.map((g: any) => g.name), axisLabel: { fontSize: 11 } },
    series: [{ type: 'bar', data: groupProgress.value.map((g: any) => g.progress), itemStyle: { color: '#0094B3' } }],
  }
})

const heatmapOption = computed(() => {
  if (!heatmapData.value.length) return null
  const names = [...new Set(heatmapData.value.map((d: any) => d.staff_name))]
  const dates = [...new Set(heatmapData.value.map((d: any) => d.date))].sort()
  const data = heatmapData.value.map((d: any) => [dates.indexOf(d.date), names.indexOf(d.staff_name), d.hours])
  return {
    tooltip: { formatter: (p: any) => `${names[p.value[1]]} ${dates[p.value[0]]}: ${p.value[2]}h` },
    xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 10, rotate: 45 } },
    yAxis: { type: 'category', data: names, axisLabel: { fontSize: 11 } },
    visualMap: { min: 0, max: 12, calculable: true, orient: 'horizontal', left: 'center', bottom: 0, inRange: { color: ['#f8f6fb', '#4b2d77'] } },
    series: [{ type: 'heatmap', data, label: { show: false } }],
  }
})

async function refreshAll() {
  loading.value = true
  try {
    const [overview, progress, workload, alerts, group, heatmap] = await Promise.all([
      http.get('/api/dashboard/overview').then(r => r.data.data ?? r.data),
      http.get('/api/dashboard/project-progress').then(r => r.data.data ?? r.data),
      http.get('/api/dashboard/staff-workload').then(r => r.data.data ?? r.data),
      http.get('/api/dashboard/risk-alerts').then(r => r.data.data ?? r.data).catch(() => []),
      http.get('/api/dashboard/group-progress').then(r => r.data.data ?? r.data).catch(() => []),
      http.get('/api/dashboard/hours-heatmap').then(r => r.data.data ?? r.data).catch(() => []),
    ])
    statCards.value = [
      { label: '在审项目', value: overview.active_projects },
      { label: '本周工时', value: overview.week_hours + 'h' },
      { label: '人员总数', value: overview.staff_count },
      { label: '超期项目', value: overview.overdue_projects },
    ]
    projectProgress.value = progress
    staffWorkload.value = workload
    riskAlerts.value = Array.isArray(alerts) ? alerts : []
    groupProgress.value = Array.isArray(group) ? group : []
    heatmapData.value = Array.isArray(heatmap) ? heatmap : []
  } finally { loading.value = false }
}

let timer: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  refreshAll()
  timer = setInterval(refreshAll, 30000) // 30s 自动刷新
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.gt-dashboard { padding: var(--gt-space-4); }
.gt-dash-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-4); }
.gt-stat-row { margin-bottom: var(--gt-space-2); }
.gt-stat-card {
  background: white; border-radius: var(--gt-radius-md); padding: 20px; text-align: center;
  box-shadow: var(--gt-shadow-sm); border-left: 3px solid var(--gt-color-primary, #4b2d77);
}
.gt-stat-value { font-size: 28px; font-weight: 700; color: var(--gt-color-primary, #4b2d77); }
.gt-stat-label { font-size: 13px; color: #888; margin-top: 4px; }
.gt-chart-card {
  background: white; border-radius: var(--gt-radius-md); padding: 16px;
  box-shadow: var(--gt-shadow-sm); min-height: 300px;
}
.gt-chart-title { font-size: 15px; font-weight: 600; margin-bottom: 12px; color: #333; }
.gt-chart-empty { text-align: center; color: #ccc; padding: 60px 0; }
.gt-progress-item { margin-bottom: 10px; }
.gt-progress-name { font-size: 13px; color: #555; display: block; margin-bottom: 4px; }
.gt-workload-item { margin-bottom: 10px; }
.gt-workload-name { font-size: 13px; font-weight: 600; color: #333; }
.gt-workload-info { font-size: 12px; color: #999; margin-left: 8px; }
</style>
