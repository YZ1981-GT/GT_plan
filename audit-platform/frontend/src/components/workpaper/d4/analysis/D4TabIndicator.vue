<script setup lang="ts">
/**
 * D4TabIndicator — D4-6 指标分析
 *
 * 指标卡片网格(2列×N行) + TB自动取数 + 结论标记
 * Requirements: 8.1, 8.2, 19.3, 21.7
 */
import { inject, toRef, type Ref } from 'vue'
import { useD4Analysis, type IndicatorRow } from '../../composables/useD4Analysis'
import { isChangeRateExceeding } from '../../composables/useD4FormulaEngine'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const { indicators } = useD4Analysis({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

function fmtChange(val: number | '' | 'N/A'): string {
  if (val === '' || val === 'N/A') return String(val || '-')
  return (val * 100).toFixed(1) + '%'
}

function getConclusionTag(c: string): { type: string; text: string } {
  if (c === 'normal') return { type: 'success', text: '正常' }
  if (c === 'abnormal') return { type: 'danger', text: '异常' }
  if (c === 'attention') return { type: 'warning', text: '关注' }
  return { type: 'info', text: '待评价' }
}
</script>

<template>
  <div class="d4-tab-indicator">
    <el-table :data="indicators" border stripe>
      <el-table-column prop="name" label="指标名称" min-width="160" />
      <el-table-column prop="currentValue" label="本期" width="120" align="right">
        <template #default="{ row }">{{ row.currentValue.toFixed(2) }}</template>
      </el-table-column>
      <el-table-column prop="priorValue" label="上期" width="120" align="right">
        <template #default="{ row }">{{ row.priorValue.toFixed(2) }}</template>
      </el-table-column>
      <el-table-column label="变动" width="100" align="right">
        <template #default="{ row }">
          <span :class="{ 'text-red-600': isChangeRateExceeding(row.change, 0.3) }">
            {{ fmtChange(row.change) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="industryRef" label="行业参考" width="120" />
      <el-table-column label="结论" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="getConclusionTag(row.conclusion).type as any" size="small">
            {{ getConclusionTag(row.conclusion).text }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <div class="mt-4">
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-medium text-gray-600">审计说明</label>
        <div class="flex gap-2">
          <el-button size="small" disabled>🤖 AI辅助</el-button>
          <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-6-note')">💬</el-button>
        </div>
      </div>
      <el-input type="textarea" :rows="3" :disabled="isReadonly" placeholder="请输入审计说明..." />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-indicator { padding: 16px; }
.mt-4 { margin-top: 16px; }
.mb-1 { margin-bottom: 4px; }
.text-red-600 { color: #dc2626; font-weight: 600; }
</style>
