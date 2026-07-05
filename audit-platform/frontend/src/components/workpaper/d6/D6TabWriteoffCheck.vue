<template>
<div class="d6-tab-writeoff-check">
  <div class="toolbar">
    <el-button size="small" @click="reversalIe.exportTemplate">导出模板(转回)</el-button>
    <el-button size="small" @click="reversalIe.exportData">导出数据(转回)</el-button>
    <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportReversalFile">
      <el-button size="small" :loading="reversalIe.importing.value">导入(转回)</el-button>
    </el-upload>
    <el-button size="small" @click="writeoffIe.exportTemplate">导出模板(核销)</el-button>
    <el-button size="small" @click="writeoffIe.exportData">导出数据(核销)</el-button>
    <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportWriteoffFile">
      <el-button size="small" :loading="writeoffIe.importing.value">导入(核销)</el-button>
    </el-upload>
  </div>
  <div v-if="useVirtualScroll" class="virtual-toolbar">
    <el-alert type="info" :closable="false" class="virtual-hint">
      行数较多（{{ browseRowCount }} 行）· {{ browseMode ? '虚拟滚动速览' : '表格编辑' }}模式
    </el-alert>
    <el-button size="small" @click="toggleBrowseMode">
      {{ browseMode ? '切换表格编辑' : '切换虚拟速览' }}
    </el-button>
  </div>
  <el-table-v2
    v-if="useVirtualScroll && browseMode"
    :columns="virtualColumns"
    :data="browseRows"
    :width="tableWidth"
    :height="tableHeight"
    :row-height="36"
    :header-height="40"
    fixed
    class="virtual-table"
  />

  <template v-if="!useVirtualScroll || !browseMode">
  <!-- (一) 转回检查 -->
  <div class="section-block">
    <div class="section-header">
      <h4 class="section-title">(一) 本期重要的减值准备转回检查</h4>
      <el-button v-if="!isReadonly" size="small" type="primary" @click="addReversalRow">添加转回记录</el-button>
    </div>
    <el-table :data="reversalRows" size="small" border style="width:100%">
      <el-table-column label="客户名称" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.customerName" size="small" @change="(v: string) => updateReversalCell(row.rowId, 'customerName', v)" />
          <span v-else>
            {{ row.customerName }}
            <GtIndexChip wp-code="D6-3" label="→D6-3" style="margin-left:4px" />
          </span>
        </template>
      </el-table-column>
      <el-table-column label="转回原因" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.reason" size="small" @change="(v: string) => updateReversalCell(row.rowId, 'reason', v)" />
          <span v-else>{{ row.reason }}</span>
        </template>
      </el-table-column>
      <el-table-column label="收回方式" width="110">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.recoveryMethod" size="small" @change="(v: string) => updateReversalCell(row.rowId, 'recoveryMethod', v)">
            <el-option v-for="m in RECOVERY_METHODS" :key="m" :label="m" :value="m" />
          </el-select>
          <span v-else>{{ row.recoveryMethod }}</span>
        </template>
      </el-table-column>
      <el-table-column label="原确定依据" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.originalBasis" size="small" @change="(v: string) => updateReversalCell(row.rowId, 'originalBasis', v)" />
          <span v-else>{{ row.originalBasis }}</span>
        </template>
      </el-table-column>
      <el-table-column label="转回金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.reversalAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateReversalCell(row.rowId, 'reversalAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.reversalAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="转回前累计准备" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.priorProvisionAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateReversalCell(row.rowId, 'priorProvisionAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.priorProvisionAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="合理性分析" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.reasonabilityAnalysis" size="small" @change="(v: string) => updateReversalCell(row.rowId, 'reasonabilityAnalysis', v)" />
          <span v-else>{{ row.reasonabilityAnalysis }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引号" width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small" @change="(v: string) => updateReversalCell(row.rowId, 'indexRef', v)" />
          <span v-else>{{ row.indexRef }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="50" align="center">
        <template #default="{ row }">
          <el-button type="danger" text size="small" @click="removeReversalRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="total-line">转回合计：{{ fmtAmt(reversalTotal) }}</div>
  </div>

  <!-- (二) 核销检查 -->
  <div class="section-block">
    <div class="section-header">
      <h4 class="section-title">(二) 核销的合同资产检查</h4>
      <el-button v-if="!isReadonly" size="small" type="primary" @click="addWriteoffRow">添加核销记录</el-button>
    </div>
    <el-table :data="writeoffRows" size="small" border style="width:100%" :row-class-name="writeoffRowClass">
      <el-table-column label="客户名称" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.customerName" size="small" @change="(v: string) => updateWriteoffCell(row.rowId, 'customerName', v)" />
          <span v-else>{{ row.customerName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="核销金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.writeoffAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateWriteoffCell(row.rowId, 'writeoffAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.writeoffAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="核销原因" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.writeoffReason" size="small" @change="(v: string) => updateWriteoffCell(row.rowId, 'writeoffReason', v)" />
          <span v-else>{{ row.writeoffReason }}</span>
        </template>
      </el-table-column>
      <el-table-column label="核销程序" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.writeoffProcedure" size="small" @change="(v: string) => updateWriteoffCell(row.rowId, 'writeoffProcedure', v)" />
          <span v-else>{{ row.writeoffProcedure }}</span>
        </template>
      </el-table-column>
      <el-table-column label="关联交易" width="100" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.isRelatedParty" size="small" @change="(v: string) => updateWriteoffCell(row.rowId, 'isRelatedParty', v)">
            <el-option v-for="o in RELATED_PARTY_OPTIONS" :key="o" :label="o" :value="o" />
          </el-select>
          <span v-else>{{ row.isRelatedParty }}</span>
        </template>
      </el-table-column>
      <el-table-column label="合理性分析" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.reasonabilityAnalysis" size="small" @change="(v: string) => updateWriteoffCell(row.rowId, 'reasonabilityAnalysis', v)" />
          <span v-else>{{ row.reasonabilityAnalysis }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引号" width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small" @change="(v: string) => updateWriteoffCell(row.rowId, 'indexRef', v)" />
          <span v-else>{{ row.indexRef }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @change="(v: string) => updateWriteoffCell(row.rowId, 'remark', v)" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="50" align="center">
        <template #default="{ row }">
          <el-button type="danger" text size="small" @click="removeWriteoffRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="total-line">核销合计：{{ fmtAmt(writeoffTotal) }}</div>
  </div>
  </template>

  <!-- 审计说明/结论 -->
  <div class="audit-notes-section">
    <h4>审计说明</h4>
    <el-input v-model="auditNotes.explanation" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="转回核销检查过程及发现..." />
    <div class="note-actions">
      <el-button size="small" @click="openReview('D6-9-note-explanation')">💬复核</el-button>
    </div>
  </div>
  <div class="audit-notes-section">
    <h4>审计结论</h4>
    <el-input v-model="auditNotes.conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="转回核销结论..." />
    <div class="note-actions">
      <el-button size="small" @click="openReview('D6-9-note-conclusion')">💬复核</el-button>
    </div>
  </div>
</div>
</template>

<script setup lang="ts">
/**
 * D6TabWriteoffCheck.vue — 减值准备转回核销检查 D6-9
 */
import { computed, inject, type Ref } from 'vue'
import {
  useD6WriteoffCheck,
  RECOVERY_METHODS,
  RELATED_PARTY_OPTIONS,
  type D6WriteoffRow,
} from '../composables/useD6WriteoffCheck'
import { useD6ImportExport } from '../composables/useD6ImportExport'
import { useWorkpaperBrowseMode } from '../composables/useWorkpaperBrowseMode'
import { virtualTextCol, virtualNumCol } from '../composables/virtualColumnHelpers'
import type { VirtualColumn } from '@/composables/useVirtualTable'
import type { ChecklistResponse } from '../composables/useD6FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
function openReview(sectionId: string) { openReviewDialog(sectionId) }
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>
const reversalIe = useD6ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D6-9-reversal',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})
const writeoffIe = useD6ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D6-9-writeoff',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})

async function onImportReversalFile(file: File) {
  await reversalIe.importData(file)
  return false
}

async function onImportWriteoffFile(file: File) {
  await writeoffIe.importData(file)
  return false
}

const {
  reversalRows, writeoffRows, reversalTotal, writeoffTotal,
  addReversalRow, addWriteoffRow, removeReversalRow, removeWriteoffRow,
  updateReversalCell, updateWriteoffCell, auditNotes,
} = useD6WriteoffCheck({
  allResponses: props.allResponses,
  debouncedSave: props.debouncedSave,
})

function writeoffRowClass({ row }: { row: D6WriteoffRow }): string {
  return row.isRelatedParty === '是' ? 'related-party-row' : ''
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const browseRows = computed(() => [
  ...reversalRows.value.map(r => ({
    label: `[转回] ${r.customerName || '-'}`,
    amount: r.reversalAmount,
  })),
  ...writeoffRows.value.map(r => ({
    label: `[核销] ${r.customerName || '-'}`,
    amount: r.writeoffAmount,
  })),
])

const browseRowCount = computed(() => browseRows.value.length)

const virtualColumns = computed<VirtualColumn[]>(() => [
  virtualTextCol('label', '项目', 220),
  virtualNumCol('amount', '金额', 120, fmtAmt),
])

const {
  browseMode,
  useVirtualScroll,
  tableWidth,
  tableHeight,
  toggleBrowseMode,
} = useWorkpaperBrowseMode({
  rows: browseRows,
  virtualColumns,
  tableWidth: 720,
})
</script>

<style scoped>
.d6-tab-writeoff-check { padding: 16px; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
.virtual-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.virtual-hint { flex: 1; min-width: 200px; margin: 0; }
.virtual-table { margin-bottom: 12px; }
.section-block { margin-bottom: 24px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.section-title { font-size: 14px; font-weight: 600; margin: 0; color: #303133; }
.total-line { margin-top: 8px; font-size: 13px; font-weight: 600; color: #606266; }
.audit-notes-section { margin-top: 16px; }
.audit-notes-section h4 { font-size: 14px; font-weight: 600; margin-bottom: 8px; }
.note-actions { display: flex; gap: 8px; margin-top: 6px; }
:deep(.related-party-row) { background-color: #fdf6ec !important; }
</style>
