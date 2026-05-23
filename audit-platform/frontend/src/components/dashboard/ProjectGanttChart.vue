<template>
  <div class="gt-project-gantt">
    <div v-if="!hasData" class="gt-gantt-empty">
      <el-empty :image-size="60" description="暂无可用日期范围的项目" />
    </div>
    <v-chart
      v-else
      :option="ganttOption"
      autoresize
      class="gt-gantt-chart"
      :style="{ height: chartHeight + 'px' }"
      @click="handleChartClick"
    />

    <!-- 颜色图例（仅显示当前数据中实际出现的循环） -->
    <div v-if="hasData" class="gt-gantt-legend" data-testid="gantt-legend">
      <span
        v-for="cycle in legendCycles"
        :key="cycle"
        class="gt-gantt-legend-item"
      >
        <span class="gt-gantt-legend-swatch" :style="{ background: cycleColor(cycle) }" />
        <span class="gt-gantt-legend-label">{{ cycleLabel(cycle) }}</span>
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { use } from 'echarts/core'
import { CustomChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, GridComponent, DataZoomComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import {
  cycleColor,
  cycleLabel,
  buildGanttRows,
  type ProjectGanttItem,
} from './projectGanttUtils'

use([
  CustomChart,
  TitleComponent,
  TooltipComponent,
  GridComponent,
  DataZoomComponent,
  CanvasRenderer,
])

/**
 * ProjectGanttChart — 多项目甘特图（M-1）
 *
 * 数据源：/api/dashboard/manager/projects-overview（含 start_date / due_date / overall_progress / primary_cycle）
 *
 * 视觉规则（design.md ADR-1b）：
 * - 横轴 = 时间（start_date → due_date）
 * - 纵轴 = 项目名（按 start 升序）
 * - 按 primary_cycle 着色（D 蓝 / F 绿 / H 橙 ...）
 * - 进度部分用深色覆盖（overall_progress%）
 * - 点击甘特条 emit 'project-click' 事件
 */
const props = withDefaults(defineProps<{
  projects: ProjectGanttItem[]
}>(), {
  projects: () => [],
})

const emit = defineEmits<{
  (e: 'project-click', projectId: string): void
}>()

// 过滤+排序后的可绘制行
const validRows = computed(() => buildGanttRows(props.projects))
const hasData = computed(() => validRows.value.length > 0)

const chartHeight = computed(() => {
  const rowH = 32
  const baseH = 80
  return Math.max(200, baseH + validRows.value.length * rowH)
})

// 图例：仅显示数据中实际出现的循环（按字母排序）
const legendCycles = computed<string[]>(() => {
  const seen = new Set<string>()
  validRows.value.forEach((r) => seen.add(r.cycle))
  return Array.from(seen).sort()
})

// ─── ECharts custom series renderer ────────────────────────────────────────
function renderItem(_params: any, apiObj: any) {
  const yIndex = apiObj.value(0)
  const start = apiObj.value(1)
  const end = apiObj.value(2)
  const progress = apiObj.value(3)
  const color = apiObj.value(5)

  const startCoord = apiObj.coord([start, yIndex])
  const endCoord = apiObj.coord([end, yIndex])
  const barHeight = apiObj.size([0, 1])[1] * 0.6

  const x = startCoord[0]
  const y = startCoord[1] - barHeight / 2
  const totalWidth = Math.max(2, endCoord[0] - startCoord[0])
  const progressWidth = (totalWidth * progress) / 100

  return {
    type: 'group',
    children: [
      // 背景条（浅色 — 未完成段）
      {
        type: 'rect',
        shape: { x, y, width: totalWidth, height: barHeight, r: 3 },
        style: { fill: color, opacity: 0.25 },
      },
      // 进度条（深色 — 已完成段）
      {
        type: 'rect',
        shape: { x, y, width: progressWidth, height: barHeight, r: 3 },
        style: { fill: color, opacity: 0.95 },
      },
    ],
  }
}

const ganttOption = computed(() => {
  const rows = validRows.value
  const projectNames = rows.map((r) => r.project_name)
  // ECharts custom series data：[yIndex, start, end, progress, project_id, color]
  const data = rows.map((r) => ({
    name: r.project_name,
    value: [r.index, r.start, r.end, r.progress, r.project_id, r.color],
  }))

  return {
    tooltip: {
      trigger: 'item',
      formatter: (p: any) => {
        const v = p.value
        const startStr = new Date(v[1]).toISOString().slice(0, 10)
        const endStr = new Date(v[2]).toISOString().slice(0, 10)
        const progress = v[3]
        return `<b>${p.name}</b><br/>${startStr} → ${endStr}<br/>进度：${progress.toFixed(1)}%`
      },
    },
    grid: {
      top: 20,
      bottom: 50,
      left: 140,
      right: 30,
      containLabel: false,
    },
    xAxis: {
      type: 'time',
      splitLine: { show: true, lineStyle: { type: 'dashed', color: '#e8e8eb' } },
      axisLabel: { color: '#86868b' },
    },
    yAxis: {
      type: 'category',
      data: projectNames,
      inverse: true,
      axisLabel: {
        color: '#1d1d1f',
        formatter: (name: string) => (name.length > 16 ? name.slice(0, 15) + '…' : name),
      },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#d2d2d7' } },
    },
    dataZoom: rows.length > 8
      ? [{ type: 'slider', yAxisIndex: 0, start: 0, end: 100, width: 12, right: 8 }]
      : [],
    series: [
      {
        type: 'custom',
        renderItem,
        encode: { x: [1, 2], y: 0 },
        data,
      },
    ],
  }
})

function handleChartClick(params: any) {
  const projectId = params?.value?.[4]
  if (typeof projectId === 'string') {
    emit('project-click', projectId)
  }
}
</script>

<style scoped>
.gt-project-gantt {
  width: 100%;
}

.gt-gantt-chart {
  width: 100%;
  min-height: 200px;
}

.gt-gantt-empty {
  padding: 24px 0;
  display: flex;
  justify-content: center;
}

.gt-gantt-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 8px;
  padding: 8px 12px;
  border-top: 1px solid var(--gt-color-border, #ebeef5);
}

.gt-gantt-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--gt-color-text-secondary, #6e6e73);
}

.gt-gantt-legend-swatch {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 2px;
}

.gt-gantt-legend-label {
  white-space: nowrap;
}
</style>
