<!--
  OpeningReconciliation — 期初核对视图

  展示本年期初 vs 上年审定差异列表，支持分析说明录入。
  Requirements: 2.2, 2.3
-->
<template>
  <div class="opening-reconciliation">
    <div class="opening-reconciliation__summary">
      <el-tag :type="data?.reconciled ? 'success' : 'warning'" size="small">
        {{ data?.reconciled ? '期初核对一致' : `${data?.differences?.length || 0} 项差异` }}
      </el-tag>
      <span class="opening-reconciliation__count">
        已匹配 {{ data?.matched || 0 }} / {{ data?.total_accounts || 0 }}
      </span>
    </div>

    <el-table
      v-if="sortedDifferences.length"
      :data="sortedDifferences"
      border
      class="gt-compact-table"
      max-height="400"
    >
      <el-table-column prop="account_code" label="科目编码" width="110" sortable />
      <el-table-column prop="account_name" label="科目名称" min-width="200" show-overflow-tooltip />
      <el-table-column prop="current_opening" label="本年期初" width="160" align="right">
        <template #default="{ row }"><GtAmountCell :value="row.current_opening" /></template>
      </el-table-column>
      <el-table-column prop="prior_audited" label="上年审定" width="160" align="right">
        <template #default="{ row }"><GtAmountCell :value="row.prior_audited" /></template>
      </el-table-column>
      <el-table-column prop="difference" label="差异" width="160" align="right">
        <template #default="{ row }">
          <GtAmountCell :value="row.difference" />
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-else-if="data" description="无差异，期初核对通过" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from '@/services/apiProxy'
import GtAmountCell from '@/components/common/GtAmountCell.vue'

const props = defineProps<{
  projectId: string
  year: number
  priorProjectId?: string
}>()

const data = ref<any>(null)

// 按科目编码从小到大排序
const sortedDifferences = computed(() => {
  const diffs = data.value?.differences || []
  return [...diffs].sort((a: any, b: any) => {
    const ca = String(a.account_code || '')
    const cb = String(b.account_code || '')
    return ca.localeCompare(cb, undefined, { numeric: true })
  })
})

async function loadData() {
  try {
    const params: Record<string, any> = {}
    if (props.priorProjectId) params.prior_project_id = props.priorProjectId
    data.value = await api.get(
      `/api/workpapers/${props.projectId}/${props.year}/opening-reconcile`,
      { params },
    )
  } catch { /* 降级 */ }
}

onMounted(loadData)
defineExpose({ loadData })
</script>

<style scoped>
.opening-reconciliation__summary {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.opening-reconciliation__count {
  font-size: var(--wp-font-size, 13px);
  color: #909399;
}
.text-danger { color: #f56c6c; font-weight: 600; }
</style>
