<template>
  <div class="eqcr-trend-chart">
    <el-tabs v-model="activeTab">
      <el-tab-pane label="年度趋势" name="trends">
        <div class="chart-container">
          <div ref="chartRef" class="echarts-box" />
        </div>
      </el-tab-pane>
      <el-tab-pane label="常见问题 Top 5" name="issues">
        <el-table :data="topIssues" stripe>
          <el-table-column type="index" label="#" width="60" />
          <el-table-column prop="category" label="问题分类" min-width="200" />
          <el-table-column prop="count" label="出现次数" width="120">
            <template #default="{ row }">
              <span class="gt-amt">{{ row.count }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- Warnings -->
    <el-alert
      v-for="(warn, idx) in warnings"
      :key="idx"
      :title="warn"
      type="warning"
      show-icon
      :closable="false"
      class="warn-alert"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, watch } from 'vue'
import axios from 'axios'
import * as echarts from 'echarts'

interface YearTrend {
  year: number
  pass_rate: number
  avg_review_days: number
  total_projects: number
}

interface TopIssue {
  category: string
  count: number
}

const activeTab = ref('trends')
const yearlyTrends = ref<YearTrend[]>([])
const topIssues = ref<TopIssue[]>([])
const warnings = ref<string[]>([])
const chartRef = ref<HTMLElement | null>(null)

let chartInstance: echarts.ECharts | null = null

onMounted(async () => {
  await loadData()
  await nextTick()
  initChart()
})

watch(activeTab, async (val) => {
  if (val === 'trends') {
    await nextTick()
    initChart()
  }
})

async function loadData() {
  try {
    const res = await axios.get('/api/eqcr/metrics/trends')
    yearlyTrends.value = res.data.yearly_trends || []
    topIssues.value = res.data.top_issues || []
    warnings.value = res.data.warnings || []
  } catch {
    warnings.value = ['数据加载失败']
  }
}

function initChart() {
  if (!chartRef.value) return

  if (chartInstance) {
    chartInstance.dispose()
  }

  chartInstance = echarts.init(chartRef.value)

  const years = yearlyTrends.value.map(t => String(t.year))
  const passRates = yearlyTrends.value.map(t => t.pass_rate)
  const reviewDays = yearlyTrends.value.map(t => t.avg_review_days)

  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
    },
    legend: {
      data: ['通过率 (%)', '平均复核天数'],
    },
    xAxis: {
      type: 'category',
      data: years,
    },
    yAxis: [
      {
        type: 'value',
        name: '通过率 (%)',
        min: 0,
        max: 100,
        axisLabel: { formatter: '{value}%' },
      },
      {
        type: 'value',
        name: '复核天数',
        min: 0,
      },
    ],
    series: [
      {
        name: '通过率 (%)',
        type: 'line',
        yAxisIndex: 0,
        data: passRates,
        smooth: true,
        itemStyle: { color: '#409EFF' },
        areaStyle: { color: 'rgba(64, 158, 255, 0.1)' },
      },
      {
        name: '平均复核天数',
        type: 'bar',
        yAxisIndex: 1,
        data: reviewDays,
        itemStyle: { color: '#67C23A' },
        barWidth: '40%',
      },
    ],
  }

  chartInstance.setOption(option)
}
</script>

<style scoped>
.eqcr-trend-chart {
  padding: 16px;
}

.chart-container {
  width: 100%;
  height: 400px;
}

.echarts-box {
  width: 100%;
  height: 100%;
}

.warn-alert {
  margin-top: 12px;
}
</style>
