<template>
  <div class="h7-tab-depreciation-alloc">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>
        审计目标：复核本期生产性生物资产折旧在各成本费用对象间的分配，验证分配依据合理、
        分配合计与折旧测算(H7-11)总额勾稽一致。
      </template>
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">+ 新增分配对象</el-button>
      <span class="chip-wrap"><GtIndexChip value="wp:H7-12" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ rows.length }} 项</el-tag>
    </div>

    <!-- 折旧总额来源 -->
    <div class="total-row">
      <span>本期折旧总额（来自 H7-11）：</span>
      <el-input-number v-if="!isReadonly" v-model="totalDepAmount" :controls="false" size="small" class="total-input" @change="persist('H7-12-total', String(totalDepAmount))" />
      <span v-else class="amount-cell">{{ fmtAmt(totalDepAmount) }}</span>
    </div>

    <el-table :data="displayRows" border stripe size="small" class="alloc-table">
      <el-table-column prop="target" label="分配对象" min-width="180" fixed>
        <template #default="{ row }">
          <el-select v-if="!row.isSubtotal && !isReadonly" v-model="row.target" filterable allow-create size="small" @change="onUpdate()">
            <el-option v-for="t in ALLOC_TARGETS" :key="t" :label="t" :value="t" />
          </el-select>
          <span v-else>{{ row.target }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="accountCode" label="对应科目" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!row.isSubtotal && !isReadonly" v-model="row.accountCode" size="small" placeholder="如5001" @change="onUpdate()" />
          <span v-else>{{ row.accountCode }}</span>
        </template>
      </el-table-column>
      <el-table-column label="分配金额" min-width="130" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="!row.isSubtotal && !isReadonly" v-model="row.amount" size="small" class="amt-input" @change="onUpdate()" />
          <span v-else class="amount-cell">{{ fmtAmt(row.amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="占比" min-width="90" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="占比=分配金额/分配合计×100">{{ ratio(row).toFixed(2) }}%</span>
        </template>
      </el-table-column>
      <el-table-column prop="basis" label="分配依据" min-width="160">
        <template #default="{ row }">
          <el-input v-if="!row.isSubtotal && !isReadonly" v-model="row.basis" size="small" @change="onUpdate()" />
          <span v-else>{{ row.basis }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="70" align="center">
        <template #default="{ row }">
          <el-button v-if="!row.isSubtotal && !isReadonly" size="small" type="danger" link @click="removeRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分配勾稽校验 -->
    <el-alert v-if="allocDiff !== 0" type="warning" :closable="false" show-icon class="check-alert">
      <template #title>分配勾稽：分配合计 {{ fmtAmt(totalAlloc) }} 与折旧总额 {{ fmtAmt(totalDepAmount) }} 差异 {{ fmtAmt(allocDiff) }}，请核对。</template>
    </el-alert>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计说明</span>
          <div class="title-actions">
            <el-button size="small" link @click="handleReview('H7-12')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="请填写折旧分配复核说明..." :disabled="isReadonly" @blur="persist('H7-12-note', auditNote)" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计结论</span></div></template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="A、未见异常。B、除上述调整事项外，其余未见异常。C、存在重大未调整事项或范围受限，不可确认。" @blur="persist('H7-12-conclusion', auditConclusion)" />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示（CAS 5 生物资产准则）</summary>
      <ul>
        <li>生产性生物资产折旧应根据受益对象分配计入相关成本费用。</li>
        <li>常见分配对象：生产成本、制造费用、管理费用、其他业务成本、在建工程等。</li>
        <li>分配合计应与折旧测算表(H7-11)本期折旧总额勾稽一致，差异非零须查明。</li>
        <li>占比列自动计算（分配金额/分配合计），灰底列为自动计算。</li>
        <li>新增分配对象须先选择或输入对象名称后创建。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * H7TabDepreciationAlloc.vue — H7-12 折旧分配分析表
 *
 * 折旧总额在成本费用对象间分配 + 占比 + 与H7-11勾稽 + 动态行。
 * 消费 useH7Depreciation(getString 种子) + api.put 持久化(remark, JSON 打包)。
 *
 * Spec: .kiro/specs/h7-biological-assets/  Requirements: 折旧分配分析
 */
import { ref, computed, onMounted, inject, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH7Depreciation } from '../../composables/useH7Depreciation'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const localResponses = ref<Map<string, any>>(new Map(props.allResponses ?? []))
const allResponsesRef = computed(() => localResponses.value)
const { getString, getNum } = useH7Depreciation(allResponsesRef as any, {
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

const ALLOC_TARGETS = ['生产成本', '制造费用', '管理费用', '其他业务成本', '在建工程', '销售费用']

function num(v: any): number { const n = Number(v); return Number.isFinite(n) ? n : 0 }

interface AllocRow { rowId: string; target: string; accountCode: string; amount: number; basis: string; isSubtotal?: boolean }
function blankRow(target: string): AllocRow {
  return { rowId: `al${Date.now()}${Math.floor(Math.random() * 1000)}`, target, accountCode: '', amount: 0, basis: '', isSubtotal: false }
}

const rows = ref<AllocRow[]>([])
const totalDepAmount = ref(0)
const auditNote = ref('')
const auditConclusion = ref('')

const totalAlloc = computed(() => rows.value.reduce((s, r) => s + num(r.amount), 0))
const allocDiff = computed(() => Number((totalAlloc.value - num(totalDepAmount.value)).toFixed(2)))
function ratio(r: AllocRow): number { return totalAlloc.value === 0 ? 0 : (num(r.amount) / totalAlloc.value) * 100 }

const subtotalRow = computed<AllocRow>(() => ({ rowId: 'subtotal', target: '合计', accountCode: '', amount: totalAlloc.value, basis: '', isSubtotal: true }))
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
  const raw = getString('H7-12-rows')
  if (raw) { try { const arr = JSON.parse(raw); if (Array.isArray(arr)) rows.value = arr } catch { /* ignore */ } }
  const t = getString('H7-12-total')
  if (t) totalDepAmount.value = num(t)
  // 若未手填，尝试从 H7-11 折旧测算合计推导
  if (!totalDepAmount.value) {
    const noimpRaw = getString('H7-11-noimp-rows')
    if (noimpRaw) { try { const arr = JSON.parse(noimpRaw); if (Array.isArray(arr)) totalDepAmount.value = arr.reduce((s: number, r: any) => s + num(r.cost) * (1 - num(r.salvageRatePct) / 100) / (num(r.usefulLife) || 1) / 12 * num(r.usedMonths), 0) } catch { /* ignore */ } }
  }
  auditNote.value = getString('H7-12-note') || ''
  auditConclusion.value = getString('H7-12-conclusion') || ''
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

function onUpdate() { void persist('H7-12-rows', rows.value) }

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入分配对象名称', '新增分配对象', { confirmButtonText: '确定', cancelButtonText: '取消', inputValue: '生产成本' })
    if (value) { rows.value.push(blankRow(value)); onUpdate() }
  } catch { /* cancelled */ }
}

function removeRow(rowId: string) {
  rows.value = rows.value.filter((r) => r.rowId !== rowId)
  onUpdate()
}

function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

onMounted(() => { void loadOwn() })
</script>

<style scoped>
.h7-tab-depreciation-alloc { padding: 16px; font-size: var(--wp-font-size, 13px); }
.obj-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.chip-wrap { display: inline-flex; }
.total-row { margin-bottom: 12px; font-weight: 500; display: flex; align-items: center; gap: 8px; }
.total-input { width: 180px; }
.alloc-table { font-size: var(--wp-font-size, 13px); }
.alloc-table :deep(.auto-calc-col) { background: var(--el-fill-color-lighter); }
.amt-input { width: 100%; }
.amount-cell { font-variant-numeric: tabular-nums; }
.formula-cell { font-variant-numeric: tabular-nums; border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.check-alert { margin: 12px 0; }
.note-card { margin: 16px 0; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
