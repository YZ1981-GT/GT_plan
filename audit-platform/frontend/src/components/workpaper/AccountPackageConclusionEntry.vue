<!--
  AccountPackageConclusionEntry.vue — D1-C / D2-C 结论入口

  spec workpaper-account-package-d1-d2-pilot Task 4.4 + Task 7.1
  提供科目结论入口，展示当前结论状态和进入结论表的链接。
  Task 7.1: 预留 AI 草稿状态展示位。

  Validates: Requirements 2.5, 3.4
-->
<template>
  <div class="gt-conclusion-entry" v-if="hasConclusionSheet">
    <div class="gt-conclusion-entry__header">
      <span class="gt-conclusion-entry__icon">🏁</span>
      <span class="gt-conclusion-entry__title">科目结论（{{ conclusionCode }}）</span>
    </div>
    <div class="gt-conclusion-entry__body">
      <div class="gt-conclusion-entry__status">
        <span class="gt-conclusion-entry__status-label">结论状态：</span>
        <el-tag :type="conclusionStatusType" size="small" effect="light">
          {{ conclusionStatusLabel }}
        </el-tag>
      </div>
      <!-- Task 7.1: AI 草稿状态展示位 -->
      <div v-if="hasAiDraft" class="gt-conclusion-entry__ai-draft">
        <el-tag type="warning" size="small" effect="plain">
          🤖 AI 草稿待确认
        </el-tag>
      </div>
      <div class="gt-conclusion-entry__actions">
        <el-button
          type="primary"
          size="small"
          @click="handleEnterConclusion"
        >
          进入结论表
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  packageId: string
  primaryWpCode: string
  hasConclusionSheet: boolean
  /** Task 7.1: 是否有 pending AI 草稿 */
  hasAiDraft?: boolean
}>()

const conclusionCode = computed(() => `${props.primaryWpCode}-C`)

// 结论状态：当有 AI 草稿时显示"AI 草稿待确认"
const conclusionStatusType = computed<'' | 'success' | 'warning' | 'info'>(() => {
  if (props.hasAiDraft) return 'warning'
  return 'info'
})
const conclusionStatusLabel = computed(() => {
  if (props.hasAiDraft) return 'AI 草稿待确认'
  return '待编制'
})

function handleEnterConclusion() {
  // 后续跳转到结论 sheet
  console.log('[AccountPackageConclusionEntry] navigate to conclusion:', conclusionCode.value)
}
</script>

<style scoped>
.gt-conclusion-entry {
  margin: 16px 0;
  padding: 16px;
  border: 1px solid var(--gt-color-border-purple, #e8e4f0);
  border-radius: 8px;
  background: #fff;
}

.gt-conclusion-entry__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.gt-conclusion-entry__icon {
  font-size: 16px;
}

.gt-conclusion-entry__title {
  font-weight: 600;
  font-size: 14px;
  color: var(--gt-color-primary, #4b2d77);
}

.gt-conclusion-entry__body {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}

.gt-conclusion-entry__status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.gt-conclusion-entry__status-label {
  color: var(--gt-color-text-secondary, #6e6e73);
}

.gt-conclusion-entry__ai-draft {
  display: flex;
  align-items: center;
}
</style>
