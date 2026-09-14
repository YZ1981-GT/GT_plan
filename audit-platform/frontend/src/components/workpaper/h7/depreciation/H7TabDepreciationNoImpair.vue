<template>
  <div class="h7-tab-depreciation-no-impair">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>
        审计目标：复核成本模式下生产性生物资产按直线法（年限平均法）计提的折旧，验证原值、残值率、使用寿命参数合理，
        年/月折旧额及累计折旧计算准确（不含减值影响）。
      </template>
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">+ 新增资产行</el-button>
      <span class="chip-wrap"><GtIndexChip value="wp:H7-11" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">直线法·不含减值 · 共 {{ rows.length }} 行</el-tag>
    </div>

    <el-table :data="displayRows" border stripe size="small" class="dep-table">
      <el-table-column prop="assetName" label="资产名称" min-width="150" fixed>
        <template #default="{ row }">
          <el-input v-if="!row.isSubtotal && !isReadonly" v-model="row.assetName" size="small" @change="onUpdate()" />
          <span v-else>{{ row.assetName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="原值" min-width="120" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="!row.isSubtotal && !isReadonly" v-model="row.cost" size="small" class="amt-input" @change="onUpdate()" />
          <span v-else class="amount-cell">{{ fmtAmt(row.cost) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="残值率(%)" min-width="100" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="!row.isSubtotal && !isReadonly" v-model="row.salvageRatePct" size="small" class="amt-input" @change="onUpdate()" />
          <span v-else class="amount-cell">{{ row.isSubtotal ? '' : row.salvageRatePct + '%' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="使用寿命(年)" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!row.isSubtotal && !isReadonly" v-model="row.usefulLife" :controls="false" :min="0" size="small" class="amt-input" @change="onUpdate()" />
          <span v-else class="amount-cell">{{ row.isSubtotal ? '' : row.usefulLife }}</span>
        </template>
      </el-table-column>
      <el-table-column label="年折旧额" min-width="120" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="年折旧=原值×(1-残值率)/使用寿命(直线法)">{{ fmtAmt(annualDep(row)) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="月折旧额" min-width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="月折旧=年折旧/12">{{ fmtAmt(monthlyDep(row)) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="已用月数" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!row.isSubtotal && !isReadonly" v-model="row.usedMonths" :controls="false" :min="0" size="small" class="amt-input" @change="onUpdate()" />
          <span v-else class="amount-cell">{{ row.isSubtotal ? '' : row.usedMonths }}</span>
        </template>
      </el-table-column>
      <el-table-column label="累计折旧" min-width="120" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="累计折旧=月折旧×已用月数">{{ fmtAmt(accDep(row)) }}</span>
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
          <span>审计说明</span>
          <div class="title-actions">
            <el-button size="small" link @click="handleReview('H7-11-noimp')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="请填写折旧测算复核说明..." :disabled="isReadonly" @blur="persist('H7-11-noimp-note', auditNote)" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计结论</span></div></template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="A、未见异常。B、除上述调整事项外，其余未见异常。C、存在重大未调整事项或范围受限，不可确认。" @blur="persist('H7-11-noimp-conclusion', auditConclusion)" />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示（CAS 5 生物资产准则）</summary>
      <ul>
        <li>成本模式下成熟(达到预定生产经营目的)的生产性生物资产采用直线法计提折旧。</li>
        <li>年折旧额 = 原值 ×(1 - 残值率)/ 使用寿命(年)。</li>
        <li>月折旧额 = 年折旧额 / 12；累计折旧 = 月折旧额 × 已使用月数。</li>
        <li>本表不考虑减值影响，如已计提减值请使用"含减值"分支。</li>
        <li>计算列采用引擎纯函数(calcStraightLine/calcMonthlyDep/calcAccDep)，灰底列为自动计算。</li>
        <li>新增资产行须先输入资产名称确认后创建。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * H7TabDepreciationNoImpair.vue — H7-11 折旧测算表（不含减值·直线法）
 *
 * 按资产逐行直线法折旧测算 + 合计 + 动态行。
 * 消费 useH7Depreciation(getString 种子) + useH7DepreciationEngine(纯函数计算) +
 * api.put 持久化(remark, JSON 打包)。
 *
 * Spec: .kiro/specs/h7-biological-assets/  Requirements: 11.1-11.4 折旧测算(直线法)
 */
import { ref, computed, onMounted, inject, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH7Depreciation } from '../../composables/useH7Depreciation'
import { calcStraightLine, calcMonthlyDep, calcAccDep } from '../../composables/useH7DepreciationEngine'

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

function num(v: any): number { const n = Number(v); return Number.isFinite(n) ? n : 0 }

interface DepRow { rowId: string; assetName: string; cost: number; salvageRatePct: number; usefulLife: number; usedMonths: number; isSubtotal?: boolean }
function blankRow(name: string): DepRow {
  return { rowId: `d${Date.now()}${Math.floor(Math.random() * 1000)}`, assetName: name, cost: 0, salvageRatePct: 5, usefulLife: 10, usedMonths: 12 }
}

const rows = ref<DepRow[]>([])
const auditNote = ref('')
const auditConclusion = ref('')

function annualDep(r: DepRow): number { return r.isSubtotal ? num((r as any).annualDep) : calcStraightLine(num(r.cost), num(r.salvageRatePct) / 100, num(r.usefulLife)) }
function monthlyDep(r: DepRow): number { return r.isSubtotal ? num((r as any).monthlyDep) : calcMonthlyDep(annualDep(r)) }
function accDep(r: DepRow): number { return r.isSubtotal ? num((r as any).accDep) : calcAccDep(monthlyDep(r), num(r.usedMonths)) }

const subtotalRow = computed<any>(() => ({
  rowId: 'subtotal', assetName: '合计', isSubtotal: true,
  cost: rows.value.reduce((s, r) => s + num(r.cost), 0),
  annualDep: rows.value.reduce((s, r) => s + annualDep(r), 0),
  monthlyDep: rows.value.reduce((s, r) => s + monthlyDep(r), 0),
  accDep: rows.value.reduce((s, r) => s + accDep(r), 0),
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
  const raw = getString('H7-11-noimp-rows')
  if (raw) { try { const arr = JSON.parse(raw); if (Array.isArray(arr)) rows.value = arr } catch { /* ignore */ } }
  auditNote.value = getString('H7-11-noimp-note') || ''
  auditConclusion.value = getString('H7-11-noimp-conclusion') || ''
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

function onUpdate() { void persist('H7-11-noimp-rows', rows.value) }

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

function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

onMounted(() => { void loadOwn() })
</script>

<style scoped>
.h7-tab-depreciation-no-impair { padding: 16px; font-size: var(--wp-font-size, 13px); }
.obj-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.chip-wrap { display: inline-flex; }
.dep-table { font-size: var(--wp-font-size, 13px); }
.dep-table :deep(.auto-calc-col) { background: var(--el-fill-color-lighter); }
.amt-input { width: 100%; }
.amount-cell { font-variant-numeric: tabular-nums; }
.formula-cell { font-variant-numeric: tabular-nums; border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.note-card { margin: 16px 0; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
