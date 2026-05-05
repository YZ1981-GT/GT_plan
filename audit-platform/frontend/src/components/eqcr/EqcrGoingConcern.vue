<template>
  <div v-loading="loading" class="eqcr-tab">
    <el-card shadow="never" class="eqcr-tab__section">
      <template #header>
        <span class="eqcr-tab__section-title">本年度持续经营评估</span>
        <el-tag
          v-if="currentEval?.conclusion"
          size="small"
          :type="conclusionType(currentEval.conclusion)"
          effect="light"
        >
          {{ conclusionLabel(currentEval.conclusion) }}
        </el-tag>
      </template>

      <el-descriptions
        v-if="currentEval"
        :column="2"
        border
        size="small"
        class="eqcr-tab__desc"
      >
        <el-descriptions-item label="评估日期">
          {{ currentEval.evaluation_date || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="结论">
          {{ conclusionLabel(currentEval.conclusion) }}
        </el-descriptions-item>
        <el-descriptions-item label="管理层计划" :span="2">
          <div class="eqcr-paragraph">
            {{ currentEval.management_plan || '—' }}
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="审计师结论" :span="2">
          <div class="eqcr-paragraph">
            {{ currentEval.auditor_conclusion || '—' }}
          </div>
        </el-descriptions-item>
      </el-descriptions>
      <el-empty
        v-else
        description="该项目尚未建立持续经营评估"
        :image-size="60"
      />
    </el-card>

    <el-card
      v-if="indicators.length > 0"
      shadow="never"
      class="eqcr-tab__section"
    >
      <template #header>
        <span class="eqcr-tab__section-title">持续经营指标</span>
        <el-tag size="small" type="info" effect="plain">
          {{ indicators.length }} 项
        </el-tag>
      </template>

      <el-table
        :data="indicators"
        size="small"
        border
        stripe
        style="width: 100%"
      >
        <el-table-column prop="indicator_type" label="指标类型" min-width="140" />
        <el-table-column label="指标值" min-width="140">
          <template #default="{ row }">
            {{ renderJson(row.indicator_value) }}
          </template>
        </el-table-column>
        <el-table-column label="阈值" min-width="140">
          <template #default="{ row }">
            {{ renderJson(row.threshold) }}
          </template>
        </el-table-column>
        <el-table-column label="是否触发" width="110">
          <template #default="{ row }">
            <el-tag
              v-if="row.is_triggered"
              type="danger"
              size="small"
              effect="light"
            >
              已触发
            </el-tag>
            <el-tag v-else type="success" size="small" effect="light">
              正常
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="严重程度" width="120">
          <template #default="{ row }">
            <el-tag
              v-if="row.severity"
              :type="severityType(row.severity)"
              size="small"
              effect="light"
            >
              {{ severityLabel(row.severity) }}
            </el-tag>
            <span v-else class="eqcr-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="notes" label="备注" min-width="220" />
      </el-table>
    </el-card>

    <el-card
      v-if="priorEvaluations.length > 0"
      shadow="never"
      class="eqcr-tab__section"
    >
      <template #header>
        <span class="eqcr-tab__section-title">历史评估</span>
        <el-tag size="small" type="info" effect="plain">
          {{ priorEvaluations.length }} 次
        </el-tag>
      </template>

      <el-table
        :data="priorEvaluations"
        size="small"
        border
        stripe
        style="width: 100%"
      >
        <el-table-column prop="evaluation_date" label="评估日期" width="140" />
        <el-table-column label="结论" width="120">
          <template #default="{ row }">
            <el-tag
              v-if="row.conclusion"
              size="small"
              :type="conclusionType(row.conclusion)"
              effect="light"
            >
              {{ conclusionLabel(row.conclusion) }}
            </el-tag>
            <span v-else class="eqcr-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="auditor_conclusion" label="审计师结论" min-width="240" />
      </el-table>
    </el-card>

    <el-card shadow="never" class="eqcr-tab__section">
      <template #header>
        <span class="eqcr-tab__section-title">EQCR 复核意见</span>
      </template>
      <EqcrOpinionForm
        :project-id="projectId"
        domain="going_concern"
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
  type EqcrDomainPayload,
  type EqcrGoingConcernData,
  type EqcrGoingConcernEvaluation,
  type EqcrGoingConcernIndicator,
  type EqcrOpinion,
} from '@/services/eqcrService'
import EqcrOpinionForm from './EqcrOpinionForm.vue'

const props = defineProps<{ projectId: string }>()

const loading = ref(false)
const payload = ref<EqcrDomainPayload<EqcrGoingConcernData> | null>(null)

const currentEval = computed<EqcrGoingConcernEvaluation | null>(
  () => payload.value?.data.current_evaluation ?? null,
)
const priorEvaluations = computed<EqcrGoingConcernEvaluation[]>(
  () => payload.value?.data.prior_evaluations ?? [],
)
const indicators = computed<EqcrGoingConcernIndicator[]>(
  () => payload.value?.data.indicators ?? [],
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
    payload.value = await eqcrApi.getGoingConcern(props.projectId)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '加载持续经营数据失败')
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

function conclusionLabel(c: string | null | undefined): string {
  if (!c) return '—'
  const map: Record<string, string> = {
    no_doubt: '无重大疑虑',
    substantial_doubt_with_mitigation: '有重大疑虑（已缓解）',
    substantial_doubt_disclosed: '有重大疑虑（已披露）',
    going_concern_invalid: '持续经营假设不再适用',
  }
  return map[c] ?? c
}

function conclusionType(
  c: string | null | undefined,
): 'info' | 'success' | 'warning' | 'danger' {
  const map: Record<string, 'info' | 'success' | 'warning' | 'danger'> = {
    no_doubt: 'success',
    substantial_doubt_with_mitigation: 'warning',
    substantial_doubt_disclosed: 'warning',
    going_concern_invalid: 'danger',
  }
  return (c && map[c]) || 'info'
}

function severityLabel(s: string | null): string {
  if (!s) return '—'
  const map: Record<string, string> = {
    low: '低',
    medium: '中',
    high: '高',
    critical: '严重',
  }
  return map[s] ?? s
}

function severityType(
  s: string | null,
): 'info' | 'success' | 'warning' | 'danger' {
  const map: Record<string, 'info' | 'success' | 'warning' | 'danger'> = {
    low: 'info',
    medium: 'warning',
    high: 'danger',
    critical: 'danger',
  }
  return (s && map[s]) || 'info'
}

function renderJson(value: any): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch {
      return String(value)
    }
  }
  return String(value)
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
.eqcr-paragraph {
  white-space: pre-wrap;
  line-height: 1.55;
}
</style>
