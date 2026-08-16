<template>
  <div class="h7-tab-depreciation-with-impair">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>
        审计目标：复核已计提减值准备的生产性生物资产折旧，验证减值后净值计算准确，
        并以减值后净值与剩余使用寿命重新测算年折旧额（直线法）。
      </template>
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">+ 新增资产行</el-button>
      <span class="chip-wrap"><GtIndexChip value="wp:H7-11" :context-project-id="projectId" /></span>
      <el-tag size="small" type="warning">含减值 · 共 {{ rows.length }} 行</el-tag>
    </div>

    <el-table :data="displayRows" border stripe size="small" class="dep-table">
      <el-table-column prop="assetName" label="资产名称" min-width="150" fixed>
        <template #default="{ row }">
          <el-input v-if="!row.isSubtotal && !isReadonly" v-model="row.assetName" size="small" @change="onUpdate()" />
          <span v-else>{{ row.assetName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="原值" min-width="115" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="!row.isSubtotal && !isReadonly" v-model="row.cost" size="small" class="amt-input" @change="onUpdate()" />
          <span v-else class="amount-cell">{{ fmtAmt(row.cost) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="已提累计折旧" min-width="120" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="!row.isSubtotal && !isReadonly" v-model="row.accDep" size="small" class="amt-input" @change="onUpdate()" />
          <span v-else class="amount-cell">{{ fmtAmt(row.accDep) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="减值准备" min-width="115" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="!row.isSubtotal && !isReadonly" v-model="row.impairment" size="small" class="amt-input" @change="onUpdate()" />
          <span v-else class="amount-cell">{{ fmtAmt(row.impairment) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="减值后净值" min-width="120" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="减值后净值=原值-累计折旧-减值准备">{{ fmtAmt(netValue(row)) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="残值率(%)" min-width="95" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="!row.isSubtotal && !isReadonly" v-model="row.salvageRatePct" size="small" class="amt-input" @change="onUpdate()" />
          <span v-else class="amount-cell">{{ row.isSubtotal ? '' : row.salvageRatePct + '%' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="剩余寿命(年)" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!row.isSubtotal && !isReadonly" v-model="row.remainLife" :controls="false" :min="0" size="small" class="amt-input" @change="onUpdate()" />
          <span v-else class="amount-cell">{{ row.isSubtotal ? '' : row.remainLife }}</span>
        </template>
      </el-table-column>
      <el-table-column label="减值后年折旧" min-width="130" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="减值后年折旧=减值后净值×(1-残值率)/剩余使用寿命">{{ fmtAmt(depAfterImp(row)) }}</span>
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
            <el-button size="small" link @click="handleReview('H7-11-imp')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="请填写含减值折旧测算复核说明..." :disabled="isReadonly" @blur="persist('H7-11-imp-note', auditNote)" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计结论</span></div></template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="A、未见异常。B、除上述调整事项外，其余未见异常。C、存在重大未调整事项或范围受限，不可确认。" @blur="persist('H7-11-imp-conclusion', auditConclusion)" />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示（CAS 5 生物资产准则）</summary>
      <ul>
        <li>已计提减值准备的生产性生物资产，应以减值后净值为基础重新测算折旧。</li>
        <li>减值后净值 = 原值 - 已提累计折旧 - 减值准备。</li>
        <li>减值后年折旧 = 减值后净值 ×(1 - 残值率)/ 剩余使用寿命(年)。</li>
        <li>减值损失一经确认，在以后会计期间不得转回。</li>
        <li>计算列采用引擎纯函数 calcDepAfterImpairment，灰底列为自动计算。</li>
        <li>新增资产行须先输入资产名称确认后创建。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * H7TabDepreciationWithImpair.vue — H7-11 折旧测算表（含减值）
 *
 * 按资产逐行减值后折旧测算 + 合计 + 动态行。
 * 消费 useH7Impairment(getString 种子) + useH7DepreciationEngine.calcDepAfterImpairment +
 * api.put 持久化(remark, JSON 打包)。
 *
 * Spec: .kiro/specs/h7-biological-assets/  Requirements: 11.x/减值后折旧
 */
import { ref, computed, onMounted, inject, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH7Impairment } from '../../composables/useH7Impairment'
import { calcDepAfterImpairment } from '../../composables/useH7DepreciationEngine'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const localResponses = ref<Map<string, any>>(new Map(props.allResponses ?? []))
const allResponsesRef = computed(() => localResponses.value)
const { getString, getNum } = useH7Impairment(allResponsesRef as any, {
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

function num(v: any): number { const n = Number(v); return Number.isFinite(n) ? n : 0 }

interface ImpDepRow { rowId: string; assetName: string; cost: number; accDep: number; impairment: number; salvageRatePct: number; remainLife: number; isSubtotal?: boolean }
function blankRow(name: string): ImpDepRow {
  return { rowId: `i${Date.now()}${Math.floor(Math.random() * 1000)}`, assetName: name, cost: 0, accDep: 0, impairment: 0, salvageRatePct: 5, remainLife: 5 }
}

const rows = ref<ImpDepRow[]>([])
const auditNote = ref('')
const auditConclusion = ref('')

function netValue(r: ImpDepRow): number { return r.isSubtotal ? num((r as any).netValue) : num(r.cost) - num(r.accDep) - num(r.impairment) }
function depAfterImp(r: ImpDepRow): number { return r.isSubtotal ? num((r as any).depAfterImp) : calcDepAfterImpairment(netValue(r), num(r.salvageRatePct) / 100, num(r.remainLife)) }

const subtotalRow = computed<any>(() => ({
  rowId: 'subtotal', assetName: '合计', isSubtotal: true,
  cost: rows.value.reduce((s, r) => s + num(r.cost), 0),
  accDep: rows.value.reduce((s, r) => s + num(r.accDep), 0),
  impairment: rows.value.reduce((s, r) => s + num(r.impairment), 0),
  netValue: rows.value.reduce((s, r) => s + netValue(r), 0),
  depAfterImp: rows.value.reduce((s, r) => s + depAfterImp(r), 0),
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
  const raw = getString('H7-11-imp-rows')
  if (raw) { try { const arr = JSON.parse(raw); if (Array.isArray(arr)) rows.value = arr } catch { /* ignore */ } }
  auditNote.value = getString('H7-11-imp-note') || ''
  auditConclusion.value = getString('H7-11-imp-conclusion') || ''
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

function onUpdate() { void persist('H7-11-imp-rows', rows.value) }

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
.h7-tab-depreciation-with-impair { padding: 16px; font-size: var(--wp-font-size, 13px); }
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
