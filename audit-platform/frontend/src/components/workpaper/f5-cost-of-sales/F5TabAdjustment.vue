<template>
  <div class="f5-adjustment">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 调整分录用于记录审计发现的营业成本（科目6401）错报，每笔分录借贷必须平衡。</p>
        <p>2. 分录类型区分 AJE(账项调整) 与 RJE(重分类)，需填写摘要、科目、编制人及审批依据。</p>
        <p>3. 借贷不平衡时底部红色警告，保存前必须修正差额。</p>
        <p>4. 调整结果同步至 F5-1 审定表"账项调整/重分类"列参与审定计算。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实营业成本（科目6401）审计调整分录的完整、准确与借贷平衡，确保审计调整恰当反映于 F5-1 审定表。"
      class="objective-alert"
    />

    <el-alert v-if="!isBalanced" type="error" :closable="false" style="margin-bottom:8px">
      ⚠️ 借贷不平衡：借方合计 {{ fmt(totalDebit) }} ≠ 贷方合计 {{ fmt(totalCredit) }}，差额 {{ fmt(Math.abs(totalDebit - totalCredit)) }}
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增行</el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="centralSyncing"
          :disabled="isReadonly || !isBalanced || rows.length === 0"
          @click="syncToCentral"
          title="把本页调整分录汇聚到集中调整登记，供合伙人跨循环审阅"
        >同步到集中登记</el-button>
        <el-tag
          v-if="centralStatus?.review_status"
          size="small"
          :type="centralStatus.review_status === 'approved' ? 'success' : (centralStatus.review_status === 'rejected' ? 'danger' : 'info')"
          :title="centralStatus.rejection_reason || ''"
        >集中登记：{{ CENTRAL_STATUS_LABELS[centralStatus.review_status] || centralStatus.review_status }}</el-tag>
        <CycleImportExportDropdown v-if="ieCtx" :wp-id="wpId" :api-prefix="ieCtx.apiPrefix" :sheet="ieCtx.sheet"
          :disabled="isReadonly" @imported="$emit('imported')" />
      </div>
      <div class="toolbar-right">
        <el-button v-if="openReviewDialog" size="small" @click="openReview">复核</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:F5-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <F5SheetAttachments
      v-if="projectId"
      :project-id="projectId"
      :wp-id="wpId"
      sheet-code="F5-4"
      label="调整分录附件"
    />

    <el-table :data="rows" border size="small" style="width:100%;font-size:13px" max-height="480">
      <el-table-column prop="seq" label="序号" width="56" />
      <el-table-column label="分录类型" width="100">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.entryType" size="small" @change="() => persist()">
            <el-option value="AJE" label="AJE" />
            <el-option value="RJE" label="RJE" />
          </el-select>
          <span v-else>{{ row.entryType }}</span>
        </template>
      </el-table-column>
      <el-table-column label="日期" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.date" size="small" @change="persist" />
          <span v-else>{{ row.date }}</span>
        </template>
      </el-table-column>
      <el-table-column label="摘要" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.summary" size="small" @change="persist" />
          <span v-else>{{ row.summary }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目代码" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.accountCode" size="small" @change="persist" />
          <span v-else>{{ row.accountCode }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目名称" min-width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.accountName" size="small" @change="persist" />
          <span v-else>{{ row.accountName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model.number="row.debitAmount" size="small" @change="persist" />
          <span v-else>{{ fmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model.number="row.creditAmount" size="small" @change="persist" />
          <span v-else>{{ fmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="编制人" width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.preparer" size="small" @change="persist" />
          <span v-else>{{ row.preparer }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="persist" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="56" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button link size="small" type="danger" @click="removeRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="f5-adj-subtotal" :class="{ 'balance-fail': !isBalanced }">
      借方合计：{{ fmt(totalDebit) }} ｜ 贷方合计：{{ fmt(totalCredit) }}
      <span v-if="isBalanced" class="ok">✓ 平衡</span>
      <span v-else class="err">✗ 不平衡</span>
    </div>

    <!-- 审计说明 -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明</span>
          <el-button
            v-if="!isReadonly && aiAvailable"
            size="small"
            type="primary"
            plain
            :loading="aiLoading"
            @click="runAdjAi('adjustment-entry-note')"
          >AI 填写说明</el-button>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5, maxRows: 8 }" :disabled="isReadonly"
        placeholder="营业成本调整分录审计说明（调整事项、依据、对审定营业成本的影响等）..." @change="saveNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计结论</span>
          <el-button
            v-if="!isReadonly && aiAvailable"
            size="small"
            type="primary"
            plain
            :loading="aiLoading"
            @click="runAdjAi('adjustment-entry-conclusion')"
          >AI 填写结论</el-button>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }" :disabled="isReadonly"
        placeholder="调整分录审计结论..." @change="saveConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/** F5TabAdjustment — F5-4 调整分录（借贷平衡校验 + 动态行 + 导入导出） */
import { ref, computed, inject, toRef, watch, onBeforeUnmount, type Ref } from 'vue'
import { parseNum, calcSubtotal, isDebitCreditBalanced } from '../composables/useF5CosOfFormulaEngine'
import { useF5AiGenerate } from '../composables/useF5AiGenerate'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '../composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'
import { resolveImportExportSheet, isImportExportSheet } from '../shared/cycleImportExportRegistry'
import CycleImportExportDropdown from '../shared/CycleImportExportDropdown.vue'
import F5SheetAttachments from './F5SheetAttachments.vue'
import GtIndexChip from '../GtIndexChip.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

defineEmits<{ imported: [] }>()
const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  isReadonly: boolean
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>
const wpIdRef = toRef(props, 'wpId') as Ref<string>

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF5AiGenerate(wpIdRef)
const STORAGE_KEY = 'F5-4-rows'
const NOTE_KEY = 'F5-4-audit-note'
const CONCLUSION_KEY = 'F5-4-audit-conclusion'

const auditNote = ref(allResponsesRef.value.get(NOTE_KEY)?.remark ?? '')
const auditConclusion = ref(allResponsesRef.value.get(CONCLUSION_KEY)?.remark ?? '')

function saveNote() {
  allResponsesRef.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: auditNote.value })
  window.dispatchEvent(new CustomEvent('f5:save-items', { detail: { items: [{ item_id: NOTE_KEY, conclusion: null, remark: auditNote.value }] } }))
}
function saveConclusion() {
  allResponsesRef.value.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: auditConclusion.value })
  window.dispatchEvent(new CustomEvent('f5:save-items', { detail: { items: [{ item_id: CONCLUSION_KEY, conclusion: null, remark: auditConclusion.value }] } }))
}

async function runAdjAi(section: 'adjustment-entry-note' | 'adjustment-entry-conclusion'): Promise<void> {
  if (props.isReadonly) return
  const isNote = section === 'adjustment-entry-note'
  const text = await generateAndConfirm(
    section,
    isNote ? auditNote.value : auditConclusion.value,
    {
      sheet: 'F5-4',
      rowCount: rows.value.length,
      debitTotal: totalDebit.value,
      creditTotal: totalCredit.value,
      isBalanced: isBalanced.value,
    },
    isNote ? 'AI · 审计说明' : 'AI · 审计结论',
  )
  if (!text) return
  if (isNote) {
    auditNote.value = text
    saveNote()
  } else {
    auditConclusion.value = text
    saveConclusion()
  }
}

interface AdjRow {
  rowId: string; seq: number; entryType: string; date: string; summary: string
  accountCode: string; accountName: string; debitAmount: number; creditAmount: number
  preparer: string; remark: string
}

function genId(): string { return `f5adj-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}` }
function emptyRow(seq: number): AdjRow {
  return { rowId: genId(), seq, entryType: 'AJE', date: '', summary: '', accountCode: '', accountName: '', debitAmount: 0, creditAmount: 0, preparer: '', remark: '' }
}

let debounceTimer: ReturnType<typeof setTimeout> | null = null
const rows = ref<AdjRow[]>([emptyRow(1)])

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
        entryType: r.entryType || 'AJE',
        date: r.date || '', summary: r.summary || '',
        accountCode: r.accountCode || '', accountName: r.accountName || '',
        debitAmount: parseNum(r.debitAmount), creditAmount: parseNum(r.creditAmount),
        preparer: r.preparer || '', remark: r.remark || '',
      }))
    }
  } catch { /* ignore */ }
}

