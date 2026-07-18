<template>
  <div class="g1-sec-count">
    <div class="section-head">
      <h3 class="sheet-title">G1-11 有价证券监盘表</h3>
      <div class="head-actions tab-toolbar">
        <G1ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G1-11"
          :disabled="isReadonly"
          @imported="emit('imported')"
        />
        <el-button size="small" type="primary" :disabled="isReadonly" @click="sc.addRow()">新增监盘行</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-12" /></span>
        <el-tag size="small" type="info">共 {{ sc.rows.value.length }} 行</el-tag>
        <el-button size="small" @click="openReviewDialog('G1-11-conclusion')">💬复核</el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：通过实地监盘或托管对账核实有价证券的存在性与数量准确性，识别盘点差异并查明原因，为证券结存及倒轧（G1-12）提供依据。"
      class="objective-alert"
    />

    <div class="stats-bar">
      监盘证券：<b>{{ sc.rows.value.length }}</b> 项 ·
      差异项：<b :class="{ warn: sc.diffCount.value > 0 }">{{ sc.diffCount.value }}</b>
    </div>

    <el-table :data="sc.rows.value" border size="small" max-height="500"
      :row-class-name="rowClass">
      <el-table-column
        v-for="col in sc.columns"
        :key="String(col.prop)"
        :label="col.label"
        :width="col.width"
        :align="col.type === 'number' ? 'right' : 'left'"
        :class-name="col.formula ? 'auto-calc-col' : ''"
        :fixed="col.prop === 'securityName' ? 'left' : undefined"
      >
        <template #default="{ row, $index }">
          <span v-if="col.prop === 'seq'">{{ $index + 1 }}</span>
          <span v-else-if="col.formula" class="formula-cell"
            :class="{ 'diff-warn': sc.isDiffAbnormal(row) }" :title="'盘点差异 = 盘点数量 - 账面数量'">
            {{ fmtNum(row[col.prop]) }}
          </span>
          <el-input-number
            v-else-if="col.type === 'number'"
            v-model="row[col.prop]"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            @change="sc.updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
          <el-input
            v-else
            v-model="row[col.prop]"
            size="small"
            :disabled="isReadonly"
            @change="sc.updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="sc.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>


    <G1AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      :conclusion="sc.auditConclusion.value"
      @update:conclusion="(v: string) => { sc.auditConclusion.value = v }"
      note-ai-section="counting-note"
      conclusion-ai-section="counting-conclusion"
      note-placeholder="填写审计说明：（1）监盘或托管对账的执行情况；（2）盘点差异的识别及原因查明结果。"
      note-hint="覆盖监盘范围、差异识别与存在性结论依据。"
    />


    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>盘点差异 = 盘点数量 - 账面数量，差异不为 0 时橙色高亮，需说明差异原因。</li>
        <li>实物证券应实地监盘，电子证券应取得托管机构对账单核对。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import {ref, toRef, inject, watch , computed} from 'vue'
import { useG1SecuritiesCount, type G1SecuritiesCountRow } from '../../composables/useG1SecuritiesCount'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import G1AuditTextCards from '../G1AuditTextCards.vue'
import G1ImportExportDropdown from '../G1ImportExportDropdown.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId?: string
}>()

const wpId = computed(() => props.wpId ?? '')

const emit = defineEmits<{ imported: [] }>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const sc = useG1SecuritiesCount({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const AUDIT_NOTE_KEY = 'G1-11-audit-note'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})

function rowClass({ row }: { row: G1SecuritiesCountRow }): string {
  return sc.isDiffAbnormal(row) ? 'diff-row' : ''
}

function fmtNum(v: unknown): string {
  return typeof v === 'number' ? v.toLocaleString() : String(v ?? '')
}
</script>

<style scoped>
.g1-sec-count { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g1-sec-count :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.g1-sec-count :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.sheet-title { margin: 0; font-size: 16px; font-weight: 600; color: #1f2a37; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert { margin-bottom: 12px; }
.stats-bar { margin-bottom: 10px; padding: 8px 12px; background: #f8f9fb; border: 1px solid #ebeef5; border-radius: 6px; font-size: 12px; color: #606266; }
.stats-bar { margin-bottom: 10px; font-size: 12px; color: #606266; }
.stats-bar .warn { color: #e6a23c; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa; }
.diff-warn { color: #e6a23c; font-weight: 600; }
.conclusion-card { margin-top: 12px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
:deep(.diff-row) { background: #fdf6ec; }
</style>
