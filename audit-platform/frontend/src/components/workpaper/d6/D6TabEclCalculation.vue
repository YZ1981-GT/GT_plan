<template>
<div class="d6-tab-ecl-calculation">
  <!-- 编制提示 -->
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 本表依 CAS22 预期信用损失（ECL）模型测算合同资产（科目1402）应计提的坏账准备，分单项计提与账龄组合计提两部分。</p>
      <p>2. 灰色底纹列为自动计算列：应计提 = 审定余额 × 损失率；差异 = 应计提 − 账面余额，差异≥0.01 时高亮提示。</p>
      <p>3. 损失率应结合历史损失经验、当前状况及前瞻性信息确定，并与 D6-7 政策检查评价一致。</p>
      <p>4. 合计应计提与账面的总差异应查明原因，测算结果回填 D6-3 减值准备明细，为审定表坏账准备提供依据。</p>
    </div>
  </details>

  <!-- 审计目标 -->
  <el-alert
    type="info"
    :closable="false"
    title="审计目标：独立测算合同资产预期信用损失，评价被审计单位坏账准备计提的充分性与损失率选取的合理性。"
    class="objective-alert"
  />

  <!-- 工具栏 -->
  <div class="tab-toolbar">
    <div class="toolbar-left"></div>
    <div class="toolbar-right">
      <el-dropdown size="small" trigger="click">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="exportTemplate">导出模板</el-dropdown-item>
            <el-dropdown-item @click="exportData">导出数据</el-dropdown-item>
            <el-dropdown-item>
              <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
                <span>导入数据</span>
              </el-upload>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <span class="chip-wrap"><GtIndexChip value="wp:D6-7" :context-project-id="projectId" /></span>
      <span class="chip-wrap"><GtIndexChip value="wp:D6-3" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ browseRowCount }} 行</el-tag>
    </div>
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
  <!-- (一) 单项计提 -->
  <div class="ecl-block">
    <div class="block-header">
      <h4 class="block-title">(一) 单项计提坏账准备</h4>
      <el-button v-if="!isReadonly" size="small" type="primary" @click="addSingleRow">添加债务人</el-button>
    </div>
    <el-table :data="singleRows" size="small" border stripe style="width:100%">
      <el-table-column label="债务人名称" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.debtorName" size="small" @change="(v: string) => updateSingleCell(row.rowId, 'debtorName', v)" />
          <span v-else>{{ row.debtorName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审定余额①" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.auditedBalance" :controls="false" size="small" style="width:100%" @change="(v: number) => updateSingleCell(row.rowId, 'auditedBalance', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.auditedBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="损失率②" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.lossRate" :controls="false" :step="0.01" :max="1" size="small" style="width:100%" @change="(v: number) => updateSingleCell(row.rowId, 'lossRate', v ?? 0)" />
          <span v-else>{{ fmtPct(row.lossRate) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="应计提③" width="120" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="auto-calc">{{ fmtAmt(row.expectedProvision) }}</span></template>
      </el-table-column>
      <el-table-column label="账面余额④" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.bookBalance" :controls="false" size="small" style="width:100%" @change="(v: number) => updateSingleCell(row.rowId, 'bookBalance', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.bookBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="差异⑤" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span :class="['auto-calc', { 'diff-warn': Math.abs(row.difference) >= 0.01 }]">{{ fmtAmt(row.difference) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="计提依据" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.basis" size="small" @change="(v: string) => updateSingleCell(row.rowId, 'basis', v)" />
          <span v-else>{{ row.basis }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引号" width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small" @change="(v: string) => updateSingleCell(row.rowId, 'indexRef', v)" />
          <span v-else>{{ row.indexRef }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="50" align="center">
        <template #default="{ row }">
          <el-button type="danger" text size="small" @click="removeSingleRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="subtotal-line">
      单项小计 — 应计提：{{ fmtAmt(singleTotal.provision) }}，账面：{{ fmtAmt(singleTotal.book) }}，差异：{{ fmtAmt(singleTotal.diff) }}
    </div>
  </div>

  <!-- (二) 账龄组合 -->
  <div class="ecl-block">
    <div class="block-header">
      <h4 class="block-title">(二) 账龄组合计提坏账准备</h4>
      <el-button v-if="!isReadonly" size="small" type="primary" @click="addAgingGroup">添加组合</el-button>
    </div>

    <div v-for="(group, gIdx) in agingGroups" :key="group.groupId" class="aging-group">
      <div class="group-header">
        <el-input
          v-if="!isReadonly"
          :model-value="group.groupName"
          size="small"
          placeholder="组合名称"
          style="width:200px"
          @change="(v: string) => updateGroupName(group.groupId, v)"
        />
        <span v-else class="group-name">{{ group.groupName || `组合${gIdx + 1}` }}</span>
        <el-button v-if="!isReadonly" type="danger" text size="small" @click="removeAgingGroup(group.groupId)">删除组合</el-button>
      </div>
      <el-table :data="group.rows" size="small" border stripe>
        <el-table-column prop="agingBand" label="账龄" width="100" />
        <el-table-column label="审定余额①" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.auditedBalance" :controls="false" size="small" style="width:100%" @change="(v: number) => updateAgingCell(group.groupId, row.rowId, 'auditedBalance', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.auditedBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="损失率②" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.lossRate" :controls="false" :step="0.01" :max="1" size="small" style="width:100%" @change="(v: number) => updateAgingCell(group.groupId, row.rowId, 'lossRate', v ?? 0)" />
            <span v-else>{{ fmtPct(row.lossRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="应计提③" width="120" align="right" class-name="auto-calc-col">
          <template #default="{ row }"><span class="auto-calc">{{ fmtAmt(row.expectedProvision) }}</span></template>
        </el-table-column>
        <el-table-column label="账面余额④" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.bookBalance" :controls="false" size="small" style="width:100%" @change="(v: number) => updateAgingCell(group.groupId, row.rowId, 'bookBalance', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.bookBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异⑤" width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span :class="['auto-calc', { 'diff-warn': Math.abs(row.difference) >= 0.01 }]">{{ fmtAmt(row.difference) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="subtotal-line">
        组合小计 — 应计提：{{ fmtAmt(agingGroupTotals[gIdx]?.provision) }}，账面：{{ fmtAmt(agingGroupTotals[gIdx]?.book) }}，差异：{{ fmtAmt(agingGroupTotals[gIdx]?.diff) }}
      </div>
    </div>
  </div>

  <!-- 合计 -->
  <div class="grand-total">
    <span>合计应计提：<strong>{{ fmtAmt(grandTotal.expectedProvision) }}</strong></span>
    <span>合计账面：<strong>{{ fmtAmt(grandTotal.bookBalance) }}</strong></span>
    <span>总差异：<strong :class="{ 'diff-warn': Math.abs(grandTotal.totalDiff) >= 0.01 }">{{ fmtAmt(grandTotal.totalDiff) }}</strong></span>
    <GtIndexChip value="wp:D6-7" :context-project-id="projectId" style="margin-left:8px" />
    <GtIndexChip value="wp:D6-3" :context-project-id="projectId" style="margin-left:4px" />
  </div>

  <el-alert v-if="diffAlert" type="warning" :closable="false" show-icon style="margin-top:12px">
    {{ diffAlert }}
  </el-alert>

  <!-- 审计意见区（卡片式） -->
  <el-card class="opinion-card" shadow="never">
    <template #header>
      <div class="opinion-header">
        <span class="opinion-title">审计说明与结论</span>
        <div class="opinion-chips">
          <GtIndexChip value="wp:D6-7" :context-project-id="projectId" />
          <GtIndexChip value="wp:D6-3" :context-project-id="projectId" />
        </div>
      </div>
    </template>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">1. 审计说明</span>
        <div class="opinion-actions">
          <el-button size="small" @click="openReview('D6-8-note-explanation')">💬</el-button>
        </div>
      </div>
      <el-input v-model="auditNotes.explanation" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="ECL模型参数及损失率选取依据..." />
    </div>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">2. 审计结论</span>
        <div class="opinion-actions">
          <el-button size="small" @click="openReview('D6-8-note-conclusion')">💬</el-button>
        </div>
      </div>
      <el-input v-model="auditNotes.conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="减值准备计提充分性结论..." />
    </div>
  </el-card>
  </template>
</div>
</template>

<script setup lang="ts">
/**
 * D6TabEclCalculation.vue — 减值准备测算 D6-8
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { useD6EclCalculation } from '../composables/useD6EclCalculation'
import { useD6ImportExport } from '../composables/useD6ImportExport'
import { useWorkpaperBrowseMode } from '../composables/useWorkpaperBrowseMode'
import { virtualTextCol, virtualNumCol } from '../composables/virtualColumnHelpers'
import type { VirtualColumn } from '@/composables/useVirtualTable'
import type { ChecklistResponse } from '../composables/useD6FormData'
import type useD6CrossSheet from '../composables/useD6CrossSheet'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, ChecklistResponse>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: ReturnType<typeof useD6CrossSheet>
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
function openReview(sectionId: string) { openReviewDialog(sectionId) }

const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>
const { importing, exportTemplate, exportData, importData } = useD6ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D6-8',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})

async function onImportFile(file: File) {
  await importData(file)
  return false
}

const {
  singleRows, singleTotal, addSingleRow, removeSingleRow, updateSingleCell,
  agingGroups, agingGroupTotals, addAgingGroup, removeAgingGroup, updateGroupName, updateAgingCell,
  grandTotal, diffAlert, auditNotes,
} = useD6EclCalculation({
  allResponses: allResponsesRef,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
})

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const browseRows = computed(() => {
  const flat: Array<{ label: string; auditedBalance: number; expectedProvision: number; difference: number }> = []
  for (const r of singleRows.value) {
    flat.push({
      label: `[单项] ${r.debtorName || '-'}`,
      auditedBalance: r.auditedBalance,
      expectedProvision: r.expectedProvision,
      difference: r.difference,
    })
  }
  for (const g of agingGroups.value) {
    for (const r of g.rows) {
      flat.push({
        label: `[${g.groupName}] ${r.agingBand}`,
        auditedBalance: r.auditedBalance,
        expectedProvision: r.expectedProvision,
        difference: r.difference,
      })
    }
  }
  return flat
})

const browseRowCount = computed(() => browseRows.value.length)

const virtualColumns = computed<VirtualColumn[]>(() => [
  virtualTextCol('label', '项目', 220),
  virtualNumCol('auditedBalance', '审定余额', 110, fmtAmt),
  virtualNumCol('expectedProvision', '应计提', 110, fmtAmt),
  virtualNumCol('difference', '差异', 100, fmtAmt),
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
  tableWidth: 900,
})

function fmtPct(rate: number): string {
  if (!rate) return '-'
  return `${(rate * 100).toFixed(2)}%`
}
</script>

<style scoped>
.d6-tab-ecl-calculation { padding: 16px; }
.d6-tab-ecl-calculation :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d6-tab-ecl-calculation :deep(.el-table .cell) {
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

.virtual-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.virtual-hint { flex: 1; min-width: 200px; margin: 0; }
.virtual-table { margin-bottom: 12px; }
.ecl-block { margin-bottom: 20px; }
.block-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.block-title { font-size: 14px; font-weight: 600; margin: 0; color: #303133; }
.aging-group { margin-bottom: 16px; padding: 12px; border: 1px solid #ebeef5; border-radius: 6px; }
.group-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.group-name { font-weight: 600; font-size: var(--wp-font-size, 13px); }
.subtotal-line { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; }
.grand-total {
  padding: 12px;
  background: #fafafa;
  border-radius: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  align-items: center;
  font-size: var(--wp-font-size, 13px);
}

/* 自动计算列灰底 */
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
.auto-calc { background: #f5f7fa; padding: 2px 6px; border-radius: 2px; color: #909399; }
.diff-warn { color: #e6a23c; font-weight: 600; }

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
