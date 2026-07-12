<template>
  <div class="h1-tab-recoverable">
    <div class="methodology-context">
      <p>DCF折现现金流模型：预测资产组未来N年自由现金流，按WACC折现求和得到使用价值(VIU)。加入永续增长率计算终值。敏感性分析验证结论稳健性。</p>
    </div>

    <!-- DCF模型参数 -->
    <el-card shadow="never" class="dcf-card">
      <template #header>
        <div class="section-title">
          <span>一、DCF模型假设</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('impairment-conclusion')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-15-dcf')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-form :model="dcfParams" label-width="120px" size="small">
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="折现率(WACC)%">
              <el-input-number v-model="dcfParams.discountRate" :min="1" :max="30" :controls="false" :disabled="isReadonly" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="预测期(年)">
              <el-input-number v-model="dcfParams.forecastPeriod" :min="3" :max="10" :disabled="isReadonly" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="永续增长率%">
              <el-input-number v-model="dcfParams.perpetualGrowthRate" :min="0" :max="5" :controls="false" :disabled="isReadonly" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <!-- 现金流预测表 -->
    <el-card shadow="never" class="cf-card">
      <template #header><span>二、未来现金流预测</span></template>
      <el-table :data="cashFlowTable" border stripe size="small">
        <el-table-column prop="year" label="年份" width="80" align="center" />
        <el-table-column prop="revenue" label="收入预测" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.revenue" :controls="false" size="small" />
            <span v-else class="amount-cell">{{ fmtAmt(row.revenue) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="cost" label="成本费用" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.cost" :controls="false" size="small" />
            <span v-else class="amount-cell">{{ fmtAmt(row.cost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="自由现金流" width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="FCF=收入-成本">{{ fmtAmt(row.fcf) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="折现系数" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="1/(1+r)^n">{{ row.discountFactor?.toFixed(4) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="现值" width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="FCF×折现系数">{{ fmtAmt(row.presentValue) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- DCF结果汇总 -->
      <div class="dcf-result">
        <el-descriptions :column="4" border size="small">
          <el-descriptions-item label="预测期现值合计"><span class="formula-cell">{{ fmtAmt(forecastPvTotal) }}</span></el-descriptions-item>
          <el-descriptions-item label="终值现值"><span class="formula-cell">{{ fmtAmt(terminalPv) }}</span></el-descriptions-item>
          <el-descriptions-item label="DCF总值"><span class="formula-cell"><b>{{ fmtAmt(dcfTotal) }}</b></span></el-descriptions-item>
          <el-descriptions-item label="可收回金额"><span class="formula-cell"><b>{{ fmtAmt(recoverableAmount) }}</b></span></el-descriptions-item>
        </el-descriptions>
      </div>
    </el-card>

    <!-- 敏感性分析矩阵 -->
    <el-card shadow="never" class="sensitivity-card">
      <template #header><span>三、敏感性分析矩阵</span></template>
      <el-table :data="sensitivityMatrix" border size="small" class="matrix-table">
        <el-table-column prop="label" label="折现率↓ / 增长率→" width="140" fixed />
        <el-table-column v-for="g in growthRates" :key="g" :label="`${g}%`" width="110" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': (row[`g_${g}`] ?? 0) < accountBookValue }]">
              {{ fmtAmt(row[`g_${g}`]) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
      <div class="matrix-hint">红色 = 可收回金额 < 账面价值（存在减值）</div>
    </el-card>

    <!-- 结论 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>DCF测试结论</span></template>
      <el-input v-model="dcfConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="基于DCF模型和敏感性分析的减值测试结论..." />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>折现率取WACC或行业平均要求回报率</li>
        <li>预测期通常3~5年，永续增长率≤GDP增速</li>
        <li>敏感性矩阵：折现率±1~2% × 增长率±0.5~1% 交叉</li>
        <li>如所有情景均>账面→不需减值；存在<账面→需计提</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, inject, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH1Impairment } from '../../composables/useH1Impairment'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const dcfConclusion = ref('')
const accountBookValue = ref(0)

const state = useH1Impairment(toRef(props, 'wpId'), toRef(props, 'projectId'), allResponsesRef as any)

const dcfParams = reactive({ discountRate: 10, forecastPeriod: 5, perpetualGrowthRate: 2 })

// Simplified cash flow table
const cashFlowTable = computed(() => {
  const rows: any[] = []
  for (let i = 1; i <= dcfParams.forecastPeriod; i++) {
    const revenue = 0; const cost = 0; const fcf = revenue - cost
    const df = 1 / Math.pow(1 + dcfParams.discountRate / 100, i)
    rows.push({ year: `Year ${i}`, revenue, cost, fcf, discountFactor: df, presentValue: fcf * df })
  }
  return rows
})

const forecastPvTotal = computed(() => cashFlowTable.value.reduce((s, r) => s + r.presentValue, 0))
const terminalPv = computed(() => 0) // Would be calculated from terminal value formula
const dcfTotal = computed(() => forecastPvTotal.value + terminalPv.value)
const recoverableAmount = computed(() => dcfTotal.value)

// Sensitivity matrix
const growthRates = [0, 1, 2, 3, 4]
const sensitivityMatrix = computed(() => {
  const rates = [dcfParams.discountRate - 2, dcfParams.discountRate - 1, dcfParams.discountRate, dcfParams.discountRate + 1, dcfParams.discountRate + 2]
  return rates.map(r => {
    const row: any = { label: `${r}%` }
    growthRates.forEach(g => { row[`g_${g}`] = 0 }) // simplified
    return row
  })
})

function handleAiGenerate(section: string) { console.log('AI:', section) }
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-recoverable { padding: 16px; font-size: var(--wp-font-size, 13px); }
.methodology-context { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; }
.dcf-card { margin-bottom: 16px; }
.cf-card { margin-bottom: 16px; }
.sensitivity-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.dcf-result { margin-top: 16px; }
.matrix-table { font-size: 12px; }
.matrix-hint { font-size: 11px; color: var(--el-text-color-secondary); margin-top: 8px; }
.note-card { margin-bottom: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
