<template>
  <div class="i5-tab-detail">
    <el-alert type="info" :closable="false" class="objective-alert">
      <template #title>一、审计目标</template>
      <ol class="obj-list">
        <li v-for="(o, i) in I5_2_OBJECTIVES" :key="i">{{ o }}</li>
      </ol>
    </el-alert>

    <div class="guidance-block">
      <div class="guidance-grid">
        <div class="guidance-step"><span class="step-num">①</span><span>录入原值未审滚动：期初→增加→减少→期末</span></div>
        <div class="guidance-step"><span class="step-num">②</span><span>填期初调整 / 账项 / 重分类，自动生成审定</span></div>
        <div class="guidance-step"><span class="step-num">③</span><span>同步填报减值准备层，净值=原值−减值</span></div>
        <div class="guidance-step"><span class="step-num">④</span><span>合同类项目核对 CAS14 流动性并索引专项底稿</span></div>
      </div>
    </div>

    <div class="methodology-context">
      <p>
        <strong>I5-2 编制逻辑（对齐 Excel）：</strong>
        按类别编制<strong>原值</strong>滚动，再编制对应<strong>减值准备</strong>，系统生成<strong>净值</strong>。
        列结构：未审数 → 期初调整(账项/重分类) → 账项调整 → 重分类调整 → 审定数。
        旧字段 beginBalance/increase/endBalance 由<strong>净值审定</strong>回写，I5-1 带入不受影响。
      </p>
    </div>

    <el-alert
      v-if="rollWarnings.length"
      type="error"
      :closable="false"
      show-icon
      class="check-alert"
    >
      <template #title>风险/勾稽提示 {{ rollWarnings.length }} 处</template>
      <div class="warn-list">
        <div v-for="w in rollWarnings.slice(0, 5)" :key="`${w.rowId}-${w.kind}-${w.layer}`">
          {{ w.projectName }}：{{ w.message }}
        </div>
        <div v-if="rollWarnings.length > 5">…其余 {{ rollWarnings.length - 5 }} 处</div>
      </div>
    </el-alert>

    <div class="toolbar-row">
      <el-segmented
        v-model="activeSection"
        :options="segmentOptions"
        class="segment-bar"
      />
      <div class="toolbar-right">
        <GtIndexChip value="wp:I5-2" :context-project-id="projectId" />
        <el-button size="small" @click="emit('navigate-sheet', 'I5-1')">← I5-1</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I5-3')">I5-3 →</el-button>
        <el-button
          v-for="chip in crossRefChips"
          :key="chip.code"
          size="small"
          text
          type="primary"
          @click="emit('navigate-sheet', chip.code)"
        >
          {{ chip.label }}
        </el-button>
        <el-button
          v-if="!isReadonly"
          type="primary"
          size="small"
          @click="handleAddRow"
        >
          + 新增类别
        </el-button>
        <el-dropdown v-if="!isReadonly" trigger="click">
          <el-button size="small">
            导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" type="primary" text @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
        <span class="row-count">共 {{ rows.length }} 类</span>
      </div>
    </div>

    <div v-if="useVirtualScroll" class="virtual-toolbar">
      <el-alert type="info" :closable="false" class="virtual-hint">
        类别较多（{{ rows.length }} 行）· {{ browseMode ? '虚拟滚动速览' : '表格编辑' }}模式 · 双击行可切换编辑
      </el-alert>
      <el-button size="small" @click="browseMode = !browseMode">
        {{ browseMode ? '切换表格编辑' : '切换虚拟速览' }}
      </el-button>
    </div>

    <el-table-v2
      v-if="useVirtualScroll && browseMode"
      :columns="virtualColumns"
      :data="rows"
      :width="tableWidth"
      :height="520"
      :row-height="36"
      :header-height="40"
      :row-event-handlers="rowEventHandlers"
      fixed
      class="virtual-table"
    />

    <el-table
      v-else
      :data="pagedDetailRows"
      border
      size="small"
      highlight-current-row
      row-key="rowId"
      class="detail-table"
      max-height="520"
      :row-class-name="rowClassName"
      @current-change="onCurrentRowChange"
    >
      <el-table-column type="index" label="#" width="45" align="center" fixed="left" />

      <el-table-column
        v-for="col in activeColumns"
        :key="col.key"
        :prop="col.key"
        :label="col.label"
        :min-width="col.width"
        :align="col.type === 'number' || col.type === 'formula' ? 'right' : 'left'"
      >
        <template v-if="col.type === 'formula'" #header>
          <el-tooltip :content="col.tooltip" placement="top">
            <span class="formula-col-header">{{ col.label }}</span>
          </el-tooltip>
        </template>

        <template #default="{ row }">
          <template v-if="col.type === 'formula'">
            <el-tooltip :content="col.tooltip" placement="top">
              <span class="formula-value">{{ fmtAmount(getCellValue(row, col)) }}</span>
            </el-tooltip>
          </template>
          <template v-else-if="col.type === 'number'">
            <el-input-number
              v-if="col.editable && !isReadonly"
              :model-value="getCellValue(row, col)"
              size="small"
              :controls="false"
              :precision="2"
              class="amt-input"
              @change="(v: number | null) => onCellEdit(row.rowId, col.path || col.key, v ?? 0)"
            />
            <span v-else>{{ fmtAmount(getCellValue(row, col)) }}</span>
          </template>
          <template v-else>
            <el-input
              v-if="col.editable && !isReadonly && col.key !== 'projectName'"
              :model-value="getCellValue(row, col)"
              size="small"
              @change="(v: string) => onCellEdit(row.rowId, col.key, v)"
            />
            <el-input
              v-else-if="col.editable && !isReadonly && col.key === 'projectName' && !row.isBuiltin"
              :model-value="row.projectName"
              size="small"
              @change="(v: string) => onCellEdit(row.rowId, 'projectName', v)"
            />
            <span v-else>
              {{ getCellValue(row, col) || '—' }}
              <el-tag v-if="col.key === 'projectName' && row.indexRef" size="small" type="warning" class="idx-tag">
                →{{ row.indexRef }}
              </el-tag>
            </span>
          </template>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="72" align="center" fixed="right">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="handleRemoveRow(row.rowId)">
            {{ row.isBuiltin ? '清空' : '删除' }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination
      v-if="useVirtualScroll && !browseMode && rows.length > editPageSize"
      v-model:current-page="editPage"
      :page-size="editPageSize"
      :total="rows.length"
      layout="total, prev, pager, next"
      class="edit-pagination"
    />

    <div class="subtotals-bar">
      <span class="subtotal-label">合计：</span>
      <span class="subtotal-item">原值未审期末 {{ fmtAmount(subtotals.grossUnadjEnding) }}</span>
      <span class="subtotal-item">原值审定期末 {{ fmtAmount(subtotals.grossAuditedEnding) }}</span>
      <span class="subtotal-item">减值审定期末 {{ fmtAmount(subtotals.impAuditedEnding) }}</span>
      <span class="subtotal-item emphasize">净值审定期末 {{ fmtAmount(subtotals.netAuditedEnding) }}</span>
    </div>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>三、审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 4 }"
        placeholder="记录分类正确性、流动性判断、减值计提、与 I5-1/专项底稿勾稽情况…"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>四、审计结论</span>
          <el-button v-if="!isReadonly" size="small" text type="primary" @click="handleFillDraft">生成草稿</el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="原值/减值/净值是否完整准确；未审→审定滚动是否平衡；期末列报是否恰当…"
        @change="saveAuditConclusion"
      />
    </el-card>

    <details class="compile-hint" open>
      <summary>编制说明（对齐 Excel）</summary>
      <ol>
        <li v-for="(n, i) in I5_2_PREP_NOTES" :key="i">{{ n }}</li>
      </ol>
      <p class="tax-title">CAS14 / 财会〔2017〕22 号提示</p>
      <ul>
        <li v-for="(n, i) in I5_2_CAS14_TIPS" :key="i">{{ n }}</li>
      </ul>
    </details>

    <details class="compile-hint">
      <summary>操作提示</summary>
      <ul>
        <li>区段：原值未审 → 原值调整与审定 → 减值准备 → 净值与索引；行跨区段同步。</li>
        <li>公式对齐 Excel：L=B+F+G，M=C+H+J，N=D+I+K，O=L+M−N；净值=原值−减值。</li>
        <li>内置 10 类与源模板一致；合同资产/取得成本/履约成本可跳转 D7、M12、G2-13。</li>
        <li>合计勾稽审定表 I5-1（带入净值审定）；导入导出覆盖原值+减值结构。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I5TabDetail.vue — I5-2 明细表（原值|减值|净值 + 未审→调整→审定）
 */
