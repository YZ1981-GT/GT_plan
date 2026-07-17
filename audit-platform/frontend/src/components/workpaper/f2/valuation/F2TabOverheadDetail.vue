<template>
  <div class="f2-val-sheet f2-overhead">
    <header class="sheet-header">
      <div><h3>制造费用明细表</h3><span class="code">F2-43</span></div>
      <div class="stat-row">
        <span class="stat">年度合计 {{ fmt(oh.annualTotal.value) }}</span>
        <el-tag v-if="oh.highVarianceCount.value" type="warning" size="small">
          变动超20% {{ oh.highVarianceCount.value }} 项
        </el-tag>
      </div>
    </header>

    <div class="section-label">一、审计目标</div>
    <ol class="objectives">
      <li v-for="(obj, i) in objectives" :key="i">{{ obj }}</li>
    </ol>

    <div class="section-label">二、审计程序</div>
    <el-input
      :model-value="oh.auditProcedure.value"
      type="textarea"
      :autosize="{ minRows: 2, maxRows: 4 }"
      :disabled="isReadonly"
      class="section-text"
      :placeholder="defaultProcedure"
      @update:model-value="(v: string) => oh.setProcedure(v)"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left" />
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-val"
          sheet="F2-43"
          :disabled="isReadonly"
          ai-section="cost-analysis"
          :existing-content="oh.auditNote.value"
          review-section="F2-43-conclusion"
          @ai-filled="(t: string) => { oh.auditNote.value = t }"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F2-43" /></span>
      </div>
    </div>

    <div class="table-scroll">
      <table class="matrix-table">
        <thead>
          <tr>
            <th rowspan="2" class="col-item">项目</th>
            <th colspan="12">月份</th>
            <th rowspan="2" class="col-total">合计</th>
            <th rowspan="2" class="col-prior">上年度</th>
            <th rowspan="2" class="col-rate">变动率</th>
            <th rowspan="2" class="col-reason">变动原因</th>
          </tr>
          <tr>
            <th v-for="m in monthLabels" :key="m.key">{{ m.label }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in oh.enriched.value.rows"
            :key="row.key"
            :class="{
              'row-total': row.kind === 'total',
              'row-warn': row.kind === 'item' && isHighVariance(row),
            }"
          >
            <td class="col-item" :class="{ indent: row.key === 'other' }">{{ row.label }}</td>
            <td v-for="mk in monthKeys" :key="mk">
              <el-input-number
                v-if="row.kind === 'item' && !isReadonly"
                :model-value="row.months[mk]"
                size="small"
                :controls="false"
                class="compact-num"
                @change="(v: number | undefined) => oh.updateMonth(row.key as OverheadItemKey, mk, v ?? 0)"
              />
              <span v-else class="auto">{{ fmt(row.months[mk]) }}</span>
            </td>
            <td class="auto col-total">{{ fmt(row.total) }}</td>
            <td>
              <el-input-number
                v-if="row.kind === 'item' && !isReadonly"
                :model-value="row.priorYear"
                size="small"
                :controls="false"
                class="compact-num"
                @change="(v: number | undefined) => oh.updateRowMeta(row.key as OverheadItemKey, { priorYear: v ?? 0 })"
              />
              <span v-else class="auto">{{ fmt(row.priorYear) }}</span>
            </td>
            <td class="auto col-rate" :class="{ 'var-warn': isHighVariance(row) }">
              {{ fmtRate(row.changeRate) }}
            </td>
            <td>
              <el-input
                v-if="row.kind === 'item' && !isReadonly"
                :model-value="row.changeReason"
                size="small"
                @update:model-value="(v: string) => oh.updateRowMeta(row.key as OverheadItemKey, { changeReason: v })"
              />
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <el-card shadow="never" class="conclusion-card">
      <template #header><span class="conclusion-header">三、审计说明</span></template>
      <el-input
        v-model="oh.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="制造费用明细审计说明..."
      />
    </el-card>

    <el-card shadow="never" class="conclusion-card">
      <template #header><span class="conclusion-header">四、审计结论</span></template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="填写审计结论。"
        @update:model-value="saveAuditConclusion"
      />
    </el-card>

    <div class="tips-box">
      <div class="tips-title">提示</div>
      <ol>
        <li v-for="(tip, i) in tips" :key="i">{{ tip }}</li>
      </ol>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, toRef } from 'vue'
