<script setup lang="ts">
/**
 * D4TabOtherContract — D4-34 合同测算
 *
 * 差异 = 实际确认 - 应确认
 * Requirements: 15.3
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

const { otherContractRows, addRow, removeRow } = useD4OtherGroup({
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
  <div class="d4-tab-other-contract">
    <div class="mb-3 flex justify-between">
      <span class="text-sm text-gray-500">其他收入合同测算（应确认 vs 实际确认）</span>
      <el-button type="primary" size="small" :disabled="isReadonly" @click="addRow('D4-34')">
        + 添加合同
      </el-button>
    </div>

    <el-table :data="otherContractRows" border stripe max-height="450">
      <el-table-column prop="contractName" label="合同名称" min-width="160" />
      <el-table-column label="合同金额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.amount) }}</template>
      </el-table-column>
      <el-table-column prop="term" label="合同期限" width="100" />
      <el-table-column label="应确认" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.shouldRecognize) }}</template>
      </el-table-column>
      <el-table-column label="实际确认" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.actualRecognize) }}</template>
      </el-table-column>
      <el-table-column label="差异" width="120" align="right">
        <template #default="{ row }">
          <span :class="{ 'text-red-500': Math.abs(row.diff) > 0 }">{{ fmtAmount(row.diff) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="100" />
      <el-table-column label="操作" width="70" align="center" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" size="small" text @click="removeRow('D4-34', row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="mt-4">
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-medium text-gray-600">审计说明</label>
        <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-34-note')">💬</el-button>
      </div>
      <el-input type="textarea" :rows="3" :disabled="isReadonly" placeholder="请输入合同测算分析结论..." />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-other-contract { padding: 16px; }
.mt-4 { margin-top: 16px; }
.mb-3 { margin-bottom: 12px; }
.mb-1 { margin-bottom: 4px; }
</style>
