<template>
  <div class="c24-benford">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <div class="methodology-bar" />
      <p>本福特定律测试：统计分录金额的首位非零数字分布，与本福特理论分布（log10(1+1/d)）对比，通过卡方检验判断是否存在显著偏离。</p>
    </div>

    <!-- 本福特首位数分布图表 (CSS bars) -->
    <section class="c24-section">
      <div class="section-header">
        <span class="section-title">首位数分布图表</span>
      </div>

      <el-alert v-if="!hasData" type="info" :closable="false" show-icon style="margin-bottom: 12px;">
        尚未导入分录数据，无法进行本福特分析。
      </el-alert>

      <div v-if="hasData" class="benford-chart">
        <div class="chart-legend">
          <span class="legend-item"><span class="legend-bar actual" />实际分布</span>
          <span class="legend-item"><span class="legend-bar expected" />理论分布</span>
        </div>
        <div class="chart-bars">
          <div v-for="item in distribution" :key="item.digit" class="bar-group">
            <div class="bar-label">{{ item.digit }}</div>
            <div class="bar-container">
              <div class="bar actual" :style="{ width: barWidth(item.actual) }" :title="`实际: ${(item.actual * 100).toFixed(1)}%`" />
              <div class="bar expected" :style="{ width: barWidth(item.expected) }" :title="`理论: ${(item.expected * 100).toFixed(1)}%`" />
            </div>
            <div class="bar-pct">{{ (item.actual * 100).toFixed(1) }}%</div>
          </div>
        </div>
      </div>
    </section>

    <!-- 数值表 -->
    <section v-if="hasData" class="c24-section">
      <div class="section-header">
        <span class="section-title">本福特分布统计表</span>
      </div>
      <el-table :data="distribution" border size="small" class="c24-table">
        <el-table-column label="首位数" prop="digit" width="80" align="center" />
        <el-table-column label="理论比例" width="100" align="center">
          <template #default="{ row }"><span class="formula-cell" title="来源：log10(1+1/d)">{{ (row.expected * 100).toFixed(2) }}%</span></template>
        </el-table-column>
        <el-table-column label="实际数量" width="90" align="center">
          <template #default="{ row }"><span class="formula-cell" title="来源：benfordDistribution.count">{{ row.count }}</span></template>
        </el-table-column>
        <el-table-column label="实际比例" width="100" align="center">
          <template #default="{ row }"><span class="formula-cell" title="来源：count/total">{{ (row.actual * 100).toFixed(2) }}%</span></template>
        </el-table-column>
        <el-table-column label="偏差" width="100" align="center">
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'text-danger': Math.abs(row.deviation) > 0.05 }" title="来源：actual-expected">
              {{ (row.deviation * 100).toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column label="卡方贡献" width="100" align="center">
          <template #default="{ row }"><span class="formula-cell" title="来源：(O-E)²/E">{{ row.chi2Contribution.toFixed(3) }}</span></template>
        </el-table-column>
      </el-table>
    </section>

    <!-- 卡方检验结果 -->
    <section v-if="hasData" class="c24-section">
      <div class="section-header">
        <span class="section-title">卡方检验结果</span>
      </div>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="样本数量">
          <span class="formula-cell" title="来源：有效金额数">{{ sampleCount }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="显著性水平 (α)">
          <span class="formula-cell" title="来源：配置参数">{{ alpha }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="卡方统计值">
          <span class="formula-cell" title="来源：Σ(O-E)²/E">{{ chiResult.chi2Total.toFixed(4) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="临界值 (df=8)">
          <span class="formula-cell" title="来源：CHISQ.INV.RT(α,8)">{{ chiResult.criticalValue.toFixed(3) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="检验结论" :span="2">
          <el-tag :type="chiResult.significant ? 'danger' : 'success'" size="small">
            {{ chiResult.significant ? '显著偏离本福特分布' : '未显著偏离本福特分布' }}
          </el-tag>
          <span style="margin-left: 8px; color: #606266; font-size: 12px;">
            （χ² = {{ chiResult.chi2Total.toFixed(3) }} {{ chiResult.significant ? '>' : '≤' }} {{ chiResult.criticalValue.toFixed(3) }}）
          </span>
        </el-descriptions-item>
      </el-descriptions>

      <el-alert
        v-if="chiResult.significant"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top: 12px;"
      >
        首位数分布显著偏离本福特定律，可能存在人为编造或异常模式，建议进一步核查。
      </el-alert>

      <!-- Req 11.3: 扩大核查范围建议 -->
      <el-alert
        v-if="significantDigitDeviation"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top: 12px;"
        data-testid="benford-expand-scope-alert"
      >
        {{ significantDigitDeviation }}
      </el-alert>
    </section>

    <!-- 测试结论 -->
    <section class="c24-section">
      <div class="section-header">
        <span class="section-title">测试结论</span>
        <el-button v-if="!isReadonly" size="small" @click="$emit('ai-suggest', 'C24-benford-conclusion')">AI 辅助</el-button>
      </div>
      <el-input
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :model-value="conclusion"
        :disabled="isReadonly"
        placeholder="请填写本福特定律测试结论"
        @input="$emit('update:conclusion', $event)"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { BenfordDigitResult, BenfordTestResult } from '@/composables/useC24AnalyticsEngine'

const props = defineProps<{
  distribution: BenfordDigitResult[]
  chiResult: BenfordTestResult
  sampleCount: number
  alpha: number
  hasData: boolean
  conclusion: string
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'update:conclusion', val: string): void
  (e: 'ai-suggest', fieldId: string): void
}>()

/** Req 11.3: 首位数偏差 > 0.05 时给出扩大核查建议 */
const BENFORD_DEVIATION_THRESHOLD = 0.05

const significantDigitDeviation = computed<string>(() => {
  if (!props.hasData || props.distribution.length === 0) return ''
  const deviating = props.distribution.filter(d => Math.abs(d.deviation) > BENFORD_DEVIATION_THRESHOLD)
  if (deviating.length === 0) return ''
  const digits = deviating.map(d => d.digit).join('、')
  return `建议扩大核查范围：首位数 ${digits} 显著偏离本福特理论分布`
})

function barWidth(ratio: number): string {
  // Max bar width 100% represents 35% (digit 1's expected ~30%)
  return `${Math.min(ratio / 0.35 * 100, 100)}%`
}
</script>

<style scoped>
.c24-benford { font-size: 13px; }
.methodology-context { display: flex; gap: 10px; align-items: flex-start; padding: 10px 12px; margin-bottom: 16px; background: #fffbf0; border-radius: 4px; }
.methodology-bar { width: 3px; min-height: 20px; align-self: stretch; background: #e6a23c; border-radius: 2px; flex-shrink: 0; }
.methodology-context p { margin: 0; font-size: 13px; color: #606266; line-height: 1.6; }
.c24-section { margin-bottom: 20px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.section-title { font-weight: 600; font-size: 14px; color: #303133; }
.c24-table { font-size: 13px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; color: #409eff; }
.text-danger { color: #f56c6c !important; }

/* Benford Chart */
.benford-chart { padding: 12px; background: #fafafa; border-radius: 6px; border: 1px solid #ebeef5; }
.chart-legend { display: flex; gap: 16px; margin-bottom: 12px; justify-content: flex-end; }
.legend-item { display: flex; align-items: center; gap: 4px; font-size: 12px; color: #606266; }
.legend-bar { display: inline-block; width: 24px; height: 10px; border-radius: 2px; }
.legend-bar.actual { background: #409eff; }
.legend-bar.expected { background: #e6a23c; opacity: 0.7; }
.chart-bars { display: flex; flex-direction: column; gap: 6px; }
.bar-group { display: flex; align-items: center; gap: 8px; }
.bar-label { width: 20px; text-align: center; font-weight: 600; color: #303133; }
.bar-container { flex: 1; display: flex; flex-direction: column; gap: 2px; }
.bar { height: 12px; border-radius: 2px; transition: width 0.3s ease; min-width: 2px; }
.bar.actual { background: #409eff; }
.bar.expected { background: #e6a23c; opacity: 0.7; }
.bar-pct { width: 50px; text-align: right; font-size: 11px; color: #909399; }
</style>
