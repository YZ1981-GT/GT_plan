<template>
  <div class="gt-basic-info-step">
    <h2 class="gt-step-title">基本信息</h2>
    <p class="gt-step-desc">请填写审计项目的基本信息</p>

    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="120px"
      label-position="right"
      class="gt-basic-form"
    >
      <div class="gt-form-two-col">
        <!-- 左栏：项目信息 + 模板与报表 -->
        <div class="gt-form-col">
          <div class="gt-form-section-title">项目信息</div>

          <el-form-item label="客户名称" prop="client_name">
            <el-input v-model="form.client_name" placeholder="请输入客户名称" />
          </el-form-item>

          <el-form-item label="企业代码" prop="company_code">
            <el-input v-model="form.company_code" placeholder="统一社会信用代码" maxlength="18" />
          </el-form-item>

          <el-form-item label="项目简称" prop="short_name">
            <el-input v-model="form.short_name" placeholder="请输入项目简称" maxlength="100" />
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
            <el-select v-model="form.project_type" placeholder="请选择" style="width: 100%">
              <el-option label="年度审计" value="annual" />
              <el-option label="专项审计" value="special" />
              <el-option label="IPO审计" value="ipo" />
              <el-option label="内控审计" value="internal_control" />
              <el-option label="验资" value="capital_verification" />
              <el-option label="税审" value="tax_audit" />
            </el-select>
          </el-form-item>

          <el-form-item label="会计准则" prop="accounting_standard">
            <el-select v-model="form.accounting_standard" placeholder="请选择" style="width: 100%">
              <el-option label="企业会计准则" value="enterprise" />
              <el-option label="小企业会计准则" value="small_enterprise" />
              <el-option label="金融企业会计准则" value="financial" />
              <el-option label="政府会计准则" value="government" />
              <el-option label="国际准则 IFRS" value="ifrs" />
            </el-select>
          </el-form-item>

          <div class="gt-form-section-title" style="margin-top: 20px">模板与报表</div>

          <el-form-item label="报表标准" prop="template_type">
            <el-select v-model="form.template_type" placeholder="请选择报表标准" style="width: 200px">
              <el-option label="国有企业" value="soe" />
              <el-option label="上市公司" value="listed" />
              <el-option label="自定义" value="custom" />
            </el-select>
            <span style="margin-left: 8px; font-size: var(--gt-font-size-xs); color: var(--gt-color-info)">
              决定报表行次和附注模板
            </span>
          </el-form-item>

          <el-form-item label="企业子类型" prop="company_subtype">
            <el-alert
              v-if="showSubtypeBanner"
              type="warning"
              :closable="false"
              show-icon
              class="gt-subtype-banner"
              title="待确认企业子类型"
            >
              <template #default>
                该项目尚未确认企业子类型。系统建议「模板{{ subtypeLetter(recommendation?.subtype || null) }}」（{{ subtypeDesc(recommendation?.subtype || null) }}），请确认或手动选择后保存。
                <el-button link type="primary" size="small" @click="applyRecommendation">采用建议</el-button>
              </template>
            </el-alert>
            <el-select v-model="form.company_subtype" placeholder="请选择企业子类型" style="width: 100%" clearable>
              <el-option label="A — 上市公司、三板创新层及公开发债" value="type_a" />
              <el-option label="B — 三板基础层、银行、保险、期货、证券" value="type_b" />
              <el-option label="C — 其他公众利益实体" value="type_c" />
              <el-option label="D — 非公众利益实体" value="type_d" />
            </el-select>
            <div
              v-if="recommendation && recommendation.subtype"
              class="gt-subtype-recommend"
            >
              <el-tag size="small" :type="recommendation.confidence === 'high' ? 'success' : 'warning'" effect="light">
                系统建议：模板{{ subtypeLetter(recommendation.subtype) }}
              </el-tag>
              <span class="gt-subtype-recommend-desc">{{ subtypeDesc(recommendation.subtype) }}</span>
              <el-button
                v-if="form.company_subtype !== recommendation.subtype"
                link
                type="primary"
                size="small"
                @click="applyRecommendation"
              >
                采用建议
              </el-button>
              <span
                v-if="recommendation.confidence !== 'high' && recommendation.candidates.length > 1"
                class="gt-subtype-recommend-hint"
              >
                （存在多个候选：{{ recommendation.candidates.map(subtypeLetter).join('、') }}，请确认）
              </span>
            </div>
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

          <el-form-item label="报表类型" prop="report_scope">
            <el-radio-group v-model="form.report_scope" @change="onReportScopeChange">
              <el-radio-button value="standalone">单户报表</el-radio-button>
              <el-radio-button value="consolidated">合并报表</el-radio-button>
            </el-radio-group>
          </el-form-item>

          <el-form-item v-if="form.report_scope === 'consolidated'" label="合并类型" prop="consolidation_type">
            <el-radio-group v-model="form.consolidation_type">
              <el-radio-button value="subsidiary">母子合并</el-radio-button>
              <el-radio-button value="branch">总分汇总</el-radio-button>
            </el-radio-group>
            <div style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-top: 4px; line-height: 1.4">
              母子合并：独立法人子公司，含内部交易/投资抵销；总分汇总：非独立法人分支机构，直接加总无抵销
            </div>
          </el-form-item>
        </div>

        <!-- 右栏：项目团队 + 预算合同 + 集团架构 -->
        <div class="gt-form-col">
          <div class="gt-form-section-title">项目团队</div>

          <el-form-item label="签字合伙人">
            <el-input v-model="form.signing_partner_id" placeholder="请输入签字合伙人" />
          </el-form-item>

          <el-form-item label="项目经理">
            <el-input v-model="form.manager_id" placeholder="请输入项目经理" />
          </el-form-item>

          <div class="gt-form-section-title" style="margin-top: 20px">预算与合同</div>

          <el-form-item label="预算工时(h)">
            <el-input-number
              v-model="form.budget_hours"
              :min="0" :max="99999" :precision="0"
              placeholder="预算工时"
              style="width: 100%"
              controls-position="right"
            />
          </el-form-item>

          <el-form-item label="合同金额(¥)">
            <el-input-number
              v-model="form.contract_amount"
              :min="0" :max="999999999" :precision="2"
              placeholder="合同金额"
              style="width: 100%"
              controls-position="right"
            />
          </el-form-item>

          <!-- 合并报表：集团架构 -->
          <template v-if="form.report_scope === 'consolidated'">
            <div class="gt-form-section-title" style="margin-top: 20px">集团架构（三码体系）</div>

            <el-form-item label="上级企业">
              <el-input v-model="form.parent_company_name" placeholder="直接控股的上级企业名称" />
            </el-form-item>

            <el-form-item label="上级代码">
              <el-input v-model="form.parent_company_code" placeholder="上级企业信用代码" maxlength="18" />
            </el-form-item>

            <el-form-item label="最终控制方">
              <el-input v-model="form.ultimate_company_name" placeholder="最终控制方企业名称" />
            </el-form-item>

            <el-form-item label="控制方代码">
              <el-input v-model="form.ultimate_company_code" placeholder="最终控制方信用代码" maxlength="18" />
            </el-form-item>
          </template>

          <el-alert
            v-if="form.report_scope === 'consolidated'"
            type="info"
            :closable="false"
            show-icon
            style="margin-top: 12px"
          >
            合并报表项目将自动创建差额表。子公司清单请在「合并项目」模块中配置。
          </el-alert>
        </div>
      </div>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { api } from '@/services/apiProxy'
