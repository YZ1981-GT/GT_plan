<template>
  <div class="basic-info-step">
    <h2 class="step-title">基本信息</h2>
    <p class="step-desc">请填写审计项目的基本信息</p>

    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="120px"
      label-position="right"
      class="basic-info-form"
    >
      <el-form-item label="客户名称" prop="client_name">
        <el-input v-model="form.client_name" placeholder="请输入客户名称" />
      </el-form-item>

      <el-form-item label="审计年度" prop="audit_year">
        <el-date-picker
          v-model="auditYearDate"
          type="year"
          placeholder="选择审计年度"
          format="YYYY"
          value-format="YYYY"
          style="width: 100%"
          @change="onYearChange"
        />
      </el-form-item>

      <el-form-item label="项目类型" prop="project_type">
        <el-select v-model="form.project_type" placeholder="请选择项目类型" style="width: 100%">
          <el-option label="年度审计" value="annual" />
          <el-option label="专项审计" value="special" />
          <el-option label="IPO审计" value="ipo" />
          <el-option label="内控审计" value="internal_control" />
        </el-select>
      </el-form-item>

      <el-form-item label="会计准则" prop="accounting_standard">
        <el-select v-model="form.accounting_standard" placeholder="请选择会计准则" style="width: 100%">
          <el-option label="企业会计准则" value="enterprise" />
          <el-option label="小企业会计准则" value="small_enterprise" />
          <el-option label="金融企业会计准则" value="financial" />
          <el-option label="政府会计准则" value="government" />
        </el-select>
      </el-form-item>

      <el-form-item label="签字合伙人" prop="signing_partner_id">
        <el-input v-model="form.signing_partner_id" placeholder="请输入签字合伙人" />
      </el-form-item>

      <el-form-item label="项目经理" prop="manager_id">
        <el-input v-model="form.manager_id" placeholder="请输入项目经理" />
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { useWizardStore, type BasicInfo } from '@/stores/wizard'

const wizardStore = useWizardStore()
const formRef = ref<FormInstance>()
const auditYearDate = ref<string>('')

const form = reactive<BasicInfo>({
  client_name: '',
  audit_year: null,
  project_type: '',
  accounting_standard: '',
  signing_partner_id: '',
  manager_id: '',
})

const rules: FormRules = {
  client_name: [{ required: true, message: '请输入客户名称', trigger: 'blur' }],
  audit_year: [{ required: true, message: '请选择审计年度', trigger: 'change' }],
  project_type: [{ required: true, message: '请选择项目类型', trigger: 'change' }],
  accounting_standard: [{ required: true, message: '请选择会计准则', trigger: 'change' }],
  signing_partner_id: [{ required: true, message: '请输入签字合伙人', trigger: 'blur' }],
  manager_id: [{ required: true, message: '请输入项目经理', trigger: 'blur' }],
}

function onYearChange(val: string) {
  form.audit_year = val ? parseInt(val, 10) : null
}

/** Restore form from store if data exists */
onMounted(() => {
  const saved = wizardStore.stepData.basic_info as unknown as BasicInfo | undefined
  if (saved) {
    Object.assign(form, saved)
    if (saved.audit_year) {
      auditYearDate.value = String(saved.audit_year)
    }
  }
})

/** Validate and return form data */
async function validate(): Promise<BasicInfo | null> {
  if (!formRef.value) return null
  try {
    await formRef.value.validate()
    return { ...form }
  } catch {
    return null
  }
}

defineExpose({ validate })
</script>

<style scoped>
.basic-info-step {
  max-width: 600px;
  margin: 0 auto;
}

.step-title {
  color: var(--gt-color-primary);
  margin-bottom: var(--gt-space-1);
  font-size: 20px;
}

.step-desc {
  color: #999;
  margin-bottom: var(--gt-space-6);
  font-size: 14px;
}

.basic-info-form {
  padding: var(--gt-space-4) 0;
}
</style>
