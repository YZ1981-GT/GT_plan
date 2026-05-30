<!--
  EControlAiPanel.vue — AI 建议面板（3 子模式复用）

  封装 useWpAiSuggest 接入 + 采纳/修改/忽略 UI。
  shell 持有本面板，子模式 emit 'ai-suggest' 冒泡 → shell 转发调用 requestSuggestion。

  gt-c-note-table-shrink Task 12
  Validates: Requirements 12
-->

<template>
  <div
    v-if="showSuggestionPanel && currentSuggestion"
    class="gt-e__ai-panel"
  >
    <div class="gt-e__ai-panel-header">
      <span class="gt-e__ai-panel-title">🤖 AI 建议</span>
      <el-tag size="small" :type="currentSuggestion.confidence >= 0.7 ? 'success' : 'warning'">
        置信度 {{ Math.round(currentSuggestion.confidence * 100) }}%
      </el-tag>
    </div>
    <pre class="gt-e__ai-panel-text">{{ currentSuggestion.text }}</pre>
    <div class="gt-e__ai-panel-actions">
      <el-button type="primary" size="small" @click="handleAdopt">✅ 采纳</el-button>
      <el-button size="small" @click="handleModify">✏️ 修改后采纳</el-button>
      <el-button size="small" @click="handleIgnore">❌ 忽略</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useWpAiSuggest } from '@/composables/useWpAiSuggest'

const props = defineProps<{
  wpId: string
  sheetName: string
  testType: string
}>()

const emit = defineEmits<{
  'adopt': [fieldName: string, text: string]
  'modify': [fieldName: string, text: string]
}>()

const {
  aiEnabled,
  aiLoading,
  currentSuggestion,
  showSuggestionPanel,
  assistedFieldsList,
  requestSuggestion,
  adoptSuggestion,
  modifySuggestion,
  ignoreSuggestion,
} = useWpAiSuggest({ wpId: props.wpId, sheetName: props.sheetName })

/**
 * 请求 AI 建议（由 shell 调用，转发子模式的 ai-suggest 事件）
 */
function triggerSuggestion(fieldName: string, existingContent: string = '') {
  requestSuggestion('fields.' + fieldName, existingContent)
}

function handleAdopt() {
  if (!currentSuggestion.value) return
  const fieldName = currentSuggestion.value.fieldName.replace(/^fields\./, '')
  const text = adoptSuggestion()
  if (text) {
    emit('adopt', fieldName, text)
  }
}

function handleModify() {
  if (!currentSuggestion.value) return
  const fieldName = currentSuggestion.value.fieldName.replace(/^fields\./, '')
  const text = currentSuggestion.value.text
  modifySuggestion(text)
  emit('modify', fieldName, text)
}

function handleIgnore() {
  ignoreSuggestion()
}

defineExpose({
  triggerSuggestion,
  aiEnabled,
  aiLoading,
  currentSuggestion,
  showSuggestionPanel,
  assistedFieldsList,
})
</script>

<style scoped>
.gt-e__ai-panel {
  margin-top: 8px;
  border: 1px solid var(--el-color-primary-light-5);
  border-radius: 6px;
  padding: 12px;
  background: var(--el-color-primary-light-9);
  width: 100%;
}
.gt-e__ai-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.gt-e__ai-panel-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-color-primary);
}
.gt-e__ai-panel-text {
  margin: 0 0 10px;
  padding: 8px 12px;
  background: var(--gt-color-bg-white, #fff);
  border-radius: 4px;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--el-text-color-regular);
  max-height: 200px;
  overflow-y: auto;
}
.gt-e__ai-panel-actions {
  display: flex;
  gap: 8px;
}
</style>
