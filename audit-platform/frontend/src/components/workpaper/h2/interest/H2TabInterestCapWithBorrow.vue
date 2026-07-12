<template>
  <div class="h2-tab-interest-cap-with-borrow">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p><strong>有专门借款利息资本化：</strong></p>
      <p>① 专门借款资本化金额 = 专门借款利息费用 - 闲置资金收益</p>
      <p>② 超出专门借款部分占用一般借款的，按一般借款加权平均利率计算补充资本化金额</p>
      <p>③ 合计资本化金额 = 专门借款资本化 + 一般借款补充资本化</p>
    </div>

    <!-- 专门借款（汇总） -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>一、专门借款</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('special-loan')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" circle @click="openReview('H2-11')">💬</el-button>
          </div>
        </div>
      </template>

      <div class="calc-grid">
        <div class="calc-item">
          <span class="calc-label">专门借款金额：</span>
          <el-input-number v-model="state.specialLoanData.value.specialLoanAmount" :controls="false"
            size="small" :disabled="isReadonly" @change="onSpecialChange('specialLoanAmount', $event)" />
        </div>
        <div class="calc-item">
          <span class="calc-label">专门借款利息费用：</span>
          <el-input-number v-model="state.specialLoanData.value.specialInterest" :controls="false"
            size="small" :disabled="isReadonly" @change="onSpecialChange('specialInterest', $event)" />
        </div>
        <div class="calc-item">
          <span class="calc-label">闲置资金收益：</span>
          <el-input-number v-model="state.specialLoanData.value.idleIncome" :controls="false"
            size="small" :disabled="isReadonly" @change="onSpecialChange('idleIncome', $event)" />
        </div>
        <div class="calc-item">
          <span class="calc-label">超出部分加权支出：</span>
          <el-input-number v-model="state.specialLoanData.value.excessWeightedExp" :controls="false"
            size="small" :disabled="isReadonly" @change="onSpecialChange('excessWeightedExp', $event)" />
        </div>
        <div class="calc-item total-item">
          <span class="calc-label">专门借款资本化金额：</span>
          <span class="calc-value formula-cell highlight" title="=专门借款利息-闲置资金收益">
            {{ fmtAmt(state.specialLoanCap.value) }}
          </span>
        </div>
      </div>
    </el-card>

    <!-- 一般借款补充 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header"><span>二、一般借款补充资本化</span></div>
      </template>

      <el-table :data="state.loansWithBorrow.value" border stripe size="small" class="loan-table">
        <el-table-column prop="lender" label="贷款方" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.lender" size="small"
              @change="onGeneralChange(row.rowId, 'lender', $event)" />
            <span v-else>{{ row.lender || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="principal" label="本金" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.principal" :controls="false"
              size="small" class="amt-input" @change="onGeneralChange(row.rowId, 'principal', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.principal) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rate" label="年利率(%)" min-width="90" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.rate" :controls="false" :precision="4"
              size="small" class="amt-input" @change="onGeneralChange(row.rowId, 'rate', $event)" />
            <span v-else>{{ row.rate?.toFixed(4) ?? '-' }}%</span>
          </template>
        </el-table-column>
        <el-table-column prop="days" label="天数" width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.days" :controls="false"
              size="small" class="amt-input" @change="onGeneralChange(row.rowId, 'days', $event)" />
            <span v-else>{{ row.days ?? '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="利息" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="=本金×利率×天数/365">{{ fmtAmt(row.interest) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="handleRemoveGeneral(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddGeneral">+ 新增一般借款</el-button>
      </div>
    </el-card>

    <!-- 合计汇总 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header"><span>三、合计</span></div>
      </template>
      <div class="calc-grid">
        <div class="calc-item">
          <span class="calc-label">专门借款资本化小计：</span>
          <span class="calc-value formula-cell" title="专门借款利息-闲置收益">
            {{ fmtAmt(state.specialLoanCap.value) }}
          </span>
        </div>
        <div class="calc-item">
          <span class="calc-label">超出部分加权支出：</span>
          <span class="calc-value formula-cell" title="超出专门借款的累计支出加权平均数">
            {{ fmtAmt(state.specialLoanData.value.excessWeightedExp) }}
          </span>
        </div>
        <div class="calc-item">
          <span class="calc-label">一般借款加权资本化率：</span>
          <span class="calc-value formula-cell" title="一般借款加权平均利率">
            {{ state.generalCapRate.value != null ? state.generalCapRate.value.toFixed(4) + '%' : '-' }}
          </span>
        </div>
        <div class="calc-item">
          <span class="calc-label">一般借款补充资本化：</span>
          <span class="calc-value formula-cell" title="=超出加权×一般利率">
            {{ fmtAmt(state.generalLoanSupp.value) }}
          </span>
        </div>
        <div class="calc-item total-item">
          <span class="calc-label">资本化利息合计：</span>
          <span class="calc-value formula-cell highlight" title="=专门+一般补充">
            {{ fmtAmt(state.totalCapAmount.value) }}
          </span>
        </div>
        <div class="calc-item">
          <span class="calc-label">利息费用化金额：</span>
          <span class="calc-value formula-cell" title="=利息总额-资本化合计">
            {{ fmtAmt(state.totalExpenseAmount.value) }}
          </span>
        </div>
      </div>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>专门借款资本化=利息费用-闲置资金投资收益</li>
        <li>超出专门借款部分的支出，占用一般借款时按一般借款利率补充资本化</li>
        <li>一般借款加权资本化率=Σ(本金×利率×天数)/Σ(本金×天数)</li>
        <li>资本化合计=专门借款资本化+一般借款补充资本化</li>
        <li>资本化利息不得超过当期实际利息总额(上限校验)</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabInterestCapWithBorrow.vue — H2-11 有专门借款利息资本化
 * 专门借款(汇总)+一般借款补充(动态行)+合计
 * Spec: Task 4.14 | Requirements: 10.1, 10.3, 10.5-10.10
 */
import { inject, toRef, computed } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH2InterestCap } from '../../composables/useH2InterestCap'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const state = useH2InterestCap({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  onPublishEvent(event: string, payload: any) {
    // Task 6.7 — publish 'h2:interest-capitalized' 利息资本化联动L(财务费用)
    console.log('[H2-11] publish', event, payload)
    http.post(`/api/projects/${props.projectId}/events/publish`, {
      event_type: event,
      payload,
    }, { _silent: true } as any).catch(() => { /* best effort */ })
  },
})

const isReadonly = computed(() => props.isReadonly)

function onSpecialChange(field: string, value: any) {
  state.updateSpecialLoanData(field as any, Number(value) || 0)
}

function onGeneralChange(rowId: string, field: string, value: any) {
  state.updateLoanWithBorrow(rowId, field, value)
}

function handleAddGeneral() { state.addLoanWithBorrow() }
function handleRemoveGeneral(rowId: string) { state.removeLoanWithBorrow(rowId) }

function handleAiGenerate(section: string) {
  console.log('AI generate H2-11:', section)
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
.h2-tab-interest-cap-with-borrow { padding: 16px; font-size: var(--wp-font-size, 13px); }
.methodology-context {
  border-left: 3px solid #f0a020; background: #fdf8e8;
  padding: 12px 16px; margin-bottom: 16px; border-radius: 4px; font-size: var(--wp-font-size, 13px);
}
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.loan-table { font-size: var(--wp-font-size, 13px); }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.formula-cell.highlight { color: var(--el-color-primary); font-weight: 600; }
.calc-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.calc-item { display: flex; align-items: center; gap: 8px; }
.calc-item.total-item { grid-column: span 2; padding: 8px; background: var(--el-fill-color-light); border-radius: 4px; }
.calc-label { font-weight: 500; }
.calc-value { font-weight: 600; font-size: 14px; }
.calc-value.highlight { color: var(--el-color-primary); font-size: 16px; }
.add-row-bar { margin-top: 12px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
