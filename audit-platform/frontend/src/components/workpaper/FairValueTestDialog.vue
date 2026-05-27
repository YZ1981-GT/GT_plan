<template>
  <el-dialog
    :model-value="visible"
    title="📊 公允价值测试（G-F4 Level 1/2/3）"
    width="820px"
    :close-on-click-modal="false"
    append-to-body
    @update:model-value="emit('update:visible', $event)"
  >
    <el-alert
      type="info"
      show-icon
      :closable="false"
      style="margin-bottom: 12px"
    >
      <template #default>
        IFRS 13 / CAS 39 公允价值层级测试。
        Level 1：活跃市场报价；Level 2：可观察输入（利率/信用利差/波动率）；Level 3：DCF 不可观察输入。
        Level 1/2 公式准确；Level 3 DCF 公式正确，AI 辅助参数建议待 wp_ai_service 升级后接入。
        <strong>「采纳并写回」会把测试结果写入当前底稿 parsed_data，便于后续溯源。</strong>
      </template>
    </el-alert>

    <el-form :model="form" label-width="140px" size="small">
      <el-form-item label="公允价值层级" required>
        <el-radio-group v-model="form.level">
          <el-radio-button :value="1">Level 1（市场报价）</el-radio-button>
          <el-radio-button :value="2">Level 2（可观察输入）</el-radio-button>
          <el-radio-button :value="3">Level 3（DCF 不可观察）</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="金融工具类型" required>
        <el-input
          v-model="form.instrument_type"
          placeholder="如 交易性金融资产 / 债权投资 / 其他权益工具投资"
          style="width: 280px"
        />
      </el-form-item>

      <el-form-item label="面值/数量" required>
        <el-input-number
          v-model="form.face_value"
          :min="0.01"
          :max="999999999999"
          :step="10000"
          :precision="2"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">元 / 单位</span>
      </el-form-item>
    </el-form>

    <!-- Level 1 参数 -->
    <template v-if="form.level === 1">
      <el-divider>Level 1 参数</el-divider>
      <el-form :model="form" label-width="140px" size="small">
        <el-form-item label="市场报价" required>
          <el-input-number
            v-model="form.market_price"
            :min="0"
            :max="999999999999"
            :step="0.01"
            :precision="4"
            controls-position="right"
            style="width: 220px"
          />
          <span class="gt-form-unit">元 / 单位</span>
        </el-form-item>

        <el-form-item label="报价日期" required>
          <el-input
            v-model="form.price_date"
            placeholder="YYYY-MM-DD"
            style="width: 220px"
          />
        </el-form-item>
      </el-form>
    </template>

    <!-- Level 2 参数 -->
    <template v-if="form.level === 2">
      <el-divider>Level 2 参数</el-divider>
      <el-form :model="form" label-width="140px" size="small">
        <el-form-item label="信用利差" required>
          <el-input-number
            v-model="form.credit_spread"
            :min="0"
            :max="0.999"
            :step="0.001"
            :precision="4"
            controls-position="right"
            style="width: 200px"
          />
          <span class="gt-form-unit">（0~1，如 0.02 = 2%）</span>
        </el-form-item>

        <el-form-item label="波动率" required>
          <el-input-number
            v-model="form.volatility"
            :min="0"
            :max="10"
            :step="0.01"
            :precision="4"
            controls-position="right"
            style="width: 200px"
          />
          <span class="gt-form-unit">（调整系数）</span>
        </el-form-item>
      </el-form>

      <el-divider>利率曲线（每期 0~1）</el-divider>
      <el-table :data="rateCurveRows" size="small" border style="margin-bottom: 12px">
        <el-table-column label="期数" width="80" align="center">
          <template #default="{ $index }">第 {{ $index + 1 }} 期</template>
        </el-table-column>
        <el-table-column label="利率（0~1）" min-width="200">
          <template #default="{ $index }">
            <el-input-number
              v-model="form.interest_rate_curve[$index]"
              :min="0"
              :max="0.999"
              :step="0.001"
              :precision="4"
              controls-position="right"
              style="width: 200px"
            />
          </template>
        </el-table-column>
        <el-table-column label="" width="80">
          <template #default="{ $index }">
            <el-button
              v-if="form.interest_rate_curve.length > 1"
              size="small"
              link
              type="danger"
              @click="removeRateCurvePeriod($index)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-button v-if="form.interest_rate_curve.length < 20" size="small" plain @click="addRateCurvePeriod">
        + 添加期数
      </el-button>
    </template>

    <!-- Level 3 参数（DCF）-->
    <template v-if="form.level === 3">
      <el-divider>Level 3 DCF 参数</el-divider>
      <el-form :model="form" label-width="140px" size="small">
        <el-form-item label="折现率" required>
          <el-input-number
            v-model="form.discount_rate"
            :min="0.001"
            :max="0.999"
            :step="0.01"
            :precision="4"
            controls-position="right"
            style="width: 200px"
          />
          <span class="gt-form-unit">（0~1，如 0.10 = 10%）</span>
        </el-form-item>

        <el-form-item label="终值">
          <el-input-number
            v-model="form.terminal_value"
            :min="0"
            :max="999999999999"
            :step="10000"
            :precision="2"
            controls-position="right"
            style="width: 220px"
          />
          <span class="gt-form-unit">元（第 N 年末残余价值，可选）</span>
        </el-form-item>
      </el-form>

      <el-divider>5 年现金流预测</el-divider>
      <el-table :data="cashFlowRows" size="small" border style="margin-bottom: 12px">
        <el-table-column label="年份" width="80" align="center">
          <template #default="{ $index }">第 {{ $index + 1 }} 年</template>
        </el-table-column>
        <el-table-column label="预测现金流（元）" min-width="200">
          <template #default="{ $index }">
            <el-input-number
              v-model="form.cash_flow_projections[$index]"
              :min="0"
              :step="10000"
              :precision="2"
              controls-position="right"
              style="width: 200px"
            />
          </template>
        </el-table-column>
        <el-table-column label="" width="80">
          <template #default="{ $index }">
            <el-button
              v-if="form.cash_flow_projections.length > 1"
              size="small"
              link
              type="danger"
              @click="removeCashFlowYear($index)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-button v-if="form.cash_flow_projections.length < 10" size="small" plain @click="addCashFlowYear">
        + 添加年份
      </el-button>
    </template>

    <!-- 计算结果 -->
    <template v-if="result">
      <el-divider>测试结果</el-divider>
      <div class="fair-value-result">
        <el-alert
          :title="result.conclusion"
          :type="resultAlertType"
          show-icon
          :closable="false"
          style="margin-bottom: 12px"
        />

        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="层级">Level {{ result.level }}</el-descriptions-item>
          <el-descriptions-item label="金融工具">{{ result.instrument_type }}</el-descriptions-item>
          <el-descriptions-item label="面值/数量">¥ {{ formatAmount(result.face_value) }}</el-descriptions-item>
          <el-descriptions-item label="公允价值">
            <span class="amt-highlight">¥ {{ formatAmount(result.fair_value) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="估值方法" :span="2">
            <span class="valuation-method">{{ result.valuation_method }}</span>
          </el-descriptions-item>
        </el-descriptions>

        <!-- Level 3 DCF 明细 -->
        <el-table
          v-if="result.dcf_details && result.dcf_details.length > 0"
          :data="result.dcf_details"
          size="small"
          border
          style="margin-top: 12px"
        >
          <el-table-column label="期数" prop="period" width="120" align="center" />
          <el-table-column label="现金流" width="160" align="right">
            <template #default="{ row }">¥ {{ formatAmount(row.cash_flow) }}</template>
          </el-table-column>
          <el-table-column label="折现因子" prop="discount_factor" width="140" align="right" />
          <el-table-column label="现值" width="160" align="right">
            <template #default="{ row }">¥ {{ formatAmount(row.present_value) }}</template>
          </el-table-column>
        </el-table>
      </div>
    </template>

    <template #footer>
      <el-button @click="emit('update:visible', false)">关闭</el-button>
      <el-button
        type="primary"
        :loading="loading"
        :disabled="!isFormValid"
        @click="onAnalyze"
      >
        🚀 计算公允价值
      </el-button>
      <el-button
        v-if="result"
        type="success"
        :loading="applying"
        :disabled="!targetSheet"
        @click="onApplyToSheet"
      >
        ✅ 采纳并写回
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'

interface Props {
  visible: boolean
  projectId: string
  wpId: string
  /** 当前活动 sheet 名（用于「采纳并写回」按钮） */
  targetSheet?: string
  /** 默认金融工具类型（按 sheet 上下文推荐：G1=交易性金融资产 / G6=其他债权投资 / G8=其他权益工具投资）*/
  instrumentType?: string
}
const props = withDefaults(defineProps<Props>(), {
  targetSheet: '',
  instrumentType: '交易性金融资产',
})
const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'applied', sheet: string): void
}>()

