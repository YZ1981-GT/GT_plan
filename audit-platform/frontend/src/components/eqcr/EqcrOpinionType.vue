<template>
  <div v-loading="loading" class="eqcr-tab">
    <el-card shadow="never" class="eqcr-tab__section">
      <template #header>
        <span class="eqcr-tab__section-title">本年度审计意见</span>
        <el-tag v-if="currentReport" size="small" type="info" effect="light">
          {{ currentReport.year }} 年
        </el-tag>
      </template>

      <el-descriptions
        v-if="currentReport"
        :column="2"
        border
        size="small"
        class="eqcr-tab__desc"
      >
        <el-descriptions-item label="意见类型">
          <el-tag
            v-if="currentReport.opinion_type"
            :type="opinionTagType(currentReport.opinion_type)"
            size="small"
            effect="light"
          >
            {{ opinionTypeLabel(currentReport.opinion_type) }}
          </el-tag>
          <span v-else class="eqcr-muted">—</span>
        </el-descriptions-item>
        <el-descriptions-item label="报告状态">
          <el-tag
            v-if="currentReport.status"
            :type="reportStatusType(currentReport.status)"
            size="small"
            effect="dark"
          >
            {{ reportStatusLabel(currentReport.status) }}
          </el-tag>
          <span v-else class="eqcr-muted">—</span>
        </el-descriptions-item>
        <el-descriptions-item label="公司类型">
          {{ companyTypeLabel(currentReport.company_type) }}
        </el-descriptions-item>
        <el-descriptions-item label="签字合伙人">
          {{ currentReport.signing_partner || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="报告日期" :span="2">
          {{ currentReport.report_date || '—' }}
        </el-descriptions-item>
      </el-descriptions>
      <el-empty
        v-else
        description="该项目尚未创建审计报告"
        :image-size="60"
      />
    </el-card>

    <el-card
      v-if="priorReports.length > 0"
      shadow="never"
      class="eqcr-tab__section"
    >
      <template #header>
        <span class="eqcr-tab__section-title">历年审计意见</span>
        <el-tag size="small" type="info" effect="plain">
          {{ priorReports.length }} 份记录
        </el-tag>
      </template>

      <el-table
        :data="priorReports"
        size="small"
        border
        stripe
        style="width: 100%"
      >
        <el-table-column prop="year" label="年度" width="80" />
        <el-table-column label="意见类型" width="160">
          <template #default="{ row }">
            <el-tag
              v-if="row.opinion_type"
              :type="opinionTagType(row.opinion_type)"
              size="small"
              effect="light"
            >
              {{ opinionTypeLabel(row.opinion_type) }}
            </el-tag>
            <span v-else class="eqcr-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag
              v-if="row.status"
              :type="reportStatusType(row.status)"
              size="small"
              effect="light"
            >
              {{ reportStatusLabel(row.status) }}
            </el-tag>
            <span v-else class="eqcr-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="signing_partner" label="签字合伙人" width="140" />
        <el-table-column prop="report_date" label="报告日期" />
      </el-table>
    </el-card>

    <el-card shadow="never" class="eqcr-tab__section">
      <template #header>
        <span class="eqcr-tab__section-title">EQCR 复核意见</span>
      </template>
      <EqcrOpinionForm
        :project-id="projectId"
        domain="opinion_type"
        :current-opinion="currentOpinion"
        :history-opinions="historyOpinions"
        @saved="onOpinionSaved"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  eqcrApi,
  type EqcrAuditReportSnapshot,
  type EqcrDomainPayload,
  type EqcrOpinion,
  type EqcrOpinionTypeData,
  type ReportStatusValue,
} from '@/services/eqcrService'
import EqcrOpinionForm from './EqcrOpinionForm.vue'

const props = defineProps<{ projectId: string }>()

const loading = ref(false)
const payload = ref<EqcrDomainPayload<EqcrOpinionTypeData> | null>(null)

const currentReport = computed<EqcrAuditReportSnapshot | null>(
  () => payload.value?.data.current_report ?? null,
)
const priorReports = computed<EqcrAuditReportSnapshot[]>(
  () => payload.value?.data.prior_reports ?? [],
)
const currentOpinion = computed<EqcrOpinion | null>(
  () => payload.value?.current_opinion ?? null,
)
const historyOpinions = computed<EqcrOpinion[]>(
  () => payload.value?.history_opinions ?? [],
)

async function load() {
  loading.value = true
  try {
    payload.value = await eqcrApi.getOpinionType(props.projectId)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '加载审计意见数据失败')
    payload.value = null
  } finally {
    loading.value = false
  }
}

function onOpinionSaved(_: EqcrOpinion) {
  load()
}

onMounted(load)

// ─── 辅助 ──────────────────────────────────────────────────────────────────

function opinionTypeLabel(t: string | null | undefined): string {
  if (!t) return '—'
  const map: Record<string, string> = {
    unqualified: '无保留意见',
    unqualified_with_emphasis: '带强调事项段的无保留意见',
    qualified: '保留意见',
    adverse: '否定意见',
    disclaimer: '无法表示意见',
  }
  return map[t] ?? t
}

function opinionTagType(
  t: string | null | undefined,
): 'success' | 'warning' | 'danger' | 'info' {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
    unqualified: 'success',
    unqualified_with_emphasis: 'warning',
    qualified: 'warning',
    adverse: 'danger',
    disclaimer: 'danger',
  }
  return (t && map[t]) || 'info'
}

function companyTypeLabel(t: string | null | undefined): string {
  if (!t) return '—'
  const map: Record<string, string> = {
    general: '一般企业',
    financial: '金融企业',
    nonprofit: '非营利组织',
    listed: '上市公司',
  }
  return map[t] ?? t
}

const REPORT_STATUS_META: Record<
  string,
  { label: string; type: 'info' | 'warning' | 'primary' | 'success' }
> = {
  draft: { label: '草稿', type: 'info' },
  review: { label: '审阅中', type: 'warning' },
  eqcr_approved: { label: 'EQCR 已锁定', type: 'primary' },
  final: { label: '已定稿', type: 'success' },
}

function reportStatusLabel(s: ReportStatusValue | string): string {
  return REPORT_STATUS_META[s]?.label ?? s
}
function reportStatusType(
  s: ReportStatusValue | string,
): 'info' | 'warning' | 'primary' | 'success' {
  return REPORT_STATUS_META[s]?.type ?? 'info'
}
</script>

<style scoped>
.eqcr-tab {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.eqcr-tab__section {
  border-radius: var(--gt-radius-md, 6px);
}
.eqcr-tab__section-title {
  font-weight: 600;
  color: var(--gt-color-text, #303133);
  margin-right: 10px;
}
.eqcr-tab__desc {
  margin-top: 4px;
}
.eqcr-muted {
  color: var(--gt-color-text-tertiary, #909399);
}
</style>
