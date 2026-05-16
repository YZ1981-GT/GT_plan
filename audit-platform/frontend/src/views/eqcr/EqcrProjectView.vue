<template>
  <div v-loading="loading" class="eqcr-project-view">
    <!-- 顶部 banner -->
    <GtPageHeader title="独立复核" :show-back="false">
      <template #actions>
        <el-button size="small" @click="goBack">← 返回工作台</el-button>
      </template>
    </GtPageHeader>

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
      <el-tab-pane name="materiality">
        <template #label>
          <span>重要性</span>
          <el-badge v-if="eqcrTabBadges.materiality > 0" :value="eqcrTabBadges.materiality" type="warning" class="eqcr-tab-badge" />
        </template>
        <EqcrMateriality v-if="activeTab === 'materiality'" :project-id="projectId" />
        <ShadowCompareRow v-if="activeTab === 'materiality' && shadowData.materiality.length" :rows="shadowData.materiality" @verdict="onShadowVerdict" />
      </el-tab-pane>
      <el-tab-pane label="会计估计" name="estimate">
        <EqcrEstimates v-if="activeTab === 'estimate'" :project-id="projectId" />
        <ShadowCompareRow v-if="activeTab === 'estimate' && shadowData.estimate.length" :rows="shadowData.estimate" @verdict="onShadowVerdict" />
      </el-tab-pane>
      <el-tab-pane label="关联方" name="related_party">
        <EqcrRelatedParties
          v-if="activeTab === 'related_party'"
          :project-id="projectId"
          :can-write="canWriteRelatedParties"
        />
        <ShadowCompareRow v-if="activeTab === 'related_party' && shadowData.related_party.length" :rows="shadowData.related_party" @verdict="onShadowVerdict" />
      </el-tab-pane>
      <el-tab-pane label="持续经营" name="going_concern">
        <EqcrGoingConcern
          v-if="activeTab === 'going_concern'"
          :project-id="projectId"
        />
        <ShadowCompareRow v-if="activeTab === 'going_concern' && shadowData.going_concern.length" :rows="shadowData.going_concern" @verdict="onShadowVerdict" />
      </el-tab-pane>
      <el-tab-pane label="审计意见" name="opinion_type">
        <EqcrOpinionType
          v-if="activeTab === 'opinion_type'"
          :project-id="projectId"
        />
        <ShadowCompareRow v-if="activeTab === 'opinion_type' && shadowData.opinion_type.length" :rows="shadowData.opinion_type" @verdict="onShadowVerdict" />
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
      <!-- 关键发现摘要 Tab [R9 F7-EQCR Task 25] -->
      <el-tab-pane label="关键发现摘要" name="key_findings_summary">
        <div v-if="activeTab === 'key_findings_summary'" class="eqcr-key-findings-summary">
          <el-alert type="info" :closable="false" show-icon style="margin-bottom: 16px">
            <template #title>本页聚合各 Tab 核心结论，便于一页纸快速浏览</template>
          </el-alert>
          <div class="eqcr-findings-grid">
            <el-card v-if="overview" shadow="hover" class="eqcr-finding-card">
              <template #header><span>📊 重要性</span></template>
              <div class="eqcr-finding-content">
                已录入 {{ (overview.opinion_summary as any)?.materiality || 0 }} 条意见
              </div>
            </el-card>
            <el-card shadow="hover" class="eqcr-finding-card">
              <template #header><span>📐 会计估计</span></template>
              <div class="eqcr-finding-content">
                已录入 {{ (overview?.opinion_summary as any)?.estimate || 0 }} 条意见
              </div>
            </el-card>
            <el-card shadow="hover" class="eqcr-finding-card">
              <template #header><span>🔗 关联方</span></template>
              <div class="eqcr-finding-content">
                已录入 {{ (overview?.opinion_summary as any)?.related_party || 0 }} 条意见
              </div>
            </el-card>
            <el-card shadow="hover" class="eqcr-finding-card">
              <template #header><span>🏢 持续经营</span></template>
              <div class="eqcr-finding-content">
                已录入 {{ (overview?.opinion_summary as any)?.going_concern || 0 }} 条意见
              </div>
            </el-card>
            <el-card shadow="hover" class="eqcr-finding-card">
              <template #header><span>📝 审计意见</span></template>
              <div class="eqcr-finding-content">
                已录入 {{ (overview?.opinion_summary as any)?.opinion_type || 0 }} 条意见
              </div>
            </el-card>
            <el-card shadow="hover" class="eqcr-finding-card">
              <template #header><span>🛡️ EQCR 总结</span></template>
              <div class="eqcr-finding-content">
                总意见数 {{ overview?.opinion_summary?.total || 0 }}，
                工时 {{ timeSummary?.total_hours ?? '—' }}h
              </div>
            </el-card>
          </div>
        </div>
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
import { eqcr as P_eqcr } from '@/services/apiPaths'
import { REPORT_STATUS } from '@/constants/statusEnum'
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
import ShadowCompareRow from '@/components/eqcr/ShadowCompareRow.vue'
import type { ShadowCompareItem } from '@/components/eqcr/ShadowCompareRow.vue'
import { feedback } from '@/utils/feedback'
import { handleApiError } from '@/utils/errorHandler'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()

