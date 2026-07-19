<template>
  <div class="g1-count-recon" data-testid="g1-count-recon">
    <div class="section-head">
      <div class="title-block">
        <h3 class="sheet-title">G1-12 有价证券盘点倒轧表</h3>
        <p class="sheet-sub">将盘点日实存倒轧至资产负债表日，与账面结存核对</p>
      </div>
      <div class="head-actions tab-toolbar">
        <G1ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G1-12"
          :disabled="isReadonly"
          @imported="emit('imported')"
        />
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="recon.syncFromSecuritiesCount(false)">
          从监盘取数
        </el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="recon.addRow()">新增倒轧行</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-11" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-4" /></span>
        <el-tag size="small" type="info">共 {{ recon.rows.value.length }} 行</el-tag>
        <el-button size="small" @click="openReviewDialog('G1-12-conclusion')">💬复核</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：通过盘点日实存倒轧至资产负债表日，确认报表日证券结存与账面结存一致，差异已查明并说明。"
    />

    <details class="procedure-block">
      <summary>编制思路与程序（展开）</summary>
      <ol>
        <li>自 G1-11 带入盘点日实存（数量、面值、票面利率、到期日）及账面数量。</li>
        <li>登记「资产负债表日 → 盘点日」期间增减（购入/处置等），取得交割单、对账单等证据。</li>
        <li>
          推算报表日实存：
          <b>报表日 = 盘点日 − 增加 + 减少</b>
          （增减口径为资产负债表日至盘点日）。
        </li>
        <li>与账面结存（数量/面值/总计）勾稽；差异查明原因，必要时调整并交叉 G1-4 / G1-3。</li>
      </ol>
    </details>

    <div class="stats-bar">
      倒轧证券 <b>{{ recon.stats.value.total }}</b> 项 ·
      差异项 <b :class="{ warn: recon.stats.value.withDiff > 0 }">{{ recon.stats.value.withDiff }}</b> ·
      债务 {{ recon.stats.value.debt }} · 权益 {{ recon.stats.value.equity }} ·
      衍生 {{ recon.stats.value.derivative }} · 其他 {{ recon.stats.value.other }}
      <span class="total">
        报表日总计 {{ fmtNum(recon.grandTotal.value.reportTotal) }} ·
        账面总计 {{ fmtNum(recon.grandTotal.value.bookTotal) }} ·
        差异 {{ fmtNum(recon.grandTotal.value.diffAmount) }}
      </span>
    </div>

    <el-alert
      v-if="recon.stats.value.withDiff > 0"
      type="warning"
      :closable="false"
      class="missing-alert"
      :title="`有 ${recon.stats.value.withDiff} 项倒轧差异≠0，请在「报表日实存+差异」区段填写备注并追查原因。`"
    />

    <el-segmented v-model="segment" :options="segmentOptions" size="small" class="segment-bar" />

    <el-table
      :data="recon.rows.value"
      border
      size="small"
      max-height="520"
      :row-class-name="rowClass"
    >
      <el-table-column
        v-for="col in currentColumns"
        :key="String(col.prop)"
        :label="col.label"
        :width="col.width"
        :min-width="col.prop === 'securityName' || col.prop === 'remark' ? 120 : undefined"
        :align="col.type === 'number' ? 'right' : 'left'"
        :class-name="col.formula ? 'auto-calc-col' : ''"
        :fixed="col.prop === 'securityName' || col.prop === 'seq' ? 'left' : undefined"
      >
        <template #default="{ row, $index }">
          <span v-if="col.prop === 'seq'">{{ $index + 1 }}</span>
          <span
            v-else-if="col.formula"
            class="formula-cell"
            :class="{ 'diff-warn': isDiffCol(col.prop) && recon.isDiffAbnormal(row) }"
            :title="formulaHint(col.prop)"
          >
            {{ fmtNum(row[col.prop]) }}
          </span>
          <el-select
            v-else-if="col.prop === 'category'"
            :model-value="row.category"
            size="small"
            clearable
            placeholder="分类"
            :disabled="isReadonly"
            style="width: 100%"
            @change="(v: string) => recon.updateRow(row.id, { category: (v || '') as any })"
          >
            <el-option
              v-for="opt in categoryOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
          <el-date-picker
            v-else-if="col.type === 'date'"
            :model-value="row[col.prop] || ''"
            type="date"
            value-format="YYYY-MM-DD"
            size="small"
            style="width: 100%"
            :disabled="isReadonly"
            @change="(v: string) => recon.updateRow(row.id, { [col.prop]: v || '' })"
          />
          <el-input-number
            v-else-if="col.type === 'number'"
            :model-value="row[col.prop] as number"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            @change="(v: number | undefined) => recon.updateRow(row.id, { [col.prop]: v ?? 0 })"
          />
          <el-input
            v-else
            :model-value="String(row[col.prop] ?? '')"
            size="small"
            :disabled="isReadonly || (segment !== 'countDate' && col.prop === 'securityName')"
            @change="(v: string) => recon.updateRow(row.id, { [col.prop]: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="56" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="recon.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals">
      <div class="grand-total">
        <span class="subtotal-label">合计</span>
        盘点日总计 {{ fmtNum(recon.grandTotal.value.countTotal) }} ·
        报表日总计 {{ fmtNum(recon.grandTotal.value.reportTotal) }} ·
        账面总计 {{ fmtNum(recon.grandTotal.value.bookTotal) }} ·
        差异 {{ fmtNum(recon.grandTotal.value.diffAmount) }}
      </div>
    </div>

    <G1AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      :conclusion="recon.auditConclusion.value"
      @update:conclusion="(v: string) => { recon.auditConclusion.value = v }"
      note-ai-section="recon-note"
      conclusion-ai-section="recon-conclusion"
      note-title="审计说明"
      conclusion-title="审计结论"
      note-placeholder="填写：（1）盘点日与报表日是否一致；（2）资产负债表日至盘点日增减核对；（3）倒轧与账面勾稽及差异处理。"
      note-hint="覆盖倒轧推算、增减变动证据与账面勾稽。"
      conclusion-placeholder="A、倒轧相符，未见异常。B、除上述应调整事项外，其余未见异常。C、因重大未调整差异或范围受限，不可确认。"
      :related-context="{
        行数: recon.stats.value.total,
        差异项: recon.stats.value.withDiff,
        报表日总计: recon.grandTotal.value.reportTotal,
        账面总计: recon.grandTotal.value.bookTotal,
      }"
    />

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>本表对齐 Excel G1-12：盘点日实存 − 报表日至盘点日增加 + 减少 = 报表日实存，再与账面结存比差。</li>
        <li>增减口径是「资产负债表日 → 盘点日」（盘点通常在期后）；勿与「盘点日 → 报表日」方向混淆。</li>
        <li>三区段切换时行同步；优先「从监盘取数」从 G1-11 带入盘点日与账面数量。</li>
        <li>分类（债务/权益/衍生/其他）便于与附注及 G1-1 勾稽；差异≠0 须填备注。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, computed, inject, watch } from 'vue'
