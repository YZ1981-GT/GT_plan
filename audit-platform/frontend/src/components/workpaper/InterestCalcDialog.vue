<template>
  <el-dialog
    :model-value="visible"
    title="🧮 利息自动测算（L-F7）"
    width="720px"
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
        输入本金、年利率、起息日、到期日、计息基准和复利频率，自动计算利息总额。
        支持 3 种计息基准（ACT/360、ACT/365、30/360）× 3 种复利频率（单利、月复利、季复利）。
        计算结果可「采纳并写回」当前底稿。
      </template>
    </el-alert>

    <el-form :model="form" label-width="120px" size="small">
      <el-form-item label="本金" required>
        <el-input-number
          v-model="form.principal"
          :min="0"
          :max="99999999999"
          :step="10000"
          :precision="2"
          controls-position="right"
          style="width: 240px"
        />
        <span class="gt-form-unit">元</span>
      </el-form-item>

      <el-form-item label="年利率" required>
        <el-input-number
          v-model="form.annual_rate"
          :min="0"
          :max="1"
          :step="0.001"
          :precision="6"
          controls-position="right"
          style="width: 200px"
        />
        <span class="gt-form-unit">（如 0.045 = 4.5%）</span>
      </el-form-item>

      <el-form-item label="起息日" required>
        <el-date-picker
          v-model="form.start_date"
          type="date"
          placeholder="选择起息日"
          value-format="YYYY-MM-DD"
          style="width: 180px"
        />
      </el-form-item>

      <el-form-item label="到期日" required>
        <el-date-picker
          v-model="form.end_date"
          type="date"
          placeholder="选择到期日"
          value-format="YYYY-MM-DD"
          style="width: 180px"
        />
      </el-form-item>

      <el-form-item label="计息基准" required>
        <el-select v-model="form.day_count_basis" style="width: 160px">
          <el-option label="ACT/360" value="ACT/360" />
          <el-option label="ACT/365" value="ACT/365" />
          <el-option label="30/360" value="30/360" />
        </el-select>
      </el-form-item>

      <el-form-item label="复利频率" required>
        <el-select v-model="form.compound_frequency" style="width: 160px">
          <el-option label="单利" value="simple" />
          <el-option label="月复利" value="monthly" />
          <el-option label="季复利" value="quarterly" />
        </el-select>
      </el-form-item>
    </el-form>

    <!-- 计算结果 -->
    <template v-if="result">
      <el-divider>计算结果</el-divider>
      <div class="interest-result">
        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="利息总额">
            <span class="gt-amt">¥ {{ formatAmount(result.interest_amount) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="日利息">
            <span class="gt-amt">¥ {{ formatAmount(result.daily_interest) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="计息天数">
            {{ result.period_days }} 天
          </el-descriptions-item>
          <el-descriptions-item label="计息基准分母">
            {{ result.day_count_divisor }}
          </el-descriptions-item>
          <el-descriptions-item v-if="result.compound_periods != null" label="复利期数">
            {{ result.compound_periods }} 期
          </el-descriptions-item>
        </el-descriptions>

        <el-alert
          type="success"
          show-icon
          :closable="false"
          style="margin-top: 12px"
        >
          <template #default>
            {{ result.calculation_detail }}
          </template>
        </el-alert>
      </div>
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
import { handleApiError } from '@/utils/errorHandler'

interface Props {
  visible: boolean
  projectId: string
  workpaperId: string
  wpCode: 'L1' | 'L3'
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

interface InterestCalcResult {
  interest_amount: string
  daily_interest: string
  period_days: number
  day_count_divisor: number
  calculation_detail: string
  compound_periods: number | null
  applied_to_sheet?: string | null
  applied_at?: string | null
}

const loading = ref(false)
const applying = ref(false)
const result = ref<InterestCalcResult | null>(null)

const form = reactive({
  principal: 1000000,
  annual_rate: 0.045,
  start_date: '',
  end_date: '',
  day_count_basis: 'ACT/360' as 'ACT/360' | 'ACT/365' | '30/360',
  compound_frequency: 'simple' as 'simple' | 'monthly' | 'quarterly',
})

const isFormValid = computed(() => {
  return (
    form.principal >= 0 &&
    form.annual_rate >= 0 &&
    form.annual_rate <= 1 &&
    form.start_date !== '' &&
    form.end_date !== '' &&
    form.start_date <= form.end_date
  )
})

function formatAmount(s: string | number) {
  const n = Number(s)
  if (!Number.isFinite(n)) return String(s)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function buildRequestBody(applySheet?: string) {
  return {
    wp_code: props.wpCode,
    principal: form.principal,
    annual_rate: form.annual_rate,
    start_date: form.start_date,
    end_date: form.end_date,
    day_count_basis: form.day_count_basis,
    compound_frequency: form.compound_frequency,
    apply_to_sheet: applySheet || null,
  }
}

async function onCalc() {
  loading.value = true
  try {
    const resp = await api.post<InterestCalcResult>(
      `/api/projects/${props.projectId}/workpapers/${props.workpaperId}/l/interest-calc`,
      buildRequestBody(),
    )
    result.value = resp
    ElMessage.success(`计算完成：利息总额 ¥${formatAmount(resp.interest_amount)}`)
  } catch (e: any) {
    handleApiError(e, '利息测算计算')
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
    const resp = await api.post<InterestCalcResult>(
      `/api/projects/${props.projectId}/workpapers/${props.workpaperId}/l/interest-calc`,
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
    handleApiError(e, '采纳写回')
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
.interest-result {
  margin-top: 8px;
}
.gt-amt {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
</style>
