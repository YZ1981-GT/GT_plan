<template>
  <div class="wh-stats-dashboard">
    <div class="wh-stats-dashboard__header">
      <h3>📈 工时统计</h3>
      <el-button size="small" @click="handleExport" :loading="exporting">📥 导出月报</el-button>
    </div>

    <!-- 周度概览 -->
    <div class="wh-stats-dashboard__summary" v-loading="loading">
      <div class="wh-stats-dashboard__card">
        <div class="wh-stats-dashboard__card-value">{{ weeklyData.this_week_total || 0 }}h</div>
        <div class="wh-stats-dashboard__card-label">本周工时</div>
      </div>
      <div class="wh-stats-dashboard__card">
        <div class="wh-stats-dashboard__card-value">{{ weeklyData.last_week_total || 0 }}h</div>
        <div class="wh-stats-dashboard__card-label">上周工时</div>
      </div>
      <div class="wh-stats-dashboard__card">
        <div class="wh-stats-dashboard__card-value" :class="{ positive: (weeklyData.change_pct || 0) > 0, negative: (weeklyData.change_pct || 0) < 0 }">
          {{ (weeklyData.change_pct || 0) > 0 ? '+' : '' }}{{ weeklyData.change_pct || 0 }}%
        </div>
        <div class="wh-stats-dashboard__card-label">同比变化</div>
      </div>
    </div>

    <!-- 按活动类型分布 -->
    <div class="wh-stats-dashboard__section">
      <h4>按活动类型</h4>
      <div class="wh-stats-dashboard__bar-list">
        <div v-for="item in weeklyData.by_activity_type || []" :key="item.type" class="wh-stats-dashboard__bar-item">
          <span class="wh-stats-dashboard__bar-label">{{ item.type }}</span>
          <div class="wh-stats-dashboard__bar-track">
            <div class="wh-stats-dashboard__bar-fill" :style="{ width: barWidth(item.hours) }"></div>
          </div>
          <span class="wh-stats-dashboard__bar-value">{{ item.hours }}h</span>
        </div>
      </div>
    </div>

    <!-- 按项目分布 -->
    <div class="wh-stats-dashboard__section">
      <h4>按项目</h4>
      <div class="wh-stats-dashboard__bar-list">
        <div v-for="item in weeklyData.by_project || []" :key="item.project" class="wh-stats-dashboard__bar-item">
          <span class="wh-stats-dashboard__bar-label">{{ item.project }}</span>
          <div class="wh-stats-dashboard__bar-track">
            <div class="wh-stats-dashboard__bar-fill wh-stats-dashboard__bar-fill--project" :style="{ width: barWidthProject(item.hours) }"></div>
          </div>
          <span class="wh-stats-dashboard__bar-value">{{ item.hours }}h</span>
        </div>
      </div>
    </div>

    <!-- 热力矩阵 -->
    <div class="wh-stats-dashboard__section">
      <h4>近 4 周负载热力图</h4>
      <div class="wh-stats-dashboard__heatmap" v-loading="heatmapLoading">
        <div v-for="cell in heatmapCells" :key="`${cell.date}-${cell.project}`" class="wh-stats-dashboard__heatmap-cell" :style="{ background: heatColor(cell.hours) }" :title="`${cell.date} ${cell.project}: ${cell.hours}h`">
        </div>
        <div v-if="!heatmapCells.length" class="wh-stats-dashboard__empty">暂无数据</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const heatmapLoading = ref(false)
const exporting = ref(false)
const weeklyData = ref<any>({})
const heatmapCells = ref<any[]>([])

function barWidth(hours: number) {
  const max = Math.max(...(weeklyData.value.by_activity_type || []).map((i: any) => i.hours), 1)
  return `${(hours / max) * 100}%`
}

function barWidthProject(hours: number) {
  const max = Math.max(...(weeklyData.value.by_project || []).map((i: any) => i.hours), 1)
  return `${(hours / max) * 100}%`
}

function heatColor(hours: number) {
  if (hours <= 0) return '#f0f0f0'
  if (hours <= 2) return '#e8d5f5'
  if (hours <= 4) return '#c9a0e0'
  if (hours <= 6) return '#9b59b6'
  if (hours <= 8) return '#7d3c98'
  return '#4b2d77'
}

async function loadWeekly() {
  loading.value = true
  try {
    const { api } = await import('@/services/apiProxy')
    weeklyData.value = await api.get('/api/workhours/stats/weekly') as any || {}
  } catch { weeklyData.value = {} }
  finally { loading.value = false }
}

async function loadHeatmap() {
  heatmapLoading.value = true
  try {
    const { api } = await import('@/services/apiProxy')
    const res = await api.get('/api/workhours/stats/heatmap', { params: { weeks: 4 } }) as any
    heatmapCells.value = res?.cells || []
  } catch { heatmapCells.value = [] }
  finally { heatmapLoading.value = false }
}

async function handleExport() {
  exporting.value = true
  try {
    const { api } = await import('@/services/apiProxy')
    const now = new Date()
    const month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
    const res = await api.get('/api/workhours/stats/export', {
      params: { month },
      responseType: 'blob',
    }) as any
    // 下载 blob
    if (res instanceof Blob) {
      const url = URL.createObjectURL(res)
      const a = document.createElement('a')
      a.href = url
      a.download = `workhour_report_${month}.xlsx`
      a.click()
      URL.revokeObjectURL(url)
      ElMessage.success('导出成功')
    } else {
      ElMessage.info('月报数据已返回（xlsx 不可用时为 JSON）')
    }
  } catch { ElMessage.warning('导出失败') }
  finally { exporting.value = false }
}

onMounted(() => {
  loadWeekly()
  loadHeatmap()
})
</script>

<style scoped>
.wh-stats-dashboard { padding: 16px; }
.wh-stats-dashboard__header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.wh-stats-dashboard__header h3 { margin: 0; font-size: 16px; }
.wh-stats-dashboard__summary { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px; }
.wh-stats-dashboard__card { padding: 16px; background: #f9f5ff; border-radius: 8px; text-align: center; }
.wh-stats-dashboard__card-value { font-size: 24px; font-weight: 700; color: #4b2d77; }
.wh-stats-dashboard__card-value.positive { color: #52c41a; }
.wh-stats-dashboard__card-value.negative { color: #f5222d; }
.wh-stats-dashboard__card-label { font-size: 12px; color: #666; margin-top: 4px; }
.wh-stats-dashboard__section { margin-bottom: 20px; }
.wh-stats-dashboard__section h4 { font-size: 14px; margin: 0 0 10px; }
.wh-stats-dashboard__bar-list { display: flex; flex-direction: column; gap: 8px; }
.wh-stats-dashboard__bar-item { display: flex; align-items: center; gap: 8px; }
.wh-stats-dashboard__bar-label { width: 80px; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wh-stats-dashboard__bar-track { flex: 1; height: 16px; background: #f0f0f0; border-radius: 8px; overflow: hidden; }
.wh-stats-dashboard__bar-fill { height: 100%; background: #4b2d77; border-radius: 8px; transition: width 0.3s; }
.wh-stats-dashboard__bar-fill--project { background: #1890ff; }
.wh-stats-dashboard__bar-value { width: 40px; font-size: 12px; text-align: right; }
.wh-stats-dashboard__heatmap { display: flex; flex-wrap: wrap; gap: 3px; }
.wh-stats-dashboard__heatmap-cell { width: 16px; height: 16px; border-radius: 3px; cursor: pointer; }
.wh-stats-dashboard__empty { color: #999; font-size: 12px; }
</style>
