<script setup lang="ts">
/**
 * D4TabCustomerStructure — D4-9 客户结构
 *
 * Top5/Top10客户集中度 + HHI + >50%警告
 * Requirements: 8.4, 17.6
 */
import { inject, toRef, type Ref } from 'vue'
import { useD4Analysis, type CustomerRankRow } from '../../composables/useD4Analysis'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const { top5Customers, top10Customers, hhi, concentrationWarning } = useD4Analysis({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

function fmtAmount(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(v: number): string {
  return v.toFixed(2) + '%'
}
</script>

<template>
  <div class="d4-tab-customer-structure">
    <!-- Warning -->
    <el-alert
      v-if="concentrationWarning"
      :title="concentrationWarning"
      type="warning"
      show-icon
      :closable="false"
      class="mb-4"
    />

    <!-- HHI -->
    <div class="mb-4 text-sm text-gray-600">
      赫芬达尔指数(HHI): <strong>{{ hhi.toFixed(0) }}</strong>
      <span v-if="hhi > 2500" class="text-red-600 ml-2">高度集中</span>
      <span v-else-if="hhi > 1500" class="text-orange-500 ml-2">中度集中</span>
      <span v-else class="text-green-600 ml-2">分散</span>
    </div>

    <!-- Top5 Table -->
    <h4 class="text-sm font-medium mb-2">前五大客户</h4>
    <el-table :data="top5Customers" border stripe size="small" class="mb-4">
      <el-table-column prop="rank" label="排名" width="60" align="center" />
      <el-table-column prop="name" label="客户名称" min-width="180" />
      <el-table-column label="金额" width="140" align="right">
        <template #default="{ row }">{{ fmtAmount(row.amount) }}</template>
      </el-table-column>
      <el-table-column label="占比" width="100" align="right">
        <template #default="{ row }">{{ fmtPercent(row.proportion) }}</template>
      </el-table-column>
    </el-table>

    <!-- Top10 Table -->
    <h4 class="text-sm font-medium mb-2">前十大客户</h4>
    <el-table :data="top10Customers" border stripe size="small">
      <el-table-column prop="rank" label="排名" width="60" align="center" />
      <el-table-column prop="name" label="客户名称" min-width="180" />
      <el-table-column label="金额" width="140" align="right">
        <template #default="{ row }">{{ fmtAmount(row.amount) }}</template>
      </el-table-column>
      <el-table-column label="占比" width="100" align="right">
        <template #default="{ row }">{{ fmtPercent(row.proportion) }}</template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <div class="mt-4">
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-medium text-gray-600">审计说明</label>
        <div class="flex gap-2">
          <el-button size="small" disabled>🤖 AI辅助</el-button>
          <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-9-note')">💬</el-button>
        </div>
      </div>
      <el-input type="textarea" :rows="3" :disabled="isReadonly" placeholder="请输入客户集中度分析说明..." />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-customer-structure { padding: 16px; }
.mt-4 { margin-top: 16px; }
.mb-4 { margin-bottom: 16px; }
.mb-2 { margin-bottom: 8px; }
.mb-1 { margin-bottom: 4px; }
.text-red-600 { color: #dc2626; }
.text-orange-500 { color: #f97316; }
.text-green-600 { color: #16a34a; }
.ml-2 { margin-left: 8px; }
</style>