const route = useRoute()
const router = useRouter()

const projectId = computed(() => String(route.params.projectId ?? ''))

// Spec A R1：EQCR Tab badge（聚合 stale 摘要 → 按 Tab 类型派生）
import { useStaleSummaryFull } from '@/composables/useStaleSummaryFull'
const eqcrYear = computed(() => Number(route.query.year) || new Date().getFullYear() - 1)
const { workpapers: eqcrWp, reports: eqcrRpt, notes: eqcrNotes, misstatements: eqcrMiss }
  = useStaleSummaryFull(projectId, eqcrYear)
// 简化：所有 Tab 共享一个"项目级"badge — 显示总 stale 数；如需精确按 Tab 类型分组，
// 需要后端返回更细粒度数据（暂作 TD-3 / 见 tasks.md 已知缺口）
const _projectStaleCount = computed(() =>
  (eqcrWp.value.stale ?? 0)
  + (eqcrRpt.value.stale ?? 0)
  + (eqcrNotes.value.stale ?? 0)
  + (eqcrMiss.value.recheck_needed ?? 0)
)
const eqcrTabBadges = computed(() => ({
  materiality: eqcrMiss.value.recheck_needed ?? 0,
  estimate: 0,
  related_party: 0,
  going_concern: 0,
  opinion_type: 0,
  shadow_compute: 0,
  review_notes: 0,
  prior_year: 0,
  memo: 0,
  component_auditor: 0,
  key_findings_summary: _projectStaleCount.value,
}))

const loading = ref(false)
const overview = ref<EqcrProjectOverview | null>(null)
const timeSummary = ref<{ total_hours: number; record_count: number } | null>(null)
const activeTab = ref<
  'materiality' | 'estimate' | 'related_party' | 'going_concern' | 'opinion_type' | 'shadow_compute' | 'review_notes' | 'prior_year' | 'memo' | 'component_auditor' | 'key_findings_summary'
>('materiality')

const project = computed(() => overview.value?.project ?? null)
const reportStatus = computed<ReportStatusValue | null>(
  () => overview.value?.report_status ?? null,
)

// R7-S3-04：影子对比数据（5 判断 Tab 各自的对比行）
const shadowData = ref<Record<string, ShadowCompareItem[]>>({
  materiality: [],
  estimate: [],
  related_party: [],
  going_concern: [],
  opinion_type: [],
})

async function onShadowVerdict(row: ShadowCompareItem, action: 'pass' | 'flag') {
  const prev = row.verdict
  row.verdict = action
  // R8-S2-04：持久化到后端 EqcrOpinion（pass→agree, flag→disagree）
  try {
    const { eqcrApi } = await import('@/services/eqcrService')
    await eqcrApi.createOpinion({
      project_id: projectId.value,
      domain: activeTab.value as any,
      verdict: action === 'pass' ? 'agree' : 'disagree',
      comment: `[ShadowCompareRow] ${row.dimension}：项目组值 ${row.teamValue}，影子值 ${row.shadowValue}，差异 ${row.diff}`,
    })
    feedback.success(`已${action === 'pass' ? '通过' : '标记'}：${row.dimension}`)
  } catch (e: any) {
    row.verdict = prev  // 回滚 UI 状态
    handleApiError(e, '保存判断')
  }
}

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
      timeSummary.value = await api.get(P_eqcr.timeSummary(projectId.value))
    } catch { timeSummary.value = null }
  } catch (err: any) {
    if (err?.response?.status === 404) {
      handleApiError(err, '项目不存在')
      router.replace({ name: 'EqcrWorkbench' })
      return
    }
    handleApiError(err, '加载项目总览')
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
  return reportStatus.value === REPORT_STATUS.REVIEW
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

  // R10 Spec C / F7：先用 confirmSign 展示操作+用户+项目+不可撤销摘要
  try {
    const { confirmSign } = await import('@/utils/confirm')
    await confirmSign('EQCR 独立复核签字（审定意见）', {
      userName: authStore.user?.full_name || authStore.user?.username || '当前用户',
      projectName: overview.value?.project?.name || projectId.value || '当前项目',
      objectName: 'EQCR 复核审批 — 审批后审计报告将进入 eqcr_approved 状态',
    })
  } catch {
    return
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
    await api.post(P_eqcr.approve(projectId.value), {
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
      handleApiError(e, '操作')
    } else {
      handleApiError(e, '审批')
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
    await api.post(P_eqcr.unlockOpinion(projectId.value), {
      reason,
    })
    ElMessage.success('EQCR 意见已解锁')
    await loadOverview()
  } catch (e: any) {
    handleApiError(e, '解锁')
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
/* Spec A R1：Tab badge 微调（el-badge 默认偏右上角，调到与文字基线对齐） */
.eqcr-tab-badge {
  margin-left: 4px;
  vertical-align: text-top;
}
.eqcr-tab-badge :deep(.el-badge__content) {
  height: 16px; line-height: 14px; padding: 0 4px;
}

/* 关键发现摘要 [R9 F7-EQCR Task 25] */
.eqcr-key-findings-summary {
  padding: 8px 0;
}
.eqcr-findings-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}
.eqcr-finding-card {
  min-height: 100px;
}
.eqcr-finding-content {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary);
  line-height: 1.6;
}
</style>
