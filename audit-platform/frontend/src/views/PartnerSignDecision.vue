<!--
  PartnerSignDecision — 合伙人签字决策面板 [R8-S2-06/07]

  三栏布局：
    左（35%）：GateReadinessPanel 就绪检查
    中（40%）：报告预览（优先 PDF blob，降级为 AuditReportEditor 只读模式嵌入）
    右（25%）：风险摘要（risk-summary 端点）

  底栏操作：← 回退到复核 / ✍️ 签字 / 📋 查看历史 / 🖨️ 打印
  签字流程：签字按钮走 confirmSignature（必须输入客户名匹配）
-->
<template>
  <div class="gt-psd gt-fade-in">
    <GtPageHeader :title="headerTitle" @back="onBack">
      <template #actions>
        <el-button size="small" @click="onViewHistory" round>📋 签字历史</el-button>
        <el-button size="small" @click="onPrint" round>🖨️ 打印</el-button>
      </template>
    </GtPageHeader>

    <div class="gt-psd-body">
      <!-- 左栏：就绪检查 -->
      <div class="gt-psd-left">
        <div class="gt-psd-section-title">就绪检查</div>
        <div v-if="readinessLoading" v-loading="true" style="min-height: 200px" />
        <GateReadinessPanel
          v-else-if="readinessData"
          :data="readinessData"
          :loading="readinessLoading"
        />
        <el-empty v-else description="未获取到就绪检查数据" />
      </div>

      <!-- 中栏：报告预览（降级 HTML） -->
      <div class="gt-psd-center">
        <div class="gt-psd-section-title">
          审计报告预览
          <el-tag v-if="reportStatus" size="small" :type="reportStatusTagType">{{ reportStatusLabel }}</el-tag>
        </div>
        <div v-if="reportLoading" v-loading="true" style="min-height: 400px" />
        <div v-else-if="reportHtml" class="gt-psd-report-preview" v-html="reportHtml" />
        <el-empty v-else description="未获取到审计报告" />
      </div>

      <!-- 右栏：风险摘要 -->
      <div class="gt-psd-right">
        <div class="gt-psd-section-title">风险摘要</div>
        <div v-if="riskLoading" v-loading="true" style="min-height: 200px" />
        <div v-else-if="riskSummary" class="gt-psd-risk-list">
          <!-- 汇总标签 -->
          <div class="gt-psd-risk-summary">
            <el-tag v-if="riskSummary.summary.can_sign" type="success" size="large">✓ 可以签字</el-tag>
            <el-tag v-else type="danger" size="large">
              ⚠️ {{ riskSummary.summary.total_blockers }} 项阻塞
            </el-tag>
            <el-tag v-if="riskSummary.summary.total_warnings > 0" type="warning" size="small" style="margin-left: 4px">
              {{ riskSummary.summary.total_warnings }} 项警告
            </el-tag>
          </div>

          <!-- 高严重度问题单 -->
          <div v-if="riskSummary.high_findings.length" class="gt-psd-risk-group">
            <div class="gt-psd-risk-group-title">🔴 高严重度问题（{{ riskSummary.high_findings.length }}）</div>
            <div v-for="f in riskSummary.high_findings" :key="f.id" class="gt-psd-risk-item">
              <span class="gt-psd-risk-dot gt-psd-risk-dot--red" />
              <span class="gt-psd-risk-text">{{ f.title }}</span>
            </div>
          </div>

          <!-- 重大错报 -->
          <div v-if="riskSummary.material_misstatements.length" class="gt-psd-risk-group">
            <div class="gt-psd-risk-group-title">💰 超重要性错报（{{ riskSummary.material_misstatements.length }}）</div>
            <div v-for="m in riskSummary.material_misstatements" :key="m.id" class="gt-psd-risk-item">
              <span class="gt-psd-risk-dot gt-psd-risk-dot--red" />
              <span class="gt-psd-risk-text">
                {{ m.description || '无描述' }}
                <small style="color: var(--gt-color-text-tertiary)">净额 {{ fmtAmt(m.net_amount) }}</small>
              </span>
            </div>
          </div>

          <!-- 被拒未转 AJE -->
          <div v-if="riskSummary.unconverted_rejected_aje.length" class="gt-psd-risk-group">
            <div class="gt-psd-risk-group-title">📝 被拒未转错报 AJE（{{ riskSummary.unconverted_rejected_aje.length }}）</div>
            <div v-for="a in riskSummary.unconverted_rejected_aje" :key="a.id" class="gt-psd-risk-item">
              <span class="gt-psd-risk-dot gt-psd-risk-dot--red" />
              <span class="gt-psd-risk-text">{{ a.adjustment_no }} {{ a.description }}</span>
            </div>
          </div>

          <!-- 持续经营 -->
          <div v-if="riskSummary.going_concern_flag" class="gt-psd-risk-group">
            <div class="gt-psd-risk-group-title">🏢 持续经营风险</div>
            <div class="gt-psd-risk-item">
              <span class="gt-psd-risk-dot gt-psd-risk-dot--red" />
              <span class="gt-psd-risk-text">评估结论非"持续经营恰当"</span>
            </div>
          </div>

          <!-- 未解决复核意见（警告） -->
          <div v-if="riskSummary.unresolved_comments.length" class="gt-psd-risk-group">
            <div class="gt-psd-risk-group-title">💬 未解决复核意见（{{ riskSummary.unresolved_comments.length }}）</div>
            <div v-for="c in riskSummary.unresolved_comments.slice(0, 5)" :key="c.id" class="gt-psd-risk-item">
              <span class="gt-psd-risk-dot gt-psd-risk-dot--yellow" />
              <span class="gt-psd-risk-text">{{ c.content }}</span>
            </div>
            <div v-if="riskSummary.unresolved_comments.length > 5" class="gt-psd-risk-more">
              还有 {{ riskSummary.unresolved_comments.length - 5 }} 条...
            </div>
          </div>
        </div>
        <el-empty v-else description="未获取到风险数据" />
      </div>
    </div>

    <!-- 底栏操作 -->
    <div class="gt-psd-footer">
      <el-button size="default" @click="onReturnToReview">← 回退到复核</el-button>
      <span style="flex: 1" />
      <el-tooltip
        v-if="!canSign"
        content="存在阻塞项，请先处理风险摘要中的红色条目"
        placement="top"
      >
        <span>
          <el-button size="default" type="danger" disabled>
            ✍️ 签字（{{ riskSummary?.summary.total_blockers || 0 }} 项阻塞）
          </el-button>
        </span>
      </el-tooltip>
      <el-button
        v-else
        size="default"
        type="primary"
        :loading="signing"
        v-permission="'sign:execute'"
        @click="onSign"
      >
        ✍️ 签字
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import * as P from '@/services/apiPaths'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import GateReadinessPanel from '@/components/gate/GateReadinessPanel.vue'
import type { GateReadinessData } from '@/components/gate/GateReadinessPanel.vue'
import { getSignReadinessV2, signDocument } from '@/services/signatureApi'
import { api } from '@/services/apiProxy'
import { REPORT_STATUS } from '@/constants/statusEnum'
import { confirmSignature } from '@/utils/confirm'
import { feedback } from '@/utils/feedback'
import { handleApiError } from '@/utils/errorHandler'
import { fmtAmount as fmtAmt } from '@/utils/formatters'
import { useAuthStore } from '@/stores/auth'

