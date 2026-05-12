<template>
  <el-dialog
    v-model="visible"
    :title="editing ? '编辑关联方' : '新增关联方'"
    width="500px"
    destroy-on-close
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
      <el-form-item label="名称" prop="name">
        <el-input v-model="form.name" placeholder="请输入关联方名称" maxlength="200" />
      </el-form-item>
      <el-form-item label="关系类型" prop="relation_type">
        <el-select v-model="form.relation_type" placeholder="请选择" style="width: 100%">
          <el-option v-for="opt in RELATION_TYPE_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="同一控制">
        <el-switch v-model="form.is_controlled_by_same_party" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="submit">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import type { EqcrRelatedPartyRegistry } from '@/services/eqcrService'

const props = defineProps<{
  modelValue: boolean
  editing: EqcrRelatedPartyRegistry | null
  saving: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  submit: [form: { name: string; relation_type: string; is_controlled_by_same_party: boolean }]
}>()

const visible = ref(props.modelValue)
watch(() => props.modelValue, (v) => { visible.value = v })
watch(visible, (v) => emit('update:modelValue', v))

const RELATION_TYPE_OPTIONS = [
  { value: 'parent', label: '母公司' },
  { value: 'subsidiary', label: '子公司' },
  { value: 'associate', label: '联营企业' },
  { value: 'joint_venture', label: '合营企业' },
  { value: 'key_management', label: '关键管理人员' },
  { value: 'family_member', label: '家庭成员' },
  { value: 'other', label: '其他' },
]

const formRef = ref<FormInstance>()
const form = reactive({ name: '', relation_type: '', is_controlled_by_same_party: false })

const rules: FormRules = {
  name: [{ required: true, message: '请输入关联方名称', trigger: 'blur' }],
  relation_type: [{ required: true, message: '请选择关系类型', trigger: 'change' }],
}

watch(() => props.editing, (row) => {
  if (row) {
    form.name = row.name
    form.relation_type = row.relation_type || ''
    form.is_controlled_by_same_party = row.is_controlled_by_same_party
  } else {
    form.name = ''
    form.relation_type = ''
    form.is_controlled_by_same_party = false
  }
})

async function submit() {
  const el = formRef.value
  if (!el) return
  const valid = await el.validate().catch(() => false)
  if (!valid) return
  emit('submit', { ...form })
}
</script>