watch(() => allResponsesRef.value.get(STORAGE_KEY)?.remark, () => {
  if (rows.value.length <= 1 && !rows.value[0]?.accountCode) loadRows()
}, { immediate: true })

const totalDebit = computed(() => calcSubtotal(rows.value.map((r) => parseNum(r.debitAmount))))
const totalCredit = computed(() => calcSubtotal(rows.value.map((r) => parseNum(r.creditAmount))))
const isBalanced = computed(() => isDebitCreditBalanced(rows.value.map((r) => parseNum(r.debitAmount)), rows.value.map((r) => parseNum(r.creditAmount))))

// ─── 同步到集中调整登记 ─────────────────────────────────────────────
const { year: centralYear } = useAuditContext()
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId: () => props.projectId || '',
  year: centralYear,
  wpId: () => props.wpId,
  wpCode: 'F5',
  itemId: STORAGE_KEY,
  buildLineItems: () => rows.value.map((r) => ({
    standard_account_code: r.accountCode || undefined,
    account_name: r.accountName || undefined,
    debit_amount: parseNum(r.debitAmount),
    credit_amount: parseNum(r.creditAmount),
  })),
  buildMeta: () => ({
    description: rows.value.find((r) => r.summary)?.summary || 'F5 营业成本调整',
    adjustmentType: rows.value.length > 0 && rows.value.every((r) => r.entryType === 'RJE') ? 'rje' : 'aje',
  }),
})
refreshStatus()

const ieCtx = computed(() => (isImportExportSheet('f5', 'F5-4') ? resolveImportExportSheet('f5', 'F5-4') : null))

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

function fmt(v: number | null | undefined): string { return v == null || v === 0 ? '-' : v.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) }
function openReview() { openReviewDialog?.('F5-4-adjustment') }
</script>

<style scoped>
.f5-adjustment { padding: 12px; }
.f5-adjustment :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f5-adjustment :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

/* 工具栏 */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

/* 审计意见卡片 */
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }

/* 借贷平衡合计 */
.f5-adj-subtotal { margin-top: 8px; padding: 8px 12px; background: #f0f9eb; border-radius: 4px; font-weight: 600; }
.f5-adj-subtotal.balance-fail { background: #fef0f0; }
.ok { color: #67c23a; margin-left: 12px; }
.err { color: #f56c6c; margin-left: 12px; }
</style>
