<template>
  <div class="gt-confirmation-step">
    <h2 class="step-title">确认项目配置</h2>
    <p class="step-desc">请确认以下项目配置信息，确认后项目将进入计划阶段</p>

    <el-alert
      v-if="pendingConfirmationStepLabels.length > 0"
      :title="`确认创建前仍需完成：${pendingConfirmationStepLabels.join('、')}`"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
    />

    <div class="summary-cards">
      <!-- Basic Info -->
      <div class="gt-card summary-card">
        <h3 class="card-title">基本信息</h3>
        <div class="card-body">
          <div class="info-row">
            <span class="info-label">客户名称</span>
            <span class="info-value">{{ basicInfo.client_name || '—' }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">审计年度</span>
            <span class="info-value">{{ basicInfo.audit_year || '—' }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">项目类型</span>
            <span class="info-value">{{ projectTypeLabel }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">会计准则</span>
            <span class="info-value">{{ standardLabel }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">附注模板</span>
            <span class="info-value">{{ templateLabel }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">签字合伙人</span>
            <span class="info-value">{{ basicInfo.signing_partner_id || '—' }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">项目经理</span>
            <span class="info-value">{{ basicInfo.manager_id || '—' }}</span>
          </div>
        </div>
      </div>

      <!-- Account Import -->
      <div class="gt-card summary-card">
        <h3 class="card-title">账套导入</h3>
        <div class="card-body">
          <div class="info-row">
            <span class="info-label">状态</span>
            <span class="info-value">
              <el-tag v-if="isStepCompleted('account_import')" type="success" size="small">已完成</el-tag>
              <el-tag v-else type="info" size="small">待完成</el-tag>
            </span>
          </div>
          <div class="info-row">
            <span class="info-label">科目数</span>
            <span class="info-value">{{ importedAccountCountLabel }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">导入年度</span>
            <span class="info-value">{{ importYearLabel }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">数据表记录</span>
            <span class="info-value">{{ importedDataRowCountLabel }}</span>
          </div>
        </div>
      </div>

      <div class="gt-card summary-card">
        <h3 class="card-title">科目映射</h3>
        <div class="card-body">
          <div class="info-row">
            <span class="info-label">状态</span>
            <span class="info-value">
              <el-tag v-if="isStepCompleted('account_mapping')" type="success" size="small">已完成</el-tag>
              <el-tag v-else type="info" size="small">待完成</el-tag>
            </span>
          </div>
          <div class="info-row">
            <span class="info-label">完成率</span>
            <span class="info-value">{{ mappingCompletionLabel }}</span>
          </div>
        </div>
      </div>

      <!-- Materiality -->
      <div class="gt-card summary-card">
        <h3 class="card-title">重要性水平</h3>
        <div class="card-body">
          <div class="info-row">
            <span class="info-label">状态</span>
            <span class="info-value">
              <el-tag v-if="isStepCompleted('materiality')" type="success" size="small">已完成</el-tag>
              <el-tag v-else type="info" size="small">待完成</el-tag>
            </span>
          </div>
        </div>
      </div>

      <!-- Team Assignment -->
      <div class="gt-card summary-card">
        <h3 class="card-title">团队分工</h3>
        <div class="card-body">
          <div class="info-row">
            <span class="info-label">状态</span>
            <span class="info-value">
              <el-tag v-if="isStepCompleted('team_assignment')" type="success" size="small">已完成</el-tag>
              <el-tag v-else type="info" size="small">待完成</el-tag>
            </span>
          </div>
          <template v-if="teamMembers.length">
            <div v-for="m in teamMembers" :key="m.staff_id" class="info-row">
              <span class="info-label">{{ m.staff_name }}</span>
              <span class="info-value">{{ roleLabel(m.role) }} · {{ (m.assigned_cycles || []).join('/') || '全部' }}</span>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CONFIRMATION_REQUIRED_STEPS, STEP_LABELS, useWizardStore, type BasicInfo, type StepKey } from '@/stores/wizard'

const wizardStore = useWizardStore()

const PROJECT_TYPE_MAP: Record<string, string> = {
  annual: '年度审计',
  special: '专项审计',
  ipo: 'IPO审计',
  internal_control: '内控审计',
}

const STANDARD_MAP: Record<string, string> = {
  enterprise: '企业会计准则',
  small_enterprise: '小企业会计准则',
  financial: '金融企业会计准则',
  government: '政府会计准则',
}

const TEMPLATE_MAP: Record<string, string> = {
  soe: '国企版',
  listed: '上市版',
  custom: '自定义',
}

const basicInfo = computed<BasicInfo>(() => {
  return (wizardStore.stepData.basic_info as unknown as BasicInfo) ?? {
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
  }
})

const projectTypeLabel = computed(() => PROJECT_TYPE_MAP[basicInfo.value.project_type] ?? '—')
const standardLabel = computed(() => STANDARD_MAP[basicInfo.value.accounting_standard] ?? '—')
const templateLabel = computed(() => {
  if (basicInfo.value.template_type === 'custom') {
    const name = basicInfo.value.custom_template_name || TEMPLATE_MAP.custom
    return basicInfo.value.custom_template_version
      ? `${name}（${basicInfo.value.custom_template_version}）`
      : name
  }
  return TEMPLATE_MAP[basicInfo.value.template_type] ?? '—'
})

const accountImport = computed<Record<string, unknown>>(() => {
  return (wizardStore.stepData.account_import as Record<string, unknown> | undefined) ?? {}
})

const accountMapping = computed<Record<string, unknown>>(() => {
  return (wizardStore.stepData.account_mapping as Record<string, unknown> | undefined) ?? {}
})

const importedAccountCountLabel = computed(() => {
  const total = accountImport.value.total_imported
  return typeof total === 'number' ? total.toLocaleString() : '—'
})

const importYearLabel = computed(() => {
  const year = accountImport.value.year ?? basicInfo.value.audit_year
  return typeof year === 'number' ? String(year) : '—'
})

const importedDataRowCountLabel = computed(() => {
  const bySheet = accountImport.value.data_sheets_imported
  if (!bySheet || typeof bySheet !== 'object') return '—'

  const total = Object.values(bySheet as Record<string, unknown>).reduce<number>((sum, count) => {
    return sum + (typeof count === 'number' ? count : 0)
  }, 0)

  return total > 0 ? total.toLocaleString() : '—'
})

const mappingCompletionLabel = computed(() => {
  const rate = accountMapping.value.completion_rate
  const mapped = accountMapping.value.mapped_count
  const total = accountMapping.value.total_count

  if (typeof rate !== 'number' && typeof mapped !== 'number' && typeof total !== 'number') {
    return '—'
  }

  const rateLabel = typeof rate === 'number' ? `${rate}%` : '—'
  if (typeof mapped === 'number' && typeof total === 'number') {
    return `${rateLabel}（${mapped}/${total}）`
  }
  return rateLabel
})

const pendingConfirmationSteps = computed<StepKey[]>(() => {
  return CONFIRMATION_REQUIRED_STEPS.filter(step => !wizardStore.isStepCompleted(step))
})

const pendingConfirmationStepLabels = computed(() => {
  return pendingConfirmationSteps.value.map(step => STEP_LABELS[step])
})

const teamMembers = computed(() => {
  const ta = wizardStore.stepData.team_assignment as any
  return ta?.members || []
})

const ROLE_LABEL_MAP: Record<string, string> = {
  signing_partner: '签字合伙人', manager: '项目经理', auditor: '审计员', qc: '质控人员',
  eqcr: '独立复核合伙人',
}
function roleLabel(role: string) { return ROLE_LABEL_MAP[role] || role }
function isStepCompleted(step: string): boolean {
  return wizardStore.isStepCompleted(step)
}
</script>

<style scoped>
.gt-confirmation-step {
  max-width: 800px;
  margin: 0 auto;
}

.step-title {
  color: var(--gt-color-primary);
  margin-bottom: var(--gt-space-1);
  font-size: 20px /* allow-px: special */;
}

.step-desc {
  color: var(--gt-color-text-tertiary);
  margin-bottom: var(--gt-space-6);
  font-size: var(--gt-font-size-sm);
}

.summary-cards {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--gt-space-4);
}

.summary-card {
  padding: var(--gt-space-4);
}

.card-title {
  color: var(--gt-color-primary);
  font-size: var(--gt-font-size-md);
  margin-bottom: var(--gt-space-3);
  padding-bottom: var(--gt-space-2);
  border-bottom: 1px solid #eee;
}

.card-body {
  display: flex;
  flex-direction: column;
  gap: var(--gt-space-2);
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: var(--gt-font-size-sm);
}

.info-label {
  color: var(--gt-color-text-tertiary);
}

.info-value {
  color: var(--gt-color-text-primary);
  font-weight: 500;
}
</style>
