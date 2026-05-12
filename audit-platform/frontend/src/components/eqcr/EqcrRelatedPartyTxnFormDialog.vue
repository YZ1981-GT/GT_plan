<template>
  <el-dialog
    v-model="visible"
    :title="editing ? '编辑交易' : '新增交易'"
    width="560px"
    destroy-on-close
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
      <el-form-item label="关联方" prop="related_party_id">
        <el-select v-model="form.related_party_id" placeholder="请选择关联方" style="width: 100%">
          <el-option v-for="r in registries" :key="r.id" :label="r.name" :value="r.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="交易类型" prop="transaction_type">
        <el-select v-model="form.transaction_type" placeholder="请选择" style="width: 100%">
          <el-option v-for="opt in TXN_TYPE_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="金额" prop="amount">
        <el-input v-model="form.amount" placeholder="请输入金额" />
      </el-form-item>
      <el-form-item label="是否公允">
        <el-radio-group v-model="form.is_arms_length_str">
          <el-radio value="true">公允</el-radio>
          <el-radio value="false">非公允</el-radio>
          <el-radio value="null">未评</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="证据引用">
        <el-input v-model="form.evidence_refs_text" type="textarea" :rows="2" placeholder="多条用逗号分隔" />
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
import type { EqcrRelatedPartyRegistry, EqcrRelatedPartyTransaction } from '@/services/eqcrService'

const props = defineProps<{
  modelValue: boolean
  editing: EqcrRelatedPartyTransaction | null
  registries: EqcrRelatedPartyRegistry[]
  saving: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  submit: [form: {
    related_party_id: string
    transaction_type: string
    amount: string | null
    is_arms_length: boolean | null
    evidence_refs: string[] | null
  }]
}>()

const visible = ref(props.modelValue)
watch(() => props.modelValue, (v) => { visible.value = v })
watch(visible, (v) => emit('update:modelValue', v))

const TXN_TYPE_OPTIONS = [
  { value: 'sales', label: '销售' },
  { value: 'purchase', label: '采购' },
  { value: 'loan', label: '借款' },
  { value: 'guarantee', label: '担保' },
  { value: 'service', label: '服务' },
  { value: 'asset_transfer', label: '资产转让' },
  { value: 'other', label: '其他' },
]

const formRef = ref<FormInstance>()
const form = reactive({
  related_party_id: '',
  transaction_type: '',
  amount: '',
  is_arms_length_str: 'null' as string,
  evidence_refs_text: '',
})

const rules: FormRules = {
  related_party_id: [{ required: true, message: '请选择关联方', trigger: 'change' }],
  transaction_type: [{ required: true, message: '请选择交易类型', trigger: 'change' }],
  amount: [{
    validator: (_rule: any, value: string, callback: any) => {
      if (value && value.trim() !== '' && isNaN(Number(value))) callback(new Error('金额必须为数字'))
      else callback()
    },
    trigger: 'blur',
  }],
}

watch(() => props.editing, (row) => {
  if (row) {
    form.related_party_id = row.related_party_id
    form.transaction_type = row.transaction_type || ''
    form.amount = row.amount ?? ''
    form.is_arms_length_str = row.is_arms_length === true ? 'true' : row.is_arms_length === false ? 'false' : 'null'
    form.evidence_refs_text = Array.isArray(row.evidence_refs) ? row.evidence_refs.join('、') : row.evidence_refs ? String(row.evidence_refs) : ''
  } else {
    form.related_party_id = ''
    form.transaction_type = ''
    form.amount = ''
    form.is_arms_length_str = 'null'
    form.evidence_refs_text = ''
  }
})

function parseEvidenceRefs(text: string): string[] | null {
  if (!text.trim()) return null
  return text.split(/[,，、]/).map((s) => s.trim()).filter(Boolean)
}

async function submit() {
  const el = formRef.value
  if (!el) return
  const valid = await el.validate().catch(() => false)
  if (!valid) return
  emit('submit', {
    related_party_id: form.related_party_id,
    transaction_type: form.transaction_type,
    amount: form.amount.trim() === '' ? null : form.amount.trim(),
    is_arms_length: form.is_arms_length_str === 'true' ? true : form.is_arms_length_str === 'false' ? false : null,
    evidence_refs: parseEvidenceRefs(form.evidence_refs_text),
  })
}
</script>
