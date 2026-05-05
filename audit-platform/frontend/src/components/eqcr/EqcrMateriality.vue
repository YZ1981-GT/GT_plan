<template>
  <div v-loading="loading" class="eqcr-tab">
    <!-- 顶部：当前年重要性 -->
    <el-card shadow="never" class="eqcr-tab__section">
      <template #header>
        <span class="eqcr-tab__section-title">本年重要性水平</span>
        <el-tag v-if="current?.year" size="small" type="info" effect="light">
          {{ current.year }} 年
        </el-tag>
        <el-tag
          v-if="current?.is_override"
          size="small"
          type="warning"
          effect="light"
          style="margin-left: 6px"
        >
          已被覆盖
        </el-tag>
      </template>

      <el-descriptions
        v-if="current"
        :column="2"
        border
        size="small"
        class="eqcr-tab__desc"
      >
        <el-descriptions-item label="基准类型">
          {{ current.benchmark_type || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="基准金额">
          {{ formatAmount(current.benchmark_amount) }}
        </el-descriptions-item>
        <el-descriptions-item label="整体重要性 (%)">
          {{ formatPercent(current.overall_percentage) }}
        </el-descriptions-item>
        <el-descriptions-item label="整体重要性金额">
          {{ formatAmount(current.overall_materiality) }}
        </el-descriptions-item>
        <el-descriptions-item label="实际执行重要性比例">
          {{ formatPercent(current.performance_ratio) }}
        </el-descriptions-item>
        <el-descriptions-item label="实际执行重要性金额">
          {{ formatAmount(current.performance_materiality) }}
        </el-descriptions-item>
        <el-descriptions-item label="明显微小错报比例">
          {{ formatPercent(current.trivial_ratio) }}
        </el-descriptions-item>
        <el-descriptions-item label="明显微小错报阈值">
          {{ formatAmount(current.trivial_threshold) }}
        </el-descriptions-item>
        <el-descriptions-item
          v-if="current.is_override"
          label="覆盖原因"
          :span="2"
        >
          {{ current.override_reason || '—' }}
        </el-descriptions-item>
      </el-descriptions>
      <el-empty
        v-else
        description="该项目尚未设定重要性水平"
        :image-size="60"
      />
    </el-card>

    <!-- 下方：历年重要性 -->
    <el-card
      v-if="priorYears.length > 0"
      shadow="never"
      class="eqcr-tab__section"
    >
      <template #header>
        <span class="eqcr-tab__section-title">历年重要性</span>
        <el-tag size="small" type="info" effect="plain">
          {{ priorYears.length }} 年记录
        </el-tag>
      </template>

      <el-table
        :data="priorYears"
        size="small"
        border
        stripe
        style="width: 100%"
      >
        <el-table-column prop="year" label="年度" width="80" />
        <el-table-column prop="benchmark_type" label="基准" width="110" />
        <el-table-column label="基准金额" width="160">
          <template #default="{ row }">
            {{ formatAmount(row.benchmark_amount) }}
          </template>
        </el-table-column>
        <el-table-column label="整体重要性" width="160">
          <template #default="{ row }">
            {{ formatAmount(row.overall_materiality) }}
          </template>
        </el-table-column>
        <el-table-column label="实际执行重要性" width="180">
          <template #default="{ row }">
            {{ formatAmount(row.performance_materiality) }}
          </template>
        </el-table-column>
        <el-table-column label="明显微小阈值" width="160">
          <template #default="{ row }">
            {{ formatAmount(row.trivial_threshold) }}
          </template>
        </el-table-column>
        <el-table-column label="覆盖">
          <template #default="{ row }">
            <el-tag
              v-if="row.is_override"
              size="small"
              type="warning"
              effect="light"
            >
              是
            </el-tag>
            <span v-else class="eqcr-muted">否</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- EQCR 意见录入 -->
    <el-card shadow="never" class="eqcr-tab__section">
      <template #header>
        <span class="eqcr-tab__section-title">EQCR 复核意见</span>
      </template>
      <EqcrOpinionForm
        :project-id="projectId"
        domain="materiality"
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
  type EqcrMaterialityData,
  type EqcrMaterialitySnapshot,
  type EqcrOpinion,
} from '@/services/eqcrService'
import EqcrOpinionForm from './EqcrOpinionForm.vue'

const props = defineProps<{ projectId: string }>()

const loading = ref(false)
const payload = ref<EqcrDomainPayload<EqcrMaterialityData> | null>(null)

const current = computed<EqcrMaterialitySnapshot | null>(
  () => payload.value?.data.current ?? null,
)
const priorYears = computed<EqcrMaterialitySnapshot[]>(
  () => payload.value?.data.prior_years ?? [],
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
    payload.value = await eqcrApi.getMateriality(props.projectId)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '加载重要性数据失败')
    payload.value = null
  } finally {
    loading.value = false
  }
}

function onOpinionSaved(_: EqcrOpinion) {
  // 重新拉取以同步 current/history
  load()
}

onMounted(load)

// ─── 辅助 ──────────────────────────────────────────────────────────────────

function formatAmount(value: string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const num = Number(value)
  if (Number.isNaN(num)) return value
  return num.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function formatPercent(value: string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const num = Number(value)
  if (Number.isNaN(num)) return value
  // 后端通常存 0.05 / 0.75 之类小数
  return (num * 100).toFixed(2) + '%'
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
