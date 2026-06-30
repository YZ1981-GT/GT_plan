<script setup lang="ts">
/**
 * D4TabProductMargin — D4-8 产品毛利对比
 *
 * 从crossSheet productRevenueForMargin取数 + 变动>10%红色
 * Requirements: 8.3, 17.5
 */
import { inject, toRef, type Ref } from 'vue'
import { useD4Analysis, type ProductMarginRow } from '../../composables/useD4Analysis'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const { productMargins } = useD4Analysis({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

function fmtAmount(v: number): string {
  if (v === 0) return '-'
  if (v < 0) return `(${Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(v: number): string {
  return (v * 100).toFixed(2) + '%'
}
</script>

<template>
  <div class="d4-tab-product-margin">
    <el-table :data="productMargins" border stripe>
      <el-table-column prop="product" label="产品" min-width="140" />
      <el-table-column label="本期收入" width="130" align="right">
        <template #default="{ row }">{{ fmtAmount(row.currentRevenue) }}</template>
      </el-table-column>
      <el-table-column label="本期成本" width="130" align="right">
        <template #default="{ row }">{{ fmtAmount(row.currentCost) }}</template>
      </el-table-column>
      <el-table-column label="本期毛利率" width="110" align="right">
        <template #default="{ row }">{{ fmtPercent(row.currentMargin) }}</template>
      </el-table-column>
      <el-table-column label="上期毛利率" width="110" align="right">
        <template #default="{ row }">{{ fmtPercent(row.priorMargin) }}</template>
      </el-table-column>
      <el-table-column label="变动" width="100" align="right">
        <template #default="{ row }">
          <span :class="{ 'text-red-600': Math.abs(row.change) > 0.1 }">
            {{ fmtPercent(row.change) }}
          </span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <div class="mt-4">
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-medium text-gray-600">审计说明</label>
        <div class="flex gap-2">
          <el-button size="small" disabled>🤖 AI辅助</el-button>
          <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-8-note')">💬</el-button>
        </div>
      </div>
      <el-input type="textarea" :rows="3" :disabled="isReadonly" placeholder="请输入产品毛利分析说明..." />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-product-margin { padding: 16px; }
.mt-4 { margin-top: 16px; }
.mb-1 { margin-bottom: 4px; }
.text-red-600 { color: #dc2626; font-weight: 600; }
</style>
