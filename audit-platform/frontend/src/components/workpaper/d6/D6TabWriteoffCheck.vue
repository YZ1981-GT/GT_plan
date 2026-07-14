<template>
<div class="d6-tab-writeoff-check">
  <!-- 编制提示 -->
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 本表检查合同资产坏账准备（科目1403）本期重要的转回及核销事项，验证其真实性、合理性与审批合规性。</p>
      <p>2. 转回检查关注收回方式、原计提依据与转回合理性；核销检查关注核销原因、核销程序及是否涉及关联交易。</p>
      <p>3. 涉及关联交易的核销记录以琥珀色高亮，需重点关注是否存在通过核销掩盖关联方资金占用的风险。</p>
      <p>4. 转回/核销金额应与 D6-3 减值准备明细的转回/核销列勾稽一致，重大项目应取得充分适当的审计证据。</p>
    </div>
  </details>

  <!-- 审计目标 -->
  <el-alert
    type="info"
    :closable="false"
    title="审计目标：验证合同资产减值准备转回与核销的真实性、合理性及审批合规性，识别是否存在利用转回核销操纵损益或掩盖关联交易的情形。"
    class="objective-alert"
  />

  <!-- 工具栏 -->
  <div class="tab-toolbar">
    <div class="toolbar-left"></div>
    <div class="toolbar-right">
      <el-dropdown size="small" trigger="click">
        <el-button size="small">导入导出(转回) ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="reversalIe.exportTemplate">导出模板</el-dropdown-item>
            <el-dropdown-item @click="reversalIe.exportData">导出数据</el-dropdown-item>
            <el-dropdown-item>
              <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportReversalFile">
                <span>导入数据</span>
              </el-upload>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-dropdown size="small" trigger="click">
        <el-button size="small">导入导出(核销) ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="writeoffIe.exportTemplate">导出模板</el-dropdown-item>
            <el-dropdown-item @click="writeoffIe.exportData">导出数据</el-dropdown-item>
            <el-dropdown-item>
              <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportWriteoffFile">
                <span>导入数据</span>
              </el-upload>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <span class="chip-wrap"><GtIndexChip value="wp:D6-3" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ reversalRows.length + writeoffRows.length }} 行</el-tag>
    </div>
  </div>

  <!-- 勾稽校验：D6-9 ↔ D6-3 -->
  <el-alert
    v-if="writeoffCrossCheck"
    :type="writeoffCrossCheck.type"
    :title="writeoffCrossCheck.message"
    :closable="false"
    show-icon
    style="margin-bottom: 8px"
  />

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
    <el-table :data="reversalRows" size="small" border stripe style="width:100%">
      <el-table-column label="客户名称" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.customerName" size="small" @change="(v: string) => updateReversalCell(row.rowId, 'customerName', v)" />
          <span v-else>
            {{ row.customerName }}
            <GtIndexChip value="wp:D6-3" :context-project-id="projectId" style="margin-left:4px" />
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
    <el-table :data="writeoffRows" size="small" border stripe style="width:100%" :row-class-name="writeoffRowClass">
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

  <!-- 审计意见区（卡片式） -->
  <el-card class="opinion-card" shadow="never">
    <template #header>
      <div class="opinion-header">
        <span class="opinion-title">审计说明与结论</span>
        <div class="opinion-chips">
          <GtIndexChip value="wp:D6-3" :context-project-id="projectId" />
        </div>
      </div>
    </template>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">1. 审计说明</span>
        <div class="opinion-actions">
          <el-button size="small" @click="openReview('D6-9-note-explanation')">💬</el-button>
        </div>
      </div>
      <el-input v-model="auditNotes.explanation" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="转回核销检查过程及发现..." />
    </div>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">2. 审计结论</span>
        <div class="opinion-actions">
          <el-button size="small" @click="openReview('D6-9-note-conclusion')">💬</el-button>
        </div>
      </div>
      <el-input v-model="auditNotes.conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="转回核销结论..." />
    </div>
  </el-card>