import { useF2OverheadDetail } from '../../composables/useF2OverheadDetail'
import {
  OVERHEAD_MONTH_KEYS,
  OVERHEAD_MONTH_LABELS,
  F2_43_OBJECTIVES,
  F2_43_PROCEDURE,
  F2_43_TIPS,
  type OverheadItemKey,
  type OverheadMatrixRow,
} from '../../composables/useF2OverheadMatrixFormulas'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const oh = useF2OverheadDetail({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const objectives = F2_43_OBJECTIVES
const tips = F2_43_TIPS
const defaultProcedure = F2_43_PROCEDURE
const monthKeys = OVERHEAD_MONTH_KEYS
const monthLabels = OVERHEAD_MONTH_LABELS

const CONCLUSION_KEY = 'F2-43-audit-conclusion'
const auditConclusion = ref('')
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY, item)
  window.dispatchEvent(new CustomEvent('f2-val:save-items', { detail: { items: [item] } }))
}
onMounted(() => {
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

function isHighVariance(row: OverheadMatrixRow): boolean {
  return row.kind === 'item' && typeof row.changeRate === 'number' && Math.abs(row.changeRate) > 0.2
}

function fmt(v: number): string {
  if (v === 0 || !Number.isFinite(v)) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(r: number | '' | 'N/A'): string {
  if (r === '' || r === 'N/A') return '—'
  return `${(r * 100).toFixed(2)}%`
}
</script>

<style scoped src="./f2ValSheetStyles.css"></style>
<style scoped>
.f2-overhead { --gt-purple: #4b2d77; --gt-purple-soft: #f3eef8; }
.section-label { margin: 14px 0 8px; font-size: 14px; font-weight: 600; color: #303133; }
.section-text { margin-bottom: 10px; }
.objectives { margin: 0 0 12px; padding-left: 1.4em; font-size: 13px; line-height: 1.7; color: #606266; }

.table-scroll { overflow-x: auto; margin-bottom: 12px; }
.matrix-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  min-width: 1280px;
}
.matrix-table th,
.matrix-table td {
  border: 1px solid #d4c8e0;
  padding: 2px 3px;
  text-align: center;
  vertical-align: middle;
}
.matrix-table thead th {
  background: var(--gt-purple-soft);
  color: #3d2a55;
  font-weight: 600;
}
.col-item { width: 110px; text-align: left !important; padding-left: 8px !important; background: #faf8fc; }
.col-total { background: #f0ebf5 !important; min-width: 80px; }
.col-prior { min-width: 80px; }
.col-rate { min-width: 64px; }
.col-reason { min-width: 100px; }
.row-total td { background: #f0ebf5; font-weight: 600; }
.row-warn td { background: #fdf6ec; }
.auto { display: block; text-align: right; padding-right: 4px; white-space: nowrap; color: #606266; }
.var-warn { color: #f56c6c !important; font-weight: 600; }

.conclusion-card { margin-top: 14px; }
.conclusion-header { font-weight: 600; font-size: 14px; }
.tips-box {
  margin-top: 16px;
  padding: 12px 16px;
  background: #ecf5ff;
  border-left: 3px solid #409eff;
  border-radius: 4px;
  font-size: 13px;
  line-height: 1.7;
}
.tips-title { font-weight: 600; color: #409eff; margin-bottom: 6px; }
.tips-box ol { margin: 0; padding-left: 1.4em; }

:deep(.compact-num) { width: 68px; }
:deep(.compact-num .el-input__inner) { text-align: right; padding: 0 3px; font-size: 11px; }
</style>
