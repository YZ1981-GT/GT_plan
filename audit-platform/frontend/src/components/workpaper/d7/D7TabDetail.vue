<template>
<div class="d7-detail">
  <!-- 编制提示 -->
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 本表按客户/合同列示合同负债（科目2205）明细，依据 CAS14 收入准则反映企业已收对价而尚未履行的履约义务。</p>
      <p>2. 灰色底纹列为自动计算列（期初审定/期末余额/期末未审/期末审定），不可手工编辑；支持从余额表一键导入客户明细。</p>
      <p>3. 关联方交易应在"关联关系"列标注，账龄按 1年以内 / 1~2年 / 2~3年 / 3年以上 四档归集，账龄超1年需在 D7-5 分析未结转原因。</p>
      <p>4. 全表自动生成合计行，请与 D7-1 审定表按性质聚合核对一致。</p>
    </div>
  </details>

  <!-- 审计目标 -->
  <el-alert
    type="info"
    :closable="false"
    title="审计目标：核实合同负债各明细项目期末余额的存在与准确，确认账龄分布及关联方归属，为审定表按性质/账龄聚合提供依据。"
    class="objective-alert"
  />

  <!-- 工具栏 -->
  <div class="tab-toolbar">
    <div class="toolbar-left">
      <el-input v-model="searchFilter" placeholder="搜索单位名称/合同名称..." size="small" style="width:220px" clearable />
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加客户</el-button>
      <el-button size="small" :disabled="isReadonly" @click="importFromAuxBalance">从余额表导入</el-button>
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
      <el-popover trigger="click" :width="260" placement="bottom-end">
        <template #reference>
          <el-button size="small" circle><el-icon><Setting /></el-icon></el-button>
        </template>
        <div class="col-prefs-popover">
          <div class="col-prefs-header">
            <span>列显示设置</span>
            <el-button size="small" text type="primary" @click="resetDefaults">重置默认</el-button>
          </div>
          <div v-for="group in columnGroups" :key="group.label" class="col-prefs-group">
            <div class="col-prefs-group-label">{{ group.label }}</div>
            <div v-for="key in group.keys" :key="key" class="col-prefs-item">
              <el-checkbox
                :model-value="isColVisible(key)"
                :disabled="group.alwaysShow"
                size="small"
                @change="toggleCol(key)"
              >{{ getColLabel(key) }}</el-checkbox>
            </div>
          </div>
        </div>
      </el-popover>
      <span class="chip-wrap"><GtIndexChip value="wp:D7-1" :context-project-id="projectId" /></span>
      <span class="chip-wrap"><GtIndexChip value="wp:D7-5" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
    </div>
  </div>

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
    <!-- 27列明细表 -->
    <el-table
      :data="displayRows"
      size="small"
      border
      max-height="600"
      :row-class-name="({ row }: any) => detailRowClassName(row)"
      style="width:100%"
    >
      <!-- 固定列 -->
      <el-table-column prop="contractName" label="合同名称" width="150" fixed>
        <template #default="{ row }">
          <el-input v-if="isDataRow(row) && !isReadonly" :model-value="row.contractName" size="small" @change="(v: string) => updateCell(row.rowId, 'contractName', v)" />
          <span v-else class="label-bold">{{ row.contractName }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="companyName" label="单位名称" width="150" fixed>
        <template #default="{ row }">
          <el-input v-if="isDataRow(row) && !isReadonly" :model-value="row.companyName" size="small" @change="(v: string) => updateCell(row.rowId, 'companyName', v)" />
          <span v-else>{{ row.companyName }}</span>
        </template>
      </el-table-column>

      <!-- 类型(款项性质) -->
      <el-table-column label="类型(款项性质)" width="140">
        <template #default="{ row }">
          <el-select v-if="isDataRow(row) && !isReadonly" :model-value="row.natureType" size="small" placeholder="请选择" @change="(v: string) => updateCell(row.rowId, 'natureType', v)">
            <el-option v-for="t in NATURE_TYPES" :key="t" :label="t" :value="t" />
          </el-select>
          <span v-else>{{ row.natureType }}</span>
        </template>
      </el-table-column>

      <!-- 关联关系 -->
      <el-table-column v-if="isColVisible('relatedPartyType')" label="关联关系" width="140">
        <template #default="{ row }">
          <el-select v-if="isDataRow(row) && !isReadonly" :model-value="row.relatedPartyType" size="small" placeholder="请选择" @change="(v: string) => updateCell(row.rowId, 'relatedPartyType', v)">
            <el-option v-for="t in RELATED_PARTY_TYPES" :key="t" :label="t" :value="t" />
          </el-select>
          <span v-else>{{ row.relatedPartyType }}</span>
        </template>
      </el-table-column>

      <!-- 期初 -->
      <el-table-column v-if="isColVisible('priorUnadjusted')" label="期初未审" width="110" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="isDataRow(row) && !isReadonly" :model-value="row.priorUnadjusted" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'priorUnadjusted', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.priorUnadjusted) }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="isColVisible('priorAje')" label="期初AJE" width="100" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="isDataRow(row) && !isReadonly" :model-value="row.priorAje" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'priorAje', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.priorAje) }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="isColVisible('priorRje')" label="期初RJE" width="100" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="isDataRow(row) && !isReadonly" :model-value="row.priorRje" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'priorRje', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.priorRje) }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="isColVisible('priorAudited')" label="期初审定" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="auto-calc">{{ fmtAmt(row.priorAudited) }}</span></template>
      </el-table-column>

      <!-- 期初账龄（按项目账龄段动态生成） -->
      <el-table-column
        v-for="band in visiblePriorBands"
        :key="`prior-${band.key}`"
        :label="`期初·${band.label}`"
        width="100"
        align="right"
      >
        <template #default="{ row }">
          <el-input-number v-if="isDataRow(row) && !isReadonly" :model-value="row.agingPrior?.[band.key] ?? 0" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, band.priorField, v ?? 0)" />
          <span v-else>{{ fmtAmt(row.agingPrior?.[band.key]) }}</span>
        </template>
      </el-table-column>

      <!-- 借贷发生 -->
      <el-table-column v-if="isColVisible('debitAmount')" label="借方发生" width="110" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="isDataRow(row) && !isReadonly" :model-value="row.debitAmount" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'debitAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="isColVisible('creditAmount')" label="贷方发生" width="110" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="isDataRow(row) && !isReadonly" :model-value="row.creditAmount" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'creditAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 期末 -->
      <el-table-column label="期末余额" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="auto-calc">{{ fmtAmt(row.endBalance) }}</span></template>
      </el-table-column>
      <el-table-column label="重分类" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="isDataRow(row) && !isReadonly" :model-value="row.entityReclass" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'entityReclass', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.entityReclass) }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="isColVisible('endUnadjusted')" label="期末未审" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="auto-calc">{{ fmtAmt(row.endUnadjusted) }}</span></template>
      </el-table-column>
      <el-table-column v-if="isColVisible('endAje')" label="期末AJE" width="100" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="isDataRow(row) && !isReadonly" :model-value="row.endAje" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'endAje', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.endAje) }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="isColVisible('endRje')" label="期末RJE" width="100" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="isDataRow(row) && !isReadonly" :model-value="row.endRje" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'endRje', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.endRje) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末审定" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="auto-calc">{{ fmtAmt(row.endAudited) }}</span></template>
      </el-table-column>

      <!-- 期末账龄（按项目账龄段动态生成） -->
      <el-table-column
        v-for="band in visibleAuditedBands"
        :key="`audited-${band.key}`"
        :label="`期末·${band.label}`"
        width="100"
        align="right"
      >
        <template #default="{ row }">
          <el-input-number v-if="isDataRow(row) && !isReadonly" :model-value="row.agingAudited?.[band.key] ?? 0" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, band.auditedField, v ?? 0)" />
          <span v-else>{{ fmtAmt(row.agingAudited?.[band.key]) }}</span>
        </template>
      </el-table-column>

      <!-- 其他 -->
      <el-table-column label="期后结转" width="100" align="right">
        <template #default="{ row }"><span>{{ fmtAmt(row.postTransfer) }}</span></template>
      </el-table-column>
      <el-table-column label="是否发函" width="80" align="center">
        <template #default="{ row }"><span>{{ row.isConfirmed || '-' }}</span></template>
      </el-table-column>

      <!-- 操作 -->
      <el-table-column v-if="!isReadonly" label="" width="60" fixed="right" align="center">
        <template #default="{ row }">
          <el-popconfirm v-if="isDataRow(row)" title="确认删除？" @confirm="removeRow(row.rowId)">
            <template #reference>
              <el-button type="danger" text size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明与结论</span>
          <div class="opinion-chips">
            <GtIndexChip value="wp:D7-1" :context-project-id="projectId" />
            <GtIndexChip value="wp:D7-5" :context-project-id="projectId" />
          </div>
        </div>
      </template>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">1. 期末变动分析</span>
          <div class="opinion-actions">
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :loading="aiLoading"
                :disabled="isReadonly || !aiAvailable" @click="genDetailChange">🤖 AI辅助</el-button>
            </el-tooltip>
          </div>
        </div>
        <el-input
          v-model="detailNotes.explanation"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="分析合同负债明细本期增减变动原因..."
        />
      </div>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">2. 合同履行情况</span>
        </div>
        <el-input
          v-model="detailNotes.contract"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="说明主要合同的履约进度及收入确认情况..."
        />
      </div>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">3. 超1年原因</span>
          <div class="opinion-actions">
            <GtIndexChip value="wp:D7-5" :context-project-id="projectId" />
          </div>
        </div>
        <el-input
          v-model="detailNotes.longTerm"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="账龄超过1年的合同负债未结转原因..."
        />
      </div>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">4. 审计结论</span>
          <div class="opinion-actions">
            <el-button size="small" @click="openReviewDialog('D7-2-note-conclusion')">💬</el-button>
          </div>
        </div>
        <el-input
          v-model="detailNotes.conclusion"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="对合同负债明细的总结性结论..."
        />
      </div>
    </el-card>
  </template>
