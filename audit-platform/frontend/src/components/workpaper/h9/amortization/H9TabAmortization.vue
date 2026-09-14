<template>
  <div class="h9-tab-amortization">
    <!-- 蓝色渐变引导区 -->
    <div class="guide-banner">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 选择合同</div>
        <div class="guide-step"><span class="step-num">②</span> 确认参数</div>
        <div class="guide-step"><span class="step-num">③</span> 生成摊销表</div>
        <div class="guide-step"><span class="step-num">④</span> 验证末期归零</div>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：按实际利率法重算租赁负债各期利息与本金摊销，验证期末余额归零、年金现值与账面初始确认一致，并与 H9-1 审定表本期利息费用勾稽。"
    />

    <!-- 方法论上下文（琥珀色块） -->
    <div class="methodology-context">
      <p><strong>CAS21 §18-19 实际利率法：</strong>承租人应当按照租赁负债的余额和租赁内含利率（或增量借款利率IBR）计算各期利息费用。每期利息=期初余额×实际利率；本金偿还=每期付款-利息费用；期末余额=期初-本金偿还。最后一期调整尾差使期末余额精确归零。</p>
    </div>

    <!-- 合同筛选 -->
    <div class="section-header">
      <span>租赁负债摊销表 H9-4</span>
      <div class="section-header-actions">
        <el-button size="small" circle @click="openReview('H9-4-amortization')">💬</el-button>
      </div>
    </div>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H9-2" :context-project-id="props.projectId" /></span>
        <el-tag size="small" type="info">共 {{ schedule.length }} 期</el-tag>
      </div>
    </div>

    <div class="contract-filter">
      <span class="filter-label">选择合同：</span>
      <el-select
        v-model="selectedContractNo"
        placeholder="请选择租赁合同"
        size="default"
        style="width: 320px"
        :disabled="contracts.length === 0"
        @change="onContractChange"
      >
        <el-option
          v-for="c in contracts"
          :key="c.contractNo"
          :label="`${c.contractNo} - ${c.lessor}`"
          :value="c.contractNo"
        />
      </el-select>
      <el-tag v-if="contracts.length === 0" type="warning" size="small" style="margin-left: 8px">
        请先在H9-2完成合同录入
      </el-tag>
    </div>

    <!-- 参数输入区 -->
    <el-card v-if="selectedContract" shadow="never" class="params-card">
      <div class="params-grid">
        <div class="param-item">
          <span class="param-label">初始余额（元）</span>
          <span class="param-value">{{ fmtAmt(selectedContract.initialBalance) }}</span>
        </div>
        <div class="param-item">
          <span class="param-label">年租金（元）</span>
          <span class="param-value">{{ fmtAmt(selectedContract.annualPayment) }}</span>
        </div>
        <div class="param-item">
          <span class="param-label">IBR年利率</span>
          <span class="param-value">{{ (selectedContract.ibrRate * 100).toFixed(2) }}%</span>
        </div>
        <div class="param-item">
          <span class="param-label">租赁期（月）</span>
          <span class="param-value">{{ selectedContract.leaseTerm }}</span>
        </div>
      </div>
    </el-card>

    <!-- 摊销表表格 -->
    <el-table
      v-if="schedule.length > 0"
      :data="schedule"
      border
      stripe
      size="small"
      class="amortization-table"
      :row-class-name="rowClassName"
      show-summary
      :summary-method="getSummary"
    >
      <el-table-column prop="period" label="期数" width="70" align="center" />
      <el-table-column prop="beginBalance" label="期初余额" min-width="130" align="right">
        <template #default="{ row }">
          <span class="amt-cell">{{ fmtAmt(row.beginBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="payment" label="本期租金" min-width="130" align="right">
        <template #default="{ row }">
          <span class="amt-cell">{{ fmtAmt(row.payment) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="interest" label="利息费用" min-width="130" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="利息费用 = 期初余额 × 月利率">{{ fmtAmt(row.interest) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="principal" label="本金偿还" min-width="130" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="本金偿还 = 本期租金 - 利息费用">{{ fmtAmt(row.principal) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="endBalance" label="期末余额" min-width="130" align="right">
        <template #default="{ row, $index }">
          <span
            :class="['formula-cell', { 'tail-error': isLastRow($index) && !validation.isValid }]"
            title="期末余额 = 期初余额 - 本金偿还"
          >{{ fmtAmt(row.endBalance) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 空状态 -->
    <el-empty v-else-if="selectedContract" description="参数不足，无法生成摊销表（请确认初始余额与租赁期大于0）" />
    <el-empty v-else description="请先选择一份租赁合同" />

    <!-- 末期验证 -->
    <div v-if="schedule.length > 0" class="validation-section">
      <el-card shadow="never" :class="['validation-card', validation.isValid ? 'valid' : 'invalid']">
        <div class="validation-header">末期验证</div>
        <div class="validation-grid">
          <div class="vd-item">
            <span class="vd-label">最后一期期末余额</span>
            <span :class="['vd-value', { 'vd-error': !validation.isValid }]">
              {{ fmtAmt(schedule[schedule.length - 1]?.endBalance ?? 0) }}
            </span>
          </div>
          <div class="vd-item">
            <span class="vd-label">允许尾差</span>
            <span class="vd-value">±1.00 元</span>
          </div>
          <div class="vd-item">
            <span class="vd-label">验证结果</span>
            <el-tag :type="validation.isValid ? 'success' : 'danger'" size="small">
              {{ validation.isValid ? '✓ 通过' : '✗ 尾差超限' }}
            </el-tag>
          </div>
        </div>
        <div v-if="!validation.isValid" class="vd-warning">
          ⚠️ {{ validation.warning }}
        </div>
      </el-card>
    </div>

    <!-- 现值验证 -->
    <div v-if="selectedContract && computedPV > 0" class="pv-section">
      <el-card shadow="never" class="pv-card">
        <div class="validation-header">现值验证</div>
        <div class="validation-grid">
          <div class="vd-item">
            <span class="vd-label">年金现值（计算）</span>
            <span class="vd-value formula-cell" title="PV = payment × (1-(1+r)^(-n))/r">{{ fmtAmt(computedPV) }}</span>
          </div>
          <div class="vd-item">
            <span class="vd-label">账面初始余额</span>
            <span class="vd-value">{{ fmtAmt(selectedContract.initialBalance) }}</span>
          </div>
          <div class="vd-item">
            <span class="vd-label">差额</span>
            <span :class="['vd-value', { 'vd-error': Math.abs(pvDiff) > 1 }]">
              {{ fmtAmt(pvDiff) }}
            </span>
          </div>
          <div class="vd-item">
            <span class="vd-label">一致性</span>
            <el-tag :type="Math.abs(pvDiff) <= 1 ? 'success' : 'warning'" size="small">
              {{ Math.abs(pvDiff) <= 1 ? '✓ 一致' : '△ 存在差异' }}
            </el-tag>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 与审定交叉验证 -->
    <div v-if="schedule.length > 0" class="cross-section">
      <el-card shadow="never" class="cross-card">
        <div class="validation-header">与审定表(H9-1)交叉验证</div>
        <div class="validation-grid">
          <div class="vd-item">
            <span class="vd-label">摊销表本期利息</span>
            <span class="vd-value formula-cell" title="前12期利息合计（年报口径）">{{ fmtAmt(validation.currentPeriodInterest) }}</span>
          </div>
          <div class="vd-item">
            <span class="vd-label">全期利息（参考）</span>
            <span class="vd-value">{{ fmtAmt(validation.totalInterest) }}</span>
          </div>
          <div class="vd-item">
            <span class="vd-label">H9-1本期利息费用</span>
            <span class="vd-value">{{ fmtAmt(h9AuditedInterest) }}</span>
          </div>
          <div class="vd-item">
            <span class="vd-label">差额</span>
            <span :class="['vd-value', { 'vd-error': Math.abs(crossDiff) > 1 }]">
              {{ fmtAmt(crossDiff) }}
            </span>
          </div>
          <div class="vd-item">
            <span class="vd-label">勾稽结果</span>
            <el-tag :type="Math.abs(crossDiff) <= 1 ? 'success' : 'danger'" size="small">
              {{ Math.abs(crossDiff) <= 1 ? '✓ 一致' : '✗ 不一致' }}
            </el-tag>
          </div>
        </div>
        <div v-if="h9AuditedInterest === 0" class="vd-hint">
          <el-text type="info" size="small">提示：H9-1审定表利息费用尚未录入，请先完成审定表。</el-text>
        </div>
      </el-card>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header" style="margin-bottom:0">
          <span>审计说明</span>
          <el-button size="small" circle @click="openReview('H9-amortization-note')">💬</el-button>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5 }"
        placeholder="请填写摊销表的审计说明：实际利率法参数来源、重算过程、末期归零与现值验证结果、与审定利息的勾稽差异说明等..."
        :disabled="isReadonly" @blur="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header" style="margin-bottom:0">
          <span>审计结论</span>
          <el-button size="small" circle @click="openReview('H9-amortization-conclusion')">💬</el-button>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3 }"
        placeholder="请填写摊销表的审计结论..." :disabled="isReadonly" @blur="saveAuditConclusion" />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>摊销表按合同维度展示，选择不同合同查看各自的摊销明细</li>
        <li>核心公式：利息=期初×月利率；本金=租金-利息；期末=期初-本金</li>
        <li>最后一期系统自动调整付款额使期末归零（CAS21尾差处理）</li>
        <li>利息合计应与H9-1审定表中的"本期利息费用"一致</li>
        <li>现值验证=年金现值公式反算，与初始确认金额差额应≤1元</li>
        <li>如合同参数不正确，请返回H9-2明细表修改</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H9TabAmortization.vue — H9-4 租赁负债摊销表（核心）
 *
 * 纯前端计算视图（无物理xlsx sheet）：
 * - 从H9-2合同列表下拉选择 → 生成实际利率法完整摊销表
 * - 末期验证（期末余额≈0）
 * - 现值验证（calcAnnuityPV vs 账面）
 * - 与H9-1审定表利息费用交叉验证
 *
 * Spec: .kiro/specs/h9-lease-liabilities/
 * Task: 4.4
 * Requirements: 4.1-4.8
 */
import { ref, computed, inject, toRef } from 'vue'
import { useH9Amortization } from '../../composables/useH9Amortization'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
// 父入口提供的持久化函数（更新共享 Map + 防抖 PUT checklist-responses）。Bug C 修复。
const saveResponse = inject<(itemId: string, value: any) => void>('saveResponse', (itemId, value) => {
  const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
  props.allResponses.set(itemId, { item_id: itemId, remark: strVal, conclusion: null })
})

// ─── Composable ──────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

const {
  selectedContractNo,
  contracts,
  selectedContract,
  schedule,
  computedPV,
  validation,
  selectContract,
} = useH9Amortization({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
})

// ─── 与审定交叉 ──────────────────────────────────────────────────────────────

/** H9-1 审定表本期利息费用（从allResponses提取） */
const h9AuditedInterest = computed<number>(() => {
  const item =
    props.allResponses.get('H9-1-interest-expense-audited')
    ?? props.allResponses.get('H9-1-interest-expense')
  if (!item) return 0
  const raw = item.remark ?? item.conclusion
  return Number(raw) || 0
})

/** 利息差额 = 摊销表本期利息 - 审定表金额 */
const crossDiff = computed<number>(() => validation.value.currentPeriodInterest - h9AuditedInterest.value)

/** 现值差额 */
const pvDiff = computed<number>(() => {
  if (!selectedContract.value) return 0
  return computedPV.value - selectedContract.value.initialBalance
})

// ─── Helpers ─────────────────────────────────────────────────────────────────

function isLastRow(index: number): boolean {
  return index === schedule.value.length - 1
}

function rowClassName({ rowIndex }: { row: any; rowIndex: number }): string {
  if (rowIndex === schedule.value.length - 1 && !validation.value.isValid) {
    return 'tail-error-row'
  }
  return ''
}

function onContractChange(val: string) {
  selectContract(val)
}

function getSummary({ columns, data }: { columns: any[]; data: any[] }) {
  const sums: string[] = []
  columns.forEach((col: any, index: number) => {
    if (index === 0) { sums[index] = '合计'; return }
    if (index === 1) { sums[index] = ''; return } // 期初余额不合计
    const prop = col.property as string
    if (['payment', 'interest', 'principal'].includes(prop)) {
      const total = data.reduce((acc: number, row: any) => acc + (Number(row[prop]) || 0), 0)
      sums[index] = fmtAmt(total)
    } else {
      sums[index] = ''
    }
  })
  return sums
}

// ─── Actions ─────────────────────────────────────────────────────────────────

function openReview(id: string) {
  openReviewDialog(id)
}

// ─── 审计说明 / 结论 ─────────────────────────────────────────────────────────
const auditNote = ref('')
const auditConclusion = ref('')
const _noteData = props.allResponses.get('H9-amortization-note')
if (_noteData) auditNote.value = _noteData.remark ?? _noteData.conclusion ?? ''
const _conclusionData = props.allResponses.get('H9-amortization-conclusion')
if (_conclusionData) auditConclusion.value = _conclusionData.remark ?? _conclusionData.conclusion ?? ''

function saveAuditNote() {
  saveResponse('H9-amortization-note', auditNote.value)
}

function saveAuditConclusion() {
  saveResponse('H9-amortization-conclusion', auditConclusion.value)
}

// ─── 金额格式化 ──────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  if (Math.abs(val) < 0.005) return '0.00'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h9-tab-amortization { padding: 16px; font-size: var(--wp-font-size, 13px); }

/* 蓝色渐变引导区 */
.guide-banner {
  background: linear-gradient(135deg, #e0f2fe 0%, #bae6fd 50%, #7dd3fc 100%);
  border-radius: 8px;
  padding: 14px 20px;
  margin-bottom: 16px;
}
.guide-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px 24px;
}
.guide-step {
  display: flex; align-items: center; gap: 8px;
  font-size: var(--wp-font-size, 13px); color: #0c4a6e; font-weight: 500;
}
.step-num {
  display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border-radius: 50%;
  background: #0284c7; color: #fff; font-size: 12px; font-weight: 700;
}

/* 方法论上下文（琥珀色块） */
.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.6;
}

/* Section header */
.section-header {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 14px; font-weight: 600; margin-bottom: 12px;
}
.section-header-actions { display: flex; align-items: center; gap: 4px; }

.objective-alert { margin-bottom: 12px; }
.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
}
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-bottom: 12px; }

/* 合同筛选 */
.contract-filter {
  display: flex; align-items: center; margin-bottom: 16px;
}
.filter-label { font-size: var(--wp-font-size, 13px); color: var(--el-text-color-regular); margin-right: 8px; }

/* 参数卡片 */
.params-card { margin-bottom: 16px; }
.params-grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
}
.param-item { text-align: center; }
.param-label { display: block; font-size: 11px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.param-value { display: block; font-size: 14px; font-weight: 600; font-variant-numeric: tabular-nums; }

/* 摊销表 */
.amortization-table { margin-bottom: 16px; font-size: var(--wp-font-size, 13px); }
.amt-cell { display: block; text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell {
  display: inline-block; text-align: right;
  border-bottom: 1px dashed #67c23a;
  cursor: help;
  color: var(--el-text-color-primary);
  font-variant-numeric: tabular-nums;
}
.tail-error { color: #f56c6c !important; border-bottom-color: #f56c6c !important; font-weight: 700; }

/* 验证区域 */
.validation-section, .pv-section, .cross-section { margin-bottom: 12px; }
.validation-card, .pv-card, .cross-card { border-radius: 6px; }
.validation-card.valid { border-left: 4px solid #67c23a; }
.validation-card.invalid { border-left: 4px solid #f56c6c; }
.pv-card { border-left: 4px solid #409eff; }
.cross-card { border-left: 4px solid #e6a23c; }

.validation-header {
  font-size: var(--wp-font-size, 13px); font-weight: 600; margin-bottom: 10px;
  color: var(--el-text-color-primary);
}
.validation-grid {
  display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px 20px;
}
.vd-item { display: flex; flex-direction: column; gap: 2px; }
.vd-label { font-size: 11px; color: var(--el-text-color-secondary); }
.vd-value { font-size: var(--wp-font-size, 13px); font-weight: 600; font-variant-numeric: tabular-nums; }
.vd-error { color: #f56c6c; }
.vd-warning {
  margin-top: 10px; padding: 8px 12px;
  background: #fef2f2; border-radius: 4px;
  font-size: 12px; color: #dc2626;
}
.vd-hint { margin-top: 8px; }

/* 编制提示 */
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }

/* 末期错误行 */
:deep(.tail-error-row) { background-color: #fef2f2 !important; }
:deep(.tail-error-row:hover td) { background-color: #fee2e2 !important; }
</style>
