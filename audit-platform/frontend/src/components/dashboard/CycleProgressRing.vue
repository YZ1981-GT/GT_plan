<template>
  <div class="cycle-progress-ring">
    <div class="cycle-progress-grid">
      <div
        v-for="item in cycleProgress"
        :key="item.cycle"
        class="cycle-ring-item"
        @click="navigateToCycle(item.cycle)"
      >
        <v-chart
          :option="getRingOption(item)"
          autoresize
          class="cycle-ring-chart"
        />
        <div class="cycle-ring-label">{{ item.cycle_name }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter, useRoute } from 'vue-router'
import { use } from 'echarts/core'
import { PieChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import type { CycleProgressItem } from '@/composables/useDashboardData'

use([PieChart, TooltipComponent, CanvasRenderer])

defineProps<{
  cycleProgress: CycleProgressItem[]
}>()

const router = useRouter()
const route = useRoute()

/**
 * 根据完成率返回对应颜色
 * < 50% → 红色 (#F56C6C)
 * 50%~99% → 橙色 (#E6A23C)
 * 100% → 绿色 (#67C23A)
 */
function getColor(rate: number): string {
  if (rate >= 100) return '#67C23A'
  if (rate >= 50) return '#E6A23C'
  return '#F56C6C'
}

/**
 * 生成单个环形图的 ECharts option
 */
function getRingOption(item: CycleProgressItem) {
  const rate = item.progress_rate
  const color = getColor(rate)
  return {
    tooltip: {
      trigger: 'item',
      formatter: `${item.cycle_name}（${item.cycle}）<br/>完成率：${rate.toFixed(1)}%`,
    },
    series: [
      {
        type: 'pie',
        radius: ['60%', '80%'],
        avoidLabelOverlap: false,
        label: {
          show: true,
          position: 'center',
          formatter: `${Math.round(rate)}%`,
          fontSize: 13,
          fontWeight: 600,
          color,
        },
        emphasis: {
          scale: false,
        },
        data: [
          {
            value: rate,
            name: '已完成',
            itemStyle: { color },
          },
          {
            value: 100 - rate,
            name: '未完成',
            itemStyle: { color: '#f0f0f5' },
          },
        ],
      },
    ],
  }
}

/**
 * 点击环形图跳转到对应循环底稿列表
 */
function navigateToCycle(cycle: string) {
  const projectId = route.params.projectId as string
  router.push({
    name: 'WorkpaperList',
    params: { projectId },
    query: { cycle },
  })
}
</script>

<style scoped>
.cycle-progress-ring {
  width: 100%;
}

.cycle-progress-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.cycle-ring-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  cursor: pointer;
  padding: 8px 4px;
  border-radius: 8px;
  transition: background-color 0.2s;
}

.cycle-ring-item:hover {
  background-color: rgba(75, 45, 119, 0.04);
}

.cycle-ring-chart {
  width: 80px;
  height: 80px;
}

.cycle-ring-label {
  margin-top: 4px;
  font-size: 12px;
  color: var(--gt-color-text-secondary, #6e6e73);
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 80px;
}
</style>