interface RiskSummaryData {
  high_findings: Array<{ id: string; title: string; severity: string; status: string; category: string; created_at: string | null }>
  unresolved_comments: Array<{ id: string; content: string; wp_id: string | null; created_at: string | null }>
  material_misstatements: Array<{ id: string; description: string; net_amount: number; threshold: number }>
  unconverted_rejected_aje: Array<{ id: string; adjustment_no: string; description: string; total_debit: number; total_credit: number }>
  ai_flags: any[]
  budget_overrun: boolean
  sla_breached: any[]
  going_concern_flag: boolean
  summary: {
    total_blockers: number
    total_warnings: number
    can_sign: boolean
  }
}

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const projectId = computed(() => route.params.projectId as string)
const year = computed(() => Number(route.params.year) || new Date().getFullYear() - 1)

// ── 数据状态 ──
const clientName = ref('')
const readinessData = ref<GateReadinessData | null>(null)
const readinessLoading = ref(false)
const reportHtml = ref('')
const reportStatus = ref('')
const reportLoading = ref(false)
const riskSummary = ref<RiskSummaryData | null>(null)
const riskLoading = ref(false)
const signing = ref(false)

const headerTitle = computed(() => `签字决策 — ${clientName.value || '项目'} ${year.value} 年度`)

const canSign = computed(() => {
  if (!riskSummary.value) return false
  return riskSummary.value.summary.can_sign
})

