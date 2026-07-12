<script setup lang="ts">
/**
 * D2VcMatrixView — 凭证检查表矩阵视图（el-table 17列完整展示）
 *
 * Spec: .kiro/specs/d2-7-voucher-check-enhancement/
 * Task: 7.2
 *
 * 职责：
 * - el-table 17 列完整展示
 * - 每行支持性文件列 📎 附件上传按钮（触发 OCR 流程）
 * - 核对内容 1~5 列可编辑/显示 AI 回填结果
 * - 异常列：el-select filterable allow-create（点选常见异常类型）
 * - 行级 GtReviewDot
 * - 计算列只读（灰底 + tooltip 来源）
 * - 13px 字体，列宽 min-width 自适应
 *
 * Requirements: 1.3, 3.2, 4.1, 4.5
 */
import { ref, toRef } from 'vue'
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

// ─── Abnormal Options ────────────────────────────────────────────────────────

const abnormalOptions = [
  '金额异常',
  '跨期疑点',
  '关联方交易',
  '无凭证',
  '期末集中',
  '对方科目异常',
  '重复记录',
]

// ─── OCR Upload Handling ─────────────────────────────────────────────────────

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
  input.value = '' // reset for re-selection

  if (!currentOcrRowId.value) return

  // Record the file name in supportingDoc
  emit('update-row', currentOcrRowId.value, 'supportingDoc', file.name)

  // Trigger OCR flow via composable
  await uploadAndOcr(currentOcrRowId.value, file)
}

// ─── Cell Update Helper ──────────────────────────────────────────────────────

function onCellChange(rowId: string, field: keyof VoucherCheckRow, value: any) {
  emit('update-row', rowId, field, value)
}
</script>