</div>
</template>

<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
/**
 * D7TabDetail.vue — 明细表 D7-2 (~400行), 27列横向滚动
 * Task: 17.1
 * Requirements: 5.1-5.12, 6.1-6.7, 7.1-7.5, 17.2, 19.3, 20.1, 22.1-22.5
 */
import { ref, computed, watch, inject, toRef, type Ref } from 'vue'
import { Setting } from '@element-plus/icons-vue'
import { useD7Detail, NATURE_TYPES, RELATED_PARTY_TYPES, type DetailRow } from '../composables/useD7Detail'
import { useD7DetailColumnPrefs } from '../composables/useD7DetailColumnPrefs'
import type { ChecklistResponse } from '../composables/useD7FormData'
import { useD7ImportExport } from '../composables/useD7ImportExport'
import { useD7AiGenerate } from '../composables/useD7AiGenerate'
import { useWorkpaperBrowseMode } from '../composables/useWorkpaperBrowseMode'
import { virtualTextCol, virtualNumCol } from '../composables/virtualColumnHelpers'
import type { VirtualColumn } from '@/composables/useVirtualTable'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const COL_LABELS: Record<string, string> = {
  customerName: '单位名称', contractName: '合同名称', natureType: '类型(款项性质)',
  priorUnadjusted: '期初未审', priorAje: '期初AJE', priorRje: '期初RJE', priorAudited: '期初审定',
  creditAmount: '贷方发生', debitAmount: '借方发生', endUnadjusted: '期末未审',
  endAje: '期末AJE', endRje: '期末RJE', endAudited: '期末审定',
  relatedPartyType: '关联关系', remark: '备注',
}

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
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>
const { importing, exportTemplate, exportData, importData } = useD7ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D7-2',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})

