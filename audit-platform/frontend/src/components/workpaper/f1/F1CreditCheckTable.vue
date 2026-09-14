<template>
  <el-table
    :data="tableData"
    size="small"
    border
    stripe
    :height="rows.length > 12 ? '380px' : undefined"
    :row-class-name="rowClassName"
  >
    <el-table-column label="供应商名称" width="120" fixed>
      <template #default="{ row }">
        <span v-if="row.rowId === '__subtotal__'" class="subtotal-label">合计</span>
        <el-input
          v-else
          :model-value="row.supplierName"
          size="small"
          :disabled="isReadonly"
          @change="(v: string) => emit('update', row.rowId, 'supplierName', v)"
        />
      </template>
    </el-table-column>
    <el-table-column label="日期" width="100">
      <template #default="{ row }">
        <el-input
          v-if="row.rowId !== '__subtotal__'"
          :model-value="row.date"
          size="small"
          :disabled="isReadonly"
          placeholder="YYYY-MM-DD"
          @change="(v: string) => emit('update', row.rowId, 'date', v)"
        />
      </template>
    </el-table-column>
    <el-table-column label="凭证编号" width="90">
      <template #default="{ row }">
        <el-input
          v-if="row.rowId !== '__subtotal__'"
          :model-value="row.voucherNo"
          size="small"
          :disabled="isReadonly"
          @change="(v: string) => emit('update', row.rowId, 'voucherNo', v)"
        />
      </template>
    </el-table-column>
    <el-table-column label="记账凭证" align="center">
      <el-table-column label="业务内容" width="120">
        <template #default="{ row }">
          <el-input
            v-if="row.rowId !== '__subtotal__'"
            :model-value="row.businessContent"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => emit('update', row.rowId, 'businessContent', v)"
          />
        </template>
      </el-table-column>
      <el-table-column label="对方科目" width="90">
        <template #default="{ row }">
          <el-input
            v-if="row.rowId !== '__subtotal__'"
            :model-value="row.counterAccount"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => emit('update', row.rowId, 'counterAccount', v)"
          />
        </template>
      </el-table-column>
      <el-table-column label="对方明细科目" width="100">
        <template #default="{ row }">
          <el-input
            v-if="row.rowId !== '__subtotal__'"
            :model-value="row.counterDetailAccount"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => emit('update', row.rowId, 'counterDetailAccount', v)"
          />
        </template>
      </el-table-column>
      <el-table-column label="贷方金额" width="100" align="right">
        <template #default="{ row }">
          <span v-if="row.rowId === '__subtotal__'" class="amt subtotal-val">{{ fmtAmount(checkedTotal) }}</span>
          <el-input
            v-else
            :model-value="row.creditAmount"
            size="small"
            :disabled="isReadonly"
            @change="(v: any) => emit('update', row.rowId, 'creditAmount', v)"
          />
        </template>
      </el-table-column>
    </el-table-column>
    <el-table-column label="入库单/签收单" align="center">
      <el-table-column label="日期/编号" width="100">
        <template #default="{ row }">
          <el-input
            v-if="row.rowId !== '__subtotal__'"
            :model-value="row.recvDateNo"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => emit('update', row.rowId, 'recvDateNo', v)"
          />
        </template>
      </el-table-column>
      <el-table-column label="品名" width="90">
        <template #default="{ row }">
          <el-input
            v-if="row.rowId !== '__subtotal__'"
            :model-value="row.recvItemName"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => emit('update', row.rowId, 'recvItemName', v)"
          />
        </template>
      </el-table-column>
      <el-table-column label="单位" width="60">
        <template #default="{ row }">
          <el-input
            v-if="row.rowId !== '__subtotal__'"
            :model-value="row.recvUnit"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => emit('update', row.rowId, 'recvUnit', v)"
          />
        </template>
      </el-table-column>
      <el-table-column label="数量" width="70">
        <template #default="{ row }">
          <el-input
            v-if="row.rowId !== '__subtotal__'"
            :model-value="row.recvQty"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => emit('update', row.rowId, 'recvQty', v)"
          />
        </template>
      </el-table-column>
    </el-table-column>
    <el-table-column label="发票" align="center">
      <el-table-column label="日期/编号" width="100">
        <template #default="{ row }">
          <el-input
            v-if="row.rowId !== '__subtotal__'"
            :model-value="row.invoiceDateNo"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => emit('update', row.rowId, 'invoiceDateNo', v)"
          />
        </template>
      </el-table-column>
      <el-table-column label="对方单位名称" width="110">
        <template #default="{ row }">
          <el-input
            v-if="row.rowId !== '__subtotal__'"
            :model-value="row.invoiceCounterparty"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => emit('update', row.rowId, 'invoiceCounterparty', v)"
          />
        </template>
      </el-table-column>
      <el-table-column label="金额" width="90" align="right">
        <template #default="{ row }">
          <el-input
            v-if="row.rowId !== '__subtotal__'"
            :model-value="row.invoiceAmount"
            size="small"
            :disabled="isReadonly"
            @change="(v: any) => emit('update', row.rowId, 'invoiceAmount', v)"
          />
        </template>
      </el-table-column>
    </el-table-column>
    <el-table-column label="索引号" width="70">
      <template #default="{ row }">
        <el-input
          v-if="row.rowId !== '__subtotal__'"
          :model-value="row.indexRef"
          size="small"
          :disabled="isReadonly"
          @change="(v: string) => emit('update', row.rowId, 'indexRef', v)"
        />
      </template>
    </el-table-column>
    <el-table-column label="是否异常" width="110">
      <template #default="{ row }">
        <el-select
          v-if="row.rowId !== '__subtotal__'"
          :model-value="row.isAbnormal"
          size="small"
          :disabled="isReadonly"
          clearable
          placeholder="—"
          :class="{ 'abnormal-cell': isAbnormalFlag(row.isAbnormal) }"
          @change="(v: string) => emit('update', row.rowId, 'isAbnormal', v || '')"
        >
          <el-option v-for="opt in F1_ABNORMAL_OPTIONS" :key="opt.value || '_empty'" :label="opt.label" :value="opt.value" />
        </el-select>
      </template>
    </el-table-column>
    <el-table-column label="勾稽" width="88" align="center" fixed="right">
      <template #default="{ row }">
        <el-tag
          v-if="row.rowId !== '__subtotal__'"
          size="small"
          :type="creditEvidenceStatus(row).type"
        >{{ creditEvidenceStatus(row).label }}</el-tag>
      </template>
    </el-table-column>
    <el-table-column v-if="!isReadonly" label="OCR" width="56" align="center" fixed="right">
      <template #default="{ row }">
        <el-upload
          v-if="row.rowId !== '__subtotal__'"
          :show-file-list="false"
          accept="image/*,.pdf"
          :disabled="ocrLoadingRowId === row.rowId"
          :before-upload="(file: File) => { emit('ocr', file, row.rowId); return false }"
        >
          <el-button link size="small" :loading="ocrLoadingRowId === row.rowId" title="上传凭证 OCR">📎</el-button>
        </el-upload>
      </template>
    </el-table-column>
    <el-table-column label="操作" :width="isReadonly ? 80 : 130" fixed="right">
      <template #default="{ row }">
        <template v-if="row.rowId !== '__subtotal__'">
          <el-button link type="primary" size="small" @click="emit('open-check', row.rowId)">单据核对</el-button>
          <el-popconfirm v-if="!isReadonly" title="删除？" @confirm="emit('remove', row.rowId)">
            <template #reference><el-button size="small" type="danger" link>删</el-button></template>
          </el-popconfirm>
        </template>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  F1_ABNORMAL_OPTIONS,
  evaluateF1CreditEvidence,
  f1EvidenceStatusLabel,
  isAbnormalFlag,
  type F1CreditCheckRow,
} from '../composables/useF1ComprehensiveCheck'

