<script setup lang="ts">
/**
 * D4TabDiscount — D4-19 折扣折让
 *
 * 政策 + 明细 + 符合性
 * Requirements: 12.1-12.4
 */
import { inject, toRef, type Ref } from 'vue'
import { useD4Inspection, type DiscountRow } from '../../composables/useD4Inspection'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const { discountRows, addSample, removeSample } = useD4Inspection({
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
  <div class="d4-tab-discount">
    <div class="mb-3 flex justify-end">
      <el-button type="primary" size="small" :disabled="isReadonly" @click="addSample('D4-19')">
        + 添加折扣记录
      </el-button>
    </div>

    <el-table :data="discountRows" border stripe max-height="450">
      <el-table-column prop="customerName" label="客户" min-width="120" />
      <el-table-column prop="contractNo" label="合同号" width="100" />
      <el-table-column prop="discountPolicy" label="折扣政策" min-width="120" />
      <el-table-column label="折扣率" width="80" align="right">
        <template #default="{ row }">{{ (row.discountRate * 100).toFixed(1) }}%</template>
      </el-table-column>
      <el-table-column label="原始金额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.originalAmount) }}</template>
      </el-table-column>
      <el-table-column label="折扣金额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.discountAmount) }}</template>
      </el-table-column>
      <el-table-column label="净额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.netAmount) }}</template>
      </el-table-column>
      <el-table-column label="符合" width="70" align="center">
        <template #default="{ row }">
          <el-tag :type="row.isCompliant === 'Y' ? 'success' : row.isCompliant === 'N' ? 'danger' : 'info'" size="small">
            {{ row.isCompliant || '-' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="70" align="center" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" size="small" text @click="removeSample('D4-19', row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <div class="mt-4">
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-medium text-gray-600">审计说明/结论</label>
        <div class="flex gap-2">
          <el-button size="small" disabled>🤖 AI辅助</el-button>
          <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-19-note')">💬</el-button>
        </div>
      </div>
      <el-input type="textarea" :rows="3" :disabled="isReadonly" placeholder="请输入折扣折让检查结论..." />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-discount { padding: 16px; }
.mt-4 { margin-top: 16px; }
.mb-3 { margin-bottom: 12px; }
.mb-1 { margin-bottom: 4px; }
</style>
