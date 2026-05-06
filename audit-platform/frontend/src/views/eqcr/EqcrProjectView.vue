<template>
  <div v-loading="loading" class="eqcr-project-view">
    <!-- 顶部 banner -->
    <div class="gt-page-banner gt-page-banner--dark">
      <div class="gt-banner-content">
        <div class="eqcr-banner__title-row">
          <el-button
            size="small"
            class="eqcr-banner__back"
            @click="goBack"
          >
            ← 返回工作台
          </el-button>
          <h2 class="eqcr-banner__title">
            🛡️ {{ project?.name || 'EQCR 项目复核' }}
          </h2>
        </div>
        <div v-if="project" class="eqcr-banner__meta">
          <span>客户：{{ project.client_name || '—' }}</span>
          <span>审计期间：
            {{ project.audit_period_start || '?' }}
            ~
            {{ project.audit_period_end || '?' }}
          </span>
          <span>签字日：{{ project.signing_date || '未设定' }}</span>
          <el-tag
            v-if="daysToSigning !== null"
            size="small"
            effect="dark"
            :type="daysTagType(daysToSigning)"
          >
            {{ daysLabel(daysToSigning) }}
          </el-tag>
        </div>
      </div>
      <div class="gt-banner-actions">
        <el-tag
          v-if="reportStatus"
          :type="reportStatusType(reportStatus)"
          effect="dark"
        >
          {{ reportStatusLabel(reportStatus) }}
        </el-tag>
        <el-button
          v-if="canApprove"
          size="small"
          type="primary"
          :loading="approving"
          @click="onApproveClick"
        >
          EQCR 审批
        </el-button>
        <el-button
          v-if="canUnlock"
          size="small"
          type="warning"
          :loading="unlocking"
          @click="onUnlockClick"
        >
          解锁意见
        </el-button>
        <el-button
          size="small"
          :loading="loading"
          @click="loadOverview"
        >
          刷新
        </el-button>
      </div>
    </div>

    <!-- 非 EQCR 访问提示 -->
    <el-alert
      v-if="overview && !overview.my_role_confirmed"
      :closable="false"
      type="warning"
      show-icon
      title="您不是本项目 EQCR"
      description="当前仅以只读模式查看项目 EQCR 数据，意见录入按钮会被禁用。"
      style="margin-top: 12px"
    />

    <!-- 关键指标摘要 -->
    <el-row v-if="overview" :gutter="12" class="eqcr-summary-row">
      <el-col :xs="12" :sm="8" :md="6" :lg="4">
        <el-card shadow="hover" class="eqcr-summary-card">
          <div class="eqcr-summary-card__label">本项目 EQCR 工时</div>
          <div class="eqcr-summary-card__value">
            {{ timeSummary?.total_hours ?? '—' }}<span class="eqcr-summary-card__unit">h</span>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6" :lg="4">
        <el-card shadow="hover" class="eqcr-summary-card">
          <div class="eqcr-summary-card__label">已录 EQCR 意见</div>
          <div class="eqcr-summary-card__value">
            {{ overview.opinion_summary.total }}
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6" :lg="4">
        <el-card shadow="hover" class="eqcr-summary-card">
          <div class="eqcr-summary-card__label">独立笔记</div>
          <div class="eqcr-summary-card__value">
            {{ overview.note_count }}
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6" :lg="4">
        <el-card shadow="hover" class="eqcr-summary-card">
          <div class="eqcr-summary-card__label">影子计算</div>
          <div class="eqcr-summary-card__value">
            {{ overview.shadow_comp_count }}
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6" :lg="4">
        <el-card
          shadow="hover"
          class="eqcr-summary-card"
          :class="{
            'eqcr-summary-card--danger': overview.disagreement_count > 0,
          }"
        >
          <div class="eqcr-summary-card__label">未解决异议</div>
          <div class="eqcr-summary-card__value">
            {{ overview.disagreement_count }}
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 5 Tab -->
    <el-tabs v-model="activeTab" class="eqcr-tabs">
      <el-tab-pane label="重要性" name="materiality">
        <EqcrMateriality v-if="activeTab === 'materiality'" :project-id="projectId" />
      </el-tab-pane>
      <el-tab-pane label="会计估计" name="estimate">
        <EqcrEstimates v-if="activeTab === 'estimate'" :project-id="projectId" />
      </el-tab-pane>
      <el-tab-pane label="关联方" name="related_party">
        <EqcrRelatedParties
          v-if="activeTab === 'related_party'"
          :project-id="projectId"
          :can-write="canWriteRelatedParties"
        />
      </el-tab-pane>
      <el-tab-pane label="持续经营" name="going_concern">
        <EqcrGoingConcern
          v-if="activeTab === 'going_concern'"
          :project-id="projectId"
        />
      </el-tab-pane>
      <el-tab-pane label="审计意见" name="opinion_type">
        <EqcrOpinionType
          v-if="activeTab === 'opinion_type'"
          :project-id="projectId"
        />
      </el-tab-pane>
      <el-tab-pane label="影子计算" name="shadow_compute">
        <EqcrShadowCompute
          v-if="activeTab === 'shadow_compute'"
          :project-id="projectId"
        />
      </el-tab-pane>
      <el-tab-pane label="独立复核笔记" name="review_notes">
        <EqcrReviewNotesPanel
          v-if="activeTab === 'review_notes'"
          :project-id="projectId"
        />
      </el-tab-pane>
      <el-tab-pane label="历年对比" name="prior_year">
        <EqcrPriorYearCompare
          v-if="activeTab === 'prior_year'"
          ref="priorYearRef"
          :project-id="projectId"
        />
      </el-tab-pane>
      <el-tab-pane label="备忘录" name="memo">
        <EqcrMemoEditor
          v-if="activeTab === 'memo'"
          :project-id="projectId"
        />
      </el-tab-pane>
      <el-tab-pane v-if="isConsolidated" label="组成部分审计师" name="component_auditor">
        <EqcrComponentAuditors
          v-if="activeTab === 'component_auditor'"
          :project-id="projectId"
        />
      </el-tab-pane>
      <!-- 预留 Tab：组成部分审计师 → Task 22 实装，本任务不渲染 -->
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, provide, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  eqcrApi,
  type EqcrProjectOverview,
  type ReportStatusValue,
} from '@/services/eqcrService'
import EqcrMateriality from '@/components/eqcr/EqcrMateriality.vue'
import EqcrEstimates from '@/components/eqcr/EqcrEstimates.vue'
import EqcrRelatedParties from '@/components/eqcr/EqcrRelatedParties.vue'
import EqcrGoingConcern from '@/components/eqcr/EqcrGoingConcern.vue'
import EqcrOpinionType from '@/components/eqcr/EqcrOpinionType.vue'
import EqcrShadowCompute from '@/components/eqcr/EqcrShadowCompute.vue'
import EqcrReviewNotesPanel from '@/components/eqcr/EqcrReviewNotesPanel.vue'
import EqcrPriorYearCompare from '@/components/eqcr/EqcrPriorYearCompare.vue'
import EqcrMemoEditor from '@/components/eqcr/EqcrMemoEditor.vue'
import EqcrComponentAuditors from '@/components/eqcr/EqcrComponentAuditors.vue'

