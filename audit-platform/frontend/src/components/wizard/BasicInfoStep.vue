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

          <el-form-item prop="short_name">
            <template #label>
              <el-tooltip
                content="该简称将用于审计报告正文中替代被审计单位全称，如 XX公司"
                placement="top"
                :show-after="300"
              >
                <span style="cursor: help; border-bottom: 1px dashed var(--el-text-color-secondary)">项目简称</span>
              </el-tooltip>
            </template>
            <el-input v-model="form.short_name" placeholder="请输入项目简称，如 XX公司" maxlength="100" />
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

          <el-form-item label="业务类型" prop="company_subtype">
            <el-alert
              v-if="showSubtypeBanner"
              type="warning"
              :closable="false"
              show-icon
              class="gt-subtype-banner"
              title="待确认业务类型"
            >
              <template #default>
                该项目尚未确认业务类型。系统建议「{{ subtypeLetter(recommendation?.subtype || null) }}」（{{ subtypeDesc(recommendation?.subtype || null) }}），请确认或手动选择后保存。
                <el-button link type="primary" size="small" @click="applyRecommendation">采用建议</el-button>
              </template>
            </el-alert>
            <el-select v-model="form.company_subtype" placeholder="请选择业务类型" style="width: 100%" clearable>
              <el-option label="A — 上市公司、三板创新层及公开发债（A1-A8）" value="type_a" />
              <el-option label="B — 三板基础层、银行、保险、期货、证券（B1-B6）" value="type_b" />
              <el-option label="C — 其他（非A非B类业务）" value="type_c" />
            </el-select>
            <el-button link type="primary" size="small" class="gt-category-ref-link" @click="showCategoryReference = true">
              📋 查看分类标准
            </el-button>
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
            <el-radio-group v-model="form.report_scope">
              <el-radio-button value="standalone">单户报表</el-radio-button>
              <el-radio-button value="consolidated">合并报表</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <!-- 「合并类型」单选已移除（consol-tree-three-code-autobuild 需求 1.7 / 4）：
               合并方式按下级企业的与上级关系自动识别，子公司与分公司可以并存。 -->
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

          <!-- 集团架构：所有项目都填写（需求 1.1）。合并企业树由各项目的这组字段自动推导 -->
          <div class="gt-form-section-title gt-group-section" style="margin-top: 20px" data-testid="group-section">
            集团架构
          </div>

          <el-form-item label="上级企业" prop="parent_company_name">
            <el-input v-model="form.parent_company_name" placeholder="直接上级企业名称（没有上级留空）" />
          </el-form-item>

          <el-form-item label="上级代码" prop="parent_company_code">
            <el-input
              v-model="form.parent_company_code"
              placeholder="直接上级的统一社会信用代码"
              maxlength="18"
              data-testid="parent-code-input"
            />
            <div v-if="selfKindHint" class="gt-self-ref-hint" data-testid="self-ref-hint">{{ selfKindHint }}</div>
          </el-form-item>

          <el-form-item label="与上级关系" prop="relation_to_parent">
            <el-select
              v-model="form.relation_to_parent"
              :disabled="!hasEffectiveParent"
              :placeholder="relationPlaceholder"
              style="width: 100%"
              data-testid="relation-select"
              @change="onRelationChange"
            >
              <el-option
                v-for="opt in RELATION_OPTIONS"
                :key="opt.value"
                :value="opt.value"
                :label="`${opt.label}（${opt.hint}）`"
              />
            </el-select>
          </el-form-item>

          <el-form-item label="最终控制方" prop="ultimate_company_name">
            <el-input v-model="form.ultimate_company_name" placeholder="最终控制方企业名称" />
          </el-form-item>

          <el-form-item label="控制方代码" prop="ultimate_company_code">
            <el-input v-model="form.ultimate_company_code" placeholder="最终控制方的统一社会信用代码" maxlength="18" />
          </el-form-item>

          <div class="gt-group-hint" data-testid="group-hint">合并项目的下级企业按各项目的上级代码自动识别：子公司进入合并，分公司并入母公司汇总，无需在合并模块再次挂接。</div>

          <el-alert
            v-if="form.report_scope === 'consolidated'"
            type="info"
            :closable="false"
            show-icon
            style="margin-top: 12px"
          >
            合并项目会自动生成「合并」「合并差额」「母公司」三个节点；抵销与调整分录记在合并差额节点。
          </el-alert>
        </div>
      </div>
    </el-form>

    <!-- 业务分类标准参考弹窗 -->
    <el-dialog v-model="showCategoryReference" title="鉴证业务分类标准（2025年12月修订）" width="960px" top="3vh" append-to-body>
      <BusinessCategoryFlowChart
        :selected-category="currentCategoryLetter"
        @select="onCategorySelect"
        @jump="jumpToWp"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { api } from '@/services/apiProxy'
