<template>
  <div class="gt-basic-info-step">
    <h2 class="gt-step-title">基本信息</h2>
    <p class="gt-step-desc">请填写审计项目的基本信息</p>

    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="140px"
      label-position="right"
      class="gt-basic-form"
    >
      <el-divider content-position="left">项目信息</el-divider>

      <el-form-item label="客户名称" prop="client_name">
        <el-input v-model="form.client_name" placeholder="请输入客户名称" />
      </el-form-item>

      <el-form-item label="企业代码" prop="company_code">
        <el-input v-model="form.company_code" placeholder="统一社会信用代码" maxlength="18" />
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
          <el-option label="验资" value="capital_verification" />
          <el-option label="税审" value="tax_audit" />
        </el-select>
      </el-form-item>

      <el-form-item label="会计准则" prop="accounting_standard">
        <el-select v-model="form.accounting_standard" placeholder="请选择会计准则" style="width: 100%">
          <el-option label="企业会计准则" value="enterprise" />
          <el-option label="小企业会计准则" value="small_enterprise" />
          <el-option label="金融企业会计准则" value="financial" />
          <el-option label="政府会计准则" value="government" />
          <el-option label="国际准则 IFRS" value="ifrs" />
        </el-select>
      </el-form-item>

      <el-divider content-position="left">模板与报表</el-divider>

      <el-form-item label="附注模板类型" prop="template_type">
        <el-radio-group v-model="form.template_type">
          <el-radio-button value="soe">国企版</el-radio-button>
          <el-radio-button value="listed">上市版</el-radio-button>
          <el-radio-button value="custom">自定义</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item v-if="form.template_type === 'custom'" label="自定义模板" prop="custom_template_id">
        <el-select
          v-model="form.custom_template_id"
          placeholder="请选择自定义附注模板"
          style="width: 100%"
          filterable
          clearable
          :loading="customTemplateLoading"
          @change="onCustomTemplateChange"
        >
          <el-option
            v-for="item in customTemplates"
            :key="item.id"
            :label="customTemplateLabel(item)"
            :value="item.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item
        v-if="form.template_type === 'custom' && !customTemplateLoading && customTemplates.length === 0"
        label="模板说明"
      >
        <el-alert
          title="暂无可用的自定义附注模板，请先创建模板后再选择。"
          type="warning"
          :closable="false"
          show-icon
        />
      </el-form-item>

      <el-form-item label="报表类型" prop="report_scope">
        <el-radio-group v-model="form.report_scope" @change="onReportScopeChange">
          <el-radio-button value="standalone">单户报表</el-radio-button>
          <el-radio-button value="consolidated">合并报表</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-alert
        v-if="form.report_scope === 'consolidated'"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 16px"
      >
        合并报表项目将自动创建一张差额表，用于填充合并抵消及其他调整分录。
        子公司清单和持股比例请在「合并项目」模块中配置。
      </el-alert>

      <!-- 合并报表：集团架构折叠面板 -->
      <el-collapse v-if="form.report_scope === 'consolidated'" v-model="groupPanelOpen" class="gt-group-collapse">
        <el-collapse-item title="集团架构信息（三码体系）" name="group">
          <el-form-item label="上级企业名称" prop="parent_company_name">
            <el-input v-model="form.parent_company_name" placeholder="直接控股的上级企业名称" />
          </el-form-item>
          <el-form-item label="上级企业代码" prop="parent_company_code">
            <el-input v-model="form.parent_company_code" placeholder="上级企业统一社会信用代码" maxlength="18" />
          </el-form-item>
          <el-form-item label="最终控制方名称" prop="ultimate_company_name">
            <el-input v-model="form.ultimate_company_name" placeholder="最终控制方企业名称" />
          </el-form-item>
          <el-form-item label="最终控制方代码" prop="ultimate_company_code">
            <el-input v-model="form.ultimate_company_code" placeholder="最终控制方统一社会信用代码" maxlength="18" />
          </el-form-item>
        </el-collapse-item>
      </el-collapse>

      <el-divider content-position="left">项目团队</el-divider>

      <el-form-item label="签字合伙人">
        <el-input v-model="form.signing_partner_id" placeholder="请输入签字合伙人" />
      </el-form-item>

      <el-form-item label="项目经理">
        <el-input v-model="form.manager_id" placeholder="请输入项目经理" />
      </el-form-item>

      <el-divider content-position="left">预算与合同</el-divider>

      <el-form-item label="预算工时（小时）" prop="budget_hours">
        <el-input-number
          v-model="form.budget_hours"
          :min="0"
          :max="99999"
          :precision="0"
          placeholder="预算工时"
          style="width: 100%"
          controls-position="right"
        />
      </el-form-item>

      <el-form-item label="合同金额（元）" prop="contract_amount">
        <el-input-number
          v-model="form.contract_amount"
          :min="0"
          :max="999999999"
          :precision="2"
          placeholder="合同金额"
          style="width: 100%"
          controls-position="right"
        />
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useWizardStore, type BasicInfo } from '@/stores/wizard'

