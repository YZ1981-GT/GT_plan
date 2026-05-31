<template>
  <el-dialog
    :model-value="visible"
    title="🧮 薪酬计提自动测算（J-F7）"
    width="780px"
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
        输入员工数、月均工资、社保比例等参数，自动计算月度计提明细 + 年度汇总。
        计算结果可「采纳并写回」当前底稿 parsed_data，便于后续溯源和审计底稿引用。
      </template>
    </el-alert>

    <el-form :model="form" label-width="140px" size="small">
      <el-form-item label="员工人数" required>
        <el-input-number
          v-model="form.employee_count"
          :min="0"
          :max="999999"
          :step="10"
          controls-position="right"
          style="width: 180px"
        />
        <span class="gt-form-unit">人</span>
      </el-form-item>

      <el-form-item label="月均工资" required>
        <el-input-number
          v-model="form.avg_monthly_salary"
          :min="0"
          :max="999999999"
          :step="1000"
          :precision="2"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">元</span>
      </el-form-item>

      <el-form-item label="计提月数">
        <el-input-number
          v-model="form.months"
          :min="1"
          :max="12"
          controls-position="right"
          style="width: 120px"
        />
        <span class="gt-form-unit">月</span>
      </el-form-item>

      <el-divider>社保五险比例</el-divider>

      <el-form-item label="养老保险" required>
        <el-input-number
          v-model="form.pension"
          :min="0"
          :max="1"
          :step="0.01"
          :precision="4"
          controls-position="right"
          style="width: 160px"
        />
      </el-form-item>

      <el-form-item label="医疗保险" required>
        <el-input-number
          v-model="form.medical"
          :min="0"
          :max="1"
          :step="0.01"
          :precision="4"
          controls-position="right"
          style="width: 160px"
        />
      </el-form-item>

      <el-form-item label="失业保险">
        <el-input-number
          v-model="form.unemployment"
          :min="0"
          :max="1"
          :step="0.005"
          :precision="4"
          controls-position="right"
          style="width: 160px"
        />
      </el-form-item>

      <el-form-item label="工伤保险">
        <el-input-number
          v-model="form.work_injury"
          :min="0"
          :max="1"
          :step="0.002"
          :precision="4"
          controls-position="right"
          style="width: 160px"
        />
      </el-form-item>

      <el-form-item label="生育保险">
        <el-input-number
          v-model="form.maternity"
          :min="0"
          :max="1"
          :step="0.005"
          :precision="4"
          controls-position="right"
          style="width: 160px"
        />
      </el-form-item>

      <el-divider>其他计提比例</el-divider>

      <el-form-item label="住房公积金">
        <el-input-number
          v-model="form.housing_fund_rate"
          :min="0"
          :max="1"
          :step="0.01"
          :precision="4"
          controls-position="right"
          style="width: 160px"
        />
      </el-form-item>

      <el-form-item label="补充公积金">
        <el-input-number
          v-model="form.supplementary_fund_rate"
          :min="0"
          :max="1"
          :step="0.01"
          :precision="4"
          controls-position="right"
          style="width: 160px"
        />
      </el-form-item>

      <el-form-item label="福利费">
        <el-input-number
          v-model="form.welfare_rate"
          :min="0"
          :max="1"
          :step="0.01"
          :precision="4"
          controls-position="right"
          style="width: 160px"
        />
      </el-form-item>

      <el-form-item label="教育经费">
        <el-input-number
          v-model="form.education_rate"
          :min="0"
          :max="1"
          :step="0.005"
          :precision="4"
          controls-position="right"
          style="width: 160px"
        />
      </el-form-item>

      <el-form-item label="工会经费">
        <el-input-number
          v-model="form.union_rate"
          :min="0"
          :max="1"
          :step="0.005"
          :precision="4"
          controls-position="right"
          style="width: 160px"
        />
      </el-form-item>
    </el-form>

    <!-- 计算结果 -->
    <template v-if="result">
      <el-divider>计算结果</el-divider>
      <div class="payroll-result">
        <el-descriptions :column="3" size="small" border>
          <el-descriptions-item label="年度工资总额">¥ {{ formatAmount(result.annual_summary.total_salary) }}</el-descriptions-item>
          <el-descriptions-item label="年度社保合计">¥ {{ formatAmount(result.annual_summary.total_social_insurance) }}</el-descriptions-item>
          <el-descriptions-item label="年度总计提">¥ {{ formatAmount(result.annual_summary.grand_total) }}</el-descriptions-item>
        </el-descriptions>

        <el-table
          :data="result.monthly_breakdown"
          size="small"
          border
          style="margin-top: 12px"
          max-height="280"
        >
          <el-table-column label="月份" prop="month" width="60" align="center" />
          <el-table-column label="工资" width="120" align="right">
            <template #default="{ row }">¥ {{ formatAmount(row.salary) }}</template>
          </el-table-column>
          <el-table-column label="养老" width="100" align="right">
            <template #default="{ row }">¥ {{ formatAmount(row.pension) }}</template>
          </el-table-column>
          <el-table-column label="医疗" width="100" align="right">
            <template #default="{ row }">¥ {{ formatAmount(row.medical) }}</template>
          </el-table-column>
          <el-table-column label="公积金" width="100" align="right">
            <template #default="{ row }">¥ {{ formatAmount(row.housing_fund) }}</template>
          </el-table-column>
          <el-table-column label="月度合计" width="130" align="right">
            <template #default="{ row }">¥ {{ formatAmount(row.total) }}</template>
          </el-table-column>
        </el-table>

        <div v-if="result.warnings && result.warnings.length" class="payroll-warnings">
          <el-alert
            v-for="(w, i) in result.warnings"
            :key="i"
            type="warning"
            :title="w"
            show-icon
            :closable="false"
            style="margin-top: 8px"
          />
        </div>
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
  wpId: string
  targetSheet?: string
}
const props = withDefaults(defineProps<Props>(), {
  targetSheet: '',
})
const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'applied', sheet: string): void
}>()