import { fetchTemplateRecommendation, type TemplateRecommendation } from '@/services/commonApi'
import { useWizardStore, type BasicInfo } from '@/stores/wizard'
import { validateUSCC } from '@/utils/uscc_validator'
import {
  RELATION_OPTIONS,
  SELF_REFERENCE_CONFIRM,
  effectiveParentCode,
  inferRelationFromName,
  selfReferenceKind,
  type GroupRelation,
} from '@/utils/groupRelation'
import BusinessCategoryFlowChart from '@/components/project/BusinessCategoryFlowChart.vue'

const router = useRouter()
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

const showCategoryReference = ref(false)

const currentCategoryLetter = computed(() => {
  const map: Record<string, string> = { type_a: 'A', type_b: 'B', type_c: 'C' }
  return map[form.company_subtype] || ''
})

function onCategorySelect(value: string) {
  form.company_subtype = value
  showCategoryReference.value = false
}

function jumpToWp(wpCode: string) {
  const projectId = wizardStore.projectId
  if (projectId) {
    showCategoryReference.value = false
    router.push({ name: 'WorkpaperByCode', params: { projectId }, query: { wp_code: wpCode } })
  }
}

/**
 * 「待确认业务类型」非阻断横幅（需求 1.7 ③ / 14.3）。
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

/** 拉取业务类型推荐（需求 7.6：须预填建议值，不仅高亮）。 */
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
  parent_company_name: '',
  parent_company_code: '',
  relation_to_parent: '',
  ultimate_company_name: '',
  ultimate_company_code: '',
  signing_partner_id: null,
  manager_id: null,
  budget_hours: null,
  contract_amount: null,
})

// ─── 集团架构：与上级关系联动（需求 1.3 / 1.5 / 2.3 / 2.4）──────────────────────
// 没有有效上级（上级代码为空，或就是本企业代码）⇒ 下拉置灰且值为空；
// 有有效上级 ⇒ 必填，默认按企业名称推断并随名称变化；
// 用户手动选过（或已保存过）的值优先，之后改名称、清空再填上级代码都不再覆盖。
const hasEffectiveParent = computed(
  () => effectiveParentCode(form.company_code, form.parent_company_code) !== null,
)
/** 上级代码 = 本企业代码时的含义：'top' 本企业就是上级企业 / 'ultimate' 三码相同即最终控制方 */
const selfKind = computed(
  () => selfReferenceKind(form.company_code, form.parent_company_code, form.ultimate_company_code),
)
const selfKindHint = computed(() => {
  if (selfKind.value === 'ultimate') return '三个代码相同：本企业即为最终控制方（集团总部或母公司）'
  if (selfKind.value === 'top') return '与本企业代码相同：表示本企业就是上级企业（集团顶层），无需选择与上级关系'
  return ''
})
const relationPlaceholder = computed(() => {
  if (hasEffectiveParent.value) return '请选择与上级关系'
  return selfKind.value ? '本企业就是上级企业，无需选择' : '先填写上级代码'
})
const manualRelation = ref<GroupRelation | ''>('')

function onRelationChange(value: GroupRelation | '' | undefined) {
  manualRelation.value = value || ''
}

function syncRelationDefault() {
  if (!hasEffectiveParent.value) {
    form.relation_to_parent = ''
    return
  }
  form.relation_to_parent = manualRelation.value || inferRelationFromName(form.client_name)
}

watch(() => [form.parent_company_code, form.client_name, form.company_code], syncRelationDefault)

// 需求 1.5：上级代码 = 本企业代码不拒绝，保存前请用户确认；同一组代码确认过（或回填自已保存数据）不再问
const confirmedSelfKey = ref('')

function groupCodeKey(): string {
  return [form.company_code, form.parent_company_code, form.ultimate_company_code]
    .map((code) => (code || '').trim())
    .join('|')
}

