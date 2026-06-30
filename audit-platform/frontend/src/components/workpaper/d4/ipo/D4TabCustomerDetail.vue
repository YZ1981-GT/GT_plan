<script setup lang="ts">
/**
 * D4TabCustomerDetail — D4-29 客户核查详细
 *
 * 动态逐客户详细核查
 * Requirements: 14.9
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

const { customerDetailRows, addRow, removeRow } = useD4Ipo({
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
  <div class="d4-tab-customer-detail">
    <div class="mb-3 flex justify-between">
      <span class="text-sm text-gray-500">逐客户详细核查信息</span>
      <el-button type="primary" size="small" :disabled="isReadonly" @click="addRow('D4-29')">
        + 添加客户
      </el-button>
    </div>

    <el-table :data="customerDetailRows" border stripe max-height="450">
      <el-table-column prop="customerName" label="客户名称" min-width="130" />
      <el-table-column prop="registrationDate" label="注册日期" width="110" />
      <el-table-column label="注册资本" width="110" align="right">
        <template #default="{ row }">{{ fmtAmount(row.registeredCapital) }}</template>
      </el-table-column>
      <el-table-column prop="mainBusiness" label="主营业务" min-width="120" />
      <el-table-column label="交易金额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.transactionAmount) }}</template>
      </el-table-column>
      <el-table-column prop="cooperationYears" label="合作年限" width="80" align="center" />
      <el-table-column prop="remark" label="备注" min-width="100" />
      <el-table-column label="操作" width="70" align="center" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" size="small" text @click="removeRow('D4-29', row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="mt-4">
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-medium text-gray-600">审计说明</label>
        <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-29-note')">💬</el-button>
      </div>
      <el-input type="textarea" :rows="3" :disabled="isReadonly" placeholder="请输入核查结论..." />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-customer-detail { padding: 16px; }
.mt-4 { margin-top: 16px; }
.mb-3 { margin-bottom: 12px; }
.mb-1 { margin-bottom: 4px; }
</style>
