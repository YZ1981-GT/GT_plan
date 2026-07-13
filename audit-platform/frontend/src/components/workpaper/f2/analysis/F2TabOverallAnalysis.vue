<script setup lang="ts">
/** F2TabOverallAnalysis — F2-18 总体分析 | Task 17.2 */
import { ref, computed, toRef, onMounted, type Ref } from 'vue'
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
import GtIndexChip from '../../GtIndexChip.vue'

use([PieChart, BarChart, LineChart, TooltipComponent, GridComponent, LegendComponent, CanvasRenderer])

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  crossSheet: ReturnType<typeof useF2CrossSheet>
}>()

// ─── 审计说明 / 审计结论 ───────────────────────────────────────────────────────
const NOTE_KEY = 'F2-overall-analysis-audit-note'
const CONCLUSION_KEY = 'F2-overall-analysis-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function persistAudit(key: string, val: string): void {
  const item = { item_id: key, conclusion: null, remark: val }
  props.allResponses.set(key, item)
  window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
}
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  persistAudit(NOTE_KEY, val)
}
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  persistAudit(CONCLUSION_KEY, val)
}
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

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
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 从结构、周转、趋势、异常四个维度对存货整体进行分析，结构数据自动从 F2-3~F2-13 取数。</p>
        <p>2. 存货周转率 = 营业成本 ÷ 平均存货；周转天数 = 365 ÷ 周转率，用于评价存货流动性。</p>
        <p>3. 依《企业会计准则第 1 号——存货》，关注占比与周转异常，识别积压、滞销及减值迹象。</p>
        <p>4. 各区块异常应结合产销率、成本变动综合判断，为跌价准备计提提供依据。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：从结构、周转、趋势维度分析存货整体的合理性，识别异常波动及减值迹象。"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left" />
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:F2-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ structureRows.length }} 类</el-tag>
      </div>
    </div>

    <el-card shadow="never" class="block-card">
      <template #header><span class="block-title">一、结构分析</span></template>
      <div class="chart-row">
        <v-chart v-if="structureRows.some(r => r.currentAmt > 0)" :option="pieOption" autoresize class="pie-chart" />
        <el-table :data="structureRows" border size="small" class="structure-table">
        <el-table-column prop="label" label="存货类别" width="140" />
        <el-table-column label="本期金额" width="120" align="right"><template #default="{ row }">{{ fmt(row.currentAmt) }}</template></el-table-column>
        <el-table-column label="上期金额" width="120" align="right"><template #default="{ row }">{{ fmt(row.priorAmt) }}</template></el-table-column>
        <el-table-column label="占比" width="80" align="right" class-name="auto-calc-col"><template #default="{ row }">{{ fmtPct(row.sharePct) }}</template></el-table-column>
        <el-table-column label="占比变动" width="90" align="right" class-name="auto-calc-col">
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

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">分析结论</span>
          <div class="opinion-actions">
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateAnalysisConclusion">🤖 AI辅助</el-button>
            <F2ReviewChip section-id="F2-18-conclusion" />
          </div>
        </div>
      </template>
      <el-input v-model="analysisConclusion" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }" :disabled="isReadonly" placeholder="总体分析结论..." />
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述存货结构、周转、趋势及异常识别的分析程序、测试情况与结果，以及减值迹象的核查与拟调整/未调整事项及其影响。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项（或审计范围受到限制），不可确认。"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<style scoped>
.f2-overall-analysis { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f2-overall-analysis :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-overall-analysis :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.block-card { margin-bottom: 12px; }
.block-title { font-weight: 600; }
.highlight { color: #e6a23c; font-weight: 600; }
.turnover-inputs { display: flex; gap: 24px; flex-wrap: wrap; align-items: center; }
.anomaly-item { margin-bottom: 8px; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-actions { display: flex; gap: 6px; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.chart-row { display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-start; }
.pie-chart { width: 280px; height: 220px; flex-shrink: 0; }
.structure-table { flex: 1; min-width: 320px; }
.turnover-block { display: flex; gap: 16px; flex-wrap: wrap; align-items: center; }
.bar-chart { width: 280px; height: 180px; }
.trend-chart { width: 100%; min-width: 320px; height: 240px; }
</style>
