<script setup lang="ts">
/**
 * D4TabFundFlow — D4-32 资金流水
 *
 * 入出+净额+时间匹配+可疑自动标记(红色高亮)
 * Requirements: 14.11
 */
import { inject, toRef, type Ref } from 'vue'
import { useD4Ipo, type FundFlowRow } from '../../composables/useD4Ipo'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const { fundFlowRows, suspiciousFlows, addRow, removeRow } = useD4Ipo({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

function fmtAmount(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getRowClass({ row }: { row: FundFlowRow }): string {
  return row.isSuspicious ? 'row-suspicious' : ''
}
</script>

<template>
  <div class="d4-tab-fund-flow">
    <!-- 可疑汇总 -->
    <el-alert
      v-if="suspiciousFlows.length > 0"
      type="error"
      :closable="false"
      show-icon
      class="mb-3"
    >
      <template #title>
        检测到 {{ suspiciousFlows.length }} 笔可疑资金回流
        （同一对手方30天内入出且金额差异&lt;10%）
      </template>
    </el-alert>

    <div class="mb-3 flex justify-between">
      <span class="text-sm text-gray-500">资金流水分析（自动标记可疑回流）</span>
      <el-button type="primary" size="small" :disabled="isReadonly" @click="addRow('D4-32')">
        + 添加流水
      </el-button>
    </div>

    <el-table :data="fundFlowRows" border stripe max-height="500" :row-class-name="getRowClass">
      <el-table-column prop="counterparty" label="对手方" min-width="130" />
      <el-table-column label="流入金额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.inAmount) }}</template>
      </el-table-column>
      <el-table-column label="流出金额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.outAmount) }}</template>
      </el-table-column>
      <el-table-column label="净额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.netAmount) }}</template>
      </el-table-column>
      <el-table-column prop="transactionDate" label="交易日期" width="110" />
      <el-table-column prop="daysDiff" label="天数差" width="80" align="center" />
      <el-table-column label="时间匹配" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.timeMatch === 'Y' ? 'success' : row.timeMatch === 'N' ? 'danger' : 'info'" size="small">
            {{ row.timeMatch || '-' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="可疑" width="70" align="center">
        <template #default="{ row }">
          <span v-if="row.isSuspicious" class="suspicious-flag">⚠️</span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="100" />
      <el-table-column label="操作" width="70" align="center" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" size="small" text @click="removeRow('D4-32', row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="mt-4">
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-medium text-gray-600">审计说明（重点关注可疑回流）</label>
        <div class="flex gap-2">
          <el-button size="small" disabled>🤖 AI分析</el-button>
          <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-32-note')">💬</el-button>
        </div>
      </div>
      <el-input type="textarea" :rows="3" :disabled="isReadonly" placeholder="请输入资金流水分析结论..." />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-fund-flow { padding: 16px; }
.mt-4 { margin-top: 16px; }
.mb-3 { margin-bottom: 12px; }
.mb-1 { margin-bottom: 4px; }
.suspicious-flag { font-size: 16px; }

:deep(.row-suspicious) { background-color: #fef0f0 !important; }
:deep(.row-suspicious td) { color: #f56c6c; font-weight: 500; }
</style>
