<script setup lang="ts">
/**
 * D4TabErpCheck — D4-13 ERP核对
 *
 * 差异 = 账面 - ERP，差异≠0红色高亮
 * Requirements: 10.1-10.4
 */
import { inject, toRef, type Ref } from 'vue'
import { useD4Inspection, type ErpCheckRow } from '../../composables/useD4Inspection'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const { erpRows, addSample, removeSample } = useD4Inspection({
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
  <div class="d4-tab-erp-check">
    <div class="mb-3 flex justify-end">
      <el-button type="primary" size="small" :disabled="isReadonly" @click="addSample('D4-13')">
        + 添加月度
      </el-button>
    </div>

    <el-table :data="erpRows" border stripe>
      <el-table-column prop="month" label="月份" width="80" />
      <el-table-column label="账面金额" width="140" align="right">
        <template #default="{ row }">{{ fmtAmount(row.bookAmount) }}</template>
      </el-table-column>
      <el-table-column label="ERP金额" width="140" align="right">
        <template #default="{ row }">{{ fmtAmount(row.erpAmount) }}</template>
      </el-table-column>
      <el-table-column label="差异" width="140" align="right">
        <template #default="{ row }">
          <span :class="{ 'text-red-600': row.difference !== 0 }">
            {{ fmtAmount(row.difference) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="explanation" label="差异说明" min-width="200" />
      <el-table-column label="操作" width="70" align="center" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" size="small" text @click="removeSample('D4-13', row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <div class="mt-4">
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-medium text-gray-600">审计说明/结论</label>
        <div class="flex gap-2">
          <el-button size="small" disabled>🤖 AI辅助</el-button>
          <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-13-note')">💬</el-button>
        </div>
      </div>
      <el-input type="textarea" :rows="3" :disabled="isReadonly" placeholder="请输入ERP核对结论..." />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-erp-check { padding: 16px; }
.mt-4 { margin-top: 16px; }
.mb-3 { margin-bottom: 12px; }
.mb-1 { margin-bottom: 4px; }
.text-red-600 { color: #dc2626; font-weight: 600; }
</style>
