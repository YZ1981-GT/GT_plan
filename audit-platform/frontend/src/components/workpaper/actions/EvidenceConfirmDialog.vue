<template>
  <el-dialog
    v-model="visible"
    title="凭证识别确认"
    width="750px"
    :close-on-click-modal="false"
    append-to-body
  >
    <div v-if="vouchers.length === 0" class="empty-state">
      <el-empty description="暂无识别结果" />
    </div>

    <div v-else class="voucher-list">
      <div class="voucher-header">
        <span>共 {{ vouchers.length }} 份凭证待确认</span>
        <el-tag :type="allProcessed ? 'success' : 'info'" size="small">
          已处理 {{ processedCount }} / {{ vouchers.length }}
        </el-tag>
      </div>

      <el-table :data="vouchers" border size="small" max-height="400">
        <el-table-column prop="filename" label="文件名" width="180" />
        <el-table-column label="凭证号" width="120">
          <template #default="{ row }">
            <el-input
              v-model="row.fields.voucher_no"
              size="small"
              placeholder="凭证号"
            />
          </template>
        </el-table-column>
        <el-table-column label="日期" width="130">
          <template #default="{ row }">
            <el-input
              v-model="row.fields.voucher_date"
              size="small"
              placeholder="YYYY-MM-DD"
            />
          </template>
        </el-table-column>
        <el-table-column label="借方" width="110">
          <template #default="{ row }">
            <el-input
              v-model="row.fields.debit_amount"
              size="small"
              placeholder="金额"
            />
          </template>
        </el-table-column>
        <el-table-column label="贷方" width="110">
          <template #default="{ row }">
            <el-input
              v-model="row.fields.credit_amount"
              size="small"
              placeholder="金额"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row, $index }">
            <el-button
              v-if="!row._confirmed"
              type="success"
              size="small"
              link
              @click="confirmVoucher($index)"
            >
              确认
            </el-button>
            <el-tag v-else type="success" size="small">已确认</el-tag>
          </template>
        </el-table-column>
      </el-table>

      <!-- 交叉核对结果 -->
      <div v-if="crossCheckResult" class="cross-check">
        <el-divider content-position="left">证据链交叉核对</el-divider>
        <el-result
          v-if="crossCheckResult.matched"
          icon="success"
          title="核对通过"
          sub-title="凭证信息与底稿数据一致"
        />
        <div v-else>
          <el-alert
            v-for="(issue, idx) in crossCheckResult.issues"
            :key="idx"
            :title="issue.message"
            :type="issue.severity === 'error' ? 'error' : 'warning'"
            :closable="false"
            show-icon
            style="margin-bottom: 8px"
          />
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button
        type="primary"
        :disabled="!allProcessed"
        :loading="submitting"
        @click="handleSubmit"
      >
        填入证据链
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface VoucherResult {
  attachment_id: string
  filename: string
  status: string
  fields: Record<string, any>
  confidence: number
  _confirmed?: boolean
}

interface CrossCheckResult {
  matched: boolean
  issues: Array<{ type: string; message: string; severity: string }>
  evidence_count: number
}

const props = defineProps<{
  modelValue: boolean
  vouchers: VoucherResult[]
  crossCheckResult?: CrossCheckResult | null
  submitting?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: [confirmed: VoucherResult[]]
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const processedCount = computed(() =>
  props.vouchers.filter(v => v._confirmed).length
)

const allProcessed = computed(() =>
  props.vouchers.length > 0 &&
  props.vouchers.every(v => v._confirmed)
)

function confirmVoucher(idx: number) {
  props.vouchers[idx]._confirmed = true
}

function handleSubmit() {
  const confirmed = props.vouchers.filter(v => v._confirmed)
  emit('submit', confirmed)
}
</script>

<style scoped>
.voucher-list {
  max-height: 600px;
  overflow-y: auto;
}
.voucher-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  font-size: 14px;
}
.cross-check {
  margin-top: 16px;
}
.empty-state {
  padding: 40px 0;
}
</style>
