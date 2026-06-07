<template>
  <el-dialog
    v-model="visible"
    title="数据质量检查"
    width="720px"
    :close-on-click-modal="false"
    @close="onClose"
  >
    <!-- Loading -->
    <div v-if="loading" style="text-align: center; padding: 40px 0">
      <el-icon class="is-loading" :size="32"><Loading /></el-icon>
      <p style="margin-top: 12px; color: var(--gt-color-info)">正在执行数据质量检查...</p>
    </div>

    <!-- Results -->
    <div v-else-if="result">
      <!-- Summary bar -->
      <div class="dq-summary">
        <span class="dq-summary__item dq-summary__item--passed">
          🟢 通过 {{ result.summary.passed }}
        </span>
        <span class="dq-summary__item dq-summary__item--warning">
          🟡 警告 {{ result.summary.warning }}
        </span>
        <span class="dq-summary__item dq-summary__item--blocking">
          🔴 阻断 {{ result.summary.blocking }}
        </span>
        <span class="dq-summary__total">
          共 {{ result.total_accounts }} 个科目
        </span>
      </div>

      <!-- Check results grouped -->
      <div class="dq-checks">
        <div
          v-for="checkName in result.checks_run"
          :key="checkName"
          class="dq-check-item"
          :class="`dq-check-item--${result.results[checkName]?.status}`"
        >
          <div class="dq-check-header">
            <span class="dq-check-icon">{{ getStatusIcon(result.results[checkName]?.status) }}</span>
            <span class="dq-check-title">{{ getCheckTitle(checkName) }}</span>
            <el-tag
              :type="getTagType(result.results[checkName]?.status)"
              size="small"
              effect="plain"
            >
              {{ getStatusLabel(result.results[checkName]?.status) }}
            </el-tag>
          </div>
          <div class="dq-check-message">
            {{ result.results[checkName]?.message }}
          </div>

          <!-- Differences detail (for balance_vs_ledger) -->
          <div
            v-if="checkName === 'balance_vs_ledger' && result.results[checkName]?.details?.differences?.length"
            class="dq-check-details"
          >
            <el-collapse>
              <el-collapse-item title="查看差异科目明细">
                <el-table
                  :data="result.results[checkName].details.differences"
                  size="small"
                  max-height="240"
                  stripe
                >
                  <el-table-column prop="account_code" label="科目编码" width="100" />
                  <el-table-column prop="account_name" label="科目名称" width="140" />
                  <el-table-column prop="closing_balance" label="期末余额" width="120" align="right" />
                  <el-table-column prop="expected_closing" label="预期期末" width="120" align="right" />
                  <el-table-column prop="difference" label="差异" width="100" align="right">
                    <template #default="{ row }">
                      <span style="color: var(--gt-color-coral); font-weight: 600">{{ row.difference }}</span>
                    </template>
                  </el-table-column>
                </el-table>
              </el-collapse-item>
            </el-collapse>
          </div>

          <!-- Mapping details -->
          <div
            v-if="checkName === 'mapping_completeness' && result.results[checkName]?.details?.completion_rate != null"
            class="dq-check-details"
          >
            <el-progress
              :percentage="result.results[checkName].details.completion_rate"
              :color="result.results[checkName].details.completion_rate >= 80 ? '#67c23a' : '#e6a23c'"
              :stroke-width="8"
              style="margin-top: 8px"
            />
          </div>

          <!-- 5.4: 借贷平衡检查打开统一诊断弹窗入口 -->
          <div
            v-if="isBalanceCheck(checkName) && result.results[checkName]?.status !== 'passed'"
            class="dq-check-details"
          >
            <el-button type="primary" size="small" link @click="openBalanceDiag(checkName)">
              查看诊断详情
            </el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- Error state -->
    <div v-else-if="error" style="text-align: center; padding: 40px 0">
      <p style="color: var(--gt-color-coral)">{{ error }}</p>
    </div>

    <template #footer>
      <el-button @click="onClose">关闭</el-button>
      <el-button type="primary" @click="runCheck" :loading="loading">重新检查</el-button>
    </template>
  </el-dialog>

  <!-- 5.4: 统一诊断弹窗（借贷平衡检查详情） -->
  <BalanceDiagnosticsDialog
    v-if="balanceDiagResult"
    v-model="balanceDiagVisible"
    :result="balanceDiagResult"
    @rerun="runCheck"
  />
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import BalanceDiagnosticsDialog from '@/components/diagnostics/BalanceDiagnosticsDialog.vue'
import type { BalanceDiagnosticsResult, Caliber } from '@/types/balance-diagnostics'
import { CALIBER_LABELS } from '@/types/balance-diagnostics'

