<template>
<div class="d7-adjustment">
    <!-- 编制提示 -->
    <details class="editing-hints">
      <summary>📋 编制提示</summary>
      <div class="hints-content">
        <p>本表记录合同负债（科目2205）相关审计调整分录。</p>
        <p>借贷金额必须平衡（借方合计=贷方合计）。</p>
        <p>完成后可推送至A13错报汇总表。</p>
      </div>
    </details>

    <!-- 工具栏 -->
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">新增调整分录</el-button>
      <el-button size="small" :disabled="isReadonly || selectedIds.length === 0" @click="handlePushToA13">推送至A13</el-button>
      <el-button size="small" @click="exportTemplate">导出模板</el-button>
      <el-button size="small" @click="exportData">导出数据</el-button>
      <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
        <el-button size="small" :loading="importing">导入数据</el-button>
      </el-upload>
    </div>

    <!-- 调整分录表 -->
    <el-table :data="rows" size="small" border @selection-change="onSelectionChange">
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
      <el-table-column label="备注" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @change="(v: string) => updateCell(row.rowId, 'remark', v)" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="60" align="center">
        <template #default="{ row }">
          <el-popconfirm title="确认删除？" @confirm="removeRow(row.rowId)">
            <template #reference>
              <el-button type="danger" text size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 借贷合计 + 平衡指示 -->
    <div class="balance-section">
      <div class="balance-row">
        <span>借方合计：<strong>{{ fmtAmt(debitTotal) }}</strong></span>
        <span>贷方合计：<strong>{{ fmtAmt(creditTotal) }}</strong></span>
        <span :class="isBalanced ? 'balanced' : 'unbalanced'">
          {{ isBalanced ? '✓ 平衡' : `✗ 不平衡：差额${fmtAmt(balanceDiff)}` }}
        </span>
      </div>
    </div>
</div>
</template>

<script setup lang="ts">
/**
 * D7TabAdjustment.vue — 调整分录 D7-3 (~250行)
 * Task: 18.1
 * Requirements: 8.1-8.7, 20.1
 */
import { ref, computed, inject, type Ref } from 'vue'
import { useD7Adjustment, ADJUSTMENT_CATEGORIES, type AdjustmentRow } from '../composables/useD7Adjustment'
import { useD7ImportExport } from '../composables/useD7ImportExport'
import type { ChecklistResponse } from '../composables/useD7FormData'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

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
  allResponses: props.allResponses,
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
.d7-adjustment { padding: 16px; }

.editing-hints {
  margin-bottom: 16px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
}
.editing-hints summary { padding: 10px 14px; cursor: pointer; font-size: 13px; font-weight: 500; color: #409eff; }
.hints-content { padding: 0 14px 12px; font-size: 13px; color: #606266; line-height: 1.8; }
.hints-content p { margin: 0 0 4px; }

.toolbar { display: flex; gap: 8px; margin-bottom: 12px; }

.balance-section { margin-top: 12px; padding: 10px 12px; background: #fafafa; border-radius: 6px; }
.balance-row { display: flex; gap: 24px; font-size: 13px; align-items: center; }
.balanced { color: #67c23a; font-weight: 600; }
.unbalanced { color: #f56c6c; font-weight: 600; }
</style>
