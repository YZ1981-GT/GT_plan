<script setup lang="ts">
/**
 * GtGoodwillImpairment — 商誉减值测试+可收回金额计算组件
 *
 * A3-8 商誉减值准备测试表 + A3-8-1 可收回金额测试（DCF/WACC）
 * Tab 切换：减值测试表 / WACC参数 / DCF现金流 / 计算结果
 *
 * 功能：
 *  - WACC 参数输入（D/E/Kd/Rf/β/Rm/T）+ 自动计算 Ke/WACC
 *  - DCF 5年现金流输入 + 永续增长率
 *  - 折现系数/现值/永续价值 自动计算
 *  - 减值判定：账面价值 vs 可收回金额
 *  - 数据自动保存到 parsed_data
 */
import { ref, computed, watch, onMounted } from 'vue'
import { api } from '@/services/apiProxy'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  wpId: string
  projectId?: string
  htmlData?: any
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save'): void
}>()

// ─── State ───
const activeTab = ref('wacc')
const saving = ref(false)

// WACC 参数
const wacc = ref({
  debt_total: 0,
  equity_total: 0,
  cost_of_debt: 0.05,
  risk_free_rate: 0.03,
  beta: 1.0,
  market_return: 0.10,
  tax_rate: 0.25,
})

// DCF 参数
const dcf = ref({
  cash_flows: [0, 0, 0, 0, 0] as number[],
  terminal_growth_rate: 0.03,
})

// 账面价值
const carryingAmount = ref(0)

// 计算结果
const results = ref<{
  ke: number
  wacc_pretax: number
  wacc_posttax: number
  market_risk_premium: number
  discount_factors: number[]
  present_values: number[]
  pv_sum: number
  terminal_value: number
  pv_terminal: number
  recoverable_amount: number
  impairment_loss: number
  needs_impairment: boolean
} | null>(null)

// ─── 本地计算（与后端引擎算法一致）───
function r4(v: number): number {
  return Math.round(v * 10000) / 10000
}

const computedResults = computed(() => {
  const w = wacc.value
  const totalCapital = w.debt_total + w.equity_total
  if (totalCapital === 0) return null

  // CAPM
  const ke = r4(w.risk_free_rate + w.beta * (w.market_return - w.risk_free_rate))
  // WACC 税后
  const waccPosttax = r4(
    (w.debt_total * w.cost_of_debt * (1 - w.tax_rate) + w.equity_total * ke) / totalCapital
  )
  // WACC 税前
  const waccPretax = w.tax_rate < 1 ? r4(waccPosttax / (1 - w.tax_rate)) : waccPosttax
  const mrp = r4(w.market_return - w.risk_free_rate)

  // DCF
  const cfs = dcf.value.cash_flows
  const g = dcf.value.terminal_growth_rate
  const n = cfs.length

  if (n === 0 || waccPretax <= g) {
    return { ke, wacc_pretax: waccPretax, wacc_posttax: waccPosttax, market_risk_premium: mrp,
      discount_factors: [], present_values: [], pv_sum: 0, terminal_value: 0,
      pv_terminal: 0, recoverable_amount: 0, impairment_loss: 0, needs_impairment: false }
  }

  const dfs = Array.from({ length: n }, (_, i) => r4(1 / Math.pow(1 + waccPretax, i + 1)))
  const pvs = cfs.map((cf, i) => r4(cf * dfs[i]))
  const pvSum = r4(pvs.reduce((a, b) => a + b, 0))
  const tv = r4(cfs[n - 1] * (1 + g) / (waccPretax - g))
  const pvTv = r4(tv * dfs[n - 1])
  const recoverable = r4(pvSum + pvTv)
  const loss = r4(Math.max(0, carryingAmount.value - recoverable))

  return {
    ke, wacc_pretax: waccPretax, wacc_posttax: waccPosttax, market_risk_premium: mrp,
    discount_factors: dfs, present_values: pvs, pv_sum: pvSum,
    terminal_value: tv, pv_terminal: pvTv, recoverable_amount: recoverable,
    impairment_loss: loss, needs_impairment: loss > 0,
  }
})

