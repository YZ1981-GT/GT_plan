<template>
  <el-dialog
    v-model="visible"
    title="截止测试取数"
    width="520px"
    :close-on-click-modal="false"
    append-to-body
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
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
          style="width: 100%"
        />
      </el-form-item>

      <el-form-item label="期末前天数" prop="days_before">
        <el-input-number
          v-model="form.days_before"
          :min="1"
          :max="30"
          style="width: 200px"
        />
        <span class="form-hint">天</span>
      </el-form-item>

      <el-form-item label="期末后天数" prop="days_after">
        <el-input-number
          v-model="form.days_after"
          :min="1"
          :max="30"
          style="width: 200px"
        />
        <span class="form-hint">天</span>
      </el-form-item>

      <el-form-item label="金额阈值" prop="amount_threshold">
        <el-input-number
          v-model="form.amount_threshold"
          :min="0"
          :step="1000"
          :precision="2"
          style="width: 200px"
        />
        <span class="form-hint">元</span>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="executing" @click="handleConfirm">
        执行取数
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
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

import { computed } from 'vue'

const formRef = ref<FormInstance>()

const form = reactive({
  account_codes: [] as string[],
  year: new Date().getFullYear() - 1,
  days_before: 5,
  days_after: 5,
  amount_threshold: 10000,
})

const rules: FormRules = {
  account_codes: [{ required: true, message: '请选择科目编码', trigger: 'change' }],
  year: [{ required: true, message: '请输入会计年度', trigger: 'blur' }],
}

// 常用科目编码
const commonAccountCodes = [
  { value: '6001', label: '主营业务收入' },
  { value: '6051', label: '其他业务收入' },
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
</style>
