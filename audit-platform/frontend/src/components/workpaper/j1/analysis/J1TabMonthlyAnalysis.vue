<template>
  <div class="j1-tab-monthly">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：通过月度趋势分析识别应付职工薪酬计提的异常波动（偏离月均 &gt;30%），关注年终奖跨期、离职集中、社保调整等异常，实施分析性程序。
      </template>
    </el-alert>

    <el-card shadow="never">
      <template #header>
        <div class="header-row">
          <span class="section-title">应付职工薪酬月度分析表（12列横向）</span>
          <el-tag v-if="hasAbnormalFluctuation" type="danger" size="small">存在异常波动</el-tag>
          <span class="chip-wrap"><GtIndexChip value="wp:J1-1" :context-project-id="projectId" /></span>
          <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
        </div>
      </template>

      <!-- 12列横向表格 -->
      <div class="monthly-table-wrapper">
        <el-table :data="rows" border size="small" style="font-size: 13px" max-height="500"
          :row-class-name="({ row }) => row.isSubtotal ? 'subtotal-row' : ''">
          <el-table-column prop="label" label="项目" min-width="140" fixed />
          <el-table-column v-for="m in 12" :key="m" :label="`${m}月`" width="90" align="right">
            <template #default="{ row }">
              <span :class="{ 'fluctuation-cell': isFluctuation(row.id, m - 1) }">
                {{ row.months?.[m - 1]?.toLocaleString() || '-' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="合计" width="110" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="formula-cell" title="合计=SUM(1月~12月)">{{ row.total?.toLocaleString() }}</span>
            </template>
          </el-table-column>
          <el-table-column label="月均" width="100" align="right">
            <template #default="{ row }">{{ row.average?.toFixed(0) }}</template>
          </el-table-column>
          <el-table-column label="同比变动" width="90" align="right">
            <template #default="{ row }">
              <span :class="{ 'text-danger': Math.abs(row.changeRate) > 30 }">
                {{ row.changeRate?.toFixed(1) }}%
              </span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- 趋势图 -->
    <el-card shadow="never" class="chart-card">
      <template #header><span class="section-title">月度趋势图</span></template>
      <div class="chart-placeholder">
        <div class="mini-bar-chart">
          <div v-for="(val, idx) in chartData" :key="idx" class="bar-item">
            <div class="bar" :style="{ height: barHeight(val) + 'px' }" />
            <span class="bar-label">{{ idx + 1 }}月</span>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 波动高亮说明 -->
    <el-card v-if="fluctuations.length > 0" shadow="never" class="fluctuation-card">
      <template #header><span class="section-title">异常波动（偏离月均>30%）</span></template>
      <el-table :data="fluctuations" size="small" style="font-size: 13px">
        <el-table-column prop="rowId" label="项目" width="120" />
        <el-table-column label="月份" width="80">
          <template #default="{ row }">{{ row.monthIndex + 1 }}月</template>
        </el-table-column>
        <el-table-column prop="amount" label="金额" width="120" align="right" />
        <el-table-column label="偏离率" width="100" align="right">
          <template #default="{ row }">
            <span class="text-danger">{{ row.avgDeviation?.toFixed(1) }}%</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 月度分析用于实施分析性程序，识别薪酬计提的期间异常与合理性。</p>
        <p>2. 灰色底纹"合计"列为自动计算列（SUM 1~12 月），不可手动编辑。</p>
        <p>3. 单月金额偏离月均超过 30% 自动高亮，须结合业务实质（年终奖、离职补偿等）判断合理性。</p>
        <p>4. 同比变动率异常项应与同行业对比分析表（J1-5）交叉印证。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useJ1MonthlyAnalysis } from '@/composables/workpaper/j1/useJ1MonthlyAnalysis'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
}>()

const htmlDataRef = ref(props.htmlData || {})
const { rows, fluctuations, chartData, hasAbnormalFluctuation, initFromHtmlData } = useJ1MonthlyAnalysis(htmlDataRef)

onMounted(() => { if (props.htmlData) initFromHtmlData(props.htmlData) })

function isFluctuation(rowId: string, monthIdx: number): boolean {
  return fluctuations.value.some(f => f.rowId === rowId && f.monthIndex === monthIdx)
}

function barHeight(val: number): number {
  const max = Math.max(...chartData.value.map(Math.abs), 1)
  return Math.max(4, (Math.abs(val) / max) * 120)
}
</script>

<style scoped>
.j1-tab-monthly { padding: 16px; }
.audit-objective { margin-bottom: 12px; }
.header-row { display: flex; align-items: center; gap: 12px; }
.chip-wrap { display: inline-flex; align-items: center; }
.section-title { font-weight: 600; font-size: 15px; }
.monthly-table-wrapper { overflow-x: auto; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.fluctuation-cell { background: #fef0f0; color: #f56c6c; font-weight: 600; padding: 2px 4px; border-radius: 2px; }
.subtotal-row { background-color: #f5f7fa !important; font-weight: 600; }
.text-danger { color: #f56c6c; }
.chart-card { margin-top: 16px; }
.fluctuation-card { margin-top: 16px; }
.chart-placeholder { padding: 16px; }
.mini-bar-chart { display: flex; align-items: flex-end; gap: 8px; height: 140px; padding: 0 16px; }
.bar-item { display: flex; flex-direction: column; align-items: center; flex: 1; }
.bar { width: 100%; max-width: 40px; background: linear-gradient(180deg, #409eff 0%, #79bbff 100%); border-radius: 2px 2px 0 0; transition: height 0.3s; }
.bar-label { font-size: 11px; color: #909399; margin-top: 4px; }
</style>
