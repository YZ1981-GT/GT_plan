<template>
  <div class="i3-tab-recoverable-test">
    <!-- 蓝色渐变引导区（DCF操作步骤）-->
    <div class="guidance-block">
      <div class="guidance-grid">
        <div class="guidance-step">
          <span class="step-num">①</span>
          <span>选择资产组(CGU)并输入5年收入/成本预测</span>
        </div>
        <div class="guidance-step">
          <span class="step-num">②</span>
          <span>设定WACC参数（权益成本/债务成本/资本结构）</span>
        </div>
        <div class="guidance-step">
          <span class="step-num">③</span>
          <span>设定永续增长率g，系统自动计算DCF现值+终值</span>
        </div>
        <div class="guidance-step">
          <span class="step-num">④</span>
          <span>查看敏感性矩阵，确认可收回金额=MAX(FV-处置费, DCF)</span>
        </div>
      </div>
    </div>

    <!-- 琥珀色方法论 block -->
    <div class="methodology-block">
      <p><strong>CAS8 可收回金额确定：</strong>可收回金额应当根据资产的公允价值减去处置费用后的净额与资产预计未来现金流量的现值（使用价值）两者之间较高者确定。预计未来现金流量的现值应当选择恰当的折现率（WACC）对预测期自由现金流进行折现。折现率应当反映货币时间价值和资产特定风险的当前市场评价。</p>
    </div>

    <!-- CGU选择器 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">I3-7 可收回金额测试（DCF核心）</span>
          <div class="section-header-actions">
            <el-select
              v-model="activeCguIndex"
              size="small"
              placeholder="选择资产组(CGU)"
              style="width: 200px"
            >
              <el-option
                v-for="(cgu, idx) in cguList"
                :key="idx"
                :label="cgu.name"
                :value="idx"
              />
            </el-select>
            <el-dropdown v-if="!isReadonly" trigger="click" @command="handleExportImport">
              <el-button size="small">导入导出 ▾</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
                  <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
                  <el-dropdown-item command="import-data" divided>导入数据</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button size="small" type="primary" link @click="handleAiWaccSuggestion">
              <el-icon><MagicStick /></el-icon> AI建议
            </el-button>
            <el-button size="small" circle @click="openReview('I3-7')">💬</el-button>
          </div>
        </div>
      </template>

      <!-- DCF输入区域：收入5年+成本5年→自由现金流 -->
      <div class="dcf-input-section" v-if="activeCgu">
        <h4 class="sub-section-title">自由现金流预测（5年）</h4>
        <div class="dcf-table-wrapper" style="max-height: 500px; overflow-y: auto;">
          <el-table
            :data="cashFlowTableData"
            border
            stripe
            size="small"
            class="dcf-core-table"
            row-key="rowKey"
          >
            <el-table-column prop="label" label="项目" min-width="140" fixed />
            <el-table-column
              v-for="year in forecastYears"
              :key="year"
              :label="`第${year}年`"
              min-width="120"
              align="right"
            >
              <template #default="{ row }">
                <template v-if="row.editable">
                  <el-input-number
                    v-if="!isReadonly"
                    :model-value="row.values[year - 1]"
                    :controls="false"
                    size="small"
                    class="amt-input"
                    @change="handleCashFlowInput(row.field, year - 1, $event)"
                  />
                  <span v-else class="amt-cell">{{ fmtAmt(row.values[year - 1]) }}</span>
                </template>
                <template v-else>
                  <span class="formula-cell" :title="row.formula">
                    {{ fmtAmt(row.values[year - 1]) }}
                  </span>
                </template>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- WACC参数区域 -->
        <h4 class="sub-section-title">
          WACC参数
          <el-button size="small" type="primary" link @click="handleAiWaccSuggestion" style="margin-left:8px">
            <el-icon><MagicStick /></el-icon> AI建议WACC
          </el-button>
        </h4>
        <div class="wacc-params-grid">
          <div class="param-item">
            <label>权益占比 (E/V)</label>
            <el-input-number
              v-if="!isReadonly"
              v-model="waccParams.equityRatio"
              :step="0.05" :precision="4" :min="0" :max="1"
              size="small" :controls="true"
              @change="recalcAll"
            />
            <span v-else class="param-value">{{ pct(waccParams.equityRatio) }}</span>
          </div>
          <div class="param-item">
            <label>负债占比 (D/V)</label>
            <el-input-number
              v-if="!isReadonly"
              v-model="waccParams.debtRatio"
              :step="0.05" :precision="4" :min="0" :max="1"
              size="small" :controls="true"
              @change="recalcAll"
            />
            <span v-else class="param-value">{{ pct(waccParams.debtRatio) }}</span>
          </div>
          <div class="param-item">
            <label>权益成本 (Re)</label>
            <el-input-number
              v-if="!isReadonly"
              v-model="waccParams.costOfEquity"
              :step="0.005" :precision="4" :min="0" :max="1"
              size="small" :controls="true"
              @change="recalcAll"
            />
            <span v-else class="param-value">{{ pct(waccParams.costOfEquity) }}</span>
          </div>
          <div class="param-item">
            <label>债务成本 (Rd)</label>
            <el-input-number
              v-if="!isReadonly"
              v-model="waccParams.costOfDebt"
              :step="0.005" :precision="4" :min="0" :max="1"
              size="small" :controls="true"
              @change="recalcAll"
            />
            <span v-else class="param-value">{{ pct(waccParams.costOfDebt) }}</span>
          </div>
          <div class="param-item">
            <label>所得税税率 (T)</label>
            <el-input-number
              v-if="!isReadonly"
              v-model="waccParams.taxRate"
              :step="0.05" :precision="4" :min="0" :max="1"
              size="small" :controls="true"
              @change="recalcAll"
            />
            <span v-else class="param-value">{{ pct(waccParams.taxRate) }}</span>
          </div>
          <div class="param-item">
            <label>永续增长率 (g)</label>
            <el-input-number
              v-if="!isReadonly"
              v-model="waccParams.growthRate"
              :step="0.005" :precision="4" :min="-0.1" :max="0.5"
              size="small" :controls="true"
              @change="recalcAll"
            />
            <span v-else class="param-value">{{ pct(waccParams.growthRate) }}</span>
          </div>
        </div>

        <!-- WACC计算结果（公式列） -->
        <div class="wacc-result">
          <span class="formula-header" title="WACC = E/V × Re + D/V × Rd × (1-T)">
            WACC =
          </span>
          <strong class="wacc-value">{{ pct(computedWacc) }}</strong>
          <el-tag v-if="computedWacc <= waccParams.growthRate" type="danger" size="small">
            ⚠ WACC ≤ 增长率，终值无法计算
          </el-tag>
        </div>

        <!-- 结果仪表板：PV + TV + Total DCF -->
        <h4 class="sub-section-title">DCF计算结果</h4>
        <div class="result-dashboard">
          <div class="result-card">
            <div class="result-label formula-header" title="= Σ(FCF_i / (1+WACC)^(i+1))">预测期现值(PV)</div>
            <div class="result-value">{{ fmtAmt(dcfResult.presentValue) }}</div>
          </div>
          <div class="result-card">
            <div class="result-label formula-header" title="= FCF_n×(1+g)/(WACC-g) / (1+WACC)^n">终值现值(TV)</div>
            <div class="result-value">{{ fmtAmt(dcfResult.discountedTerminalValue) }}</div>
          </div>
          <div class="result-card highlight-card">
            <div class="result-label formula-header" title="= PV + TV现值">使用价值(DCF合计)</div>
            <div class="result-value primary-value">{{ fmtAmt(dcfResult.totalDcf) }}</div>
          </div>
        </div>

        <!-- 公允价值减处置费用输入 -->
        <h4 class="sub-section-title">公允价值减处置费用</h4>
        <div class="fv-disposal-section">
          <div class="param-item" style="max-width: 300px">
            <label>公允价值 - 处置费用</label>
            <el-input-number
              v-if="!isReadonly"
              v-model="fairValueLessDisposal"
              :controls="false"
              size="small"
              class="amt-input"
              @change="recalcAll"
            />
            <span v-else class="param-value amt-cell">{{ fmtAmt(fairValueLessDisposal) }}</span>
          </div>
        </div>

        <!-- 最终可收回金额（高亮） -->
        <div class="final-recoverable">
          <span class="final-label">可收回金额 = MAX(公允-处置费, DCF使用价值)</span>
          <span class="final-value">{{ fmtAmt(finalRecoverableAmount) }}</span>
          <el-tag
            :type="finalRecoverableAmount === dcfResult.totalDcf ? 'primary' : 'success'"
            size="small"
          >
            {{ finalRecoverableAmount === dcfResult.totalDcf ? '取使用价值(DCF)' : '取公允-处置费' }}
          </el-tag>
        </div>

        <!-- 敏感性分析矩阵 3×3: WACC±1% / growth±0.5% -->
        <h4 class="sub-section-title">
          敏感性分析（WACC ± 1% / 增长率 ± 0.5%）
          <el-button size="small" type="primary" link @click="handleAiGrowthSuggestion" style="margin-left:8px">
            <el-icon><MagicStick /></el-icon> AI建议增长率
          </el-button>
        </h4>
        <div class="sensitivity-matrix-wrapper">
          <table class="sensitivity-matrix">
            <thead>
              <tr>
                <th class="matrix-corner">WACC \ g</th>
                <th v-for="gDelta in growthDeltas" :key="gDelta">
                  g {{ gDelta >= 0 ? '+' : '' }}{{ (gDelta * 100).toFixed(1) }}%
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="wDelta in waccDeltas" :key="wDelta">
                <td class="matrix-row-header">
                  WACC {{ wDelta >= 0 ? '+' : '' }}{{ (wDelta * 100).toFixed(1) }}%
                </td>
                <td
                  v-for="gDelta in growthDeltas"
                  :key="gDelta"
                  :class="getSensitivityCellClass(wDelta, gDelta)"
                >
                  {{ fmtAmt(getSensitivityValue(wDelta, gDelta)) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 无CGU时的空状态 -->
      <el-empty v-else description="请先在I3-6减值测试中添加CGU，或在上方选择资产组" />
    </el-card>

    <!-- 审计说明与结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>审计说明与结论</span>
          <el-button size="small" type="primary" link @click="handleAiConclusion">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写DCF模型测试结论（如：经DCF折现现金流模型测算，该资产组使用价值为…万元，高于/低于其账面价值…）"
        :disabled="isReadonly"
        @blur="handleSaveConclusion"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>DCF使用价值 = Σ(FCF_i / (1+WACC)^(i+1)) + TV / (1+WACC)^n</li>
        <li>终值TV = FCF_n × (1+g) / (WACC - g)，永续增长模型（Gordon Growth Model）</li>
        <li>WACC = E/V × Re + D/V × Rd × (1-T)，加权平均资本成本</li>
        <li>可收回金额 = MAX(公允价值-处置费用, 使用价值DCF)，取两者孰高</li>
        <li>敏感性分析验证关键假设变动对结果的影响（WACC±1% / 增长率±0.5%）</li>
        <li>折现率(WACC)必须 > 永续增长率(g)，否则终值模型无效</li>
        <li>AI建议按钮可根据行业数据自动建议折现率和增长率范围</li>
        <li>计算结果自动回传I3-6减值测试表的"可收回金额"列</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I3TabRecoverableTest.vue — I3-7 可收回金额测试（DCF核心超大表）
 *
 * 100行×16列, 22公式 — DCF核心超大表
 * Uses useI3DcfEngine (calcDcfPresentValue, calcTerminalValue, calcWacc, calcRecoverableAmount, calcSensitivity)
 * CGU selector, DCF input section (revenue 5yr + cost 5yr → FCF)
 * WACC parameters section, terminal growth rate
 * Result dashboard: PV + TV + Total DCF
 * Sensitivity matrix (3×3: WACC±/growth±)
 * Fair value less disposal input
 * Final: 可收回金额=MAX(FV-disposal, DCF) highlighted
 * Virtual scrolling (max-height=500 with overflow)
 * 蓝色渐变引导区 + AI button for WACC/growth suggestions
 *
 * Spec: .kiro/specs/i3-goodwill/
 * Task: 4.8
 * Requirements: 6.1-6.7
 */
import { ref, reactive, computed, watch, inject, onMounted } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import {
  calcDcfPresentValue,
  calcTerminalValue,
  calcWacc,
  calcRecoverableAmount,
  calcSensitivity,
} from '../../composables/useI3DcfEngine'

// ─── Props & Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Types ───────────────────────────────────────────────────────────────────

interface CguItem {
  name: string
  index: number
}

interface CashFlowRow {
  rowKey: string
  label: string
  field: string
  editable: boolean
  formula?: string
  values: number[]
}

interface DcfResult {
  presentValue: number
  terminalValue: number
  discountedTerminalValue: number
  totalDcf: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const FORECAST_YEARS = 5
const forecastYears = [1, 2, 3, 4, 5]
const waccDeltas = [-0.01, 0, 0.01]   // WACC ±1%
const growthDeltas = [-0.005, 0, 0.005] // growth ±0.5%

// ─── State ───────────────────────────────────────────────────────────────────

const activeCguIndex = ref(0)
const auditConclusion = ref('')
const fairValueLessDisposal = ref(0)

/** WACC参数 */
const waccParams = reactive({
  equityRatio: 0.6,
  debtRatio: 0.4,
  costOfEquity: 0.12,
  costOfDebt: 0.05,
  taxRate: 0.25,
  growthRate: 0.03,
})

/** 5年收入预测 */
const revenueForecasts = ref<number[]>([0, 0, 0, 0, 0])
/** 5年成本预测 */
const costForecasts = ref<number[]>([0, 0, 0, 0, 0])
/** 5年资本支出 */
const capexForecasts = ref<number[]>([0, 0, 0, 0, 0])
/** 5年营运资本变动 */
const wcChangeForecasts = ref<number[]>([0, 0, 0, 0, 0])
/** 5年折旧摊销 */
const depreciationForecasts = ref<number[]>([0, 0, 0, 0, 0])
/** 5年所得税 */
const taxForecasts = ref<number[]>([0, 0, 0, 0, 0])

// ─── CGU List (from allResponses or local) ───────────────────────────────────

const cguList = computed<CguItem[]>(() => {
  // 从 allResponses 中读取 I3-6 的CGU列表
  const raw = props.allResponses?.get('I3-6-cgu-list')
  if (raw && Array.isArray(raw)) {
    return raw.map((name: string, idx: number) => ({ name, index: idx }))
  }
  // 降级：返回默认占位
  return [{ name: '资产组1', index: 0 }]
})

const activeCgu = computed(() => cguList.value[activeCguIndex.value] ?? null)

// ─── Computed: FCF (Free Cash Flow) ──────────────────────────────────────────

/** 自由现金流 = 收入 - 成本 - 所得税 + 折旧摊销 - 资本支出 - 营运资本变动 */
const freeCashFlows = computed<number[]>(() => {
  return forecastYears.map((_, i) => {
    const ebit = revenueForecasts.value[i] - costForecasts.value[i]
    const fcf = ebit - taxForecasts.value[i] + depreciationForecasts.value[i]
      - capexForecasts.value[i] - wcChangeForecasts.value[i]
    return fcf
  })
})

// ─── Computed: WACC ──────────────────────────────────────────────────────────

const computedWacc = computed(() => {
  return calcWacc(
    waccParams.equityRatio,
    waccParams.debtRatio,
    waccParams.costOfEquity,
    waccParams.costOfDebt,
    waccParams.taxRate,
  )
})

// ─── Computed: DCF Result ────────────────────────────────────────────────────

const dcfResult = computed<DcfResult>(() => {
  const wacc = computedWacc.value
  const fcfs = freeCashFlows.value
  const g = waccParams.growthRate

  const pv = calcDcfPresentValue(fcfs, wacc)
  const lastFcf = fcfs[fcfs.length - 1] ?? 0
  const tv = calcTerminalValue(lastFcf, g, wacc)
  const discountedTV = wacc > 0
    ? tv / Math.pow(1 + wacc, FORECAST_YEARS)
    : 0
  const totalDcf = pv + discountedTV

  return {
    presentValue: pv,
    terminalValue: tv,
    discountedTerminalValue: discountedTV,
    totalDcf,
  }
})

// ─── Computed: Final Recoverable Amount ──────────────────────────────────────

const finalRecoverableAmount = computed(() => {
  return calcRecoverableAmount(fairValueLessDisposal.value, dcfResult.value.totalDcf)
})

// ─── Cash Flow Table Data (for el-table) ─────────────────────────────────────

const cashFlowTableData = computed<CashFlowRow[]>(() => {
  const fcfs = freeCashFlows.value
  const wacc = computedWacc.value
  return [
    {
      rowKey: 'revenue',
      label: '营业收入',
      field: 'revenue',
      editable: true,
      values: [...revenueForecasts.value],
    },
    {
      rowKey: 'cost',
      label: '营业成本及费用',
      field: 'cost',
      editable: true,
      values: [...costForecasts.value],
    },
    {
      rowKey: 'tax',
      label: '所得税',
      field: 'tax',
      editable: true,
      values: [...taxForecasts.value],
    },
    {
      rowKey: 'depreciation',
      label: '折旧摊销(加回)',
      field: 'depreciation',
      editable: true,
      values: [...depreciationForecasts.value],
    },
    {
      rowKey: 'capex',
      label: '资本支出',
      field: 'capex',
      editable: true,
      values: [...capexForecasts.value],
    },
    {
      rowKey: 'wcChange',
      label: '营运资本变动',
      field: 'wcChange',
      editable: true,
      values: [...wcChangeForecasts.value],
    },
    {
      rowKey: 'fcf',
      label: '自由现金流(FCF)',
      field: 'fcf',
      editable: false,
      formula: '= 收入 - 成本 - 税 + 折旧 - 资本支出 - 营运资本变动',
      values: [...fcfs],
    },
    {
      rowKey: 'discounted',
      label: '折现现金流',
      field: 'discounted',
      editable: false,
      formula: '= FCF_i / (1+WACC)^(i+1)',
      values: fcfs.map((cf, i) => wacc > 0 ? cf / Math.pow(1 + wacc, i + 1) : 0),
    },
  ]
})

// ─── Sensitivity Matrix ──────────────────────────────────────────────────────

function getSensitivityValue(waccDelta: number, growthDelta: number): number {
  const adjustedWacc = computedWacc.value + waccDelta
  const adjustedGrowth = waccParams.growthRate + growthDelta
  const fcfs = freeCashFlows.value

  if (adjustedWacc <= 0) return 0
  const pv = calcDcfPresentValue(fcfs, adjustedWacc)
  const lastFcf = fcfs[fcfs.length - 1] ?? 0
  const tv = adjustedWacc > adjustedGrowth
    ? calcTerminalValue(lastFcf, adjustedGrowth, adjustedWacc)
    : 0
  const discountedTV = tv / Math.pow(1 + adjustedWacc, FORECAST_YEARS)
  return pv + discountedTV
}

function getSensitivityCellClass(waccDelta: number, growthDelta: number): string {
  if (waccDelta === 0 && growthDelta === 0) return 'matrix-cell matrix-base'
  const val = getSensitivityValue(waccDelta, growthDelta)
  const base = dcfResult.value.totalDcf
  if (base === 0) return 'matrix-cell'
  const diff = (val - base) / Math.abs(base)
  if (diff > 0.05) return 'matrix-cell matrix-positive'
  if (diff < -0.05) return 'matrix-cell matrix-negative'
  return 'matrix-cell'
}

// ─── Cash Flow Input Handler ─────────────────────────────────────────────────

function handleCashFlowInput(field: string, yearIndex: number, value: number | null) {
  const v = value ?? 0
  switch (field) {
    case 'revenue': revenueForecasts.value[yearIndex] = v; break
    case 'cost': costForecasts.value[yearIndex] = v; break
    case 'tax': taxForecasts.value[yearIndex] = v; break
    case 'depreciation': depreciationForecasts.value[yearIndex] = v; break
    case 'capex': capexForecasts.value[yearIndex] = v; break
    case 'wcChange': wcChangeForecasts.value[yearIndex] = v; break
  }
  triggerAutoSave()
}

// ─── Auto-save & Persistence ─────────────────────────────────────────────────

let saveTimer: ReturnType<typeof setTimeout> | null = null

function triggerAutoSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => persistState(), 800)
}

function recalcAll() {
  // Ensure E/V + D/V = 1 (auto-adjust)
  if (waccParams.equityRatio + waccParams.debtRatio > 1.001) {
    waccParams.debtRatio = Math.max(0, 1 - waccParams.equityRatio)
  }
  triggerAutoSave()
}

function persistState() {
  const cguIdx = activeCguIndex.value
  const statePayload = {
    cguIndex: cguIdx,
    revenue: revenueForecasts.value,
    cost: costForecasts.value,
    tax: taxForecasts.value,
    depreciation: depreciationForecasts.value,
    capex: capexForecasts.value,
    wcChange: wcChangeForecasts.value,
    waccParams: { ...waccParams },
    fairValueLessDisposal: fairValueLessDisposal.value,
  }
  emit('save', `I3-7-dcf-cgu-${cguIdx}`, JSON.stringify(statePayload))
  // Also persist recoverable amount for I3-6 consumption
  emit('save', `I3-7-recoverable-cgu-${cguIdx}`, finalRecoverableAmount.value)
}

function loadState() {
  const cguIdx = activeCguIndex.value
  const raw = props.allResponses?.get(`I3-7-dcf-cgu-${cguIdx}`)
  if (raw) {
    try {
      const state = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (state.revenue) revenueForecasts.value = state.revenue
      if (state.cost) costForecasts.value = state.cost
      if (state.tax) taxForecasts.value = state.tax
      if (state.depreciation) depreciationForecasts.value = state.depreciation
      if (state.capex) capexForecasts.value = state.capex
      if (state.wcChange) wcChangeForecasts.value = state.wcChange
      if (state.waccParams) Object.assign(waccParams, state.waccParams)
      if (state.fairValueLessDisposal != null) fairValueLessDisposal.value = state.fairValueLessDisposal
    } catch { /* ignore parse error */ }
  }
  // Load conclusion
  const conclusion = props.allResponses?.get('I3-7-conclusion')
  if (conclusion) auditConclusion.value = String(conclusion)
}

// ─── Watch CGU switch → reload state ─────────────────────────────────────────

watch(activeCguIndex, () => {
  resetForecasts()
  loadState()
})

function resetForecasts() {
  revenueForecasts.value = [0, 0, 0, 0, 0]
  costForecasts.value = [0, 0, 0, 0, 0]
  taxForecasts.value = [0, 0, 0, 0, 0]
  depreciationForecasts.value = [0, 0, 0, 0, 0]
  capexForecasts.value = [0, 0, 0, 0, 0]
  wcChangeForecasts.value = [0, 0, 0, 0, 0]
  fairValueLessDisposal.value = 0
}

onMounted(() => {
  loadState()
})

// ─── AI Handlers ─────────────────────────────────────────────────────────────

function handleAiWaccSuggestion() {
  console.log('[I3-7] AI: suggest WACC params based on industry data')
  // TODO: call /api/workpapers/{wp_id}/ai/generate-text with WACC context
}

function handleAiGrowthSuggestion() {
  console.log('[I3-7] AI: suggest growth rate based on industry/macro data')
}

function handleAiConclusion() {
  console.log('[I3-7] AI: generate DCF conclusion')
}

// ─── Import/Export ───────────────────────────────────────────────────────────

function handleExportImport(command: string) {
  switch (command) {
    case 'export-template':
      console.log('[I3-7] Export DCF template')
      break
    case 'export-data':
      console.log('[I3-7] Export DCF data')
      break
    case 'import-data':
      console.log('[I3-7] Import DCF data')
      break
  }
}

// ─── Save & Review ───────────────────────────────────────────────────────────

function handleSaveConclusion() {
  emit('save', 'I3-7-conclusion', auditConclusion.value)
}

function openReview(id: string) {
  openReviewDialog(id)
}

// ─── Format Helpers ──────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function pct(val: number | null | undefined): string {
  if (val == null) return '-'
  return (val * 100).toFixed(2) + '%'
}
</script>

