<template>
<div class="d6-tab-policy-check">
  <details class="guidance-hint">
    <summary>📋 编制提示</summary>
    <div class="hint-content">
      逐段评价被审计单位合同资产减值准备会计政策及ECL模型的合理性，对照CAS22准则要求。
      每段评价应关注政策合规性、历史损失预测、前瞻性信息及同行业对比。
      <GtIndexChip wp-code="D6-8" label="→D6-8测算" style="margin-left:4px" />
    </div>
  </details>

  <div class="audit-objective">
    <h4>审计目标</h4>
    <el-input
      v-model="auditObjective"
      type="textarea"
      :autosize="{ minRows: 2, maxRows: 4 }"
      :disabled="isReadonly"
      placeholder="本程序审计目标..."
    />
  </div>

  <div v-for="item in policyEvalItems" :key="item.id" class="eval-card">
    <h4 class="eval-title">{{ item.title }}</h4>
    <el-input
      :model-value="evaluations[item.id]"
      type="textarea"
      :autosize="{ minRows: 4, maxRows: 12 }"
      :disabled="isReadonly"
      placeholder="请输入审计评价..."
      @change="(v: string) => updateEvaluation(item.id, v)"
    />
    <div class="note-actions">
      <el-button size="small" @click="openReview(item.itemId)">💬复核</el-button>
    </div>
  </div>

  <div class="audit-notes-section">
    <h4>三、审计说明</h4>
    <el-input v-model="auditNotes.explanation" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="政策检查过程及发现..." />
    <div class="note-actions">
      <el-button size="small" @click="openReview('D6-7-note-explanation')">💬复核</el-button>
    </div>
  </div>
  <div class="audit-notes-section">
    <h4>四、审计结论</h4>
    <el-input v-model="auditNotes.conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="政策合理性结论..." />
    <div class="note-actions">
      <el-button size="small" @click="openReview('D6-7-note-conclusion')">💬复核</el-button>
    </div>
  </div>
</div>
</template>

<script setup lang="ts">
/**
 * D6TabPolicyCheck.vue — 减值准备会计政策检查 D6-7（段落式）
 */
import { inject, type Ref } from 'vue'
import { useD6PolicyCheck } from '../composables/useD6PolicyCheck'
import type { ChecklistResponse } from '../composables/useD6FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
function openReview(sectionId: string) { openReviewDialog(sectionId) }

const {
  evaluations, updateEvaluation, auditObjective, auditNotes, policyEvalItems,
} = useD6PolicyCheck({
  allResponses: props.allResponses,
  debouncedSave: props.debouncedSave,
})
</script>

<style scoped>
.d6-tab-policy-check { padding: 16px; }
.guidance-hint {
  margin-bottom: 16px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
}
.guidance-hint summary { padding: 8px 12px; cursor: pointer; font-size: 13px; color: #409eff; }
.hint-content { padding: 8px 12px 12px; font-size: 12px; color: #606266; line-height: 1.6; }
.audit-objective { margin-bottom: 20px; }
.audit-objective h4, .eval-title { font-size: 14px; font-weight: 600; margin-bottom: 8px; color: #303133; }
.eval-card {
  margin-bottom: 20px;
  padding: 16px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fff;
}
.audit-notes-section { margin-top: 20px; }
.audit-notes-section h4 { font-size: 14px; font-weight: 600; margin-bottom: 8px; }
.note-actions { display: flex; gap: 8px; margin-top: 6px; }
</style>
