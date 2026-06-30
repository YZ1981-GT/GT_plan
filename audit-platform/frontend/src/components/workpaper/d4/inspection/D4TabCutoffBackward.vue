<script setup lang="ts">
/**
 * D4TabCutoffBackward — D4-18 截止反向测试
 *
 * 跨期自动判断 + 天数 + 红色高亮（方向：期后→期内）
 * Requirements: 11.1-11.8, 19.8
 */
import { inject, toRef, type Ref } from 'vue'
import { useD4Inspection, type CutoffRow } from '../../composables/useD4Inspection'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const { cutoffBackwardRows, cutoffSummary, addSample, removeSample } = useD4Inspection({
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
</script>

<template>
  <div class="d4-tab-cutoff-backward">
    <!-- Toolbar -->
    <div class="mb-3 flex justify-between items-center">
      <span class="text-sm text-gray-500">反向测试：检查期后确认收入是否应归属本期</span>
      <el-button type="primary" size="small" :disabled="isReadonly" @click="addSample('D4-18')">
        + 添加样本
      </el-button>
    </div>

    <!-- Table -->
    <el-table :data="cutoffBackwardRows" border stripe max-height="450" :row-class-name="({ row }: any) => row.isCrossPeriod ? 'cross-period-row' : ''">
      <el-table-column prop="voucherNo" label="凭证号" width="100" />
      <el-table-column prop="voucherDate" label="凭证日期" width="100" />
      <el-table-column prop="customerName" label="客户" min-width="120" />
      <el-table-column label="金额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.amount) }}</template>
      </el-table-column>
      <el-table-column prop="shipDate" label="发货日" width="100" />
      <el-table-column prop="signDate" label="签收日" width="100" />
      <el-table-column prop="acceptDate" label="验收日" width="100" />
      <el-table-column label="跨期" width="60" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.isCrossPeriod" type="danger" size="small">是</el-tag>
          <span v-else>否</span>
        </template>
      </el-table-column>
      <el-table-column label="天数" width="60" align="center">
        <template #default="{ row }">
          <span :class="{ 'text-red-600': row.crossPeriodDays > 0 }">{{ row.crossPeriodDays || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="adjustSuggestion" label="调整建议" min-width="120" />
      <el-table-column label="操作" width="70" align="center" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" size="small" text @click="removeSample('D4-18', row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <div class="mt-4">
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-medium text-gray-600">审计说明/结论</label>
        <div class="flex gap-2">
          <el-button size="small" disabled>🤖 AI辅助</el-button>
          <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-18-note')">💬</el-button>
        </div>
      </div>
      <el-input type="textarea" :rows="3" :disabled="isReadonly" placeholder="请输入截止反向测试结论..." />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-cutoff-backward { padding: 16px; }
.mt-4 { margin-top: 16px; }
.mb-3 { margin-bottom: 12px; }
.mb-1 { margin-bottom: 4px; }
.text-red-600 { color: #dc2626; font-weight: 600; }
:deep(.cross-period-row) { background-color: #fef2f2 !important; }
</style>