import { fetchTemplateRecommendation, type TemplateRecommendation } from '@/services/commonApi'
import { useWizardStore, type BasicInfo } from '@/stores/wizard'
import { validateUSCC } from '@/utils/uscc_validator'

const wizardStore = useWizardStore()
const formRef = ref<FormInstance>()
const auditYearDate = ref<string>('')
const customTemplateLoading = ref(false)
const customTemplates = ref<Array<{ id: string; name: string; version?: string }>>([])
const recommendation = ref<TemplateRecommendation | null>(null)

const SUBTYPE_DESC: Record<string, string> = {
  type_a: '上市公司、三板创新层及公开发债',
  type_b: '三板基础层、银行、保险、期货、证券',
  type_c: '其他公众利益实体',
  type_d: '非公众利益实体',
}

function subtypeLetter(subtype: string | null): string {
  if (!subtype) return ''
  return subtype.replace('type_', '').toUpperCase()
}

function subtypeDesc(subtype: string | null): string {
  return subtype ? (SUBTYPE_DESC[subtype] || '') : ''
}

function applyRecommendation() {
  if (recommendation.value?.subtype) {
    form.company_subtype = recommendation.value.subtype
  }
}

/**
 * 「待确认企业子类型」非阻断横幅（需求 1.7 ③ / 14.3）。
 * 仅当：存量项目（有 projectId）+ 用户尚未选择 company_subtype + 后端标记 needs_confirmation
 * + 存在建议值时展示。用户选择后即消失（confirmed，需求 1.8）。
 */
