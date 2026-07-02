<script setup lang="ts">
/**
 * D1AuditNoteSection.vue — 通用审计说明/结论子组件
 *
 * Spec: .kiro/specs/d1-inspection-check/
 * Task: 19.4
 *
 * 职责：
 * - 审计说明 textarea + 🤖AI(disabled) + 💬复核对话入口
 * - 审计结论 textarea + 🤖AI(disabled) + 💬复核对话入口
 * - 编制提示折叠区（<details> 蓝色左边线+浅蓝背景，默认收起）
 * - emit(update:note/update:conclusion) 通知父组件
 *
 * Requirements: 20.4
 */
import { inject } from 'vue'

const props = defineProps<{
  /** 唯一标识，用于复核对话 sectionId 前缀，如 'D1-inventory' */
  sectionId: string
  /** 审计说明文本 */
  noteText: string
  /** 审计结论文本 */
  conclusionText: string
  /** 编制提示段落数组 */
  guidanceHtml: string[]
  /** 是否只读 */
  isReadonly: boolean
}>()

const emit = defineEmits<{
  'update:note': [value: string]
  'update:conclusion': [value: string]
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<any>('openReviewDialog', null)

// ─── Methods ─────────────────────────────────────────────────────────────────

function onReview(suffix: string) {
  if (openReviewDialog) openReviewDialog({ sectionId: `${props.sectionId}-${suffix}` })
}
</script>

<template>
  <div class="d1-audit-note-section">
    <!-- 审计说明 -->
    <div class="section-title">审计说明</div>
    <div class="note-section">
      <el-input
        type="textarea"
        :rows="4"
        :model-value="noteText"
        placeholder="请输入审计说明..."
        :disabled="isReadonly"
        @change="(v: string) => emit('update:note', v || '')"
      />
      <div class="note-actions">
        <el-tooltip content="AI生成（开发中）" placement="top">
          <el-button size="small" disabled>🤖 AI</el-button>
        </el-tooltip>
        <el-button
          v-if="openReviewDialog"
          size="small"
          @click="onReview('note')"
        >
          💬 复核
        </el-button>
      </div>
    </div>

    <!-- 审计结论 -->
    <div class="section-title">审计结论</div>
    <div class="note-section">
      <el-input
        type="textarea"
        :rows="4"
        :model-value="conclusionText"
        placeholder="请输入审计结论..."
        :disabled="isReadonly"
        @change="(v: string) => emit('update:conclusion', v || '')"
      />
      <div class="note-actions">
        <el-tooltip content="AI生成（开发中）" placement="top">
          <el-button size="small" disabled>🤖 AI</el-button>
        </el-tooltip>
        <el-button
          v-if="openReviewDialog"
          size="small"
          @click="onReview('conclusion')"
        >
          💬 复核
        </el-button>
      </div>
    </div>

    <!-- 编制提示 -->
    <details v-if="guidanceHtml.length > 0" class="guidance-fold">
      <summary>📋 编制提示</summary>
      <p v-for="(t, i) in guidanceHtml" :key="'g-' + i">{{ t }}</p>
    </details>
  </div>
</template>

<style scoped>
/* 段落标题 */
.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin: 18px 0 10px;
}

/* 审计说明/结论区 */
.note-section {
  margin-bottom: 8px;
}

.note-actions {
  margin-top: 6px;
  display: flex;
  gap: 8px;
}

/* 编制提示折叠区 — 匹配 D1TabInventoryCount.vue 的 guidance-fold 样式 */
.guidance-fold {
  margin: 16px 0;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  padding: 10px 14px;
  border-radius: 0 4px 4px 0;
  font-size: 13px;
  color: #606266;
}

.guidance-fold summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}

.guidance-fold p {
  margin: 6px 0;
  line-height: 1.6;
}
</style>