interface DcfDetail {
  period: string | number
  cash_flow: string
  discount_factor: string
  present_value: string
}

interface FairValueTestResponse {
  level: number
  instrument_type: string
  face_value: string
  fair_value: string
  valuation_method: string
  conclusion: string
  dcf_details: DcfDetail[] | null
  is_llm_stub: boolean
  applied_to_sheet?: string | null
}

const loading = ref(false)
const applying = ref(false)
const result = ref<FairValueTestResponse | null>(null)

const form = reactive({
  level: 1 as 1 | 2 | 3,
  instrument_type: props.instrumentType,
  face_value: 1000000,
  // Level 1
  market_price: 1.0 as number | null,
  price_date: new Date().toISOString().slice(0, 10),
  // Level 2
  interest_rate_curve: [0.025, 0.028, 0.030, 0.032, 0.035] as number[],
  credit_spread: 0.02 as number | null,
  volatility: 0.15 as number | null,
  // Level 3 DCF
  cash_flow_projections: [200000, 220000, 240000, 260000, 280000] as number[],
  discount_rate: 0.10 as number | null,
  terminal_value: 0,
})

const cashFlowRows = computed(() => form.cash_flow_projections.map((_, i) => ({ index: i })))
const rateCurveRows = computed(() => form.interest_rate_curve.map((_, i) => ({ index: i })))

