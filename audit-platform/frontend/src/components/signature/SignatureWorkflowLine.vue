<!--
  SignatureWorkflowLine — R1 需求 4 签字流水线时间线组件

  显示三级签字的 order / role / status 时间线。
  当前用户 ready 的 step 高亮。
-->
<template>
  <div class="gt-sig-workflow">
    <div class="gt-sig-workflow-title">签字流水线</div>
    <div class="gt-sig-timeline">
      <div
        v-for="step in props.workflow"
        :key="step.order"
        class="gt-sig-step"
        :class="{
          'gt-sig-step--waiting': step.status === 'waiting',
          'gt-sig-step--ready': step.status === 'ready',
          'gt-sig-step--signed': step.status === 'signed',
        }"
      >
        <div class="gt-sig-step-icon">
          <span v-if="step.status === 'signed'" class="gt-sig-icon gt-sig-icon--signed">✓</span>
          <span v-else-if="step.status === 'ready'" class="gt-sig-icon gt-sig-icon--ready">●</span>
          <span v-else class="gt-sig-icon gt-sig-icon--waiting">○</span>
        </div>
        <div class="gt-sig-step-connector" v-if="step.order < maxOrder" />
        <div class="gt-sig-step-content">
          <div class="gt-sig-step-label">
            <span class="gt-sig-step-order">第 {{ step.order }} 级</span>
            <span class="gt-sig-step-role">{{ roleLabel(step.role) }}</span>
          </div>
          <div class="gt-sig-step-meta">
            <template v-if="step.status === 'signed'">
              <span class="gt-sig-step-signer">{{ step.signed_by || '—' }}</span>
              <span class="gt-sig-step-time">{{ formatTime(step.signed_at) }}</span>
            </template>
            <template v-else-if="step.status === 'ready'">
              <el-tag size="small" type="primary" effect="light">等待签字</el-tag>
            </template>
            <template v-else>
              <el-tag size="small" type="info" effect="light">未到</el-tag>
            </template>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export interface WorkflowStep {
  order: number
  role: string
  required_user_id?: string | null
  status: 'waiting' | 'ready' | 'signed'
  signed_at?: string | null
  signed_by?: string | null
}

const props = defineProps<{
  workflow: WorkflowStep[]
}>()

const ROLE_MAP: Record<string, string> = {
  auditor: '项目组长',
  manager: '项目经理',
  partner: '签字合伙人',
  eqcr: '独立复核',
  archive_signer: '归档签字',
  project_manager: '项目经理',
  qc_reviewer: '质控复核',
  signing_partner: '签字合伙人',
}

const maxOrder = computed(() => {
  if (!props.workflow || !props.workflow.length) return 0
  return Math.max(...props.workflow.map(s => s.order))
})

function roleLabel(role: string): string {
  return ROLE_MAP[role] || role
}

function formatTime(ts: string | null | undefined): string {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  } catch {
    return ts
  }
}
</script>

<style scoped>
.gt-sig-workflow {
  padding: 12px 0;
}

.gt-sig-workflow-title {
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
  margin-bottom: 12px;
}

.gt-sig-timeline {
  display: flex;
  flex-direction: column;
  gap: 0;
  position: relative;
}

.gt-sig-step {
  display: flex;
  align-items: flex-start;
  position: relative;
  padding-bottom: 20px;
}

.gt-sig-step:last-child {
  padding-bottom: 0;
}

.gt-sig-step-icon {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  position: relative;
  z-index: 1;
}

.gt-sig-icon {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--gt-font-size-xs);
  font-weight: 600;
}

.gt-sig-icon--signed {
  background: var(--gt-color-success);
  color: var(--gt-color-text-inverse);
}

.gt-sig-icon--ready {
  background: var(--gt-color-teal);
  color: var(--gt-color-text-inverse);
  animation: pulse-ready 1.5s ease-in-out infinite;
}

.gt-sig-icon--waiting {
  background: var(--gt-color-border-light);
  color: var(--gt-color-info);
}

@keyframes pulse-ready {
  0%, 100% { box-shadow: 0 0 0 0 rgba(64, 158, 255, 0.4); }
  50% { box-shadow: 0 0 0 6px rgba(64, 158, 255, 0); }
}

.gt-sig-step-connector {
  position: absolute;
  left: 13px;
  top: 28px;
  width: 2px;
  height: calc(100% - 28px);
  z-index: 0;
}

.gt-sig-step--signed .gt-sig-step-connector {
  background: var(--gt-color-success);
}

.gt-sig-step--ready .gt-sig-step-connector {
  background: linear-gradient(to bottom, #409eff, #e4e7ed);
}

.gt-sig-step--waiting .gt-sig-step-connector {
  background: var(--gt-color-border-light);
}

.gt-sig-step-content {
  margin-left: 12px;
  flex: 1;
}

.gt-sig-step-label {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gt-sig-step-order {
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
}

.gt-sig-step-role {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary, #606266);
}

.gt-sig-step-meta {
  margin-top: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--gt-font-size-xs);
}

.gt-sig-step-signer {
  color: var(--gt-color-text-secondary, #606266);
}

.gt-sig-step-time {
  color: var(--gt-color-text-tertiary, #909399);
}

/* ready step 高亮 */
.gt-sig-step--ready .gt-sig-step-order {
  color: var(--gt-color-teal);
}

.gt-sig-step--ready .gt-sig-step-content {
  background: rgba(64, 158, 255, 0.04);
  border-radius: 6px;
  padding: 6px 10px;
  margin-left: 8px;
}
</style>
