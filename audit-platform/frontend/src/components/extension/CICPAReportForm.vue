<template>
  <el-dialog v-model="visible" title="中注协审计报告备案" width="600px" @close="resetForm">
    <el-form ref="formRef" :model="form" :rules="rules" label-width="120px" size="default">
      <el-form-item label="项目ID" prop="project_id">
        <el-input v-model="form.project_id" placeholder="选择或输入项目ID" />
      </el-form-item>
      <el-form-item label="报告编号" prop="report_no">
        <el-input v-model="form.report_no" placeholder="审计报告编号" />
      </el-form-item>
      <el-form-item label="被审计单位" prop="entity_name">
        <el-input v-model="form.entity_name" placeholder="被审计单位名称" />
      </el-form-item>
      <el-form-item label="审计年度" prop="audit_year">
        <el-date-picker v-model="form.audit_year" type="year" placeholder="选择年度" value-format="YYYY" style="width: 100%" />
      </el-form-item>
      <el-form-item label="意见类型" prop="opinion_type">
        <el-select v-model="form.opinion_type" style="width: 100%">
          <el-option label="标准无保留意见" value="unqualified" />
          <el-option label="保留意见" value="qualified" />
          <el-option label="否定意见" value="adverse" />
          <el-option label="无法表示意见" value="disclaimer" />
        </el-select>
      </el-form-item>
      <el-form-item label="签字注册会计师" prop="signing_cpa">
        <el-input v-model="form.signing_cpa" placeholder="签字注册会计师姓名" />
      </el-form-item>
      <el-form-item label="报告日期" prop="report_date">
        <el-date-picker v-model="form.report_date" type="date" placeholder="选择日期" value-format="YYYY-MM-DD" style="width: 100%" />
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
  report_no: '',
  entity_name: '',
  audit_year: '',
  opinion_type: 'unqualified',
  signing_cpa: '',
  report_date: '',
})

const rules: FormRules = {
  project_id: [{ required: true, message: '请输入项目ID', trigger: 'blur' }],
  report_no: [{ required: true, message: '请输入报告编号', trigger: 'blur' }],
  entity_name: [{ required: true, message: '请输入被审计单位', trigger: 'blur' }],
  audit_year: [{ required: true, message: '请选择审计年度', trigger: 'change' }],
  opinion_type: [{ required: true, message: '请选择意见类型', trigger: 'change' }],
}

async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    await http.post('/api/regulatory/cicpa-report', form.value)
    ElMessage.success('备案提交成功')
    emit('submitted')
    visible.value = false
  } catch { ElMessage.error('备案提交失败') }
  finally { submitting.value = false }
}

function resetForm() {
  formRef.value?.resetFields()
}
</script>
