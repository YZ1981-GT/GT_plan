<template>
  <div class="f5-major-adj">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表核查营业成本（科目6401）本期发生的重大调整事项，逐笔记录调整日期、事项、金额、原因及审批依据。</p>
        <p>2. 单笔调整金额超过重要性水平自动标橙（底部统计超重要性笔数），须重点关注授权审批与凭证支持。</p>
        <p>3. 可通过下方"自动抽凭"按方法选取 6401 重大成本调整凭证，样本自动填入核查行。</p>
        <p>4. 核查结论应说明重大调整的合理性、授权完整性及是否存在跨期或人为调节成本的迹象。</p>
      </div>
    </details>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增行</el-button>
        <CycleImportExportDropdown v-if="ieCtx" :wp-id="wpId" :api-prefix="ieCtx.apiPrefix" :sheet="ieCtx.sheet"
          :disabled="isReadonly" @imported="$emit('imported')" />
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:F5-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 抽凭引擎 -->
    <el-collapse v-if="wpId && projectId && !isReadonly" class="f5-sampling">
      <el-collapse-item title="⚡ 自动抽凭（科目 6401 营业成本，选取重大成本调整凭证）" name="sampling">
        <GtVoucherSamplingEngine
          account-code="6401"
          phase="final"
          default-method="monetary"
          :workpaper-id="wpId"
          :project-id="projectId"
          :year="auditYear"
          @filled="handleSamplingFilled"
        />
      </el-collapse-item>
    </el-collapse>

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

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计结论</span>
          <div class="opinion-actions">
            <el-button size="small" @click="openReview">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly"
        placeholder="重大调整核查结论（调整合理性、授权完整性、是否存在跨期或人为调节等）..." @change="saveConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/** F5TabMajorAdjustment — F5-8 重大调整核查表（8列 + >重要性橙色 + 抽凭引擎 + 导入导出） */
import { ref, computed, inject, toRef, watch, onBeforeUnmount, type Ref } from 'vue'
import { parseNum, calcSubtotal } from '../composables/useF5CosOfFormulaEngine'
import { resolveImportExportSheet, isImportExportSheet } from '../shared/cycleImportExportRegistry'
import CycleImportExportDropdown from '../shared/CycleImportExportDropdown.vue'
import GtVoucherSamplingEngine from '../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtIndexChip from '../GtIndexChip.vue'
import type { SampledVoucher } from '../composables/useSamplingAlgorithms'
import type { ChecklistResponse } from '../composables/useF1FormData'

defineEmits<{ imported: [] }>()
const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  materiality?: number
  auditYear?: number
}>()

// 父组件模板绑定会自动解包 computed → 子组件收到纯 Map；重新包成 ref 供内部逻辑使用
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const STORAGE_KEY = 'F5-8-rows'
const CONCLUSION_KEY = 'F5-8-conclusion'
const auditYear = computed(() => props.auditYear ?? new Date().getFullYear())

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
const conclusion = ref(allResponsesRef.value.get(CONCLUSION_KEY)?.remark ?? '')

function loadRows(): void {
  const raw = allResponsesRef.value.get(STORAGE_KEY)?.remark
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

watch(() => allResponsesRef.value.get(STORAGE_KEY)?.remark, () => {
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
  allResponsesRef.value.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: JSON.stringify(rows.value) })
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    debounceTimer = null
    const item = allResponsesRef.value.get(STORAGE_KEY)
    if (item) window.dispatchEvent(new CustomEvent('f5:save-items', { detail: { items: [item] } }))
  }, 2000)
}
onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); persist() } })

/** 抽凭引擎填充：将样本凭证映射为重大调整行 */
function handleSamplingFilled(samples: SampledVoucher[]) {
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
  allResponsesRef.value.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: conclusion.value })
  window.dispatchEvent(new CustomEvent('f5:save-items', { detail: { items: [{ item_id: CONCLUSION_KEY, conclusion: null, remark: conclusion.value }] } }))
}

function rowClass({ row }: { row: any }): string { return exceedsMateriality(row) ? 'f5-row-orange' : '' }
function fmt(v: number | null | undefined): string { return v == null || v === 0 ? '-' : v.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) }
function openReview() { openReviewDialog('F5-8-conclusion') }
</script>

<style scoped>
.f5-major-adj { padding: 12px; }
.f5-major-adj :deep(.el-table) { --el-table-font-size: 13px; font-size: 13px; }
.f5-major-adj :deep(.el-table .cell) { font-size: 13px !important; }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }

/* 工具栏 */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

/* 抽凭引擎 */
.f5-sampling { margin-bottom: 12px; }

/* 汇总 */
.f5-ma-summary { display: flex; gap: 20px; margin-top: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; }
.f5-ma-summary .is-warn { color: #e6a23c; }
.is-warn { color: #e6a23c; font-weight: 600; }

/* 审计意见卡片 */
.opinion-card { margin-top: 12px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-actions { display: flex; gap: 6px; }
:deep(.f5-row-orange) { background: #fdf6ec; }
</style>