const reportStatusLabel = computed(() => {
  const map: Record<string, string> = {
    draft: '草稿',
    review: '审阅中',
    eqcr_approved: 'EQCR 已批准',
    final: '已定稿',
  }
  return map[reportStatus.value] || reportStatus.value
})

const reportStatusTagType = computed<'primary' | 'info' | 'warning' | 'success' | 'danger' | undefined>(() => {
  if (reportStatus.value === REPORT_STATUS.FINAL) return 'success'
  if (reportStatus.value === REPORT_STATUS.EQCR_APPROVED) return 'success'
  if (reportStatus.value === REPORT_STATUS.REVIEW) return 'warning'
  return 'info'
})

// ── 加载 ──
async function loadProject() {
  try {
    const data: any = await api.get(P.projects.detail(projectId.value))
    clientName.value = data?.client_name || data?.name || ''
  } catch { /* ignore */ }
}

async function loadReadiness() {
  readinessLoading.value = true
  try {
    readinessData.value = await getSignReadinessV2(projectId.value)
  } catch (e) {
    handleApiError(e, '加载就绪检查')
  } finally {
    readinessLoading.value = false
  }
}

async function loadReport() {
  reportLoading.value = true
  try {
    const data: any = await api.get(P.auditReport.get(projectId.value, year.value))
    reportStatus.value = data?.status || 'draft'
    // 拼 HTML 预览（降级方案：不使用 PDF 预览端点，直接渲染 paragraphs）
    const paragraphs = data?.paragraphs || {}
    const orderedSections = [
      ['title', '报告标题'],
      ['addressee', '收件人'],
      ['opinion_section', '审计意见'],
      ['basis_section', '形成审计意见的基础'],
      ['kam_section', '关键审计事项'],
      ['other_information', '其他信息'],
      ['responsibilities_management', '管理层责任'],
      ['responsibilities_auditor', '注册会计师责任'],
    ]
    reportHtml.value = orderedSections
      .filter(([key]) => paragraphs[key])
      .map(([key, label]) => `<h3>${label}</h3><div>${paragraphs[key]}</div>`)
      .join('')
  } catch (e) {
    reportHtml.value = ''
  } finally {
    reportLoading.value = false
  }
}

async function loadRiskSummary() {
  riskLoading.value = true
  try {
    const data = await api.get<RiskSummaryData>(P.projects.riskSummary(projectId.value))
    riskSummary.value = data
  } catch (e) {
    handleApiError(e, '加载风险摘要')
  } finally {
    riskLoading.value = false
  }
}

// ── 操作 ──
function onBack() { router.push(`/dashboard/partner`) }
function onViewHistory() { router.push('/extension/signatures') }
function onPrint() { window.print() }
function onReturnToReview() {
  router.push({ name: 'AuditReport', params: { projectId: projectId.value }, query: { year: String(year.value) } })
}

