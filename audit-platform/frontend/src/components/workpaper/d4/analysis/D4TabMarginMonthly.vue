<script setup lang="ts">
/**
 * D4TabMarginMonthly — D4-7 月度毛利率趋势表
 *
 * 12月×产品矩阵 + 波动>5%黄色高亮
 * Requirements: 8.2, 8.3, 19.3
 */
import { inject, toRef, type Ref } from 'vue'
import { useD4Analysis, type MarginRow } from '../../composables/useD4Analysis'
import { isChangeRateExceeding } from '../../composables/useD4FormulaEngine'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const { marginMonthly } = useD4Analysis({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const MONTHS = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']

function fmtPercent(val: number): string {
  return (val * 100).toFixed(1) + '%'
}

function isVolatile(current: number, prior: number): boolean {
  return Math.abs(current - prior) > 0.05
}
</script>

<template>
  <div class="d4-tab-margin-monthly">
    <el-table :data="marginMonthly" border stripe style="width: 100%" max-height="500">
      <el-table-column prop="product" label="产品" min-width="120" fixed />
      <el-table-column v-for="(m, idx) in MONTHS" :key="idx" :label="m" width="80" align="right">
        <template #default="{ row }">
          <span :class="{ 'volatile-cell': isVolatile(row.months[idx] || 0, row.priorMonths[idx] || 0) }">
            {{ fmtPercent(row.months[idx] || 0) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="全年" width="80" align="right">
        <template #default="{ row }">{{ fmtPercent(row.annual) }}</template>
      </el-table-column>
      <el-table-column label="上期" width="80" align="right">
        <template #default="{ row }">{{ fmtPercent(row.priorAnnual) }}</template>
      </el-table-column>
      <el-table-column label="变动" width="80" align="right">
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
          <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-7-note')">💬</el-button>
        </div>
      </div>
      <el-input type="textarea" :rows="3" :disabled="isReadonly" placeholder="请输入月度毛利率分析说明..." />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-margin-monthly { padding: 16px; }
.mt-4 { margin-top: 16px; }
.mb-1 { margin-bottom: 4px; }
.volatile-cell { background-color: #fef9c3; font-weight: 500; }
.text-red-600 { color: #dc2626; font-weight: 600; }
</style>