interface MonthlyItem {
  month: number
  salary: string
  pension: string
  medical: string
  unemployment: string
  work_injury: string
  maternity: string
  housing_fund: string
  supplementary_fund: string
  welfare: string
  education: string
  union_fee: string
  total: string
}

interface PayrollResponse {
  monthly_breakdown: MonthlyItem[]
  annual_summary: {
    total_salary: string
    total_social_insurance: string
    total_housing_fund: string
    total_supplementary_fund: string
    total_welfare: string
    total_education: string
    total_union: string
    grand_total: string
  }
  warnings: string[]
  applied_to_sheet?: string | null
  applied_at?: string | null
}

const loading = ref(false)
const applying = ref(false)
const result = ref<PayrollResponse | null>(null)

const form = reactive({
  employee_count: 100,
  avg_monthly_salary: 15000,
  months: 12,
  pension: 0.16,
  medical: 0.095,
  unemployment: 0.005,
  work_injury: 0.004,
  maternity: 0.008,
  housing_fund_rate: 0.12,
  supplementary_fund_rate: 0,
  welfare_rate: 0.14,
  education_rate: 0.025,
  union_rate: 0.02,
})

const isFormValid = computed(() => {
  return form.employee_count >= 0 && form.avg_monthly_salary >= 0 && form.months >= 1
})

function formatAmount(s: string | number) {
  const n = Number(s)
  if (!Number.isFinite(n)) return String(s)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function buildRequestBody(applySheet?: string) {
  return {
    employee_count: form.employee_count,
    avg_monthly_salary: form.avg_monthly_salary,
    social_insurance_rates: {
      pension: form.pension,
      medical: form.medical,
      unemployment: form.unemployment,
      work_injury: form.work_injury,
      maternity: form.maternity,
    },
    housing_fund_rate: form.housing_fund_rate,
    supplementary_fund_rate: form.supplementary_fund_rate,
    welfare_rate: form.welfare_rate,
    education_rate: form.education_rate,
    union_rate: form.union_rate,
    months: form.months,
    apply_to_sheet: applySheet || null,
  }
}

async function onCalc() {
  loading.value = true
  try {
    const resp = await api.post<PayrollResponse>(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/j1/payroll-calc`,
      buildRequestBody(),
    )
    result.value = resp
    ElMessage.success(`计算完成：${resp.monthly_breakdown.length} 期月度明细`)
  } catch (e: any) {
    handleApiError(e, '薪酬计提计算')
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
    const resp = await api.post<PayrollResponse>(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/j1/payroll-calc`,
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
.payroll-result {
  margin-top: 8px;
}
.payroll-warnings {
  margin-top: 8px;
}
</style>
