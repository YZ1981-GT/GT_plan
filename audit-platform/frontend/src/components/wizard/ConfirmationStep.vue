<template>
  <div class="gt-confirmation-step">
    <h2 class="step-title">确认项目配置</h2>
    <p class="step-desc">请确认以下项目配置信息，确认后项目将进入计划阶段</p>

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
        <h3 class="card-title">科目导入</h3>
        <div class="card-body">
          <div class="info-row">
            <span class="info-label">状态</span>
            <span class="info-value">
              <el-tag v-if="isStepCompleted('account_import')" type="success" size="small">已完成</el-tag>
              <el-tag v-else type="info" size="small">待完成</el-tag>
            </span>
          </div>
        </div>
      </div>

      <!-- Account Mapping -->
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
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useWizardStore, type BasicInfo } from '@/stores/wizard'

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

const basicInfo = computed<BasicInfo>(() => {
  return (wizardStore.stepData.basic_info as unknown as BasicInfo) ?? {
    client_name: '',
    audit_year: null,
    project_type: '',
    accounting_standard: '',
    signing_partner_id: '',
    manager_id: '',
  }
})

const projectTypeLabel = computed(() => PROJECT_TYPE_MAP[basicInfo.value.project_type] ?? '—')
const standardLabel = computed(() => STANDARD_MAP[basicInfo.value.accounting_standard] ?? '—')

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
  font-size: 20px;
}

.step-desc {
  color: #999;
  margin-bottom: var(--gt-space-6);
  font-size: 14px;
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
  font-size: 16px;
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
  font-size: 14px;
}

.info-label {
  color: #999;
}

.info-value {
  color: #333;
  font-weight: 500;
}
</style>
