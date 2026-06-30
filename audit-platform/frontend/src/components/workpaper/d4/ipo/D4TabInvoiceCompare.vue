<script setup lang="ts">
/**
 * D4TabInvoiceCompare — D4-23 发票对比
 *
 * 月度收入vs开票金额对比 + >10%黄色
 * Requirements: 14.3
 */
import { inject, toRef, type Ref } from 'vue'
import { useD4Ipo, type InvoiceCompareRow } from '../../composables/useD4Ipo'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const { invoiceRows, addRow, removeRow } = useD4Ipo({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

function fmtAmount(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(v: number | '' | 'N/A'): string {
  if (v === '' || v === 'N/A') return String(v || '-')
  return (v * 100).toFixed(2) + '%'
}

function getRowClass({ row }: { row: InvoiceCompareRow }): string {
  if (typeof row.diffRate === 'number' && Math.abs(row.diffRate) > 0.1) return 'row-yellow'
  return ''
}
</script>

<template>
  <div class="d4-tab-invoice-compare">
    <div class="mb-3 flex justify-between">
      <span class="text-sm text-gray-500">按月对比收入确认金额与开票金额差异</span>
      <el-button type="primary" size="small" :disabled="isReadonly" @click="addRow('D4-23')">
        + 添加月份
      </el-button>
    </div>

    <el-table :data="invoiceRows" border stripe max-height="450" :row-class-name="getRowClass">
      <el-table-column prop="month" label="月份" width="90" />
      <el-table-column label="收入金额" width="130" align="right">
        <template #default="{ row }">{{ fmtAmount(row.revenue) }}</template>
      </el-table-column>
      <el-table-column label="开票金额" width="130" align="right">
        <template #default="{ row }">{{ fmtAmount(row.invoiceAmount) }}</template>
      </el-table-column>
      <el-table-column label="差异" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.diff) }}</template>
      </el-table-column>
      <el-table-column label="差异率" width="100" align="right">
        <template #default="{ row }">{{ fmtRate(row.diffRate) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="70" align="center" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" size="small" text @click="removeRow('D4-23', row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="mt-4">
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-medium text-gray-600">审计说明</label>
        <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-23-note')">💬</el-button>
      </div>
      <el-input type="textarea" :rows="3" :disabled="isReadonly" placeholder="请输入发票对比分析结论..." />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-invoice-compare { padding: 16px; }
.mt-4 { margin-top: 16px; }
.mb-3 { margin-bottom: 12px; }
.mb-1 { margin-bottom: 4px; }
:deep(.row-yellow) { background-color: #fdf6ec !important; }
</style>
