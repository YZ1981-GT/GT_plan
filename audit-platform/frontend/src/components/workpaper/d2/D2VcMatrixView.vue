<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
/**
 * D2VcMatrixView — 凭证检查表矩阵视图（固定列 + 列设置器）
 *
 * 改进：左侧固定基础信息列（序号/凭证号/日期/借方/贷方），
 * 右侧按分组可控显示（核对/证据/备注），默认隐藏空列。
 * 列设置 popover 控制可见性。
 *
 * Spec: .kiro/specs/d2-7-voucher-check-enhancement/
 * Task: 7.2 (改进)
 */
import { ref, computed, toRef } from 'vue'
import type { VoucherCheckRow } from '../composables/useD2VoucherCheckEnhanced'
import { useD2VcOcrCheck } from '../composables/useD2VcOcrCheck'
import GtReviewDot from '../GtReviewDot.vue'

const props = defineProps<{
  rows: VoucherCheckRow[]
  isReadonly: boolean
  wpId: string
  projectId: string
}>()

const emit = defineEmits<{
  (e: 'update-row', rowId: string, field: keyof VoucherCheckRow, value: any): void
  (e: 'add-row'): void
  (e: 'remove-row', rowId: string): void
}>()

// ─── OCR Composable ──────────────────────────────────────────────────────────

const wpIdRef = toRef(props, 'wpId')

const { isProcessing, uploadAndOcr } = useD2VcOcrCheck({
  wpId: wpIdRef,
  getRow: (rowId: string) => props.rows.find(r => r.rowId === rowId),
  updateRow: (rowId: string, field: keyof VoucherCheckRow, value: any) => {
    emit('update-row', rowId, field, value)
  },
})

// ─── Column Visibility (列设置) ─────────────────────────────────────────────

interface ColGroup {
  key: string
  label: string
  visible: boolean
  columns: string[]
}

const columnGroups = ref<ColGroup[]>([
  { key: 'basic', label: '基础信息', visible: false, columns: ['customerName', 'businessContent'] },
  { key: 'account', label: '科目信息', visible: false, columns: ['counterpartAccount', 'counterpartDetail'] },
  { key: 'check', label: '核对结果', visible: true, columns: ['check1', 'check2', 'check3', 'check4', 'check5'] },
  { key: 'evidence', label: '证据附件', visible: true, columns: ['supportingDoc'] },
  { key: 'result', label: '检查结论', visible: true, columns: ['isAbnormal', 'remark'] },
])

const showColumnSettings = ref(false)

// 默认隐藏空列组：如果某列组所有行数据全空，自动折叠
const autoHideEmptyGroups = computed(() => {
  const groups = columnGroups.value
  return groups.map(g => {
    if (g.key === 'basic' || g.key === 'check' || g.key === 'result') return g // 这些组始终按用户设置
    // 科目信息组：如果所有行的科目都为空，自动隐藏
    const hasData = g.columns.some(col =>
      props.rows.some(row => {
        const val = (row as any)[col]
        return val != null && val !== '' && val !== 0
      })
    )
    return { ...g, visible: g.visible && (hasData || props.rows.length === 0) }
  })
})

function isColVisible(colKey: string): boolean {
  return autoHideEmptyGroups.value.some(g => g.visible && g.columns.includes(colKey))
}

// ─── Abnormal Options ────────────────────────────────────────────────────────

const abnormalOptions = [
  '金额异常', '跨期疑点', '关联方交易', '无凭证', '期末集中', '对方科目异常', '重复记录',
]

// ─── OCR Upload ──────────────────────────────────────────────────────────────

const ocrFileInput = ref<HTMLInputElement | null>(null)
const currentOcrRowId = ref('')

function triggerOcrUpload(rowId: string) {
  if (props.isReadonly) return
  currentOcrRowId.value = rowId
  ocrFileInput.value?.click()
}

async function handleOcrFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = ''
  if (!currentOcrRowId.value) return
  emit('update-row', currentOcrRowId.value, 'supportingDoc', file.name)
  await uploadAndOcr(currentOcrRowId.value, file)
}

// ─── Cell Update ─────────────────────────────────────────────────────────────

function onCellChange(rowId: string, field: keyof VoucherCheckRow, value: any) {
  emit('update-row', rowId, field, value)
}
</script>