async function onImportFile(file: File) {
  await importData(file)
  return false
}

const relatedParties = computed(() => {
  const json = allResponsesRef.value.get('D7-6-rows')?.remark
  if (!json) return [] as string[]
  try {
    const parsed = JSON.parse(json)
    if (!Array.isArray(parsed)) return []
    return parsed
      .map((r: { partyName?: string; companyName?: string }) => r.partyName || r.companyName || '')
      .filter(Boolean)
  } catch {
    return []
  }
})

const {
  rows, totalRow, addRow, removeRow, updateCell, importFromAuxBalance, searchFilter, filteredRows,
  segments, bands,
} = useD7Detail({
  allResponses: allResponsesRef,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  relatedParties,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})

// ─── Column Preferences（账龄组按当前 segments 动态生成）──────────────────────
const { columnGroups, isColVisible, toggleCol, resetDefaults, colLabel } = useD7DetailColumnPrefs(segments)
function getColLabel(key: string): string { return COL_LABELS[key] || colLabel(key) }

// 账龄列显隐过滤（避免 v-if + v-for 同元素坑）
const visiblePriorBands = computed(() => bands.value.filter(b => isColVisible(b.priorField)))
const visibleAuditedBands = computed(() => bands.value.filter(b => isColVisible(b.auditedField)))