function addCashFlowYear() {
  if (form.cash_flow_projections.length < 10) {
    const last = form.cash_flow_projections[form.cash_flow_projections.length - 1] || 0
    form.cash_flow_projections.push(last)
  }
}

function removeCashFlowYear(idx: number) {
  if (form.cash_flow_projections.length > 1) {
    form.cash_flow_projections.splice(idx, 1)
  }
}

function addRateCurvePeriod() {
  if (form.interest_rate_curve.length < 20) {
    const last = form.interest_rate_curve[form.interest_rate_curve.length - 1] || 0.03
    form.interest_rate_curve.push(last)
  }
}

function removeRateCurvePeriod(idx: number) {
  if (form.interest_rate_curve.length > 1) {
    form.interest_rate_curve.splice(idx, 1)
  }
}

const isFormValid = computed(() => {
  if (!form.instrument_type) return false
  if (form.face_value <= 0) return false

  if (form.level === 1) {
    if (form.market_price == null || form.market_price < 0) return false
    if (!form.price_date) return false
    return true
  }

  if (form.level === 2) {
    if (form.credit_spread == null || form.credit_spread < 0 || form.credit_spread >= 1) return false
    if (form.volatility == null || form.volatility < 0) return false
    if (form.interest_rate_curve.length === 0) return false
    if (form.interest_rate_curve.some((r) => r < 0 || r >= 1)) return false
    return true
  }

  if (form.level === 3) {
    if (form.discount_rate == null || form.discount_rate <= 0 || form.discount_rate >= 1) return false
    if (form.cash_flow_projections.length === 0) return false
    if (!form.cash_flow_projections.some((cf) => cf > 0)) return false
    return true
  }

  return false
})

const resultAlertType = computed<'success' | 'warning' | 'error'>(() => {
  if (!result.value) return 'success'
  const c = result.value.conclusion || ''
  if (c.includes('重大偏差')) return 'error'
  if (c.includes('需关注')) return 'warning'
  return 'success'
})

function formatAmount(s: string | number) {
  const n = Number(s)
  if (!Number.isFinite(n)) return String(s)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function buildRequestBody(applySheet?: string): Record<string, any> {
  const body: Record<string, any> = {
    level: form.level,
    instrument_type: form.instrument_type,
    face_value: form.face_value,
  }

  if (form.level === 1) {
    body.market_price = form.market_price
    body.price_date = form.price_date
  } else if (form.level === 2) {
    body.interest_rate_curve = form.interest_rate_curve
    body.credit_spread = form.credit_spread
    body.volatility = form.volatility
  } else if (form.level === 3) {
    body.cash_flow_projections = form.cash_flow_projections.filter((cf) => cf >= 0)
    body.discount_rate = form.discount_rate
    body.terminal_value = form.terminal_value
  }

  if (applySheet) {
    body.apply_to_sheet = applySheet
  }
  return body
}

async function onAnalyze() {
  loading.value = true
  try {
    const resp = await api.post<FairValueTestResponse>(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/g/fair-value-test`,
      buildRequestBody(),
    )
    result.value = resp
    ElMessage.success(`分析完成：公允价值 ¥${formatAmount(resp.fair_value)}`)
  } catch (e: any) {
    handleApiError(e, '公允价值测试')
  } finally {
    loading.value = false
  }
}

async function onApplyToSheet() {
  if (!props.targetSheet) {
    ElMessage.warning('未识别到当前 sheet，无法写回')
    return
  }
  applying.value = true
  try {
    const resp = await api.post<FairValueTestResponse>(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/g/fair-value-test`,
      buildRequestBody(props.targetSheet),
    )
    result.value = resp
    if (resp?.applied_to_sheet) {
      ElMessage.success(`已采纳并写回 ${resp.applied_to_sheet}`)
      emit('applied', resp.applied_to_sheet)
    } else {
      ElMessage.warning('分析完成但未写回（applied_to_sheet 为空）')
    }
  } catch (e: any) {
    handleApiError(e, '采纳写回')
  } finally {
    applying.value = false
  }
}

// 重置 result + 同步 instrumentType prop 在弹窗关闭/打开时
watch(() => props.visible, (v) => {
  if (!v) {
    result.value = null
  } else {
    // 弹窗打开时同步 instrumentType prop（按当前 sheet 上下文推荐）
    if (props.instrumentType) {
      form.instrument_type = props.instrumentType
    }
  }
})

defineExpose({
  form,
  result,
  isFormValid,
  buildRequestBody,
  onAnalyze,
  onApplyToSheet,
  addCashFlowYear,
  removeCashFlowYear,
  addRateCurvePeriod,
  removeRateCurvePeriod,
})
</script>

<style scoped>
.gt-form-unit {
  margin-left: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.fair-value-result {
  margin-top: 8px;
}
.amt-highlight {
  color: var(--el-color-primary);
  font-weight: 600;
}
.valuation-method {
  font-size: 12px;
  color: var(--el-text-color-regular);
  font-family: monospace;
}
</style>
