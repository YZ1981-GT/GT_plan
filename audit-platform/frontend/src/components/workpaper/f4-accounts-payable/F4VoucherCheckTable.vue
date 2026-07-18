<script setup lang="ts">
/** F4VoucherCheckTable — F4-8 借/贷检查区表格（弹窗逐单据核对） */
import { computed, ref, watch, type Ref } from 'vue'
import {
  evaluateF4VoucherEvidence,
  sectionEvidenceKind,
  F4_VOUCHER_SECTION_LABELS,
  type F4VoucherCheckRow,
  type F4VoucherSection,
} from '../composables/useF4VoucherCheck'
import { useF4AiGenerate } from '../composables/useF4AiGenerate'
import F4ImportExportToolbar from './F4ImportExportToolbar.vue'
import type { F4ImportableSheet } from '../composables/useF4ImportExport'

const SCROLL_THRESHOLD = 50
const TABLE_MAX_HEIGHT = 480

const props = defineProps<{
  section: F4VoucherSection
  rows: F4VoucherCheckRow[]
  isReadonly: boolean
  wpId: string
  projectId: string
  allResponses?: Map<string, any>
}>()

const emit = defineEmits<{
  (e: 'update-cell', rowId: string, field: string, value: unknown): void
  (e: 'remove-row', rowId: string): void
  (e: 'add-row'): void
  (e: 'open-check', rowId: string): void
  (e: 'imported'): void
}>()

const useScroll = computed(() => props.rows.length > SCROLL_THRESHOLD)
const sectionLabel = computed(() => F4_VOUCHER_SECTION_LABELS[props.section])
const evidenceKind = computed(() => sectionEvidenceKind(props.section))
const amountLabel = computed(() => (props.section === 'credit' ? '贷方金额' : '借方金额'))
const evidenceLabel = computed(() =>
  evidenceKind.value === 'payment' ? '付款审批单 + 银行回单' : '入库单/验收单 + 采购发票',
)
const sheet = computed<F4ImportableSheet>(() =>
  props.section === 'debit' ? 'F4-8-debit' : 'F4-8-credit',
)

