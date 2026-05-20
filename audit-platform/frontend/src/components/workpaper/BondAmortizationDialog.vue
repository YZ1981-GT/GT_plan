<template>
  <el-dialog
    :model-value="visible"
    title="📊 应付债券摊余成本测算（L-F8）"
    width="860px"
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
        输入面值、发行价格、票面利率、实际利率、期限和付息频率，自动生成摊余成本表（实际利率法）。
        最后一期做尾差调整确保期末摊余成本收敛到面值。计算结果可「采纳并写回」当前底稿。
      </template>
    </el-alert>

    <el-form :model="form" label-width="120px" size="small">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="面值" required>
            <el-input-number
              v-model="form.face_value"
              :min="0.01"
              :max="99999999999"
              :step="100000"
              :precision="2"
              controls-position="right"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="发行价格" required>
            <el-input-number
              v-model="form.issue_price"
              :min="0.01"
              :max="99999999999"
              :step="100000"
              :precision="2"
              controls-position="right"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="票面利率" required>
            <el-input-number
              v-model="form.coupon_rate"
              :min="0"
              :max="1"
              :step="0.005"
              :precision="6"
              controls-position="right"
              style="width: 100%"
            />
            <span class="gt-form-unit">（如 0.05 = 5%）</span>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="实际利率" required>
            <el-input-number
              v-model="form.effective_rate"
              :min="0.0001"
              :max="1"
              :step="0.005"
              :precision="6"
              controls-position="right"
              style="width: 100%"
            />
            <span class="gt-form-unit">（如 0.06 = 6%）</span>
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="期限（年）" required>
            <el-input-number
              v-model="form.term_years"
              :min="1"
              :max="50"
              :step="1"
              :precision="0"
              controls-position="right"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="付息频率" required>
            <el-select v-model="form.payment_frequency" style="width: 100%">
              <el-option label="年付息" value="annual" />
              <el-option label="半年付息" value="semi_annual" />
              <el-option label="季付息" value="quarterly" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>

    <!-- 计算结果 -->
    <template v-if="result">
      <el-divider>计算结果</el-divider>

      <!-- 汇总指标 -->
      <el-descriptions :column="2" size="small" border style="margin-bottom: 12px">
        <el-descriptions-item label="利息费用合计">
          <span class="gt-amt">¥ {{ formatAmount(result.total_interest_expense) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="票面利息合计">
          <span class="gt-amt">¥ {{ formatAmount(result.total_coupon_payments) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="摊销额合计">
          <span class="gt-amt">¥ {{ formatAmount(result.total_amortization) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="最终摊余成本">
          <span class="gt-amt">¥ {{ formatAmount(result.final_carrying_amount) }}</span>
        </el-descriptions-item>
      </el-descriptions>

      <!-- is_llm_stub 指示器 -->
      <el-tag v-if="result.is_llm_stub" type="warning" size="small" style="margin-bottom: 8px">
        ⚠ LLM 辅助参数建议待接入（当前为公式计算结果）
      </el-tag>

      <!-- 摊余成本表 -->
      <el-table
        :data="result.amortization_schedule"
        size="small"
        border
        stripe
        max-height="320"
        style="width: 100%"
      >
        <el-table-column prop="period" label="期数" width="60" align="center" />
        <el-table-column prop="opening_carrying" label="期初摊余成本" min-width="130" align="right">
          <template #default="{ row }">
            <span class="gt-amt">{{ formatAmount(row.opening_carrying) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="interest_expense" label="利息费用" min-width="110" align="right">
          <template #default="{ row }">
            <span class="gt-amt">{{ formatAmount(row.interest_expense) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="coupon_payment" label="票面利息" min-width="110" align="right">
          <template #default="{ row }">
            <span class="gt-amt">{{ formatAmount(row.coupon_payment) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="amortization" label="摊销额" min-width="110" align="right">
          <template #default="{ row }">
            <span class="gt-amt">{{ formatAmount(row.amortization) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="closing_carrying" label="期末摊余成本" min-width="130" align="right">
          <template #default="{ row }">
            <span class="gt-amt">{{ formatAmount(row.closing_carrying) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <template #footer>
      <el-button @click="emit('update:visible', false)">关闭</el-button>
      <el-button
        type="primary"
        :loading="loading"
        :disabled="!isFormValid"
        @click="onCalc"
      >
        🚀 计算
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

interface Props {
  visible: boolean
  projectId: string
  workpaperId: string
  targetSheet?: string
}
const props = withDefaults(defineProps<Props>(), {
  targetSheet: '',
})
const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'applied', sheet: string): void
  (e: 'close'): void
}>()

interface ScheduleItem {
  period: number
  opening_carrying: string
  interest_expense: string
  coupon_payment: string
  amortization: string
  closing_carrying: string
}

interface BondAmortizationResult {
  amortization_schedule: ScheduleItem[]
  total_interest_expense: string
  total_coupon_payments: string
  total_amortization: string
  final_carrying_amount: string
  is_llm_stub: boolean
  applied_to_sheet?: string | null
  applied_at?: string | null
}

const loading = ref(false)
const applying = ref(false)
const result = ref<BondAmortizationResult | null>(null)

const form = reactive({
  face_value: 1000000,
  issue_price: 950000,
  coupon_rate: 0.05,
  effective_rate: 0.06,
  term_years: 5,
  payment_frequency: 'annual' as 'annual' | 'semi_annual' | 'quarterly',
})

const isFormValid = computed(() => {
  return (
    form.face_value > 0 &&
    form.issue_price > 0 &&
    form.coupon_rate >= 0 &&
    form.coupon_rate <= 1 &&
    form.effective_rate > 0 &&
    form.effective_rate <= 1 &&
    form.term_years >= 1
  )
})

function formatAmount(s: string | number) {
  const n = Number(s)
  if (!Number.isFinite(n)) return String(s)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function buildRequestBody(applySheet?: string) {
  return {
    face_value: form.face_value,
    issue_price: form.issue_price,
    coupon_rate: form.coupon_rate,
    effective_rate: form.effective_rate,
    term_years: form.term_years,
    payment_frequency: form.payment_frequency,
    apply_to_sheet: applySheet || null,
  }
}

async function onCalc() {
  loading.value = true
  try {
    const resp = await api.post<BondAmortizationResult>(
      `/api/projects/${props.projectId}/workpapers/${props.workpaperId}/l5/bond-amortization`,
      buildRequestBody(),
    )
    result.value = resp
    ElMessage.success(`计算完成：${resp.amortization_schedule.length} 期摊余成本表已生成`)
  } catch (e: any) {
    ElMessage.error(e?.message || '摊余成本计算失败')
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
    const resp = await api.post<BondAmortizationResult>(
      `/api/projects/${props.projectId}/workpapers/${props.workpaperId}/l5/bond-amortization`,
      buildRequestBody(props.targetSheet),
    )
    result.value = resp
    if (resp?.applied_to_sheet) {
      ElMessage.success(`已采纳并写回 ${resp.applied_to_sheet}`)
      emit('applied', resp.applied_to_sheet)
    } else {
      ElMessage.warning('计算完成但未写回（applied_to_sheet 为空）')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '采纳写回失败')
  } finally {
    applying.value = false
  }
}

watch(() => props.visible, (v) => {
  if (!v) result.value = null
})
</script>

<style scoped>
.gt-form-unit {
  margin-left: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.gt-amt {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
</style>
