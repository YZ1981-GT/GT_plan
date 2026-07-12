<template>
  <div class="l3-tab-interest-calc">
    <!-- ═══ Header: title + 发布利息 + 导入导出 + AI/复核 ═══ -->
    <div class="l3-interest-header">
      <div class="l3-interest-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">
          ← 返回目录
        </el-button>
        <h3 class="l3-interest-title">L3-5 利息测算表</h3>
        <GtIndexChip value="L2" :context-project-id="props.projectId" />
        <GtIndexChip value="L8" :context-project-id="props.projectId" />
      </div>
      <div class="l3-interest-header-right">
        <el-button
          v-if="!isReadonly"
          size="small"
          type="success"
          @click="handlePublish"
        >
          发布利息
        </el-button>
        <!-- 导入导出三级 dropdown -->
        <el-dropdown v-if="!isReadonly" size="small" trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="triggerImport">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" circle title="AI辅助">🤖</el-button>
        <el-button size="small" circle title="复核">✓</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="l3-methodology-context">
      <div class="l3-methodology-text">
        <strong>利息测算公式（365天制）：</strong>
        利息 = 本金 × 年利率 × 天数 / 365，测算利息合计联动L2应付利息/L8财务费用。
        <strong>差异 = 测算利息 − 账载利息</strong>，超阈值红色高亮提示异常。
      </div>
    </div>

    <!-- ═══ 按合同号筛选 ═══ -->
    <div class="l3-filter-bar">
      <el-select
        v-model="filterContractNo"
        placeholder="按合同号筛选"
        clearable
        filterable
        size="small"
        style="width: 200px"
        @change="handleFilterChange"
      >
        <el-option
          v-for="c in contractOptions"
          :key="c"
          :label="c"
          :value="c"
        />
      </el-select>
      <span class="l3-filter-count">
        共 {{ filteredRows.length }} 笔
        <template v-if="filterContractNo">
          （已筛选，全部 {{ computedRows.length }} 笔）
        </template>
      </span>
      <el-button
        v-if="!isReadonly"
        size="small"
        type="primary"
        @click="handleAddRow"
      >
        + 新增测算行
      </el-button>
    </div>

    <!-- ═══ 利息测算表主体 ═══ -->
    <el-table
      :data="filteredRows"
      border
      size="small"
      style="width: 100%"
      :row-class-name="getRowClassName"
      show-summary
      :summary-method="getSummary"
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
      <el-table-column prop="bank" label="银行" min-width="100">
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

      <!-- 本金 -->
      <el-table-column prop="principal" label="本金" min-width="120" align="right">
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

      <!-- 年利率 -->
      <el-table-column prop="annualRate" label="年利率" width="90" align="right">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input-number
              :model-value="row.annualRate * 100"
              :controls="false"
              :precision="4"
              size="small"
              style="width: 100%"
              placeholder="%"
              @change="(val: number | undefined) => handleFieldChange($index, 'annualRate', (val ?? 0) / 100)"
            />
          </template>
          <span v-else>{{ row.annualRate ? (row.annualRate * 100).toFixed(2) + '%' : '-' }}</span>
        </template>
      </el-table-column>

      <!-- 计息起始日 -->
      <el-table-column prop="loanStart" label="计息起始日" width="130">
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

      <!-- 计息天数（公式列） -->
      <el-table-column label="计息天数" width="80" align="center">
        <template #header>
          <el-tooltip content="整年=365; 非整年=截止-起算+1" placement="top">
            <span class="l3-formula-col-header">计息天数</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip content="max(报告期始,借款始)~min(借款止,报告期末)" placement="top">
            <span class="l3-formula-cell">{{ row.computedDays || '-' }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 测算利息（公式列） -->
      <el-table-column label="测算利息" min-width="110" align="right">
        <template #header>
          <el-tooltip content="测算利息 = 本金 × 年利率 × 天数 / 365" placement="top">
            <span class="l3-formula-col-header">测算利息</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip content="本金×年利率×天数/365" placement="top">
            <span class="l3-formula-cell">{{ fmtAmount(row.computedInterest) }}</span>
          </el-tooltip>
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

      <!-- 差异（公式列） -->
      <el-table-column label="差异" min-width="100" align="right">
        <template #header>
          <el-tooltip content="差异 = 测算利息 − 账载利息" placement="top">
            <span class="l3-formula-col-header">差异</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip content="测算利息 − 账载利息" placement="top">
            <span :class="['l3-formula-cell', { 'l3-diff-warning': row.hasDiffWarning }]">
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

    <!-- ═══ 合计区 + 跨底稿联动 ═══ -->
    <div class="l3-summary-section">
      <div class="l3-summary-grid">
        <div class="l3-summary-item">
          <span class="l3-summary-label">本金合计</span>
          <span class="l3-summary-value">{{ fmtAmount(totalPrincipal) }}</span>
        </div>
        <div class="l3-summary-item">
          <span class="l3-summary-label">测算利息合计</span>
          <span class="l3-summary-value">{{ fmtAmount(totalCalculatedInterest) }}</span>
        </div>
        <div class="l3-summary-item">
          <span class="l3-summary-label">账载利息合计</span>
          <span class="l3-summary-value">{{ fmtAmount(totalBookedInterest) }}</span>
        </div>
        <div class="l3-summary-item">
          <span class="l3-summary-label">差异合计</span>
          <span :class="['l3-summary-value', { 'l3-diff-warning': Math.abs(totalDiff) > 0.01 }]">
            {{ fmtAmount(totalDiff) }}
          </span>
        </div>
      </div>
      <div class="l3-cross-wp-links">
        <span class="l3-cross-wp-label">cross_wp_ref 联动：</span>
        <GtIndexChip value="L2" :context-project-id="props.projectId" />
        <span class="l3-cross-wp-desc">应付利息</span>
        <GtIndexChip value="L8" :context-project-id="props.projectId" />
        <span class="l3-cross-wp-desc">财务费用</span>
      </div>
    </div>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l3-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>公式基准</strong>：利息 = 本金 × 年利率 × 计息天数 / 365（365天制）</li>
        <li><strong>天数逻辑</strong>：起算=max(报告期始,借款始), 截止=min(借款止,报告期末), 整年365/非整年差值+1</li>
        <li><strong>差异高亮</strong>：|测算-账载| > 0.01 元红色高亮</li>
        <li><strong>发布联动</strong>：点击"发布利息"按钮将测算合计推送至L2应付利息、L8财务费用</li>
        <li><strong>导入</strong>：支持xlsx批量导入合同利息信息（导入导出▾→导入数据）</li>
      </ul>
    </details>

    <!-- 隐藏文件input用于导入 -->
    <input
      ref="importFileRef"
      type="file"
      accept=".xlsx,.xls"
      style="display: none"
      @change="handleImportFile"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * L3TabInterestCalc — L3-5 利息测算表（核心！联动L2/L8）
 *
 * 利息测算公式：测算利息 = 本金 × 年利率 × 计息天数 / 365
 * 差异高亮：|差异| > 0.01 红色高亮
 * EventBus publish 'l3:interest-calculated' → L2/L8
 * cross_wp_ref: L2应付利息 / L8财务费用
 *
 * Spec: .kiro/specs/l3-long-term-loans/
 * Task: 4.4
 * Requirements: 4.1-4.6
 */
import { computed, inject, ref, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useL3InterestCalc, type L3InterestCalcRow } from '@/composables/useL3InterestCalc'
import { useL3ImportExport } from '@/composables/useL3ImportExport'
import type { useL3FormData } from '@/components/workpaper/composables/useL3FormData'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── Inject l3FormData ───────────────────────────────────────────────────────

const formData = inject<ReturnType<typeof useL3FormData>>('l3FormData')!

// ─── Reactive interest rows (data source) ────────────────────────────────────

const interestRows = ref<L3InterestCalcRow[]>([])

// ─── 报告期（默认当年） ──────────────────────────────────────────────────────

const currentYear = new Date().getFullYear()
const reportStart = ref(`${currentYear}-01-01`)
const reportEnd = ref(`${currentYear}-12-31`)

// ─── Composable: 利息测算 ────────────────────────────────────────────────────

const {
  computedRows,
  filteredRows: rawFilteredRows,
  totalCalculatedInterest,
  totalBookedInterest,
  totalDiff,
  setFilter,
  clearFilter,
  addRow,
  removeRow,
  updateRow,
  publishInterestCalculated,
} = useL3InterestCalc(formData, interestRows, reportStart, reportEnd)

// ─── Composable: 导入导出三级 (sheet='L3-5') ─────────────────────────────────

const wpIdRef = toRef(props, 'wpId')
const projectIdRef = toRef(props, 'projectId')

const {
  exportTemplate,
  exportData,
  importData,
} = useL3ImportExport(wpIdRef, projectIdRef)

// ─── 按合同号筛选 ────────────────────────────────────────────────────────────

const filterContractNo = ref('')

/** 合同号选项（去重） */
const contractOptions = computed(() => {
  const set = new Set<string>()
  interestRows.value.forEach(r => {
    if (r.contractNo) set.add(r.contractNo)
  })
  return Array.from(set).sort()
})

/** 筛选后的行 */
const filteredRows = computed(() => rawFilteredRows.value)

function handleFilterChange(): void {
  if (!filterContractNo.value) {
    clearFilter()
  } else {
    setFilter({ contractNo: filterContractNo.value })
  }
}

// ─── 本金合计 ────────────────────────────────────────────────────────────────

const totalPrincipal = computed(() => {
  return computedRows.value.reduce((sum, r) => sum + r.principal, 0)
})

// ─── 字段编辑 ────────────────────────────────────────────────────────────────

function handleFieldChange(index: number, field: keyof L3InterestCalcRow, value: string | number): void {
  updateRow(index, field, value)
}

// ─── 新增行（ElMessageBox.prompt：合同号+银行） ──────────────────────────────

async function handleAddRow(): Promise<void> {
  try {
    const { value: contractNo } = await ElMessageBox.prompt(
      '请输入借款合同号',
      '新增利息测算行',
      {
        confirmButtonText: '下一步',
        cancelButtonText: '取消',
        inputPlaceholder: '如：LTL-2024-001',
        inputValidator: (val: string) => {
          if (!val?.trim()) return '合同号不能为空'
          return true
        },
      },
    )
    if (!contractNo?.trim()) return

    const { value: bank } = await ElMessageBox.prompt(
      '请输入借款银行',
      '新增利息测算行',
      {
        confirmButtonText: '确认新增',
        cancelButtonText: '取消',
        inputPlaceholder: '如：中国银行',
        inputValidator: (val: string) => {
          if (!val?.trim()) return '银行名称不能为空'
          return true
        },
      },
    )
    if (bank?.trim()) {
      addRow(contractNo.trim(), bank.trim())
    }
  } catch {
    // 用户取消
  }
}

// ─── 删除行 ──────────────────────────────────────────────────────────────────

function handleRemoveRow(index: number): void {
  removeRow(index)
}

// ─── 发布利息测算（EventBus） ────────────────────────────────────────────────

function handlePublish(): void {
  publishInterestCalculated()
  ElMessage.success(`已发布利息测算结果：合计测算利息 ${fmtAmount(totalCalculatedInterest.value)}`)
}

// ─── 导入导出处理 ────────────────────────────────────────────────────────────

const importFileRef = ref<HTMLInputElement | null>(null)

function handleExportTemplate(): void {
  exportTemplate('L3-5')
}

function handleExportData(): void {
  exportData('L3-5')
}

function triggerImport(): void {
  importFileRef.value?.click()
}

async function handleImportFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  await importData(file, 'L3-5')
  // reset input
  input.value = ''
}

