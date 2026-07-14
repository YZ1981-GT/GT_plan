<template>
<div class="d7-adjustment">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表记录合同负债（科目2205）相关审计调整分录，依据 CAS14 收入准则更正错误的会计处理或确认未入账事项。</p>
        <p>2. 审计调整分录（AJE）用于更正错报；重分类调整分录（RJE）用于调整报表列报分类，不影响利润。</p>
        <p>3. 常见调整：合同负债与预收账款（2203）重分类、跨期收入确认更正、履约义务完成后的结转。</p>
        <p>4. 借贷必须平衡（借方合计=贷方合计），每笔分录需注明调整事由和索引号；可选中分录推送至 A13 错报汇总表。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：验证调整分录的准确性与完整性，确认借贷平衡且调整事由充分合理。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增调整分录</el-button>
        <el-button size="small" :disabled="isReadonly || selectedIds.length === 0" @click="handlePushToA13">推送至A13</el-button>
      </div>
      <div class="toolbar-right">
        <el-dropdown size="small" trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile" :disabled="isReadonly">
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="chip-wrap"><GtIndexChip value="wp:D7-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:A13" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 调整分录表 -->
    <el-table :data="rows" size="small" border stripe @selection-change="onSelectionChange">
      <el-table-column v-if="!isReadonly" type="selection" width="40" />
      <el-table-column label="调整事项说明" min-width="160">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.description" size="small" @change="(v: string) => updateCell(row.rowId, 'description', v)" />
          <span v-else>{{ row.description }}</span>
        </template>
      </el-table-column>
      <el-table-column label="类别" width="110">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.category" size="small" @change="(v: string) => updateCell(row.rowId, 'category', v)">
            <el-option v-for="c in CATEGORIES" :key="c" :label="c" :value="c" />
          </el-select>
          <span v-else>{{ row.category }}</span>
        </template>
      </el-table-column>
      <el-table-column label="报表项目" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.reportItem" size="small" @change="(v: string) => updateCell(row.rowId, 'reportItem', v)" />
          <span v-else>{{ row.reportItem }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目名称" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.accountName" size="small" @change="(v: string) => updateCell(row.rowId, 'accountName', v)" />
          <span v-else>{{ row.accountName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="附注项目" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.noteItem" size="small" @change="(v: string) => updateCell(row.rowId, 'noteItem', v)" />
          <span v-else>{{ row.noteItem }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'debitAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'creditAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引" width="80">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small" @change="(v: string) => updateCell(row.rowId, 'indexRef', v)" />
          <span v-else>{{ row.indexRef }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @change="(v: string) => updateCell(row.rowId, 'remark', v)" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-popconfirm title="确认删除？" @confirm="removeRow(row.rowId)">
            <template #reference>
              <el-button type="danger" text size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部借贷合计行 + 平衡指示 -->
    <div class="balance-row">
      <span class="balance-item">借方合计：<strong>{{ fmtAmt(debitTotal) }}</strong></span>
      <span class="balance-item">贷方合计：<strong>{{ fmtAmt(creditTotal) }}</strong></span>
      <el-tag v-if="isBalanced" type="success" size="small">借贷平衡</el-tag>
      <el-tag v-else type="danger" size="small">不平衡 差额 {{ fmtAmt(balanceDiff) }}</el-tag>
    </div>
</div>
</template>

<script setup lang="ts">
/**
 * D7TabAdjustment.vue — 调整分录 D7-3 (~250行)
 * Task: 18.1
 * Requirements: 8.1-8.7, 20.1
 */
import { ref, computed, inject, toRef, type Ref } from 'vue'
import { useD7Adjustment, ADJUSTMENT_CATEGORIES, type AdjustmentRow } from '../composables/useD7Adjustment'
import { useD7ImportExport } from '../composables/useD7ImportExport'
import type { ChecklistResponse } from '../composables/useD7FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, ChecklistResponse>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const CATEGORIES = ADJUSTMENT_CATEGORIES
const selectedIds = ref<string[]>([])
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>
const { importing, exportTemplate, exportData, importData } = useD7ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D7-3',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})

async function onImportFile(file: File) {
  await importData(file)
  return false
}

const {
  rows, debitTotal, creditTotal, isBalanced, balanceDiff,
  addRow, removeRow, updateCell, pushToA13,
} = useD7Adjustment({
  allResponses: allResponsesRef,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
})

function onSelectionChange(selection: AdjustmentRow[]) {
  selectedIds.value = selection.map(r => r.rowId)
}

function handlePushToA13() {
  pushToA13(selectedIds.value)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.d7-adjustment { padding: 12px; }
.d7-adjustment :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d7-adjustment :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}

/* 审计目标 */
.objective-alert { margin-bottom: 12px; }

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
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p { margin: 2px 0; }

/* 工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

/* 借贷平衡指示 */
.balance-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-top: 12px;
  font-size: var(--wp-font-size, 13px);
}
.balance-item { color: #606266; }
.balance-item strong { color: #303133; }
</style>
