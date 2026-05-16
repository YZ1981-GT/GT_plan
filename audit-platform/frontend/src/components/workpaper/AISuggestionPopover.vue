<script setup lang="ts">
/**
 * AI 建议浮窗
 * Sprint 7 Task 7.6: 确认写入/修改后写入/拒绝 三按钮
 */
import { ref, computed } from 'vue'

interface AISuggestion {
  id: string
  content: string
  confidence: number
  source_model: string
  target_field?: string
  target_cell?: string
  generated_at: string
}

const props = defineProps<{
  suggestion: AISuggestion | null
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'confirm', suggestion: AISuggestion): void
  (e: 'revise', suggestion: AISuggestion, revisedContent: string): void
  (e: 'reject', suggestion: AISuggestion): void
  (e: 'close'): void
}>()

const isEditing = ref(false)
const revisedContent = ref('')

const confidenceLabel = computed(() => {
  if (!props.suggestion) return ''
  const c = props.suggestion.confidence
  if (c >= 0.8) return '高'
  if (c >= 0.5) return '中'
  return '低'
})

const confidenceType = computed((): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' => {
  if (!props.suggestion) return 'info'
  const c = props.suggestion.confidence
  if (c >= 0.8) return 'success'
  if (c >= 0.5) return 'warning'
  return 'danger'
})

function handleConfirm() {
  if (props.suggestion) {
    emit('confirm', props.suggestion)
    emit('close')
  }
}

function startRevise() {
  if (props.suggestion) {
    revisedContent.value = props.suggestion.content
    isEditing.value = true
  }
}

function handleRevise() {
  if (props.suggestion && revisedContent.value.trim()) {
    emit('revise', props.suggestion, revisedContent.value.trim())
    isEditing.value = false
    emit('close')
  }
}

function handleReject() {
  if (props.suggestion) {
    emit('reject', props.suggestion)
    emit('close')
  }
}

function cancelEdit() {
  isEditing.value = false
  revisedContent.value = ''
}
</script>

<template>
  <el-popover
    :visible="visible && !!suggestion"
    placement="bottom"
    :width="420"
    :trigger="('manual' as any)"
    popper-class="ai-suggestion-popover"
  >
    <template #reference>
      <slot />
    </template>

    <div v-if="suggestion" class="ai-suggestion-content">
      <div class="suggestion-header">
        <div class="header-left">
          <el-icon class="ai-icon"><svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M12 2a2 2 0 012 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 017 7h1a1 1 0 110 2h-1v1a7 7 0 01-7 7h-1v1.27c.6.34 1 .99 1 1.73a2 2 0 11-4 0c0-.74.4-1.39 1-1.73V24h-1a7 7 0 01-7-7v-1H2a1 1 0 110-2h1a7 7 0 017-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 012-2z"/></svg></el-icon>
          <span class="title">AI 建议</span>
        </div>
        <el-tag :type="confidenceType || undefined" size="small">
          置信度: {{ confidenceLabel }}
        </el-tag>
      </div>

      <!-- 内容展示 -->
      <div v-if="!isEditing" class="suggestion-body">
        <p class="suggestion-text">{{ suggestion.content }}</p>
        <div class="meta">
          <span>模型: {{ suggestion.source_model }}</span>
          <span v-if="suggestion.target_field">目标: {{ suggestion.target_field }}</span>
        </div>
      </div>

      <!-- 编辑模式 -->
      <div v-else class="suggestion-edit">
        <el-input
          v-model="revisedContent"
          type="textarea"
          :rows="4"
          placeholder="修改 AI 建议内容..."
        />
      </div>

      <!-- 操作按钮 -->
      <div class="suggestion-actions">
        <template v-if="!isEditing">
          <el-button type="success" size="small" @click="handleConfirm">
            ✓ 确认写入
          </el-button>
          <el-button type="warning" size="small" @click="startRevise">
            ✎ 修改后写入
          </el-button>
          <el-button type="danger" size="small" @click="handleReject">
            ✗ 拒绝
          </el-button>
        </template>
        <template v-else>
          <el-button type="primary" size="small" @click="handleRevise">
            保存修改
          </el-button>
          <el-button size="small" @click="cancelEdit">取消</el-button>
        </template>
      </div>
    </div>
  </el-popover>
</template>

<style scoped>
.ai-suggestion-content {
  padding: 4px;
}
.suggestion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 6px;
}
.ai-icon {
  color: var(--el-color-primary);
}
.title {
  font-weight: 600;
  font-size: var(--gt-font-size-sm);
}
.suggestion-body {
  margin-bottom: 12px;
}
.suggestion-text {
  margin: 0 0 8px;
  padding: 8px 12px;
  background: var(--gt-bg-info);
  border-radius: 6px;
  font-size: var(--gt-font-size-sm);
  line-height: 1.6;
  color: var(--gt-color-text-primary);
}
.meta {
  display: flex;
  gap: 12px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-info);
}
.suggestion-edit {
  margin-bottom: 12px;
}
.suggestion-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
</style>
