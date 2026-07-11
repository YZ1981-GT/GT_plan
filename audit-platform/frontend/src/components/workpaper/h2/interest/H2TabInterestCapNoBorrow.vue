<template>
  <div class="h2-tab-interest-cap-no-borrow">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p><strong>无专门借款利息资本化：</strong>以一般借款的加权平均资本化率为基础，按累计资产支出加权平均数计算应予资本化的利息金额。</p>
      <p>公式：资本化金额 = 累计支出加权平均数 × 加权平均资本化率</p>
    </div>

    <!-- 分支选择器 -->
    <div class="branch-selector">
      <el-segmented v-model="activeBranch" :options="branchOptions" />
    </div>

    <!-- 借款明细 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>一般借款明细</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('interest-summary')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" circle @click="openReview('H2-10')">💬</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.loansNoBorrow.value" border stripe size="small" class="loan-table">
        <el-table-column prop="lender" label="贷款方" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.lender" size="small"
              @change="onLoanChange(row.rowId, 'lender', $event)" />
            <span v-else>{{ row.lender || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="principal" label="本金" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.principal" :controls="false"
              size="small" class="amt-input" @change="onLoanChange(row.rowId, 'principal', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.principal) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rate" label="年利率(%)" min-width="90" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.rate" :controls="false" :precision="4"
              size="small" class="amt-input" @change="onLoanChange(row.rowId, 'rate', $event)" />
            <span v-else>{{ row.rate?.toFixed(4) ?? '-' }}%</span>
          </template>
        </el-table-column>
        <el-table-column prop="startDate" label="起始日" min-width="100">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.startDate" type="date" size="small"
              value-format="YYYY-MM-DD" style="width:100%"
              @change="onLoanChange(row.rowId, 'startDate', $event)" />
            <span v-else>{{ row.startDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="endDate" label="到期日" min-width="100">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.endDate" type="date" size="small"
              value-format="YYYY-MM-DD" style="width:100%"
              @change="onLoanChange(row.rowId, 'endDate', $event)" />
            <span v-else>{{ row.endDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="days" label="天数" width="60" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="借款期间天数">{{ row.days ?? '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="利息" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="=本金×利率×天数/365">{{ fmtAmt(row.interest) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="handleRemoveLoan(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddLoan">+ 新增借款</el-button>
      </div>
    </el-card>

    <!-- 加权计算结果 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header"><span>加权计算</span></div>
      </template>
      <div class="calc-grid">
        <div class="calc-item">
          <span class="calc-label">加权平均资本化率：</span>
          <span class="calc-value formula-cell" title="=Σ(本金×利率×天数/365)/Σ(本金×天数/365)">
            {{ state.weightedCapRate.value?.toFixed(4) ?? '-' }}%
          </span>
        </div>
        <div class="calc-item">
          <span class="calc-label">累计支出加权平均数：</span>
          <span class="calc-value formula-cell" title="按支出时点加权计算">
            {{ fmtAmt(state.weightedExpenditure.value) }}
          </span>
        </div>
        <div class="calc-item">
          <span class="calc-label">资本化利息金额：</span>
          <span class="calc-value formula-cell highlight" title="=加权平均数×资本化率">
            {{ fmtAmt(state.capAmountNoBorrow.value) }}
          </span>
        </div>
        <div class="calc-item">
          <span class="calc-label">利息费用化金额：</span>
          <span class="calc-value formula-cell" title="=利息总额-资本化金额">
            {{ fmtAmt(state.expenseAmount.value) }}
          </span>
        </div>
      </div>
    </el-card>

    <!-- 累计支出明细 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header"><span>累计资产支出明细</span></div>
      </template>
      <el-table :data="state.expenditures.value" border stripe size="small" class="exp-table">
        <el-table-column prop="month" label="支出日期/月份" min-width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.month" type="date" size="small"
              value-format="YYYY-MM-DD" style="width:100%"
              @change="onExpChange(row.rowId, 'month', $event)" />
            <span v-else>{{ row.month || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="amount" label="支出金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.amount" :controls="false"
              size="small" class="amt-input" @change="onExpChange(row.rowId, 'amount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="days" label="占用天数" min-width="90" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.days" :controls="false"
              size="small" class="amt-input" @change="onExpChange(row.rowId, 'days', $event)" />
            <span v-else>{{ row.days ?? '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="加权金额" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="=支出金额×占用天数">{{ fmtAmt(row.weightedAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="handleRemoveExp(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddExp">+ 新增支出</el-button>
      </div>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>无专门借款时：资本化金额=累计支出加权平均数×加权平均资本化率</li>
        <li>加权平均资本化率=Σ(本金×利率×天数)/Σ(本金×天数)</li>
        <li>累计支出加权平均数=Σ(各笔支出×支出日至期末天数/365)</li>
        <li>资本化利息不得超过当期实际利息总额</li>
        <li>分支选择器：如有专门借款请切换到H2-11</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabInterestCapNoBorrow.vue — H2-10 利息资本化(无专门借款)
 * 28列78行(12公式) + 分支选择器 + 借款明细 + 加权计算
 * Spec: Task 4.13 | Requirements: 10.1-10.4, 10.6-10.10
 */
import { ref, inject, toRef, computed } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH2InterestCap } from '../../composables/useH2InterestCap'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const activeBranch = ref('noBorrow')
const branchOptions = [
  { label: '无专门借款(H2-10)', value: 'noBorrow' },
  { label: '有专门借款(H2-11)', value: 'withBorrow' },
]

const state = useH2InterestCap({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  onPublishEvent(event: string, payload: any) {
    // Task 6.7 — publish 'h2:interest-capitalized' 利息资本化联动L(财务费用)
    console.log('[H2-10] publish', event, payload)
    http.post(`/api/projects/${props.projectId}/events/publish`, {
      event_type: event,
      payload,
    }, { _silent: true } as any).catch(() => { /* best effort */ })
  },
})

function onLoanChange(rowId: string, field: string, value: any) {
  state.updateLoanNoBorrow(rowId, field, value)
}

function onExpChange(rowId: string, field: string, value: any) {
  state.updateExpenditure(rowId, field, value)
}

function handleAddLoan() { state.addLoanNoBorrow() }
function handleRemoveLoan(rowId: string) { state.removeLoanNoBorrow(rowId) }
function handleAddExp() { state.addExpenditure() }
function handleRemoveExp(rowId: string) { state.removeExpenditure(rowId) }

function handleAiGenerate(section: string) {
  console.log('AI generate H2-10:', section)
}

function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h2-tab-interest-cap-no-borrow { padding: 16px; font-size: 13px; }
.methodology-context {
  border-left: 3px solid #f0a020; background: #fdf8e8;
  padding: 12px 16px; margin-bottom: 16px; border-radius: 4px; font-size: 13px;
}
.branch-selector { margin-bottom: 16px; }
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.loan-table, .exp-table { font-size: 13px; }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.calc-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.calc-item { display: flex; align-items: center; gap: 8px; }
.calc-label { font-weight: 500; }
.calc-value { font-weight: 600; font-size: 14px; }
.calc-value.highlight { color: var(--el-color-primary); font-size: 16px; }
.add-row-bar { margin-top: 12px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
