<template>
  <div class="f5-major-adj">
    <div class="f5-ma-toolbar">
      <span class="f5-ma-title">F5-8 重大调整核查表</span>
      <div class="f5-ma-actions">
        <GtVoucherSamplingEngine :project-id="projectId" :account-codes="['6401']" dialog-mode :phase="'final'"
          @filled="handleSamplingFilled" />
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增行</el-button>
        <CycleImportExportDropdown v-if="ieCtx" :wp-id="wpId" :api-prefix="ieCtx.apiPrefix" :sheet="ieCtx.sheet"
          :disabled="isReadonly" @imported="$emit('imported')" />
        <el-button size="small" @click="openReview">💬 复核</el-button>
      </div>
    </div>

    <el-table :data="rows" size="small" border stripe :row-class-name="rowClass" max-height="480">
      <el-table-column prop="seq" label="序号" width="56" />
      <el-table-column label="调整日期" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.adjustmentDate" size="small" @change="persist" />
          <span v-else>{{ row.adjustmentDate }}</span>
        </template>
      </el-table-column>
      <el-table-column label="调整事项" min-width="150">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.adjustmentItem" size="small" @change="persist" />
          <span v-else>{{ row.adjustmentItem }}</span>
        </template>
      </el-table-column>
      <el-table-column label="调整金额" width="120" align="right">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model.number="row.adjustmentAmount" size="small" @change="persist" />
          <span v-else :class="{ 'is-warn': exceedsMateriality(row) }">{{ fmt(row.adjustmentAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="调整原因" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.adjustmentReason" size="small" @change="persist" />
          <span v-else>{{ row.adjustmentReason }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审批依据" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.approvalBasis" size="small" @change="persist" />
          <span v-else>{{ row.approvalBasis }}</span>
        </template>
      </el-table-column>
      <el-table-column label="凭证编号" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="persist" />
          <span v-else>{{ row.voucherNo }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审计评价" min-width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.auditEvaluation" size="small" @change="persist" />
          <span v-else>{{ row.auditEvaluation }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="56" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button link size="small" type="danger" @click="removeRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="f5-ma-summary">
      <span>调整笔数：<b>{{ rows.length }}</b></span>
      <span>调整总额：<b>{{ fmt(totalAmount) }}</b></span>
      <span>超重要性笔数：<b class="is-warn">{{ exceedCount }}</b></span>
    </div>

    <el-card class="f5-ma-note" shadow="never">
      <template #header>
        <div class="f5-card-header"><span>审计结论</span></div>
      </template>
      <el-input v-model="conclusion" type="textarea" autosize :disabled="isReadonly" placeholder="重大调整核查结论..." @change="saveConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/** F5TabMajorAdjustment — F5-8 重大调整核查表（8列 + >重要性橙色 + 抽凭引擎 + 导入导出） */
import { ref, computed, inject, watch, onBeforeUnmount, type Ref } from 'vue'
import { parseNum, calcSubtotal } from '../composables/useF5CosOfFormulaEngine'
import { resolveImportExportSheet, isImportExportSheet } from '../shared/cycleImportExportRegistry'
import CycleImportExportDropdown from '../shared/CycleImportExportDropdown.vue'
import GtVoucherSamplingEngine from '../voucher-sampling/GtVoucherSamplingEngine.vue'
import type { SampledVoucher, FillMode } from '../composables/useSamplingAlgorithms'
import type { ChecklistResponse } from '../composables/useF1FormData'

defineEmits<{ imported: [] }>()
const props = defineProps<{
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: string
  projectId: string
  isReadonly: boolean
  materiality?: number
  auditYear?: number
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const STORAGE_KEY = 'F5-8-rows'
const CONCLUSION_KEY = 'F5-8-conclusion'

interface MajorAdjRow {
  rowId: string; seq: number; adjustmentDate: string; adjustmentItem: string
  adjustmentAmount: number; adjustmentReason: string; approvalBasis: string
  voucherNo: string; auditEvaluation: string
}

function genId(): string { return `f5ma-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}` }
function emptyRow(seq: number): MajorAdjRow {
  return { rowId: genId(), seq, adjustmentDate: '', adjustmentItem: '', adjustmentAmount: 0, adjustmentReason: '', approvalBasis: '', voucherNo: '', auditEvaluation: '' }
}

let debounceTimer: ReturnType<typeof setTimeout> | null = null
const rows = ref<MajorAdjRow[]>([emptyRow(1)])
const conclusion = ref(props.allResponses.value.get(CONCLUSION_KEY)?.remark ?? '')

function loadRows(): void {
  const raw = props.allResponses.value.get(STORAGE_KEY)?.remark
  if (!raw) return
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed) && parsed.length) {
      rows.value = parsed.map((r: any, i: number) => ({
        ...emptyRow(i + 1),
        rowId: r.rowId || genId(),
        seq: r.seq ?? i + 1,
        adjustmentDate: r.adjustmentDate || '', adjustmentItem: r.adjustmentItem || '',
        adjustmentAmount: parseNum(r.adjustmentAmount), adjustmentReason: r.adjustmentReason || '',
        approvalBasis: r.approvalBasis || '', voucherNo: r.voucherNo || '', auditEvaluation: r.auditEvaluation || '',
      }))
    }
  } catch { /* ignore */ }
}

watch(() => props.allResponses.value.get(STORAGE_KEY)?.remark, () => {
  if (rows.value.length <= 1 && !rows.value[0]?.adjustmentItem) loadRows()
}, { immediate: true })

const totalAmount = computed(() => calcSubtotal(rows.value.map((r) => parseNum(r.adjustmentAmount))))
const exceedCount = computed(() => rows.value.filter(exceedsMateriality).length)
const ieCtx = computed(() => (isImportExportSheet('f5', 'F5-8') ? resolveImportExportSheet('f5', 'F5-8') : null))

function exceedsMateriality(row: MajorAdjRow): boolean {
  const m = props.materiality ?? 0
  if (m <= 0) return false
  return Math.abs(parseNum(row.adjustmentAmount)) > m
}

function addRow() {
  if (props.isReadonly) return
  rows.value.push(emptyRow(rows.value.length + 1))
  persist()
}
function removeRow(rowId: string) {
  if (props.isReadonly || rows.value.length <= 1) return
  const idx = rows.value.findIndex((r) => r.rowId === rowId)
  if (idx === -1) return
  rows.value.splice(idx, 1)
  rows.value.forEach((r, i) => { r.seq = i + 1 })
  persist()
}
function persist() {
  if (props.isReadonly) return
  props.allResponses.value.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: JSON.stringify(rows.value) })
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    debounceTimer = null
    const item = props.allResponses.value.get(STORAGE_KEY)
    if (item) window.dispatchEvent(new CustomEvent('f5:save-items', { detail: { items: [item] } }))
  }, 2000)
}
onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); persist() } })

