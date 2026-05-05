<template>
  <div v-loading="loading" class="eqcr-tab">
    <el-card shadow="never" class="eqcr-tab__section">
      <template #header>
        <span class="eqcr-tab__section-title">会计估计相关底稿</span>
        <el-tag size="small" type="info" effect="plain">
          共 {{ items.length }} 份
        </el-tag>
        <el-tag
          v-if="keywords.length > 0"
          size="small"
          effect="plain"
          style="margin-left: 8px"
        >
          关键词：{{ keywords.join('、') }}
        </el-tag>
      </template>

      <el-empty
        v-if="!loading && items.length === 0"
        description="未匹配到含估计/减值/折旧/摊销等关键词的底稿"
        :image-size="60"
      />

      <el-table
        v-else
        :data="items"
        size="small"
        border
        stripe
        style="width: 100%"
      >
        <el-table-column prop="wp_code" label="底稿编号" width="120" />
        <el-table-column prop="wp_name" label="底稿名称" min-width="220" />
        <el-table-column prop="audit_cycle" label="循环" width="120" />
        <el-table-column label="索引状态" width="120">
          <template #default="{ row }">
            <el-tag
              v-if="row.index_status"
              size="small"
              :type="indexStatusType(row.index_status)"
              effect="light"
            >
              {{ indexStatusLabel(row.index_status) }}
            </el-tag>
            <span v-else class="eqcr-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="底稿状态" width="120">
          <template #default="{ row }">
            <el-tag
              v-if="row.file_status"
              size="small"
              :type="fileStatusType(row.file_status)"
              effect="light"
            >
              {{ fileStatusLabel(row.file_status) }}
            </el-tag>
            <span v-else class="eqcr-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="复核状态" width="120">
          <template #default="{ row }">
            <el-tag
              v-if="row.review_status"
              size="small"
              :type="reviewStatusType(row.review_status)"
              effect="light"
            >
              {{ reviewStatusLabel(row.review_status) }}
            </el-tag>
            <span v-else class="eqcr-muted">—</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="eqcr-tab__section">
      <template #header>
        <span class="eqcr-tab__section-title">EQCR 复核意见</span>
      </template>
      <EqcrOpinionForm
        :project-id="projectId"
        domain="estimate"
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
  type EqcrEstimateData,
  type EqcrEstimateItem,
  type EqcrOpinion,
} from '@/services/eqcrService'
import EqcrOpinionForm from './EqcrOpinionForm.vue'

const props = defineProps<{ projectId: string }>()

const loading = ref(false)
const payload = ref<EqcrDomainPayload<EqcrEstimateData> | null>(null)

const items = computed<EqcrEstimateItem[]>(
  () => payload.value?.data.items ?? [],
)
const keywords = computed<string[]>(() => payload.value?.data.keywords ?? [])
const currentOpinion = computed<EqcrOpinion | null>(
  () => payload.value?.current_opinion ?? null,
)
const historyOpinions = computed<EqcrOpinion[]>(
  () => payload.value?.history_opinions ?? [],
)

async function load() {
  loading.value = true
  try {
    payload.value = await eqcrApi.getEstimates(props.projectId)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '加载会计估计数据失败')
    payload.value = null
  } finally {
    loading.value = false
  }
}

function onOpinionSaved(_: EqcrOpinion) {
  load()
}

onMounted(load)

// ─── 辅助：状态文案与 tag type ────────────────────────────────────────────

function indexStatusLabel(s: string): string {
  const map: Record<string, string> = {
    planned: '待生成',
    generated: '已生成',
    assigned: '已分配',
    completed: '已完成',
    archived: '已归档',
  }
  return map[s] ?? s
}
function indexStatusType(s: string): 'info' | 'warning' | 'success' | 'primary' {
  const map: Record<string, 'info' | 'warning' | 'success' | 'primary'> = {
    planned: 'info',
    generated: 'warning',
    assigned: 'primary',
    completed: 'success',
    archived: 'success',
  }
  return map[s] ?? 'info'
}

function fileStatusLabel(s: string): string {
  const map: Record<string, string> = {
    draft: '草稿',
    in_progress: '进行中',
    edit_complete: '编辑完成',
    under_review: '复核中',
    completed: '已完成',
    archived: '已归档',
  }
  return map[s] ?? s
}
function fileStatusType(s: string): 'info' | 'warning' | 'success' | 'primary' {
  const map: Record<string, 'info' | 'warning' | 'success' | 'primary'> = {
    draft: 'info',
    in_progress: 'warning',
    edit_complete: 'primary',
    under_review: 'warning',
    completed: 'success',
    archived: 'success',
  }
  return map[s] ?? 'info'
}

function reviewStatusLabel(s: string): string {
  const map: Record<string, string> = {
    pending: '待复核',
    in_review: '复核中',
    approved: '已通过',
    rejected: '已退回',
  }
  return map[s] ?? s
}
function reviewStatusType(
  s: string,
): 'info' | 'warning' | 'success' | 'danger' {
  const map: Record<string, 'info' | 'warning' | 'success' | 'danger'> = {
    pending: 'info',
    in_review: 'warning',
    approved: 'success',
    rejected: 'danger',
  }
  return map[s] ?? 'info'
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
.eqcr-muted {
  color: var(--gt-color-text-tertiary, #909399);
}
</style>
