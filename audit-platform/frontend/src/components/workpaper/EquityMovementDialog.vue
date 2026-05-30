<template>
  <el-dialog
    :model-value="visible"
    title="📊 权益变动表计算（M-F7）"
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
        输入权益各科目期初余额及本期变动项（净利润、股利、盈余公积、资本公积变动、OCI 变动），
        自动计算 6 列期末余额及变动汇总。计算结果可「采纳并写回」当前底稿。
      </template>
    </el-alert>

    <!-- is_llm_stub 指示器 -->
    <el-tag v-if="isLlmStub !== null" :type="isLlmStub ? 'warning' : 'success'" size="small" style="margin-bottom: 12px">
      {{ isLlmStub ? '⚠️ Stub 模式（待 AI 服务接入）' : '✅ AI 服务已启用' }}
    </el-tag>

    <el-form :model="form" label-width="140px" size="small">
      <el-divider content-position="left">期初余额（6 列）</el-divider>

      <el-form-item label="实收资本（股本）" required>
        <el-input-number
          v-model="form.paid_in_capital"
          :precision="2"
          :step="10000"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">元</span>
      </el-form-item>

      <el-form-item label="资本公积" required>
        <el-input-number
          v-model="form.capital_reserve"
          :precision="2"
          :step="10000"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">元</span>
      </el-form-item>

      <el-form-item label="盈余公积" required>
        <el-input-number
          v-model="form.surplus_reserve"
          :precision="2"
          :step="10000"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">元</span>
      </el-form-item>

      <el-form-item label="未分配利润" required>
        <el-input-number
          v-model="form.retained_earnings"
          :precision="2"
          :step="10000"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">元</span>
      </el-form-item>

      <el-form-item label="其他综合收益">
        <el-input-number
          v-model="form.oci"
          :precision="2"
          :step="1000"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">元</span>
      </el-form-item>

      <el-form-item label="其他权益工具">
        <el-input-number
          v-model="form.other_equity_instruments"
          :precision="2"
          :step="1000"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">元</span>
      </el-form-item>

      <el-divider content-position="left">本期变动项</el-divider>

      <el-form-item label="本期净利润" required>
        <el-input-number
          v-model="form.net_profit"
          :precision="2"
          :step="10000"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">元（负数=亏损）</span>
      </el-form-item>

      <el-form-item label="本期分配股利">
        <el-input-number
          v-model="form.dividends"
          :min="0"
          :precision="2"
          :step="10000"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">元</span>
      </el-form-item>

      <el-form-item label="本期提取盈余公积">
        <el-input-number
          v-model="form.surplus_reserve_change"
          :min="0"
          :precision="2"
          :step="1000"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">元</span>
      </el-form-item>

      <el-form-item label="资本公积变动">
        <el-input-number
          v-model="form.capital_reserve_changes"
          :precision="2"
          :step="1000"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">元（正=增加）</span>
      </el-form-item>

      <el-form-item label="OCI 变动">
        <el-input-number
          v-model="form.oci_changes"
          :precision="2"
          :step="1000"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">元</span>
      </el-form-item>
    </el-form>

    <!-- 计算结果 -->
    <template v-if="result">
      <el-divider content-position="left">期末余额</el-divider>
      <el-descriptions :column="2" size="small" border>
        <el-descriptions-item label="实收资本">
          <span class="gt-amt">¥ {{ formatAmount(result.closing_balances.paid_in_capital) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="资本公积">
          <span class="gt-amt">¥ {{ formatAmount(result.closing_balances.capital_reserve) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="盈余公积">
          <span class="gt-amt">¥ {{ formatAmount(result.closing_balances.surplus_reserve) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="未分配利润">
          <span class="gt-amt">¥ {{ formatAmount(result.closing_balances.retained_earnings) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="其他综合收益">
          <span class="gt-amt">¥ {{ formatAmount(result.closing_balances.oci) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="其他权益工具">
          <span class="gt-amt">¥ {{ formatAmount(result.closing_balances.other_equity_instruments) }}</span>
        </el-descriptions-item>
      </el-descriptions>

      <el-divider content-position="left">变动汇总（6 列）</el-divider>
      <el-descriptions :column="2" size="small" border>
        <el-descriptions-item label="实收资本变动">
          <span class="gt-amt">{{ formatChange(result.movement_summary.paid_in_capital_change) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="资本公积变动">
          <span class="gt-amt">{{ formatChange(result.movement_summary.capital_reserve_change) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="盈余公积变动">
          <span class="gt-amt">{{ formatChange(result.movement_summary.surplus_reserve_change) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="未分配利润变动">
          <span class="gt-amt">{{ formatChange(result.movement_summary.retained_earnings_change) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="OCI 变动">
          <span class="gt-amt">{{ formatChange(result.movement_summary.oci_change) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="其他权益工具变动">
          <span class="gt-amt">{{ formatChange(result.movement_summary.other_equity_instruments_change) }}</span>
        </el-descriptions-item>
      </el-descriptions>
    </template>

    <template #footer>
      <el-button @click="emit('update:visible', false)">关闭</el-button>
      <el-button
        type="primary"
        :loading="loading"
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
import { reactive, ref, watch } from 'vue'
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

interface ClosingBalancesResult {
  paid_in_capital: string
  capital_reserve: string
  surplus_reserve: string
  retained_earnings: string
  oci: string
  other_equity_instruments: string
}

interface MovementSummaryResult {
  paid_in_capital_change: string
  capital_reserve_change: string
  surplus_reserve_change: string
  retained_earnings_change: string
  oci_change: string
  other_equity_instruments_change: string
}

interface EquityMovementResult {
  closing_balances: ClosingBalancesResult
  movement_summary: MovementSummaryResult
  is_llm_stub: boolean
  applied_to_sheet?: string | null
  applied_at?: string | null
}

const loading = ref(false)
const applying = ref(false)
const result = ref<EquityMovementResult | null>(null)
const isLlmStub = ref<boolean | null>(null)

const form = reactive({
  // opening_balances
  paid_in_capital: 0,
  capital_reserve: 0,
  surplus_reserve: 0,
  retained_earnings: 0,
  oci: 0,
  other_equity_instruments: 0,
  // changes
  net_profit: 0,
  dividends: 0,
  surplus_reserve_change: 0,
  capital_reserve_changes: 0,
  oci_changes: 0,
})

function formatAmount(s: string | number) {
  const n = Number(s)
  if (!Number.isFinite(n)) return String(s)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatChange(s: string | number) {
  const n = Number(s)
  if (!Number.isFinite(n)) return String(s)
  const prefix = n > 0 ? '+' : ''
  return prefix + n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function buildRequestBody(applySheet?: string) {
  return {
    opening_balances: {
      paid_in_capital: form.paid_in_capital,
      capital_reserve: form.capital_reserve,
      surplus_reserve: form.surplus_reserve,
      retained_earnings: form.retained_earnings,
      oci: form.oci,
      other_equity_instruments: form.other_equity_instruments,
    },
    net_profit: form.net_profit,
    dividends: form.dividends,
    surplus_reserve: form.surplus_reserve_change,
    capital_reserve_changes: form.capital_reserve_changes,
    oci_changes: form.oci_changes,
    apply_to_sheet: applySheet || null,
  }
}

async function onCalc() {
  loading.value = true
  try {
    const resp = await api.post<EquityMovementResult>(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/m6/equity-movement`,
      buildRequestBody(),
    )
    result.value = resp
    isLlmStub.value = resp.is_llm_stub
    ElMessage.success('权益变动计算完成')
  } catch (e: any) {
    handleApiError(e, '权益变动计算')
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
    const resp = await api.post<EquityMovementResult>(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/m6/equity-movement`,
      buildRequestBody(props.targetSheet),
    )
    result.value = resp
    isLlmStub.value = resp.is_llm_stub
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
  if (!v) {
    result.value = null
    isLlmStub.value = null
  }
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
