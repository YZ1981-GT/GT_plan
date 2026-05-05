<template>
  <div v-loading="loading" class="eqcr-tab">
    <el-alert
      :closable="false"
      type="info"
      show-icon
      title="EQCR 视角为只读"
      description="关联方注册与交易录入由项目经理负责（Round 5 任务 7 提供写入界面），EQCR 仅就数据与意见判断。"
    />

    <el-card shadow="never" class="eqcr-tab__section">
      <template #header>
        <span class="eqcr-tab__section-title">关联方注册</span>
        <el-tag size="small" type="info" effect="plain">
          共 {{ summary.registry_count }} 家
        </el-tag>
      </template>

      <el-empty
        v-if="!loading && registries.length === 0"
        description="该项目尚未登记关联方"
        :image-size="60"
      />

      <el-table
        v-else
        :data="registries"
        size="small"
        border
        stripe
        style="width: 100%"
      >
        <el-table-column prop="name" label="关联方名称" min-width="220" />
        <el-table-column prop="relation_type" label="关系类型" width="160" />
        <el-table-column label="同一控制" width="110">
          <template #default="{ row }">
            <el-tag
              v-if="row.is_controlled_by_same_party"
              type="warning"
              size="small"
              effect="light"
            >
              是
            </el-tag>
            <span v-else class="eqcr-muted">否</span>
          </template>
        </el-table-column>
        <el-table-column label="登记时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="eqcr-tab__section">
      <template #header>
        <span class="eqcr-tab__section-title">关联方交易</span>
        <el-tag size="small" type="info" effect="plain">
          共 {{ summary.transaction_count }} 笔
        </el-tag>
      </template>

      <el-empty
        v-if="!loading && transactions.length === 0"
        description="该项目尚未登记关联方交易"
        :image-size="60"
      />

      <el-table
        v-else
        :data="transactions"
        size="small"
        border
        stripe
        style="width: 100%"
      >
        <el-table-column label="关联方" min-width="220">
          <template #default="{ row }">
            {{ registryName(row.related_party_id) }}
          </template>
        </el-table-column>
        <el-table-column prop="transaction_type" label="交易类型" width="140" />
        <el-table-column label="金额" width="180" align="right">
          <template #default="{ row }">
            {{ formatAmount(row.amount) }}
          </template>
        </el-table-column>
        <el-table-column label="是否公允" width="110">
          <template #default="{ row }">
            <el-tag
              v-if="row.is_arms_length === true"
              type="success"
              size="small"
              effect="light"
            >
              公允
            </el-tag>
            <el-tag
              v-else-if="row.is_arms_length === false"
              type="danger"
              size="small"
              effect="light"
            >
              非公允
            </el-tag>
            <span v-else class="eqcr-muted">未评</span>
          </template>
        </el-table-column>
        <el-table-column label="证据引用" min-width="200">
          <template #default="{ row }">
            <span v-if="!row.evidence_refs" class="eqcr-muted">—</span>
            <span v-else>{{ renderEvidence(row.evidence_refs) }}</span>
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
        domain="related_party"
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
  type EqcrOpinion,
  type EqcrRelatedPartyData,
  type EqcrRelatedPartyRegistry,
  type EqcrRelatedPartyTransaction,
} from '@/services/eqcrService'
import EqcrOpinionForm from './EqcrOpinionForm.vue'

const props = defineProps<{ projectId: string }>()

const loading = ref(false)
const payload = ref<EqcrDomainPayload<EqcrRelatedPartyData> | null>(null)

const registries = computed<EqcrRelatedPartyRegistry[]>(
  () => payload.value?.data.registries ?? [],
)
const transactions = computed<EqcrRelatedPartyTransaction[]>(
  () => payload.value?.data.transactions ?? [],
)
const summary = computed(
  () =>
    payload.value?.data.summary ?? {
      registry_count: 0,
      transaction_count: 0,
    },
)
const currentOpinion = computed<EqcrOpinion | null>(
  () => payload.value?.current_opinion ?? null,
)
const historyOpinions = computed<EqcrOpinion[]>(
  () => payload.value?.history_opinions ?? [],
)

const registryNameMap = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const r of registries.value) {
    map[r.id] = r.name
  }
  return map
})

function registryName(id: string): string {
  return registryNameMap.value[id] ?? '（已删除）'
}

async function load() {
  loading.value = true
  try {
    payload.value = await eqcrApi.getRelatedParties(props.projectId)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '加载关联方数据失败')
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

function formatAmount(value: string | null): string {
  if (value === null || value === undefined || value === '') return '—'
  const num = Number(value)
  if (Number.isNaN(num)) return value
  return num.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

function renderEvidence(refs: any): string {
  if (Array.isArray(refs)) {
    return refs.length === 0 ? '—' : refs.join('、')
  }
  if (typeof refs === 'string') return refs
  try {
    return JSON.stringify(refs)
  } catch {
    return '—'
  }
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
