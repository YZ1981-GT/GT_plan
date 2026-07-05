<template>
<div class="d6-tab-ecl-calculation">
  <div class="toolbar">
    <el-button-group size="small">
      <el-button @click="exportTemplate">导出模板</el-button>
      <el-button @click="exportData">导出数据</el-button>
      <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
        <el-button :loading="importing">导入数据</el-button>
      </el-upload>
    </el-button-group>
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
    <el-table :data="singleRows" size="small" border style="width:100%">
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
      <el-table-column label="应计提③" width="120" align="right">
        <template #default="{ row }"><span class="auto-calc">{{ fmtAmt(row.expectedProvision) }}</span></template>
      </el-table-column>
      <el-table-column label="账面余额④" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.bookBalance" :controls="false" size="small" style="width:100%" @change="(v: number) => updateSingleCell(row.rowId, 'bookBalance', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.bookBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="差异⑤" width="110" align="right">
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
      <el-table :data="group.rows" size="small" border>
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
        <el-table-column label="应计提③" width="120" align="right">
          <template #default="{ row }"><span class="auto-calc">{{ fmtAmt(row.expectedProvision) }}</span></template>
        </el-table-column>
        <el-table-column label="账面余额④" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.bookBalance" :controls="false" size="small" style="width:100%" @change="(v: number) => updateAgingCell(group.groupId, row.rowId, 'bookBalance', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.bookBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异⑤" width="110" align="right">
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
    <GtIndexChip wp-code="D6-7" label="→D6-7政策" style="margin-left:8px" />
    <GtIndexChip wp-code="D6-3" label="→D6-3明细" style="margin-left:4px" />
  </div>

  <el-alert v-if="diffAlert" type="warning" :closable="false" show-icon style="margin-top:12px">
    {{ diffAlert }}
  </el-alert>

  <!-- 审计说明/结论 -->
  <div class="audit-notes-section">
    <h4>审计说明</h4>
    <el-input v-model="auditNotes.explanation" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="ECL模型参数及损失率选取依据..." />
    <div class="note-actions">
      <el-button size="small" @click="openReview('D6-8-note-explanation')">💬复核</el-button>
    </div>
  </div>
  <div class="audit-notes-section">
    <h4>审计结论</h4>
    <el-input v-model="auditNotes.conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="减值准备计提充分性结论..." />
    <div class="note-actions">
      <el-button size="small" @click="openReview('D6-8-note-conclusion')">💬复核</el-button>
    </div>
  </div>
  </template>
</div>
</template>

<script setup lang="ts">
/**
 * D6TabEclCalculation.vue — 减值准备测算 D6-8
 */
import { computed, inject, type Ref } from 'vue'
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
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: ReturnType<typeof useD6CrossSheet>
}>()

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
  allResponses: props.allResponses,
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
.toolbar { margin-bottom: 12px; }
.virtual-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.virtual-hint { flex: 1; min-width: 200px; margin: 0; }
.virtual-table { margin-bottom: 12px; }
.ecl-block { margin-bottom: 20px; }
.block-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.block-title { font-size: 14px; font-weight: 600; margin: 0; color: #303133; }
.aging-group { margin-bottom: 16px; padding: 12px; border: 1px solid #ebeef5; border-radius: 6px; }
.group-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.group-name { font-weight: 600; font-size: 13px; }
.subtotal-line { margin-top: 8px; font-size: 13px; color: #606266; }
.grand-total {
  padding: 12px;
  background: #fafafa;
  border-radius: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  align-items: center;
  font-size: 13px;
}
.auto-calc { background: #f5f7fa; padding: 2px 6px; border-radius: 2px; color: #909399; }
.diff-warn { color: #e6a23c; font-weight: 600; }
.audit-notes-section { margin-top: 16px; }
.audit-notes-section h4 { font-size: 14px; font-weight: 600; margin-bottom: 8px; }
.note-actions { display: flex; gap: 8px; margin-top: 6px; }
</style>