import {
  useG1CountReconciliation,
  G1_SECURITY_CATEGORY_OPTIONS,
  type G1ReconciliationRow,
} from '../../composables/useG1CountReconciliation'
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

const recon = useG1CountReconciliation({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const AUDIT_NOTE_KEY = 'G1-12-audit-note'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})
watch(
  () => props.allResponses.get(AUDIT_NOTE_KEY)?.remark,
  (v) => { if (v != null && !auditNote.value) auditNote.value = v },
)

const segment = ref<'countDate' | 'changes' | 'reportDate'>('countDate')
const segmentOptions = [
  { label: '盘点日实存', value: 'countDate' },
  { label: '增减变动', value: 'changes' },
  { label: '报表日实存+差异', value: 'reportDate' },
]
const categoryOptions = G1_SECURITY_CATEGORY_OPTIONS

const currentColumns = computed(() => {
  if (segment.value === 'changes') return recon.changesColumns
  if (segment.value === 'reportDate') return recon.calcColumns
  return recon.countDayColumns
})

const FORMULA_HINTS: Partial<Record<keyof G1ReconciliationRow, string>> = {
  countTotal: '总计 = 面值 × 数量',
  reportQuantity: '报表日数量 = 盘点日数量 − 增加 + 减少',
  reportTotal: '报表日总计 = 报表日面值 × 报表日数量',
  diffQuantity: '差异·数量 = 报表日数量 − 账面数量',
  diffAmount: '差异·金额 = 报表日总计 − 账面总计',
}

function formulaHint(prop: keyof G1ReconciliationRow): string {
  return FORMULA_HINTS[prop] ?? ''
}

function isDiffCol(prop: keyof G1ReconciliationRow): boolean {
  return prop === 'diffQuantity' || prop === 'diffAmount'
}

function rowClass({ row }: { row: G1ReconciliationRow }): string {
  return recon.isDiffAbnormal(row) ? 'diff-row' : ''
}

function fmtNum(v: unknown): string {
  if (typeof v !== 'number' || !Number.isFinite(v)) return String(v ?? '')
  return v.toLocaleString(undefined, { maximumFractionDigits: 4 })
}
</script>

<style scoped>
.g1-count-recon { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g1-count-recon :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.g1-count-recon :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.title-block { min-width: 200px; }
.sheet-title { margin: 0; font-size: 16px; font-weight: 600; color: #1f2a37; }
.sheet-sub { margin: 4px 0 0; font-size: 12px; color: #909399; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert { margin-bottom: 10px; }
.procedure-block { margin-bottom: 12px; padding: 8px 12px; background: #f8f9fb; border: 1px solid #ebeef5; border-radius: 6px; font-size: 12px; color: #606266; }
.procedure-block summary { cursor: pointer; font-weight: 600; color: #303133; }
.procedure-block ol { margin: 8px 0 0; padding-left: 18px; }
.stats-bar { margin-bottom: 10px; padding: 8px 12px; background: #f8f9fb; border: 1px solid #ebeef5; border-radius: 6px; font-size: 12px; color: #606266; }
.stats-bar .warn { color: #e6a23c; }
.stats-bar .total { margin-left: 8px; color: #303133; }
.missing-alert { margin-bottom: 10px; }
.segment-bar { margin-bottom: 12px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa; }
.diff-warn { color: #e6a23c; font-weight: 600; }
.totals { margin-top: 12px; font-size: 12px; color: #606266; }
.subtotal-label { font-weight: 600; margin-right: 8px; }
.grand-total { margin-top: 6px; padding-top: 6px; border-top: 1px solid #dcdfe6; font-weight: 600; color: #303133; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
:deep(.diff-row) { background: #fdf6ec; }
</style>
