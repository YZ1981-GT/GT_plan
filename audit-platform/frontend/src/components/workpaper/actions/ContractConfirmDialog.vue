<template>
  <el-dialog
    v-model="visible"
    title="合同识别确认"
    width="800px"
    :close-on-click-modal="false"
    append-to-body
  >
    <div v-if="contracts.length === 0" class="empty-state">
      <el-empty description="暂无识别结果" />
    </div>

    <div v-else class="contract-list">
      <div class="contract-header">
        <span>共 {{ contracts.length }} 份合同待确认</span>
        <el-tag :type="allConfirmed ? 'success' : 'info'" size="small">
          已确认 {{ confirmedCount }} / {{ contracts.length }}
        </el-tag>
      </div>

      <el-collapse v-model="activeNames">
        <el-collapse-item
          v-for="(contract, idx) in contracts"
          :key="contract.attachment_id"
          :name="idx"
        >
          <template #title>
            <div class="contract-title">
              <el-icon v-if="contract._confirmed" color="var(--el-color-success)">
                <CircleCheck />
              </el-icon>
              <el-icon v-else color="var(--el-color-warning)">
                <Warning />
              </el-icon>
              <span>{{ contract.filename }}</span>
              <el-tag v-if="contract.confidence" size="small" type="info">
                置信度 {{ (contract.confidence * 100).toFixed(0) }}%
              </el-tag>
            </div>
          </template>

          <el-form label-width="100px" size="small">
            <el-form-item
              v-for="(value, key) in contract.fields"
              :key="key"
              :label="fieldLabels[key as string] || key"
            >
              <el-input
                v-model="contract.fields[key as string]"
                :placeholder="`请输入${fieldLabels[key as string] || key}`"
              />
            </el-form-item>
          </el-form>

          <div class="contract-actions">
            <el-button
              type="success"
              size="small"
              @click="confirmContract(idx)"
            >
              确认
            </el-button>
            <el-button
              type="danger"
              size="small"
              @click="rejectContract(idx)"
            >
              驳回
            </el-button>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button
        type="primary"
        :disabled="!allConfirmed"
        :loading="submitting"
        @click="handleSubmit"
      >
        全部填入台账
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { CircleCheck, Warning } from '@element-plus/icons-vue'

interface ContractResult {
  attachment_id: string
  filename: string
  status: string
  fields: Record<string, any>
  confidence: number
  _confirmed?: boolean
  _rejected?: boolean
}

const props = defineProps<{
  modelValue: boolean
  contracts: ContractResult[]
  submitting?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: [confirmed: ContractResult[]]
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const activeNames = ref<number[]>([0])

const fieldLabels: Record<string, string> = {
  contract_no: '合同编号',
  contract_name: '合同名称',
  party_a: '甲方',
  party_b: '乙方',
  contract_amount: '合同金额',
  currency: '币种',
  sign_date: '签订日期',
  start_date: '开始日期',
  end_date: '结束日期',
  contract_type: '合同类型',
  payment_terms: '付款条件',
  key_terms: '关键条款',
}

const confirmedCount = computed(() =>
  props.contracts.filter(c => c._confirmed).length
)

const allConfirmed = computed(() =>
  props.contracts.length > 0 &&
  props.contracts.every(c => c._confirmed || c._rejected)
)

function confirmContract(idx: number) {
  props.contracts[idx]._confirmed = true
  props.contracts[idx]._rejected = false
}

function rejectContract(idx: number) {
  props.contracts[idx]._rejected = true
  props.contracts[idx]._confirmed = false
}

function handleSubmit() {
  const confirmed = props.contracts.filter(c => c._confirmed)
  emit('submit', confirmed)
}
</script>

<style scoped>
.contract-list {
  max-height: 500px;
  overflow-y: auto;
}
.contract-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  font-size: 14px;
}
.contract-title {
  display: flex;
  align-items: center;
  gap: 8px;
}
.contract-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.empty-state {
  padding: 40px 0;
}
</style>