</div>
</template>

<script setup lang="ts">
/**
 * D6TabWriteoffCheck.vue — 减值准备转回核销检查 D6-9
 */
import { computed, inject, toRef, type Ref } from 'vue'
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
  allResponses: Map<string, ChecklistResponse>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

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
  allResponses: allResponsesRef,
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

// 勾稽校验：D6-9 转回/核销 ↔ D6-3 减值明细转回/核销列
const writeoffCrossCheck = computed<{ type: 'info' | 'success' | 'warning'; message: string } | null>(() => {
  const responses = allResponsesRef.value
  if (!responses || responses.size === 0) return null

  // 读取 D6-3 减值明细行数据，汇总转回/核销
  const d63RowsRaw = responses.get('D6-3-rows')?.remark
  let d63ReversalTotal = 0
  let d63WriteoffTotal = 0

  if (d63RowsRaw) {
    try {
      const d63Rows = JSON.parse(d63RowsRaw)
      if (Array.isArray(d63Rows)) {
        for (const row of d63Rows) {
          d63ReversalTotal += parseFloat(row.reversal || row.reversalAmount || 0) || 0
          d63WriteoffTotal += parseFloat(row.writeOff || row.writeOffAmount || row.writeoffAmount || 0) || 0
        }
      }
    } catch { /* ignore parse errors */ }
  }

  // D6-3 尚无数据
  if (!d63RowsRaw) {
    return { type: 'info', message: '勾稽校验：D6-3 减值明细数据尚未填写，无法核对' }
  }

  // D6-9 本表合计
  const d69ReversalTotal = reversalTotal.value
  const d69WriteoffTotal = writeoffTotal.value

  const reversalDiff = Math.abs(d69ReversalTotal - d63ReversalTotal)
  const writeoffDiff = Math.abs(d69WriteoffTotal - d63WriteoffTotal)

  if (reversalDiff < 0.01 && writeoffDiff < 0.01) {
    return { type: 'success', message: `勾稽校验通过：转回 ${fmtAmt(d69ReversalTotal)} = D6-3 ${fmtAmt(d63ReversalTotal)}，核销 ${fmtAmt(d69WriteoffTotal)} = D6-3 ${fmtAmt(d63WriteoffTotal)}` }
  }

  const parts: string[] = []
  if (reversalDiff >= 0.01) parts.push(`转回差异 ${fmtAmt(d69ReversalTotal - d63ReversalTotal)}（D6-9: ${fmtAmt(d69ReversalTotal)} vs D6-3: ${fmtAmt(d63ReversalTotal)}）`)
  if (writeoffDiff >= 0.01) parts.push(`核销差异 ${fmtAmt(d69WriteoffTotal - d63WriteoffTotal)}（D6-9: ${fmtAmt(d69WriteoffTotal)} vs D6-3: ${fmtAmt(d63WriteoffTotal)}）`)

  return { type: 'warning', message: `勾稽校验：${parts.join('；')}` }
})

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
.d6-tab-writeoff-check :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d6-tab-writeoff-check :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
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
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

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
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
}
.chip-wrap { display: inline-flex; align-items: center; }

.virtual-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.virtual-hint { flex: 1; min-width: 200px; margin: 0; }
.virtual-table { margin-bottom: 12px; }
.section-block { margin-bottom: 24px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.section-title { font-size: 14px; font-weight: 600; margin: 0; color: #303133; }
.total-line { margin-top: 8px; font-size: var(--wp-font-size, 13px); font-weight: 600; color: #606266; }
:deep(.related-party-row) { background-color: #fdf6ec !important; }

/* 审计意见卡片 */
.opinion-card {
  margin-top: 16px;
  border-radius: 8px;
}
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.opinion-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.opinion-chips {
  display: flex;
  gap: 6px;
}
.opinion-section {
  margin-bottom: 16px;
}
.opinion-section:last-child {
  margin-bottom: 0;
}
.opinion-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.opinion-section-label {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}
.opinion-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}
</style>
