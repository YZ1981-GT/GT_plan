<template>
  <div class="h7-tab-disposal-cost">
    <el-alert type="info" :closable="false" show-icon class="audit-goal">
      <template #title>
        审计目标：验证本期生产性生物资产减少（出售/死亡/毁损/淘汰）的真实性、完整性，处置损益计算准确并已恰当核算（CAS 5《生物资产》）。
      </template>
    </el-alert>

    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H7-7" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
    </div>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>
            H7-7 减少检查（成本模式）— {{ rows.length }}项 处置净损益 {{ fmtAmt(totalGainLoss) }}
            <GtIndexChip value="wp:H7-2" />
            <el-tag size="small" type="info" class="row-tag">共 {{ rows.length }} 行</el-tag>
          </span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="handleReview('H7-7')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <div class="summary-row">
        <span>减少原值合计：{{ fmtAmt(totalCost) }}</span>
        <span>处置收入合计：{{ fmtAmt(totalProceeds) }}</span>
        <span :class="{ 'text-danger': totalGainLoss < 0 }">处置净损益：{{ fmtAmt(totalGainLoss) }}</span>
      </div>

      <el-table :data="rows" border stripe size="small" class="check-table" max-height="500">
        <el-table-column type="index" label="序" width="46" align="center" fixed />
        <el-table-column prop="assetName" label="资产名称" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetName" size="small" @change="persistRows" />
            <span v-else>{{ row.assetName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="disposalType" label="减少方式" width="120">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.disposalType" size="small" @change="persistRows">
              <el-option v-for="t in DISPOSAL_TYPES" :key="t" :label="t" :value="t" />
            </el-select>
            <span v-else>{{ row.disposalType }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="cost" label="账面原值" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.cost" :controls="false" size="small" @change="persistRows" />
            <span v-else class="amount-cell">{{ fmtAmt(row.cost) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accDep" label="累计折旧" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.accDep" :controls="false" size="small" @change="persistRows" />
            <span v-else class="amount-cell">{{ fmtAmt(row.accDep) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="impairment" label="减值准备" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.impairment" :controls="false" size="small" @change="persistRows" />
            <span v-else class="amount-cell">{{ fmtAmt(row.impairment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面净值" min-width="110" align="right">
          <template #default="{ row }">
            <span class="calc-cell" title="=账面原值-累计折旧-减值准备">{{ fmtAmt(netValue(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="proceeds" label="处置收入" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.proceeds" :controls="false" size="small" @change="persistRows" />
            <span v-else class="amount-cell">{{ fmtAmt(row.proceeds) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="disposalCost" label="处置费用" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.disposalCost" :controls="false" size="small" @change="persistRows" />
            <span v-else class="amount-cell">{{ fmtAmt(row.disposalCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="处置损益" min-width="110" align="right">
          <template #default="{ row }">
            <span class="calc-cell" :class="{ 'has-loss': gainLoss(row) < 0 }" title="=处置收入-处置费用-账面净值">{{ fmtAmt(gainLoss(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="voucherNo" label="凭证号" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="persistRows" />
            <span v-else>{{ row.voucherNo }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="检查结论" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.conclusion" size="small" @change="persistRows" />
            <span v-else>{{ row.conclusion }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="56" align="center" v-if="!isReadonly">
          <template #default="{ row }"><el-button type="danger" link size="small" @click="removeRow(row.rowId)">删除</el-button></template>
        </el-table-column>
      </el-table>

      <div class="action-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddRow">+ 新增减少项</el-button>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计说明与结论</span>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="记录减少检查过程、死亡/淘汰审批与处置损益核算" @blur="persist('H7-7-cost-note', auditNote)" />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计结论</span></div></template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="A、未见异常。B、除上述调整事项外，其余未见异常。C、存在重大未调整事项或范围受限，不可确认。" @blur="persist('H7-7-cost-conclusion', auditConclusion)" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>账面净值 = 账面原值 − 累计折旧 − 减值准备。</li>
        <li>处置损益 = 处置收入 − 处置费用 − 账面净值；损失以负数表示。</li>
        <li>生物资产死亡、毁损的，扣除保险赔偿及残料价值后计入当期损益。</li>
        <li>本期减少合计应与 H7-2 明细表本期减少、H7-1 审定表贷方发生额勾稽一致。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, onMounted, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH7DisposalCheck } from '../../composables/useH7DisposalCheck'
import { calcSubtotal, calcNetValue } from '../../composables/useH7FormulaEngine'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly?: boolean }>()
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const allResponsesRef = computed(() => props.allResponses)
const check = useH7DisposalCheck(allResponsesRef as any, { wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })

const DISPOSAL_TYPES = ['出售', '死亡', '毁损', '淘汰', '对外投资', '互转转出', '其他']

interface Row {
  rowId: string
  assetName: string
  disposalType: string
  cost: number
  accDep: number
  impairment: number
  proceeds: number
  disposalCost: number
  voucherNo: string
  conclusion: string
}

const rows = ref<Row[]>([])
const auditNote = ref('')
const auditConclusion = ref('')

function netValue(r: Row): number { return calcNetValue(Number(r.cost) || 0, Number(r.accDep) || 0, Number(r.impairment) || 0) }
function gainLoss(r: Row): number { return (Number(r.proceeds) || 0) - (Number(r.disposalCost) || 0) - netValue(r) }

const totalCost = computed(() => calcSubtotal(rows.value.map((r) => Number(r.cost) || 0)))
const totalProceeds = computed(() => calcSubtotal(rows.value.map((r) => Number(r.proceeds) || 0)))
const totalGainLoss = computed(() => calcSubtotal(rows.value.map((r) => gainLoss(r))))

function normalize(raw: any): Row {
  return {
    rowId: raw.rowId ?? `r-${Math.random().toString(36).slice(2, 9)}`,
    assetName: raw.assetName ?? '',
    disposalType: raw.disposalType ?? '',
    cost: Number(raw.cost) || 0,
    accDep: Number(raw.accDep) || 0,
    impairment: Number(raw.impairment) || 0,
    proceeds: Number(raw.proceeds) || 0,
    disposalCost: Number(raw.disposalCost) || 0,
    voucherNo: raw.voucherNo ?? '',
    conclusion: raw.conclusion ?? '',
  }
}

function seed(): void {
  const raw = check.getString('H7-7-cost-rows')
  if (raw) { try { const p = JSON.parse(raw); if (Array.isArray(p)) rows.value = p.map(normalize) } catch { /* ignore */ } }
  auditNote.value = check.getString('H7-7-cost-note')
  auditConclusion.value = check.getString('H7-7-cost-conclusion') || ''
}
onMounted(seed)

function persist(itemId: string, val: any): void { if (!props.isReadonly) saveResponse(itemId, val) }
function persistRows(): void { persist('H7-7-cost-rows', rows.value) }

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入资产名称', '新增减少项', { confirmButtonText: '确定', cancelButtonText: '取消' })
    if (value) { rows.value.push(normalize({ assetName: value })); persistRows() }
  } catch { /* cancelled */ }
}
function removeRow(rowId: string): void {
  const i = rows.value.findIndex((r) => r.rowId === rowId)
  if (i >= 0) { rows.value.splice(i, 1); persistRows() }
}
function handleReview(id: string): void { openReviewDialog(id) }
function fmtAmt(v: number | null | undefined): string {
  return v == null ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h7-tab-disposal-cost { padding: 16px; font-size: var(--wp-font-size, 13px); }
.audit-goal { margin-bottom: 12px; }
.tab-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.chip-wrap { display: inline-flex; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.row-tag { margin-left: 8px; }
.summary-row { display: flex; gap: 24px; margin-bottom: 12px; padding: 6px 12px; background: var(--el-fill-color-lighter); border-radius: 4px; }
.text-danger { color: var(--el-color-danger); }
.check-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.calc-cell { font-variant-numeric: tabular-nums; background: var(--el-fill-color-light); border-bottom: 1px dashed var(--el-border-color); cursor: help; display: inline-block; width: 100%; text-align: right; }
.calc-cell.has-loss { color: var(--el-color-danger); font-weight: 600; }
.action-bar { margin: 12px 0; }
.note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
