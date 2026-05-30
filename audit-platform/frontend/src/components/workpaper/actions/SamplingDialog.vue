<template>
  <el-dialog
    v-model="visible"
    title="抽凭取数"
    width="560px"
    :close-on-click-modal="false"
    append-to-body
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
      <el-form-item label="抽样方式" prop="method">
        <el-radio-group v-model="form.method">
          <el-radio-button value="random">随机抽样</el-radio-button>
          <el-radio-button value="stratified">分层抽样</el-radio-button>
          <el-radio-button value="top_n">大额抽样</el-radio-button>
          <el-radio-button value="mus">MUS</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="科目编码" prop="account_codes">
        <el-select
          v-model="form.account_codes"
          multiple
          filterable
          allow-create
          placeholder="输入或选择科目编码"
          style="width: 100%"
        >
          <el-option
            v-for="code in commonAccountCodes"
            :key="code.value"
            :label="`${code.value} ${code.label}`"
            :value="code.value"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="会计年度" prop="year">
        <el-input-number
          v-model="form.year"
          :min="2000"
          :max="2100"
          style="width: 200px"
        />
      </el-form-item>

      <el-form-item label="样本量" prop="sample_size">
        <el-input-number
          v-model="form.sample_size"
          :min="1"
          :max="200"
          style="width: 200px"
        />
        <span class="form-hint">笔</span>
      </el-form-item>

      <el-form-item
        v-if="form.method === 'top_n'"
        label="大额阈值"
        prop="amount_threshold"
      >
        <el-input-number
          v-model="form.amount_threshold"
          :min="0"
          :step="10000"
          :precision="2"
          style="width: 200px"
        />
        <span class="form-hint">元</span>
      </el-form-item>

      <el-form-item
        v-if="form.method === 'mus'"
        label="抽样间距"
        prop="sampling_interval"
      >
        <el-input-number
          v-model="form.sampling_interval"
          :min="1000"
          :step="10000"
          style="width: 200px"
        />
        <span class="form-hint">元</span>
      </el-form-item>
    </el-form>

    <div class="method-desc">
      <template v-if="form.method === 'random'">
        随机从序时账中抽取指定数量的凭证
      </template>
      <template v-else-if="form.method === 'stratified'">
        按金额区间分层，每层按比例抽取样本
      </template>
      <template v-else-if="form.method === 'top_n'">
        抽取金额超过阈值的所有凭证（大额全查）
      </template>
      <template v-else-if="form.method === 'mus'">
        货币单位抽样：按固定间距从累计金额中抽取
      </template>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="executing" @click="handleConfirm">
        执行抽样
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'

const props = defineProps<{
  modelValue: boolean
  executing?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: [params: Record<string, any>]
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const formRef = ref<FormInstance>()

const form = reactive({
  method: 'random' as 'random' | 'stratified' | 'top_n' | 'mus',
  account_codes: [] as string[],
  year: new Date().getFullYear() - 1,
  sample_size: 25,
  amount_threshold: 100000,
  sampling_interval: 50000,
})

const rules: FormRules = {
  method: [{ required: true, message: '请选择抽样方式', trigger: 'change' }],
  account_codes: [{ required: true, message: '请选择科目编码', trigger: 'change' }],
  year: [{ required: true, message: '请输入会计年度', trigger: 'blur' }],
  sample_size: [{ required: true, message: '请输入样本量', trigger: 'blur' }],
}

const commonAccountCodes = [
  { value: '6001', label: '主营业务收入' },
  { value: '6401', label: '主营业务成本' },
  { value: '1122', label: '应收账款' },
  { value: '2202', label: '应付账款' },
  { value: '1403', label: '原材料' },
  { value: '1405', label: '库存商品' },
]

async function handleConfirm() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  emit('confirm', { ...form })
}
</script>

<style scoped>
.form-hint {
  margin-left: 8px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.method-desc {
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
</style>
