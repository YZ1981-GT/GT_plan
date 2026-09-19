<script setup lang="ts">
/** F3VoucherCheckTable — F3-7 检查区表格（借方/贷方/日后三区通用，弹窗逐单据核对） */
import { computed, ref, watch, type Ref } from 'vue'
import {
  evaluateF3VoucherEvidence,
  sectionEvidenceKind,
  F3_VOUCHER_SECTION_LABELS,
  type F3VoucherCheckRow,
  type F3VoucherSection,
} from '../composables/useF3VoucherCheck'
import { useF3AiGenerate } from '../composables/useF3AiGenerate'

const SCROLL_THRESHOLD = 50
const TABLE_MAX_HEIGHT = 480

const props = defineProps<{
  section: F3VoucherSection
  rows: F3VoucherCheckRow[]
  isReadonly: boolean
  wpId?: string
  projectId?: string
  allResponses?: Map<string, any>
}>()

const emit = defineEmits<{
  (e: 'update-cell', rowId: string, field: string, value: unknown): void
  (e: 'remove-row', rowId: string): void
  (e: 'open-check', rowId: string): void
}>()

const useScroll = computed(() => props.rows.length > SCROLL_THRESHOLD)
const sectionLabel = computed(() => F3_VOUCHER_SECTION_LABELS[props.section])
const evidenceKind = computed(() => sectionEvidenceKind(props.section))
const amountLabel = computed(() => (props.section === 'credit' ? '贷方金额' : '借方金额'))
const evidenceLabel = computed(() =>
  evidenceKind.value === 'payment' ? '付款审批单 + 银行回单' : '入库单/验收单 + 采购发票',
)

function fmt(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function onUpdate(field: string, rowId: string, value: unknown): void {
  emit('update-cell', rowId, field, value)
}

function evidenceStatus(row: F3VoucherCheckRow): { type: 'success' | 'warning' | 'danger'; label: string } {
  const checks = evaluateF3VoucherEvidence(row, evidenceKind.value)
  if (checks.some((item) => item.status === 'mismatch')) return { type: 'danger', label: '勾稽不符' }
  if (checks.some((item) => item.status === 'missing')) return { type: 'warning', label: '单据待补' }
  return { type: 'success', label: '勾稽完成' }
}

function summaryMethod({ columns }: { columns: any[] }) {
  return columns.map((column, index) => {
    if (index === 0) return '合计'
    if (column.property === 'amount') {
      return fmt(props.rows.reduce((sum, row) => sum + (row.amount || 0), 0))
    }
    if (column.property === 'bankAmount' && evidenceKind.value === 'payment') {
      return fmt(props.rows.reduce((sum, row) => sum + (row.bankAmount || 0), 0))
    }
    if (column.property === 'invoiceAmount' && evidenceKind.value === 'purchase') {
      return fmt(props.rows.reduce((sum, row) => sum + (row.invoiceAmount || 0), 0))
    }
    return ''
  })
}

// ─── 分区审计说明（F3 约定：写入 allResponses + f3:save-items 事件持久化） ───
const NOTE_KEY = computed(() => `F3-7-${props.section}-check-note`)
const auditNote = ref('')
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  const item = { item_id: NOTE_KEY.value, conclusion: null, remark: val }
  props.allResponses?.set(NOTE_KEY.value, item)
  window.dispatchEvent(new CustomEvent('f3:save-items', { detail: { items: [item] } }))
}
watch(
  () => props.allResponses?.get(NOTE_KEY.value)?.remark,
  (v) => { if (typeof v === 'string') auditNote.value = v },
  { immediate: true },
)

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF3AiGenerate(
  computed(() => props.wpId || '') as Ref<string>,
)

async function generateNoteAi(): Promise<void> {
  if (props.isReadonly) return
  const abnormalRows = props.rows.filter((row) => row.isAbnormal === '是')
  const generated = await generateAndConfirm(
    'voucher-check-note',
    auditNote.value,
    {
      section: sectionLabel.value,
      evidence: evidenceLabel.value,
      sampleCount: props.rows.filter((row) => row.voucherNo || row.amount).length,
      totalAmount: props.rows.reduce((sum, row) => sum + (row.amount || 0), 0),
      abnormalCount: abnormalRows.length,
      abnormalRows: abnormalRows.map((row) => ({
        voucherNo: row.voucherNo,
        amount: row.amount,
        issueDesc: row.issueDesc,
      })),
      evidenceStatus: props.rows.map((row) => ({
        voucherNo: row.voucherNo,
        status: evidenceStatus(row).label,
      })),
    },
    `AI 生成 · ${sectionLabel.value} 审计说明`,
  )
  if (generated) saveAuditNote(generated)
}
</script>