import { ref, computed, toRef, inject, onMounted, h } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowDown, MagicStick } from '@element-plus/icons-vue'
import { useVirtualTable, type VirtualColumn } from '@/composables/useVirtualTable'
import GtIndexChip from '../../GtIndexChip.vue'
import {
  useI5Detail,
  I5_2_OBJECTIVES,
  I5_2_PREP_NOTES,
  I5_2_CAS14_TIPS,
  buildI5DetailConclusionDraft,
  type I5DetailRow,
} from '../../composables/useI5Detail'
import { useI5ImportExport } from '../../composables/useI5ImportExport'
import http from '@/utils/http'
import { DisplayPrefs_Key } from '../../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

// 🔴 金额展示走 displayPrefs 单一真源（千分符 / 2 位小数 / 单位「元」/ showZero 偏好）。
//    必须 setup **顶层** inject —— 写进函数体会静默失效（平台铁律）。
//    DisplayPrefs_Key 只能从 composables/displayPrefsKey 引入，
//    从 @/stores/displayPrefs 连带引会让整页崩（该 store 没有这个导出）。
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})
const isReadonly = computed(() => Boolean(props.isReadonly))
const projectId = computed(() => props.projectId)

const {
  rows,
  activeSection,
  activeColumns,
  subtotals,
  rollWarnings,
  sections,
  setActiveRow,
  getCellValue,
  updateCell,
  addRow,
  removeRow,
} = useI5Detail(
  toRef(props, 'allResponses'),
  { onSave: (itemId, value) => emit('save', itemId, value) },
)

