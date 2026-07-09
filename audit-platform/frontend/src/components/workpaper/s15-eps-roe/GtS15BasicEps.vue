<template>
  <div class="s15-basic-eps">
    <!-- 本年/上年对比标题 -->
    <div class="period-comparison-header">
      <el-tag type="primary" size="small">本年</el-tag>
      <el-tag type="info" size="small">上年</el-tag>
      <span class="comparison-hint">S15-2 基本每股收益计算表 — 本年/上年对比展示</span>
      <span class="data-source-hint">取数来源：</span>
      <GtIndexChip value="审定报表" />
      <GtIndexChip value="B22" />
    </div>

    <div class="dual-period-container">
      <!-- ─── 本年数据 ─── -->
      <el-card shadow="never" class="period-card">
        <template #header>
          <div class="section-header">
            <span>本年（当期）</span>
          </div>
        </template>

        <el-form
          :model="currentYear"
          label-width="200px"
          size="small"
          :disabled="isReadonly"
          class="eps-form"
        >
          <el-form-item label="归母净利润 (a1)">
            <el-input-number
              v-model="currentYear.npAttrParent"
              :controls="false"
              :precision="2"
              placeholder="0.00"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="扣非归母净利润 (a2)">
            <el-input-number
              v-model="currentYear.npAttrParentEx"
              :controls="false"
              :precision="2"
              placeholder="0.00"
              class="input-amount"
            />
          </el-form-item>
          <el-divider content-position="left">股本结构</el-divider>
          <el-form-item label="期初股份总数 (b0)">
            <el-input-number
              v-model="currentYear.shareOpening"
              :controls="false"
              :precision="0"
              placeholder="0"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="转增/股票股利增加 (b1)">
            <el-input-number
              v-model="currentYear.shareCapitalized"
              :controls="false"
              :precision="0"
              placeholder="0"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="发行新股 - 股份数 (c1)">
            <el-input-number
              v-model="currentYear.newIssueCount"
              :controls="false"
              :precision="0"
              placeholder="0"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="发行新股 - 月份数 (c2)">
            <el-input-number
              v-model="currentYear.newIssueMonths"
              :controls="false"
              :min="0"
              :max="12"
              placeholder="0"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="债转股 - 股份数 (d1)">
            <el-input-number
              v-model="currentYear.debtToEquityCount"
              :controls="false"
              :precision="0"
              placeholder="0"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="债转股 - 月份数 (d2)">
            <el-input-number
              v-model="currentYear.debtToEquityMonths"
              :controls="false"
              :min="0"
              :max="12"
              placeholder="0"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="回购股份数 (e1)">
            <el-input-number
              v-model="currentYear.repurchaseCount"
              :controls="false"
              :precision="0"
              placeholder="0"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="回购 - 月份数 (e2)">
            <el-input-number
              v-model="currentYear.repurchaseMonths"
              :controls="false"
              :min="0"
              :max="12"
              placeholder="0"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="并股数 (b4)">
            <el-input-number
              v-model="currentYear.merged"
              :controls="false"
              :precision="0"
              placeholder="0"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="报告期月份数 (m0)">
            <el-input-number
              v-model="currentYear.periodMonths"
              :controls="false"
              :min="1"
              :max="12"
              placeholder="12"
              class="input-amount"
            />
          </el-form-item>

          <el-divider content-position="left">计算结果（公式单元格，不可手工覆盖）</el-divider>
          <el-form-item label="加权平均股数">
            <span class="formula-cell" title="b = b0 + b1 + (c1×c2/m0 + d1×d2/m0) - (e1×e2/m0) - b4">
              {{ fmtShares(currentYearResult.weightedAvgShares) }}
            </span>
          </el-form-item>
          <el-form-item label="基本每股收益 (元/股)">
            <span
              class="formula-cell"
              :class="{ unable: currentYearResult.basicEps.unable }"
              title="eps = 归母净利润 ÷ 加权平均股数"
            >
              {{ currentYearResult.basicEps.unable ? '不可计算' : fmtEps(currentYearResult.basicEps.eps) }}
            </span>
          </el-form-item>
          <el-form-item label="扣非基本每股收益 (元/股)">
            <span
              class="formula-cell"
              :class="{ unable: currentYearResult.basicEps.unable }"
              title="epsEx = 扣非归母净利润 ÷ 加权平均股数"
            >
              {{ currentYearResult.basicEps.unable ? '不可计算' : fmtEps(currentYearResult.basicEps.epsEx) }}
            </span>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- ─── 上年数据 ─── -->
      <el-card shadow="never" class="period-card">
        <template #header>
          <div class="section-header">
            <span>上年（比较期）</span>
          </div>
        </template>

        <el-form
          :model="priorYear"
          label-width="200px"
          size="small"
          :disabled="isReadonly"
          class="eps-form"
        >
          <el-form-item label="归母净利润 (a1)">
            <el-input-number
              v-model="priorYear.npAttrParent"
              :controls="false"
              :precision="2"
              placeholder="0.00"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="扣非归母净利润 (a2)">
            <el-input-number
              v-model="priorYear.npAttrParentEx"
              :controls="false"
              :precision="2"
              placeholder="0.00"
              class="input-amount"
            />
          </el-form-item>
          <el-divider content-position="left">股本结构</el-divider>
          <el-form-item label="期初股份总数 (b0)">
            <el-input-number
              v-model="priorYear.shareOpening"
              :controls="false"
              :precision="0"
              placeholder="0"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="转增/股票股利增加 (b1)">
            <el-input-number
              v-model="priorYear.shareCapitalized"
              :controls="false"
              :precision="0"
              placeholder="0"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="发行新股 - 股份数 (c1)">
            <el-input-number
              v-model="priorYear.newIssueCount"
              :controls="false"
              :precision="0"
              placeholder="0"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="发行新股 - 月份数 (c2)">
            <el-input-number
              v-model="priorYear.newIssueMonths"
              :controls="false"
              :min="0"
              :max="12"
              placeholder="0"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="债转股 - 股份数 (d1)">
            <el-input-number
              v-model="priorYear.debtToEquityCount"
              :controls="false"
              :precision="0"
              placeholder="0"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="债转股 - 月份数 (d2)">
            <el-input-number
              v-model="priorYear.debtToEquityMonths"
              :controls="false"
              :min="0"
              :max="12"
              placeholder="0"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="回购股份数 (e1)">
            <el-input-number
              v-model="priorYear.repurchaseCount"
              :controls="false"
              :precision="0"
              placeholder="0"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="回购 - 月份数 (e2)">
            <el-input-number
              v-model="priorYear.repurchaseMonths"
              :controls="false"
              :min="0"
              :max="12"
              placeholder="0"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="并股数 (b4)">
            <el-input-number
              v-model="priorYear.merged"
              :controls="false"
              :precision="0"
              placeholder="0"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="报告期月份数 (m0)">
            <el-input-number
              v-model="priorYear.periodMonths"
              :controls="false"
              :min="1"
              :max="12"
              placeholder="12"
              class="input-amount"
            />
          </el-form-item>

          <el-divider content-position="left">计算结果（公式单元格，不可手工覆盖）</el-divider>
          <el-form-item label="加权平均股数">
            <span class="formula-cell" title="b = b0 + b1 + (c1×c2/m0 + d1×d2/m0) - (e1×e2/m0) - b4">
              {{ fmtShares(priorYearResult.weightedAvgShares) }}
            </span>
          </el-form-item>
          <el-form-item label="基本每股收益 (元/股)">
            <span
              class="formula-cell"
              :class="{ unable: priorYearResult.basicEps.unable }"
              title="eps = 归母净利润 ÷ 加权平均股数"
            >
              {{ priorYearResult.basicEps.unable ? '不可计算' : fmtEps(priorYearResult.basicEps.eps) }}
            </span>
          </el-form-item>
          <el-form-item label="扣非基本每股收益 (元/股)">
            <span
              class="formula-cell"
              :class="{ unable: priorYearResult.basicEps.unable }"
              title="epsEx = 扣非归母净利润 ÷ 加权平均股数"
            >
              {{ priorYearResult.basicEps.unable ? '不可计算' : fmtEps(priorYearResult.basicEps.epsEx) }}
            </span>
          </el-form-item>
        </el-form>
      </el-card>
    </div>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>基本每股收益 = 归母净利润 ÷ 发行在外普通股加权平均数。</p>
      <p>加权平均股数 b = b0 + b1 + (c1×c2/m0 + d1×d2/m0) - (e1×e2/m0) - b4。</p>
      <p>公式单元格（虚线下划线）自动计算，不可手工覆盖。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * GtS15BasicEps.vue — S15-2 基本每股收益计算表
 *
 * 功能：
 * - 本年/上年双期并列展示（Req 3.4）
 * - 使用 calcWeightedAvgShares + calcBasicEps 纯函数计算
 * - 公式单元格只读不可手工覆盖（Req 2.5）
 * - 输入变更实时重算所有派生单元格
 *
 * Requirements: 2.1, 2.2, 2.3, 2.5, 3.4
 */
