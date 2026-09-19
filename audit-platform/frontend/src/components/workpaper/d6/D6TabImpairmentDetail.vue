<template>
<div class="d6-tab-impairment-detail">
  <!-- 编制提示 -->
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 本表列示合同资产坏账准备（科目1403）明细，按"单项评估"与"信用风险组合"两类分别计提，对应 CAS22 金融工具减值 ECL 模型。</p>
      <p>2. 灰色底纹列为自动计算列（期初审定/期末未审/期末审定），期末审定 = 期初审定 + 计提 + 其他增加 − 转回 − 核销 − 其他减少。</p>
      <p>3. 单项评估适用于信用风险显著不同的合同资产；组合评估按账龄/信用风险特征分组，损失率取自 D6-8 ECL 测算。</p>
      <p>4. 本表期末审定合计应与 D6-1 审定表坏账准备区块（block2）勾稽一致，差异需查明原因。</p>
    </div>
  </details>

  <!-- 审计目标 -->
  <el-alert
    type="info"
    :closable="false"
    title="审计目标：确认合同资产坏账准备的计提方法（单项/组合）恰当，本期计提、转回、核销准确完整，期末余额与审定表及减值测算勾稽一致。"
    class="objective-alert"
  />

  <!-- 工具栏 -->
  <div class="tab-toolbar">
    <div class="toolbar-left"></div>
    <div class="toolbar-right">
      <el-dropdown size="small" trigger="click" :disabled="isReadonly">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="exportTemplate">导出模板</el-dropdown-item>
            <el-dropdown-item @click="exportData">导出数据</el-dropdown-item>
            <el-dropdown-item>
              <el-upload
                :show-file-list="false"
                accept=".xlsx"
                :auto-upload="false"
                :disabled="isReadonly || importing"
                @change="(f: any) => onImportFile(f.raw || f)"
              >
                <span>导入数据</span>
              </el-upload>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <span class="chip-wrap"><GtIndexChip value="wp:D6-1" :context-project-id="projectId" /></span>
      <span class="chip-wrap"><GtIndexChip value="wp:D6-8" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ singleRows.length + groupRows.length }} 行</el-tag>
    </div>
  </div>

  <!-- 与 D6-1 block2 勾稽 -->
  <el-alert
    v-if="Math.abs(reconciliation.diff) >= 0.01"
    type="warning"
    :closable="false"
    class="recon-alert"
  >
    D6-3 期末审定合计（{{ fmtAmount(reconciliation.d63Total) }}）与 D6-1 减值准备 block2（{{ fmtAmount(reconciliation.d61Total) }}）差异 {{ fmtAmount(reconciliation.diff) }}
  </el-alert>
  <el-alert
    v-else-if="singleRows.length > 0 || groupRows.length > 0"
    type="success"
    :closable="false"
    class="recon-alert"
  >
    ✓ D6-3 与 D6-1 block2 勾稽一致（{{ fmtAmount(reconciliation.d63Total) }}）
  </el-alert>

  <div v-if="useVirtualScroll" class="virtual-toolbar">
    <el-alert type="info" :closable="false" class="virtual-hint">
      行数较多（{{ browseRowCount }} 行）· {{ browseMode ? '虚拟滚动速览' : '表格编辑' }}模式 · 双击行可切换编辑
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
    :row-event-handlers="rowEventHandlers"
    fixed
    class="virtual-table"
  />

  <template v-if="!useVirtualScroll || !browseMode">
  <!-- 按单项评估计提 -->
  <div class="section-block">
    <div class="section-header">
      <span class="section-title">按单项评估计提</span>
      <el-button v-if="!isReadonly" size="small" type="primary" @click="addRow('single')">添加行</el-button>
    </div>
    <el-table :data="singleDisplayRows" size="small" border stripe max-height="400" style="width:100%">
      <el-table-column label="项目" min-width="140" fixed>
        <template #default="{ row }">
          <template v-if="row._isSubtotal">
            <span class="subtotal-label">{{ row.itemName }}</span>
          </template>
          <el-input
            v-else-if="!isReadonly"
            :model-value="row.itemName"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'itemName', v)"
          />
          <span v-else>{{ row.itemName }}</span>
        </template>
      </el-table-column>
      <template v-for="col in numericCols" :key="'single-' + col.field">
        <el-table-column :label="col.label" :width="col.width" align="right" :class-name="col.auto ? 'auto-calc-col' : ''">
          <template #default="{ row }">
            <template v-if="row._isSubtotal">
              <span class="subtotal-amount">{{ fmtAmount(row[col.field]) }}</span>
            </template>
            <span v-else-if="col.auto" class="auto-calc">{{ fmtAmount(row[col.field]) }}</span>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row[col.field]"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(row.rowId, col.field, v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row[col.field]) }}</span>
          </template>
        </el-table-column>
      </template>
      <el-table-column v-if="!isReadonly" label="操作" width="60" fixed="right" align="center">
        <template #default="{ row }">
          <el-button v-if="!row._isSubtotal" type="danger" text size="small" @click="removeRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>

  <!-- 按信用风险组合计提 -->
  <div class="section-block">
    <div class="section-header">
      <span class="section-title">按信用风险组合计提</span>
      <el-button v-if="!isReadonly" size="small" type="primary" @click="addRow('group')">添加行</el-button>
    </div>
    <el-table :data="groupDisplayRows" size="small" border stripe max-height="400" style="width:100%">
      <el-table-column label="项目" min-width="140" fixed>
        <template #default="{ row }">
          <template v-if="row._isSubtotal">
            <span class="subtotal-label">{{ row.itemName }}</span>
          </template>
          <el-input
            v-else-if="!isReadonly"
            :model-value="row.itemName"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'itemName', v)"
          />
          <span v-else>{{ row.itemName }}</span>
        </template>
      </el-table-column>
      <template v-for="col in numericCols" :key="'group-' + col.field">
        <el-table-column :label="col.label" :width="col.width" align="right" :class-name="col.auto ? 'auto-calc-col' : ''">
          <template #default="{ row }">
            <template v-if="row._isSubtotal">
              <span class="subtotal-amount">{{ fmtAmount(row[col.field]) }}</span>
            </template>
            <span v-else-if="col.auto" class="auto-calc">{{ fmtAmount(row[col.field]) }}</span>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row[col.field]"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(row.rowId, col.field, v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row[col.field]) }}</span>
          </template>
        </el-table-column>
      </template>
      <el-table-column v-if="!isReadonly" label="操作" width="60" fixed="right" align="center">
        <template #default="{ row }">
          <el-button v-if="!row._isSubtotal" type="danger" text size="small" @click="removeRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
  </template>

  <!-- 合计 -->
  <div class="total-section">
    <span>期初审定合计：<strong>{{ fmtAmount(totalRow.priorAudited) }}</strong></span>
    <span>期末审定合计：<strong>{{ fmtAmount(totalRow.endAudited) }}</strong></span>
  </div>

  <!-- 审计意见区（卡片式） -->
  <el-card class="opinion-card" shadow="never">
    <template #header>
      <div class="opinion-header">
        <span class="opinion-title">审计说明与结论</span>
        <div class="opinion-chips">
          <GtIndexChip value="wp:D6-1" :context-project-id="projectId" />
          <GtIndexChip value="wp:D6-8" :context-project-id="projectId" />
        </div>
      </div>
    </template>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">1. 审计说明</span>
        <div class="opinion-actions">
          <el-tooltip :content="aiTip" placement="top">
            <el-button size="small" type="primary" plain :loading="aiLoading"
              :disabled="isReadonly || !aiAvailable" @click="genImpairmentNote">🤖 AI辅助</el-button>
          </el-tooltip>
          <GtReviewTrigger section-id="D6-3-note-explanation" label="💬 复核" />
        </div>
      </div>
      <el-input
        v-model="auditNotes.explanation"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="对减值准备明细的分析说明..."
      />
    </div>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">2. 审计结论</span>
        <div class="opinion-actions">
          <GtReviewTrigger section-id="D6-3-note-conclusion" label="💬 复核" />
        </div>
      </div>
      <el-input
        v-model="auditNotes.conclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="减值准备计提结论..."
      />
    </div>
  </el-card>