const wizardStore = useWizardStore()
const formRef = ref<FormInstance>()
const auditYearDate = ref<string>('')
const groupPanelOpen = ref<string[]>(['group'])
const customTemplateLoading = ref(false)
const customTemplates = ref<Array<{ id: string; name: string; version?: string }>>([])

const form = reactive<BasicInfo>({
  client_name: '',
  audit_year: null,
  project_type: '',
  accounting_standard: '',
  company_code: '',
  template_type: 'soe',
  custom_template_id: '',
  custom_template_name: '',
  custom_template_version: '',
  report_scope: 'standalone',
  parent_company_name: '',
  parent_company_code: '',
  ultimate_company_name: '',
  ultimate_company_code: '',
  signing_partner_id: null,
  manager_id: null,
  budget_hours: null,
  contract_amount: null,
})

const rules: FormRules = {
  client_name: [{ required: true, message: '请输入客户名称', trigger: 'blur' }],
  audit_year: [{ required: true, message: '请选择审计年度', trigger: 'change' }],
  project_type: [{ required: true, message: '请选择项目类型', trigger: 'change' }],
  accounting_standard: [{ required: true, message: '请选择会计准则', trigger: 'change' }],
  template_type: [{ required: true, message: '请选择附注模板类型', trigger: 'change' }],
  custom_template_id: [{
    validator: (_rule, value, callback) => {
      if (form.template_type === 'custom' && !value) {
        callback(new Error('请选择自定义附注模板'))
        return
      }
      callback()
    },
    trigger: 'change',
  }],
  report_scope: [{ required: true, message: '请选择报表类型', trigger: 'change' }],
}

function customTemplateLabel(item: { id: string; name: string; version?: string }) {
  const lockedName = item.id === form.custom_template_id && form.custom_template_name
    ? form.custom_template_name
    : item.name
  const lockedVersion = item.id === form.custom_template_id && form.custom_template_version
    ? form.custom_template_version
    : item.version
  return lockedVersion ? `${lockedName}（${lockedVersion}）` : lockedName
}

async function loadCustomTemplates() {
  customTemplateLoading.value = true
  try {
    const data = await api.get('/api/note-templates/custom')
    const list = Array.isArray(data) ? data : []
    customTemplates.value = list
  } finally {
    customTemplateLoading.value = false
  }
}

function clearCustomTemplateSelection() {
  form.custom_template_id = ''
  form.custom_template_name = ''
  form.custom_template_version = ''
}

function onCustomTemplateChange(templateId: string | undefined) {
  if (!templateId) {
    clearCustomTemplateSelection()
    return
  }
  const selected = customTemplates.value.find(item => item.id === templateId)
  const keepLockedMetadata = templateId === form.custom_template_id && !!form.custom_template_version
  form.custom_template_id = templateId
  form.custom_template_name = keepLockedMetadata
    ? (form.custom_template_name || selected?.name || '')
    : (selected?.name || '')
  form.custom_template_version = keepLockedMetadata
    ? form.custom_template_version
    : (selected?.version || '')
}

function onYearChange(val: string) {
  form.audit_year = val ? parseInt(val, 10) : null
}

function onReportScopeChange(val: string) {
  if (val === 'consolidated') {
    groupPanelOpen.value = ['group']
  }
}

watch(() => form.template_type, async (val) => {
  if (val === 'custom') {
    await loadCustomTemplates()
    if (form.custom_template_id) {
      onCustomTemplateChange(form.custom_template_id)
    }
    return
  }
  clearCustomTemplateSelection()
})

onMounted(async () => {
  const saved = wizardStore.stepData.basic_info as unknown as BasicInfo | undefined
  if (saved) {
    Object.assign(form, saved)
    if (saved.audit_year) {
      auditYearDate.value = String(saved.audit_year)
    }
  }
  if (form.template_type === 'custom') {
    await loadCustomTemplates()
    if (form.custom_template_id) {
      onCustomTemplateChange(form.custom_template_id)
    }
  }
})

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
.gt-basic-info-step { max-width: 650px; margin: 0 auto; }
.gt-step-title { color: var(--gt-color-primary); margin-bottom: var(--gt-space-1); font-size: 20px; }
.gt-step-desc { color: var(--gt-color-text-tertiary); margin-bottom: var(--gt-space-4); font-size: 14px; }
.gt-basic-form { padding: var(--gt-space-2) 0; }
.gt-group-collapse { margin-bottom: var(--gt-space-4); border: 1px solid var(--gt-color-primary-lighter); border-radius: var(--gt-radius-md); }
.gt-group-collapse :deep(.el-collapse-item__header) { color: var(--gt-color-primary); font-weight: 600; padding-left: var(--gt-space-3); }
.gt-group-collapse :deep(.el-collapse-item__content) { padding: var(--gt-space-2) var(--gt-space-3); }
</style>
