<template>
  <div class="partner-dashboard">
    <GtPageHeader title="合伙人看板" variant="banner" icon="🏛️" :show-back="false">
      <template #subtitle>
        <span v-if="overview">
          {{ overview.total_projects }} 个项目 · {{ overview.risk_alert_count }} 个风险预警 · {{ overview.pending_sign_count }} 个待签字
        </span>
      </template>
      <div class="gt-header-refresh-wrap">
        <el-button
          circle
          size="small"
          :loading="loading"
          :icon="Refresh"
          title="刷新"
          @click="loadAll"
        />
      </div>
      <template #actions>
        <DashboardViewSwitcher />
        <!-- 待签字项目一键跳转 [R9 F7-Partner Task 24] -->
        <el-button
          v-if="overview && overview.pending_sign_count > 0"
          size="small"
          type="warning"
          @click="goToPartnerSignDecision"
        >
          ✍️ 待签字项目 ({{ overview.pending_sign_count }})
        </el-button>
      </template>
    </GtPageHeader>

    <!-- 风险预警横幅（用户可关闭，组件 remount 后再次提示） -->
    <el-alert
      v-if="overview && overview.risk_alert_count > 0 && riskAlertVisible"
      type="warning"
      closable
      style="margin-bottom: 16px"
      @close="riskAlertVisible = false"
    >
      <template #title>
        ⚠️ {{ overview.risk_alert_count }} 个项目存在风险预警
      </template>
      <div v-for="a in overview.risk_alerts" :key="a.id" style="margin-top: 4px; font-size: var(--gt-font-size-sm)">
        <span style="font-weight: 600">{{ a.client_name || a.name }}</span>：{{ a.risk_reasons.join('、') }}
      </div>
    </el-alert>

    <!-- 独立性待声明提醒卡 -->
    <el-card v-if="pendingIndependenceProjects.projects.length" class="independence-reminder-card" shadow="hover" style="margin-bottom: 16px">
      <template #header>
        <div style="display: flex; align-items: center; gap: 8px">
          <span style="font-size: var(--gt-font-size-md)">📋</span>
          <span style="font-weight: 600">独立性待声明</span>
          <el-badge :value="pendingIndependenceProjects.total" type="warning" />
        </div>
      </template>
      <div class="independence-reminder-list">
        <div v-for="p in pendingIndependenceProjects.projects" :key="p.id" class="independence-reminder-item">
          <span class="independence-reminder-name">{{ p.client_name || p.name }}</span>
          <el-button size="small" type="warning" plain @click="goToIndependence(p.id)">
            去声明 →
          </el-button>
        </div>
      </div>
      <!-- Batch 3-10: has_more=true 时提供"加载更多"按钮 -->
      <div v-if="pendingIndependenceProjects.hasMore" class="independence-reminder-footer">
        <el-button
          link
          type="primary"
          :loading="pendingIndependenceLoadingMore"
          @click="loadMorePendingIndependence"
        >
          加载更多（还有 {{ Math.max(pendingIndependenceProjects.total - pendingIndependenceProjects.projects.length, 0) }} 个）
        </el-button>
      </div>
    </el-card>

    <!-- 轮换预警卡片 -->
    <el-card v-if="rotationWarnings.length" class="rotation-warning-card" shadow="hover" style="margin-bottom: 16px">
      <template #header>
        <div style="display: flex; align-items: center; gap: 8px">
          <span style="font-size: var(--gt-font-size-md)">🔄</span>
          <span style="font-weight: 600">轮换预警</span>
          <el-badge :value="rotationWarnings.length" type="danger" />
        </div>
      </template>
      <div class="rotation-warning-list">
        <div v-for="item in rotationWarnings" :key="item.staff_id + item.client_name" class="rotation-warning-item">
          <div class="rotation-warning-info">
            <span class="rotation-warning-name">{{ item.staff_name || item.staff_id }}</span>
            <span class="rotation-warning-sep">→</span>
            <span class="rotation-warning-client">{{ item.client_name }}</span>
            <el-tag
              :type="item.continuous_years >= item.rotation_limit ? 'danger' : 'warning'"
              size="small"
              style="margin-left: 8px"
            >
              连续 {{ item.continuous_years }} 年
            </el-tag>
            <el-tag v-if="item.current_override_id" type="success" size="small" style="margin-left: 4px">
              已 Override
            </el-tag>
          </div>
          <div class="rotation-warning-actions">
            <el-button
              v-if="item.continuous_years >= item.rotation_limit && !item.current_override_id"
              size="small"
              type="danger"
              plain
              @click="openOverrideDialog(item)"
            >
              申请 Override
            </el-button>
            <span v-else-if="item.continuous_years >= (item.rotation_limit - 1)" class="rotation-warning-hint">
              下年需轮换
            </span>
          </div>
        </div>
      </div>
    </el-card>

    <el-tabs v-model="activeTab">
      <!-- Tab 1: 项目总览 -->
      <el-tab-pane label="项目总览" name="projects">
        <el-table
          :data="overview?.projects || []"
          stripe
          border
          v-loading="loading"
          @row-click="onProjectClick"
          class="gt-projects-overview-table"
          style="cursor: pointer"
        >
          <el-table-column label="风险" width="70" align="center" resizable>
            <template #default="{ row }">
              <span :class="'gt-risk-dot gt-risk-dot--' + row.risk_level" />
            </template>
          </el-table-column>
          <el-table-column label="客户" prop="client_name" min-width="180" resizable show-overflow-tooltip />
          <el-table-column label="项目" prop="name" min-width="220" resizable show-overflow-tooltip />
          <el-table-column label="状态" min-width="100" resizable>
            <template #default="{ row }">
              <el-tag size="small" :type="(statusType(row.status)) || undefined">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="完成率" min-width="130" resizable>
            <template #default="{ row }">
              <el-progress :percentage="row.completion_rate" :stroke-width="6"
                :color="row.completion_rate >= 80 ? 'var(--gt-color-success)' : row.completion_rate >= 50 ? 'var(--gt-color-wheat)' : 'var(--gt-color-coral)'" />
            </template>
          </el-table-column>
          <el-table-column label="底稿" min-width="80" align="center" resizable>
            <template #default="{ row }"><span class="gt-amt">{{ row.wp_passed }}/{{ row.wp_total }}</span></template>
          </el-table-column>
          <el-table-column label="待复核" min-width="100" align="right" resizable>
            <template #default="{ row }">
              <span class="gt-amt" :style="{ color: row.wp_pending > 0 ? 'var(--gt-color-wheat)' : 'var(--gt-color-text-tertiary)' }">{{ row.wp_pending }}</span>
            </template>
          </el-table-column>
          <el-table-column label="退回" min-width="90" align="right" resizable>
            <template #default="{ row }">
              <span class="gt-amt" :style="{ color: row.wp_rejected > 0 ? 'var(--gt-color-coral)' : 'var(--gt-color-text-tertiary)' }">{{ row.wp_rejected }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="170" fixed="right">
            <template #default="{ row }">
              <div class="gt-row-actions-inline">
                <el-button size="small" link type="primary" @click.stop="goToProject(row.id)">进入</el-button>
                <el-button size="small" link @click.stop="checkSign(row.id)">签字检查</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Tab 2: 待签字 -->
      <el-tab-pane name="sign">
        <template #label>
          待签字
          <el-badge v-if="overview?.pending_sign_count" :value="overview.pending_sign_count" type="danger" style="margin-left: 4px" />
        </template>
        <div v-if="overview?.pending_sign?.length" class="sign-list">
          <div v-for="p in overview.pending_sign" :key="p.id" class="sign-card" @click="checkSign(p.id)">
            <div class="sign-card-left">
              <div class="sign-card-name">{{ p.client_name || p.name }}</div>
              <div class="sign-card-meta">{{ signCardText(p) }}</div>
            </div>
            <div class="sign-card-actions">
              <el-button size="small" plain @click.stop="goToReport(p.id)">查看报告</el-button>
              <el-button size="small" plain @click.stop="goToSignDecision(p.id, (p as any).audit_year || (p as any).year)">决策面板 →</el-button>
              <el-button type="primary" size="small" round>签字前检查 →</el-button>
            </div>
          </div>
        </div>
        <el-empty v-else description="暂无待签字项目" />
      </el-tab-pane>

      <!-- Tab 3: 团队效能 -->
      <el-tab-pane label="团队效能" name="team">
        <!-- KPI 卡片网格（与项目总览风险卡视觉风格统一）-->
        <div v-if="teamData" class="gt-team-kpi-grid">
          <div
            v-for="s in teamStats"
            :key="s.label"
            class="gt-team-kpi-card"
            :class="`gt-team-kpi-card--${s.tone}`"
          >
            <div class="gt-team-kpi-icon">{{ s.icon }}</div>
            <div class="gt-team-kpi-body">
              <div class="gt-team-kpi-num">{{ s.value }}</div>
              <div class="gt-team-kpi-label">{{ s.label }}</div>
            </div>
          </div>
        </div>

        <!-- 团队成员明细表 -->
        <el-table
          :data="teamData?.staff_metrics || []"
          stripe
          border
          v-loading="teamLoading"
          class="gt-team-staff-table"
        >
          <template #empty>
            <el-empty description="暂无团队成员效能数据" :image-size="60" />
          </template>
          <el-table-column label="人员" prop="user_name" min-width="160" resizable show-overflow-tooltip />
          <el-table-column label="底稿总数" prop="total" min-width="120" align="right" resizable>
            <template #default="{ row }"><span class="gt-amt">{{ row.total }}</span></template>
          </el-table-column>
          <el-table-column label="通过" prop="passed" min-width="100" align="right" resizable>
            <template #default="{ row }"><span class="gt-amt">{{ row.passed }}</span></template>
          </el-table-column>
          <el-table-column label="退回" min-width="100" align="right" resizable>
            <template #default="{ row }">
              <span class="gt-amt" :style="{ color: row.rejected > 0 ? 'var(--gt-color-coral)' : 'var(--gt-color-text-tertiary)' }">{{ row.rejected }}</span>
            </template>
          </el-table-column>
          <el-table-column label="通过率" min-width="220" resizable>
            <template #default="{ row }">
              <el-progress
                :percentage="row.pass_rate ?? 0"
                :stroke-width="8"
                :color="row.pass_rate >= 80 ? 'var(--gt-color-success)' : row.pass_rate >= 50 ? 'var(--gt-color-wheat)' : 'var(--gt-color-coral)'"
              />
            </template>
          </el-table-column>
          <el-table-column label="退回率" min-width="120" align="right" resizable>
            <template #default="{ row }">
              <span class="gt-amt" :style="{ color: row.reject_rate > 10 ? 'var(--gt-color-coral)' : 'var(--gt-color-text-tertiary)' }">{{ row.reject_rate ?? 0 }}%</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 签字前检查弹窗（改造版） -->
    <el-dialog v-model="showSignDialog" title="🖊️ 签字前检查" width="700" append-to-body destroy-on-close>
      <div v-loading="signLoading" style="min-height: 120px">
        <!-- 顶部：GateReadinessPanel -->
        <GateReadinessPanel
          v-if="readinessData"
          :data="readinessData"
          :loading="readinessLoading"
          :project-id="currentSignProjectId"
          :on-refresh="refreshReadiness"
        />

        <!-- 中部：签字流水线 -->
        <div v-if="workflowData && workflowData.length" style="margin-top: 16px">
          <SignatureWorkflowLine :workflow="workflowData" />
        </div>

        <!-- 底部：立即签字按钮 -->
        <div v-if="readinessData" class="gt-sign-action-bar">
          <el-button
            type="primary"
            size="large"
            :disabled="!canSign"
            :loading="signing"
            @click="handleSign"
          >
            立即签字
          </el-button>
          <div v-if="!canSign && readinessData" class="gt-sign-hint">
            <template v-if="!readinessData.ready">
              <div style="color: var(--gt-color-coral); font-weight: 600; margin-bottom: 4px">就绪检查未通过，无法签字</div>
              <div v-if="readinessData.groups?.length" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-info)">
                <template v-for="group in readinessData.groups" :key="group.id">
                  <div v-for="finding in group.findings" :key="finding.rule_code || finding.message" style="padding: 2px 0">
                    ❌ {{ finding.rule_code ? `[${finding.rule_code}]` : '' }} {{ finding.message }}
                  </div>
                </template>
              </div>
            </template>
            <template v-else-if="!myReadyStep">当前未轮到你签字</template>
          </div>
        </div>
      </div>
    </el-dialog>

    <!-- 轮换 Override 申请弹窗 -->
    <el-dialog v-model="showOverrideDialog" title="🔄 申请轮换 Override" width="520" append-to-body destroy-on-close>
      <div v-if="overrideTarget" style="margin-bottom: 16px">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="人员">{{ overrideTarget.staff_name || overrideTarget.staff_id }}</el-descriptions-item>
          <el-descriptions-item label="客户">{{ overrideTarget.client_name }}</el-descriptions-item>
          <el-descriptions-item label="连续年数">{{ overrideTarget.continuous_years }} 年</el-descriptions-item>
          <el-descriptions-item label="轮换上限">{{ overrideTarget.rotation_limit }} 年</el-descriptions-item>
        </el-descriptions>
      </div>
      <el-form label-position="top">
        <el-form-item label="Override 原因" required>
          <el-input
            v-model="overrideReason"
            type="textarea"
            :rows="4"
            placeholder="请说明需要继续委派的原因（如客户特殊性、无合适替代人选等）"
          />
        </el-form-item>
      </el-form>
      <div class="override-sign-status">
        <div class="override-sign-title">审批状态（需双签）</div>
        <div class="override-sign-item">
          <span>合规合伙人签字</span>
          <el-tag v-if="overrideResult?.approved_by_compliance_partner" type="success" size="small">已签</el-tag>
          <el-tag v-else type="info" size="small">待签</el-tag>
        </div>
        <div class="override-sign-item">
          <span>首席风控合伙人签字</span>
          <el-tag v-if="overrideResult?.approved_by_chief_risk_partner" type="success" size="small">已签</el-tag>
          <el-tag v-else type="info" size="small">待签</el-tag>
        </div>
      </div>
      <template #footer>
        <el-button @click="showOverrideDialog = false">取消</el-button>
        <el-button
          type="primary"
          :loading="overrideSubmitting"
          :disabled="!overrideReason.trim() || !!overrideResult"
          @click="submitOverride"
        >
          {{ overrideResult ? '已提交' : '提交申请' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useNavigationStack } from '@/composables/useNavigationStack'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import DashboardViewSwitcher from '@/components/dashboard/DashboardViewSwitcher.vue'
import { useAuthStore } from '@/stores/auth'
import {
  getPartnerOverview, getTeamEfficiency,
  type PartnerOverview, type TeamEfficiency,
} from '@/services/partnerApi'
import {
  getSignatureWorkflow, signDocument, getSignReadinessV2,
  type WorkflowStep,
} from '@/services/signatureApi'
import {
  checkRotation, createRotationOverride,
  type RotationCheckResult, type RotationOverrideResult,
} from '@/services/rotationApi'
import { api } from '@/services/apiProxy'
import { my as P_my } from '@/services/apiPaths'
import { PROJECT_STATUS } from '@/constants/statusEnum'
import type { GateReadinessData } from '@/components/gate/GateReadinessPanel.vue'
import GateReadinessPanel from '@/components/gate/GateReadinessPanel.vue'
import SignatureWorkflowLine from '@/components/signature/SignatureWorkflowLine.vue'
import { parseApiError } from '@/composables/useApiError'
import { handleApiError } from '@/utils/errorHandler'

const router = useRouter()
const { push: pushNavStack } = useNavigationStack()

/** 跳转前记录来源（按 Backspace 可返回当前 PartnerDashboard） */
function recordOrigin() {
  pushNavStack({ source_view: '/dashboard/partner', query: {} })
}
const authStore = useAuthStore()
const loading = ref(false)
const activeTab = ref('projects')

const overview = ref<PartnerOverview | null>(null)

// 风险预警横幅本次会话可见性：组件 unmount 即重置为 true，
// 切换路由回来 / 刷新 dashboard 都会重新提示（与 ManagerDashboard 待审批工时横幅同语义）
const riskAlertVisible = ref(true)
const teamData = ref<TeamEfficiency | null>(null)
const teamLoading = ref(false)

// 签字弹窗状态
const showSignDialog = ref(false)
const signLoading = ref(false)
const signing = ref(false)
const currentSignProjectId = ref('')
const readinessData = ref<GateReadinessData | null>(null)
const readinessLoading = ref(false)
const workflowData = ref<WorkflowStep[]>([])

// 缓存每个项目的 workflow 用于 sign-list 卡片文案
const projectWorkflowCache = ref<Record<string, WorkflowStep[]>>({})

// 轮换预警
interface RotationWarningItem extends RotationCheckResult {
  staff_name?: string
}
const rotationWarnings = ref<RotationWarningItem[]>([])

// Override 弹窗状态
const showOverrideDialog = ref(false)
const overrideTarget = ref<RotationWarningItem | null>(null)
const overrideReason = ref('')
const overrideSubmitting = ref(false)
const overrideResult = ref<RotationOverrideResult | null>(null)
const teamStats = computed(() => {
  const s = teamData.value?.summary
  if (!s) return []
  const fmtPct = (v: number | null | undefined): string => {
    return v == null || Number.isNaN(v) ? '—' : `${v}%`
  }
  const fmtNum = (v: number | null | undefined): string | number => {
    return v == null || Number.isNaN(v) ? '—' : v
  }
  return [
    { label: '团队人数',   value: fmtNum(s.total_staff),       icon: '👥', tone: 'primary' },
    { label: '底稿总数',   value: fmtNum(s.total_workpapers),  icon: '📄', tone: 'teal' },
    { label: '平均通过率', value: fmtPct(s.avg_pass_rate),     icon: '✅', tone: 'success' },
    { label: '平均退回率', value: fmtPct(s.avg_reject_rate),   icon: '⚠️', tone: 'coral' },
    { label: '人均底稿',   value: fmtNum(s.avg_per_person),    icon: '📊', tone: 'wheat' },
  ]
})

// 独立性待声明项目（Batch 3-3: 改为结构化对象，区分 total/hasMore/projects）
interface PendingIndependenceProject {
  id: string
  name?: string
  client_name?: string | null
  status?: string | null
}
const pendingIndependenceProjects = ref<{
  projects: PendingIndependenceProject[]
  total: number
  hasMore: boolean
}>({ projects: [], total: 0, hasMore: false })
const pendingIndependenceLoadingMore = ref(false)

function goToIndependence(pid: string) {
  recordOrigin()
  router.push(`/projects/${pid}/independence`)
}

// 当前用户 ready 的 step
const myReadyStep = computed(() => {
  if (!workflowData.value || !workflowData.value.length) return null
  const userId = authStore.userId
  // 找到 status=ready 且 required_user_id 匹配当前用户（或无指定用户）的 step
  return workflowData.value.find(
    s => s.status === 'ready' && (!s.required_user_id || s.required_user_id === userId)
  ) || null
})

// 是否可签字
const canSign = computed(() => {
  return !!(readinessData.value?.ready && myReadyStep.value)
})

function statusLabel(s: string) {
  const m: Record<string, string> = { created: '已创建', planning: '计划中', execution: '执行中', completion: '完成中', reporting: '报告中', archived: '已归档' }
  return m[s] || s
}
function statusType(s: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  if (s === PROJECT_STATUS.ARCHIVED) return 'success'
  if (s === PROJECT_STATUS.EXECUTION) return ''
  if (s === PROJECT_STATUS.REPORTING || s === PROJECT_STATUS.COMPLETION) return 'warning'
  return 'info'
}

function goToProject(pid: string) {
  recordOrigin()
  router.push(`/projects/${pid}/progress-board`)
}

// [R9 F7-Partner Task 24] 一键跳转待签字项目
function goToPartnerSignDecision() {
  // 如果只有一个待签字项目，直接跳到该项目的签字决策页
  if (overview.value?.pending_sign?.length === 1) {
    recordOrigin()
    router.push(`/projects/${overview.value.pending_sign[0].id}/sign-decision`)
  } else {
    // 多个待签字项目，跳到待签字 Tab
    activeTab.value = 'sign'
  }
}

function goToReport(pid: string) {
  recordOrigin()
  router.push(`/projects/${pid}/audit-report`)
}

// R8-S2-06：跳转签字决策面板
function goToSignDecision(pid: string, year?: number) {
  recordOrigin()
  const y = year || new Date().getFullYear() - 1
  router.push(`/partner/sign-decision/${pid}/${y}`)
}
function onProjectClick(row: any) {
  goToProject(row.id)
}

/**
 * sign-list 卡片文案：从 workflow 推算"已 X/Y 级，待你签"
 */
function signCardText(project: any): string {
  const wf = projectWorkflowCache.value[project.id]
  if (wf && wf.length) {
    const signed = wf.filter(s => s.status === 'signed').length
    const total = wf.length
    return `已 ${signed}/${total} 级，待你签`
  }
  // 降级：无 workflow 数据时显示旧文案
  return `完成率 ${project.completion_rate}% · ${project.wp_passed}/${project.wp_total} 底稿通过`
}

/**
 * 打开签字弹窗：并行拉 sign-readiness + workflow
 */
async function checkSign(pid: string) {
  showSignDialog.value = true
  currentSignProjectId.value = pid
  readinessData.value = null
  workflowData.value = []
  signLoading.value = true

  try {
    const [readiness, workflow] = await Promise.allSettled([
      getSignReadinessV2(pid),
      getSignatureWorkflow(pid),
    ])

    if (readiness.status === 'fulfilled') {
      readinessData.value = readiness.value
    } else {
      handleApiError(readiness.reason, '加载就绪检查')
    }

    if (workflow.status === 'fulfilled') {
      workflowData.value = workflow.value
      // 缓存到 projectWorkflowCache
      projectWorkflowCache.value[pid] = workflow.value
    }
  } finally {
    signLoading.value = false
  }
}

/**
 * 刷新 readiness 数据
 */
async function refreshReadiness() {
  if (!currentSignProjectId.value) return
  readinessLoading.value = true
  try {
    readinessData.value = await getSignReadinessV2(currentSignProjectId.value)
  } catch (e: any) {
    handleApiError(e, '刷新')
  } finally {
    readinessLoading.value = false
  }
}

/**
 * 执行签字
 */
async function handleSign() {
  if (!canSign.value || !myReadyStep.value || !readinessData.value) return

  const step = myReadyStep.value
  // 计算 prerequisite_signature_ids：当前 step 之前所有 signed 的 step
  const prerequisiteIds: string[] = []
  for (const s of workflowData.value) {
    if (s.order < step.order && s.status === 'signed') {
      // 后端 SignService.get_workflow 返回 id 字段，读取用于前置依赖校验
      if (s.id) {
        prerequisiteIds.push(s.id)
      }
    }
  }

  signing.value = true
  try {
    await signDocument({
      object_type: 'audit_report',
      object_id: currentSignProjectId.value,
      signer_id: authStore.userId,
      signature_level: `level${step.order}`,
      gate_eval_id: readinessData.value.gate_eval_id || undefined,
      project_id: currentSignProjectId.value,
      gate_type: 'sign_off',
      required_order: step.order,
      required_role: step.role,
      prerequisite_signature_ids: prerequisiteIds.length ? prerequisiteIds : undefined,
    })

    ElMessage.success('签字成功')
    showSignDialog.value = false
    // 刷新待签字列表
    loadAll()
  } catch (err: any) {
    // R1 Bug Fix 8: 使用 parseApiError 统一解析错误
    const parsed = parseApiError(err)
    if (parsed.code === 'PREREQUISITE_NOT_MET') {
      handleApiError(err, '前置签字未完成')
    } else if (parsed.code === 'GATE_STALE') {
      ElMessage.warning('检查已过期，请刷新')
      refreshReadiness()
    } else {
      handleApiError(err, '签字')
    }
  } finally {
    signing.value = false
  }
}

async function loadAll() {
  loading.value = true
  try { overview.value = await getPartnerOverview() } catch (e: any) { handleApiError(e, '加载') }
  finally { loading.value = false }
  teamLoading.value = true
  try { teamData.value = await getTeamEfficiency() } catch {}
  finally { teamLoading.value = false }

  // 预加载待签字项目的 workflow 数据（用于卡片文案）
  if (overview.value?.pending_sign?.length) {
    for (const p of overview.value.pending_sign) {
      if (!projectWorkflowCache.value[p.id]) {
        getSignatureWorkflow(p.id)
          .then(wf => { projectWorkflowCache.value[p.id] = wf })
          .catch(() => { /* 静默失败 */ })
      }
    }
  }

  // 检查独立性待声明项目
  loadPendingIndependence()

  // 加载轮换预警
  loadRotationWarnings()
}

/**
 * 检查独立性待声明项目：调用批量端点（R1 Bug Fix 7）
 *
 * Batch 2-5: 失败不再静默降级，给用户提示。
 * Batch 2-10: 显式传 limit=50 避免后端默认值变更破坏前端假设。
 * Batch 3-3: 同时记录 total/has_more，badge 显示真实总数而不是截断后的条数。
 */
async function loadPendingIndependence() {
  try {
    const res = await api.get<{ projects: PendingIndependenceProject[]; total: number; has_more?: boolean }>(
      P_my.pendingIndependence, { params: { limit: 50 } },
    )
    pendingIndependenceProjects.value = {
      projects: res.projects || [],
      total: res.total || 0,
      hasMore: res.has_more || false,
    }
  } catch {
    ElMessage.warning('独立性待声明检查失败，请刷新')
    pendingIndependenceProjects.value = { projects: [], total: 0, hasMore: false }
  }
}

/**
 * Batch 3-10: has_more=true 时"加载更多"按钮的回调，用更大的 limit 拉全量。
 */
async function loadMorePendingIndependence() {
  pendingIndependenceLoadingMore.value = true
  try {
    const res = await api.get<{ projects: PendingIndependenceProject[]; total: number; has_more?: boolean }>(
      P_my.pendingIndependence, { params: { limit: 200 } },
    )
    pendingIndependenceProjects.value = {
      projects: res.projects || [],
      total: res.total || 0,
      hasMore: res.has_more || false,
    }
  } catch {
    ElMessage.warning('加载更多失败，请稍后重试')
  } finally {
    pendingIndependenceLoadingMore.value = false
  }
}

/**
 * 加载轮换预警：遍历 overview.projects 的 signing_partner 调 rotation/check
 * 显示连续年数 ≥ 4 的合伙人+客户组合
 */
async function loadRotationWarnings() {
  if (!overview.value?.projects?.length) return
  const warnings: RotationWarningItem[] = []
  const checked = new Set<string>()

  const activeProjects = overview.value.projects.filter(p => p.status !== 'archived')
  for (const p of activeProjects.slice(0, 20)) {
    // 从项目中获取 signing_partner 信息
    const staffId = (p as any).signing_partner_id || (p as any).signing_partner
    const clientName = p.client_name
    if (!staffId || !clientName) continue

    const key = `${staffId}|${clientName}`
    if (checked.has(key)) continue
    checked.add(key)

    try {
      const result = await checkRotation(staffId, clientName)
      if (result.continuous_years >= 4) {
        warnings.push({
          ...result,
          staff_name: (p as any).signing_partner_name || undefined,
        })
      }
    } catch {
      // 静默失败
    }
  }
  rotationWarnings.value = warnings
}

/**
 * 打开 Override 申请弹窗
 */
function openOverrideDialog(item: RotationWarningItem) {
  overrideTarget.value = item
  overrideReason.value = ''
  overrideResult.value = null
  showOverrideDialog.value = true
}

/**
 * 提交 Override 申请
 */
async function submitOverride() {
  if (!overrideTarget.value || !overrideReason.value.trim()) return
  overrideSubmitting.value = true
  try {
    const result = await createRotationOverride({
      staff_id: overrideTarget.value.staff_id,
      client_name: overrideTarget.value.client_name,
      original_years: overrideTarget.value.continuous_years,
      override_reason: overrideReason.value.trim(),
    })
    overrideResult.value = result
    ElMessage.success('Override 申请已提交，待合规合伙人 + 首席风控合伙人双签')
  } catch (err: any) {
    const msg = err?.response?.data?.detail?.message || err?.response?.data?.detail || 'Override 申请失败'
    handleApiError(err, 'Override 申请')
  } finally {
    overrideSubmitting.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.partner-dashboard { padding: 0; }

/* 刷新按钮：放在 GtPageHeader row1 右端（小图标圆按钮 + 下方"X 前"时间标） */
:deep(.gt-page-header__row1 .gt-header-refresh-wrap) {
  margin-left: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
:deep(.gt-page-header__row1 .gt-header-refresh-wrap .gt-last-update) {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.7);
  white-space: nowrap;
  line-height: 1;
}
.sign-list { display: flex; flex-direction: column; gap: var(--gt-space-3); }
.sign-card {
  display: flex; justify-content: space-between; align-items: center;
  padding: var(--gt-space-4) var(--gt-space-5); background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md); box-shadow: var(--gt-shadow-sm);
  cursor: pointer; transition: all var(--gt-transition-fast);
  border: 1px solid var(--gt-color-border-light);
}
.sign-card:hover { box-shadow: var(--gt-shadow-md); border-color: rgba(75,45,119,0.08); }
.sign-card-name { font-size: var(--gt-font-size-md); font-weight: 600; color: var(--gt-color-text); }
.sign-card-meta { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-top: 4px; }

/* 签字操作栏 */
.gt-sign-action-bar {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter, #ebeef5);
  display: flex;
  align-items: center;
  gap: 12px;
}
.gt-sign-hint {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary, #909399);
}

/* 独立性待声明提醒卡 */
.independence-reminder-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: var(--gt-bg-warning);
}
.independence-reminder-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.independence-reminder-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
}
.independence-reminder-name {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text, #303133);
}
.independence-reminder-footer {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--el-border-color-lighter, #ebeef5);
  text-align: center;
}

