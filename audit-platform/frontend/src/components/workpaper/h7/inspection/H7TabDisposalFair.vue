<template>
  <div class="h7-tab-disposal-fair">
    <el-alert type="info" :closable="false" show-icon class="audit-goal">
      <template #title>
        审计目标：验证公允价值模式下本期生产性生物资产减少的真实性、完整性，处置损益基于处置前账面公允价值计算准确（CAS 5《生物资产》）。
      </template>
    </el-alert>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>
            H7-7 减少检查（公允价值模式）— {{ rows.length }}项 处置净损益 {{ fmtAmt(totalGainLoss) }}
            <GtIndexChip value="wp:H7-2" />
            <el-tag size="small" type="info" class="row-tag">共 {{ rows.length }} 行</el-tag>
          </span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAi"><el-icon><MagicStick /></el-icon> AI说明</el-button>
            <el-button size="small" type="default" link @click="handleReview('H7-7')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <div class="summary-row">
        <span>处置前公允价值合计：{{ fmtAmt(totalCarrying) }}</span>
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
        <el-table-column prop="carryingFairValue" label="处置前公允价值" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.carryingFairValue" :controls="false" size="small" @change="persistRows" />
            <span v-else class="amount-cell">{{ fmtAmt(row.carryingFairValue) }}</span>
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
            <span class="calc-cell" :class="{ 'has-loss': gainLoss(row) < 0 }" title="=处置收入-处置费用-处置前公允价值">{{ fmtAmt(gainLoss(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="voucherNo" label="凭证号" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="persistRows" />
            <span v-else>{{ row.voucherNo }}</span>
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
        <el-button size="small" @click="handleAddRow">+ 新增减少项</el-button>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计说明与结论</span>
          <el-button size="small" type="primary" link @click="handleAi"><el-icon><MagicStick /></el-icon> AI说明</el-button>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="记录减少检查过程与处置损益核算" @blur="persist('H7-7-fair-note', auditNote)" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>公允价值模式下不计提折旧、不计提减值，处置基础为处置前账面公允价值。</li>
        <li>处置损益 = 处置收入 − 处置费用 − 处置前公允价值；损失以负数表示。</li>
        <li>处置前公允价值应与 H7-13 公允价值复核表最近一期确认的公允价值一致。</li>
        <li>本期减少合计应与 H7-2 明细表（公允）本期减少勾稽一致。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, onMounted, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH7DisposalCheck } from '../../composables/useH7DisposalCheck'
import { calcSubtotal } from '../../composables/useH7FormulaEngine'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly?: boolean }>()
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const generateAiText = inject<((section: string, ctx: string, existing: string) => Promise<string>) | null>('generateAiText', null)

const allResponsesRef = computed(() => props.allResponses)
const check = useH7DisposalCheck(allResponsesRef as any, { wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })

const DISPOSAL_TYPES = ['出售', '死亡', '毁损', '淘汰', '对外投资', '互转转出', '其他']

interface Row {
  rowId: string
  assetName: string
  disposalType: string
  carryingFairValue: number
  proceeds: number
  disposalCost: number
  voucherNo: string
  conclusion: string
}

const rows = ref<Row[]>([])
const auditNote = ref('')

function gainLoss(r: Row): number { return (Number(r.proceeds) || 0) - (Number(r.disposalCost) || 0) - (Number(r.carryingFairValue) || 0) }

const totalCarrying = computed(() => calcSubtotal(rows.value.map((r) => Number(r.carryingFairValue) || 0)))
const totalProceeds = computed(() => calcSubtotal(rows.value.map((r) => Number(r.proceeds) || 0)))
const totalGainLoss = computed(() => calcSubtotal(rows.value.map((r) => gainLoss(r))))

function normalize(raw: any): Row {
  return {
    rowId: raw.rowId ?? `r-${Math.random().toString(36).slice(2, 9)}`,
    assetName: raw.assetName ?? '',
    disposalType: raw.disposalType ?? '',
    carryingFairValue: Number(raw.carryingFairValue) || 0,
    proceeds: Number(raw.proceeds) || 0,
    disposalCost: Number(raw.disposalCost) || 0,
    voucherNo: raw.voucherNo ?? '',
    conclusion: raw.conclusion ?? '',
  }
}

function seed(): void {
  const raw = check.getString('H7-7-fair-rows')
  if (raw) { try { const p = JSON.parse(raw); if (Array.isArray(p)) rows.value = p.map(normalize) } catch { /* ignore */ } }
  auditNote.value = check.getString('H7-7-fair-note')
}
onMounted(seed)

function persist(itemId: string, val: any): void { if (!props.isReadonly) saveResponse(itemId, val) }
function persistRows(): void { persist('H7-7-fair-rows', rows.value) }

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
async function handleAi(): Promise<void> {
  if (!generateAiText) return
  const ctx = `公允价值模式下本期生产性生物资产减少 ${rows.value.length} 项，处置净损益 ${fmtAmt(totalGainLoss.value)}。`
  const text = await generateAiText('h7-disposal-fair', ctx, auditNote.value)
  if (text) { auditNote.value = text; persist('H7-7-fair-note', auditNote.value) }
}
function handleReview(id: string): void { openReviewDialog(id) }
function fmtAmt(v: number | null | undefined): string {
  return v == null ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h7-tab-disposal-fair { padding: 16px; font-size: 13px; }
.audit-goal { margin-bottom: 12px; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.row-tag { margin-left: 8px; }
.summary-row { display: flex; gap: 24px; margin-bottom: 12px; padding: 6px 12px; background: var(--el-fill-color-lighter); border-radius: 4px; }
.text-danger { color: var(--el-color-danger); }
.check-table { font-size: 13px; }
.amount-cell { font-variant-numeric: tabular-nums; }
.calc-cell { font-variant-numeric: tabular-nums; background: var(--el-fill-color-light); border-bottom: 1px dashed var(--el-border-color); cursor: help; display: inline-block; width: 100%; text-align: right; }
.calc-cell.has-loss { color: var(--el-color-danger); font-weight: 600; }
.action-bar { margin: 12px 0; }
.note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
