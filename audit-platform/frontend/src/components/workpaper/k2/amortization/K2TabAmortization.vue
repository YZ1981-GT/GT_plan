<template>
  <div class="k2-tab-amortization">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>
        <b>CAS14合同取得成本摊销测算：</b>
        直线法 = 取得成本 ÷ 摊销期总月数 × 本期月数；进度法 = 取得成本 × (本期履约进度 - 上期履约进度)。
        逐合同独立计算测算摊销额，与企业账面核对差异，超过重要性水平的差异标红提示调整。
      </p>
    </div>

    <!-- 区段Tab -->
    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>K2-5 摊销测算表</span>
          <div class="title-actions">
            <!-- Cross-validation badge -->
            <el-tag
              v-if="crossValidation"
              :type="crossValidation.isMatch ? 'success' : 'danger'"
              size="small"
              effect="plain"
              class="cross-badge"
            >
              K2-4↔K2-5 {{ crossValidation.isMatch ? '✓一致' : `差异${fmtAmt(crossValidation.diff)}` }}
            </el-tag>

            <!-- 重要性水平 -->
            <el-input-number
              v-model="materiality"
              :controls="false"
              :min="0"
              :precision="2"
              size="small"
              :disabled="isReadonly"
              placeholder="重要性水平"
              class="materiality-input"
              @change="handleMaterialityChange"
            />
            <span class="materiality-label">重要性水平</span>

            <!-- 导入导出 -->
            <el-dropdown trigger="click" :disabled="isReadonly" @command="handleImportExport">
              <el-button size="small">
                导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
                  <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
                  <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </template>

      <!-- el-segmented 区段切换 -->
      <div class="segment-bar">
        <el-segmented
          v-model="activeSection"
          :options="sectionOptions"
          size="default"
          @change="handleSectionChange"
        />
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          @click="handleAddRow"
        >+ 新增行</el-button>
      </div>

      <!-- 表格 -->
      <el-table
        :data="rows"
        border
        stripe
        size="small"
        max-height="520"
        class="amort-table"
        :row-class-name="getRowClassName"
      >
        <el-table-column type="index" label="#" width="40" fixed />

        <!-- 基础区段列 -->
        <template v-if="activeSection === 0">
          <el-table-column prop="contractNo" label="合同编号" width="130" show-overflow-tooltip>
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                v-model="row.contractNo"
                size="small"
                class="cell-input"
                @change="handleCellChange(row.rowId, 'contractNo', $event)"
              />
              <span v-else>{{ row.contractNo }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="cost" label="取得成本" width="130" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.cost"
                :controls="false"
                size="small"
                :min="0"
                :precision="2"
                class="cell-input"
                @change="handleCellChange(row.rowId, 'cost', $event)"
              />
              <span v-else class="amount-cell">{{ fmtAmt(row.cost) }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="method" label="摊销方法" width="120" align="center">
            <template #default="{ row }">
              <el-segmented
                v-if="!isReadonly"
                :model-value="row.method"
                :options="methodOptions"
                size="small"
                class="method-segmented"
                @change="handleMethodSwitch(row.rowId, $event as string)"
              />
              <span v-else>{{ row.method }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="totalPeriods" label="摊销期(月)" width="100" align="center">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.totalPeriods"
                :controls="false"
                size="small"
                :min="0"
                :max="600"
                class="cell-input"
                @change="handleCellChange(row.rowId, 'totalPeriods', $event)"
              />
              <span v-else>{{ row.totalPeriods }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="currentPeriods" label="本期期数(月)" width="110" align="center">
            <template #header>
              <el-tooltip content="直线法使用：本期计提摊销的月数" placement="top">
                <span class="formula-header">本期期数(月)</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.currentPeriods"
                :controls="false"
                size="small"
                :min="0"
                :max="600"
                class="cell-input"
                @change="handleCellChange(row.rowId, 'currentPeriods', $event)"
              />
              <span v-else>{{ row.currentPeriods }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="startDate" label="起始日" width="130">
            <template #default="{ row }">
              <el-date-picker
                v-if="!isReadonly"
                v-model="row.startDate"
                type="date"
                size="small"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                class="cell-input"
                @change="handleCellChange(row.rowId, 'startDate', $event)"
              />
              <span v-else>{{ row.startDate }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="currentProgress" label="本期进度" width="100" align="center">
            <template #header>
              <el-tooltip content="进度法使用：本期累计履约进度(0~100%)" placement="top">
                <span class="formula-header">本期进度</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.currentProgress"
                :controls="false"
                size="small"
                :min="0"
                :max="1"
                :step="0.01"
                :precision="4"
                class="cell-input"
                @change="handleCellChange(row.rowId, 'currentProgress', $event)"
              />
              <span v-else class="percent-cell">{{ fmtPercent(row.currentProgress) }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="priorProgress" label="上期进度" width="100" align="center">
            <template #header>
              <el-tooltip content="进度法使用：上期累计履约进度(0~100%)" placement="top">
                <span class="formula-header">上期进度</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.priorProgress"
                :controls="false"
                size="small"
                :min="0"
                :max="1"
                :step="0.01"
                :precision="4"
                class="cell-input"
                @change="handleCellChange(row.rowId, 'priorProgress', $event)"
              />
              <span v-else class="percent-cell">{{ fmtPercent(row.priorProgress) }}</span>
            </template>
          </el-table-column>
        </template>

        <!-- 测算区段列 -->
        <template v-if="activeSection === 1">
          <el-table-column prop="contractNo" label="合同编号" width="130" fixed show-overflow-tooltip>
            <template #default="{ row }">
              <span>{{ row.contractNo }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="calculatedAmort" label="本期应摊销" width="140" align="right">
            <template #header>
              <el-tooltip content="直线:cost/总期×本期期数; 进度:cost×(本期进度-上期进度)" placement="top">
                <span class="formula-header">本期应摊销</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span class="formula-cell">{{ fmtAmt(row.calculatedAmort) }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="accumulatedAmort" label="累计摊销" width="130" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.accumulatedAmort"
                :controls="false"
                size="small"
                :min="0"
                :precision="2"
                class="cell-input"
                @change="handleCellChange(row.rowId, 'accumulatedAmort', $event)"
              />
              <span v-else class="amount-cell">{{ fmtAmt(row.accumulatedAmort) }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="amortizedBalance" label="摊余成本" width="140" align="right">
            <template #header>
              <el-tooltip content="取得成本 - 累计摊销" placement="top">
                <span class="formula-header">摊余成本</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span class="formula-cell">{{ fmtAmt(row.amortizedBalance) }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="bookedAmort" label="企业摊销" width="130" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.bookedAmort"
                :controls="false"
                size="small"
                :precision="2"
                class="cell-input"
                @change="handleCellChange(row.rowId, 'bookedAmort', $event)"
              />
              <span v-else class="amount-cell">{{ fmtAmt(row.bookedAmort) }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="variance" label="差异" width="120" align="right">
            <template #header>
              <el-tooltip content="测算摊销 - 企业摊销" placement="top">
                <span class="formula-header">差异</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span
                :class="['formula-cell', { 'variance-danger': isVarianceExceeded(row.rowId) }]"
              >{{ fmtAmt(row.variance) }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="conclusion" label="结论" width="130">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                v-model="row.conclusion"
                size="small"
                clearable
                placeholder="请选择"
                class="cell-input"
                @change="handleCellChange(row.rowId, 'conclusion', $event)"
              >
                <el-option
                  v-for="opt in conclusionOptions"
                  :key="opt"
                  :label="opt"
                  :value="opt"
                />
              </el-select>
              <el-tag
                v-else-if="row.conclusion"
                :type="getConclTagType(row.conclusion)"
                size="small"
              >{{ row.conclusion }}</el-tag>
            </template>
          </el-table-column>

          <el-table-column prop="remark" label="备注" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                v-model="row.remark"
                size="small"
                class="cell-input"
                @change="handleCellChange(row.rowId, 'remark', $event)"
              />
              <span v-else>{{ row.remark }}</span>
            </template>
          </el-table-column>
        </template>

        <!-- 操作列 -->
        <el-table-column v-if="!isReadonly" label="操作" width="60" fixed="right" align="center">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="handleRemoveRow(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 底部合计行 -->
      <div class="subtotal-bar">
        <span class="subtotal-label">合计（{{ subtotals.count }} 行）：</span>
        <span class="subtotal-item">取得成本 <b>{{ fmtAmt(subtotals.cost) }}</b></span>
        <span class="subtotal-item">测算摊销 <b>{{ fmtAmt(subtotals.calculatedAmort) }}</b></span>
        <span class="subtotal-item">累计摊销 <b>{{ fmtAmt(subtotals.accumulatedAmort) }}</b></span>
        <span class="subtotal-item">摊余成本 <b>{{ fmtAmt(subtotals.amortizedBalance) }}</b></span>
        <span class="subtotal-item">企业摊销 <b>{{ fmtAmt(subtotals.bookedAmort) }}</b></span>
        <span class="subtotal-item" :class="{ 'variance-danger-text': Math.abs(subtotals.variance) > materiality && materiality > 0 }">
          差异合计 <b>{{ fmtAmt(subtotals.variance) }}</b>
        </span>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * K2TabAmortization.vue — K2-5 摊销测算表
 *
 * 28列 × 最多66行，37公式列，2区段Tab切换(基础/测算)。
 * 直线法/进度法 per-row el-segmented 切换。
 * 差异>重要性水平 → 红色高亮。
 * 66行使用 el-table max-height 原生滚动。
 *
 * Spec: .kiro/specs/k2-other-current-assets/
 * Task: 4.5
 * Requirements: 5.1-5.7
 */
import { ref, computed, toRef, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { fmtAmount } from '@/utils/formatters'
import {
  useK2Amortization,
  K2_AMORT_SECTION_LABELS,
  type K2AmortMethod,
  type K2AmortSection,
} from '../../composables/useK2Amortization'
import { useK2CrossSheet } from '../../composables/useK2CrossSheet'
import { useK2ImportExport } from '../../composables/useK2ImportExport'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── Composable Integration ──────────────────────────────────────────────────

const allResponsesRef = toRef(props, 'allResponses')

const {
  rows,
  activeSection,
  materiality,
  subtotals,
  varianceExceedRows,
  switchSection,
  switchMethod,
  updateCell,
  recalcAll,
  addRow,
  removeRow,
  importRows,
  exportRows,
} = useK2Amortization(allResponsesRef, {
  onSave: (itemId, value) => emit('save', itemId, value),
})

const { contractCostVsAmort } = useK2CrossSheet(allResponsesRef)

const wpIdRef = toRef(props, 'wpId')
const { exportTemplate, exportData, importData } = useK2ImportExport({ wpId: wpIdRef })

// ─── Section Options ─────────────────────────────────────────────────────────

const sectionOptions = K2_AMORT_SECTION_LABELS.map((label, idx) => ({
  label,
  value: idx,
}))

const methodOptions = ['直线法', '进度法']
const conclusionOptions = ['正常', '差异不重大', '差异重大-需调整', '待确认']

// ─── Cross-validation badge ──────────────────────────────────────────────────

const crossValidation = computed(() => contractCostVsAmort.value)

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleSectionChange(val: number | string): void {
  switchSection(val as K2AmortSection)
}

function handleCellChange(rowId: string, field: string, value: any): void {
  updateCell(rowId, field, value)
}

function handleMethodSwitch(rowId: string, method: string): void {
  switchMethod(rowId, method as K2AmortMethod)
}

function handleMaterialityChange(val: number | undefined): void {
  emit('save', 'K2-5-materiality', String(val ?? 0))
}

async function handleAddRow(): Promise<void> {
  const { value: contractNo } = await ElMessageBox.prompt(
    '请输入合同编号',
    '新增摊销行',
    { confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '合同编号（如C-001）' },
  ).catch(() => ({ value: '' }))
  if (contractNo === undefined) return
  addRow(contractNo || `C-${String(rows.value.length + 1).padStart(3, '0')}`)
  recalcAll()
}

function handleRemoveRow(rowId: string): void {
  removeRow(rowId)
}

async function handleImportExport(command: string): Promise<void> {
  try {
    if (command === 'export-template') {
      await exportTemplate('K2-5')
    } else if (command === 'export-data') {
      await exportData('K2-5')
    } else if (command === 'import-data') {
      // 创建隐藏文件输入
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = '.xlsx,.xls'
      input.onchange = async () => {
        const file = input.files?.[0]
        if (!file) return
        try {
          const result = await importData('K2-5', file)
          if (result && result.rowCount > 0) {
            ElMessage.success(`成功导入 ${result.rowCount} 行`)
          }
        } catch (err: any) {
          ElMessage.error(err?.message || '导入失败')
        }
      }
      input.click()
    }
  } catch (err: any) {
    ElMessage.error(err?.message || '导入导出失败')
  }
}

// ─── Variance Check ──────────────────────────────────────────────────────────

function isVarianceExceeded(rowId: string): boolean {
  return varianceExceedRows.value.has(rowId)
}

function getRowClassName({ row }: { row: any }): string {
  if (isVarianceExceeded(row.rowId)) return 'row-variance-exceed'
  return ''
}

function getConclTagType(conclusion: string): 'success' | 'warning' | 'danger' | 'info' {
  if (conclusion === '正常') return 'success'
  if (conclusion === '差异不重大') return 'warning'
  if (conclusion === '差异重大-需调整') return 'danger'
  return 'info'
}

// ─── Format Helpers ──────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return fmtAmount(val)
}

function fmtPercent(val: number | null | undefined): string {
  if (val == null) return '-'
  return `${(val * 100).toFixed(2)}%`
}

// ─── Recalc on mount (ensure formula columns are computed) ───────────────────

watch(() => rows.value.length, () => {
  recalcAll()
}, { immediate: true })
</script>

<style scoped>
.k2-tab-amortization {
  padding: 12px 0;
}

.methodology-context {
  border-left: 3px solid #e6a23c;
  background: #fef9e7;
  padding: 8px 12px;
  margin-bottom: 12px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  font-weight: 600;
}

.title-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.cross-badge {
  font-size: 11px;
}

.materiality-input {
  width: 110px;
}

.materiality-label {
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
}

.segment-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.amort-table {
  font-size: var(--wp-font-size, 13px);
}

.amort-table :deep(.cell-input) {
  width: 100%;
}

.amort-table :deep(.cell-input .el-input__inner),
.amort-table :deep(.cell-input .el-input-number__decrease),
.amort-table :deep(.cell-input .el-input-number__increase) {
  font-size: var(--wp-font-size, 13px);
}

.method-segmented {
  --el-segmented-item-selected-bg-color: var(--el-color-primary-light-3);
}

.formula-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

.formula-cell {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
  padding-bottom: 1px;
}

.amount-cell {
  font-variant-numeric: tabular-nums;
}

.percent-cell {
  color: #409eff;
}

.variance-danger {
  color: #f56c6c;
  font-weight: 600;
  background: rgba(245, 108, 108, 0.08);
  padding: 2px 4px;
  border-radius: 2px;
}

.variance-danger-text {
  color: #f56c6c;
  font-weight: 600;
}

/* 差异超过重要性的行高亮 */
.amort-table :deep(.row-variance-exceed) {
  background-color: rgba(245, 108, 108, 0.06) !important;
}

.amort-table :deep(.row-variance-exceed:hover > td) {
  background-color: rgba(245, 108, 108, 0.12) !important;
}

.subtotal-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  padding: 10px 12px;
  margin-top: 8px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
}

.subtotal-label {
  color: #606266;
  font-weight: 500;
}

.subtotal-item {
  color: #303133;
}

.subtotal-item b {
  font-variant-numeric: tabular-nums;
  margin-left: 4px;
}
</style>
