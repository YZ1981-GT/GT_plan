<template>
  <div class="l1-tab-interest-calc">
    <!-- ═══ 返回目录 + 标题 + 操作栏 ═══ -->
    <div class="interest-header">
      <div class="interest-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">
          ← 返回目录
        </el-button>
        <h3 class="interest-title">L1-5 利息测算表</h3>
      </div>
      <div class="interest-header-right">
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          @click="handleAddRow"
        >
          + 新增测算行
        </el-button>
      </div>
    </div>

    <!-- ═══ 蓝色引导区：联动说明 ═══ -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step">
          <span class="guide-num">①</span>
          <span>录入/导入每笔借款的合同号、本金、利率、起止日期</span>
        </div>
        <div class="guide-step">
          <span class="guide-num">②</span>
          <span>系统自动裁剪起止时点 → 计算天数 → 测算利息</span>
        </div>
        <div class="guide-step">
          <span class="guide-num">③</span>
          <span>比对账载利息，差异超阈值红色高亮</span>
        </div>
        <div class="guide-step">
          <span class="guide-num">④</span>
          <span>测算结果自动联动 <GtIndexChip value="L2" :validate="false" /> 应付利息 / <GtIndexChip value="L8" :validate="false" /> 财务费用</span>
        </div>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色：365天制+天数逻辑） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>利息测算公式（365天制）：</strong>
        测算利息 = 本金 × 年利率 × 计息天数 / 365。
        <strong>天数逻辑：</strong>起算 = max(报告期始, 借款始)；截止 = min(借款止, 报告期末)；
        整年(差=365天)取365天，非整年取差值+1（算头算尾）。
      </div>
    </div>

    <!-- ═══ 筛选区 ═══ -->
    <div class="filter-bar">
      <el-input
        v-model="filterContract"
        placeholder="按合同号筛选"
        clearable
        size="small"
        style="width: 180px"
        @input="handleFilterChange"
      />
      <el-input
        v-model="filterBank"
        placeholder="按借款银行筛选"
        clearable
        size="small"
        style="width: 180px"
        @input="handleFilterChange"
      />
      <span class="filter-count">
        共 {{ filteredRows.length }} 笔
        <template v-if="filterContract || filterBank">
          （已筛选，全部 {{ computedRows.length }} 笔）
        </template>
      </span>
    </div>

    <!-- ═══ 利息测算表主体 ═══ -->
    <el-table
      :data="filteredRows"
      border
      size="small"
      style="width: 100%"
      :row-class-name="getRowClassName"
      max-height="560"
    >
      <!-- 序号 -->
      <el-table-column type="index" label="#" width="42" align="center" />

      <!-- 借款合同号 -->
      <el-table-column prop="contractNo" label="借款合同号" min-width="130">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input
              :model-value="row.contractNo"
              size="small"
              placeholder="合同号"
              @input="(val: string) => handleFieldChange($index, 'contractNo', val)"
            />
          </template>
          <span v-else>{{ row.contractNo || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 借款银行 -->
      <el-table-column prop="bank" label="借款银行" min-width="110">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input
              :model-value="row.bank"
              size="small"
              placeholder="银行"
              @input="(val: string) => handleFieldChange($index, 'bank', val)"
            />
          </template>
          <span v-else>{{ row.bank || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 借款起始日 -->
      <el-table-column prop="loanStart" label="借款起始日" width="130">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-date-picker
              :model-value="row.loanStart"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              placeholder="起始日"
              style="width: 100%"
              @update:model-value="(val: string) => handleFieldChange($index, 'loanStart', val || '')"
            />
          </template>
          <span v-else>{{ row.loanStart || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 借款讫止日 -->
      <el-table-column prop="loanEnd" label="借款讫止日" width="130">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-date-picker
              :model-value="row.loanEnd"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              placeholder="讫止日"
              style="width: 100%"
              @update:model-value="(val: string) => handleFieldChange($index, 'loanEnd', val || '')"
            />
          </template>
          <span v-else>{{ row.loanEnd || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 起算时点（公式列） -->
      <el-table-column label="起算时点" width="110">
        <template #header>
          <el-tooltip content="起算 = max(报告期起始日, 借款起始日)" placement="top">
            <span class="formula-col-header">起算时点</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip content="max(报告期始, 借款始)" placement="top">
            <span class="formula-cell">{{ row.effectiveStart || '-' }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 截止时点（公式列） -->
      <el-table-column label="截止时点" width="110">
        <template #header>
          <el-tooltip content="截止 = min(借款讫止日, 报告期截止日)" placement="top">
            <span class="formula-col-header">截止时点</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip content="min(借款止, 报告期末)" placement="top">
            <span class="formula-cell">{{ row.effectiveEnd || '-' }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 年利率 -->
      <el-table-column prop="rate" label="年利率" width="90" align="right">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input-number
              :model-value="row.rate * 100"
              :controls="false"
              :precision="4"
              size="small"
              style="width: 100%"
              placeholder="%"
              @change="(val: number | undefined) => handleFieldChange($index, 'rate', (val ?? 0) / 100)"
            />
          </template>
          <span v-else>{{ row.rate ? (row.rate * 100).toFixed(2) + '%' : '-' }}</span>
        </template>
      </el-table-column>

      <!-- 借款本金 -->
      <el-table-column prop="principal" label="借款本金" min-width="120" align="right">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input-number
              :model-value="row.principal"
              :controls="false"
              :precision="2"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleFieldChange($index, 'principal', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.principal) }}</span>
        </template>
      </el-table-column>

      <!-- 账载利息 -->
      <el-table-column prop="bookedInterest" label="账载利息" min-width="110" align="right">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input-number
              :model-value="row.bookedInterest"
              :controls="false"
              :precision="2"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleFieldChange($index, 'bookedInterest', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.bookedInterest) }}</span>
        </template>
      </el-table-column>

      <!-- 计息天数（公式列） -->
      <el-table-column label="计息天数" width="80" align="center">
        <template #header>
          <el-tooltip content="整年=365; 非整年=截止-起算+1" placement="top">
            <span class="formula-col-header">计息天数</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip content="整年取365; 非整年: 截止-起算+1天" placement="top">
            <span class="formula-cell">{{ row.computedDays || '-' }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 测算利息（公式列） -->
      <el-table-column label="测算利息" min-width="110" align="right">
        <template #header>
          <el-tooltip content="测算利息 = 本金 × 年利率 × 天数 / 365" placement="top">
            <span class="formula-col-header">测算利息</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip content="本金×年利率×天数/365" placement="top">
            <span class="formula-cell">{{ fmtAmount(row.computedInterest) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 差异（公式列） -->
      <el-table-column label="差异" min-width="100" align="right">
        <template #header>
          <el-tooltip content="差异 = 测算利息 − 账载利息" placement="top">
            <span class="formula-col-header">差异</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip content="测算利息 − 账载利息" placement="top">
            <span :class="['formula-cell', { 'diff-warning': row.hasDiffWarning }]">
              {{ fmtAmount(row.computedDiff) }}
            </span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
        <template #default="{ $index }">
          <el-button
            text
            type="danger"
            size="small"
            @click="handleRemoveRow($index)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计区 ═══ -->
    <div class="summary-section">
      <div class="summary-grid">
        <div class="summary-item">
          <span class="summary-label">测算利息合计</span>
          <span class="summary-value">{{ fmtAmount(totalCalculatedInterest) }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">账载利息合计</span>
          <span class="summary-value">{{ fmtAmount(totalBookedInterest) }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">总差异</span>
          <span :class="['summary-value', { 'diff-warning': Math.abs(totalDiff) > 0.01 }]">
            {{ fmtAmount(totalDiff) }}
          </span>
        </div>
        <div class="summary-item">
          <span class="summary-label">差异笔数</span>
          <span :class="['summary-value', { 'diff-warning': warningCount > 0 }]">
            {{ warningCount }} 笔
          </span>
        </div>
      </div>
      <!-- 跨底稿联动跳转 -->
      <div class="cross-wp-links">
        <span class="cross-wp-label">联动底稿：</span>
        <GtIndexChip value="L2" :context-project-id="props.projectId" />
        <GtIndexChip value="L8" :context-project-id="props.projectId" />
      </div>
    </div>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>公式基准</strong>：利息 = 本金 × 年利率 × 计息天数 / 365（365天制，致同2025修订版）</li>
        <li><strong>起止裁剪</strong>：起算 = max(报告期始, 借款始)；截止 = min(借款止, 报告期末)</li>
        <li><strong>天数逻辑</strong>：截止-起算差值=365天取365；其他取差值+1天（算头算尾）</li>
        <li><strong>差异高亮</strong>：|测算-账载| > 0.01 元红色高亮，需关注并说明原因</li>
        <li><strong>联动L2/L8</strong>：测算结果通过 EventBus 自动推送至 L2应付利息 和 L8财务费用</li>
        <li><strong>数据来源</strong>：借款信息应与明细表L1-2保持一致（按合同号关联）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L1TabInterestCalc — L1-5 利息测算表（核心！联动L2/L8）
 *
 * 利息测算公式：测算利息 = 本金 × 年利率 × 计息天数 / 365
 * 天数逻辑：整年365/非整年(截止-起算+1)
 * 差异高亮：|差异| > 0.01 红色高亮
 * L2/L8联动：publishInterestCalculated EventBus
 *
 * Spec: .kiro/specs/l1-short-term-loans/
 * Task: 4.4
 * Requirements: 4.1-4.7
 */
import { computed, inject, ref, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import type { useL1FormData } from '@/composables/useL1FormData'
import type { InterestCalcRow } from '@/composables/useL1FormData'
import { useL1InterestCalc, type InterestCalcComputed } from '@/composables/useL1InterestCalc'
import {
  calcStartDate,
  calcEndDate,
  calcInterestDays,
} from '@/composables/useL1InterestEngine'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── Inject formData (由父组件 provide) ──────────────────────────────────────

const formData = inject<ReturnType<typeof useL1FormData>>('l1FormData')!

// ─── 报告期日期（从 formData 或默认取当年） ──────────────────────────────────

const currentYear = new Date().getFullYear()
const reportStart = ref<Date>(new Date(currentYear, 0, 1))  // 1月1日
const reportEnd = ref<Date>(new Date(currentYear, 11, 31)) // 12月31日

// ─── Composable: 利息测算业务逻辑 ───────────────────────────────────────────

const {
  computedRows,
  filteredRows: rawFilteredRows,
  totalCalculatedInterest,
  totalBookedInterest,
  totalDiff,
  warningCount,
  setFilter,
  clearFilter,
  addRow,
  removeRow,
  updateRow,
} = useL1InterestCalc(formData, reportStart, reportEnd)

// ─── Inject 联动发布函数 ─────────────────────────────────────────────────────

const publishInterestCalculated = inject<() => void>(
  'publishInterestCalculated',
  () => { /* noop if not provided */ },
)

// ─── 筛选状态 ────────────────────────────────────────────────────────────────

const filterContract = ref('')
const filterBank = ref('')

function handleFilterChange(): void {
  if (!filterContract.value && !filterBank.value) {
    clearFilter()
  } else {
    setFilter({
      contractNo: filterContract.value || undefined,
      bank: filterBank.value || undefined,
    })
  }
}

// ─── 扩展计算行（附加公式列展示值） ─────────────────────────────────────────

interface DisplayRow extends InterestCalcComputed {
  effectiveStart: string
  effectiveEnd: string
}

const filteredRows = computed<DisplayRow[]>(() => {
  return rawFilteredRows.value.map(row => {
    let effectiveStart = ''
    let effectiveEnd = ''

    const loanStart = row.loanStart ? new Date(row.loanStart) : null
    const loanEnd = row.loanEnd ? new Date(row.loanEnd) : null

    if (loanStart && loanEnd) {
      const start = calcStartDate(loanStart, reportStart.value)
      const end = calcEndDate(loanEnd, reportEnd.value)
      effectiveStart = formatDate(start)
      effectiveEnd = formatDate(end)
    }

    return {
      ...row,
      effectiveStart,
      effectiveEnd,
    }
  })
})

// ─── 字段编辑处理 ────────────────────────────────────────────────────────────

function handleFieldChange(index: number, field: keyof InterestCalcRow, value: string | number): void {
  updateRow(index, field, value)
}

// ─── 新增行 ──────────────────────────────────────────────────────────────────

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入借款合同号',
      '新增利息测算行',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        inputPlaceholder: '如：LOAN-2024-001',
        inputValidator: (val: string) => {
          if (!val?.trim()) return '合同号不能为空'
          return true
        },
      },
    )
    if (value?.trim()) {
      addRow(value.trim(), '')
    }
  } catch {
    // 用户取消
  }
}

// ─── 删除行 ──────────────────────────────────────────────────────────────────

function handleRemoveRow(index: number): void {
  removeRow(index)
}

// ─── Watch: 利息变化时自动发布联动事件 ───────────────────────────────────────

watch(
  totalCalculatedInterest,
  () => {
    publishInterestCalculated()
  },
  { flush: 'post' },
)

// ─── 行样式 ──────────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: DisplayRow }): string {
  if (row.hasDiffWarning) return 'warning-row'
  return ''
}

// ─── 工具函数 ────────────────────────────────────────────────────────────────

function formatDate(date: Date): string {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.l1-tab-interest-calc {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 头部 ─── */
.interest-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.interest-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.interest-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.interest-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

/* ─── 蓝色引导区 ─── */
.guide-area {
  background: linear-gradient(135deg, #ecf5ff 0%, #f0f7ff 100%);
  border: 1px solid #d9ecff;
  border-radius: 8px;
  padding: 14px 18px;
  margin-bottom: 14px;
}

.guide-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 24px;
}

.guide-step {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #409eff;
  line-height: 1.5;
}

.guide-num {
  font-weight: 700;
  font-size: 14px;
  min-width: 18px;
}

/* ─── 方法论上下文（琥珀色左边线+浅黄背景） ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 14px;
  font-size: var(--wp-font-size, 13px);
  color: #5a4e3a;
  line-height: 1.6;
}

.methodology-text strong {
  color: #b88230;
}

/* ─── 筛选区 ─── */
.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.filter-count {
  font-size: 12px;
  color: #909399;
}

/* ─── 公式列表头（虚线下划线 + cursor:help） ─── */
.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}

/* ─── 公式列单元格（虚线下划线 + cursor:help） ─── */
.formula-cell {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
  padding-bottom: 1px;
  display: inline-block;
}

/* ─── 差异高亮 ─── */
.diff-warning {
  color: #f56c6c !important;
  font-weight: 700;
  border-bottom-color: #f56c6c;
}

/* ─── 警告行背景 ─── */
:deep(.warning-row) {
  background-color: #fef0f0 !important;
}

/* ─── 表格统一13px字体 ─── */
:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.el-table th .cell) {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

/* ─── 合计区 ─── */
.summary-section {
  margin-top: 16px;
  padding: 14px 18px;
  background: #f0f9eb;
  border: 1px solid #e1f3d8;
  border-radius: 8px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.summary-label {
  font-size: 12px;
  color: #909399;
}

.summary-value {
  font-size: 15px;
  font-weight: 700;
  color: #303133;
}

/* ─── 跨底稿联动跳转 ─── */
.cross-wp-links {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed #e1f3d8;
  font-size: 12px;
}

.cross-wp-label {
  color: #909399;
}

/* ─── 编制提示折叠 ─── */
.l1-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.l1-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.l1-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
