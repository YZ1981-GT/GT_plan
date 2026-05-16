<script setup lang="ts">
/**
 * OCR 识别结果展示面板
 * Sprint 7 Task 7.3: 识别结果展示 + 置信度标记 + 批量修正
 */
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'

interface VoucherEntry {
  account_code: string
  account_name: string
  amount: string
}

interface VoucherRow {
  id: string
  voucher_no: string
  voucher_date: string | null
  summary: string
  debit_entries: VoucherEntry[]
  credit_entries: VoucherEntry[]
  preparer: string
  reviewer: string
  confidence: number
  attachment_id: string | null
  source: string
}

const props = defineProps<{
  results: VoucherRow[]
}>()

const emit = defineEmits<{
  (e: 'confirm', row: VoucherRow): void
  (e: 'edit', row: VoucherRow): void
  (e: 'reject', rowId: string): void
  (e: 'batch-confirm'): void
}>()

const editingId = ref<string | null>(null)
const editForm = ref<Partial<VoucherRow>>({})

const highConfidence = computed(() =>
  props.results.filter(r => r.confidence >= 0.8)
)
const lowConfidence = computed(() =>
  props.results.filter(r => r.confidence < 0.8)
)

function getConfidenceType(conf: number): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  if (conf >= 0.8) return 'success'
  if (conf >= 0.5) return 'warning'
  return 'danger'
}

function startEdit(row: VoucherRow) {
  editingId.value = row.id
  editForm.value = { ...row }
}

function saveEdit() {
  if (editingId.value && editForm.value) {
    emit('edit', editForm.value as VoucherRow)
    editingId.value = null
  }
}

function cancelEdit() {
  editingId.value = null
  editForm.value = {}
}

function batchConfirmAll() {
  if (highConfidence.value.length === 0) {
    ElMessage.warning('没有高置信度结果可确认')
    return
  }
  emit('batch-confirm')
}
</script>

<template>
  <div class="ocr-result-panel">
    <div class="panel-header">
      <h4>OCR 识别结果</h4>
      <div class="actions">
        <el-badge :value="highConfidence.length" type="success">
          <el-button size="small" type="primary" @click="batchConfirmAll">
            批量确认高置信度
          </el-button>
        </el-badge>
      </div>
    </div>

    <el-table :data="results" size="small" stripe border max-height="400">
      <el-table-column label="置信度" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="getConfidenceType(row.confidence) || undefined" size="small">
            {{ (row.confidence * 100).toFixed(0) }}%
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="凭证号" prop="voucher_no" width="100" />
      <el-table-column label="日期" prop="voucher_date" width="110" />
      <el-table-column label="摘要" prop="summary" min-width="150" show-overflow-tooltip />

      <el-table-column label="借方" min-width="140">
        <template #default="{ row }">
          <div v-for="(e, i) in row.debit_entries" :key="i" class="entry-line">
            <span class="acct">{{ e.account_name || e.account_code }}</span>
            <span class="amt gt-amt">{{ e.amount }}</span>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="贷方" min-width="140">
        <template #default="{ row }">
          <div v-for="(e, i) in row.credit_entries" :key="i" class="entry-line">
            <span class="acct">{{ e.account_name || e.account_code }}</span>
            <span class="amt gt-amt">{{ e.amount }}</span>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button-group size="small">
            <el-button type="success" @click="emit('confirm', row)">确认</el-button>
            <el-button type="warning" @click="startEdit(row)">修改</el-button>
            <el-button type="danger" @click="emit('reject', row.id)">拒绝</el-button>
          </el-button-group>
        </template>
      </el-table-column>
    </el-table>

    <!-- 编辑弹窗 -->
    <el-dialog :model-value="!!editingId" title="修正 OCR 结果" width="500px" @close="cancelEdit">
      <el-form v-if="editForm" label-width="80px" size="small">
        <el-form-item label="凭证号">
          <el-input v-model="editForm.voucher_no" />
        </el-form-item>
        <el-form-item label="日期">
          <el-input v-model="editForm.voucher_date" placeholder="YYYY-MM-DD" />
        </el-form-item>
        <el-form-item label="摘要">
          <el-input v-model="editForm.summary" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cancelEdit">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.ocr-result-panel {
  padding: 12px;
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.panel-header h4 {
  margin: 0;
  font-size: var(--gt-font-size-sm);
}
.entry-line {
  display: flex;
  justify-content: space-between;
  font-size: var(--gt-font-size-xs);
  line-height: 1.8;
}
.entry-line .acct {
  color: var(--gt-color-text-regular);
}
.entry-line .amt {
  font-family: 'Arial Narrow', Arial, sans-serif;
  white-space: nowrap;
}
</style>
