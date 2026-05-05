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
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="eqcr-summary-card">
          <div class="eqcr-summary-card__label">已录 EQCR 意见</div>
          <div class="eqcr-summary-card__value">
            {{ overview.opinion_summary.total }}
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="eqcr-summary-card">
          <div class="eqcr-summary-card__label">独立笔记</div>
          <div class="eqcr-summary-card__value">
            {{ overview.note_count }}
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6">
        <el-card shadow="hover" class="eqcr-summary-card">
          <div class="eqcr-summary-card__label">影子计算</div>
          <div class="eqcr-summary-card__value">
            {{ overview.shadow_comp_count }}
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="6">
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
      <!-- 预留 Tab 7：组成部分审计师 → Task 22 实装，本任务不渲染 -->
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, provide, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
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

const route = useRoute()
const router = useRouter()

const projectId = computed(() => String(route.params.projectId ?? ''))

const loading = ref(false)
const overview = ref<EqcrProjectOverview | null>(null)
const activeTab = ref<
  'materiality' | 'estimate' | 'related_party' | 'going_concern' | 'opinion_type' | 'shadow_compute'
>('materiality')

const project = computed(() => overview.value?.project ?? null)
const reportStatus = computed<ReportStatusValue | null>(
  () => overview.value?.report_status ?? null,
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
