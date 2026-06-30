<script setup lang="ts">
/**
 * D4TabInterviewSummary — D4-30 访谈汇总
 *
 * 多客户访谈汇总表
 * Requirements: 14.10
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

const { interviewSummaryRows, addRow, removeRow } = useD4Ipo({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})
</script>

<template>
  <div class="d4-tab-interview-summary">
    <div class="mb-3 flex justify-between">
      <span class="text-sm text-gray-500">客户访谈汇总</span>
      <el-button type="primary" size="small" :disabled="isReadonly" @click="addRow('D4-30')">
        + 添加访谈
      </el-button>
    </div>

    <el-table :data="interviewSummaryRows" border stripe max-height="450">
      <el-table-column prop="customerName" label="客户" min-width="120" />
      <el-table-column prop="interviewDate" label="访谈日期" width="110" />
      <el-table-column prop="interviewee" label="受访人" width="100" />
      <el-table-column prop="keyFindings" label="主要发现" min-width="200" />
      <el-table-column label="结论" width="90" align="center">
        <template #default="{ row }">
          <el-tag
            :type="row.conclusion === 'abnormal' ? 'danger' : row.conclusion === 'attention' ? 'warning' : 'success'"
            size="small"
          >
            {{ row.conclusion === 'normal' ? '正常' : row.conclusion === 'abnormal' ? '异常' : row.conclusion === 'attention' ? '关注' : '-' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="70" align="center" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" size="small" text @click="removeRow('D4-30', row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="mt-4">
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-medium text-gray-600">审计说明</label>
        <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-30-note')">💬</el-button>
      </div>
      <el-input type="textarea" :rows="3" :disabled="isReadonly" placeholder="请输入访谈汇总结论..." />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-interview-summary { padding: 16px; }
.mt-4 { margin-top: 16px; }
.mb-3 { margin-bottom: 12px; }
.mb-1 { margin-bottom: 4px; }
</style>
