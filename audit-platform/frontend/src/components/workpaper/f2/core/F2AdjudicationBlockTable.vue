<template>
  <div class="f2-adjudication-block">
    <!-- 编制提示（可编辑审定区块，随 allResponses 提供时展示） -->
    <details v-if="allResponses" class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本区块按存货类别审定{{ blockLabel }}，期末未审 = 期初 + 增加 − 减少；期末审定 = 未审数 + 账项调整（灰底为公式，只读）。</p>
        <p>2. 依《企业会计准则第 1 号——存货》，存货期末按成本与可变现净值孰低计量，跌价准备应计提充分。</p>
        <p>3. 账项调整取自 F2-14 调整分录；审定合计回写 F2-1 审定表。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      v-if="allResponses"
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      :title="`审计目标：确认存货${blockLabel}期末余额的存在、完整与准确，验证账项调整依据充分并准确联动 F2-1 审定表。`"
    />

    <!-- 工具栏 -->
    <div v-if="allResponses" class="tab-toolbar">
      <div class="toolbar-left" />
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:F2-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ Array.isArray(rows) ? rows.length : 0 }} 类</el-tag>
      </div>
    </div>

    <el-table :data="tableData" size="small" border stripe style="width:100%;font-size:13px">
    <el-table-column prop="label" label="项目" min-width="160" fixed />
    <el-table-column label="索引" width="72" fixed>
      <template #default="{ row }">
        <GtIndexChip
          v-if="row.rowKey !== 'subtotal' && sheetCodeForRowKey(row.rowKey)"
          :value="sheetCodeForRowKey(row.rowKey)!"
          :context-project-id="projectId"
        />
      </template>
    </el-table-column>
    <el-table-column label="期初数" min-width="110" align="right">
      <template #default="{ row }">
        <el-input-number
          v-if="!readonly && row.rowKey !== 'subtotal'"
          :model-value="row.opening"
          size="small"
          :controls="false"
          @change="(v: number) => onUpdate(row.rowKey, 'opening', v)"
        />
        <span v-else>{{ fmt(row.opening) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="本期增加" min-width="110" align="right">
      <template #default="{ row }">
        <el-input-number
          v-if="!readonly && row.rowKey !== 'subtotal'"
          :model-value="row.increase"
          size="small"
          :controls="false"
          @change="(v: number) => onUpdate(row.rowKey, 'increase', v)"
        />
        <span v-else>{{ fmt(row.increase) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="本期减少" min-width="110" align="right">
      <template #default="{ row }">
        <el-input-number
          v-if="!readonly && row.rowKey !== 'subtotal'"
          :model-value="row.decrease"
          size="small"
          :controls="false"
          @change="(v: number) => onUpdate(row.rowKey, 'decrease', v)"
        />
        <span v-else>{{ fmt(row.decrease) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="期末未审" min-width="110" align="right">
      <template #default="{ row }">
        <el-tooltip content="公式：期初 + 增加 - 减少" placement="top">
          <span class="formula-cell">{{ fmt(row.endUnadjusted) }}</span>
        </el-tooltip>
      </template>
    </el-table-column>
    <el-table-column label="账项调整" min-width="110" align="right">
      <template #default="{ row }">
        <el-input-number
          v-if="!readonly && row.rowKey !== 'subtotal'"
          :model-value="row.adjustment"
          size="small"
          :controls="false"
          @change="(v: number) => onUpdate(row.rowKey, 'adjustment', v)"
        />
        <span v-else>{{ fmt(row.adjustment) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="期末审定" min-width="110" align="right">
      <template #default="{ row }">
        <el-tooltip content="公式：未审数 + 账项调整" placement="top">
          <span class="formula-cell">{{ fmt(row.endAudited) }}</span>
        </el-tooltip>
      </template>
    </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <el-card v-if="allResponses" shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="readonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述本区块审定过程、账项调整依据及与 F2-14/F2-1 的核对情况。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card v-if="allResponses" shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="readonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项，不可确认。"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import type { F2AdjudicationRow, F2BlockKey } from '../../composables/useF2Adjudication'
import type { ChecklistResponse } from '../../composables/useF2FormData'
import { sheetCodeForRowKey } from '../../composables/useF2CrossSheet'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  rows: F2AdjudicationRow[]
  subtotal: F2AdjudicationRow
  block: F2BlockKey
  projectId?: string
  readonly?: boolean
  wpId?: string
  allResponses?: Map<string, ChecklistResponse>
}>()

const emit = defineEmits<{
  (e: 'update', block: F2BlockKey, rowKey: string, field: string, value: number): void
}>()

const tableData = computed(() => [
  ...(Array.isArray(props.rows) ? props.rows : []),
  props.subtotal,
])

const blockLabel = computed(() => (props.block === 'impairment' ? '跌价准备' : '原值'))

function fmt(n: number) {
  return Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function onUpdate(rowKey: string, field: string, value: number) {
  emit('update', props.block, rowKey, field, value ?? 0)
}

// ─── 审计说明 / 审计结论（按区块 keyed，随 allResponses 提供时启用） ─────────────
const noteKey = computed(() => `F2-adjudication-${props.block}-audit-note`)
const conclusionKey = computed(() => `F2-adjudication-${props.block}-audit-conclusion`)
const auditNote = ref('')
const auditConclusion = ref('')

function persistAudit(key: string, val: string): void {
  if (!props.allResponses) return
  const item = { item_id: key, conclusion: null, remark: val }
  props.allResponses.set(key, item)
  window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
}

function saveAuditNote(val: string): void {
  if (props.readonly) return
  auditNote.value = val
  persistAudit(noteKey.value, val)
}

function saveAuditConclusion(val: string): void {
  if (props.readonly) return
  auditConclusion.value = val
  persistAudit(conclusionKey.value, val)
}

onMounted(() => {
  if (!props.allResponses) return
  const n = props.allResponses.get(noteKey.value)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(conclusionKey.value)
  if (c?.remark) auditConclusion.value = c.remark
})
</script>

<style scoped>
:deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
:deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.formula-cell { border-bottom: 1px dashed #c0c4cc; cursor: help; }
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
</style>
