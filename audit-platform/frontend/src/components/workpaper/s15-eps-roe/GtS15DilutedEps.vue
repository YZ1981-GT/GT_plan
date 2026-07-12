<template>
  <div class="s15-diluted-eps">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>审计目标</template>
      <div class="audit-objective-text">
        复核稀释每股收益计算，验证稀释性潜在普通股的识别、分子（利息与转换费用的税后调整）与分母（加权稀释股数）调整是否符合《企业会计准则第34号——每股收益》，确认稀释后金额不高于基本每股收益。
      </div>
    </el-alert>

    <!-- 本年/上年对比标题 -->
    <div class="period-comparison-header">
      <el-tag type="primary" size="small">本年</el-tag>
      <el-tag type="info" size="small">上年</el-tag>
      <span class="comparison-hint">S15-3 稀释每股收益计算表 — 本年/上年对比展示</span>
    </div>

    <div class="dual-period-container">
      <!-- ─── 本年 ─── -->
      <el-card shadow="never" class="period-card">
        <template #header>
          <span>本年（当期）</span>
        </template>

        <el-form
          :model="currentYear"
          label-width="240px"
          size="small"
          :disabled="isReadonly"
          class="eps-form"
        >
          <el-form-item label="归母净利润 P">
            <el-input-number
              v-model="currentYear.npAttrParent"
              :controls="false"
              :precision="2"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="基本加权平均股数 b">
            <el-input-number
              v-model="currentYear.weightedAvgShares"
              :controls="false"
              :precision="0"
              class="input-amount"
            />
            <GtIndexChip value="S15-2" style="margin-left: 8px" />
          </el-form-item>
          <el-divider content-position="left">稀释性潜在普通股调整</el-divider>
          <el-form-item label="已确认为费用的稀释性利息">
            <el-input-number
              v-model="currentYear.dilutionInterest"
              :controls="false"
              :precision="2"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="转换费用">
            <el-input-number
              v-model="currentYear.conversionCost"
              :controls="false"
              :precision="2"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="所得税率">
            <el-input-number
              v-model="currentYear.taxRate"
              :controls="false"
              :precision="4"
              :step="0.01"
              :min="0"
              :max="1"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="稀释性潜在普通股数">
            <el-input-number
              v-model="currentYear.dilutionShares"
              :controls="false"
              :precision="0"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="稀释性潜在普通股存续月份">
            <el-input-number
              v-model="currentYear.dilutionMonths"
              :controls="false"
              :min="0"
              :max="12"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="报告期月份数 m0">
            <el-input-number
              v-model="currentYear.periodMonths"
              :controls="false"
              :min="1"
              :max="12"
              class="input-amount"
            />
          </el-form-item>

          <el-divider content-position="left">计算结果（公式单元格，不可手工覆盖）</el-divider>
          <el-form-item label="稀释每股收益 (元/股)">
            <span
              class="formula-cell"
              :class="{ unable: currentYearResult.unable }"
              title="稀释EPS = (P + (利息-转换费用)×(1-税率)) ÷ (b + 稀释股数×月份/m0)"
            >
              {{ currentYearResult.unable ? '不可计算' : fmtEps(currentYearResult.dilutedEps) }}
            </span>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- ─── 上年 ─── -->
      <el-card shadow="never" class="period-card">
        <template #header>
          <span>上年（比较期）</span>
        </template>

        <el-form
          :model="priorYear"
          label-width="240px"
          size="small"
          :disabled="isReadonly"
          class="eps-form"
        >
          <el-form-item label="归母净利润 P">
            <el-input-number
              v-model="priorYear.npAttrParent"
              :controls="false"
              :precision="2"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="基本加权平均股数 b">
            <el-input-number
              v-model="priorYear.weightedAvgShares"
              :controls="false"
              :precision="0"
              class="input-amount"
            />
          </el-form-item>
          <el-divider content-position="left">稀释性潜在普通股调整</el-divider>
          <el-form-item label="已确认为费用的稀释性利息">
            <el-input-number
              v-model="priorYear.dilutionInterest"
              :controls="false"
              :precision="2"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="转换费用">
            <el-input-number
              v-model="priorYear.conversionCost"
              :controls="false"
              :precision="2"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="所得税率">
            <el-input-number
              v-model="priorYear.taxRate"
              :controls="false"
              :precision="4"
              :step="0.01"
              :min="0"
              :max="1"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="稀释性潜在普通股数">
            <el-input-number
              v-model="priorYear.dilutionShares"
              :controls="false"
              :precision="0"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="稀释性潜在普通股存续月份">
            <el-input-number
              v-model="priorYear.dilutionMonths"
              :controls="false"
              :min="0"
              :max="12"
              class="input-amount"
            />
          </el-form-item>
          <el-form-item label="报告期月份数 m0">
            <el-input-number
              v-model="priorYear.periodMonths"
              :controls="false"
              :min="1"
              :max="12"
              class="input-amount"
            />
          </el-form-item>

          <el-divider content-position="left">计算结果（公式单元格，不可手工覆盖）</el-divider>
          <el-form-item label="稀释每股收益 (元/股)">
            <span
              class="formula-cell"
              :class="{ unable: priorYearResult.unable }"
              title="稀释EPS = (P + (利息-转换费用)×(1-税率)) ÷ (b + 稀释股数×月份/m0)"
            >
              {{ priorYearResult.unable ? '不可计算' : fmtEps(priorYearResult.dilutedEps) }}
            </span>
          </el-form-item>
        </el-form>
      </el-card>
    </div>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>稀释每股收益 = (归母净利润 + (稀释性利息 - 转换费用) × (1 - 所得税率)) ÷ (加权平均股数 + 稀释性潜在普通股加权数)。</p>
      <p>若无稀释性潜在普通股，稀释每股收益 = 基本每股收益。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * GtS15DilutedEps.vue — S15-3 稀释每股收益计算表
 *
 * 功能：
 * - 本年/上年双期并列展示（Req 3.4）
 * - 使用 calcDilutedEps 纯函数计算
 * - 公式单元格只读不可手工覆盖（Req 2.5）
 * - 引用 S15-2 的加权平均股数（GtIndexChip）
 *
 * Requirements: 2.5, 3.3, 3.4
 */
