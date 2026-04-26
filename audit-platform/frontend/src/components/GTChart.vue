<template>
  <div class="gt-chart" :style="{ height: height + 'px' }">
    <div v-if="loading" class="gt-chart-loading">
      <el-skeleton :rows="3" animated />
    </div>
    <div v-else-if="isEmpty" class="gt-chart-empty">
      <el-empty :description="emptyText" :image-size="60" />
    </div>
    <v-chart v-else :option="mergedOption" autoresize />
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { use } from 'echarts/core'
import { PieChart, BarChart, LineChart, HeatmapChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, GridComponent, LegendComponent, CalendarComponent, VisualMapComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'

use([PieChart, BarChart, LineChart, HeatmapChart, TitleComponent, TooltipComponent, GridComponent, LegendComponent, CalendarComponent, VisualMapComponent, CanvasRenderer])

// GT 品牌色 — 渐变色系
const GT_COLORS = ['#4b2d77', '#0094B3', '#FF5149', '#FFC23D', '#28a745', '#6b42a8', '#00b894', '#A06DFF']

const GT_THEME = {
  textStyle: { fontFamily: 'GT Walsheim, Microsoft YaHei, PingFang SC, sans-serif' },
  title: { textStyle: { color: '#1d1d1f', fontWeight: 700 } },
  tooltip: {
    backgroundColor: 'rgba(255,255,255,0.96)',
    borderColor: 'rgba(75,45,119,0.1)',
    borderWidth: 1,
    textStyle: { color: '#1d1d1f', fontSize: 13 },
    extraCssText: 'box-shadow: 0 4px 16px rgba(75,45,119,0.12); border-radius: 8px; backdrop-filter: blur(8px);',
  },
  legend: { textStyle: { color: '#6e6e73', fontSize: 12 } },
  categoryAxis: {
    axisLine: { lineStyle: { color: '#e5e5ea' } },
    axisTick: { show: false },
    axisLabel: { color: '#6e6e73', fontSize: 12 },
    splitLine: { lineStyle: { color: '#f0f0f5', type: 'dashed' } },
  },
  valueAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: '#999', fontSize: 11 },
    splitLine: { lineStyle: { color: '#f0f0f5', type: 'dashed' } },
  },
}

const props = withDefaults(defineProps<{
  option: Record<string, any>
  height?: number
  loading?: boolean
  emptyText?: string
}>(), { height: 300, loading: false, emptyText: '暂无数据' })

const isEmpty = computed(() => {
  if (!props.option) return true
  const series = props.option.series
  if (!series) return true
  if (Array.isArray(series) && series.length === 0) return true
  return false
})

const mergedOption = computed(() => ({
  color: GT_COLORS,
  ...GT_THEME,
  tooltip: { trigger: 'item', ...GT_THEME.tooltip },
  ...props.option,
}))
</script>
<style scoped>
.gt-chart { width: 100%; position: relative; border-radius: var(--gt-radius-md, 8px); overflow: hidden; }
.gt-chart-loading, .gt-chart-empty { display: flex; align-items: center; justify-content: center; height: 100%; flex-direction: column; gap: 8px; }
</style>
