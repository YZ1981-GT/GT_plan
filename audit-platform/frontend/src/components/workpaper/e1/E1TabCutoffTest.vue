<script setup lang="ts">
/**
 * E1TabCutoffTest.vue — E1-21/22 截止测试 (variant: bank/other)
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.15
 *
 * - Uses useE1CutoffTest composable
 * - Props: variant detected from sheetName (E1-21→'bank', E1-22→'other')
 * - el-table: 凭证号 | 日期 | 金额 | 对方账户 | 是否跨期(readonly, computed, red highlight)
 * - Dynamic rows
 *
 * Requirements: 10.4-10.5
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useE1CutoffTest,
  type CutoffVariant,
  type CutoffTestRow,
} from '../composables/useE1CutoffTest'
import { useE1ImportExport } from '../composables/useE1ImportExport'
import type { UseE1BaseOptions } from '../composables/useE1Adjudication'
import GtIndexChip from '../GtIndexChip.vue'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>
  debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean
  sheetName?: string
  bsDate?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) =>
    v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

// ─── Variant Detection ───────────────────────────────────────────────────────

const variant = computed<CutoffVariant>(() => {
  const name = props.sheetName || ''
  if (name.includes('E1-22') || name.includes('其他货币资金')) return 'other'
  return 'bank'
})

// ─── Composable ──────────────────────────────────────────────────────────────

const options: UseE1BaseOptions & { variant: CutoffVariant } = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
  bsDate: toRef(props, 'bsDate') as unknown as Ref<string>,
  variant: variant.value,
}

const {
  rows,
  balanceSheetDate,
  isLoading,
  addRow,
  removeRow,
  updateCell,
} = useE1CutoffTest(options)

// ─── 导入导出（E1-21 bank / E1-22 other） ─────────────────────────────────────

const sheetCode = computed(() => (variant.value === 'other' ? 'E1-22' : 'E1-21'))
const { exportTemplate, exportData, importData, isImporting } = useE1ImportExport({
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  sheet: sheetCode as unknown as Ref<string>,
})

async function handleImport(file: File): Promise<boolean> {
  const res = await importData(file)
  if (res.success) {
    ElMessage.success(res.message || '导入成功')
    await reloadWorkpaperData?.()
  } else {
    ElMessage.warning(res.message || '导入失败')
  }
  return false
}

// ─── Row Class ───────────────────────────────────────────────────────────────

function getRowClass({ row }: { row: CutoffTestRow }): string {
  if (row.isCrossover) return 'e1-cutoff-red-row'
  return ''
}
</script>

<template>
  <div class="e1-tab-cutoff-test">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 抽取资产负债表日前后各若干天（通常±3~5天）的银行收付款凭证进行截止测试。</p>
        <p>2. 检查款项是否记入正确会计期间，"是否跨期"列由系统根据凭证日期与资产负债表日自动判定（跨期红色高亮）。</p>
        <p>3. 跨期项目应评估对货币资金及往来科目（应收/应付）的影响，必要时提请调整。</p>
        <p>4. 结合银行对账单、余额调节表（E1-6）核查未达账项的真实性与合理性。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：通过截止测试确认货币资金收支已记入正确会计期间，防止跨期错报。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag size="small" :type="variant === 'other' ? 'warning' : 'success'">
          {{ variant === 'other' ? '其他货币资金 (E1-22)' : '银行存款 (E1-21)' }}
        </el-tag>
        <el-tag v-if="balanceSheetDate" size="small" type="info">资产负债表日：{{ balanceSheetDate }}</el-tag>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
      </div>
      <div class="toolbar-right">
        <el-dropdown size="small" trigger="click" :disabled="isReadonly">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate()">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData()">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload
                  :show-file-list="false"
                  accept=".xlsx,.xls"
                  :before-upload="handleImport"
                  :disabled="isImporting"
                >
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="chip-wrap"><GtIndexChip value="wp:E1-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <el-skeleton :loading="isLoading" :rows="8" animated>
      <template #default>
        <el-table
          :data="rows"
          border
          stripe
          size="small"
          max-height="500"
          style="width: 100%"
          :row-class-name="getRowClass"
        >
          <el-table-column label="凭证号" width="130">
            <template #default="{ row }">
              <el-input :model-value="row.voucherNo" :disabled="isReadonly" size="small"
                @change="(val: string) => updateCell(row.id, 'voucherNo', val)" />
            </template>
          </el-table-column>
          <el-table-column label="日期" width="140">
            <template #default="{ row }">
              <el-date-picker :model-value="row.date" :disabled="isReadonly" type="date"
                value-format="YYYY-MM-DD" size="small" style="width: 100%"
                @update:model-value="(val: string) => updateCell(row.id, 'date', val || '')" />
            </template>
          </el-table-column>
          <el-table-column label="金额" width="150" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="row.amount" :disabled="isReadonly"
                :controls="false" size="small"
                @change="(val: number) => updateCell(row.id, 'amount', val ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="对方账户" min-width="150">
            <template #default="{ row }">
              <el-input :model-value="row.counterparty" :disabled="isReadonly" size="small"
                @change="(val: string) => updateCell(row.id, 'counterparty', val)" />
            </template>
          </el-table-column>
          <el-table-column label="是否跨期" width="100" align="center" class-name="auto-calc-col">
            <template #default="{ row }">
              <el-tag v-if="row.isCrossover" type="danger" size="small">跨期</el-tag>
              <span v-else class="auto-calc-value">否</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="70" align="center" fixed="right">
            <template #default="{ row }">
              <el-button v-if="!isReadonly" type="danger" text size="small"
                @click="removeRow(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-cutoff-test {
  padding: 12px 0;
}
.e1-tab-cutoff-test :deep(.el-table) {
  --el-table-font-size: 13px;
  font-size: 13px;
}
.e1-tab-cutoff-test :deep(.el-table .cell) {
  font-size: 13px !important;
}

/* 编制提示 */
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.objective-alert {
  margin-bottom: 12px;
}

/* 工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }

/* 自动计算列灰底 */
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
.auto-calc-value {
  color: #909399;
}
:deep(.e1-cutoff-red-row) {
  background-color: #fef0f0 !important;
}
:deep(.e1-cutoff-red-row td) {
  color: #f56c6c;
}
</style>