<template>
  <div class="vc-matrix-view">
    <!-- Hidden file input for OCR uploads -->
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
    >
      <!-- 1. 序号 -->
      <el-table-column
        label="序号"
        prop="seq"
        width="50"
        align="center"
        fixed="left"
      >
        <template #default="{ row }">
          <span class="seq-cell">
            {{ row.seq }}
            <GtReviewDot row-prefix="vc-row" :row-key="row.rowId" />
          </span>
        </template>
      </el-table-column>

      <!-- 2. 客户名称 -->
      <el-table-column label="客户名称" min-width="120">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.customerName"
            size="small"
            placeholder="客户名称"
            @change="(val: string) => onCellChange(row.rowId, 'customerName', val)"
          />
          <span v-else>{{ row.customerName || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 3. 日期 -->
      <el-table-column label="日期" min-width="140">
        <template #default="{ row }">
          <el-date-picker
            v-if="!isReadonly"
            :model-value="row.voucherDate"
            type="date"
            value-format="YYYY-MM-DD"
            size="small"
            placeholder="选择日期"
            style="width: 100%"
            @change="(val: string) => onCellChange(row.rowId, 'voucherDate', val || '')"
          />
          <span v-else>{{ row.voucherDate || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 4. 凭证编号 -->
      <el-table-column label="凭证编号" min-width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.voucherNo"
            size="small"
            placeholder="凭证号"
            @change="(val: string) => onCellChange(row.rowId, 'voucherNo', val)"
          />
          <span v-else>{{ row.voucherNo || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 5. 业务内容 -->
      <el-table-column label="业务内容" min-width="140">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.businessContent"
            size="small"
            placeholder="业务内容"
            @change="(val: string) => onCellChange(row.rowId, 'businessContent', val)"
          />
          <span v-else>{{ row.businessContent || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 6. 对方科目 -->
      <el-table-column label="对方科目" min-width="110">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.counterpartAccount"
            size="small"
            placeholder="对方科目"
            @change="(val: string) => onCellChange(row.rowId, 'counterpartAccount', val)"
          />
          <span v-else>{{ row.counterpartAccount || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 7. 对方明细科目 -->
      <el-table-column label="对方明细科目" min-width="120">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.counterpartDetail"
            size="small"
            placeholder="明细科目"
            @change="(val: string) => onCellChange(row.rowId, 'counterpartDetail', val)"
          />
          <span v-else>{{ row.counterpartDetail || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 8. 借方金额 -->
      <el-table-column label="借方金额" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.debitAmount"
            size="small"
            :controls="false"
            :precision="2"
            :min="0"
            style="width: 100%"
            placeholder="0.00"
            @change="(val: number | undefined) => onCellChange(row.rowId, 'debitAmount', val ?? 0)"
          />
          <span v-else class="amount-cell">{{ row.debitAmount ? row.debitAmount.toFixed(2) : '-' }}</span>
        </template>
      </el-table-column>

      <!-- 9. 贷方金额 -->
      <el-table-column label="贷方金额" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.creditAmount"
            size="small"
            :controls="false"
            :precision="2"
            :min="0"
            style="width: 100%"
            placeholder="0.00"
            @change="(val: number | undefined) => onCellChange(row.rowId, 'creditAmount', val ?? 0)"
          />
          <span v-else class="amount-cell">{{ row.creditAmount ? row.creditAmount.toFixed(2) : '-' }}</span>
        </template>
      </el-table-column>

      <!-- 10. 支持性文件（📎附件上传） -->
      <el-table-column label="支持性文件" min-width="130">
        <template #default="{ row }">
          <div class="supporting-doc-cell">
            <el-button
              v-if="!isReadonly"
              size="small"
              text
              :loading="isProcessing && currentOcrRowId === row.rowId"
              title="上传附件并OCR识别"
              @click="triggerOcrUpload(row.rowId)"
            >📎</el-button>
            <span
              v-if="row.supportingDoc"
              class="doc-name"
              :title="row.supportingDoc"
            >{{ row.supportingDoc }}</span>
            <span v-else-if="isReadonly" class="no-doc">-</span>
          </div>
        </template>
      </el-table-column>

      <!-- 11~15. 核对内容1~5（可编辑 / AI回填） -->
      <el-table-column label="核对内容1" min-width="100">
        <template #header>
          <span title="金额一致性（AI回填）">核对内容1</span>
        </template>
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.check1"
            size="small"
            placeholder="金额核对"
            :class="{ 'ai-backfill': row.check1 && row.ocrResult }"
            @change="(val: string) => onCellChange(row.rowId, 'check1', val)"
          />
          <span v-else :class="{ 'ai-backfill-text': row.check1 && row.ocrResult }">{{ row.check1 || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="核对内容2" min-width="100">
        <template #header>
          <span title="日期一致性（AI回填）">核对内容2</span>
        </template>
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.check2"
            size="small"
            placeholder="日期核对"
            :class="{ 'ai-backfill': row.check2 && row.ocrResult }"
            @change="(val: string) => onCellChange(row.rowId, 'check2', val)"
          />
          <span v-else :class="{ 'ai-backfill-text': row.check2 && row.ocrResult }">{{ row.check2 || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="核对内容3" min-width="100">
        <template #header>
          <span title="对方科目匹配（AI回填）">核对内容3</span>
        </template>
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.check3"
            size="small"
            placeholder="科目核对"
            :class="{ 'ai-backfill': row.check3 && row.ocrResult }"
            @change="(val: string) => onCellChange(row.rowId, 'check3', val)"
          />
          <span v-else :class="{ 'ai-backfill-text': row.check3 && row.ocrResult }">{{ row.check3 || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="核对内容4" min-width="100">
        <template #header>
          <span title="业务内容相符（AI回填）">核对内容4</span>
        </template>
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.check4"
            size="small"
            placeholder="业务核对"
            :class="{ 'ai-backfill': row.check4 && row.ocrResult }"
            @change="(val: string) => onCellChange(row.rowId, 'check4', val)"
          />
          <span v-else :class="{ 'ai-backfill-text': row.check4 && row.ocrResult }">{{ row.check4 || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="核对内容5" min-width="100">
        <template #header>
          <span title="附件完整性（AI回填）">核对内容5</span>
        </template>
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.check5"
            size="small"
            placeholder="附件完整性"
            :class="{ 'ai-backfill': row.check5 && row.ocrResult }"
            @change="(val: string) => onCellChange(row.rowId, 'check5', val)"
          />
          <span v-else :class="{ 'ai-backfill-text': row.check5 && row.ocrResult }">{{ row.check5 || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 16. 是否异常 (el-select filterable allow-create) -->
      <el-table-column label="是否异常" min-width="130">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.isAbnormal"
            filterable
            allow-create
            clearable
            size="small"
            placeholder="正常"
            style="width: 100%"
            @change="(val: string) => onCellChange(row.rowId, 'isAbnormal', val || '')"
          >
            <el-option
              v-for="opt in abnormalOptions"
              :key="opt"
              :label="opt"
              :value="opt"
            />
          </el-select>
          <el-tag
            v-else-if="row.isAbnormal"
            type="danger"
            size="small"
          >{{ row.isAbnormal }}</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>

      <!-- 17. 备注说明 -->
      <el-table-column label="备注说明" min-width="140">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.remark"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            size="small"
            placeholder="备注"
            @change="(val: string) => onCellChange(row.rowId, 'remark', val)"
          />
          <span v-else>{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 操作列（非只读时显示删除按钮） -->
      <el-table-column
        v-if="!isReadonly"
        label=""
        width="40"
        fixed="right"
        align="center"
      >
        <template #default="{ row }">
          <el-button
            type="danger"
            text
            size="small"
            title="删除此行"
            @click="emit('remove-row', row.rowId)"
          >✕</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部新增按钮 -->
    <div v-if="!isReadonly" class="vc-matrix-footer">
      <el-button
        type="primary"
        text
        size="small"
        @click="emit('add-row')"
      >＋ 新增</el-button>
    </div>
  </div>
</template>

<style scoped>
.vc-matrix-view {
  font-size: 13px;
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

.no-doc {
  color: #c0c4cc;
}

/* AI回填高亮样式 */
.ai-backfill :deep(.el-input__inner) {
  background: #f0f9eb;
  border-color: #b3e19d;
}

.ai-backfill-text {
  color: #67c23a;
  font-weight: 500;
}

/* 计算列只读灰底 */
.calc-readonly {
  background: #f5f7fa;
  cursor: help;
  border-bottom: 1px dashed #dcdfe6;
  padding: 2px 4px;
  display: inline-block;
}

.vc-matrix-footer {
  padding: 8px 0;
  text-align: left;
}
</style>
