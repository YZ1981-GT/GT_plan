<template>
  <el-dialog append-to-body v-model="visible" title="密码确认签名 (Level 1)" width="400px" @close="onClose">
    <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
      <el-form-item label="用户名">
        <el-input :model-value="username" disabled />
      </el-form-item>
      <el-form-item label="密码" prop="password">
        <el-input v-model="form.password" type="password" show-password placeholder="请输入密码确认签名" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="onSign" :loading="signing" v-permission="'sign:execute'">确认签名</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { api } from '@/services/apiProxy'
import { signatures as P_sig } from '@/services/apiPaths'

const props = defineProps<{
  modelValue: boolean
  objectType: string
  objectId: string
  username?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'signed', record: any): void
  (e: 'close'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const formRef = ref<FormInstance>()
const signing = ref(false)
const form = ref({ password: '' })
const rules: FormRules = {
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function onSign() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  signing.value = true
  try {
    const data = await api.post(P_sig.sign, {
      object_type: props.objectType,
      object_id: props.objectId,
      signature_level: 'level1',
      password: form.value.password,
    })
    ElMessage.success('签名成功')
    emit('signed', data)
    visible.value = false
  } catch { ElMessage.error('签名失败，请检查密码') }
  finally { signing.value = false }
}

function onClose() {
  form.value.password = ''
  emit('close')
}
</script>
