<template>
  <div class="wp-note-textarea" :class="{ 'is-card': card }">
    <div class="note-head">
      <component :is="card ? 'span' : 'label'" class="note-label">{{ label }}</component>
      <div class="note-actions">
        <el-button
          size="small"
          link
          :loading="aiLoading"
          :disabled="disabled"
          :data-testid="`${testidPrefix}-ai`"
          @click="emit('ai')"
        >🤖 AI 辅助</el-button>
        <el-button
          v-if="showReview"
          size="small"
          link
          :data-testid="`${testidPrefix}-review`"
          @click="emit('review')"
        >💬 复核</el-button>
      </div>
    </div>
    <p v-if="hint" class="src-hint">{{ hint }}</p>
    <el-input
      :model-value="modelValue"
      type="textarea"
      :autosize="{ minRows, maxRows }"
      :disabled="disabled"
      :placeholder="placeholder"
      @update:model-value="(v: string) => emit('update:modelValue', v)"
      @change="emit('change')"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * 披露说明文本域（标题行右侧带「🤖 AI 辅助」「💬 复核」）—— 各循环共用
 *
 * 平台铁律：**多 section 底稿每个文本区都要 AI 辅助**，且 AI 按钮必须真调
 * `review-dialog/ai-generate`（配 `useDisclosureNoteAi`），不能 `emit` 一个
 * 宿主未处理的事件 —— 后者按钮可见可点、零网络请求，`get_diagnostics` 与
 * vitest 全绿，只有浏览器实测才暴露（H8/H9 四个 Tab 曾如此）。
 *
 * 用法::
 *
 *     const ai = useDisclosureNoteAi({ … })
 *     <WpNoteTextArea
 *       v-model="noteImpairment"
 *       label="减值测试披露说明"
 *       testid-prefix="h8-listed-impairment"
 *       :disabled="isReadonly"
 *       :ai-loading="ai.aiLoadingSection.value === 'impairment'"
 *       @change="persist"
 *       @ai="ai.runAi('impairment')"
 *       @review="ai.openReview('impairment')"
 *     />
 *
 * spec: .kiro/specs/h-cycle-legacy-cleanup-and-platform-hygiene/ R2 / R3
 */
withDefaults(
  defineProps<{
    modelValue: string
    label: string
    /** 源模板红字/编制口径提示（琥珀色左边线块） */
    hint?: string
    placeholder?: string
    disabled?: boolean
    minRows?: number
    maxRows?: number
    aiLoading?: boolean
    showReview?: boolean
    /** `el-card` 语境下用 span 而非 label（避免 label 语义嵌套） */
    card?: boolean
    testidPrefix?: string
  }>(),
  {
    hint: '',
    placeholder: '',
    disabled: false,
    minRows: 3,
    maxRows: 10,
    aiLoading: false,
    showReview: true,
    card: false,
    testidPrefix: 'wp-note',
  },
)

const emit = defineEmits<{
  (e: 'update:modelValue', v: string): void
  (e: 'change'): void
  (e: 'ai'): void
  (e: 'review'): void
}>()
</script>

<style scoped>
.wp-note-textarea { margin: 8px 0 14px; }
.note-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px; margin-bottom: 4px;
}
.note-label { font-size: 12px; color: #606266; font-weight: 500; }
.is-card .note-label { font-size: 14px; font-weight: 600; color: #303133; }
.note-actions { display: flex; align-items: center; gap: 4px; }
.src-hint {
  background: #fffbeb; border-left: 3px solid #f59e0b; padding: 6px 10px;
  border-radius: 0 4px 4px 0; margin: 0 0 6px; font-size: 12px; color: #92400e;
}
</style>
