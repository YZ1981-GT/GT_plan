<template>
  <div class="h7-tab-fair-value-review">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>
        审计目标：复核公允价值模式下生产性生物资产的公允价值确定，验证数量×单位公允价值计算准确、
        估值层级恰当，公允价值总额与账面价值差异可解释。
      </template>
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">+ 新增资产行</el-button>
      <span class="chip-wrap"><GtIndexChip value="wp:H7-13" :context-project-id="projectId" /></span>
      <el-tag size="small" type="warning">公允价值复核 · 共 {{ rows.length }} 行</el-tag>
    </div>

    <el-table :data="displayRows" border stripe size="small" class="fv-table">
      <el-table-column prop="assetName" label="资产名称" min-width="150" fixed>
        <template #default="{ row }">
          <el-input v-if="!row.isSubtotal && !isReadonly" v-model="row.assetName" size="small" @change="onUpdate()" />
          <span v-else>{{ row.assetName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="数量" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!row.isSubtotal && !isReadonly" v-model="row.quantity" :controls="false" size="small" class="amt-input" @change="onUpdate()" />
          <span v-else class="amount-cell">{{ row.isSubtotal ? '' : fmtNum(row.quantity) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="unit" label="单位" min-width="80">
        <template #default="{ row }">
          <el-input v-if="!row.isSubtotal && !isReadonly" v-model="row.unit" size="small" placeholder="头/株/亩" @change="onUpdate()" />
          <span v-else>{{ row.unit }}</span>
        </template>
      </el-table-column>
      <el-table-column label="单位公允价值" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!row.isSubtotal && !isReadonly" v-model="row.unitFv" :controls="false" size="small" class="amt-input" @change="onUpdate()" />
          <span v-else class="amount-cell">{{ row.isSubtotal ? '' : fmtAmt(row.unitFv) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="公允价值总额" min-width="130" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="公允价值总额=数量×单位公允价值">{{ fmtAmt(fvTotal(row)) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="账面价值" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!row.isSubtotal && !isReadonly" v-model="row.bookValue" :controls="false" size="small" class="amt-input" @change="onUpdate()" />
          <span v-else class="amount-cell">{{ fmtAmt(row.bookValue) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="差异" min-width="120" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" :class="{ diff: Math.abs(diffVal(row)) > 0.005 }" title="差异=公允价值总额-账面价值">{{ fmtAmt(diffVal(row)) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="fvLevel" label="估值层级" min-width="120">
        <template #default="{ row }">
          <el-select v-if="!row.isSubtotal && !isReadonly" v-model="row.fvLevel" size="small" @change="onUpdate()">
            <el-option v-for="l in FV_LEVELS" :key="l" :label="l" :value="l" />
          </el-select>
          <span v-else>{{ row.fvLevel }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="method" label="估值方法/依据" min-width="150">
        <template #default="{ row }">
          <el-input v-if="!row.isSubtotal && !isReadonly" v-model="row.method" size="small" @change="onUpdate()" />
          <span v-else>{{ row.method }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="70" align="center">
        <template #default="{ row }">
          <el-button v-if="!row.isSubtotal && !isReadonly" size="small" type="danger" link @click="removeRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计说明 / 结论</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAi('fv-review')"><el-icon><MagicStick /></el-icon> AI生成</el-button>
            <el-button size="small" link @click="handleReview('H7-13')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="请填写公允价值复核说明（估值技术、关键参数、市场数据来源、差异原因等）..." :disabled="isReadonly" @blur="persist('H7-13-note', auditNote)" />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示（CAS 5 生物资产准则 / CAS 39 公允价值计量）</summary>
      <ul>
        <li>公允价值模式下须复核公允价值确定的可靠性：数量×单位公允价值=公允价值总额。</li>
        <li>估值层级：第一层次(活跃市场报价)、第二层次(可观察输入值)、第三层次(不可观察输入值)。</li>
        <li>公允价值总额与账面价值差异应能合理解释（估值日、市场波动等）。</li>
        <li>关注单位公允价值的市场数据来源、估值技术与关键假设的合理性。</li>
        <li>计算列(公允价值总额/差异)采用自动计算，灰底列不可手改。</li>
        <li>新增资产行须先输入资产名称确认后创建。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H7TabFairValueReview.vue — H7-13 公允价值复核表
 *
 * 按资产逐行复核公允价值(数量×单价) vs 账面价值差异 + 估值层级 + 动态行。
 * 消费 useH7FairValueReview(getString 种子) + api.put 持久化(remark, JSON 打包)。
 *
 * Spec: .kiro/specs/h7-biological-assets/  Requirements: 公允价值复核
 */
import { ref, computed, onMounted, inject, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH7FairValueReview } from '../../composables/useH7FairValueReview'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const localResponses = ref<Map<string, any>>(new Map(props.allResponses ?? []))
const allResponsesRef = computed(() => localResponses.value)
const { getString, getNum } = useH7FairValueReview(allResponsesRef as any, {
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

const FV_LEVELS = ['第一层次(L1)', '第二层次(L2)', '第三层次(L3)']

function num(v: any): number { const n = Number(v); return Number.isFinite(n) ? n : 0 }

interface FvRow { rowId: string; assetName: string; quantity: number; unit: string; unitFv: number; bookValue: number; fvLevel: string; method: string; isSubtotal?: boolean }
function blankRow(name: string): FvRow {
  return { rowId: `fv${Date.now()}${Math.floor(Math.random() * 1000)}`, assetName: name, quantity: 0, unit: '头', unitFv: 0, bookValue: 0, fvLevel: '第二层次(L2)', method: '' }
}

const rows = ref<FvRow[]>([])
const auditNote = ref('')

function fvTotal(r: FvRow): number { return r.isSubtotal ? num((r as any).fvTotal) : num(r.quantity) * num(r.unitFv) }
function diffVal(r: FvRow): number { return r.isSubtotal ? num((r as any).diff) : fvTotal(r) - num(r.bookValue) }

const subtotalRow = computed<any>(() => ({
  rowId: 'subtotal', assetName: '合计', unit: '', fvLevel: '', method: '', isSubtotal: true,
  fvTotal: rows.value.reduce((s, r) => s + fvTotal(r), 0),
  bookValue: rows.value.reduce((s, r) => s + num(r.bookValue), 0),
  diff: rows.value.reduce((s, r) => s + diffVal(r), 0),
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
  const raw = getString('H7-13-rows')
  if (raw) { try { const arr = JSON.parse(raw); if (Array.isArray(arr)) rows.value = arr } catch { /* ignore */ } }
  auditNote.value = getString('H7-13-note') || ''
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

function onUpdate() { void persist('H7-13-rows', rows.value) }

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入资产名称', '新增资产行', { confirmButtonText: '确定', cancelButtonText: '取消' })
    if (value) { rows.value.push(blankRow(value)); onUpdate() }
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
function fmtNum(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN')
}

onMounted(() => { void loadOwn() })
</script>

<style scoped>
.h7-tab-fair-value-review { padding: 16px; font-size: var(--wp-font-size, 13px); }
.obj-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.chip-wrap { display: inline-flex; }
.fv-table { font-size: var(--wp-font-size, 13px); }
.fv-table :deep(.auto-calc-col) { background: var(--el-fill-color-lighter); }
.amt-input { width: 100%; }
.amount-cell { font-variant-numeric: tabular-nums; }
.formula-cell { font-variant-numeric: tabular-nums; border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.formula-cell.diff { color: var(--el-color-warning); font-weight: 600; }
.note-card { margin: 16px 0; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