const route = useRoute()
const router = useRouter()

const projectId = computed(() => String(route.params.projectId ?? ''))

const loading = ref(false)
const overview = ref<EqcrProjectOverview | null>(null)
const timeSummary = ref<{ total_hours: number; record_count: number } | null>(null)
const activeTab = ref<
  'materiality' | 'estimate' | 'related_party' | 'going_concern' | 'opinion_type' | 'shadow_compute' | 'review_notes' | 'prior_year' | 'memo' | 'component_auditor'
>('materiality')

const project = computed(() => overview.value?.project ?? null)
const reportStatus = computed<ReportStatusValue | null>(
  () => overview.value?.report_status ?? null,
)
const isConsolidated = computed<boolean>(
  () => project.value?.report_scope === 'consolidated',
)

/** 当前用户是否为本项目 EQCR。非 EQCR 用户进入只读模式，禁用意见录入。 */
const opinionFormDisabled = computed<boolean>(
  () => !(overview.value?.my_role_confirmed ?? false),
)
provide('eqcrOpinionFormDisabled', opinionFormDisabled)

/**
 * 关联方 CRUD 写入权限：非 EQCR 角色（经理/合伙人/admin）可写。
 * 后端已做 403 兜底，前端仅控制 UI 显隐。
 */
const canWriteRelatedParties = computed<boolean>(
  () => !(overview.value?.my_role_confirmed ?? true),
)

