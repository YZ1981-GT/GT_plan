<template>
  <div class="c24-benford">
    <!-- 顶部蓝色渐变引导区 -->
    <div class="c24-guide-area">
      <div class="guide-steps">
        <div class="guide-step">
          <span class="guide-num">①</span>
          <span class="guide-text">导入分录数据后系统自动提取所有金额的首位非零数字</span>
        </div>
        <div class="guide-step">
          <span class="guide-num">②</span>
          <span class="guide-text">统计首位数 1~9 的实际频率并与本福特理论分布对比</span>
        </div>
        <div class="guide-step">
          <span class="guide-num">③</span>
          <span class="guide-text">卡方检验判断偏离是否显著，显著时需关注异常数字</span>
        </div>
        <div class="guide-step">
          <span class="guide-num">④</span>
          <span class="guide-text">结合异常数字对应分录进一步核查，形成测试结论</span>
        </div>
      </div>
    </div>

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <div class="methodology-bar" />
      <div class="methodology-content">
        <p><b>一、审计目标</b></p>
        <p>运用本福特定律对会计分录金额的首位数分布进行统计分析，识别是否存在非常态分布，以辅助判断是否有人为编造金额、虚构交易或凌驾于控制之上的风险。</p>
        <p style="margin-top:8px;"><b>二、审计过程</b></p>
        <p>1. <b>测试范围：</b>期间、分录范围、币种、科目层级、借贷方向等。</p>
        <p>2. <b>数据筛选与处理：</b>保留金额≠0、非货币性数据等符合统计分析要求的记录。保证绝对值首位数的非零性。</p>
        <p>3. <b>样本数量：</b>{{ sampleCount > 0 ? `${sampleCount.toLocaleString()} 条` : '待导入数据' }}（一般建议 ≥ 500 条以保证统计有效性）。</p>
        <p>4. <b>检验评估方法：</b>使用卡方统计量 χ² = Σ(O-E)²/E，自由度 df=8（数字 1~9 减 1），在 α={{ alpha }} 水平下比较临界值 {{ chiResult.criticalValue.toFixed(3) }}。</p>
        <p>5. <b>显著性水平设为：</b>{{ alpha }}（即 {{ (alpha * 100).toFixed(0) }}% 误判风险）。</p>
      </div>
    </div>

    <!-- 编制提示 -->
    <details class="c24-compile-hint">
      <summary>📖 编制提示与解读指引</summary>
      <div class="hint-body">
        <p><b>本福特定律（Benford's Law）：</b>在自然产生的数据集中，首位数字为 d 的概率 = log₁₀(1 + 1/d)。例如首位数为 1 的概率约 30.1%，为 9 的概率仅 4.6%。</p>
        <p><b>适用场景：</b>适用于跨越多个数量级的数据（如分录金额、发票金额）。不适用于固定范围数据（如部门编号、电话号码）或人为指定金额。</p>
        <p><b>偏离解读：</b></p>
        <ul>
          <li>首位数 <b>1 偏低、7/8/9 偏高</b> → 可能存在人为编造的金额（虚构交易倾向使用较大首位数）</li>
          <li>首位数 <b>5 偏高</b> → 可能存在刚好低于审批限额（如限额 50 万→大量 4x 万分录）</li>
          <li>单一数字显著偏高 → 需追溯对应分录集合，核查是否有合理商业解释</li>
          <li>多个数字均偏离 → 数据整体异常，需扩大抽查范围</li>
        </ul>
        <p><b>注意事项：</b>单独的本福特测试不能直接得出舞弊结论。显著偏离时应与 C24-5 异常分录筛选结合，追溯具体分录并获取充分审计证据。</p>
      </div>
    </details>

    <!-- 本福特首位数分布图表 (CSS bars) -->
    <section class="c24-section">
      <div class="section-header">
        <span class="section-title">首位数分布图表</span>
        <el-tag v-if="hasData" size="small" type="info" effect="plain">样本量：{{ sampleCount.toLocaleString() }}</el-tag>
      </div>

      <el-alert v-if="!hasData" type="info" :closable="false" show-icon style="margin-bottom: 12px;">
        <template #title>尚未导入分录数据，无法进行本福特分析</template>
        <p style="margin:4px 0 0;font-size:12px;color:#606266;">请先在数据源区域点击「从序时账导入」或「Excel导入」加载会计分录，系统将自动计算首位数分布。</p>
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
        <el-tooltip content="卡方检验：衡量实际分布与理论分布之间差异大小的统计方法。χ²值越大表示偏离越严重。" placement="top">
          <el-icon style="cursor:help;color:#909399;"><QuestionFilled /></el-icon>
        </el-tooltip>
      </div>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="样本数量">
          <span class="formula-cell" title="来源：有效金额数（去除零值）">{{ sampleCount.toLocaleString() }}</span>
          <el-tag v-if="sampleCount < 500" type="warning" size="small" style="margin-left:6px;">样本偏少</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="显著性水平 (α)">
          <span class="formula-cell" title="来源：配置参数，通常取0.05。α越小判定越严格">{{ alpha }}</span>
          <span style="margin-left:4px;font-size:11px;color:#909399;">（{{ (alpha * 100).toFixed(0) }}% 误判风险）</span>
        </el-descriptions-item>
        <el-descriptions-item label="卡方统计值 (χ²)">
          <span class="formula-cell" title="来源：Σ(实际频率-理论频率)²/理论频率">{{ chiResult.chi2Total.toFixed(4) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="临界值 (df=8)">
          <span class="formula-cell" title="来源：CHISQ.INV.RT(α,8)，df=9个数字-1=8">{{ chiResult.criticalValue.toFixed(3) }}</span>
          <span style="margin-left:4px;font-size:11px;color:#909399;">（自由度=8）</span>
        </el-descriptions-item>
        <el-descriptions-item label="检验结论" :span="2">
          <el-tag :type="chiResult.significant ? 'danger' : 'success'" size="small">
            {{ chiResult.significant ? '⚠ 显著偏离本福特分布' : '✓ 未显著偏离本福特分布' }}
          </el-tag>
          <span style="margin-left: 8px; color: #606266; font-size: 12px;">
            （χ² = {{ chiResult.chi2Total.toFixed(3) }} {{ chiResult.significant ? '>' : '≤' }} {{ chiResult.criticalValue.toFixed(3) }}）
          </span>
        </el-descriptions-item>
      </el-descriptions>

      <!-- 判定逻辑说明 -->
      <div class="chi-decision-hint">
        <span class="formula-cell" style="font-size:12px;" title="卡方检验判定逻辑">判定逻辑：</span>
        <span style="font-size:12px;color:#606266;">
          若 χ²({{ chiResult.chi2Total.toFixed(3) }}) > 临界值({{ chiResult.criticalValue.toFixed(3) }})，则拒绝"分布符合本福特定律"的原假设 →
          <b :style="{ color: chiResult.significant ? '#f56c6c' : '#67c23a' }">
            {{ chiResult.significant ? '首位数分布异常，建议进一步核查' : '首位数分布正常，未发现异常模式' }}
          </b>
        </span>
      </div>

      <el-alert
        v-if="chiResult.significant"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top: 12px;"
      >
        <template #title>首位数分布显著偏离本福特定律</template>
        <p style="margin:4px 0 0;font-size:12px;color:#606266;">
          可能存在人为编造金额或异常模式。建议：①追溯偏离较大数字对应的分录明细 ②结合C24-5异常筛选结果综合判断 ③获取管理层解释并记录于下方结论区。
        </p>
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

      <!-- 偏离数字详情提示 -->
      <div v-if="deviatingDigits.length > 0" class="deviation-detail">
        <p class="deviation-title">⚡ 偏离较大的首位数字：</p>
        <div v-for="d in deviatingDigits" :key="d.digit" class="deviation-item">
          <el-tag size="small" :type="d.direction === 'high' ? 'danger' : 'warning'" effect="plain">
            数字 {{ d.digit }}
          </el-tag>
          <span class="deviation-desc">
            实际 {{ (d.actual * 100).toFixed(1) }}% vs 理论 {{ (d.expected * 100).toFixed(1) }}%，
            {{ d.direction === 'high' ? '偏高' : '偏低' }} {{ (Math.abs(d.deviation) * 100).toFixed(1) }}%
            <span class="deviation-hint">{{ d.hint }}</span>
          </span>
        </div>
      </div>
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
import { QuestionFilled } from '@element-plus/icons-vue'
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

/** 偏离较大的数字详情（含审计解读） */
interface DeviatingDigit {
  digit: number
  actual: number
  expected: number
  deviation: number
  direction: 'high' | 'low'
  hint: string
}

const DIGIT_HINTS: Record<number, { high: string; low: string }> = {
  1: { high: '', low: '— 首位1偏低可能表明缺少小额真实交易' },
  2: { high: '', low: '' },
  3: { high: '', low: '' },
  4: { high: '— 可能与刚好低于50万审批限额有关', low: '' },
  5: { high: '— 可能存在刚好低于审批限额的金额编造', low: '' },
  6: { high: '— 关注是否有大量相似金额的虚构交易', low: '' },
  7: { high: '— 首位7/8/9偏高是人为编造的典型信号', low: '' },
  8: { high: '— 首位7/8/9偏高是人为编造的典型信号', low: '' },
  9: { high: '— 首位7/8/9偏高是人为编造的典型信号', low: '' },
}

const deviatingDigits = computed<DeviatingDigit[]>(() => {
  if (!props.hasData || props.distribution.length === 0) return []
  return props.distribution
    .filter(d => Math.abs(d.deviation) > BENFORD_DEVIATION_THRESHOLD)
    .map(d => {
      const direction = d.deviation > 0 ? 'high' : 'low'
      const hints = DIGIT_HINTS[d.digit] || { high: '', low: '' }
      return {
        digit: d.digit,
        actual: d.actual,
        expected: d.expected,
        deviation: d.deviation,
        direction,
        hint: hints[direction],
      } as DeviatingDigit
    })
    .sort((a, b) => Math.abs(b.deviation) - Math.abs(a.deviation))
})

function barWidth(ratio: number): string {
  // Max bar width 100% represents 35% (digit 1's expected ~30%)
  return `${Math.min(ratio / 0.35 * 100, 100)}%`
}
</script>

<style scoped>
.c24-benford { font-size: var(--wp-font-size, 13px); }

/* 顶部蓝色渐变引导区 */
.c24-guide-area {
  background: linear-gradient(135deg, #ecf5ff 0%, #f0f9ff 100%);
  border: 1px solid #d9ecff;
  border-radius: 8px;
  padding: 14px 18px;
  margin-bottom: 16px;
}
.guide-steps {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 24px;
}
.guide-step {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.guide-num {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  line-height: 22px;
  text-align: center;
  background: #409eff;
  color: #fff;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 600;
}
.guide-text {
  font-size: var(--wp-font-size, 13px);
  color: #303133;
  line-height: 1.5;
}

/* 方法论上下文 */
.methodology-context { display: flex; gap: 10px; align-items: flex-start; padding: 12px 14px; margin-bottom: 16px; background: #fffbf0; border-radius: 4px; border-left: 3px solid #e6a23c; }
.methodology-bar { display: none; }
.methodology-content p { margin: 0 0 2px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.methodology-content b { color: #303133; }

/* 编制提示 */
.c24-compile-hint {
  margin-bottom: 16px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  overflow: hidden;
}
.c24-compile-hint summary {
  padding: 10px 14px;
  background: #fafafa;
  cursor: pointer;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #303133;
  user-select: none;
}
.c24-compile-hint summary:hover { background: #f5f7fa; }
.hint-body {
  padding: 12px 14px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.7;
}
.hint-body p { margin: 0 0 6px; }
.hint-body ul { margin: 4px 0 8px 20px; padding: 0; }
.hint-body li { margin-bottom: 4px; }

/* Sections */
.c24-section { margin-bottom: 20px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; gap: 8px; }
.section-title { font-weight: 600; font-size: 14px; color: #303133; }
.c24-table { font-size: var(--wp-font-size, 13px); }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; color: #409eff; }
.text-danger { color: #f56c6c !important; }

/* 卡方判定提示 */
.chi-decision-hint {
  margin-top: 10px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  border-left: 3px solid #409eff;
}

/* 偏离数字详情 */
.deviation-detail {
  margin-top: 12px;
  padding: 10px 14px;
  background: #fef0f0;
  border-radius: 6px;
  border: 1px solid #fde2e2;
}
.deviation-title {
  margin: 0 0 8px;
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
  color: #f56c6c;
}
.deviation-item {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.deviation-desc {
  font-size: 12px;
  color: #606266;
}
.deviation-hint {
  color: #e6a23c;
  font-weight: 500;
}

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