const props = defineProps<{
  modelValue: boolean
  projectId: string
  year: number
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const visible = ref(props.modelValue)
const loading = ref(false)
const error = ref('')
const result = ref<any>(null)

watch(() => props.modelValue, (val) => {
  visible.value = val
  if (val && !result.value) {
    runCheck()
  }
})

watch(visible, (val) => {
  emit('update:modelValue', val)
})

function onClose() {
  visible.value = false
}

async function runCheck() {
  loading.value = true
  error.value = ''
  try {
    // api.get 已经直接返回业务数据,不需要二次解构 .data
    const data = await api.get(`/api/projects/${props.projectId}/data-quality/check`, {
      params: { checks: 'all', year: props.year },
    })
    result.value = data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '检查失败'
  } finally {
    loading.value = false
  }
}

const CHECK_TITLES: Record<string, string> = {
  debit_credit_balance: '借贷平衡检查',
  balance_vs_ledger: '余额表 vs 序时账一致性',
  mapping_completeness: '科目映射完整性',
  report_balance: '报表平衡检查（资产=负债+权益）',
  profit_reconciliation: '利润表勾稽检查',
}

// ─── 5.4: 统一诊断弹窗 ─────────────────────────────────────────────

const balanceDiagVisible = ref(false)
const balanceDiagResult = ref<BalanceDiagnosticsResult | null>(null)

const BALANCE_CHECKS = ['debit_credit_balance', 'balance_vs_ledger', 'report_balance']

function isBalanceCheck(checkName: string): boolean {
  return BALANCE_CHECKS.includes(checkName)
}

const CHECK_TO_CALIBER: Record<string, Caliber> = {
  debit_credit_balance: 'ledger_debit_credit',
  balance_vs_ledger: 'balance_vs_ledger',
  report_balance: 'balance_sheet_equation',
}

function openBalanceDiag(checkName: string) {
  const checkResult = result.value?.results?.[checkName]
  if (!checkResult) return
  const caliber: Caliber = CHECK_TO_CALIBER[checkName] || 'ledger_debit_credit'
  balanceDiagResult.value = {
    caliber,
    caliber_label: CALIBER_LABELS[caliber],
    status: checkResult.status || 'warning',
    difference: checkResult.details?.difference || 0,
    debit_total: checkResult.details?.debit_total || 0,
    credit_total: checkResult.details?.credit_total || 0,
    likely_causes: [{
      cause_code: 'source_data_unbalanced',
      severity: checkResult.status === 'blocking' ? 5 : 3,
      confidence: 0.7,
      description: checkResult.message || '借贷不平衡',
      evidence: {},
    }],
    unmatched_accounts: [],
    sign_anomalies: [],
    sign_anomalies_unavailable: false,
    top_contributors: checkResult.details?.differences || [],
    jump_targets: [],
    data_sources: {},
  }
  balanceDiagVisible.value = true
}

function getCheckTitle(name: string): string {
  return CHECK_TITLES[name] || name
}

function getStatusIcon(status: string): string {
  if (status === 'passed') return '🟢'
  if (status === 'warning') return '🟡'
  if (status === 'blocking') return '🔴'
  return '⚪'
}

function getStatusLabel(status: string): string {
  if (status === 'passed') return '通过'
  if (status === 'warning') return '警告'
  if (status === 'blocking') return '阻断'
  return '未知'
}

function getTagType(status: string): 'success' | 'warning' | 'danger' | 'info' {
  if (status === 'passed') return 'success'
  if (status === 'warning') return 'warning'
  if (status === 'blocking') return 'danger'
  return 'info'
}
</script>

<style scoped>
.dq-summary {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  background: var(--gt-bg-subtle);
  border-radius: 8px;
  margin-bottom: 16px;
}

.dq-summary__item {
  font-size: var(--gt-font-size-sm);
  font-weight: 500;
}

.dq-summary__total {
  margin-left: auto;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-info);
}

.dq-checks {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dq-check-item {
  padding: 12px 16px;
  border-radius: 8px;
  border: 1px solid var(--gt-color-border-lighter);
  transition: border-color 0.2s;
}

.dq-check-item--passed {
  border-left: 3px solid var(--gt-color-success);
}

.dq-check-item--warning {
  border-left: 3px solid var(--gt-color-wheat);
  background: var(--gt-bg-warning);
}

.dq-check-item--blocking {
  border-left: 3px solid var(--gt-color-coral);
  background: var(--gt-bg-danger);
}

.dq-check-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dq-check-icon {
  font-size: var(--gt-font-size-md);
}

.dq-check-title {
  font-size: var(--gt-font-size-sm);
  font-weight: 500;
  flex: 1;
}

.dq-check-message {
  margin-top: 6px;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-regular);
  padding-left: 24px;
}

.dq-check-details {
  margin-top: 8px;
  padding-left: 24px;
}
</style>