const BROWSE_THRESHOLD = 30
const browseMode = ref(true)
const tableWidth = ref(1200)
const editPage = ref(1)
const editPageSize = 50
const useVirtualScroll = computed(() => rows.value.length > BROWSE_THRESHOLD)

const virtualColumns = computed<VirtualColumn[]>(() => {
  return [
    { key: 'projectName', dataKey: 'projectName', title: '项目', width: 160 },
    { key: 'category', dataKey: 'category', title: '类别', width: 120 },
    {
      key: 'ending',
      dataKey: 'projectName',
      title: '审定期末',
      width: 110,
      align: 'right',
      cellRenderer: ({ rowData }) => {
        const r = rowData as I5DetailRow
        const gross = Number(r.gross?.auditedEnding ?? 0)
        const imp = Number(r.impairment?.auditedEnding ?? 0)
        const val = activeSection.value === 'impairment' ? imp : gross - imp
        return h('span', {}, fmtAmount(val))
      },
    },
  ]
})

const { rowEventHandlers } = useVirtualTable({
  rows,
  columns: virtualColumns,
  width: tableWidth,
  height: 520,
  onRowDblclick: () => { browseMode.value = false },
})

const pagedDetailRows = computed(() => {
  if (!useVirtualScroll.value || browseMode.value) return rows.value
  const start = (editPage.value - 1) * editPageSize
  return rows.value.slice(start, start + editPageSize)
})

const { exportTemplate, exportData, importData } = useI5ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

const segmentOptions = computed(() =>
  sections.map((s) => ({ label: s.label, value: s.key })),
)

const crossRefChips = [
  { code: 'D7', label: '→D7 合同资产' },
  { code: 'M12', label: '→M12 取得成本' },
  { code: 'G2-13', label: '→G2-13 履约成本' },
]

function onCurrentRowChange(row: I5DetailRow | null): void {
  if (row) {
    const idx = rows.value.findIndex((r) => r.rowId === row.rowId)
    setActiveRow(idx)
  }
}

function onCellEdit(rowId: string, field: string, value: any): void {
  updateCell(rowId, field, value)
}

async function handleAddRow(): Promise<void> {
  await addRow()
}

function handleRemoveRow(rowId: string): void {
  removeRow(rowId)
}

function handleExportTemplate(): void {
  exportTemplate('I5-2')
}