<template>
  <div class="f3-voucher-table-wrap">
    <div v-if="useScroll" class="scroll-hint">共 {{ rows.length }} 行 · 固定表头滚动</div>
    <el-table
      :data="rows"
      border
      size="small"
      show-summary
      :summary-method="summaryMethod"
      :max-height="useScroll ? TABLE_MAX_HEIGHT : undefined"
    >
      <el-table-column prop="seq" label="序号" width="50" fixed align="center" />
      <el-table-column prop="voucherDate" label="日期" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.voucherDate" size="small" placeholder="YYYY-MM-DD"
            @change="(v: string) => onUpdate('voucherDate', row.rowId, v)" />
          <span v-else>{{ row.voucherDate }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="voucherNo" label="凭证编号" width="110">
        <template #default="{ row }">
          <el-tooltip v-if="row.sampleSource" :content="`来自${row.sampleSource}`" placement="top">
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small"
              @change="(v: string) => onUpdate('voucherNo', row.rowId, v)" />
            <span v-else>{{ row.voucherNo }}</span>
          </el-tooltip>
          <template v-else>
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small"
              @change="(v: string) => onUpdate('voucherNo', row.rowId, v)" />
            <span v-else>{{ row.voucherNo }}</span>
          </template>
        </template>
      </el-table-column>
      <el-table-column prop="businessContent" label="业务内容" min-width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.businessContent" size="small"
            @change="(v: string) => onUpdate('businessContent', row.rowId, v)" />
          <span v-else>{{ row.businessContent }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="counterAccount" label="对方科目" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.counterAccount" size="small"
            @change="(v: string) => onUpdate('counterAccount', row.rowId, v)" />
          <span v-else>{{ row.counterAccount }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="detailAccount" label="明细科目" width="105">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.detailAccount" size="small"
            @change="(v: string) => onUpdate('detailAccount', row.rowId, v)" />
          <span v-else>{{ row.detailAccount }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="amount" :label="amountLabel" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.amount" :controls="false" size="small" style="width:100%"
            @change="(v: number | undefined) => onUpdate('amount', row.rowId, v ?? 0)" />
          <span v-else>{{ fmt(row.amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="noteType" label="票据类别" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.noteType" size="small"
            @change="(v: string) => onUpdate('noteType', row.rowId, v)" />
          <span v-else>{{ row.noteType }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="evidenceLabel" width="150" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="evidenceStatus(row).type">{{ evidenceStatus(row).label }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="indexNo" label="索引号" width="95">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.indexNo" size="small"
            @change="(v: string) => onUpdate('indexNo', row.rowId, v)" />
          <span v-else>{{ row.indexNo }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="isAbnormal" label="是否异常" width="95" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.isAbnormal" size="small" clearable
            @change="(v: string) => onUpdate('isAbnormal', row.rowId, v ?? '')">
            <el-option label="否" value="否" />
            <el-option label="是" value="是" />
          </el-select>
          <el-tag v-else-if="row.isAbnormal" size="small" :type="row.isAbnormal === '是' ? 'danger' : 'success'">
            {{ row.isAbnormal }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="emit('open-check', row.rowId)">单据核对</el-button>
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="emit('remove-row', row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分区审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>本区审计说明</span>
          <el-button size="small" type="primary" plain
            :disabled="isReadonly || !aiAvailable" :loading="aiLoading"
            @click="generateNoteAi">🤖 AI 生成说明</el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :placeholder="`填写本区（${sectionLabel}）审计说明：单据核对情况、异常凭证及处理、追加程序说明。`"
        @change="(v: string) => saveAuditNote(v)"
      />
    </el-card>
  </div>
</template>

<style scoped>
.f3-voucher-table-wrap { margin-bottom: 8px; }
.f3-voucher-table-wrap :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.f3-voucher-table-wrap :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}
.f3-voucher-table-wrap :deep(.el-table__footer .cell) { font-weight: 700; }
.scroll-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
  text-align: right;
}
.audit-note-card { margin-top: 12px; }
.audit-note-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}
</style>