/** 抽凭引擎填充：将样本凭证映射为重大调整行 */
function handleSamplingFilled(payload: { samples: SampledVoucher[]; fillMode?: FillMode }) {
  const samples = payload?.samples
  if (props.isReadonly || !Array.isArray(samples) || !samples.length) return
  const mapped: MajorAdjRow[] = samples.map((s: any, i: number) => ({
    ...emptyRow(rows.value.length + i + 1),
    adjustmentDate: s.voucher_date || s.date || '',
    adjustmentItem: s.summary || s.abstract || '重大成本调整',
    adjustmentAmount: parseNum(s.amount ?? s.debit_amount ?? s.credit_amount),
    voucherNo: s.voucher_no || s.voucherNo || '',
  }))
  // 若当前只有默认空行则替换，否则追加
  if (rows.value.length === 1 && !rows.value[0].adjustmentItem) {
    rows.value = mapped
  } else {
    rows.value.push(...mapped)
  }
  rows.value.forEach((r, i) => { r.seq = i + 1 })
  persist()
}

function saveConclusion() {
  props.allResponses.value.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: conclusion.value })
  window.dispatchEvent(new CustomEvent('f5:save-items', { detail: { items: [{ item_id: CONCLUSION_KEY, conclusion: null, remark: conclusion.value }] } }))
}

function rowClass({ row }: { row: any }): string { return exceedsMateriality(row) ? 'f5-row-orange' : '' }
function fmt(v: number | null | undefined): string { return v == null || v === 0 ? '-' : v.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) }
function openReview() { openReviewDialog('F5-8-conclusion') }
</script>

<style scoped>
.f5-major-adj { padding: 12px; font-size: 13px; }
.f5-ma-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.f5-ma-title { font-weight: 600; }
.f5-ma-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.f5-ma-summary { display: flex; gap: 20px; margin-top: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; }
.f5-ma-summary .is-warn { color: #e6a23c; }
.is-warn { color: #e6a23c; font-weight: 600; }
.f5-ma-note { margin-top: 12px; }
.f5-card-header { display: flex; align-items: center; justify-content: space-between; }
:deep(.f5-row-orange) { background: #fdf6ec; }
</style>
