<template>
  <div class="l1-tab-detail">
    <!-- ═══ 返回目录 + 标题 + 操作栏 ═══ -->
    <div class="detail-header">
      <div class="detail-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">
          ← 返回目录
        </el-button>
        <h3 class="detail-title">L1-2 短期借款明细表</h3>
      </div>
      <div class="detail-header-right">
        <!-- 导入导出 -->
        <el-dropdown trigger="click" :disabled="isReadonly" @command="handleImportExport">
          <el-button size="small" :disabled="isReadonly || isExporting || isImporting">
            导入导出 ▾
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item command="importData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <!-- 新增行 -->
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          @click="handleAddRow"
        >
          + 新增借款
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色：负债类方向说明） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>负债类贷方科目：</strong>
        期末余额 = 期初 + 本期借入（贷方） − 本期归还（借方）。
        明细合计应与审定表L1-1一致。30列按区段切换，行数据全程同步。
      </div>
    </div>

    <!-- ═══ 区段Tab切换（el-segmented / el-radio-group） ═══ -->
    <div class="segment-bar">
      <el-radio-group
        :model-value="activeSegment"
        size="small"
        @change="switchSegment"
      >
        <el-radio-button
          v-for="seg in DETAIL_SEGMENTS"
          :key="seg.key"
          :value="seg.key"
        >
          {{ seg.label }}（{{ seg.fields.length }}列）
        </el-radio-button>
      </el-radio-group>

      <!-- 筛选区 -->
      <div class="filter-area">
        <el-select
          v-model="filterBank"
          placeholder="筛选银行"
          clearable
          size="small"
          style="width: 130px"
          @change="handleFilterChange"
        >
          <el-option
            v-for="b in bankOptions"
            :key="b"
            :label="b"
            :value="b"
          />
        </el-select>
        <el-select
          v-model="filterType"
          placeholder="筛选类型"
          clearable
          size="small"
          style="width: 110px"
          @change="handleFilterChange"
        >
          <el-option v-for="t in loanTypeOptions" :key="t" :label="t" :value="t" />
        </el-select>
        <el-select
          v-model="filterCurrency"
          placeholder="筛选币种"
          clearable
          size="small"
          style="width: 100px"
          @change="handleFilterChange"
        >
          <el-option v-for="c in currencyOptions" :key="c" :label="c" :value="c" />
        </el-select>
      </div>
    </div>

    <!-- ═══ 明细表主体（区段按 segment 显示列） ═══ -->
    <el-table
      :data="displayRows"
      border
      size="small"
      style="width: 100%"
      :row-class-name="getRowClassName"
      max-height="520"
    >
      <!-- 序号固定列 -->
      <el-table-column type="index" label="#" width="45" fixed />

      <!-- ═══ 区段1：借款信息（10列） ═══ -->
      <template v-if="activeSegment === 'basic'">
        <el-table-column prop="bank" label="借款银行" min-width="120">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.bank"
              size="small"
              @change="(val: string) => handleCellUpdate($index, 'bank', val)"
            />
            <span v-else class="cell-text">{{ row.bank }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="contractNo" label="合同号" min-width="130">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.contractNo"
              size="small"
              @change="(val: string) => handleCellUpdate($index, 'contractNo', val)"
            />
            <span v-else>{{ row.contractNo }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="loanType" label="借款类型" min-width="100">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.loanType"
              size="small"
              placeholder="选择"
              @change="(val: string) => handleCellUpdate($index, 'loanType', val)"
            >
              <el-option label="信用" value="信用" />
              <el-option label="保证" value="保证" />
              <el-option label="抵押" value="抵押" />
              <el-option label="质押" value="质押" />
            </el-select>
            <span v-else>{{ row.loanType }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="amount" label="借款金额" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.amount"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleCellUpdate($index, 'amount', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rate" label="年利率(%)" min-width="90" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.rate"
              :controls="false"
              :precision="4"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleCellUpdate($index, 'rate', val ?? 0)"
            />
            <span v-else>{{ row.rate ? (row.rate * 100).toFixed(2) + '%' : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="startDate" label="起始日" min-width="120">
          <template #default="{ row, $index }">
            <el-date-picker
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.startDate"
              type="date"
              format="YYYY-MM-DD"
              value-format="YYYY-MM-DD"
              size="small"
              style="width: 100%"
              @change="(val: string) => handleCellUpdate($index, 'startDate', val || '')"
            />
            <span v-else>{{ row.startDate }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="endDate" label="到期日" min-width="120">
          <template #default="{ row, $index }">
            <el-date-picker
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.endDate"
              type="date"
              format="YYYY-MM-DD"
              value-format="YYYY-MM-DD"
              size="small"
              style="width: 100%"
              @change="(val: string) => handleCellUpdate($index, 'endDate', val || '')"
            />
            <span v-else>{{ row.endDate }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="purpose" label="用途" min-width="120">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.purpose"
              size="small"
              @change="(val: string) => handleCellUpdate($index, 'purpose', val)"
            />
            <span v-else>{{ row.purpose || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="guarantee" label="担保方式" min-width="100">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.guarantee"
              size="small"
              @change="(val: string) => handleCellUpdate($index, 'guarantee', val)"
            />
            <span v-else>{{ row.guarantee || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="currency" label="币种" min-width="80">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.currency"
              size="small"
              @change="(val: string) => handleCellUpdate($index, 'currency', val)"
            >
              <el-option label="CNY" value="CNY" />
              <el-option label="USD" value="USD" />
              <el-option label="EUR" value="EUR" />
              <el-option label="HKD" value="HKD" />
            </el-select>
            <span v-else>{{ row.currency }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段2：期间变动（3列） ═══ -->
      <template v-if="activeSegment === 'movement'">
        <el-table-column prop="beginning" label="期初余额" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.beginning"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleCellUpdate($index, 'beginning', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.beginning) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="creditAmount" label="贷方(借入)" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.creditAmount"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleCellUpdate($index, 'creditAmount', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="debitAmount" label="借方(归还)" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.debitAmount"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleCellUpdate($index, 'debitAmount', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段3：期末余额（1列公式列） ═══ -->
      <template v-if="activeSegment === 'balance'">
        <el-table-column label="期末余额" min-width="150" align="right">
          <template #header>
            <el-tooltip content="期末 = 期初 + 贷方(借入) − 借方(归还)（负债类！）" placement="top">
              <span class="formula-col-header">期末余额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="期末 = 期初 + 贷方 − 借方" placement="top">
              <span class="formula-cell">{{ fmtAmount(row.endBalance) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列（非readonly时显示） -->
      <el-table-column
        v-if="!isReadonly"
        label="操作"
        width="60"
        fixed="right"
        align="center"
      >
        <template #default="{ $index, row }">
          <el-button
            v-if="!row._isTotal"
            type="danger"
            text
            size="small"
            @click="handleRemoveRow($index)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计行信息 + 勾稽校验 ═══ -->
    <div class="detail-footer">
      <div class="total-info">
        <span>合计期末余额：<strong>{{ fmtAmount(totalEndBalance) }}</strong></span>
        <span class="row-count">（共 {{ filteredRows.length }} 笔借款）</span>
      </div>
      <div class="cross-check-row">
        <span class="cross-check-label">与审定表L1-1交叉验证：</span>
        <span :class="crossCheckClass">
          <template v-if="crossCheckResult.isMatch">✓ 匹配</template>
          <template v-else>✗ 差额 {{ fmtAmount(crossCheckResult.diff) }}</template>
        </span>
      </div>
    </div>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>区段切换</strong>：30列按「借款信息/期间变动/期末余额」三区段Tab切换，行数据全程同步</li>
        <li><strong>负债类公式</strong>：期末余额 = 期初 + 贷方(借入) − 借方(归还)，与资产类方向相反</li>
        <li><strong>动态行</strong>：点击"新增借款"输入银行名称后创建新行</li>
        <li><strong>导入导出</strong>：支持导出模板/导出数据/导入数据（xlsx格式）</li>
        <li><strong>勾稽</strong>：明细合计应与审定表L1-1期末合计一致；明细与L1-5利息测算按合同号对应</li>
      </ul>
    </details>

    <!-- 隐藏的文件上传input -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".xlsx,.xls"
      style="display: none"
      @change="handleFileSelected"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * L1TabDetail — L1-2 短期借款明细表
 *
 * 30列宽表按区段Tab切换（借款信息/期间变动/期末余额），行同步。
 * - 区段1「借款信息」10列：银行/合同号/类型/金额/利率/起始日/到期日/用途/担保/币种
 * - 区段2「期间变动」3列：期初/贷方(借入)/借方(归还)
 * - 区段3「期末余额」1列：期末（公式列=期初+贷-借，负债类！）
 * - 动态行：ElMessageBox.prompt 输入银行名称后新增
 * - 导入导出：el-dropdown 三级（模板/数据/导入）
 * - 排序/筛选：按银行/类型/币种筛选
 * - 与审定表L1-1合计交叉验证
 *
 * Spec: .kiro/specs/l1-short-term-loans/
 * Task: 4.3
 * Requirements: 3.1-3.6
 */
import { computed, inject, ref, type Ref } from 'vue'
import type { useL1FormData } from '@/composables/useL1FormData'
import type { DetailRow } from '@/composables/useL1FormData'
import { useL1Detail, DETAIL_SEGMENTS } from '@/composables/useL1Detail'
import { useL1ImportExport } from '@/composables/useL1ImportExport'
import type { AdjudicationVsDetailResult } from '@/composables/useL1CrossSheet'

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

// ─── Composable: 明细表业务逻辑 ─────────────────────────────────────────────

const {
  activeSegment,
  switchSegment,
  filteredRows,
  filterConfig,
  setFilter,
  clearFilter,
  computedRows,
  totalEndBalance,
  addRow,
  removeRow,
  updateRow,
} = useL1Detail(formData)

// ─── Composable: 导入导出 ────────────────────────────────────────────────────

const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const { exportTemplate, exportData, importData, isExporting, isImporting } =
  useL1ImportExport(wpIdRef, projectIdRef)

// ─── Inject 勾稽校验 ─────────────────────────────────────────────────────────

const adjudicationVsDetail = inject<Ref<AdjudicationVsDetailResult>>(
  'adjudicationVsDetail',
  computed(() => ({ diff: 0, isMatch: true })) as unknown as Ref<AdjudicationVsDetailResult>,
)

const crossCheckResult = computed<AdjudicationVsDetailResult>(() => adjudicationVsDetail.value)

const crossCheckClass = computed(() => ({
  'cross-check-match': crossCheckResult.value.isMatch,
  'cross-check-diff': !crossCheckResult.value.isMatch,
}))

// ─── 筛选状态 ────────────────────────────────────────────────────────────────

const filterBank = ref<string>('')
const filterType = ref<string>('')
const filterCurrency = ref<string>('')

/** 可选银行列表（从数据中提取） */
const bankOptions = computed(() => {
  const banks = new Set<string>()
  for (const row of formData.detailRows.value) {
    if (row.bank) banks.add(row.bank)
  }
  return [...banks].sort()
})

/** 可选借款类型 */
const loanTypeOptions = computed(() => {
  const types = new Set<string>()
  for (const row of formData.detailRows.value) {
    if (row.loanType) types.add(row.loanType)
  }
  return [...types].sort()
})

/** 可选币种 */
const currencyOptions = computed(() => {
  const currencies = new Set<string>()
  for (const row of formData.detailRows.value) {
    if (row.currency) currencies.add(row.currency)
  }
  return [...currencies].sort()
})

function handleFilterChange(): void {
  setFilter({
    bank: filterBank.value || undefined,
    loanType: filterType.value || undefined,
    currency: filterCurrency.value || undefined,
  })
}

// ─── 表格数据（含合计行） ────────────────────────────────────────────────────

interface DisplayRow extends DetailRow {
  _isTotal: boolean
}

const displayRows = computed<DisplayRow[]>(() => {
  const rows: DisplayRow[] = filteredRows.value.map(row => {
    // 从 computedRows 获取带有正确 endBalance 的行
    const computed = computedRows.value.find(
      cr => cr.bank === row.bank && cr.contractNo === row.contractNo,
    )
    return {
      ...row,
      endBalance: computed?.endBalance ?? row.endBalance,
      _isTotal: false,
    }
  })

  // 合计行
  rows.push({
    bank: '合  计',
    contractNo: '',
    loanType: '',
    amount: rows.reduce((s, r) => s + r.amount, 0),
    rate: 0,
    startDate: '',
    endDate: '',
    purpose: '',
    guarantee: '',
    beginning: rows.reduce((s, r) => s + r.beginning, 0),
    creditAmount: rows.reduce((s, r) => s + r.creditAmount, 0),
    debitAmount: rows.reduce((s, r) => s + r.debitAmount, 0),
    endBalance: totalEndBalance.value,
    currency: '',
    _isTotal: true,
  })

  return rows
})

// ─── 行样式 ──────────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: DisplayRow }): string {
  if (row._isTotal) return 'total-row'
  return ''
}

// ─── 编辑处理 ────────────────────────────────────────────────────────────────

function handleCellUpdate(index: number, field: keyof DetailRow, value: string | number): void {
  // 排除合计行
  if (index >= filteredRows.value.length) return
  // 找到原始行索引（筛选后index与原始可能不同）
  const targetRow = filteredRows.value[index]
  const originalIndex = formData.detailRows.value.indexOf(targetRow)
  if (originalIndex < 0) return
  updateRow(originalIndex, field, value)
}

// ─── 动态行操作 ──────────────────────────────────────────────────────────────

async function handleAddRow(): Promise<void> {
  await addRow()
}

function handleRemoveRow(index: number): void {
  if (index >= filteredRows.value.length) return
  const targetRow = filteredRows.value[index]
  const originalIndex = formData.detailRows.value.indexOf(targetRow)
  if (originalIndex < 0) return
  removeRow(originalIndex)
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────

const fileInputRef = ref<HTMLInputElement | null>(null)

function handleImportExport(command: string): void {
  switch (command) {
    case 'exportTemplate':
      exportTemplate('L1-2')
      break
    case 'exportData':
      exportData('L1-2')
      break
    case 'importData':
      fileInputRef.value?.click()
      break
  }
}

async function handleFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  const result = await importData(file, 'L1-2')
  if (result) {
    // 重新加载数据
    await formData.selfLoad()
  }
  // 清空文件选择，允许重复导入同一文件
  input.value = ''
}

// ─── 金额格式化 ──────────────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.l1-tab-detail {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 头部 ─── */
.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.detail-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.detail-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.detail-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

/* ─── 方法论上下文（琥珀色左边线+浅黄背景） ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
  font-size: var(--wp-font-size, 13px);
  color: #5a4e3a;
  line-height: 1.6;
}

.methodology-text strong {
  color: #b88230;
}

/* ─── 区段切换栏 ─── */
.segment-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}

.filter-area {
  display: flex;
  align-items: center;
  gap: 6px;
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

/* ─── 表格统一13px字体 ─── */
:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.el-table th .cell) {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

/* ─── 合计行样式 ─── */
:deep(.total-row) {
  background-color: #f0f9eb !important;
  font-weight: 700;
}

/* ─── 底部合计+勾稽 ─── */
.detail-footer {
  margin-top: 16px;
  padding: 10px 14px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.total-info {
  font-size: var(--wp-font-size, 13px);
  color: #303133;
}

.total-info strong {
  color: #409eff;
}

.row-count {
  color: #909399;
  margin-left: 6px;
}

.cross-check-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--wp-font-size, 13px);
}

.cross-check-label {
  color: #606266;
}

.cross-check-match {
  color: #67c23a;
  font-weight: 600;
}

.cross-check-diff {
  color: #f56c6c;
  font-weight: 600;
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

/* ─── 单元格文本 ─── */
.cell-text {
  font-weight: 500;
}
</style>
