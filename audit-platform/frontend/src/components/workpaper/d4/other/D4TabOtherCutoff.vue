<script setup lang="ts">
/**
 * D4TabOtherCutoff — D4-36 其他收入截止测试
 *
 * 同D4-17/18结构
 * Requirements: 15.7
 */
import { inject, toRef, type Ref } from 'vue'
import { useD4OtherGroup, type OtherCutoffRow } from '../../composables/useD4OtherGroup'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const { otherCutoffRows, otherCutoffSummary, addRow, removeRow } = useD4OtherGroup({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

function fmtAmount(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getRowClass({ row }: { row: OtherCutoffRow }): string {
  return row.isCrossPeriod ? 'row-cross-period' : ''
}
</script>

<template>
  <div class="d4-tab-other-cutoff">
    <!-- 汇总信息 -->
    <div class="summary-bar mb-3">
      <span class="summary-item">
        <label>检查总数：</label>
        <strong>{{ otherCutoffSummary.total }}</strong>
      </span>
      <span class="summary-item">
        <label>跨期笔数：</label>
        <strong class="text-red-500">{{ otherCutoffSummary.crossCount }}</strong>
      </span>
      <span class="summary-item">
        <label>跨期金额：</label>
        <strong class="text-red-500">{{ fmtAmount(otherCutoffSummary.crossAmount) }}</strong>
      </span>
      <span class="summary-item">
        <label>建议调整：</label>
        <strong>{{ fmtAmount(otherCutoffSummary.adjustAmount) }}</strong>
      </span>
    </div>

    <div class="mb-3 flex justify-end">
      <el-button type="primary" size="small" :disabled="isReadonly" @click="addRow('D4-36')">
        + 添加凭证
      </el-button>
    </div>

    <el-table :data="otherCutoffRows" border stripe max-height="450" :row-class-name="getRowClass">
      <el-table-column prop="voucherNo" label="凭证号" width="100" />
      <el-table-column prop="voucherDate" label="凭证日期" width="100" />
      <el-table-column prop="customerName" label="客户" min-width="110" />
      <el-table-column label="金额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.amount) }}</template>
      </el-table-column>
      <el-table-column prop="shipDate" label="发货日" width="100" />
      <el-table-column prop="signDate" label="签收日" width="100" />
      <el-table-column prop="acceptDate" label="验收日" width="100" />
      <el-table-column label="跨期" width="60" align="center">
        <template #default="{ row }">
          <el-tag :type="row.isCrossPeriod ? 'danger' : 'success'" size="small">
            {{ row.isCrossPeriod ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="天数" width="60" align="center">
        <template #default="{ row }">{{ row.crossPeriodDays || '-' }}</template>
      </el-table-column>
      <el-table-column prop="adjustSuggestion" label="调整建议" min-width="100" />
      <el-table-column label="操作" width="70" align="center" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" size="small" text @click="removeRow('D4-36', row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="mt-4">
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-medium text-gray-600">审计说明</label>
        <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-36-note')">💬</el-button>
      </div>
      <el-input type="textarea" :rows="3" :disabled="isReadonly" placeholder="请输入截止测试结论..." />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-other-cutoff { padding: 16px; }
.mt-4 { margin-top: 16px; }
.mb-3 { margin-bottom: 12px; }
.mb-1 { margin-bottom: 4px; }
.summary-bar {
  display: flex; gap: 24px; padding: 8px 12px;
  background: #f5f7fa; border-radius: 4px;
}
.summary-item label { color: #606266; font-size: 13px; }
.summary-item strong { color: #303133; }
:deep(.row-cross-period) { background-color: #fef0f0 !important; }
</style>