const showSubtypeBanner = computed(() => {
  return (
    !!wizardStore.projectId &&
    !form.company_subtype &&
    !!recommendation.value?.needs_confirmation &&
    !!recommendation.value?.subtype
  )
})

/** 拉取企业子类型推荐（需求 7.6：须预填建议值，不仅高亮）。 */
async function loadRecommendation() {
  const projectId = wizardStore.projectId
  if (!projectId) return
  try {
    const rec = await fetchTemplateRecommendation(projectId)
    if (rec && rec.subtype) {
      recommendation.value = rec
      // 需求 7.6：预填建议值（用户未手动选择时）
      if (!form.company_subtype) {
        form.company_subtype = rec.subtype
      }
    }
  } catch {
    // 推荐失败不阻断向导
  }
}

const form = reactive<BasicInfo>({
  client_name: '',
  short_name: '',
  audit_year: null,
  project_type: '',
  accounting_standard: '',
  company_code: '',
  template_type: 'soe',
  company_subtype: null,
  custom_template_id: '',
  custom_template_name: '',
  custom_template_version: '',
  report_scope: 'standalone',
  consolidation_type: 'subsidiary',
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
  short_name: [{ required: true, message: '项目简称为必填项', trigger: 'blur' }],
  company_code: [
    { required: true, message: '企业代码为必填项', trigger: 'blur' },
    {
      validator: (_rule, value: string, callback) => {
        if (!value) {
          callback()
          return
        }
        const result = validateUSCC(value)
        if (!result.valid) {
          callback(new Error(result.message))
        } else {
          callback()
        }
      },
      trigger: ['blur', 'change'],
    },
  ],
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

function onReportScopeChange(_val: string | number | boolean | undefined) {
  // 切换到合并报表时无需额外操作
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
  // 需求 7.6：已有项目进入向导时拉取企业子类型推荐并预填
  await loadRecommendation()
})

// 兜底：store 异步加载完成后填充表单（解决组件挂载时 store 还在 loading 的时序问题）
watch(() => wizardStore.stepData.basic_info, (newVal) => {
  if (newVal && !form.client_name) {
    Object.assign(form, newVal as any)
    if ((newVal as any).audit_year) {
      auditYearDate.value = String((newVal as any).audit_year)
    }
  }
}, { immediate: false })

async function validate(): Promise<BasicInfo | null> {
  if (!formRef.value) return null
  try {
    await formRef.value.validate()
    return { ...form }
  } catch {
    return null
  }
}

defineExpose({ validate, formRef })
</script>

<style scoped>
.gt-basic-info-step {
  max-width: 960px;
  margin: 0 auto;
  padding: 0 16px;
}
.gt-step-title {
  color: var(--gt-color-primary);
  margin-bottom: 4px;
  font-size: var(--gt-font-size-xl);
  font-weight: 700;
}
.gt-step-desc {
  color: var(--gt-color-text-tertiary);
  margin-bottom: 20px;
  font-size: var(--gt-font-size-sm);
}

/* 两栏布局 */
.gt-form-two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 32px;
}

.gt-form-col {
  background: var(--gt-color-bg-white);
  border-radius: 10px;
  padding: 20px 24px;
  border: 1px solid var(--gt-color-border-purple);
  box-shadow: 0 1px 4px rgba(0,0,0,0.03);
}

.gt-form-section-title {
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-primary);
  margin-bottom: 14px;
  padding-bottom: 6px;
  border-bottom: 2px solid var(--gt-color-primary-lighter, #e8e0f0);
}

/* 企业子类型系统建议 */
.gt-subtype-banner {
  margin-bottom: 8px;
}
.gt-subtype-recommend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}
.gt-subtype-recommend-desc {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
}
.gt-subtype-recommend-hint {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-warning, #e6a23c);
}

/* 响应式：窄屏回退单栏 */
@media (max-width: 768px) {
  .gt-form-two-col {
    grid-template-columns: 1fr;
    gap: 16px;
  }
}
</style>
