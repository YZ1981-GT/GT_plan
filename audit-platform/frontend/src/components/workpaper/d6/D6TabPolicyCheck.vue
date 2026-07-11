<template>
<div class="d6-tab-policy-check">
  <!-- 编制提示 -->
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 逐段评价被审计单位合同资产坏账准备会计政策及 ECL 模型的合理性，对照 CAS22 金融工具减值准则要求。</p>
      <p>2. 每段评价应关注政策合规性、历史损失率预测、前瞻性信息调整及同行业可比性。</p>
      <p>3. 评价结论应与 D6-8 减值测算的损失率参数选取相互印证。</p>
      <p>4. 发现政策不当或参数不合理时，应评估对减值准备计提充分性的影响并考虑调整。</p>
    </div>
  </details>

  <!-- 审计目标 -->
  <el-alert
    type="info"
    :closable="false"
    title="审计目标：评价合同资产坏账准备会计政策及 ECL 模型的合理性与一贯性，确认损失率选取及前瞻性调整符合 CAS22 要求。"
    class="objective-alert"
  />

  <!-- 工具栏 -->
  <div class="tab-toolbar">
    <div class="toolbar-left"></div>
    <div class="toolbar-right">
      <span class="chip-wrap"><GtIndexChip value="wp:D6-8" :context-project-id="projectId" /></span>
    </div>
  </div>

  <div class="audit-objective">
    <h4>审计目标（可编辑）</h4>
    <el-input
      v-model="auditObjective"
      type="textarea"
      :autosize="{ minRows: 2, maxRows: 6 }"
      :disabled="isReadonly"
      placeholder="本程序审计目标..."
    />
  </div>

  <div v-for="item in policyEvalItems" :key="item.id" class="eval-card">
    <div class="eval-header">
      <span class="eval-title">{{ item.title }}</span>
      <el-button size="small" @click="openReview(item.itemId)">💬</el-button>
    </div>
    <el-input
      :model-value="evaluations[item.id]"
      type="textarea"
      :autosize="{ minRows: 4, maxRows: 12 }"
      :disabled="isReadonly"
      placeholder="请输入审计评价..."
      @change="(v: string) => updateEvaluation(item.id, v)"
    />
  </div>

  <!-- 审计意见区（卡片式） -->
  <el-card class="opinion-card" shadow="never">
    <template #header>
      <div class="opinion-header">
        <span class="opinion-title">审计说明与结论</span>
        <div class="opinion-chips">
          <GtIndexChip value="wp:D6-8" :context-project-id="projectId" />
        </div>
      </div>
    </template>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">三、审计说明</span>
        <div class="opinion-actions">
          <el-button size="small" @click="openReview('D6-7-note-explanation')">💬</el-button>
        </div>
      </div>
      <el-input v-model="auditNotes.explanation" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="政策检查过程及发现..." />
    </div>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">四、审计结论</span>
        <div class="opinion-actions">
          <el-button size="small" @click="openReview('D6-7-note-conclusion')">💬</el-button>
        </div>
      </div>
      <el-input v-model="auditNotes.conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="政策合理性结论..." />
    </div>
  </el-card>
</div>
</template>

<script setup lang="ts">
/**
 * D6TabPolicyCheck.vue — 减值准备会计政策检查 D6-7（段落式）
 */
import { inject, toRef, type Ref } from 'vue'
import { useD6PolicyCheck } from '../composables/useD6PolicyCheck'
import type { ChecklistResponse } from '../composables/useD6FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, ChecklistResponse>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
function openReview(sectionId: string) { openReviewDialog(sectionId) }

const {
  evaluations, updateEvaluation, auditObjective, auditNotes, policyEvalItems,
} = useD6PolicyCheck({
  allResponses: allResponsesRef,
  debouncedSave: props.debouncedSave,
})
</script>

<style scoped>
.d6-tab-policy-check { padding: 16px; }

/* 编制提示 */
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

/* 工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }

.audit-objective { margin-bottom: 20px; }
.audit-objective h4 { font-size: 14px; font-weight: 600; margin-bottom: 8px; color: #303133; }

.eval-card {
  margin-bottom: 20px;
  padding: 16px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fff;
}
.eval-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.eval-title { font-size: 14px; font-weight: 600; color: #303133; }

/* 审计意见卡片 */
.opinion-card {
  margin-top: 16px;
  border-radius: 8px;
}
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.opinion-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.opinion-chips {
  display: flex;
  gap: 6px;
}
.opinion-section {
  margin-bottom: 16px;
}
.opinion-section:last-child {
  margin-bottom: 0;
}
.opinion-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.opinion-section-label {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}
.opinion-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}
</style>