// ─── 行样式（差异高亮红色背景） ──────────────────────────────────────────────

function getRowClassName({ row }: { row: any }): string {
  if (row.hasDiffWarning) return 'l3-warning-row'
  return ''
}

// ─── 合计行方法 ──────────────────────────────────────────────────────────────

function getSummary({ columns }: { columns: any[]; data: any[] }) {
  const sums: string[] = []
  columns.forEach((col, index) => {
    if (index === 0) { sums[index] = '合计'; return }
    if (index === 1 || index === 2) { sums[index] = ''; return }
    const prop = col.property
    if (prop === 'principal') {
      sums[index] = fmtAmount(totalPrincipal.value)
    } else if (col.label === '测算利息') {
      sums[index] = fmtAmount(totalCalculatedInterest.value)
    } else if (prop === 'bookedInterest') {
      sums[index] = fmtAmount(totalBookedInterest.value)
    } else if (col.label === '差异') {
      sums[index] = fmtAmount(totalDiff.value)
    } else {
      sums[index] = ''
    }
  })
  return sums
}

// ─── 工具函数 ────────────────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.l3-tab-interest-calc {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── Header ─── */
.l3-interest-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.l3-interest-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.l3-interest-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.l3-interest-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

/* ─── 方法论上下文（琥珀色左边线+浅黄背景） ─── */
.l3-methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 14px;
  font-size: var(--wp-font-size, 13px);
  color: #5a4e3a;
  line-height: 1.6;
}