<style scoped>
.i3-tab-recoverable-test { padding: 16px; font-size: var(--wp-font-size, 13px); }

/* 蓝色渐变引导区 */
.guidance-block {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6ecfa 100%);
  border: 1px solid #b3d8f0;
  border-radius: 8px;
  padding: 16px 20px;
  margin-bottom: 16px;
}
.guidance-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 24px;
}
.guidance-step {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #1a5276;
  line-height: 1.5;
}
.step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #2980b9;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

/* 琥珀色方法论 block */
.methodology-block {
  border-left: 4px solid var(--el-color-warning);
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 16px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}

.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.section-title { font-weight: 600; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }

.sub-section-title {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  margin: 16px 0 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  display: flex;
  align-items: center;
}

/* DCF表格 */
.dcf-input-section { margin-top: 8px; }
.dcf-table-wrapper { border: 1px solid var(--el-border-color-lighter); border-radius: 4px; }
.dcf-core-table { font-size: var(--wp-font-size, 13px); }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }

/* 公式列样式 */
.formula-header {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
}
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}

/* WACC参数网格 */
.wacc-params-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px 20px;
  margin-bottom: 12px;
}
.param-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.param-item label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-weight: 500;
}
.param-value {
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

/* WACC结果行 */
.wacc-result {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  font-size: var(--wp-font-size, 13px);
}
.wacc-value {
  font-size: 16px;
  color: var(--el-color-primary);
}

/* 结果仪表板 */
.result-dashboard {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}
.result-card {
  background: #f8f9fa;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 14px 16px;
  text-align: center;
}
.result-card .result-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}
.result-card .result-value {
  font-size: 18px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.highlight-card {
  background: linear-gradient(135deg, #e3f2fd 0%, #e8f5e9 100%);
  border-color: var(--el-color-primary-light-5);
}
.primary-value {
  color: var(--el-color-primary);
}

/* 公允价值减处置费用 */
.fv-disposal-section {
  margin-bottom: 16px;
}

/* 最终可收回金额（高亮区域） */
.final-recoverable {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  margin: 16px 0;
  background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
  border: 2px solid #66bb6a;
  border-radius: 10px;
}
.final-label {
  font-size: 14px;
  font-weight: 600;
  color: #2e7d32;
}
.final-value {
  font-size: 22px;
  font-weight: 700;
  color: #1b5e20;
  font-variant-numeric: tabular-nums;
}

/* 敏感性矩阵 */
.sensitivity-matrix-wrapper {
  overflow-x: auto;
  margin-bottom: 16px;
}
.sensitivity-matrix {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.sensitivity-matrix th,
.sensitivity-matrix td {
  border: 1px solid var(--el-border-color);
  padding: 8px 12px;
  text-align: right;
  white-space: nowrap;
}
.sensitivity-matrix th {
  background: #f5f7fa;
  font-weight: 600;
  text-align: center;
}
.matrix-corner {
  text-align: center !important;
  background: #ebeef5 !important;
}
.matrix-row-header {
  text-align: left !important;
  font-weight: 500;
  background: #f5f7fa;
}
.matrix-cell { transition: background 0.2s; }
.matrix-base {
  background: #e3f2fd !important;
  font-weight: 600;
}
.matrix-positive { background: #e8f5e9 !important; color: #2e7d32; }
.matrix-negative { background: #fce4ec !important; color: #c62828; }

/* 审计说明 */
.audit-note-card { margin-bottom: 12px; }

/* 编制提示 */
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