// Display rows: filtered data + total row
const displayRows = computed(() => [...filteredRows.value, totalRow.value])

const browseRows = filteredRows
const browseRowCount = computed(() => filteredRows.value.length)

function fmtBrowseAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const virtualColumns = computed<VirtualColumn[]>(() => [
  virtualTextCol('contractName', '合同名称', 150),
  virtualTextCol('companyName', '单位名称', 150),
  virtualTextCol('natureType', '类型', 120),
  virtualNumCol('priorUnadjusted', '期初未审', 110, fmtBrowseAmt),
  virtualNumCol('endUnadjusted', '期末未审', 110, fmtBrowseAmt),
  virtualNumCol('endAudited', '期末审定', 110, fmtBrowseAmt),
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
  tableWidth: 1400,
})

function isDataRow(row: DetailRow): boolean {
  return !row.rowId.startsWith('__')
}

function detailRowClassName(row: DetailRow): string {
  if (!row) return ''
  if (row.rowId?.startsWith('__')) return 'total-row'
  if (row.relatedPartyType && row.relatedPartyType !== '非关联方' && row.relatedPartyType !== '') return 'related-party-row'
  return ''
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// Audit notes for detail tab
const detailNotes = ref({ explanation: '', contract: '', longTerm: '', conclusion: '' })

watch(() => allResponsesRef.value, (map) => {
  detailNotes.value.explanation = map.get('D7-2-note-explanation')?.remark || ''
  detailNotes.value.contract = map.get('D7-2-note-contract')?.remark || ''
  detailNotes.value.longTerm = map.get('D7-2-note-longterm')?.remark || ''
  detailNotes.value.conclusion = map.get('D7-2-note-conclusion')?.remark || ''
}, { immediate: true })

watch(() => detailNotes.value.explanation, v => props.debouncedSave('D7-2-note-explanation', { remark: v }))
watch(() => detailNotes.value.contract, v => props.debouncedSave('D7-2-note-contract', { remark: v }))
watch(() => detailNotes.value.longTerm, v => props.debouncedSave('D7-2-note-longterm', { remark: v }))
watch(() => detailNotes.value.conclusion, v => props.debouncedSave('D7-2-note-conclusion', { remark: v }))

const { generateAndConfirm, aiAvailable, loading: aiLoading } = useD7AiGenerate(toRef(props, 'wpId'))

const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

async function genDetailChange() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('detail-change', detailNotes.value.explanation, {
    task: '合同负债明细变动分析',
    rowCount: filteredRows.value.length,
    endAuditedTotal: totalRow.value.endAudited,
  }, 'AI · 变动分析')
  if (text) detailNotes.value.explanation = text
}
</script>

<style scoped>
.d7-detail { padding: 12px; }
.d7-detail :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d7-detail :deep(.el-table .cell) {
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
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

.virtual-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.virtual-hint { flex: 1; margin: 0; }

/* 自动计算列灰底 */
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.auto-calc { background: #f5f7fa; padding: 2px 4px; border-radius: 2px; color: #909399; font-size: 12px; }
.label-bold { font-weight: 700; }

:deep(.total-row) { background-color: #fafafa !important; font-weight: 600; }
:deep(.related-party-row) { background-color: #fdf6ec !important; }

/* 审计意见卡片 */
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-chips { display: flex; gap: 6px; }
.opinion-section { margin-bottom: 16px; }
.opinion-section:last-child { margin-bottom: 0; }
.opinion-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.opinion-section-label { font-size: 14px; font-weight: 500; color: #303133; }
.opinion-actions { display: flex; gap: 6px; align-items: center; }

/* 列设置 popover */
.col-prefs-popover { max-height: 320px; overflow-y: auto; }
.col-prefs-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-weight: 600; }
.col-prefs-group { margin-bottom: 8px; }
.col-prefs-group-label { font-size: 12px; color: #909399; margin-bottom: 4px; }
.col-prefs-item { margin-left: 8px; }
</style>
