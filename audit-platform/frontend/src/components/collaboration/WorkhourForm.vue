<template>
  <div class="workhour-form">
    <el-form ref="formRef" :model="form" :rules="rules" label-width="110px" @submit.prevent="handleSubmit">
      <el-form-item label="审计年度" prop="auditCycle">
        <el-select v-model="form.auditCycle" placeholder="请选择审计年度" style="width: 100%">
          <el-option label="2024年度" value="2024年度" />
          <el-option label="2025年度" value="2025年度" />
          <el-option label="2026年度" value="2026年度" />
        </el-select>
      </el-form-item>

      <el-form-item label="项目" prop="projectId">
        <el-select v-model="form.projectId" placeholder="请选择项目" style="width: 100%">
          <el-option
            v-for="p in projectOptions"
            :key="p.id"
            :label="p.name"
            :value="p.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="工作日期" prop="workDate">
        <el-date-picker
          v-model="form.workDate"
          type="date"
          placeholder="选择日期"
          value-format="YYYY-MM-DD"
          style="width: 100%"
        />
      </el-form-item>

      <el-form-item label="工时(小时)" prop="hours">
        <el-input-number
          v-model="form.hours"
          :min="0"
          :max="24"
          :step="0.5"
          :precision="1"
          style="width: 100%"
        />
      </el-form-item>

      <el-form-item label="工作内容" prop="description">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="4"
          placeholder="请填写工作内容摘要"
          maxlength="500"
          show-word-limit
        />
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">提交工时</el-button>
        <el-button @click="handleReset">重置</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { projectMgmtApi } from '@/services/collaborationApi'

const emit = defineEmits<{
  submitted: []
}>()

const projectId = 'current-project-id'
const formRef = ref<FormInstance>()
const submitting = ref(false)

const form = reactive({
  auditCycle: '',
  projectId: '',
  workDate: '',
  hours: 8,
  description: '',
})

const rules: FormRules = {
  auditCycle: [{ required: true, message: '请选择审计年度', trigger: 'change' }],
  projectId: [{ required: true, message: '请选择项目', trigger: 'change' }],
  workDate: [{ required: true, message: '请选择工作日期', trigger: 'change' }],
  hours: [
    { required: true, message: '请输入工时', trigger: 'blur' },
    { type: 'number', min: 0.5, max: 24, message: '工时需在0.5-24之间', trigger: 'blur' },
  ],
  description: [
    { required: true, message: '请填写工作内容', trigger: 'blur' },
    { min: 5, message: '工作内容至少5个字符', trigger: 'blur' },
  ],
}

// Mock project options
const projectOptions = [
  { id: 'p1', name: 'ABC公司2024年度审计' },
  { id: 'p2', name: 'XYZ集团年报审计' },
  { id: 'p3', name: 'DEF公司IPO审计' },
]

async function handleSubmit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  submitting.value = true
  try {
    const targetProject = form.projectId || projectId
    await projectMgmtApi.logWorkHours(targetProject, {
      audit_cycle: form.auditCycle,
      work_date: form.workDate,
      hours: form.hours,
      description: form.description,
    })
    ElMessage.success('工时提交成功')
    handleReset()
    emit('submitted')
  } catch (e: any) {
    ElMessage.error(e?.message ?? '提交失败，请重试')
  } finally {
    submitting.value = false
  }
}

function handleReset() {
  formRef.value?.resetFields()
  form.hours = 8
}
</script>

<style scoped>
.workhour-form {
  max-width: 560px;
}
</style>
