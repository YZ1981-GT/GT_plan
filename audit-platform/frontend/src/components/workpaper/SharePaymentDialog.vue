<template>
  <el-dialog
    :model-value="visible"
    title="🧮 股份支付公允价值测算（J-F8 Black-Scholes）"
    width="680px"
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
        基于 Black-Scholes 模型计算期权公允价值，支持含股息率的扩展公式。
        计算结果可「采纳并写回」当前底稿 parsed_data。
      </template>
    </el-alert>

    <el-form :model="form" label-width="140px" size="small">
      <el-form-item label="标的股票价格 S" required>
        <el-input-number v-model="form.stock_price" :min="0.01" :step="1" :precision="2" controls-position="right" style="width: 180px" />
        <span class="gt-form-unit">元</span>
      </el-form-item>

      <el-form-item label="行权价格 K" required>
        <el-input-number v-model="form.exercise_price" :min="0.01" :step="1" :precision="2" controls-position="right" style="width: 180px" />
        <span class="gt-form-unit">元</span>
      </el-form-item>

      <el-form-item label="无风险利率 r" required>
        <el-input-number v-model="form.risk_free_rate" :min="0" :max="1" :step="0.005" :precision="4" controls-position="right" style="width: 160px" />
      </el-form-item>

      <el-form-item label="波动率 σ" required>
        <el-input-number v-model="form.volatility" :min="0.01" :max="5" :step="0.05" :precision="4" controls-position="right" style="width: 160px" />
      </el-form-item>

      <el-form-item label="到期时间 T" required>
        <el-input-number v-model="form.time_to_maturity" :min="0.01" :max="30" :step="0.5" :precision="2" controls-position="right" style="width: 160px" />
        <span class="gt-form-unit">年</span>
      </el-form-item>

      <el-form-item label="股息率 q">
        <el-input-number v-model="form.dividend_yield" :min="0" :max="1" :step="0.005" :precision="4" controls-position="right" style="width: 160px" />
      </el-form-item>

      <el-form-item label="授予数量" required>
        <el-input-number v-model="form.grant_quantity" :min="1" :step="10000" controls-position="right" style="width: 200px" />
        <span class="gt-form-unit">份</span>
      </el-form-item>

      <el-form-item label="等待期" required>
        <el-input-number v-model="form.vesting_period" :min="1" :max="10" controls-position="right" style="width: 120px" />
        <span class="gt-form-unit">年</span>
      </el-form-item>
    </el-form>

    <!-- 计算结果 -->
    <template v-if="result">
      <el-divider>计算结果</el-divider>
      <div class="bs-result">
        <el-descriptions :column="3" size="small" border>
          <el-descriptions-item label="单份期权价值">¥ {{ formatAmount(result.option_value) }}</el-descriptions-item>
          <el-descriptions-item label="公允价值总额">¥ {{ formatAmount(result.total_fair_value) }}</el-descriptions-item>
          <el-descriptions-item label="LLM Stub">{{ result.is_llm_stub ? '是（待接入）' : '否' }}</el-descriptions-item>
        </el-descriptions>

        <el-table :data="result.annual_expense_schedule" size="small" border style="margin-top: 12px" max-height="200">
          <el-table-column label="年度" prop="year" width="80" align="center" />
          <el-table-column label="当年费用" width="150" align="right">
            <template #default="{ row }">¥ {{ formatAmount(row.expense) }}</template>
          </el-table-column>
          <el-table-column label="累计费用" width="150" align="right">
            <template #default="{ row }">¥ {{ formatAmount(row.cumulative) }}</template>
          </el-table-column>
        </el-table>
      </div>
    </template>

    <template #footer>
      <el-button @click="emit('update:visible', false)">关闭</el-button>
      <el-button type="primary" :loading="loading" :disabled="!isFormValid" @click="onCalc">🚀 计算</el-button>
      <el-button v-if="result" type="success" :loading="applying" :disabled="!targetSheet" @click="onApplyToSheet">✅ 采纳并写回</el-button>
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
  targetSheet?: string
}
const props = withDefaults(defineProps<Props>(), { targetSheet: '' })
const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'applied', sheet: string): void
}>()

interface ScheduleItem { year: number; expense: number; cumulative: number }
interface BSResponse {
  option_value: number
  total_fair_value: number
  annual_expense_schedule: ScheduleItem[]
  is_llm_stub: boolean
  applied_to_sheet?: string | null
}

const loading = ref(false)
const applying = ref(false)
const result = ref<BSResponse | null>(null)

const form = reactive({
  stock_price: 20,
  exercise_price: 18,
  risk_free_rate: 0.03,
  volatility: 0.35,
  time_to_maturity: 3,
  dividend_yield: 0.01,
  grant_quantity: 1000000,
  vesting_period: 4,
})

const isFormValid = computed(() => form.stock_price > 0 && form.exercise_price > 0 && form.volatility > 0 && form.time_to_maturity > 0)

function formatAmount(n: number) {
  if (!Number.isFinite(n)) return String(n)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
}

function buildBody(applySheet?: string) {
  return { ...form, apply_to_sheet: applySheet || null }
}

async function onCalc() {
  loading.value = true
  try {
    const resp = await api.post<BSResponse>(`/api/projects/${props.projectId}/workpapers/${props.wpId}/j3/share-payment-calc`, buildBody())
    result.value = resp
    ElMessage.success(`计算完成：期权价值 ¥${resp.option_value.toFixed(4)}`)
  } catch (e: any) { handleApiError(e, '计算') }
  finally { loading.value = false }
}

async function onApplyToSheet() {
  if (!props.targetSheet) { ElMessage.warning('未识别到当前 sheet'); return }
  applying.value = true
  try {
    const resp = await api.post<BSResponse>(`/api/projects/${props.projectId}/workpapers/${props.wpId}/j3/share-payment-calc`, buildBody(props.targetSheet))
    result.value = resp
    if (resp?.applied_to_sheet) { ElMessage.success(`已写回 ${resp.applied_to_sheet}`); emit('applied', resp.applied_to_sheet) }
    else { ElMessage.warning('计算完成但未写回') }
  } catch (e: any) { handleApiError(e, '写回') }
  finally { applying.value = false }
}

watch(() => props.visible, (v) => { if (!v) result.value = null })
</script>

<style scoped>
.gt-form-unit { margin-left: 8px; color: var(--el-text-color-secondary); font-size: 12px; }
.bs-result { margin-top: 8px; }
</style>