import { reactive, computed, defineAsyncComponent } from 'vue'
import {
  calcWeightedAvgShares,
  calcBasicEps,
  type EpsInput,
} from '../composables/useS15FormulaEngine'
import { fmtAmount } from '@/utils/formatters'

const GtIndexChip = defineAsyncComponent(() => import('../GtIndexChip.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

// ─── 本年输入 ────────────────────────────────────────────────

const currentYear = reactive({
  npAttrParent: 0,
  npAttrParentEx: 0,
  shareOpening: 0,
  shareCapitalized: 0,
  newIssueCount: 0,
  newIssueMonths: 0,
  debtToEquityCount: 0,
  debtToEquityMonths: 0,
  repurchaseCount: 0,
  repurchaseMonths: 0,
  merged: 0,
  periodMonths: 12,
})

// ─── 上年输入 ────────────────────────────────────────────────

const priorYear = reactive({
  npAttrParent: 0,
  npAttrParentEx: 0,
  shareOpening: 0,
  shareCapitalized: 0,
  newIssueCount: 0,
  newIssueMonths: 0,
  debtToEquityCount: 0,
  debtToEquityMonths: 0,
  repurchaseCount: 0,
  repurchaseMonths: 0,
  merged: 0,
  periodMonths: 12,
})

// ─── 构建 EpsInput ───────────────────────────────────────────

function toEpsInput(data: typeof currentYear): EpsInput {
  return {
    npAttrParent: data.npAttrParent,
    npAttrParentEx: data.npAttrParentEx,
    shareOpening: data.shareOpening,
    shareCapitalized: data.shareCapitalized,
    newIssue: { count: data.newIssueCount, monthsToEnd: data.newIssueMonths },
    debtToEquity: { count: data.debtToEquityCount, monthsToEnd: data.debtToEquityMonths },
    repurchase: { count: data.repurchaseCount, monthsToEnd: data.repurchaseMonths },
    merged: data.merged,
    periodMonths: data.periodMonths,
  }
}

// ─── 实时计算结果（公式单元格不可手工覆盖） ──────────────────

const currentYearResult = computed(() => {
  const input = toEpsInput(currentYear)
  return {
    weightedAvgShares: calcWeightedAvgShares(input),
    basicEps: calcBasicEps(input),
  }
})

const priorYearResult = computed(() => {
  const input = toEpsInput(priorYear)
  return {
    weightedAvgShares: calcWeightedAvgShares(input),
    basicEps: calcBasicEps(input),
  }
})

// ─── 格式化 ──────────────────────────────────────────────────

function fmtShares(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}

function fmtEps(val: number): string {
  return val.toFixed(4)
}
</script>

<style scoped>
.s15-basic-eps {
  padding: 12px;
}
.period-comparison-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.comparison-hint {
  font-size: 13px;
  color: #606266;
}
.data-source-hint {
  font-size: 12px;
  color: #909399;
  margin-left: auto;
  white-space: nowrap;
}
.dual-period-container {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.period-card {
  font-size: 13px;
}
.section-header {
  font-weight: 600;
}
.input-amount {
  width: 180px;
}
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  font-weight: 600;
  color: #303133;
  padding: 2px 4px;
}
.formula-cell.unable {
  color: #f56c6c;
  font-style: italic;
}
.eps-form :deep(.el-form-item) {
  margin-bottom: 12px;
}
.edit-hints {
  margin-top: 16px;
  font-size: 12px;
  color: #909399;
}
.edit-hints summary {
  cursor: pointer;
  user-select: none;
}
</style>