async function confirmSelfReference(): Promise<boolean> {
  const kind = selfKind.value
  if (!kind) return true
  const key = groupCodeKey()
  if (key === confirmedSelfKey.value) return true
  try {
    await ElMessageBox.confirm(SELF_REFERENCE_CONFIRM[kind], '请确认集团关系', {
      confirmButtonText: kind === 'ultimate' ? '确认，本企业即最终控制方' : '确认，本企业就是上级企业',
      cancelButtonText: '返回修改',
      type: 'warning',
    })
  } catch {
    return false
  }
  confirmedSelfKey.value = key
  return true
}

/** 回填已保存数据：旧数据可能带已停用的 consolidation_type，丢弃；已保存的关系视为手选 */
function applySaved(saved: Partial<BasicInfo> & Record<string, unknown>) {
  const rest: Record<string, unknown> = { ...saved }
  delete rest.consolidation_type
  Object.assign(form, rest)
  for (const key of ['parent_company_name', 'parent_company_code', 'relation_to_parent',
    'ultimate_company_name', 'ultimate_company_code'] as const) {
    if (form[key] == null) form[key] = ''
  }
  const savedRelation = form.relation_to_parent
  manualRelation.value = savedRelation === 'subsidiary' || savedRelation === 'branch' ? savedRelation : ''
  // 已保存的「上级=本企业」当时已确认过（或经批量预校验提示），回填后再保存不重复询问
  confirmedSelfKey.value = selfKind.value ? groupCodeKey() : ''
  if (saved.audit_year) {
    auditYearDate.value = String(saved.audit_year)
  }
}

/** 选填的统一社会信用代码校验（前后端同一规则，需求 1.4） */
function optionalUsccValidator(_rule: unknown, value: string, callback: (err?: Error) => void) {
  const code = (value || '').trim()
  if (!code) {
    callback()
    return
  }
  const result = validateUSCC(code)
  callback(result.valid ? undefined : new Error(result.message))
}

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
  // 上级代码可以等于本企业代码（需求 1.5：本企业就是上级企业，保存前弹确认），这里只校验格式
  parent_company_code: [{ validator: optionalUsccValidator, trigger: ['blur', 'change'] }],
  relation_to_parent: [{
    validator: (_rule, value: string, callback) => {
      if (hasEffectiveParent.value && !value) {
        callback(new Error('请选择与上级关系'))
        return
      }
      callback()
    },
    trigger: 'change',
  }],
  ultimate_company_code: [{ validator: optionalUsccValidator, trigger: ['blur', 'change'] }],
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
  const saved = wizardStore.stepData.basic_info as unknown as (BasicInfo & Record<string, unknown>) | undefined
  if (saved) {
    applySaved(saved)
  }
  if (form.template_type === 'custom') {
    await loadCustomTemplates()
    if (form.custom_template_id) {
      onCustomTemplateChange(form.custom_template_id)
    }
  }
  // 需求 7.6：已有项目进入向导时拉取业务类型推荐并预填
  await loadRecommendation()
})

// 兜底：store 异步加载完成后填充表单（解决组件挂载时 store 还在 loading 的时序问题）
watch(() => wizardStore.stepData.basic_info, (newVal) => {
  if (newVal && !form.client_name) {
    applySaved(newVal as Partial<BasicInfo> & Record<string, unknown>)
  }
}, { immediate: false })

async function validate(): Promise<BasicInfo | null> {
  if (!formRef.value) return null
  try {
    await formRef.value.validate()
  } catch {
    return null
  }
  // 用户取消确认 ⇒ 停留在表单，不保存
  if (!(await confirmSelfReference())) return null
  // 没有有效上级时关系必须为空（后端同样强制，这里保证提交值自洽）
  return { ...form, relation_to_parent: hasEffectiveParent.value ? form.relation_to_parent : '' }
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

/* 业务类型系统建议 */
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

/* 业务类型参考链接 */
.gt-category-ref-link { margin-left: 8px; font-size: 12px; }

/* 上级代码 = 本企业代码时的说明 */
.gt-self-ref-hint {
  width: 100%;
  margin-top: 4px;
  font-size: var(--gt-font-size-xs);
  line-height: 1.4;
  color: var(--gt-color-warning, #e6a23c);
}

/* 集团架构说明 */
.gt-group-hint {
  margin: -4px 0 0 120px;
  font-size: var(--gt-font-size-xs);
  line-height: 1.5;
  color: var(--gt-color-text-tertiary);
}
@media (max-width: 768px) {
  .gt-group-hint { margin-left: 0; }
}
</style>
