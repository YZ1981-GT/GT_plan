<template>
  <div class="h2-tab-interest-cap-no-borrow">
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：在无专门借款情形下，测算一般借款应予资本化的利息；验证加权资本化率与累计支出加权平均数，并与账面资本化金额比对。" />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag size="small" type="warning">适用：全部支出占用一般借款</el-tag>
        <el-tag size="small" type="info">与 H2-11 互斥</el-tag>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H2-10" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H2-11" :context-project-id="projectId" context="有专门借款改走 H2-11" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H2-2" :context-project-id="projectId" context="利息列勾稽" /></span>
        <el-tag size="small" type="info">借款 {{ state.loansNoBorrow.value.length }} 笔</el-tag>
        <el-button size="small" circle @click="openReview('H2-10')">💬</el-button>
      </div>
    </div>

    <div class="methodology-context">
      <p><strong>编制思路（CAS17 · 无专门借款）：</strong></p>
      <ol>
        <li>先算一般借款<strong>年加权资本化率</strong>＝Σ实际利息 ÷ Σ本金加权平均数</li>
        <li>再按月登记工程支出，用<strong>半月平均法</strong>滚动计算加权平均支出</li>
        <li>资本化金额＝各月加权支出 × 月资本化率；与账面比对后决定是否调整</li>
      </ol>
      <p class="hint-line">若存在专门借款，请改用 <a href="#" @click.prevent="goWithBorrow">H2-11</a>（专门借款利息−闲置收益＋一般借款补充）。二者只编其一。</p>
    </div>

    <!-- 一、一般借款资本化加权平均年利率 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>一、计算一般借款资本化加权平均年利率</span>
          <div class="section-header-actions" v-if="!isReadonly">
            <el-button size="small" type="success" plain :loading="state.l1Pulling.value" @click="handlePullL1Loans">
              从 L1 带入借款
            </el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.loansNoBorrow.value" border stripe size="small" class="loan-table"
        show-summary :summary-method="loanSummary">
        <el-table-column type="index" label="序号" width="50" align="center" />
        <el-table-column prop="lender" label="贷款方" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.lender" size="small"
              @change="onLoanChange(row.rowId, 'lender', $event)" />
            <span v-else>{{ row.lender || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="①一般借款本金" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.principal" :controls="false"
              size="small" class="amt-input" @change="onLoanChange(row.rowId, 'principal', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.principal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="开始计息日" min-width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.startDate" type="date" size="small"
              value-format="YYYY-MM-DD" style="width:100%"
              @change="onLoanChange(row.rowId, 'startDate', $event)" />
            <span v-else>{{ row.startDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="结束计息日" min-width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.endDate" type="date" size="small"
              value-format="YYYY-MM-DD" style="width:100%"
              @change="onLoanChange(row.rowId, 'endDate', $event)" />
            <span v-else>{{ row.endDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="②计息天数" width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.days" :controls="false"
              size="small" class="amt-input" @change="onLoanChange(row.rowId, 'days', $event)" />
            <span v-else>{{ row.days || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="③当期天数" width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.periodDays" :controls="false"
              size="small" class="amt-input" @change="onLoanChange(row.rowId, 'periodDays', $event)" />
            <span v-else>{{ row.periodDays || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="④本金加权平均数" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="④=①×②/③">{{ fmtAmt(row.weightedPrincipal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="⑤实际利息费用" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.actualInterest" :controls="false"
              size="small" class="amt-input" @change="onLoanChange(row.rowId, 'actualInterest', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.actualInterest) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="年利率(%)" width="90" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.rate" :controls="false" :precision="4"
              size="small" class="amt-input" @change="onLoanChange(row.rowId, 'rate', $event)" />
            <span v-else>{{ row.rate?.toFixed(4) ?? '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="44" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="handleRemoveLoan(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddLoan">+ 新增一般借款</el-button>
      </div>
      <div class="rate-banner">
        <span>一般借款加权平均年利率⑥＝Σ⑤/Σ④：</span>
        <strong class="formula-cell highlight" title="资本化率=实际利息合计/本金加权合计">
          {{ pct(state.effectiveAnnualCapRate.value) }}
        </strong>
        <span class="muted">（月利率默认＝年利率/12：{{ pct(state.monthlyCapRate.value) }}）</span>
      </div>
      <p class="note-text">说明：借款增减时按占用天数/当期天数加权；利率相同且本金不变时，加权平均利率即该利率。实际利息优先取自账面。</p>
    </el-card>

    <!-- 二、资本化金额测算（月度） -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>二、计算一般借款利息资本化金额</span>
          <div class="section-header-actions">
            <span class="rate-edit-label">资本化率(月)%：</span>
            <el-input-number
              v-if="!isReadonly"
              :model-value="state.monthlyCapRatePct.value ?? Number((state.monthlyCapRate.value * 100).toFixed(6))"
              :controls="false" :precision="6" size="small" class="rate-input"
              @change="onMonthlyRateChange"
            />
            <span v-else>{{ pct(state.monthlyCapRate.value) }}</span>
          </div>
        </div>
      </template>

      <el-table :data="state.monthlyRows.value" border stripe size="small" class="exp-table"
        :row-class-name="monthRowClass">
        <el-table-column prop="monthLabel" label="月份" width="88" fixed />
        <el-table-column label="①前期开发" min-width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="canEditMonth(row)" v-model="row.prelimDev" :controls="false"
              size="small" class="amt-input" @change="onMonthChange(row.rowId, 'prelimDev', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.prelimDev) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="②工程费用" min-width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="canEditMonth(row)" v-model="row.engCost" :controls="false"
              size="small" class="amt-input" @change="onMonthChange(row.rowId, 'engCost', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.engCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="③借款费用" min-width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="canEditMonth(row)" v-model="row.borrowCost" :controls="false"
              size="small" class="amt-input" @change="onMonthChange(row.rowId, 'borrowCost', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.borrowCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="④建安工程" min-width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="canEditMonth(row)" v-model="row.install" :controls="false"
              size="small" class="amt-input" @change="onMonthChange(row.rowId, 'install', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.install) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="⑤土地" min-width="90" align="right">
          <template #default="{ row }">
            <el-input-number v-if="canEditMonth(row)" v-model="row.land" :controls="false"
              size="small" class="amt-input" @change="onMonthChange(row.rowId, 'land', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.land) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="⑥支出合计" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="⑥=①+②+③+④+⑤">{{ fmtAmt(calcRow(row.rowId)?.expTotal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="⑦本年减少" min-width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="canEditMonth(row)" v-model="row.decrease" :controls="false"
              size="small" class="amt-input" @change="onMonthChange(row.rowId, 'decrease', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="⑧预付工程款" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="canEditMonth(row)" v-model="row.prepaid" :controls="false"
              size="small" class="amt-input" @change="onMonthChange(row.rowId, 'prepaid', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.prepaid) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="⑨加权平均支出" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :title="row.rowType === 'opening'
              ? '年初⑨=⑥+⑧-③'
              : '⑨=上月⑨+(⑥-⑦-③+⑧)/2'">{{ fmtAmt(calcRow(row.rowId)?.weightedExp) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="⑩资本化金额" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="⑩=⑨×月资本化率">
              {{ row.rowType === 'opening' ? '-' : fmtAmt(calcRow(row.rowId)?.capAmount) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="90">
          <template #default="{ row }">
            <el-input v-if="canEditMonth(row)" v-model="row.remark" size="small"
              @change="onMonthChange(row.rowId, 'remark', $event)" />
            <span v-else>{{ row.remark || '' }}</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="calc-grid summary-grid">
        <div class="calc-item">
          <span class="calc-label">本年测算资本化合计：</span>
          <span class="calc-value formula-cell highlight">{{ fmtAmt(state.capAmountNoBorrow.value) }}</span>
        </div>
        <div class="calc-item">
          <span class="calc-label">账面资本化（可改）：</span>
          <el-input-number v-if="!isReadonly" :model-value="state.bookCapForCompare.value"
            :controls="false" size="small" class="amt-input"
            @change="state.setClientCapAmount(Number($event) || 0)" />
          <span v-else class="calc-value">{{ fmtAmt(state.bookCapForCompare.value) }}</span>
        </div>
        <div class="calc-item">
          <span class="calc-label">差异（测算−账面）：</span>
          <span class="calc-value" :class="{ 'diff-warn': Math.abs(state.capDifference.value) >= 0.01 }">
            {{ fmtAmt(state.capDifference.value) }}
          </span>
        </div>
        <div class="calc-item">
          <span class="calc-label">利息费用化（利息总额−资本化）：</span>
          <span class="calc-value formula-cell">{{ fmtAmt(state.expenseAmount.value) }}</span>
        </div>
      </div>

      <el-alert
        v-if="state.exceedsInterestCeiling.value"
        type="error" :closable="false" show-icon class="ceiling-alert"
        title="资本化金额超过一般借款实际利息总额，违反 CAS17 上限，请复核。"
      />
    </el-card>

    <!-- 三、测算结论 / 建议分录 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header"><span>三、测算结论与建议调整</span></div>
      </template>
      <pre class="aje-box">{{ state.suggestedAje.value.text }}</pre>
      <p class="note-text">关注：资本化起止时点是否正确；资本化率计算是否正确；会计处理是否恰当。资本化期间为开工至达到预定可使用状态。</p>
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="section-header"><span>审计说明</span></div></template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 4 }"
        placeholder="概述一般借款加权资本化率、月度加权支出及与账面差异的复核过程。"
        :disabled="isReadonly" @blur="state.saveNote(state.auditNote.value)" />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="section-header"><span>审计结论</span></div></template>
      <el-input v-model="state.auditConclusion.value" type="textarea" :autosize="{ minRows: 3 }"
        placeholder="如：测算与账面差异在可接受范围内 / 已建议调整多资本化利息××元。"
        :disabled="isReadonly" @blur="state.saveConclusion(state.auditConclusion.value)" />
    </el-card>

    <details class="edit-tips">
      <summary>编制提示 · 与 H2-11 关系</summary>
      <ul>
        <li><strong>H2-10</strong>：无专门借款 → 全部合格支出 × 一般借款加权资本化率</li>
        <li><strong>H2-11</strong>：有专门借款 → 先专门借款利息−闲置收益，超出专门借款的支出再按一般借款利率补充；一般借款明细可从本表带入</li>
        <li>加权平均支出⑨：年初＝支出合计+预付−借款费用；各月＝上月⑨+(本月支出−减少−借款费用+预付)/2</li>
        <li>资本化利息不得超过当期实际利息总额</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabInterestCapNoBorrow.vue — H2-10 利息资本化(无专门借款)
 * 对齐 xlsx：①年加权利率表 ②月度支出资本化表 ③差异与建议分录
 * Spec: Task 4.13 | Requirements: 10.1-10.4, 10.6-10.10
 */
import { inject, toRef, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useH2InterestCap } from '../../composables/useH2InterestCap'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import type { MonthlyExpRow } from '../../composables/useH2InterestCap'

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
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const state = useH2InterestCap({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
  onPublishEvent(event: string, payload: any) {
    http.post(`/api/projects/${props.projectId}/events/publish`, {
      event_type: event,
      payload,
    }, { _silent: true } as any).catch(() => { /* best effort */ })
  },
})

// 进入本页即锁定无专门借款分支（与 H2-11 互斥）
if (state.branch.value !== 'noBorrow') state.setBranch('noBorrow')

function onLoanChange(rowId: string, field: string, value: any) {
  state.updateLoanNoBorrow(rowId, field, value)
}
function handleAddLoan() { state.addLoanNoBorrow() }

async function handlePullL1Loans() {
  const res = await state.pullGeneralLoansFromL1(props.projectId)
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}
function handleRemoveLoan(rowId: string) { state.removeLoanNoBorrow(rowId) }

function calcRow(rowId: string) {
  return state.monthlyCalc.value.rows.find(r => r.rowId === rowId)
}

function canEditMonth(row: MonthlyExpRow) {
  return !props.isReadonly && (row.rowType === 'opening' || row.rowType === 'month')
}
function onMonthChange(rowId: string, field: string, value: any) {
  state.updateMonthlyRow(rowId, field, value)
}
function onMonthlyRateChange(v: number | undefined) {
  if (v == null || Number.isNaN(Number(v))) {
    state.setMonthlyCapRatePct(null)
  } else {
    state.setMonthlyCapRatePct(Number(v))
  }
}

function monthRowClass({ row }: { row: MonthlyExpRow }) {
  return row.rowType === 'opening' ? 'row-opening' : ''
}

function loanSummary({ columns, data }: { columns: any[]; data: any[] }) {
  const sums: string[] = []
  columns.forEach((col, idx) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    const prop = col.property
    if (prop === 'lender' || col.label === '贷款方') { sums[idx] = ''; return }
    if (col.label?.includes('①') || col.label?.includes('本金加权') || col.label?.includes('实际利息')) {
      const key = col.label?.includes('①') ? 'principal'
        : col.label?.includes('本金加权') ? 'weightedPrincipal' : 'actualInterest'
      const total = data.reduce((s, r) => s + (Number(r[key]) || 0), 0)
      sums[idx] = fmtAmt(total)
      return
    }
    sums[idx] = ''
  })
  return sums
}

function goWithBorrow() {
  state.setBranch('withBorrow')
  emit('navigate-sheet', 'H2-11 利息资本化有专门借款')
}

function openReview(id: string) { openReviewDialog(id) }

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function pct(decimalRate: number | null | undefined): string {
  if (decimalRate == null) return '-'
  return `${(decimalRate * 100).toFixed(4)}%`
}
</script>

<style scoped>
.h2-tab-interest-cap-no-borrow { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; gap: 8px; flex-wrap: wrap; }
.toolbar-left, .toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.methodology-context {
  border-left: 3px solid #c45c26; background: #faf6f1;
  padding: 12px 16px; margin-bottom: 16px; border-radius: 4px; font-size: var(--wp-font-size, 13px);
}
.methodology-context ol { margin: 6px 0 0; padding-left: 20px; }
.hint-line { margin-top: 8px; color: var(--el-text-color-secondary); }
.hint-line a { color: var(--el-color-primary); }
.block-card, .audit-note-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.rate-edit-label { font-size: 12px; color: var(--el-text-color-secondary); }
.rate-input { width: 120px; }
.loan-table, .exp-table { font-size: var(--wp-font-size, 13px); }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.formula-cell.highlight, .calc-value.highlight { color: var(--el-color-primary); font-weight: 600; }
.rate-banner { margin-top: 12px; display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.muted { color: var(--el-text-color-secondary); font-size: 12px; }
.note-text { margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary); }
.add-row-bar { margin-top: 12px; }
.calc-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 16px; }
.calc-item { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.calc-label { font-weight: 500; }
.calc-value { font-weight: 600; font-size: 14px; font-variant-numeric: tabular-nums; }
.diff-warn { color: var(--el-color-danger); }
.ceiling-alert { margin-top: 12px; }
.aje-box {
  margin: 0; padding: 12px; background: var(--el-fill-color-light);
  border-radius: 4px; white-space: pre-wrap; font-family: inherit; font-size: 13px;
}
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
:deep(.row-opening) { background: var(--el-fill-color-lighter); }
</style>