// ─── 数据加载/保存 ───
async function loadData() {
  if (!props.wpId) return
  try {
    const data = await api.get(`/api/workpapers/${props.wpId}/render-config`)
    // 优先从 html_data 取，降级从 sheets[0] 的 parsed_data
    const parsed = data?.sheets?.[0]?.html_data?.goodwill_impairment
      || data?.fill_results?.goodwill_impairment
    if (parsed) {
      if (parsed.wacc) Object.assign(wacc.value, parsed.wacc)
      if (parsed.dcf) Object.assign(dcf.value, parsed.dcf)
      if (parsed.carrying_amount != null) carryingAmount.value = parsed.carrying_amount
    }
  } catch { /* 降级：使用默认值 */ }
}

async function saveData() {
  if (props.readonly || saving.value) return
  saving.value = true
  try {
    await api.put(`/api/workpapers/${props.wpId}/parsed-data`, {
      goodwill_impairment: {
        wacc: wacc.value,
        dcf: dcf.value,
        carrying_amount: carryingAmount.value,
        results: computedResults.value,
      },
    })
    emit('save')
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

// debounce 自动保存
let saveTimer: ReturnType<typeof setTimeout> | null = null
watch([wacc, dcf, carryingAmount], () => {
  if (props.readonly) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(saveData, 2000)
}, { deep: true })

onMounted(loadData)
</script>

<template>
  <div class="gt-goodwill-impairment">
    <el-tabs v-model="activeTab" type="border-card">
      <!-- Tab 1: WACC 参数 -->
      <el-tab-pane label="WACC 参数" name="wacc">
        <div class="gt-gi-section">
          <h4>资本结构</h4>
          <el-form label-width="140px" size="small">
            <el-form-item label="债务总额 D">
              <el-input-number v-model="wacc.debt_total" :min="0" :step="100" :disabled="readonly" />
              <span class="gt-gi-unit">万元</span>
            </el-form-item>
            <el-form-item label="权益总额 E">
              <el-input-number v-model="wacc.equity_total" :min="0" :step="100" :disabled="readonly" />
              <span class="gt-gi-unit">万元</span>
            </el-form-item>
            <el-form-item label="税前债务成本 Kd">
              <el-input-number v-model="wacc.cost_of_debt" :min="0" :max="1" :step="0.005" :precision="4" :disabled="readonly" />
            </el-form-item>
            <el-form-item label="所得税率 T">
              <el-input-number v-model="wacc.tax_rate" :min="0" :max="1" :step="0.05" :precision="4" :disabled="readonly" />
            </el-form-item>
          </el-form>

          <h4>CAPM 参数</h4>
          <el-form label-width="140px" size="small">
            <el-form-item label="无风险报酬率 Rf">
              <el-input-number v-model="wacc.risk_free_rate" :min="0" :max="0.2" :step="0.005" :precision="4" :disabled="readonly" />
            </el-form-item>
            <el-form-item label="β 系数">
              <el-input-number v-model="wacc.beta" :min="0" :max="5" :step="0.1" :precision="4" :disabled="readonly" />
            </el-form-item>
            <el-form-item label="市场平均收益率 Rm">
              <el-input-number v-model="wacc.market_return" :min="0" :max="0.5" :step="0.005" :precision="4" :disabled="readonly" />
            </el-form-item>
          </el-form>

          <!-- 实时计算结果 -->
          <div v-if="computedResults" class="gt-gi-result-card">
            <div class="gt-gi-result-row"><span>Ke（权益成本）</span><strong>{{ (computedResults.ke * 100).toFixed(2) }}%</strong></div>
            <div class="gt-gi-result-row"><span>WACC（税后）</span><strong>{{ (computedResults.wacc_posttax * 100).toFixed(2) }}%</strong></div>
            <div class="gt-gi-result-row"><span>WACC（税前）</span><strong>{{ (computedResults.wacc_pretax * 100).toFixed(2) }}%</strong></div>
            <div class="gt-gi-result-row"><span>市场风险溢价</span><strong>{{ (computedResults.market_risk_premium * 100).toFixed(2) }}%</strong></div>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 2: DCF 现金流 -->
      <el-tab-pane label="DCF 现金流" name="dcf">
        <div class="gt-gi-section">
          <h4>预测期现金流量（税前）</h4>
          <el-table :data="dcf.cash_flows.map((cf, i) => ({ year: i + 1, cf }))" border size="small" class="gt-compact-table">
            <el-table-column label="年度" prop="year" width="80" align="center">
              <template #default="{ row }">第{{ row.year }}年</template>
            </el-table-column>
            <el-table-column label="现金净流量（万元）" min-width="180">
              <template #default="{ $index }">
                <el-input-number
                  v-model="dcf.cash_flows[$index]"
                  :step="10"
                  size="small"
                  :disabled="readonly"
                  style="width: 100%"
                />
              </template>
            </el-table-column>
            <el-table-column label="折现系数" width="120" align="center">
              <template #default="{ $index }">
                {{ computedResults?.discount_factors[$index]?.toFixed(4) || '-' }}
              </template>
            </el-table-column>
            <el-table-column label="现值（万元）" width="140" align="right">
              <template #default="{ $index }">
                {{ computedResults?.present_values[$index]?.toFixed(2) || '-' }}
              </template>
            </el-table-column>
          </el-table>

          <el-form label-width="140px" size="small" style="margin-top: 12px">
            <el-form-item label="永续增长率 g">
              <el-input-number v-model="dcf.terminal_growth_rate" :min="0" :max="0.1" :step="0.005" :precision="4" :disabled="readonly" />
            </el-form-item>
          </el-form>
        </div>
      </el-tab-pane>

      <!-- Tab 3: 减值判定 -->
      <el-tab-pane label="减值判定" name="result">
        <div class="gt-gi-section">
          <el-form label-width="140px" size="small">
            <el-form-item label="账面价值">
              <el-input-number v-model="carryingAmount" :min="0" :step="100" :disabled="readonly" />
              <span class="gt-gi-unit">万元</span>
            </el-form-item>
          </el-form>

          <div v-if="computedResults" class="gt-gi-impairment-summary">
            <div class="gt-gi-result-row">
              <span>预测期现值合计</span>
              <strong>{{ computedResults.pv_sum.toFixed(2) }} 万元</strong>
            </div>
            <div class="gt-gi-result-row">
              <span>永续价值</span>
              <strong>{{ computedResults.terminal_value.toFixed(2) }} 万元</strong>
            </div>
            <div class="gt-gi-result-row">
              <span>永续价值现值</span>
              <strong>{{ computedResults.pv_terminal.toFixed(2) }} 万元</strong>
            </div>
            <div class="gt-gi-result-row gt-gi-highlight">
              <span>可收回金额</span>
              <strong>{{ computedResults.recoverable_amount.toFixed(2) }} 万元</strong>
            </div>
            <div class="gt-gi-result-row" :class="{ 'gt-gi-danger': computedResults.needs_impairment }">
              <span>减值损失</span>
              <strong>{{ computedResults.impairment_loss.toFixed(2) }} 万元</strong>
            </div>
            <el-alert
              v-if="computedResults.needs_impairment"
              type="warning"
              :closable="false"
              style="margin-top: 12px"
            >
              账面价值（{{ carryingAmount.toFixed(2) }}万元）超过可收回金额（{{ computedResults.recoverable_amount.toFixed(2) }}万元），需计提商誉减值准备 {{ computedResults.impairment_loss.toFixed(2) }} 万元。
            </el-alert>
            <el-alert
              v-else
              type="success"
              :closable="false"
              style="margin-top: 12px"
            >
              账面价值未超过可收回金额，无需计提减值。
            </el-alert>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.gt-goodwill-impairment {
  padding: 12px;
}
.gt-gi-section h4 {
  margin: 12px 0 8px;
  font-size: 14px;
  color: var(--gt-primary, #4b2d77);
}
.gt-gi-unit {
  margin-left: 8px;
  color: #999;
  font-size: 12px;
}
.gt-gi-result-card {
  background: var(--gt-bg-light, #f4f0fa);
  border: 1px solid var(--gt-border-light, #d8b8ee);
  border-radius: 6px;
  padding: 12px 16px;
  margin-top: 16px;
}
.gt-gi-result-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 0;
  font-size: var(--wp-font-size, 13px);
}
.gt-gi-result-row strong {
  color: var(--gt-primary, #4b2d77);
}
.gt-gi-highlight {
  background: #f0f9ff;
  border-radius: 4px;
  padding: 8px 12px;
  margin: 4px -12px;
}
.gt-gi-danger strong {
  color: #e6323e;
}
.gt-gi-impairment-summary {
  background: #fafafa;
  border: 1px solid #eee;
  border-radius: 6px;
  padding: 16px;
  margin-top: 12px;
}
</style>
