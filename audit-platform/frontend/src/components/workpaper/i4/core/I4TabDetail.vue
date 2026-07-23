<template>
  <div class="i4-tab-detail">
    <el-alert type="info" :closable="false" class="objective-alert">
      <template #title>一、审计目标</template>
      <ol class="obj-list">
        <li v-for="(o, i) in I4_2_OBJECTIVES" :key="i">{{ o }}</li>
      </ol>
    </el-alert>

    <div class="guidance-block">
      <div class="guidance-grid">
        <div class="guidance-step"><span class="step-num">①</span><span>录入未审滚动：期初→增加→摊销/其他减少→期末</span></div>
        <div class="guidance-step"><span class="step-num">②</span><span>填期初调整与账项调整，自动生成审定滚动</span></div>
        <div class="guidance-step"><span class="step-num">③</span><span>完善摊销政策与合同索引，合计勾稽 I4-1</span></div>
        <div class="guidance-step"><span class="step-num">④</span><span>开办费不得资本化；对照税法大修理认定</span></div>
      </div>
    </div>

    <div class="methodology-context">
      <p>
        <strong>I4-2 编制逻辑（对齐 Excel 滚动勾稽）：</strong>
        先记录客户账面<strong>未审数</strong>，再登记<strong>期初调整 / 账项调整</strong>，公式生成<strong>审定数</strong>。
        本期减少拆分为「摊销」与「其他减少」（提前终止/转出），避免与正常摊销混淆。
        旧字段 beginBalance / currentIncrease 等由审定滚动自动回写，I4-1 / I4-5 不受影响。
      </p>
    </div>

    <el-alert
      v-if="rollWarnings.length"
      type="error"
      :closable="false"
      show-icon
      class="check-alert"
    >
      <template #title>
        风险/勾稽提示 {{ rollWarnings.length }} 处
      </template>
      <div class="warn-list">
        <div v-for="w in rollWarnings.slice(0, 5)" :key="`${w.rowId}-${w.kind}`">
          {{ w.projectName }}：{{ w.message || w.kind }}
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
        <GtIndexChip value="wp:I4-2" :context-project-id="projectId" />
        <el-button size="small" @click="emit('navigate-sheet', 'I4-1')">← I4-1</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I4-3')">I4-3 →</el-button>
        <el-button
          v-if="!isReadonly"
          type="primary"
          size="small"
          @click="handleAddRow"
        >
          + 新增
        </el-button>
        <I4SheetImportExport
          v-if="!isReadonly"
          sheet="I4-2"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          @imported="onImported"
        />
        <el-button size="small" type="primary" text @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
        <span class="row-count">共 {{ rows.length }} 行</span>
      </div>
    </div>

    <el-table
      :data="rows"
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
              <span class="formula-value">
                {{ col.key === 'amortizationProgress' ? fmtPercent(row[col.key]) : fmtAmount(row[col.key]) }}
              </span>
            </el-tooltip>
          </template>
          <template v-else-if="col.type === 'number'">
            <el-input-number
              v-if="col.editable && !isReadonly"
              :model-value="row[col.key]"
              size="small"
              :controls="false"
              :precision="2"
              class="amt-input"
              @change="(v: number | null) => onCellEdit(row.rowId, col.key, v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row[col.key]) }}</span>
          </template>
          <template v-else-if="col.type === 'date'">
            <el-date-picker
              v-if="col.editable && !isReadonly"
              :model-value="row[col.key]"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              style="width: 100%"
              @update:model-value="(v: string) => onCellEdit(row.rowId, col.key, v || '')"
            />
            <span v-else>{{ row[col.key] || '—' }}</span>
          </template>
          <template v-else-if="col.type === 'month'">
            <el-date-picker
              v-if="col.editable && !isReadonly"
              :model-value="row[col.key]"
              type="month"
              size="small"
              value-format="YYYY-MM"
              style="width: 100%"
              @update:model-value="(v: string) => onCellEdit(row.rowId, col.key, v || '')"
            />
            <span v-else>{{ row[col.key] || '—' }}</span>
          </template>
          <template v-else-if="col.type === 'select'">
            <el-select
              v-if="col.editable && !isReadonly"
              :model-value="row[col.key]"
              size="small"
              clearable
              filterable
              allow-create
              style="width: 100%"
              @change="(v: string) => onCellEdit(row.rowId, col.key, v || '')"
            >
              <el-option v-for="opt in col.options || []" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <span v-else>{{ row[col.key] || '—' }}</span>
          </template>
          <template v-else>
            <el-input
              v-if="col.editable && !isReadonly"
              :model-value="row[col.key]"
              size="small"
              @change="(v: string) => onCellEdit(row.rowId, col.key, v)"
            />
            <span v-else>{{ row[col.key] || '—' }}</span>
          </template>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="handleRemoveRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Excel 表尾：合计 + 类别小计 -->
    <div class="subtotals-bar">
      <span class="subtotal-label">合计：</span>
      <span class="subtotal-item">初始 {{ fmtAmount(subtotals.originalAmount) }}</span>
      <span class="subtotal-item">未审期末 {{ fmtAmount(subtotals.unadjEnding) }}</span>
      <span class="subtotal-item">审定期初 {{ fmtAmount(subtotals.auditedOpening) }}</span>
      <span class="subtotal-item">审定增加 {{ fmtAmount(subtotals.auditedIncrease) }}</span>
      <span class="subtotal-item">审定摊销 {{ fmtAmount(subtotals.auditedAmortization) }}</span>
      <span class="subtotal-item">审定其他减 {{ fmtAmount(subtotals.auditedOtherDecrease) }}</span>
      <span class="subtotal-item emphasize">审定期末 {{ fmtAmount(subtotals.auditedEnding) }}</span>
    </div>

    <div v-if="categorySubtotals.length" class="category-bar">
      <span class="subtotal-label">类别小计：</span>
      <el-tag
        v-for="c in categorySubtotals"
        :key="c.category"
        size="small"
        type="info"
        class="cat-tag"
      >
        {{ c.category }} {{ c.count }}项 / 审定 {{ fmtAmount(c.auditedEnding) }}
      </el-tag>
    </div>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>三、审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 4 }"
        placeholder="记录期初与上期审定核对、开办费排查、大修理税法判断、与 I4-1/I4-6 勾稽情况…"
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
        placeholder="明细是否完整准确；未审→审定滚动是否平衡；期末余额是否恰当…"
        @change="saveAuditConclusion"
      />
    </el-card>

    <details class="compile-hint" open>
      <summary>编制说明（对齐 Excel）</summary>
      <ol>
        <li v-for="(n, i) in I4_2_PREP_NOTES" :key="i">{{ n }}</li>
      </ol>
      <p class="tax-title">税法参考</p>
      <ul>
        <li v-for="(n, i) in I4_2_TAX_NOTES" :key="i">{{ n }}</li>
      </ul>
    </details>

    <details class="compile-hint">
      <summary>操作提示</summary>
      <ul>
        <li>区段：未审滚动 → 调整与审定 → 摊销信息 → 基础信息；行跨区段同步。</li>
        <li>公式：未审/审定期末 = 期初+增加−摊销−其他减少；审定* = 未审* + 对应调整。</li>
        <li>合计勾稽审定表 I4-1；本期摊销可与 I4-6/I4-7 测算交叉；抽凭总体取自本表本期增加（I4-5）。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I4TabDetail.vue — I4-2 明细表（未审→调整→审定滚动）
 */
