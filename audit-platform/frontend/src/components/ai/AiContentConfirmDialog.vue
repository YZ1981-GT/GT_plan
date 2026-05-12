<template>
  <el-dialog
    :model-value="visible"
    title="AI 内容确认"
    width="520px"
    :close-on-click-modal="false"
    @update:model-value="$emit('update:visible', $event)"
    @close="onClose"
  >
    <!-- AI 内容信息 -->
    <div class="ai-confirm-info" v-if="aiContentItem">
      <div class="ai-confirm-meta">
        <el-tag type="warning" size="small">🤖 AI 生成</el-tag>
        <span class="ai-confirm-model">模型: {{ aiContentItem.source_model || '未知' }}</span>
        <span class="ai-confirm-confidence">置信度: {{ formatConfidence(aiContentItem.confidence) }}</span>
      </div>
      <div class="ai-confirm-target" v-if="aiContentItem.target_cell">
        目标单元格: <code>{{ aiContentItem.target_cell }}</code>
      </div>
      <div class="ai-confirm-content">
        <label>AI 生成内容：</label>
        <div class="ai-confirm-content-text">{{ aiContentItem.content }}</div>
      </div>
    </div>

    <!-- 修订模式：编辑区 -->
    <div v-if="mode === 'revise'" class="ai-confirm-revise">
      <label>修订内容：</label>
      <el-input
        v-model="revisedContent"
        type="textarea"
        :rows="4"
        placeholder="请输入修订后的内容..."
      />
    </div>

    <!-- 操作按钮 -->
    <template #footer>
      <div class="ai-confirm-actions">
        <el-button
          type="success"
          :loading="submitting"
          @click="onAccept"
        >
          ✅ 确认采纳
        </el-button>
        <el-button
          type="warning"
          :loading="submitting"
          @click="onRevise"
        >
          ✏️ 修订
        </el-button>
        <el-button
          type="danger"
          :loading="submitting"
          @click="onReject"
        >
          ❌ 拒绝
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

export interface AiContentItemForConfirm {
  id: string
  type?: string
  source_model?: string
  confidence?: number
  content?: string
  target_cell?: string | null
  target_field?: string | null
  confirmed_by?: string | null
  confirmed_at?: string | null
  confirm_action?: string | null
  revised_content?: string | null
}

const props = defineProps<{
  visible: boolean
  aiContentItem: AiContentItemForConfirm | null
}>()

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
  (e: 'confirm', action: 'accept' | 'revise' | 'reject', revisedContent?: string): void
}>()

const mode = ref<'choose' | 'revise'>('choose')
const revisedContent = ref('')
const submitting = ref(false)

watch(() => props.visible, (val) => {
  if (val) {
    mode.value = 'choose'
    revisedContent.value = props.aiContentItem?.content || ''
  }
})

function formatConfidence(c?: number): string {
  if (c == null) return '未知'
  return `${(c * 100).toFixed(0)}%`
}

function onAccept() {
  submitting.value = true
  emit('confirm', 'accept')
  submitting.value = false
}

function onRevise() {
  if (mode.value === 'choose') {
    // 第一次点击：切换到修订模式
    mode.value = 'revise'
    return
  }
  // 第二次点击（修订模式下）：提交修订
  if (!revisedContent.value.trim()) {
    return
  }
  submitting.value = true
  emit('confirm', 'revise', revisedContent.value.trim())
  submitting.value = false
}

function onReject() {
  submitting.value = true
  emit('confirm', 'reject')
  submitting.value = false
}

function onClose() {
  mode.value = 'choose'
  revisedContent.value = ''
}
</script>

<style scoped>
.ai-confirm-info {
  margin-bottom: 16px;
}
.ai-confirm-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.ai-confirm-model,
.ai-confirm-confidence {
  font-size: 12px;
  color: #666;
}
.ai-confirm-target {
  font-size: 13px;
  color: #333;
  margin-bottom: 8px;
}
.ai-confirm-target code {
  background: #f5f5f5;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: monospace;
}
.ai-confirm-content label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 4px;
  color: #333;
}
.ai-confirm-content-text {
  background: #faf8ff;
  border: 1px dashed #9b59b6;
  border-radius: 6px;
  padding: 10px 12px;
  font-size: 13px;
  color: #444;
  max-height: 150px;
  overflow-y: auto;
  white-space: pre-wrap;
}
.ai-confirm-revise {
  margin-top: 12px;
}
.ai-confirm-revise label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 4px;
  color: #333;
}
.ai-confirm-actions {
  display: flex;
  gap: 8px;
  justify-content: center;
}
</style>
