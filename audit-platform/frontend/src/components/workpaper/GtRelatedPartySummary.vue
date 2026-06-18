<script setup lang="ts">
/**
 * GtRelatedPartySummary — A7-1 关联方交易及关联往来汇总
 *
 * 从后端 API 获取关联方注册表 + 交易记录，
 * 渲染为项目/母公司/子公司/合计矩阵形式。
 *
 * spec: a7-a15-completion-workpapers Task 40
 */
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/services/apiProxy'
import { useProjectStore } from '@/stores/project'

const props = defineProps<{
  wpId?: string
  projectId?: string
  year?: number
}>()

const route = useRoute()
const projectStore = useProjectStore()

const resolvedProjectId = computed(
  () => props.projectId || (route.params.projectId as string) || '',
)
const resolvedYear = computed(
  () => props.year || parseInt(route.query.year as string) || projectStore.year || new Date().getFullYear() - 1,
)

interface RelatedParty {
  id: string
  party_name: string
  relationship: string
  transaction_count: number
  total_amount: number
}

const parties = ref<RelatedParty[]>([])
const loading = ref(false)
const totalAmount = ref(0)
const totalCount = ref(0)

async function loadData() {
  if (!resolvedProjectId.value) return
  loading.value = true
  try {
    const res = await api.get<{
      parties: RelatedParty[]
      total_amount: number
      total_count: number
    }>(`/api/projects/${resolvedProjectId.value}/related-party-summary`, {
      params: { year: resolvedYear.value },
    })
    parties.value = res?.parties || []
    totalAmount.value = res?.total_amount || 0
    totalCount.value = res?.total_count || 0
  } catch {
    // 降级：无数据时保持空态
  } finally {
    loading.value = false
  }
}

function formatAmount(val: number): string {
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2 })
}

onMounted(loadData)
</script>

<template>
  <div class="related-party-summary">
    <div v-if="loading" class="related-party-summary__loading">
      <el-skeleton :rows="5" animated />
    </div>

    <div v-else-if="parties.length === 0" class="related-party-summary__empty">
      <el-empty description="暂无关联方交易数据">
        <template #description>
          <p>在「关联方注册表」录入关联方并登记交易后，此处自动汇总。</p>
        </template>
      </el-empty>
    </div>

    <div v-else>
      <el-alert type="info" :closable="false" style="margin-bottom: 12px">
        <template #title>
          共 {{ parties.length }} 个关联方，{{ totalCount }} 笔交易，合计 {{ formatAmount(totalAmount) }} 元
        </template>
      </el-alert>

      <el-table :data="parties" border stripe size="small" class="gt-compact-table">
        <el-table-column prop="party_name" label="关联方名称" min-width="180" />
        <el-table-column prop="relationship" label="关联关系" width="150" />
        <el-table-column prop="transaction_count" label="交易笔数" width="100" align="center" />
        <el-table-column label="交易金额" width="140" align="right">
          <template #default="{ row }">
            {{ formatAmount(row.total_amount) }}
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<style scoped>
.related-party-summary__empty {
  padding: 40px 0;
  text-align: center;
}
.related-party-summary__loading {
  padding: 24px;
}
</style>