</div>
</template>

<script setup lang="ts">
/**
 * D6TabImpairmentDetail.vue — 减值准备明细 D6-3（14列63公式）
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { useD6ImpairmentDetail, type ImpairmentDetailRow } from '../composables/useD6ImpairmentDetail'
import type { ChecklistResponse } from '../composables/useD6FormData'
import { useD6ImportExport } from '../composables/useD6ImportExport'
import { useD6AiGenerate } from '../composables/useD6AiGenerate'
import { useWorkpaperBrowseMode } from '../composables/useWorkpaperBrowseMode'
import { virtualTextCol, virtualNumCol } from '../composables/virtualColumnHelpers'
import type { VirtualColumn } from '@/composables/useVirtualTable'
import GtReviewTrigger from '../GtReviewTrigger.vue'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, ChecklistResponse>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: any
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>
const { importing, exportTemplate, exportData, importData } = useD6ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D6-3',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})

async function onImportFile(file: File) {
  await importData(file)
}

const {
  singleRows,
  groupRows,
  singleSubtotal,
  groupSubtotal,
  totalRow,
  reconciliation,
  addRow,
  removeRow,
  updateCell,
  auditNotes,
} = useD6ImpairmentDetail({
  allResponses: allResponsesRef,
  crossSheet: props.crossSheet,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
})

const { generateAndConfirm, aiAvailable, loading: aiLoading } = useD6AiGenerate(toRef(props, 'wpId'))

const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

async function genImpairmentNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('impairment-note', auditNotes.value.explanation, {
    task: '合同资产减值准备明细分析说明',
    endAuditedTotal: totalRow.value.endAudited,
    reconciliationDiff: reconciliation.value.diff,
    singleRowCount: singleRows.value.length,
    groupRowCount: groupRows.value.length,
  }, 'AI · 减值准备说明')
  if (text) auditNotes.value.explanation = text
}

type NumericField = keyof Pick<ImpairmentDetailRow,
  'priorUnadjusted' | 'priorAje' | 'priorRje' | 'priorAudited' |
  'provision' | 'otherIncrease' | 'reversal' | 'writeOff' | 'otherDecrease' |
  'endUnadjusted' | 'endAje' | 'endRje' | 'endAudited'
>

const numericCols: Array<{ label: string; field: NumericField; width: number; auto?: boolean }> = [
  { label: '期初未审', field: 'priorUnadjusted', width: 100 },
  { label: '期初AJE', field: 'priorAje', width: 90 },
  { label: '期初RJE', field: 'priorRje', width: 90 },
  { label: '期初审定', field: 'priorAudited', width: 100, auto: true },
  { label: '计提', field: 'provision', width: 100 },
  { label: '其他增加', field: 'otherIncrease', width: 100 },
  { label: '转回', field: 'reversal', width: 90 },
  { label: '核销', field: 'writeOff', width: 90 },
  { label: '其他减少', field: 'otherDecrease', width: 100 },
  { label: '期末未审', field: 'endUnadjusted', width: 100, auto: true },
  { label: '期末AJE', field: 'endAje', width: 90 },
  { label: '期末RJE', field: 'endRje', width: 90 },
  { label: '期末审定', field: 'endAudited', width: 100, auto: true },
]

interface DisplayImpairmentRow extends ImpairmentDetailRow {
  _isSubtotal?: boolean
}

const singleDisplayRows = computed<DisplayImpairmentRow[]>(() => {
  const rows: DisplayImpairmentRow[] = singleRows.value.map(r => ({ ...r }))
  if (singleRows.value.length > 0) {
    rows.push({ ...singleSubtotal.value, _isSubtotal: true })
  }
  return rows
})

const groupDisplayRows = computed<DisplayImpairmentRow[]>(() => {
  const rows: DisplayImpairmentRow[] = groupRows.value.map(r => ({ ...r }))
  if (groupRows.value.length > 0) {
    rows.push({ ...groupSubtotal.value, _isSubtotal: true })
  }
  return rows
})

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const browseRows = computed(() => [...singleRows.value, ...groupRows.value])
const browseRowCount = computed(() => browseRows.value.length)

const virtualColumns = computed<VirtualColumn[]>(() => [
  virtualTextCol('itemName', '项目', 160),
  virtualNumCol('priorAudited', '期初审定', 100, fmtAmount),
  virtualNumCol('endAudited', '期末审定', 100, fmtAmount),
])

const {
  browseMode,
  useVirtualScroll,
  rowEventHandlers,
  tableWidth,
  tableHeight,
  toggleBrowseMode,
} = useWorkpaperBrowseMode({
  rows: browseRows,
  virtualColumns,
  tableWidth: 900,
})
</script>

<style scoped>
.d6-tab-impairment-detail { padding: 16px; }
.d6-tab-impairment-detail :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d6-tab-impairment-detail :deep(.el-table .cell) {
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
}
.chip-wrap { display: inline-flex; align-items: center; }

.recon-alert { margin-bottom: 12px; }

.virtual-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.virtual-hint { flex: 1; }

.section-block { margin-bottom: 20px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.section-title { font-size: 14px; font-weight: 600; }

/* 自动计算列灰底 */
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
.auto-calc { background: #f5f7fa; padding: 2px 6px; border-radius: 2px; color: #909399; }
.subtotal-label { font-weight: 700; }
.subtotal-amount { font-weight: 700; }

.total-section {
  margin-top: 12px;
  padding: 10px 12px;
  background: #fafafa;
  border-radius: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  font-size: var(--wp-font-size, 13px);
}

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