/* 轮换预警卡片 */
.rotation-warning-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: var(--gt-bg-danger);
}
.rotation-warning-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.rotation-warning-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5);
}
.rotation-warning-item:last-child {
  border-bottom: none;
}
.rotation-warning-info {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}
.rotation-warning-name {
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-text, #303133);
}
.rotation-warning-sep {
  color: var(--gt-color-text-tertiary, #909399);
  margin: 0 4px;
}
.rotation-warning-client {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text, #303133);
}
.rotation-warning-actions {
  flex-shrink: 0;
}
.rotation-warning-hint {
  font-size: var(--gt-font-size-xs);
  color: var(--el-color-warning, #e6a23c);
}

/* Override 弹窗 */
.override-sign-status {
  margin-top: 16px;
  padding: 12px;
  background: var(--el-fill-color-lighter, #f5f7fa);
  border-radius: 6px;
}
.override-sign-title {
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-text, #303133);
  margin-bottom: 8px;
}
.override-sign-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary, #606266);
}

/* ── 团队效能 KPI 卡片 ─────────────────────────────────────── */
.gt-team-kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--gt-space-3);
  margin-bottom: var(--gt-space-4);
}
.gt-team-kpi-card {
  display: flex;
  align-items: center;
  gap: var(--gt-space-3);
  padding: var(--gt-space-3) var(--gt-space-4);
  border-radius: var(--gt-radius-md);
  background: var(--gt-color-bg-white);
  border: 1px solid var(--gt-color-border-light);
  border-left-width: 3px;
  box-shadow: var(--gt-shadow-sm);
  transition: transform 0.15s, box-shadow 0.15s;
}
.gt-team-kpi-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--gt-shadow-md);
}
.gt-team-kpi-card--primary { border-left-color: var(--gt-color-primary); }
.gt-team-kpi-card--teal    { border-left-color: var(--gt-color-teal); }
.gt-team-kpi-card--success { border-left-color: var(--gt-color-success); }
.gt-team-kpi-card--coral   { border-left-color: var(--gt-color-coral); }
.gt-team-kpi-card--wheat   { border-left-color: var(--gt-color-wheat); }

.gt-team-kpi-icon {
  font-size: 24px;
  line-height: 1;
  flex-shrink: 0;
}
.gt-team-kpi-body { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.gt-team-kpi-num {
  font-size: var(--gt-font-size-xl, 22px);
  font-weight: 700;
  color: var(--gt-color-text);
  line-height: 1.2;
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
}
.gt-team-kpi-label {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
}

.gt-team-staff-table {
  margin-top: var(--gt-space-3);
}
.gt-team-staff-table :deep(.el-table__row td) { padding: 10px 0; }

/* 项目总览 — 操作列内联按钮：禁止竖排折行 */
.gt-row-actions-inline {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}
</style>
