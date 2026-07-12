<template>
  <div class="h7-tab-adjustment">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>
        审计目标：汇总生产性生物资产相关的调整分录（AJE）与重分类分录（RJE），确保每笔分录借贷平衡，
        并可追溯至审定表(H7-1)与试算表回写。
      </template>
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddEntry">+ 新增调整分录</el-button>
      <span class="chip-wrap"><GtIndexChip value="wp:H7-3" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ rows.length }} 笔</el-tag>
      <el-tag size="small" :type="isBalanced ? 'success' : 'danger'">{{ isBalanced ? '借贷平衡' : '借贷不平衡' }}</el-tag>
    </div>

    <el-table :data="displayRows" border stripe size="small" class="adj-table">
      <el-table-column prop="entryNo" label="分录号" min-width="90">
        <template #default="{ row }">
          <el-input v-if="!row.isSubtotal && !isReadonly" v-model="row.entryNo" size="small" @change="onUpdate()" />
          <span v-else>{{ row.entryNo }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="type" label="类型" min-width="90">
        <template #default="{ row }">
          <el-select v-if="!row.isSubtotal && !isReadonly" v-model="row.type" size="small" @change="onUpdate()">
            <el-option label="AJE" value="AJE" />
            <el-option label="RJE" value="RJE" />
          </el-select>
          <span v-else>{{ row.type }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="summary" label="摘要" min-width="180">
        <template #default="{ row }">
          <el-input v-if="!row.isSubtotal && !isReadonly" v-model="row.summary" size="small" @change="onUpdate()" />
          <span v-else>{{ row.summary }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="accountCode" label="科目编码" min-width="110">
        <template #default="{ row }">
          <el-input v-if="!row.isSubtotal && !isReadonly" v-model="row.accountCode" size="small" placeholder="如1621" @change="onUpdate()" />
          <span v-else>{{ row.accountCode }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="accountName" label="科目名称" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!row.isSubtotal && !isReadonly" v-model="row.accountName" size="small" @change="onUpdate()" />
          <span v-else>{{ row.accountName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!row.isSubtotal && !isReadonly" v-model="row.debit" :controls="false" size="small" class="amt-input" @change="onUpdate()" />
          <span v-else class="amount-cell">{{ fmtAmt(row.debit) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!row.isSubtotal && !isReadonly" v-model="row.credit" :controls="false" size="small" class="amt-input" @change="onUpdate()" />
          <span v-else class="amount-cell">{{ fmtAmt(row.credit) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="70" align="center">
        <template #default="{ row }">
          <el-button v-if="!row.isSubtotal && !isReadonly" size="small" type="danger" link @click="removeRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 借贷平衡校验 -->
    <el-alert v-if="!isBalanced" type="error" :closable="false" show-icon class="balance-alert">
      <template #title>借贷不平衡：借方合计 {{ fmtAmt(totalDebit) }} ≠ 贷方合计 {{ fmtAmt(totalCredit) }}，差额 {{ fmtAmt(totalDebit - totalCredit) }}。</template>
    </el-alert>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>调整说明</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAi('adjustment')"><el-icon><MagicStick /></el-icon> AI生成</el-button>
            <el-button size="small" link @click="handleReview('H7-3')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="请填写调整分录的依据说明..." :disabled="isReadonly" @blur="persist('H7-3-note', auditNote)" />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示（CAS 5 生物资产准则）</summary>
      <ul>
        <li>AJE（审计调整分录）用于更正错报，影响审定数；RJE（重分类分录）仅调整列报不影响损益。</li>
        <li>每笔调整分录借贷必须平衡（借方合计=贷方合计）。</li>
        <li>常见生物资产调整：折旧计提不足/减值计提、公允价值变动确认、成熟资产转入等。</li>
        <li>调整分录审定后应与 H7-1 审定表的 AJE/RJE 列勾稽一致。</li>
        <li>新增分录须先输入分录号确认后创建。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H7TabAdjustment.vue — H7-3 调整分录汇总
 *
 * AJE/RJE 分录表 + 借贷平衡校验 + 动态行。
 * 消费 useH7Adjustment(getString 种子) + api.put 持久化(remark, JSON 打包行数组)。
 *
 * Spec: .kiro/specs/h7-biological-assets/  Requirements: 调整分录汇总
 */
import { ref, computed, onMounted, inject, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH7Adjustment } from '../../composables/useH7Adjustment'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const localResponses = ref<Map<string, any>>(new Map(props.allResponses ?? []))
const allResponsesRef = computed(() => localResponses.value)
const { getString, getNum } = useH7Adjustment(allResponsesRef as any, {
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

function num(v: any): number { const n = Number(v); return Number.isFinite(n) ? n : 0 }

interface AdjEntry { rowId: string; entryNo: string; type: string; summary: string; accountCode: string; accountName: string; debit: number; credit: number; isSubtotal?: boolean }
function blankEntry(no: string): AdjEntry {
  return { rowId: `e${Date.now()}${Math.floor(Math.random() * 1000)}`, entryNo: no, type: 'AJE', summary: '', accountCode: '', accountName: '', debit: 0, credit: 0 }
}

const rows = ref<AdjEntry[]>([])
const auditNote = ref('')

const totalDebit = computed(() => rows.value.reduce((s, r) => s + num(r.debit), 0))
const totalCredit = computed(() => rows.value.reduce((s, r) => s + num(r.credit), 0))
const isBalanced = computed(() => Math.abs(totalDebit.value - totalCredit.value) < 0.005)
const subtotalRow = computed<AdjEntry>(() => ({
  rowId: 'subtotal', entryNo: '合计', type: '', summary: '', accountCode: '', accountName: '',
  debit: totalDebit.value, credit: totalCredit.value, isSubtotal: true,
}))
const displayRows = computed(() => [...rows.value, subtotalRow.value])

async function loadOwn() {
  try {
    const list: any[] = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const m = new Map(localResponses.value)
    for (const r of (Array.isArray(list) ? list : [])) {
      if (r.item_id?.startsWith('H7-')) m.set(r.item_id, { item_id: r.item_id, conclusion: r.conclusion ?? null, remark: r.remark ?? null })
    }
    localResponses.value = m
  } catch { /* empty */ }
  const raw = getString('H7-3-rows')
  if (raw) { try { const arr = JSON.parse(raw); if (Array.isArray(arr)) rows.value = arr } catch { /* ignore */ } }
  auditNote.value = getString('H7-3-note') || ''
  void getNum
}

async function persist(itemId: string, value: any) {
  const remark = value == null ? null : (typeof value === 'string' ? value : JSON.stringify(value))
  localResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark })
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items: [{ item_id: itemId, conclusion: null, remark }],
    })
  } catch { ElMessage.error('保存失败，请稍后重试') }
}

function onUpdate() { void persist('H7-3-rows', rows.value) }

async function handleAddEntry() {
  try {
    const { value } = await ElMessageBox.prompt('请输入分录号', '新增调整分录', { confirmButtonText: '确定', cancelButtonText: '取消', inputValue: `AJE-${rows.value.length + 1}` })
    if (value) { rows.value.push(blankEntry(value)); onUpdate() }
  } catch { /* cancelled */ }
}

function removeRow(rowId: string) {
  rows.value = rows.value.filter((r) => r.rowId !== rowId)
  onUpdate()
}

function handleAi(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section, wpId: props.wpId } }))
}
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

onMounted(() => { void loadOwn() })
</script>

<style scoped>
.h7-tab-adjustment { padding: 16px; font-size: var(--wp-font-size, 13px); }
.obj-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.chip-wrap { display: inline-flex; }
.adj-table { font-size: var(--wp-font-size, 13px); }
.amt-input { width: 100%; }
.amount-cell { font-variant-numeric: tabular-nums; }
.balance-alert { margin: 12px 0; }
.note-card { margin: 16px 0; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