<template>
  <div class="vc-matrix-view">
    <!-- 列设置工具栏 -->
    <div class="vc-matrix-toolbar">
      <span class="row-count-tag">共 {{ rows.length }} 行</span>
      <el-popover
        v-model:visible="showColumnSettings"
        placement="bottom-end"
        :width="220"
        trigger="click"
      >
        <template #reference>
          <el-button size="small" text title="列设置">⚙ 列设置</el-button>
        </template>
        <div class="col-settings-panel">
          <div class="col-settings-title">显示列组</div>
          <el-checkbox
            v-for="group in columnGroups"
            :key="group.key"
            v-model="group.visible"
            :label="group.label"
            style="display: block; margin: 4px 0"
          />
        </div>
      </el-popover>
    </div>

    <!-- Hidden file input for OCR -->
    <input
      ref="ocrFileInput"
      type="file"
      accept=".pdf,.png,.jpg,.jpeg,.tiff,.bmp"
      style="display: none"
      @change="handleOcrFileChange"
    />

    <el-table
      :data="rows"
      border
      stripe
      size="small"
      class="vc-matrix-table"
      :header-cell-style="{ fontSize: '13px', background: '#f5f7fa' }"
      :cell-style="{ fontSize: '13px' }"
      max-height="500"
    >
      <!-- ═══ 固定列：序号 + 凭证号 + 日期 + 借方 + 贷方 ═══ -->
      <el-table-column label="序号" prop="seq" width="50" align="center" fixed="left">
        <template #default="{ row }">
          <span class="seq-cell">
            {{ row.seq }}
            <GtReviewDot row-prefix="vc-row" :row-key="row.rowId" />
          </span>
        </template>
      </el-table-column>

      <el-table-column label="凭证编号" width="110" fixed="left">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" placeholder="凭证号" @change="(val: string) => onCellChange(row.rowId, 'voucherNo', val)" />
          <span v-else>{{ row.voucherNo || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="日期" width="120" fixed="left">
        <template #default="{ row }">
          <el-date-picker v-if="!isReadonly" :model-value="row.voucherDate" type="date" value-format="YYYY-MM-DD" size="small" placeholder="日期" style="width: 100%" @change="(val: string) => onCellChange(row.rowId, 'voucherDate', val || '')" />
          <span v-else>{{ row.voucherDate || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="借方" width="100" align="right" fixed="left">
        <template #default="{ row }">
          <WpAmountInput v-if="!isReadonly" :model-value="row.debitAmount" size="small" style="width: 100%" @change="(val: number | undefined) => onCellChange(row.rowId, 'debitAmount', val ?? 0)" />
          <span v-else class="amount-cell">{{ row.debitAmount ? row.debitAmount.toFixed(2) : '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="贷方" width="100" align="right" fixed="left">
        <template #default="{ row }">
          <WpAmountInput v-if="!isReadonly" :model-value="row.creditAmount" size="small" style="width: 100%" @change="(val: number | undefined) => onCellChange(row.rowId, 'creditAmount', val ?? 0)" />
          <span v-else class="amount-cell">{{ row.creditAmount ? row.creditAmount.toFixed(2) : '-' }}</span>
        </template>
      </el-table-column>

      <!-- ═══ 基础信息组（可折叠） ═══ -->
      <el-table-column v-if="isColVisible('customerName')" label="客户名称" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.customerName" size="small" placeholder="客户" @change="(val: string) => onCellChange(row.rowId, 'customerName', val)" />
          <span v-else>{{ row.customerName || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="isColVisible('businessContent')" label="业务内容" width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.businessContent" size="small" placeholder="业务内容" @change="(val: string) => onCellChange(row.rowId, 'businessContent', val)" />
          <span v-else>{{ row.businessContent || '-' }}</span>
        </template>
      </el-table-column>

      <!-- ═══ 科目信息组（默认折叠，有数据时显示） ═══ -->
      <el-table-column v-if="isColVisible('counterpartAccount')" label="对方科目" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.counterpartAccount" size="small" placeholder="科目" @change="(val: string) => onCellChange(row.rowId, 'counterpartAccount', val)" />
          <span v-else>{{ row.counterpartAccount || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="isColVisible('counterpartDetail')" label="明细科目" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.counterpartDetail" size="small" placeholder="明细" @change="(val: string) => onCellChange(row.rowId, 'counterpartDetail', val)" />
          <span v-else>{{ row.counterpartDetail || '-' }}</span>
        </template>
      </el-table-column>

      <!-- ═══ 核对结果组（5列） ═══ -->
      <el-table-column v-if="isColVisible('check1')" label="金额" width="70">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.check1" size="small" placeholder="-" :class="{ 'ai-backfill': row.check1 && row.ocrResult }" @change="(val: string) => onCellChange(row.rowId, 'check1', val)" />
          <span v-else :class="{ 'ai-text': row.ocrResult }">{{ row.check1 || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="isColVisible('check2')" label="日期" width="70">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.check2" size="small" placeholder="-" :class="{ 'ai-backfill': row.check2 && row.ocrResult }" @change="(val: string) => onCellChange(row.rowId, 'check2', val)" />
          <span v-else :class="{ 'ai-text': row.ocrResult }">{{ row.check2 || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="isColVisible('check3')" label="科目" width="70">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.check3" size="small" placeholder="-" :class="{ 'ai-backfill': row.check3 && row.ocrResult }" @change="(val: string) => onCellChange(row.rowId, 'check3', val)" />
          <span v-else :class="{ 'ai-text': row.ocrResult }">{{ row.check3 || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="isColVisible('check4')" label="业务" width="70">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.check4" size="small" placeholder="-" :class="{ 'ai-backfill': row.check4 && row.ocrResult }" @change="(val: string) => onCellChange(row.rowId, 'check4', val)" />
          <span v-else :class="{ 'ai-text': row.ocrResult }">{{ row.check4 || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="isColVisible('check5')" label="附件" width="70">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.check5" size="small" placeholder="-" :class="{ 'ai-backfill': row.check5 && row.ocrResult }" @change="(val: string) => onCellChange(row.rowId, 'check5', val)" />
          <span v-else :class="{ 'ai-text': row.ocrResult }">{{ row.check5 || '-' }}</span>
        </template>
      </el-table-column>

      <!-- ═══ 证据附件组 ═══ -->
      <el-table-column v-if="isColVisible('supportingDoc')" label="📎 附件" width="100">
        <template #default="{ row }">
          <div class="supporting-doc-cell">
            <el-button v-if="!isReadonly" size="small" text :loading="isProcessing && currentOcrRowId === row.rowId" title="上传附件并OCR识别" @click="triggerOcrUpload(row.rowId)">📎</el-button>
            <span v-if="row.supportingDoc" class="doc-name" :title="row.supportingDoc">{{ row.supportingDoc }}</span>
            <span v-else-if="isReadonly">-</span>
          </div>
        </template>
      </el-table-column>

      <!-- ═══ 检查结论组 ═══ -->
      <el-table-column v-if="isColVisible('isAbnormal')" label="异常" width="110">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.isAbnormal" filterable allow-create clearable size="small" placeholder="正常" style="width: 100%" @change="(val: string) => onCellChange(row.rowId, 'isAbnormal', val || '')">
            <el-option v-for="opt in abnormalOptions" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <el-tag v-else-if="row.isAbnormal" type="danger" size="small">{{ row.isAbnormal }}</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>

      <el-table-column v-if="isColVisible('remark')" label="备注" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.remark" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" size="small" placeholder="备注" @change="(val: string) => onCellChange(row.rowId, 'remark', val)" />
          <span v-else>{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>

      <!-- ═══ 操作列（固定右侧） ═══ -->
      <el-table-column v-if="!isReadonly" label="" width="40" fixed="right" align="center">
        <template #default="{ row }">
          <el-button type="danger" text size="small" title="删除" @click="emit('remove-row', row.rowId)">✕</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部新增按钮 -->
    <div v-if="!isReadonly" class="vc-matrix-footer">
      <el-button type="primary" text size="small" @click="emit('add-row')">＋ 新增</el-button>
    </div>
  </div>
</template>

<style scoped>
.vc-matrix-view {
  font-size: 13px;
}

.vc-matrix-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.row-count-tag {
  font-size: 12px;
  color: #909399;
}

.col-settings-panel {
  padding: 4px 0;
}

.col-settings-title {
  font-weight: 500;
  font-size: 13px;
  margin-bottom: 6px;
  color: #303133;
}

.vc-matrix-table {
  width: 100%;
}

.vc-matrix-table :deep(.el-table__cell) {
  padding: 4px 6px;
}

.vc-matrix-table :deep(.el-input__inner),
.vc-matrix-table :deep(.el-textarea__inner) {
  font-size: 13px;
}

.vc-matrix-table :deep(.el-input-number .el-input__inner) {
  text-align: right;
}

.seq-cell {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-weight: 500;
  color: #606266;
}

.amount-cell {
  font-variant-numeric: tabular-nums;
  text-align: right;
  display: block;
}

.supporting-doc-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}

.doc-name {
  font-size: 12px;
  color: #409eff;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 80px;
}

.ai-backfill :deep(.el-input__inner) {
  background: #f0f9eb;
  border-color: #b3e19d;
}

.ai-text {
  color: #67c23a;
  font-weight: 500;
}

.vc-matrix-footer {
  padding: 8px 0;
  text-align: left;
}
</style>