function handleExportData(): void {
  exportData('I5-2')
}

async function handleImportData(): Promise<void> {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls,.csv'
  input.onchange = async (e: Event) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (file) await importData('I5-2', file)
  }
  input.click()
}

async function handleAiGenerate(): Promise<void> {
  try {
    await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'detail',
      prompt: 'I5其他非流动资产明细表（原值/减值/净值）数据分析',
      context: {
        wpCode: 'I5-2',
        rowCount: rows.value.length,
        netAuditedEnding: subtotals.value.netAuditedEnding,
      },
    })
  } catch { /* ignore */ }
}

function handleReview(): void {
  openReviewDialog('I5-2 明细表')
}

function rowClassName({ row }: { row: I5DetailRow }): string {
  return rollWarnings.value.some((w) => w.rowId === row.rowId) ? 'roll-warn-row' : ''
}

const NOTE_KEY = 'I5-detail-audit-note'
const CONCLUSION_KEY = 'I5-detail-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  emit('save', NOTE_KEY, val)
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  emit('save', CONCLUSION_KEY, val)
}

function handleFillDraft(): void {
  auditConclusion.value = buildI5DetailConclusionDraft({
    rowCount: rows.value.length,
    netAuditedEnding: subtotals.value.netAuditedEnding,
    grossAuditedEnding: subtotals.value.grossAuditedEnding,
    impAuditedEnding: subtotals.value.impAuditedEnding,
    warningCount: rollWarnings.value.length,
  })
  saveAuditConclusion(auditConclusion.value)
  ElMessage.success('已生成审计结论草稿')
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

function fmtAmount(value: number | null | undefined): string {
  return displayPrefs.fmtAmount(value)
}
</script>

<style scoped>
.i5-tab-detail { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.obj-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.6; font-size: 12px; }

.guidance-block {
  margin-bottom: 12px; padding: 10px 12px;
  background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px;
}
.guidance-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 8px;
}
.guidance-step { display: flex; align-items: flex-start; gap: 8px; font-size: 12px; color: #334155; line-height: 1.5; }
.step-num {
  flex-shrink: 0; width: 20px; height: 20px; border-radius: 50%;
  background: #1e40af; color: #fff; font-size: 11px; font-weight: 600;
  display: inline-flex; align-items: center; justify-content: center;
}

.methodology-context {
  border-left: 4px solid #d97706; background: #fffbeb;
  padding: 12px 16px; margin-bottom: 12px; border-radius: 4px;
  font-size: 12px; color: #92400e; line-height: 1.75;
}
.methodology-context p { margin: 0; }
.methodology-context strong { color: #78350f; }

.check-alert { margin-bottom: 10px; }
.warn-list { font-size: 12px; line-height: 1.6; }

.toolbar-row {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
}
.segment-bar { flex-shrink: 0; }
.toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.row-count { font-size: 12px; color: var(--el-text-color-secondary); }

.detail-table { font-size: var(--wp-font-size, 13px); }
.virtual-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.virtual-hint { flex: 1; margin: 0; }
.edit-pagination { margin-top: 8px; justify-content: flex-end; }
.amt-input { width: 100%; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; padding-bottom: 2px; }
.formula-value {
  border-bottom: 1px dashed #c0c4cc; cursor: help; padding-bottom: 1px;
  color: #303133; font-weight: 500; font-variant-numeric: tabular-nums;
}
.idx-tag { margin-left: 4px; }

.subtotals-bar {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  padding: 10px 12px; margin-top: 10px;
  background: #f0f9ff; border-radius: 6px; font-size: 12px;
}
.subtotal-label { font-weight: 600; color: #303133; }
.subtotal-item { color: #606266; }
.subtotal-item.emphasize { color: #1d4ed8; font-weight: 600; }

.audit-note-card { margin-top: 12px; margin-bottom: 12px; }
.audit-note-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; }
.card-header { display: flex; align-items: center; justify-content: space-between; font-size: 14px; font-weight: 500; }

.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; color: #374151; }
.compile-hint ol, .compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.75; }
.compile-hint li { margin-bottom: 4px; }
.tax-title { margin: 10px 0 0; font-weight: 600; color: #374151; }

:deep(.roll-warn-row) { background-color: #fef2f2 !important; }
</style>
