<script setup lang="ts">
/**
 * D4TabOtherCheck — D4-35 其他收入凭证检查
 *
 * 同D4-14结构(发生检查)
 * Requirements: 15.5
 */
import { inject, toRef, type Ref } from 'vue'
import { useD4OtherGroup } from '../../composables/useD4OtherGroup'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const { otherCheckRows, otherCheckAnomalyRate, addRow, removeRow } = useD4OtherGroup({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

function fmtAmount(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<template>
  <div class="d4-tab-other-check">
    <!-- 汇总信息 -->
    <div class="summary-bar mb-3">
      <span class="summary-item">
        <label>检查笔数：</label>
        <strong>{{ otherCheckRows.length }}</strong>
      </span>
      <span class="summary-item">
        <label>异常率：</label>
        <strong :class="{ 'text-red-500': otherCheckAnomalyRate > 5 }">
          {{ otherCheckAnomalyRate.toFixed(2) }}%
        </strong>
      </span>
    </div>

    <div class="mb-3 flex justify-end">
      <el-button type="primary" size="small" :disabled="isReadonly" @click="addRow('D4-35')">
        + 添加凭证
      </el-button>
    </div>

    <el-table :data="otherCheckRows" border stripe max-height="450">
      <el-table-column prop="voucherNo" label="凭证号" width="100" />
      <el-table-column prop="voucherDate" label="凭证日期" width="100" />
      <el-table-column prop="customerName" label="客户" min-width="120" />
      <el-table-column label="金额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.amount) }}</template>
      </el-table-column>
      <el-table-column label="合同" width="60" align="center">
        <template #default="{ row }">{{ row.hasContract || '-' }}</template>
      </el-table-column>
      <el-table-column label="发货" width="60" align="center">
        <template #default="{ row }">{{ row.hasDelivery || '-' }}</template>
      </el-table-column>
      <el-table-column label="发票" width="60" align="center">
        <template #default="{ row }">{{ row.hasInvoice || '-' }}</template>
      </el-table-column>
      <el-table-column label="异常" width="60" align="center">
        <template #default="{ row }">
          <el-tag :type="row.isAnomalous ? 'danger' : 'success'" size="small">
            {{ row.isAnomalous ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="100" />
      <el-table-column label="操作" width="70" align="center" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" size="small" text @click="removeRow('D4-35', row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="mt-4">
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-medium text-gray-600">审计说明</label>
        <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-35-note')">💬</el-button>
      </div>
      <el-input type="textarea" :rows="3" :disabled="isReadonly" placeholder="请输入其他收入凭证检查结论..." />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-other-check { padding: 16px; }
.mt-4 { margin-top: 16px; }
.mb-3 { margin-bottom: 12px; }
.mb-1 { margin-bottom: 4px; }
.summary-bar {
  display: flex; gap: 24px; padding: 8px 12px;
  background: #f5f7fa; border-radius: 4px;
}
.summary-item label { color: #606266; font-size: 13px; }
.summary-item strong { color: #303133; }
</style>
