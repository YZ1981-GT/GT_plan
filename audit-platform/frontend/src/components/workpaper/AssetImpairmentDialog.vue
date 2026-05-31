<template>
  <el-dialog
    :model-value="visible"
    title="🧮 AI 辅助减值分析（H-F12 DCF）"
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
        基于 DCF（折现现金流）模型计算资产组可收回金额，与账面价值比较判断是否需要计提减值。
        可收回金额 = max(公允价值−处置费用, 未来现金流现值)。
        当前 LLM 接入为 stub 实现，DCF 公式计算正确，AI 辅助分析待 wp_ai_service 升级后接入。
        <strong>「采纳并写回」会把分析结果写入当前底稿 parsed_data，便于后续溯源。</strong>
      </template>
    </el-alert>

    <el-form :model="form" label-width="140px" size="small">
      <el-form-item label="资产组 ID" required>
        <el-input
          v-model="form.asset_group_id"
          placeholder="如 CGU-001"
          style="width: 200px"
        />
      </el-form-item>

      <el-form-item label="账面价值" required>
        <el-input-number
          v-model="form.book_value"
          :min="0.01"
          :max="999999999999"
          :step="10000"
          :precision="2"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">元</span>
      </el-form-item>

      <el-form-item label="折现率" required>
        <el-input-number
          v-model="form.discount_rate"
          :min="0.001"
          :max="0.999"
          :step="0.01"
          :precision="4"
          controls-position="right"
          style="width: 160px"
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
        <span class="gt-form-unit">元（第 N 年末残余价值）</span>
      </el-form-item>

      <el-form-item label="公允价值减处置费用">
        <el-input-number
          v-model="form.fair_value_less_costs"
          :min="0"
          :max="999999999999"
          :step="10000"
          :precision="2"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">元（可选，若已知）</span>
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
            v-model="form.cash_flows[$index]"
            :min="0"
            :step="10000"
            :precision="2"
            controls-position="right"
            style="width: 200px"
          />
        </template>
      </el-table-column>
      <el-table-column label="" width="60">
        <template #default="{ $index }">
          <el-button
            v-if="form.cash_flows.length > 1"
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

    <el-button v-if="form.cash_flows.length < 10" size="small" plain @click="addCashFlowYear">
      + 添加年份
    </el-button>

    <!-- 计算结果 -->
    <template v-if="result">
      <el-divider>分析结果</el-divider>
      <div class="impairment-result">
        <el-alert
          :title="result.summary"
          :type="result.is_impaired ? 'warning' : 'success'"
          show-icon
          :closable="false"
          style="margin-bottom: 12px"
        />

        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="资产组">{{ result.asset_group_id }}</el-descriptions-item>
          <el-descriptions-item label="账面价值">¥ {{ formatAmount(result.book_value) }}</el-descriptions-item>
          <el-descriptions-item label="未来现金流现值">¥ {{ formatAmount(result.present_value_of_cash_flows) }}</el-descriptions-item>
          <el-descriptions-item label="公允价值减处置费用">
            {{ result.fair_value_less_costs ? '¥ ' + formatAmount(result.fair_value_less_costs) : '未提供' }}
          </el-descriptions-item>
          <el-descriptions-item label="可收回金额">
            <span class="amt-highlight">¥ {{ formatAmount(result.recoverable_amount) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="减值损失">
            <span :class="result.is_impaired ? 'amt-danger' : 'amt-safe'">
              ¥ {{ formatAmount(result.impairment_loss) }}
            </span>
          </el-descriptions-item>
        </el-descriptions>

        <el-table
          :data="result.dcf_details"
          size="small"
          border
          style="margin-top: 12px"
        >
          <el-table-column label="年份" prop="year" width="100" align="center" />
          <el-table-column label="现金流" width="140" align="right">
            <template #default="{ row }">¥ {{ formatAmount(row.cash_flow) }}</template>
          </el-table-column>
          <el-table-column label="折现因子" prop="discount_factor" width="120" align="right" />
          <el-table-column label="现值" width="140" align="right">
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
        🚀 计算分析
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
}
const props = withDefaults(defineProps<Props>(), {
  targetSheet: '',
})
const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'applied', sheet: string): void
}>()

interface DcfDetail {
  year: string | number
  cash_flow: string
  discount_factor: string
  present_value: string
}

interface ImpairmentResponse {
  asset_group_id: string
  book_value: string
  present_value_of_cash_flows: string
  fair_value_less_costs: string | null
  recoverable_amount: string
  impairment_loss: string
  is_impaired: boolean
  dcf_details: DcfDetail[]
  summary: string
  is_llm_stub: boolean
  applied_to_sheet?: string | null
}

const loading = ref(false)
const applying = ref(false)
const result = ref<ImpairmentResponse | null>(null)

const form = reactive({
  asset_group_id: 'CGU-001',
  book_value: 1000000,
  discount_rate: 0.10,
  terminal_value: 0,
  fair_value_less_costs: null as number | null,
  cash_flows: [200000, 220000, 240000, 260000, 280000] as number[],
})

const cashFlowRows = computed(() => form.cash_flows.map((_, i) => ({ index: i })))

function addCashFlowYear() {
  if (form.cash_flows.length < 10) {
    const last = form.cash_flows[form.cash_flows.length - 1] || 0
    form.cash_flows.push(last)
  }
}

function removeCashFlowYear(idx: number) {
  if (form.cash_flows.length > 1) {
    form.cash_flows.splice(idx, 1)
  }
}

const isFormValid = computed(() => {
  if (!form.asset_group_id) return false
  if (form.book_value <= 0) return false
  if (form.discount_rate <= 0 || form.discount_rate >= 1) return false
  if (form.cash_flows.length === 0) return false
  return form.cash_flows.some((cf) => cf > 0)
})

function formatAmount(s: string | number) {
  const n = Number(s)
  if (!Number.isFinite(n)) return String(s)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function buildRequestBody(applySheet?: string) {
  const body: Record<string, any> = {
    asset_group_id: form.asset_group_id,
    book_value: form.book_value,
    cash_flows: form.cash_flows.filter((cf) => cf >= 0),
    discount_rate: form.discount_rate,
    terminal_value: form.terminal_value,
  }
  if (form.fair_value_less_costs != null && form.fair_value_less_costs > 0) {
    body.fair_value_less_costs = form.fair_value_less_costs
  }
  if (applySheet) {
    body.apply_to_sheet = applySheet
  }
  return body
}

async function onAnalyze() {
  loading.value = true
  try {
    const resp = await api.post<ImpairmentResponse>(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/h1/impairment-analysis`,
      buildRequestBody(),
    )
    result.value = resp
    if (resp?.is_impaired) {
      ElMessage.warning(`分析完成：需计提减值 ¥${formatAmount(resp.impairment_loss)}`)
    } else {
      ElMessage.success('分析完成：无需计提减值')
    }
  } catch (e: any) {
    handleApiError(e, '减值分析')
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
    const resp = await api.post<ImpairmentResponse>(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/h1/impairment-analysis`,
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
.impairment-result {
  margin-top: 8px;
}
.amt-highlight {
  color: var(--el-color-primary);
  font-weight: 600;
}
.amt-danger {
  color: var(--el-color-danger);
  font-weight: 600;
}
.amt-safe {
  color: var(--el-color-success);
  font-weight: 600;
}
</style>