const daysToSigning = computed<number | null>(() => {
  const sd = project.value?.signing_date
  if (!sd) return null
  try {
    const target = new Date(sd)
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    target.setHours(0, 0, 0, 0)
    const diff = Math.round((target.getTime() - today.getTime()) / 86400000)
    return diff
  } catch {
    return null
  }
})

async function loadOverview() {
  if (!projectId.value) return
  loading.value = true
  try {
    overview.value = await eqcrApi.getProjectOverview(projectId.value)
    // Fetch time summary in parallel
    try {
      const api = (await import('@/services/apiProxy')).default
      timeSummary.value = await api.get(`/api/eqcr/projects/${projectId.value}/time-summary`)
    } catch { timeSummary.value = null }
  } catch (err: any) {
    if (err?.response?.status === 404) {
      ElMessage.error('项目不存在')
      router.replace({ name: 'EqcrWorkbench' })
      return
    }
    ElMessage.error(err?.response?.data?.detail || '加载项目总览失败')
    overview.value = null
  } finally {
    loading.value = false
  }
}

function goBack() {
  router.push({ name: 'EqcrWorkbench' })
}

// ─── EQCR 审批/解锁（需求 5、6、7） ────────────────────────────────────────

const priorYearRef = ref<any>(null)
const approving = ref(false)
const unlocking = ref(false)

const canApprove = computed<boolean>(() => {
  if (!overview.value?.my_role_confirmed) return false
  return reportStatus.value === 'review'
})

const canUnlock = computed<boolean>(() => {
  if (!overview.value?.my_role_confirmed) return false
  return reportStatus.value === 'eqcr_approved'
})

async function onApproveClick() {
  // 需求 7.3：若历年对比有差异，必须先填写所有差异原因
  if (priorYearRef.value) {
    const allProvided = priorYearRef.value.allDiffReasonsProvided?.()
    if (allProvided === false) {
      ElMessage.warning(
        '历年 EQCR 意见存在差异，请先在"历年对比" Tab 填写所有差异原因后再审批',
      )
      activeTab.value = 'prior_year'
      return
    }
  }

  const { value: comment } = await ElMessageBox.prompt(
    'EQCR 审批意见（将记录到签字流水）',
    '确认 EQCR 审批',
    {
      confirmButtonText: '确认审批',
      cancelButtonText: '取消',
      inputType: 'textarea',
      inputPlaceholder: '请输入审批评论...',
      inputValidator: (v) => (v && v.trim() ? true : '审批评论不能为空'),
    },
  ).catch(() => ({ value: null }))

  if (!comment) return

  approving.value = true
  try {
    const diffReasons = priorYearRef.value?.getDiffReasons?.() ?? {}
    const api = (await import('@/services/apiProxy')).default
    await api.post(`/api/eqcr/projects/${projectId.value}/approve`, {
      verdict: 'approve',
      comment,
      // 差异原因附加到审批记录（后端 extra_payload 可扩展）
      ...(Object.keys(diffReasons).length ? { prior_year_diff_reasons: diffReasons } : {}),
    })
    ElMessage.success('EQCR 审批完成，审计报告已锁定')
    await loadOverview()
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    if (detail?.error_code === 'EQCR_GATE_BLOCKED') {
      const rules = detail.blocking_rules || []
      const msg = rules.map((r: any) => `[${r.rule_code}] ${r.message}`).join('\n')
      ElMessage.error(`EQCR 门禁阻断：\n${msg}`)
    } else {
      ElMessage.error(typeof detail === 'string' ? detail : '审批失败')
    }
  } finally {
    approving.value = false
  }
}

