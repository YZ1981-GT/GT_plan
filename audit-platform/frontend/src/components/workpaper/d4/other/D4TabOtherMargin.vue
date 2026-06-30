<script setup lang="ts">
/**
 * D4TabOtherMargin — D4-33 其他业务毛利率分析
 *
 * 同D4-8结构，数据源D4-3
 * Requirements: 15.1
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

const { otherMarginRows, addRow, removeRow } = useD4OtherGroup({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

function fmtAmount(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(v: number): string {
  if (v === 0) return '-'
  return (v * 100).toFixed(2) + '%'
}
</script>

<template>
  <div class="d4-tab-other-margin">
    <div class="mb-3 flex justify-between">
      <span class="text-sm text-gray-500">其他业务收入毛利率分析（数据来源D4-3）</span>
      <el-button type="primary" size="small" :disabled="isReadonly" @click="addRow('D4-33')">
        + 添加项目
      </el-button>
    </div>

    <el-table :data="otherMarginRows" border stripe max-height="450">
      <el-table-column prop="product" label="项目/产品" min-width="160" />
      <el-table-column label="收入" width="130" align="right">
        <template #default="{ row }">{{ fmtAmount(row.revenue) }}</template>
      </el-table-column>
      <el-table-column label="成本" width="130" align="right">
        <template #default="{ row }">{{ fmtAmount(row.cost) }}</template>
      </el-table-column>
      <el-table-column label="毛利率" width="100" align="right">
        <template #default="{ row }">
          <span :class="{ 'text-red-500': Math.abs(row.margin) > 0.5 }">{{ fmtPercent(row.margin) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="70" align="center" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" size="small" text @click="removeRow('D4-33', row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="mt-4">
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-medium text-gray-600">审计说明</label>
        <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-33-note')">💬</el-button>
      </div>
      <el-input type="textarea" :rows="3" :disabled="isReadonly" placeholder="请输入其他毛利分析结论..." />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-other-margin { padding: 16px; }
.mt-4 { margin-top: 16px; }
.mb-3 { margin-bottom: 12px; }
.mb-1 { margin-bottom: 4px; }
</style>