import { ref, computed, toRef, inject, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import I4SheetImportExport from '../shared/I4SheetImportExport.vue'
import {
  useI4Detail,
  I4_2_OBJECTIVES,
  I4_2_PREP_NOTES,
  I4_2_TAX_NOTES,
  buildI4DetailConclusionDraft,
  type I4DetailRow,
} from '../../composables/useI4Detail'
import http from '@/utils/http'

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
  categorySubtotals,
  sections,
  setActiveRow,
  updateCell,
  addRow,
  removeRow,
} = useI4Detail(
  toRef(props, 'allResponses'),
  { onSave: (itemId, value) => emit('save', itemId, value) },
)

const segmentOptions = computed(() =>
  sections.map((s) => ({ label: s.label, value: s.key })),
)

function onImported(): void {
  ElMessage.success('导入完成，请核对明细行')
}

function onCurrentRowChange(row: I4DetailRow | null): void {
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

async function handleAiGenerate(): Promise<void> {
  try {
    await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'detail',
      prompt: 'I4长期待摊费用明细表数据分析',
      context: { wpCode: 'I4-2', rowCount: rows.value.length },
    })
  } catch { /* ignore */ }
}

function handleReview(): void {
  openReviewDialog('I4-2 明细表')
}

function rowClassName({ row }: { row: I4DetailRow }): string {
  return rollWarnings.value.some((w) => w.rowId === row.rowId) ? 'roll-warn-row' : ''
}

const NOTE_KEY = 'I4-detail-audit-note'
const CONCLUSION_KEY = 'I4-detail-audit-conclusion'
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
  auditConclusion.value = buildI4DetailConclusionDraft({
    rowCount: rows.value.length,
    auditedEnding: subtotals.value.auditedEnding,
    unadjEnding: subtotals.value.unadjEnding,
    warningCount: rollWarnings.value.length,
    categoryCount: categorySubtotals.value.length,
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
  if (value == null) return '—'
  if (Math.abs(value) < 0.005) return '—'
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${(value * 100).toFixed(1)}%`
}
</script>

<style scoped>
.i4-tab-detail { padding: 16px; font-size: var(--wp-font-size, 13px); }
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
.amt-input { width: 100%; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; padding-bottom: 2px; }
.formula-value {
  border-bottom: 1px dashed #c0c4cc; cursor: help; padding-bottom: 1px;
  color: #303133; font-weight: 500; font-variant-numeric: tabular-nums;
}

.subtotals-bar, .category-bar {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  padding: 10px 12px; margin-top: 10px;
  background: #f0f9ff; border-radius: 6px; font-size: 12px;
}
.category-bar { background: #f8fafc; }
.subtotal-label { font-weight: 600; color: #303133; }
.subtotal-item { color: #606266; }
.subtotal-item.emphasize { color: #1d4ed8; font-weight: 600; }
.cat-tag { margin: 0; }

.audit-note-card { margin-top: 12px; margin-bottom: 12px; }
.audit-note-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; }
.card-header { display: flex; align-items: center; justify-content: space-between; font-size: 14px; font-weight: 500; }

.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; color: #374151; }
.compile-hint ol, .compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.75; }
.compile-hint li { margin-bottom: 4px; }
.tax-title { margin: 10px 0 0; font-weight: 600; color: #374151; }

:deep(.roll-warn-row) { background-color: #fef2f2 !important; }
:deep(.roll-warn-row:hover > td) { background-color: #fee2e2 !important; }
</style>
