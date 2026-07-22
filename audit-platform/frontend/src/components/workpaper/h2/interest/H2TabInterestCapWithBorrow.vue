<template>
  <div class="h2-tab-interest-cap-with-borrow">
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：有专门借款时，测算专门借款资本化（利息−闲置收益）＋一般借款补充资本化（扣 SP 后的月度加权支出×月利率），与账面比对后确定调整。" />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag size="small" type="warning">适用：存在专门借款</el-tag>
        <el-tag size="small" type="info">与 H2-10 互斥</el-tag>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H2-11" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H2-10" :context-project-id="projectId" context="无专门借款改走 H2-10" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H2-2" :context-project-id="projectId" context="利息列勾稽" /></span>
        <el-tag size="small" type="info">一般借款 {{ state.loansWithBorrow.value.length }} 笔</el-tag>
        <el-button v-if="!isReadonly" size="small" @click="handleImportLoans">带入借款</el-button>
        <el-button v-if="!isReadonly" size="small" @click="handleImportMonthly">带入月度支出</el-button>
        <el-button size="small" circle @click="openReview('H2-11')">💬</el-button>
      </div>
    </div>

    <div class="methodology-context">
      <p><strong>编制思路（CAS17 · 有专门借款）：</strong></p>
      <ol>
        <li>① 专门借款资本化＝利息费用 − 闲置资金收益</li>
        <li>② 月度登记工程支出，扣减专门借款已占用额(SP)，半月平均滚动加权</li>
        <li>③ 一般借款补充＝各月加权超额支出 × 一般借款月资本化率；合计＝①＋③</li>
      </ol>
    </div>

    <!-- 一、专门借款 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header"><span>一、专门借款资本化</span></div>
      </template>
      <div class="calc-grid">
        <div class="calc-item">
          <span class="calc-label">专门借款本金：</span>
          <el-input-number v-model="state.specialLoanData.value.specialLoanAmount" :controls="false"
            size="small" :disabled="isReadonly" @change="onSpecialChange('specialLoanAmount', $event)" />
        </div>
        <div class="calc-item">
          <span class="calc-label">专门借款利息费用：</span>
          <el-input-number v-model="state.specialLoanData.value.specialInterest" :controls="false"
            size="small" :disabled="isReadonly" @change="onSpecialChange('specialInterest', $event)" />
        </div>
        <div class="calc-item">
          <span class="calc-label">减：闲置资金收益：</span>
          <el-input-number v-model="state.specialLoanData.value.idleIncome" :controls="false"
            size="small" :disabled="isReadonly" @change="onSpecialChange('idleIncome', $event)" />
        </div>
        <div class="calc-item total-item">
          <span class="calc-label">专门借款资本化金额：</span>
          <span class="calc-value formula-cell highlight" title="=max(利息−闲置收益,0)">
            {{ fmtAmt(state.specialLoanCap.value) }}
          </span>
        </div>
      </div>
    </el-card>

    <!-- 二、一般借款明细（算资本化率） -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header"><span>二、一般借款（补充资本化率）</span></div>
      </template>
      <el-table :data="state.loansWithBorrow.value" border stripe size="small" class="loan-table">
        <el-table-column prop="lender" label="贷款方" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.lender" size="small"
              @change="onGeneralChange(row.rowId, 'lender', $event)" />
            <span v-else>{{ row.lender || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="principal" label="本金" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.principal" :controls="false"
              size="small" class="amt-input" @change="onGeneralChange(row.rowId, 'principal', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.principal) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rate" label="年利率(%)" width="90" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.rate" :controls="false" :precision="4"
              size="small" class="amt-input" @change="onGeneralChange(row.rowId, 'rate', $event)" />
            <span v-else>{{ row.rate?.toFixed(4) ?? '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="days" label="计息天数" width="88" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.days" :controls="false"
              size="small" class="amt-input" @change="onGeneralChange(row.rowId, 'days', $event)" />
            <span v-else>{{ row.days ?? '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="实际利息" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.actualInterest" :controls="false"
              size="small" class="amt-input" @change="onGeneralChange(row.rowId, 'actualInterest', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.actualInterest || row.interest) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="44" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="handleRemoveGeneral(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddGeneral">+ 新增一般借款</el-button>
      </div>
      <div class="rate-banner">
        <span>一般借款加权资本化率（年）：</span>
        <strong class="formula-cell highlight">{{ pct(state.generalCapRate.value) }}</strong>
        <span class="muted">月利率默认＝年/12：{{ pct(state.monthlyCapRate11.value) }}</span>
      </div>
    </el-card>

    <!-- 三、月度支出（扣 SP） -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>三、一般借款补充资本化（月度·扣 SP）</span>
          <div class="section-header-actions">
            <span class="rate-edit-label">资本化率(月)%：</span>
            <el-input-number
              v-if="!isReadonly"
              :model-value="state.monthlyCapRatePct11.value ?? Number((state.monthlyCapRate11.value * 100).toFixed(6))"
              :controls="false" :precision="6" size="small" class="rate-input"
              @change="onMonthlyRateChange"
            />
            <span v-else>{{ pct(state.monthlyCapRate11.value) }}</span>
          </div>
        </div>
      </template>

      <el-table :data="state.monthlyRows11.value" border stripe size="small" class="exp-table"
        :row-class-name="monthRowClass">
        <el-table-column prop="monthLabel" label="月份" width="80" fixed />
        <el-table-column label="①前期开发" min-width="90" align="right">
          <template #default="{ row }">
            <el-input-number v-if="canEditMonth(row)" v-model="row.prelimDev" :controls="false"
              size="small" class="amt-input" @change="onMonthChange(row.rowId, 'prelimDev', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.prelimDev) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="②工程费用" min-width="90" align="right">
          <template #default="{ row }">
            <el-input-number v-if="canEditMonth(row)" v-model="row.engCost" :controls="false"
              size="small" class="amt-input" @change="onMonthChange(row.rowId, 'engCost', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.engCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="③借款费用" min-width="90" align="right">
          <template #default="{ row }">
            <el-input-number v-if="canEditMonth(row)" v-model="row.borrowCost" :controls="false"
              size="small" class="amt-input" @change="onMonthChange(row.rowId, 'borrowCost', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.borrowCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="④建安" min-width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="canEditMonth(row)" v-model="row.install" :controls="false"
              size="small" class="amt-input" @change="onMonthChange(row.rowId, 'install', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.install) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="⑤土地" min-width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="canEditMonth(row)" v-model="row.land" :controls="false"
              size="small" class="amt-input" @change="onMonthChange(row.rowId, 'land', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.land) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="⑥合计" min-width="90" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="⑥=①+…+⑤">{{ fmtAmt(calcRow(row.rowId)?.expTotal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="⑦减少" min-width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="canEditMonth(row)" v-model="row.decrease" :controls="false"
              size="small" class="amt-input" @change="onMonthChange(row.rowId, 'decrease', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="⑧预付" min-width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="canEditMonth(row)" v-model="row.prepaid" :controls="false"
              size="small" class="amt-input" @change="onMonthChange(row.rowId, 'prepaid', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.prepaid) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="SP已占用" min-width="90" align="right">
          <template #default="{ row }">
            <el-input-number v-if="canEditMonth(row)" v-model="row.specialLoanUsed" :controls="false"
              size="small" class="amt-input" @change="onMonthChange(row.rowId, 'specialLoanUsed', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.specialLoanUsed) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="⑨加权支出" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :title="row.rowType === 'opening'
              ? '年初⑨=max(0,⑥+⑧−③−SP)'
              : '⑨=max(0,上月⑨+(⑥−⑦−③+⑧−SP)/2)'">
              {{ fmtAmt(calcRow(row.rowId)?.weightedExp) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="⑩资本化" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="⑩=⑨×月资本化率">
              {{ row.rowType === 'opening' ? '-' : fmtAmt(calcRow(row.rowId)?.capAmount) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
      <p class="note-text">SP＝专门借款已占用额。⑨已扣除 SP，即一般借款资本化基数；未填月度时回退为「超额加权×年利率」。</p>
    </el-card>

    <!-- 四、合计与差异 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header"><span>四、合计与账面比对</span></div>
      </template>
      <div class="calc-grid">
        <div class="calc-item">
          <span class="calc-label">专门借款资本化：</span>
          <span class="calc-value formula-cell">{{ fmtAmt(state.specialLoanCap.value) }}</span>
        </div>
        <div class="calc-item">
          <span class="calc-label">一般借款补充（月度优先）：</span>
          <span class="calc-value formula-cell">{{ fmtAmt(state.generalLoanSupp.value) }}</span>
        </div>
        <div class="calc-item total-item">
          <span class="calc-label">应予资本化合计：</span>
          <span class="calc-value formula-cell highlight">{{ fmtAmt(state.capAmountWithBorrow.value) }}</span>
        </div>
        <div class="calc-item">
          <span class="calc-label">账面资本化（可改）：</span>
          <el-input-number v-if="!isReadonly" :model-value="state.bookCapForCompare11.value"
            :controls="false" size="small" class="amt-input"
            @change="state.setClientCapAmount11(Number($event) || 0)" />
          <span v-else class="calc-value">{{ fmtAmt(state.bookCapForCompare11.value) }}</span>
        </div>
        <div class="calc-item">
          <span class="calc-label">差异（测算−账面）：</span>
          <span class="calc-value" :class="{ 'diff-warn': hasMaterialDiff }">
            {{ fmtAmt(state.capDifference.value) }}
          </span>
        </div>
        <div class="calc-item">
          <span class="calc-label">差异率：</span>
          <span class="calc-value formula-cell">
            {{ state.capDiffRate.value == null ? '—' : (state.capDiffRate.value * 100).toFixed(2) + '%' }}
          </span>
        </div>
        <div class="calc-item">
          <span class="calc-label">利息费用化：</span>
          <span class="calc-value formula-cell">{{ fmtAmt(state.totalExpenseAmount.value) }}</span>
        </div>
      </div>
      <pre class="aje-box">{{ state.suggestedAje.value.text }}</pre>
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="section-header"><span>审计说明</span></div></template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 4 }"
        placeholder="概述专门借款资本化、SP 扣除、一般借款补充及与账面差异。"
        :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="section-header"><span>审计结论</span></div></template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }"
        placeholder="如：测算准确 / 已建议冲回多资本化××元。"
        :disabled="isReadonly" @change="saveAuditConclusion" />
    </el-card>

    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>专门借款资本化＝max(利息−闲置收益, 0)</li>
        <li>月度⑨扣 SP（已占用专门借款），勿填「未使用」金额</li>
        <li>可从 H2-10 带入一般借款与月度支出，再补填各月 SP</li>
        <li>差异率为「—」表示应予资本化合计为 0（避免 #DIV/0!）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabInterestCapWithBorrow.vue — H2-11 有专门借款利息资本化
 * 对齐 xlsx：专门借款区 + 一般借款利率 + 月度扣SP资本化 + 差异
 */
import { ref, inject, toRef, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useH2InterestCap } from '../../composables/useH2InterestCap'
import type { MonthlyExpRow } from '../../composables/useH2InterestCap'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
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

const isReadonly = computed(() => props.isReadonly)
const hasMaterialDiff = computed(() => Math.abs(state.capDifference.value) >= 0.01)

const NOTE_KEY = 'H2-11-audit-note'
const CONCLUSION_KEY = 'H2-11-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  saveResponse(NOTE_KEY, val)
}
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  saveResponse(CONCLUSION_KEY, val)
}

onMounted(() => {
  if (state.branch.value !== 'withBorrow') state.setBranch('withBorrow')
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

function onSpecialChange(field: string, value: any) {
  state.updateSpecialLoanData(field as any, Number(value) || 0)
}
function onGeneralChange(rowId: string, field: string, value: any) {
  state.updateLoanWithBorrow(rowId, field, value)
}
function handleAddGeneral() { state.addLoanWithBorrow() }
function handleRemoveGeneral(rowId: string) { state.removeLoanWithBorrow(rowId) }

function calcRow(rowId: string) {
  return state.monthlyCalcWithBorrow.value.rows.find(r => r.rowId === rowId)
}
function canEditMonth(row: MonthlyExpRow) {
  return !props.isReadonly && (row.rowType === 'opening' || row.rowType === 'month')
}
function onMonthChange(rowId: string, field: string, value: any) {
  state.updateMonthlyRow11(rowId, field, value)
}
function onMonthlyRateChange(v: number | undefined) {
  if (v == null || Number.isNaN(Number(v))) state.setMonthlyCapRatePct11(null)
  else state.setMonthlyCapRatePct11(Number(v))
}
function monthRowClass({ row }: { row: MonthlyExpRow }) {
  return row.rowType === 'opening' ? 'row-opening' : ''
}

function handleImportLoans() {
  const n = state.importGeneralLoansFromH210()
  ElMessage.success(n ? `已带入 ${n} 笔一般借款` : 'H2-10 暂无一般借款可带入')
}
function handleImportMonthly() {
  const n = state.importMonthlyFromH210()
  ElMessage.success(n ? `已带入 ${n} 行月度支出（请补填 SP）` : 'H2-10 暂无月度支出')
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
.h2-tab-interest-cap-with-borrow { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; gap: 8px; flex-wrap: wrap; }
.toolbar-left, .toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.methodology-context {
  border-left: 3px solid #f0a020; background: #fdf8e8;
  padding: 12px 16px; margin-bottom: 16px; border-radius: 4px;
}
.methodology-context ol { margin: 6px 0 0; padding-left: 20px; }
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
.calc-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.calc-item { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.calc-item.total-item { grid-column: span 2; padding: 8px; background: var(--el-fill-color-light); border-radius: 4px; }
.calc-label { font-weight: 500; white-space: nowrap; }
.calc-value { font-weight: 600; font-size: 14px; font-variant-numeric: tabular-nums; }
.diff-warn { color: var(--el-color-danger); }
.aje-box {
  margin: 12px 0 0; padding: 12px; background: var(--el-fill-color-light);
  border-radius: 4px; white-space: pre-wrap; font-family: inherit; font-size: 13px;
}
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
:deep(.row-opening) { background: var(--el-fill-color-lighter); }
</style>
