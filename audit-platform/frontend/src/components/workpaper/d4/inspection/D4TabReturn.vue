<script setup lang="ts">
/**
 * D4TabReturn — D4-20 退货检查
 *
 * 本期退货 + 期后退货 双段表
 * Requirements: 12.5-12.8
 */
import { inject, toRef, type Ref } from 'vue'
import { useD4Inspection, type ReturnRow } from '../../composables/useD4Inspection'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const { returnRows, postReturnRows, addSample, removeSample } = useD4Inspection({
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
  <div class="d4-tab-return">
    <!-- Section 1: 本期退货 -->
    <h4 class="text-sm font-medium mb-2">一、本期退货</h4>
    <div class="mb-3 flex justify-end">
      <el-button type="primary" size="small" :disabled="isReadonly" @click="addSample('D4-20')">
        + 添加退货
      </el-button>
    </div>

    <el-table :data="returnRows" border stripe max-height="300" class="mb-4">
      <el-table-column prop="customerName" label="客户" min-width="120" />
      <el-table-column prop="returnDate" label="退货日期" width="100" />
      <el-table-column prop="invoiceNo" label="发票号" width="110" />
      <el-table-column prop="productName" label="产品" min-width="100" />
      <el-table-column prop="quantity" label="数量" width="70" align="right" />
      <el-table-column label="金额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.amount) }}</template>
      </el-table-column>
      <el-table-column prop="reason" label="退货原因" min-width="120" />
      <el-table-column label="操作" width="70" align="center" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" size="small" text @click="removeSample('D4-20', row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Section 2: 期后退货 -->
    <h4 class="text-sm font-medium mb-2">二、期后退货（资产负债表日后）</h4>
    <el-table :data="postReturnRows" border stripe max-height="300">
      <el-table-column prop="customerName" label="客户" min-width="120" />
      <el-table-column prop="returnDate" label="退货日期" width="100" />
      <el-table-column prop="invoiceNo" label="发票号" width="110" />
      <el-table-column prop="productName" label="产品" min-width="100" />
      <el-table-column prop="quantity" label="数量" width="70" align="right" />
      <el-table-column label="金额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.amount) }}</template>
      </el-table-column>
      <el-table-column prop="reason" label="退货原因" min-width="120" />
    </el-table>

    <!-- 审计说明 -->
    <div class="mt-4">
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-medium text-gray-600">审计说明/结论</label>
        <div class="flex gap-2">
          <el-button size="small" disabled>🤖 AI辅助</el-button>
          <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-20-note')">💬</el-button>
        </div>
      </div>
      <el-input type="textarea" :rows="3" :disabled="isReadonly" placeholder="请输入退货检查结论..." />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-return { padding: 16px; }
.mt-4 { margin-top: 16px; }
.mb-4 { margin-bottom: 16px; }
.mb-3 { margin-bottom: 12px; }
.mb-2 { margin-bottom: 8px; }
.mb-1 { margin-bottom: 4px; }
</style>