async function onUnlockClick() {
  const { value: reason } = await ElMessageBox.prompt(
    '解锁后审计报告回到 review 状态，意见类型可修改。请说明解锁原因：',
    '确认解锁 EQCR 意见',
    {
      confirmButtonText: '确认解锁',
      cancelButtonText: '取消',
      inputType: 'textarea',
      inputValidator: (v) => (v && v.trim() ? true : '解锁原因不能为空'),
    },
  ).catch(() => ({ value: null }))

  if (!reason) return

  unlocking.value = true
  try {
    const api = (await import('@/services/apiProxy')).default
    await api.post(`/api/eqcr/projects/${projectId.value}/unlock-opinion`, {
      reason,
    })
    ElMessage.success('EQCR 意见已解锁')
    await loadOverview()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '解锁失败')
  } finally {
    unlocking.value = false
  }
}

onMounted(loadOverview)

watch(
  () => projectId.value,
  (newId, oldId) => {
    if (newId && newId !== oldId) {
      loadOverview()
    }
  },
)

// ─── 视觉辅助 ─────────────────────────────────────────────────────────────

function daysTagType(days: number): 'danger' | 'warning' | 'info' {
  if (days <= 7) return 'danger'
  if (days <= 30) return 'warning'
  return 'info'
}

function daysLabel(days: number): string {
  if (days < 0) return `已逾期 ${Math.abs(days)} 天`
  if (days === 0) return '今日签字'
  return `距签字 ${days} 天`
}

const REPORT_STATUS_META: Record<
  ReportStatusValue,
  { label: string; type: 'info' | 'warning' | 'success' | 'primary' }
> = {
  draft: { label: '报告草稿', type: 'info' },
  review: { label: '报告审阅中', type: 'warning' },
  eqcr_approved: { label: 'EQCR 已通过', type: 'primary' },
  final: { label: '报告已定稿', type: 'success' },
}

function reportStatusLabel(s: ReportStatusValue): string {
  return REPORT_STATUS_META[s]?.label ?? s
}
function reportStatusType(
  s: ReportStatusValue,
): 'info' | 'warning' | 'success' | 'primary' {
  return REPORT_STATUS_META[s]?.type ?? 'info'
}
</script>

<style scoped>
.eqcr-project-view {
  padding: 0;
}

.eqcr-banner__title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.eqcr-banner__back {
  flex-shrink: 0;
}
.eqcr-banner__title {
  margin: 0;
}
.eqcr-banner__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-top: 6px;
  font-size: var(--gt-font-size-sm, 13px);
  color: var(--gt-color-text-secondary, #606266);
}
.eqcr-banner__meta > span {
  display: inline-flex;
  align-items: center;
}

.eqcr-summary-row {
  margin-top: 12px;
  margin-bottom: 4px;
}
.eqcr-summary-card {
  border-radius: var(--gt-radius-md, 6px);
}
.eqcr-summary-card__label {
  font-size: var(--gt-font-size-xs, 12px);
  color: var(--gt-color-text-tertiary, #909399);
  margin-bottom: 4px;
}
.eqcr-summary-card__value {
  font-size: var(--gt-font-size-xl, 22px);
  font-weight: 600;
  color: var(--gt-color-text, #303133);
}
.eqcr-summary-card__unit {
  font-size: var(--gt-font-size-sm, 13px);
  font-weight: 400;
  color: var(--gt-color-text-tertiary, #909399);
  margin-left: 2px;
}
.eqcr-summary-card--danger {
  border-left: 4px solid var(--el-color-danger, #f56c6c);
}
.eqcr-summary-card--danger .eqcr-summary-card__value {
  color: var(--el-color-danger, #f56c6c);
}

.eqcr-tabs {
  margin-top: 16px;
}
</style>
