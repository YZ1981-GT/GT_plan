<template>
  <div class="h7-tab-transfer-review">
    <el-alert type="info" :closable="false" show-icon class="audit-goal">
      <template #title>
        审计目标：审核生物资产在生产性/消耗性/公益性三类之间互转的合规性与会计处理正确性，验证互转按账面价值完整结转（转出 = 转入，差额为 0）（CAS 5《生物资产》第十四条）。
      </template>
    </el-alert>

    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H7-14" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
    </div>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>
            H7-14 互转审核 — {{ rows.length }}项
            <GtIndexChip value="wp:H7-2" />
            <el-tag size="small" type="info" class="row-tag">共 {{ rows.length }} 行</el-tag>
            <el-tag v-if="diffCount > 0" size="small" type="danger" class="row-tag">差额异常 {{ diffCount }}</el-tag>
          </span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="handleReview('H7-14')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <div class="summary-row">
        <span>转出合计：{{ fmtAmt(totalOut) }}</span>
        <span>转入合计：{{ fmtAmt(totalIn) }}</span>
        <span :class="{ 'text-danger': diffCount > 0 }">差额异常（差额 ≠ 0）：{{ diffCount }} 项</span>
      </div>

      <el-table :data="rows" border stripe size="small" class="check-table" max-height="480">
        <el-table-column type="index" label="序" width="46" align="center" fixed />
        <el-table-column prop="assetName" label="资产名称" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetName" size="small" @change="persistRows" />
            <span v-else>{{ row.assetName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="direction" label="互转方向" width="180">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.direction" size="small" @change="persistRows">
              <el-option v-for="d in TRANSFER_DIRECTIONS" :key="d" :label="d" :value="d" />
            </el-select>
            <span v-else>{{ row.direction }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="transferOut" label="转出账面价值" min-width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" v-model="row.transferOut" size="small" @change="persistRows" />
            <span v-else class="amount-cell">{{ fmtAmt(row.transferOut) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="transferIn" label="转入账面价值" min-width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" v-model="row.transferIn" size="small" @change="persistRows" />
            <span v-else class="amount-cell">{{ fmtAmt(row.transferIn) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="互转差额" min-width="110" align="right">
          <template #default="{ row }">
            <span class="calc-cell" :class="{ 'has-diff': diff(row) !== 0 }" title="=转出账面价值-转入账面价值（应为0）">{{ fmtAmt(diff(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="approvalDoc" label="审批依据" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.approvalDoc" size="small" @change="persistRows" />
            <span v-else>{{ row.approvalDoc }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accountingCorrect" label="会计处理正确" width="120" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.accountingCorrect" size="small" style="width:92px" @change="persistRows">
              <el-option label="正确" value="正确" />
              <el-option label="不正确" value="不正确" />
            </el-select>
            <el-tag v-else :type="row.accountingCorrect === '正确' ? 'success' : 'danger'" size="small">{{ row.accountingCorrect || '-' }}</el-tag>
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
        <el-button size="small" @click="handleAddRow">+ 新增互转记录</el-button>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计说明（互转审核）</span>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="记录互转事项的商业实质、审批合规性与会计处理正确性" @blur="persist('H7-14-note', auditNote)" />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计结论</span></div></template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="A、未见异常。B、除上述调整事项外，其余未见异常。C、存在重大未调整事项或范围受限，不可确认。" @blur="persist('H7-14-conclusion', auditConclusion)" />
    </el-card>

    <!-- 产量记录（H7 独有，集成于 H7-14） -->
    <el-divider content-position="left">产量记录</el-divider>
    <H7TabProductionRecord
      :wp-id="props.wpId"
      :project-id="props.projectId"
      :all-responses="props.allResponses"
      :is-readonly="props.isReadonly"
      embedded
    />

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>生物资产可在消耗性 ↔ 生产性 ↔ 公益性三类间互转，互转按账面价值结转，不产生损益。</li>
        <li>互转差额 = 转出账面价值 − 转入账面价值，应恒为 0；差额 ≠ 0 时红色高亮，需核实会计处理。</li>
        <li>互转应有管理层审批依据并具备商业实质，防止通过分类变更规避折旧/减值。</li>
        <li>互转导致的分类变更应联动更新 H7-2 明细表的资产分类。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { ref, computed, inject, onMounted, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import H7TabProductionRecord from '../production/H7TabProductionRecord.vue'
import { useH7TransferReview } from '../../composables/useH7TransferReview'
import { calcTransferDiff } from '../../composables/useH7TransferEngine'
import { calcSubtotal } from '../../composables/useH7FormulaEngine'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly?: boolean }>()
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const allResponsesRef = computed(() => props.allResponses)
const review = useH7TransferReview(allResponsesRef as any, { wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })

const TRANSFER_DIRECTIONS = [
  '生产性→消耗性', '生产性→公益性', '消耗性→生产性',
  '公益性→生产性', '消耗性→公益性', '公益性→消耗性',
]

interface Row {
  rowId: string
  assetName: string
  direction: string
  transferOut: number
  transferIn: number
  approvalDoc: string
  accountingCorrect: string
  conclusion: string
}

const rows = ref<Row[]>([])
const auditNote = ref('')
const auditConclusion = ref('')

function diff(r: Row): number { return calcTransferDiff(Number(r.transferOut) || 0, Number(r.transferIn) || 0) }
const totalOut = computed(() => calcSubtotal(rows.value.map((r) => Number(r.transferOut) || 0)))
const totalIn = computed(() => calcSubtotal(rows.value.map((r) => Number(r.transferIn) || 0)))
const diffCount = computed(() => rows.value.filter((r) => diff(r) !== 0).length)

function normalize(raw: any): Row {
  return {
    rowId: raw.rowId ?? `r-${Math.random().toString(36).slice(2, 9)}`,
    assetName: raw.assetName ?? '',
    direction: raw.direction ?? '',
    transferOut: Number(raw.transferOut) || 0,
    transferIn: Number(raw.transferIn) || 0,
    approvalDoc: raw.approvalDoc ?? '',
    accountingCorrect: raw.accountingCorrect ?? '',
    conclusion: raw.conclusion ?? '',
  }
}

function seed(): void {
  const raw = review.getString('H7-14-rows')
  if (raw) { try { const p = JSON.parse(raw); if (Array.isArray(p)) rows.value = p.map(normalize) } catch { /* ignore */ } }
  auditNote.value = review.getString('H7-14-note')
  auditConclusion.value = review.getString('H7-14-conclusion') || ''
}
onMounted(seed)

function persist(itemId: string, val: any): void { if (!props.isReadonly) saveResponse(itemId, val) }
function persistRows(): void { persist('H7-14-rows', rows.value) }

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入资产名称', '新增互转记录', { confirmButtonText: '确定', cancelButtonText: '取消' })
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
.h7-tab-transfer-review { padding: 16px; font-size: var(--wp-font-size, 13px); }
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
.calc-cell.has-diff { color: var(--el-color-danger); font-weight: 600; }
.action-bar { margin: 12px 0; }
.note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
