<template>
  <div class="h7-tab-related-party">
    <el-alert type="info" :closable="false" show-icon class="audit-goal">
      <template #title>
        审计目标：识别与生产性生物资产相关的关联方交易，评价交易定价的公允性及披露的完整性，关注是否通过关联交易调节资产价值或损益（CAS 36《关联方披露》）。
      </template>
    </el-alert>

    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H7-17" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
    </div>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>
            H7-17 关联交易检查 — {{ rows.length }}项 合计 {{ fmtAmt(totalAmount) }}
            <GtIndexChip value="wp:H7-2" />
            <el-tag size="small" type="info" class="row-tag">共 {{ rows.length }} 行</el-tag>
          </span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="handleReview('H7-17')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <div class="summary-row">
        <span>价差异常（|价差率|&gt;10%）：<b :class="{ 'text-danger': abnormalCount > 0 }">{{ abnormalCount }}</b> 项</span>
        <span>未披露：<b :class="{ 'text-warn': undisclosedCount > 0 }">{{ undisclosedCount }}</b> 项</span>
      </div>

      <el-table :data="rows" border stripe size="small" class="check-table" max-height="500">
        <el-table-column type="index" label="序" width="46" align="center" fixed />
        <el-table-column prop="relatedParty" label="关联方名称" min-width="130" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.relatedParty" size="small" @change="persistRows" />
            <span v-else>{{ row.relatedParty }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="txType" label="交易类型" width="130">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.txType" size="small" @change="persistRows">
              <el-option v-for="t in TX_TYPES" :key="t" :label="t" :value="t" />
            </el-select>
            <span v-else>{{ row.txType }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="txAmount" label="交易金额" min-width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" v-model="row.txAmount" size="small" @change="persistRows" />
            <span v-else class="amount-cell">{{ fmtAmt(row.txAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="txPrice" label="交易单价" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.txPrice" :controls="false" size="small" @change="persistRows" />
            <span v-else class="amount-cell">{{ fmtAmt(row.txPrice) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="marketPrice" label="市场公允单价" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.marketPrice" :controls="false" size="small" @change="persistRows" />
            <span v-else class="amount-cell">{{ fmtAmt(row.marketPrice) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="价差率" min-width="90" align="right">
          <template #default="{ row }">
            <span class="calc-cell" :class="{ 'has-warn': isAbnormal(row) }" title="=(交易单价-市场公允单价)/市场公允单价×100%">
              {{ fmtRate(priceDiff(row)) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="fairness" label="定价公允性" width="120" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.fairness" size="small" style="width:96px" @change="persistRows">
              <el-option label="公允" value="公允" />
              <el-option label="不公允" value="不公允" />
              <el-option label="待核实" value="待核实" />
            </el-select>
            <el-tag v-else :type="row.fairness === '公允' ? 'success' : (row.fairness === '不公允' ? 'danger' : 'warning')" size="small">{{ row.fairness || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="disclosed" label="是否披露" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.disclosed" size="small" style="width:80px" @change="persistRows">
              <el-option label="已披露" value="已披露" />
              <el-option label="未披露" value="未披露" />
            </el-select>
            <el-tag v-else :type="row.disclosed === '已披露' ? 'success' : 'danger'" size="small">{{ row.disclosed || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="检查结论" min-width="120">
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
        <el-button size="small" @click="handleAddRow">+ 新增关联交易</el-button>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计说明与结论</span>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="记录关联交易识别、定价公允性评价与披露检查结果" @blur="persist('H7-17-note', auditNote)" />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计结论</span></div></template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="A、未见异常。B、除上述调整事项外，其余未见异常。C、存在重大未调整事项或范围受限，不可确认。" @blur="persist('H7-17-conclusion', auditConclusion)" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>价差率 = (交易单价 − 市场公允单价) / 市场公允单价 × 100%；|价差率| &gt; 10% 需重点关注定价公允性。</li>
        <li>关注是否存在通过关联方低价/高价买卖生物资产调节资产账面价值或利润的情形。</li>
        <li>关联方交易应在附注中充分披露交易类型、金额、定价政策及未结算余额。</li>
        <li>结合 H7-2 明细表核对关联交易涉及的资产是否已恰当入账。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { ref, computed, inject, onMounted, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH7RelatedParty } from '../../composables/useH7RelatedParty'
import { calcSubtotal, calcPriceDiffRate } from '../../composables/useH7FormulaEngine'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly?: boolean }>()
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const allResponsesRef = computed(() => props.allResponses)
const check = useH7RelatedParty(allResponsesRef as any, { wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })

const TX_TYPES = ['购买生物资产', '出售生物资产', '生物资产租赁', '产品购销', '劳务/服务', '其他']

interface Row {
  rowId: string
  relatedParty: string
  txType: string
  txAmount: number
  txPrice: number
  marketPrice: number
  fairness: string
  disclosed: string
  conclusion: string
}

const rows = ref<Row[]>([])
const auditNote = ref('')
const auditConclusion = ref('')

function priceDiff(r: Row): number { return calcPriceDiffRate(Number(r.txPrice) || 0, Number(r.marketPrice) || 0) }
function isAbnormal(r: Row): boolean { return (Number(r.marketPrice) || 0) > 0 && Math.abs(priceDiff(r)) > 10 }

const totalAmount = computed(() => calcSubtotal(rows.value.map((r) => Number(r.txAmount) || 0)))
const abnormalCount = computed(() => rows.value.filter((r) => isAbnormal(r)).length)
const undisclosedCount = computed(() => rows.value.filter((r) => r.disclosed === '未披露').length)

function normalize(raw: any): Row {
  return {
    rowId: raw.rowId ?? `r-${Math.random().toString(36).slice(2, 9)}`,
    relatedParty: raw.relatedParty ?? '',
    txType: raw.txType ?? '',
    txAmount: Number(raw.txAmount) || 0,
    txPrice: Number(raw.txPrice) || 0,
    marketPrice: Number(raw.marketPrice) || 0,
    fairness: raw.fairness ?? '',
    disclosed: raw.disclosed ?? '',
    conclusion: raw.conclusion ?? '',
  }
}

function seed(): void {
  const raw = check.getString('H7-17-rows')
  if (raw) { try { const p = JSON.parse(raw); if (Array.isArray(p)) rows.value = p.map(normalize) } catch { /* ignore */ } }
  auditNote.value = check.getString('H7-17-note')
  auditConclusion.value = check.getString('H7-17-conclusion') || ''
}
onMounted(seed)

function persist(itemId: string, val: any): void { if (!props.isReadonly) saveResponse(itemId, val) }
function persistRows(): void { persist('H7-17-rows', rows.value) }

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入关联方名称', '新增关联交易', { confirmButtonText: '确定', cancelButtonText: '取消' })
    if (value) { rows.value.push(normalize({ relatedParty: value })); persistRows() }
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
function fmtRate(v: number): string { return `${v.toFixed(2)}%` }
</script>

<style scoped>
.h7-tab-related-party { padding: 16px; font-size: var(--wp-font-size, 13px); }
.audit-goal { margin-bottom: 12px; }
.tab-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.chip-wrap { display: inline-flex; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.row-tag { margin-left: 8px; }
.summary-row { display: flex; gap: 24px; margin-bottom: 12px; padding: 6px 12px; background: var(--el-fill-color-lighter); border-radius: 4px; }
.text-danger { color: var(--el-color-danger); }
.text-warn { color: var(--el-color-warning); }
.check-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.calc-cell { font-variant-numeric: tabular-nums; background: var(--el-fill-color-light); border-bottom: 1px dashed var(--el-border-color); cursor: help; display: inline-block; width: 100%; text-align: right; }
.calc-cell.has-warn { color: var(--el-color-danger); font-weight: 600; }
.action-bar { margin: 12px 0; }
.note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
