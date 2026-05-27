<template>
  <el-dialog
    :model-value="visible"
    :title="dialogTitle"
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
        I 循环摊销自动测算（直线法 / 工作量法）。计算结果可「采纳并写回」当前底稿
        parsed_data，便于后续溯源和审计底稿引用。
      </template>
    </el-alert>

    <el-form :model="form" label-width="140px" size="small">
      <el-form-item label="摊销方法" required>
        <el-radio-group v-model="form.method">
          <el-radio value="straight_line">直线法 / 剩余年限法</el-radio>
          <el-radio value="units_of_production">工作量法</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="原值" required>
        <el-input-number
          v-model="form.original_cost"
          :min="0"
          :max="999999999999"
          :step="10000"
          :precision="2"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">元</span>
      </el-form-item>

      <el-form-item label="残值率" required>
        <el-input-number
          v-model="form.residual_rate"
          :min="0"
          :max="1"
          :step="0.01"
          :precision="4"
          controls-position="right"
          style="width: 160px"
        />
        <span class="gt-form-unit">（0~1，无形资产通常 0）</span>
      </el-form-item>

      <el-form-item label="使用年限（月）" required>
        <el-input-number
          v-model="form.useful_life_months"
          :min="1"
          :max="600"
          :step="12"
          controls-position="right"
          style="width: 160px"
        />
        <span class="gt-form-unit">月</span>
      </el-form-item>

      <el-form-item label="起始月份">
        <el-input-number
          v-model="form.start_month"
          :min="1"
          :max="12"
          controls-position="right"
          style="width: 120px"
        />
      </el-form-item>

      <el-form-item label="已计提月数">
        <el-input-number
          v-model="form.already_amortized_months"
          :min="0"
          :max="form.useful_life_months"
          controls-position="right"
          style="width: 160px"
        />
        <span class="gt-form-unit">月（续提场景）</span>
      </el-form-item>

      <!-- 工作量法专用字段 -->
      <template v-if="form.method === 'units_of_production'">
        <el-divider>工作量法参数</el-divider>
        <el-form-item label="总工作量" required>
          <el-input-number
            v-model="form.total_units"
            :min="0.01"
            :step="100"
            :precision="2"
            controls-position="right"
            style="width: 200px"
          />
        </el-form-item>
        <el-form-item label="当期工作量" required>
          <el-input-number
            v-model="form.current_period_units"
            :min="0"
            :step="10"
            :precision="2"
            controls-position="right"
            style="width: 200px"
          />
        </el-form-item>
      </template>
    </el-form>

    <!-- 计算结果 -->
    <template v-if="result">
      <el-divider>计算结果</el-divider>
      <div class="amortization-result">
        <el-descriptions :column="3" size="small" border>
          <el-descriptions-item label="摊销方法">{{ methodLabel(result.method) }}</el-descriptions-item>
          <el-descriptions-item label="累计摊销">¥ {{ formatAmount(result.total_amortization) }}</el-descriptions-item>
          <el-descriptions-item label="剩余账面净值">¥ {{ formatAmount(result.remaining_book_value) }}</el-descriptions-item>
        </el-descriptions>

        <el-table
          :data="schedulePreview"
          size="small"
          border
          style="margin-top: 12px"
          max-height="240"
        >
          <el-table-column label="月份" prop="month" width="80" align="center" />
          <el-table-column label="当月摊销" width="140" align="right">
            <template #default="{ row }">¥ {{ formatAmount(row.amortization) }}</template>
          </el-table-column>
          <el-table-column label="累计摊销" width="140" align="right">
            <template #default="{ row }">¥ {{ formatAmount(row.accumulated) }}</template>
          </el-table-column>
        </el-table>

        <div v-if="result.monthly_schedule.length > 12" class="schedule-note">
          显示前 12 条，共 {{ result.monthly_schedule.length }} 条月度记录
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
  /** "I1" 或 "I4" — 决定调用哪个 endpoint */
  section: 'I1' | 'I4'
  /** 当前活动 sheet 名（用于「采纳并写回」按钮） */
  targetSheet?: string
}
const props = withDefaults(defineProps<Props>(), {
  targetSheet: '',
})
const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'applied', sheet: string): void
}>()

interface ScheduleItem {
  month: number
  // 后端返回 amortization 字段（H-F11 引擎已升级支持 term='amortization' 参数，
  // 见 backend/app/routers/wp_h_depreciation.py / Sprint 4 Task 4.8）
  amortization: string
  accumulated: string
}

interface AmortizationResponse {
  method: string
  monthly_schedule: ScheduleItem[]
  total_amortization: string
  remaining_book_value: string
  applied_to_sheet?: string | null
}

const loading = ref(false)
const applying = ref(false)
const result = ref<AmortizationResponse | null>(null)

const form = reactive({
  method: 'straight_line' as 'straight_line' | 'units_of_production',
  original_cost: 100000,
  residual_rate: 0,
  useful_life_months: 120,
  start_month: 1,
  already_amortized_months: 0,
  total_units: 10000,
  current_period_units: 500,
})

const dialogTitle = computed(() => {
  return props.section === 'I1'
    ? '🧮 I1 无形资产摊销自动测算'
    : '🧮 I4 长期待摊费用摊销自动测算'
})

const isFormValid = computed(() => {
  if (form.original_cost <= 0) return false
  if (form.useful_life_months <= 0) return false
  if (form.method === 'units_of_production') {
    if (!form.total_units || form.total_units <= 0) return false
    if (form.current_period_units == null || form.current_period_units < 0) return false
  }
  return true
})

const schedulePreview = computed(() => {
  if (!result.value) return []
  return result.value.monthly_schedule.slice(0, 12)
})

function methodLabel(m: string) {
  const map: Record<string, string> = {
    straight_line: '直线法 / 剩余年限法',
    units_of_production: '工作量法',
  }
  return map[m] || m
}

function formatAmount(s: string | number) {
  const n = Number(s)
  if (!Number.isFinite(n)) return String(s)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function endpointPath(): string {
  const seg = props.section.toLowerCase() // 'i1' | 'i4'
  return `/api/projects/${props.projectId}/workpapers/${props.wpId}/${seg}/amortization-calc`
}

function buildBody(applyToSheet?: string): Record<string, any> {
  const body: Record<string, any> = {
    method: form.method,
    original_cost: form.original_cost,
    residual_rate: form.residual_rate,
    useful_life_months: form.useful_life_months,
    start_month: form.start_month,
    already_amortized_months: form.already_amortized_months,
  }
  if (form.method === 'units_of_production') {
    body.total_units = form.total_units
    body.current_period_units = form.current_period_units
  }
  if (applyToSheet) body.apply_to_sheet = applyToSheet
  return body
}

async function onCalc() {
  loading.value = true
  try {
    const resp = await api.post<AmortizationResponse>(endpointPath(), buildBody())
    result.value = resp
    const total = resp?.monthly_schedule?.length || 0
    ElMessage.success(`计算完成：${methodLabel(resp.method)}，共 ${total} 期`)
  } catch (e: any) {
    handleApiError(e, '摊销计算')
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
    const resp = await api.post<AmortizationResponse>(
      endpointPath(),
      buildBody(props.targetSheet),
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

// 重置 result 在弹窗关闭时
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
.amortization-result {
  margin-top: 8px;
}
.schedule-note {
  margin-top: 8px;
  text-align: center;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
