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

    <el-alert v-if="!isBalanced" type="error" :closable="false" style="margin-bottom:8px">
      ⚠️ 借贷不平衡：借方合计 {{ fmt(totalDebit) }} ≠ 贷方合计 {{ fmt(totalCredit) }}，差额 {{ fmt(Math.abs(totalDebit - totalCredit)) }}
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增行</el-button>
        <CycleImportExportDropdown v-if="ieCtx" :wp-id="wpId" :api-prefix="ieCtx.apiPrefix" :sheet="ieCtx.sheet"
          :disabled="isReadonly" @imported="$emit('imported')" />
      </div>
      <div class="toolbar-right">
        <el-button size="small" @click="openReview">💬 复核</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:F5-1" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

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
  </div>
</template>

<script setup lang="ts">
/** F5TabAdjustment — F5-4 调整分录（借贷平衡校验 + 动态行 + 导入导出） */
import { ref, computed, inject, toRef, watch, onBeforeUnmount, type Ref } from 'vue'
import { parseNum, calcSubtotal, isDebitCreditBalanced } from '../composables/useF5CosOfFormulaEngine'
import { resolveImportExportSheet, isImportExportSheet } from '../shared/cycleImportExportRegistry'
import CycleImportExportDropdown from '../shared/CycleImportExportDropdown.vue'
import GtIndexChip from '../GtIndexChip.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

defineEmits<{ imported: [] }>()
const props = defineProps<{ allResponses: Map<string, ChecklistResponse>; wpId: string; isReadonly: boolean }>()

// 父组件模板绑定会自动解包 computed → 子组件收到纯 Map；重新包成 ref 供内部逻辑使用
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const STORAGE_KEY = 'F5-4-rows'

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
function openReview() { openReviewDialog('F5-4-adjustment') }
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

/* 工具栏 */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

/* 借贷平衡合计 */
.f5-adj-subtotal { margin-top: 8px; padding: 8px 12px; background: #f0f9eb; border-radius: 4px; font-weight: 600; }
.f5-adj-subtotal.balance-fail { background: #fef0f0; }
.ok { color: #67c23a; margin-left: 12px; }
.err { color: #f56c6c; margin-left: 12px; }
</style>