async function onSign() {
  if (!canSign.value) {
    ElMessage.warning('存在阻塞项，无法签字')
    return
  }
  // 必须输入客户名匹配才能确认
  try {
    const confirmed = await confirmSignature(clientName.value, '年度审计报告')
    if (!confirmed) return
  } catch {
    return  // 用户取消
  }

  signing.value = true
  try {
    // 找报告 ID
    const reportData: any = await api.get(P.auditReport.get(projectId.value, year.value))
    if (!reportData?.id) {
      ElMessage.error('未找到报告，请先生成')
      return
    }
    const userId = authStore.user?.id
    if (!userId) {
      ElMessage.error('用户未登录')
      return
    }
    await signDocument({
      object_type: 'audit_report',
      object_id: reportData.id,
      signer_id: userId,
      signature_level: 'signing_partner',
      project_id: projectId.value,
      required_role: 'signing_partner',
      required_order: 3,
    })
    feedback.success(`✍️ 已签字 · ${clientName.value} ${year.value} 年度审计报告`)
    // 刷新状态
    await Promise.all([loadReadiness(), loadReport()])
  } catch (e: any) {
    handleApiError(e, '签字')
  } finally {
    signing.value = false
  }
}

onMounted(() => {
  loadProject()
  loadReadiness()
  loadReport()
  loadRiskSummary()
})
</script>

<style scoped>
.gt-psd { padding: var(--gt-space-4); display: flex; flex-direction: column; height: 100%; }

.gt-psd-body {
  flex: 1; display: grid;
  grid-template-columns: 35% 40% 25%;
  gap: var(--gt-space-3);
  margin: var(--gt-space-3) 0;
  min-height: 0;
}

.gt-psd-left, .gt-psd-center, .gt-psd-right {
  background: var(--gt-color-bg-white);
  border: 1px solid var(--gt-color-border-light);
  border-radius: var(--gt-radius-md);
  padding: var(--gt-space-3);
  overflow-y: auto;
}

.gt-psd-section-title {
  font-size: var(--gt-font-size-md);
  font-weight: 600;
  color: var(--gt-color-text);
  margin-bottom: var(--gt-space-3);
  padding-bottom: var(--gt-space-2);
  border-bottom: 2px solid var(--gt-color-primary);
  display: flex; align-items: center; gap: var(--gt-space-2);
}

/* 报告预览 */
.gt-psd-report-preview {
  font-size: var(--gt-font-size-sm);
  line-height: 1.8;
  color: var(--gt-color-text);
}
.gt-psd-report-preview :deep(h3) {
  font-size: var(--gt-font-size-base);
  font-weight: 600;
  color: var(--gt-color-primary);
  margin: var(--gt-space-4) 0 var(--gt-space-2);
}

/* 风险摘要 */
.gt-psd-risk-summary {
  text-align: center;
  padding: var(--gt-space-3);
  background: var(--gt-color-bg-elevated);
  border-radius: var(--gt-radius-sm);
  margin-bottom: var(--gt-space-3);
}
.gt-psd-risk-group { margin-bottom: var(--gt-space-3); }
.gt-psd-risk-group-title {
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-text);
  margin-bottom: var(--gt-space-2);
}
.gt-psd-risk-item {
  display: flex; align-items: flex-start; gap: 6px;
  padding: 4px 0;
  font-size: var(--gt-font-size-xs);
  line-height: 1.5;
}
.gt-psd-risk-dot {
  width: 8px; height: 8px; border-radius: 50%;
  flex-shrink: 0; margin-top: 6px;
}
.gt-psd-risk-dot--red { background: var(--gt-color-coral); }
.gt-psd-risk-dot--yellow { background: var(--gt-color-wheat); }
.gt-psd-risk-text { flex: 1; color: var(--gt-color-text); word-break: break-word; }
.gt-psd-risk-more {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
  padding-left: 14px;
}

/* 底栏 */
.gt-psd-footer {
  display: flex; align-items: center; gap: var(--gt-space-2);
  padding: var(--gt-space-3) var(--gt-space-4);
  background: var(--gt-color-bg-white);
  border-top: 1px solid var(--gt-color-border-light);
  border-radius: var(--gt-radius-md);
}
</style>