import { reactive, computed, watch, onMounted, nextTick, defineAsyncComponent } from 'vue'
import { calcDilutedEps, type DilutedEpsInput } from '../composables/useS15FormulaEngine'
import { useSExpertPersist, parseResponseValue } from '../composables/useSExpertPersist'

const GtIndexChip = defineAsyncComponent(() => import('../GtIndexChip.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  /** 主入口透传的持久化快照（已解包纯 Map） */
  allResponses?: Map<string, any>
}>()

// ─── 本年输入 ────────────────────────────────────────────────

const currentYear = reactive({
  npAttrParent: 0,
  weightedAvgShares: 0,
  dilutionInterest: 0,
  conversionCost: 0,
  taxRate: 0.25,
  dilutionShares: 0,
  dilutionMonths: 0,
  periodMonths: 12,
})

// ─── 上年输入 ────────────────────────────────────────────────

const priorYear = reactive({
  npAttrParent: 0,
  weightedAvgShares: 0,
  dilutionInterest: 0,
  conversionCost: 0,
  taxRate: 0.25,
  dilutionShares: 0,
  dilutionMonths: 0,
  periodMonths: 12,
})

// ─── 构建输入 ────────────────────────────────────────────────

function toDilutedInput(data: typeof currentYear): DilutedEpsInput {
  return {
    npAttrParent: data.npAttrParent,
    weightedAvgShares: data.weightedAvgShares,
    dilutionInterest: data.dilutionInterest,
    conversionCost: data.conversionCost,
    taxRate: data.taxRate,
    dilutionShares: data.dilutionShares,
    dilutionMonths: data.dilutionMonths,
    periodMonths: data.periodMonths,
  }
}

// ─── 实时计算（公式单元格不可覆盖） ─────────────────────────

const currentYearResult = computed(() => calcDilutedEps(toDilutedInput(currentYear)))
const priorYearResult = computed(() => calcDilutedEps(toDilutedInput(priorYear)))

// ─── 格式化 ──────────────────────────────────────────────────

function fmtEps(val: number): string {
  return val.toFixed(4)
}

// ─── 持久化接线（load seed + save；reactive 对象用 watch，hydrating 防回写） ───

const CY_ID = 'S15-3-current'
const PY_ID = 'S15-3-prior'
const { save } = useSExpertPersist(() => props.allResponses)

let hydrating = false

onMounted(async () => {
  hydrating = true
  const cy = parseResponseValue(props.allResponses, CY_ID)
  if (cy && typeof cy === 'object') Object.assign(currentYear, cy)
  const py = parseResponseValue(props.allResponses, PY_ID)
  if (py && typeof py === 'object') Object.assign(priorYear, py)
  await nextTick()
  hydrating = false
})

watch(currentYear, () => { if (!hydrating) save(CY_ID, { ...currentYear }) }, { deep: true })
watch(priorYear, () => { if (!hydrating) save(PY_ID, { ...priorYear }) }, { deep: true })
</script>

<style scoped>
.s15-diluted-eps {
  padding: 12px;
}
.audit-objective {
  margin-bottom: 12px;
}
.audit-objective-text {
  font-size: var(--wp-font-size, 13px);
  line-height: 1.6;
}
.period-comparison-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.comparison-hint {
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}
.dual-period-container {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.period-card {
  font-size: var(--wp-font-size, 13px);
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
