<template>
  <el-dialog append-to-body v-model="visible" title="电子底稿归档标准备案" width="600px" @close="resetForm">
    <el-form ref="formRef" :model="form" :rules="rules" label-width="120px" size="default">
      <el-form-item label="项目ID" prop="project_id">
        <el-input v-model="form.project_id" placeholder="选择或输入项目ID" />
      </el-form-item>
      <el-form-item label="归档编号" prop="archival_no">
        <el-input v-model="form.archival_no" placeholder="归档编号" />
      </el-form-item>
      <el-form-item label="被审计单位" prop="entity_name">
        <el-input v-model="form.entity_name" placeholder="被审计单位名称" />
      </el-form-item>
      <el-form-item label="审计年度" prop="audit_year">
        <el-date-picker v-model="form.audit_year" type="year" placeholder="选择年度" value-format="YYYY" style="width: 100%" />
      </el-form-item>
      <el-form-item label="底稿数量" prop="workpaper_count">
        <el-input-number v-model="form.workpaper_count" :min="0" style="width: 100%" />
      </el-form-item>
      <el-form-item label="归档格式" prop="format">
        <el-select v-model="form.format" style="width: 100%">
          <el-option label="XML" value="xml" />
          <el-option label="JSON" value="json" />
        </el-select>
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="form.notes" type="textarea" :rows="2" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="onSubmit" :loading="submitting">提交备案</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import http from '@/utils/http'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'submitted'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const formRef = ref<FormInstance>()
const submitting = ref(false)

const form = ref({
  project_id: '',
  archival_no: '',
  entity_name: '',
  audit_year: '',
  workpaper_count: 0,
  format: 'xml',
  notes: '',
})

const rules: FormRules = {
  project_id: [{ required: true, message: '请输入项目ID', trigger: 'blur' }],
  archival_no: [{ required: true, message: '请输入归档编号', trigger: 'blur' }],
  entity_name: [{ required: true, message: '请输入被审计单位', trigger: 'blur' }],
  audit_year: [{ required: true, message: '请选择审计年度', trigger: 'change' }],
}

async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    await http.post('/api/regulatory/archival-standard', form.value)
    ElMessage.success('归档备案提交成功')
    emit('submitted')
    visible.value = false
  } catch { ElMessage.error('备案提交失败') }
  finally { submitting.value = false }
}

function resetForm() { formRef.value?.resetFields() }
</script>
