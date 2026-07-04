<script setup lang="ts">
/** F2TabOverallAnalysis — F2-18 总体分析 | Task 17.2 */
import { computed, toRef, type Ref } from 'vue'
import { use } from 'echarts/core'
import { PieChart, BarChart, LineChart } from 'echarts/charts'
import { TooltipComponent, GridComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import { useF2OverallAnalysis } from '../../composables/useF2Analysis'
import { useF2AiGenerate } from '../../composables/useF2AiGenerate'
import type { ChecklistResponse } from '../../composables/useF2FormData'
import type { useF2CrossSheet } from '../../composables/useF2CrossSheet'
import F2ReviewChip from '../shared/F2ReviewChip.vue'

use([PieChart, BarChart, LineChart, TooltipComponent, GridComponent, LegendComponent, CanvasRenderer])

const props = defineProps<{
  wpId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  crossSheet: ReturnType<typeof useF2CrossSheet>
}>()

function fmt(v: number): string {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtPct(v: number): string {
  return `${v.toFixed(1)}%`
}

const {
  structureRows, anomalies, analysisConclusion,
  cogsAmount, computedTurnoverRate, computedTurnoverDays, updateTurnoverInputs,
} = useF2OverallAnalysis({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  crossSheet: props.crossSheet,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2AiGenerate(toRef(props, 'wpId') as Ref<string>)

async function generateAnalysisConclusion() {
  const text = await generateAndConfirm(
    'analysis-conclusion',
    analysisConclusion.value,
    {
      anomalyCount: anomalies.value.length,
      turnoverRate: computedTurnoverRate.value,
      turnoverDays: computedTurnoverDays.value,
    },
    'AI 生成 · 总体分析结论',
  )
  if (text) analysisConclusion.value = text
}

const pieOption = computed(() => ({
  tooltip: { trigger: 'item' as const },
  series: [{
    type: 'pie' as const,
    radius: '58%',
    data: structureRows.value
      .filter((r) => r.currentAmt > 0)
      .map((r) => ({ name: r.label, value: r.currentAmt })),
  }],
}))

const turnoverBarOption = computed(() => ({
  tooltip: { trigger: 'axis' as const },
  grid: { left: 40, right: 16, top: 24, bottom: 28 },
  xAxis: { type: 'category' as const, data: ['周转率(次)', '周转天数(天)'] },
  yAxis: { type: 'value' as const },
  series: [{
    type: 'bar' as const,
    data: [Number(computedTurnoverRate.value.toFixed(2)), Number(computedTurnoverDays.value.toFixed(0))],
    itemStyle: { color: '#409eff' },
  }],
}))

const trendLineOption = computed(() => ({
  tooltip: { trigger: 'axis' as const },
  legend: { data: ['本期', '上期'], bottom: 0 },
  grid: { left: 48, right: 16, top: 28, bottom: 36 },
  xAxis: {
    type: 'category' as const,
    data: structureRows.value.map((r) => r.label),
    axisLabel: { rotate: 30, fontSize: 11 },
  },
  yAxis: { type: 'value' as const },
  series: [
    {
      name: '本期',
      type: 'line' as const,
      data: structureRows.value.map((r) => r.currentAmt),
      smooth: true,
      itemStyle: { color: '#409eff' },
    },
    {
      name: '上期',
      type: 'line' as const,
      data: structureRows.value.map((r) => r.priorAmt),
      smooth: true,
      itemStyle: { color: '#909399' },
    },
  ],
}))
</script>

<template>
  <div class="f2-overall-analysis">
    <details class="guidance-details"><summary>📋 编制提示</summary><p>结构/周转/趋势/异常四区块；结构数据自动从 F2-3~13 取数。</p></details>

    <el-card shadow="never" class="block-card">
      <template #header><span class="block-title">一、结构分析</span></template>
      <div class="chart-row">
        <v-chart v-if="structureRows.some(r => r.currentAmt > 0)" :option="pieOption" autoresize class="pie-chart" />
        <el-table :data="structureRows" border size="small" class="structure-table">
        <el-table-column prop="label" label="存货类别" width="140" />
        <el-table-column label="本期金额" width="120" align="right"><template #default="{ row }">{{ fmt(row.currentAmt) }}</template></el-table-column>
        <el-table-column label="上期金额" width="120" align="right"><template #default="{ row }">{{ fmt(row.priorAmt) }}</template></el-table-column>
        <el-table-column label="占比" width="80" align="right"><template #default="{ row }">{{ fmtPct(row.sharePct) }}</template></el-table-column>
        <el-table-column label="占比变动" width="90" align="right">
          <template #default="{ row }">
            <span :class="{ highlight: row.isHighlight }">{{ fmtPct(row.shareChange) }}</span>
          </template>
        </el-table-column>
      </el-table>
      </div>
    </el-card>

    <el-card shadow="never" class="block-card">
      <template #header><span class="block-title">二、周转分析</span></template>
      <div class="turnover-block">
        <div class="turnover-inputs">
        <span>营业成本：
          <el-input-number :model-value="cogsAmount" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => updateTurnoverInputs({ cogsAmount: v ?? 0 })" />
        </span>
        <span>周转率：{{ computedTurnoverRate.toFixed(2) }}</span>
        <span>周转天数：{{ computedTurnoverDays.toFixed(0) }} 天</span>
        </div>
        <v-chart :option="turnoverBarOption" autoresize class="bar-chart" />
      </div>
    </el-card>

    <el-card shadow="never" class="block-card">
      <template #header><span class="block-title">三、趋势分析</span></template>
      <v-chart
        v-if="structureRows.some(r => r.currentAmt > 0 || r.priorAmt > 0)"
        :option="trendLineOption"
        autoresize
        class="trend-chart"
      />
      <el-empty v-else description="暂无趋势数据" :image-size="60" />
    </el-card>

    <el-card shadow="never" class="block-card">
      <template #header><span class="block-title">四、异常识别</span></template>
      <el-empty v-if="!anomalies.length" description="暂无异常标记" :image-size="60" />
      <el-alert v-for="a in anomalies" :key="a.id" :title="a.message" :type="a.severity === 'danger' ? 'error' : 'warning'" :closable="false" show-icon class="anomaly-item" />
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span class="block-title">分析结论</span>
          <div class="header-actions">
            <F2ReviewChip section-id="F2-18-conclusion" />
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateAnalysisConclusion">AI 生成</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="analysisConclusion" type="textarea" :rows="4" :disabled="isReadonly" placeholder="总体分析结论..." />
    </el-card>
  </div>
</template>

<style scoped>
.f2-overall-analysis { padding: 12px; font-size: 13px; }
.block-card { margin-bottom: 12px; }
.block-title { font-weight: 600; }
.highlight { color: #e6a23c; font-weight: 600; }
.turnover-inputs { display: flex; gap: 24px; flex-wrap: wrap; align-items: center; }
.anomaly-item { margin-bottom: 8px; }
.guidance-details { margin-bottom: 8px; font-size: 12px; color: #606266; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.header-actions { display: flex; gap: 8px; align-items: center; }
.chart-row { display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-start; }
.pie-chart { width: 280px; height: 220px; flex-shrink: 0; }
.structure-table { flex: 1; min-width: 320px; }
.turnover-block { display: flex; gap: 16px; flex-wrap: wrap; align-items: center; }
.bar-chart { width: 280px; height: 180px; }
.trend-chart { width: 100%; min-width: 320px; height: 240px; }
</style>