const props = defineProps<{
  rows: F1CreditCheckRow[]
  checkedTotal: number
  isReadonly: boolean
  ocrLoadingRowId?: string | null
}>()

const emit = defineEmits<{
  update: [rowId: string, field: string, value: any]
  remove: [rowId: string]
  ocr: [file: File, rowId: string]
  'open-check': [rowId: string]
}>()

function creditEvidenceStatus(row: F1CreditCheckRow) {
  return f1EvidenceStatusLabel(evaluateF1CreditEvidence(row))
}

const tableData = computed(() => [
  ...props.rows,
  {
    rowId: '__subtotal__',
    supplierName: '合计',
    date: '',
    voucherNo: '',
    businessContent: '',
    counterAccount: '',
    counterDetailAccount: '',
    creditAmount: 0,
    recvDateNo: '',
    recvItemName: '',
    recvUnit: '',
    recvQty: '',
    invoiceDateNo: '',
    invoiceCounterparty: '',
    invoiceAmount: 0,
    indexRef: '',
    isAbnormal: '',
    remark: '',
  } as F1CreditCheckRow,
])

function rowClassName({ row }: { row: { rowId: string } }) {
  return row.rowId === '__subtotal__' ? 'subtotal-row' : ''
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
</script>

<style scoped>
.subtotal-label { font-weight: 700; }
.subtotal-val { font-weight: 700; }
.amt { text-align: right; display: inline-block; width: 100%; }
.abnormal-cell { color: #f56c6c; }
:deep(.subtotal-row) { background-color: #fafafa !important; font-weight: 600; }
</style>
