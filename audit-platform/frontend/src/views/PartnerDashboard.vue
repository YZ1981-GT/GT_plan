<template>
  <div class="partner-dashboard">
    <div class="gt-page-banner gt-page-banner--dark">
      <div class="gt-banner-content">
        <h2>🏛️ 合伙人看板</h2>
        <span class="gt-banner-sub" v-if="overview">
          {{ overview.total_projects }} 个项目 · {{ overview.risk_alert_count }} 个风险预警 · {{ overview.pending_sign_count }} 个待签字
        </span>
      </div>
      <div class="gt-banner-actions">
        <el-button size="small" @click="loadAll" :loading="loading">刷新</el-button>
      </div>
    </div>

    <!-- 风险预警横幅 -->
    <el-alert v-if="overview && overview.risk_alert_count > 0" type="warning" :closable="false" style="margin-bottom: 16px">
      <template #title>
        ⚠️ {{ overview.risk_alert_count }} 个项目存在风险预警
      </template>
      <div v-for="a in overview.risk_alerts" :key="a.id" style="margin-top: 4px; font-size: 13px">
        <span style="font-weight: 600">{{ a.client_name || a.name }}</span>：{{ a.risk_reasons.join('、') }}
      </div>
    </el-alert>

    <el-tabs v-model="activeTab">
      <!-- Tab 1: 项目总览 -->
      <el-tab-pane label="项目总览" name="projects">
        <el-table :data="overview?.projects || []" stripe v-loading="loading" @row-click="onProjectClick" style="cursor: pointer">
          <el-table-column label="风险" width="60" align="center">
            <template #default="{ row }">
              <span :class="'gt-risk-dot gt-risk-dot--' + row.risk_level" />
            </template>
          </el-table-column>
          <el-table-column label="客户" prop="client_name" width="160" />
          <el-table-column label="项目" prop="name" min-width="180" />
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag size="small" :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="完成率" width="130">
            <template #default="{ row }">
              <el-progress :percentage="row.completion_rate" :stroke-width="6"
                :color="row.completion_rate >= 80 ? '#67c23a' : row.completion_rate >= 50 ? '#e6a23c' : '#f56c6c'" />
            </template>
          </el-table-column>
          <el-table-column label="底稿" width="80" align="center">
            <template #default="{ row }">{{ row.wp_passed }}/{{ row.wp_total }}</template>
          </el-table-column>
          <el-table-column label="待复核" width="70" align="center">
            <template #default="{ row }">
              <span :style="{ color: row.wp_pending > 0 ? '#e6a23c' : '#999' }">{{ row.wp_pending }}</span>
            </template>
          </el-table-column>
          <el-table-column label="退回" width="60" align="center">
            <template #default="{ row }">
              <span :style="{ color: row.wp_rejected > 0 ? '#f56c6c' : '#999' }">{{ row.wp_rejected }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button size="small" link type="primary" @click.stop="goToProject(row.id)">进入</el-button>
              <el-button size="small" link @click.stop="checkSign(row.id)">签字检查</el-button>
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
            <el-button type="primary" size="small" round>签字前检查 →</el-button>
          </div>
        </div>
        <el-empty v-else description="暂无待签字项目" />
      </el-tab-pane>

      <!-- Tab 3: 团队效能 -->
      <el-tab-pane label="团队效能" name="team">
        <div v-if="teamData" class="gt-team-summary">
          <div class="gt-team-stat" v-for="s in teamStats" :key="s.label">
            <div class="gt-team-stat-num">{{ s.value }}</div>
            <div class="gt-team-stat-label">{{ s.label }}</div>
          </div>
        </div>
        <el-table :data="teamData?.staff_metrics || []" stripe v-loading="teamLoading">
          <el-table-column label="人员" prop="user_name" width="120" />
          <el-table-column label="底稿数" prop="total" width="80" align="center" />
          <el-table-column label="通过" prop="passed" width="60" align="center" />
          <el-table-column label="退回" width="60" align="center">
            <template #default="{ row }">
              <span :style="{ color: row.rejected > 0 ? '#f56c6c' : '#999' }">{{ row.rejected }}</span>
            </template>
          </el-table-column>
          <el-table-column label="通过率" width="120">
            <template #default="{ row }">
              <el-progress :percentage="row.pass_rate" :stroke-width="6"
                :color="row.pass_rate >= 80 ? '#67c23a' : row.pass_rate >= 50 ? '#e6a23c' : '#f56c6c'" />
            </template>
          </el-table-column>
          <el-table-column label="退回率" width="80" align="center">
            <template #default="{ row }">
              <span :style="{ color: row.reject_rate > 10 ? '#f56c6c' : '#999' }">{{ row.reject_rate }}%</span>
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
            <template v-if="!readinessData.ready">就绪检查未通过，无法签字</template>
            <template v-else-if="!myReadyStep">当前未轮到你签字</template>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import {
  getPartnerOverview, getTeamEfficiency,
  type PartnerOverview, type TeamEfficiency,
} from '@/services/partnerApi'
import {
  getSignatureWorkflow, signDocument, getSignReadinessV2,
  type WorkflowStep,
} from '@/services/signatureApi'
import type { GateReadinessData } from '@/components/gate/GateReadinessPanel.vue'
import GateReadinessPanel from '@/components/gate/GateReadinessPanel.vue'
import SignatureWorkflowLine from '@/components/signature/SignatureWorkflowLine.vue'

const router = useRouter()
const authStore = useAuthStore()
const loading = ref(false)
const activeTab = ref('projects')

const overview = ref<PartnerOverview | null>(null)
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

const teamStats = computed(() => {
  const s = teamData.value?.summary
  if (!s) return []
  return [
    { label: '团队人数', value: s.total_staff },
    { label: '底稿总数', value: s.total_workpapers },
    { label: '平均通过率', value: s.avg_pass_rate + '%' },
    { label: '平均退回率', value: s.avg_reject_rate + '%' },
    { label: '人均底稿', value: s.avg_per_person },
  ]
})

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
function statusType(s: string) {
  if (s === 'archived') return 'success'
  if (s === 'execution') return ''
  if (s === 'reporting' || s === 'completion') return 'warning'
  return 'info'
}

function goToProject(pid: string) {
  router.push(`/projects/${pid}/progress-board`)
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
      ElMessage.error('就绪检查加载失败')
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
  } catch {
    ElMessage.error('刷新失败')
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
      // 如果 workflow 返回了 id 字段则用，否则不传
      if ((s as any).id) {
        prerequisiteIds.push((s as any).id)
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
    const detail = err?.response?.data?.detail
    const errorCode = detail?.error_code || detail?.code || ''

    if (errorCode === 'PREREQUISITE_NOT_MET') {
      ElMessage.error('前置签字未完成')
    } else if (errorCode === 'GATE_STALE') {
      ElMessage.warning('检查已过期，请刷新')
      refreshReadiness()
    } else {
      ElMessage.error(detail?.message || '签字失败')
    }
  } finally {
    signing.value = false
  }
}

async function loadAll() {
  loading.value = true
  try { overview.value = await getPartnerOverview() } catch { ElMessage.error('加载失败') }
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
}

onMounted(loadAll)
</script>

<style scoped>
.partner-dashboard { padding: 0; }
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
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}
</style>
