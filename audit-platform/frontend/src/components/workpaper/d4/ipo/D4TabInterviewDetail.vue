<script setup lang="ts">
/**
 * D4TabInterviewDetail — D4-31 访谈详细记录
 *
 * 单客户逐问答详细
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

const { interviewDetailRows, addRow, removeRow } = useD4Ipo({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})
</script>

<template>
  <div class="d4-tab-interview-detail">
    <div class="mb-3 flex justify-between">
      <span class="text-sm text-gray-500">单客户逐问答详细记录（AI可辅助生成提问清单）</span>
      <div class="flex gap-2">
        <el-button size="small" disabled>🤖 AI建议问题</el-button>
        <el-button type="primary" size="small" :disabled="isReadonly" @click="addRow('D4-31')">
          + 添加记录
        </el-button>
      </div>
    </div>

    <el-table :data="interviewDetailRows" border stripe max-height="450">
      <el-table-column prop="customerName" label="客户" width="110" />
      <el-table-column prop="question" label="问题" min-width="180" />
      <el-table-column prop="answer" label="回答" min-width="200" />
      <el-table-column prop="followUp" label="追问/备注" min-width="140" />
      <el-table-column label="操作" width="70" align="center" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" size="small" text @click="removeRow('D4-31', row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="mt-4">
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-medium text-gray-600">审计说明</label>
        <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-31-note')">💬</el-button>
      </div>
      <el-input type="textarea" :rows="3" :disabled="isReadonly" placeholder="请输入访谈详细记录结论..." />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-interview-detail { padding: 16px; }
.mt-4 { margin-top: 16px; }
.mb-3 { margin-bottom: 12px; }
.mb-1 { margin-bottom: 4px; }
</style>
