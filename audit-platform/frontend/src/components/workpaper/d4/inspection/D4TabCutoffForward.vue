<script setup lang="ts">
/**
 * D4TabCutoffForward — D4-17 截止正向测试
 *
 * 跨期自动判断 + 天数 + 红色高亮 + 汇总
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

const { cutoffForwardRows, cutoffSummary, addSample, removeSample } = useD4Inspection({
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
  <div class="d4-tab-cutoff-forward">
    <!-- Summary -->
    <el-card shadow="never" class="mb-4">
      <el-descriptions :column="4" size="small">
        <el-descriptions-item label="检查总数">{{ cutoffSummary.total }}</el-descriptions-item>
        <el-descriptions-item label="跨期笔数">
          <span :class="{ 'text-red-600': cutoffSummary.crossCount > 0 }">{{ cutoffSummary.crossCount }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="跨期金额">
          <span :class="{ 'text-red-600': cutoffSummary.crossAmount !== 0 }">{{ fmtAmount(cutoffSummary.crossAmount) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="建议调整">{{ fmtAmount(cutoffSummary.adjustAmount) }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- Toolbar -->
    <div class="mb-3 flex justify-end">
      <el-button type="primary" size="small" :disabled="isReadonly" @click="addSample('D4-17')">
        + 添加样本
      </el-button>
    </div>

    <!-- Table -->
    <el-table :data="cutoffForwardRows" border stripe max-height="450" :row-class-name="({ row }: any) => row.isCrossPeriod ? 'cross-period-row' : ''">
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
          <el-button type="danger" size="small" text @click="removeSample('D4-17', row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <div class="mt-4">
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-medium text-gray-600">审计说明/结论</label>
        <div class="flex gap-2">
          <el-button size="small" disabled>🤖 AI辅助</el-button>
          <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-17-note')">💬</el-button>
        </div>
      </div>
      <el-input type="textarea" :rows="3" :disabled="isReadonly" placeholder="请输入截止正向测试结论..." />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-cutoff-forward { padding: 16px; }
.mt-4 { margin-top: 16px; }
.mb-4 { margin-bottom: 16px; }
.mb-3 { margin-bottom: 12px; }
.mb-1 { margin-bottom: 4px; }
.text-red-600 { color: #dc2626; font-weight: 600; }
:deep(.cross-period-row) { background-color: #fef2f2 !important; }
</style>
