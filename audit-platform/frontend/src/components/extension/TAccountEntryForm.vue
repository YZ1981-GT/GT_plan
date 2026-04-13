<template>
  <el-form ref="formRef" :model="form" :rules="rules" label-width="100px" size="small">
    <el-form-item label="方向" prop="side">
      <el-radio-group v-model="form.side">
        <el-radio value="debit">借方</el-radio>
        <el-radio value="credit">贷方</el-radio>
      </el-radio-group>
    </el-form-item>
    <el-form-item label="金额" prop="amount">
      <el-input-number v-model="form.amount" :precision="2" :min="0" style="width: 100%" />
    </el-form-item>
    <el-form-item label="摘要" prop="description">
      <el-input v-model="form.description" placeholder="分录摘要" />
    </el-form-item>
    <el-form-item label="对方科目">
      <el-input v-model="form.counterpart_account" placeholder="对方科目名称（可选）" />
    </el-form-item>
    <el-form-item>
      <el-button type="primary" @click="onSubmit" :loading="submitting">添加分录</el-button>
      <el-button @click="resetForm">重置</el-button>
    </el-form-item>
  </el-form>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'

const emit = defineEmits<{
  (e: 'submit', entry: { side: string; amount: number; description: string; counterpart_account: string }): void
}>()

const formRef = ref<FormInstance>()
const submitting = ref(false)

const form = ref({
  side: 'debit',
  amount: 0,
  description: '',
  counterpart_account: '',
})

const rules: FormRules = {
  side: [{ required: true, message: '请选择方向', trigger: 'change' }],
  amount: [{ required: true, message: '请输入金额', trigger: 'blur' }],
  description: [{ required: true, message: '请输入摘要', trigger: 'blur' }],
}

async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  emit('submit', { ...form.value })
  submitting.value = false
  resetForm()
}

function resetForm() {
  form.value = { side: 'debit', amount: 0, description: '', counterpart_account: '' }
}
</script>
