<script setup lang="ts">
/**
 * D4TabOverseas — D4-26 境外销售核对
 *
 * 贸易条款 + 海关金额 + 账面差异
 * Requirements: 14.6
 */
import { inject, toRef, type Ref } from 'vue'
import { useD4Ipo } from '../../composables/useD4Ipo'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const { overseasRows, addRow, removeRow } = useD4Ipo({
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
  <div class="d4-tab-overseas">
    <div class="mb-3 flex justify-between">
      <span class="text-sm text-gray-500">境外销售：海关申报数据与账面金额对比</span>
      <el-button type="primary" size="small" :disabled="isReadonly" @click="addRow('D4-26')">
        + 添加记录
      </el-button>
    </div>

    <el-table :data="overseasRows" border stripe max-height="450">
      <el-table-column prop="customer" label="客户" min-width="120" />
      <el-table-column prop="country" label="国家/地区" width="100" />
      <el-table-column prop="tradeTerms" label="贸易条款" width="100" />
      <el-table-column label="海关金额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.customsAmount) }}</template>
      </el-table-column>
      <el-table-column label="账面金额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.bookAmount) }}</template>
      </el-table-column>
      <el-table-column label="差异" width="120" align="right">
        <template #default="{ row }">
          <span :class="{ 'text-red-500': Math.abs(row.diff) > 0 }">{{ fmtAmount(row.diff) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="100" />
      <el-table-column label="操作" width="70" align="center" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" size="small" text @click="removeRow('D4-26', row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="mt-4">
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-medium text-gray-600">审计说明</label>
        <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-26-note')">💬</el-button>
      </div>
      <el-input type="textarea" :rows="3" :disabled="isReadonly" placeholder="请输入境外销售核对结论..." />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-overseas { padding: 16px; }
.mt-4 { margin-top: 16px; }
.mb-3 { margin-bottom: 12px; }
.mb-1 { margin-bottom: 4px; }
</style>
