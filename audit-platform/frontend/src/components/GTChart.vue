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

// GT 品牌色
const GT_COLORS = ['#4b2d77', '#0094B3', '#FF5149', '#F5A623', '#28a745', '#6c5ce7', '#00b894']

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
  tooltip: { trigger: 'item' },
  ...props.option,
}))
</script>
<style scoped>
.gt-chart { width: 100%; position: relative; }
.gt-chart-loading, .gt-chart-empty { display: flex; align-items: center; justify-content: center; height: 100%; }
</style>