.l3-methodology-text strong {
  color: #b88230;
}

/* ─── 筛选区 ─── */
.l3-filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.l3-filter-count {
  font-size: 12px;
  color: #909399;
}

/* ─── 公式列表头（虚线下划线 + cursor:help） ─── */
.l3-formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}

/* ─── 公式列单元格 ─── */
.l3-formula-cell {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
  padding-bottom: 1px;
  display: inline-block;
}

/* ─── 差异高亮（红色） ─── */
.l3-diff-warning {
  color: #f56c6c !important;
  font-weight: 700;
  border-bottom-color: #f56c6c;
}

/* ─── 警告行背景 ─── */
:deep(.l3-warning-row) {
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
.l3-summary-section {
  margin-top: 16px;
  padding: 14px 18px;
  background: #f0f9eb;
  border: 1px solid #e1f3d8;
  border-radius: 8px;
}

.l3-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.l3-summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.l3-summary-label {
  font-size: 12px;
  color: #909399;
}

.l3-summary-value {
  font-size: 15px;
  font-weight: 700;
  color: #303133;
}

/* ─── 跨底稿联动 ─── */
.l3-cross-wp-links {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed #e1f3d8;
  font-size: 12px;
}

.l3-cross-wp-label {
  color: #909399;
}

.l3-cross-wp-desc {
  color: #606266;
  font-size: 12px;
}

/* ─── 编制提示折叠 ─── */
.l3-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.l3-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.l3-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