function fmt(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function evidenceStatus(row: F4VoucherCheckRow): { type: 'success' | 'warning' | 'danger'; label: string } {
  const checks = evaluateF4VoucherEvidence(row, evidenceKind.value)
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

const NOTE_KEY = computed(() => `F4-8-${props.section}-check-note`)
const sectionNote = ref('')
function saveSectionNote(val: string): void {
  if (props.isReadonly) return
  sectionNote.value = val
  const item = { item_id: NOTE_KEY.value, conclusion: null, remark: val }
  props.allResponses?.set(NOTE_KEY.value, item)
  window.dispatchEvent(new CustomEvent('f4:save-items', { detail: { items: [item] } }))
}
watch(
  () => props.allResponses?.get(NOTE_KEY.value)?.remark,
  (v) => { if (typeof v === 'string') sectionNote.value = v },
  { immediate: true },
)

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF4AiGenerate(
  computed(() => props.wpId) as Ref<string>,
)

async function generateSectionNoteAi(): Promise<void> {
  if (props.isReadonly) return
  const abnormalRows = props.rows.filter((row) => row.isAbnormal === '是')
  const generated = await generateAndConfirm(
    'voucher-check-note',
    sectionNote.value,
    {
      section: sectionLabel.value,
      evidence: evidenceLabel.value,
      sampleCount: props.rows.filter((row) => row.voucherNo || row.amount).length,
      totalAmount: props.rows.reduce((sum, row) => sum + (row.amount || 0), 0),
      abnormalCount: abnormalRows.length,
      abnormalRows: abnormalRows.map((row) => ({
        supplierName: row.supplierName,
        voucherNo: row.voucherNo,
        amount: row.amount,
        issueDesc: row.issueDesc,
      })),
      evidenceStatus: props.rows.map((row) => ({
        voucherNo: row.voucherNo,
        status: evidenceStatus(row).label,
      })),
    },
    `AI 生成 · ${sectionLabel.value} 分区说明`,
  )
  if (generated) saveSectionNote(generated)
}
</script>

<template>
  <div class="f4-voucher-table-wrap">
    <div class="section-heading">
      <div>
        <h3>{{ sectionLabel }}</h3>
        <p>逐笔核对：记账凭证 ↔ {{ evidenceLabel }}。点击「单据核对」打开弹窗分单据上传识别。</p>
      </div>
      <div class="section-actions">
        <F4ImportExportToolbar
          :wp-id="wpId"
          :project-id="projectId"
          :sheet="sheet"
          :disabled="isReadonly"
          @imported="emit('imported')"
        />
        <el-button size="small" :disabled="isReadonly" @click="emit('add-row')">+ 新增行</el-button>
      </div>
    </div>

    <div v-if="useScroll" class="scroll-hint">共 {{ rows.length }} 行 · 固定表头滚动</div>
    <div class="table-scroll-wrap">
      <el-table
        :data="rows"
        border
        size="small"
        show-summary
        :summary-method="summaryMethod"
        :max-height="useScroll ? TABLE_MAX_HEIGHT : undefined"
        class="voucher-table"
      >
        <el-table-column type="index" label="序号" width="58" fixed="left" />
        <el-table-column label="供应商名称" min-width="140" fixed="left">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.supplierName"
              size="small"
              @change="(v: string) => emit('update-cell', row.rowId, 'supplierName', v)"
            />
            <span v-else>{{ row.supplierName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证日期" width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.voucherDate"
              size="small"
              placeholder="YYYY-MM-DD"
              @change="(v: string) => emit('update-cell', row.rowId, 'voucherDate', v)"
            />
            <span v-else>{{ row.voucherDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证编号" width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.voucherNo"
              size="small"
              @change="(v: string) => emit('update-cell', row.rowId, 'voucherNo', v)"
            />
            <span v-else>{{ row.voucherNo }}</span>
          </template>
        </el-table-column>
        <el-table-column label="业务内容" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.businessContent"
              size="small"
              @change="(v: string) => emit('update-cell', row.rowId, 'businessContent', v)"
            />
            <span v-else>{{ row.businessContent }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对方科目" width="110">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.counterAccount"
              size="small"
              @change="(v: string) => emit('update-cell', row.rowId, 'counterAccount', v)"
            />
            <span v-else>{{ row.counterAccount }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="amount" :label="amountLabel" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.amount"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => emit('update-cell', row.rowId, 'amount', v ?? 0)"
            />
            <span v-else>{{ fmt(row.amount) }}</span>
          </template>
        </el-table-column>

        <template v-if="evidenceKind === 'payment'">
          <el-table-column label="审批单日期/编号" width="140">
            <template #default="{ row }">{{ row.approvalDateNo || '—' }}</template>
          </el-table-column>
          <el-table-column label="是否恰当审批" width="110" align="center">
            <template #default="{ row }">
              <el-tag
                v-if="row.approvalProper"
                size="small"
                :type="row.approvalProper === '否' ? 'danger' : 'success'"
              >{{ row.approvalProper }}</el-tag>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column prop="bankAmount" label="银行回单金额" width="120" align="right">
            <template #default="{ row }">{{ fmt(row.bankAmount) }}</template>
          </el-table-column>
        </template>
        <template v-else>
          <el-table-column label="入库单日期/编号" width="140">
            <template #default="{ row }">{{ row.receiptDateNo || '—' }}</template>
          </el-table-column>
          <el-table-column label="品名" width="110">
            <template #default="{ row }">{{ row.receiptProduct || '—' }}</template>
          </el-table-column>
          <el-table-column prop="invoiceAmount" label="发票金额" width="120" align="right">
            <template #default="{ row }">{{ fmt(row.invoiceAmount) }}</template>
          </el-table-column>
        </template>

        <el-table-column label="索引号" width="100">
          <template #default="{ row }">{{ row.indexNo || '—' }}</template>
        </el-table-column>
        <el-table-column label="是否异常" width="90" align="center">
          <template #default="{ row }">
            <el-tag
              v-if="row.isAbnormal"
              size="small"
              :type="row.isAbnormal === '是' ? 'danger' : 'success'"
            >{{ row.isAbnormal }}</el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="勾稽状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="evidenceStatus(row).type">{{ evidenceStatus(row).label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="145" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="emit('open-check', row.rowId)">单据核对</el-button>
            <el-button
              link
              type="danger"
              size="small"
              :disabled="isReadonly"
              @click="emit('remove-row', row.rowId)"
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-card shadow="never" class="section-note-card">
      <template #header>
        <div class="note-header">
          <span>本区审计说明</span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="generateSectionNoteAi"
          >🤖 AI生成</el-button>
        </div>
      </template>
      <el-input
        :model-value="sectionNote"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        :placeholder="`说明${sectionLabel}的样本选取、单据勾稽及异常处理`"
        @change="saveSectionNote"
      />
    </el-card>
  </div>
</template>

<style scoped>
.f4-voucher-table-wrap { margin-bottom: 20px; }
.section-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 8px;
}
.section-heading h3 { margin: 0; font-size: 14px; color: #263a52; }
.section-heading p { margin: 4px 0 0; color: #7a8491; font-size: 12px; }
.section-actions { display: flex; align-items: center; gap: 8px; }
.scroll-hint { margin-bottom: 4px; color: #909399; font-size: 12px; }
.table-scroll-wrap { width: 100%; overflow-x: auto; }
.voucher-table { min-width: 1400px; }
.voucher-table :deep(.el-input-number) { width: 100%; }
.section-note-card { margin-top: 10px; border-radius: 6px; }
.section-note-card :deep(.el-card__header) { padding: 10px 12px; background: #fafafa; }
.note-header { display: flex; align-items: center; justify-content: space-between; }
</style>
