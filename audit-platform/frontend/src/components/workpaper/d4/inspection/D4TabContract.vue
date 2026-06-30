<script setup lang="ts">
/**
 * D4TabContract — D4-12 合同检查
 *
 * 动态行 + 覆盖率指示 + 结论下拉
 * Requirements: 9.1-9.7, 19.5
 */
import { inject, toRef, type Ref } from 'vue'
import { useD4Inspection, type ContractRow } from '../../composables/useD4Inspection'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const { contractRows, coverageRate, addSample, removeSample } = useD4Inspection({
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
  <div class="d4-tab-contract">
    <!-- Coverage indicator -->
    <el-card shadow="never" class="mb-4">
      <div class="flex items-center gap-4">
        <span class="text-sm text-gray-600">合同覆盖率：</span>
        <el-progress
          :percentage="Math.min(coverageRate, 100)"
          :stroke-width="8"
          :color="coverageRate >= 60 ? '#67c23a' : '#e6a23c'"
          style="width: 200px;"
        />
        <span class="text-sm font-medium">{{ coverageRate.toFixed(1) }}%</span>
        <el-tag v-if="coverageRate < 60" type="warning" size="small">覆盖率不足</el-tag>
      </div>
    </el-card>

    <!-- Toolbar -->
    <div class="mb-3 flex justify-end">
      <el-button type="primary" size="small" :disabled="isReadonly" @click="addSample('D4-12')">
        + 添加合同
      </el-button>
    </div>

    <!-- Table -->
    <el-table :data="contractRows" border stripe max-height="500">
      <el-table-column prop="customerName" label="客户名称" min-width="120" />
      <el-table-column prop="contractNo" label="合同编号" width="120" />
      <el-table-column prop="contractDate" label="合同日期" width="110" />
      <el-table-column label="金额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.amount) }}</template>
      </el-table-column>
      <el-table-column prop="revenueType" label="收入类型" width="100" />
      <el-table-column prop="performanceObligation" label="履约义务" min-width="120" />
      <el-table-column prop="recognitionBasis" label="确认依据" min-width="100" />
      <el-table-column label="结论" width="80" align="center">
        <template #default="{ row }">
          <el-tag
            :type="row.conclusion === 'Y' ? 'success' : row.conclusion === 'N' ? 'danger' : 'info'"
            size="small"
          >
            {{ row.conclusion || '-' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="70" align="center" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" size="small" text @click="removeSample('D4-12', row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <div class="mt-4">
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-medium text-gray-600">审计说明/结论</label>
        <div class="flex gap-2">
          <el-button size="small" disabled>🤖 AI辅助</el-button>
          <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-12-note')">💬</el-button>
        </div>
      </div>
      <el-input type="textarea" :rows="3" :disabled="isReadonly" placeholder="请输入合同检查审计结论..." />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-contract { padding: 16px; }
.mt-4 { margin-top: 16px; }
.mb-4 { margin-bottom: 16px; }
.mb-3 { margin-bottom: 12px; }
.mb-1 { margin-bottom: 4px; }
</style>
