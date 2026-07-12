<template>
  <div class="followup-memo-preview">
    <div class="followup-memo-preview__header">
      <h4 class="followup-memo-preview__title">备忘录预览</h4>
      <div class="followup-memo-preview__actions">
        <el-radio-group v-model="mode" size="small" :disabled="readonly">
          <el-radio-button value="auto">自动</el-radio-button>
          <el-radio-button value="manual">手动</el-radio-button>
        </el-radio-group>
        <el-button
          v-if="mode === 'auto'"
          size="small"
          type="warning"
          :disabled="readonly"
          @click="handleRegenerate"
        >
          重新生成
        </el-button>
        <el-button size="small" @click="handleCopy">
          复制
        </el-button>
      </div>
    </div>

    <div class="followup-memo-preview__content">
      <template v-if="mode === 'auto'">
        <!-- Auto mode: rendered text with missing fields highlighted -->
        <div class="followup-memo-preview__text" v-html="highlightedText" />
        <div v-if="missingFields.length > 0" class="followup-memo-preview__missing">
          <el-alert
            :title="`${missingFields.length} 个字段待填写`"
            type="warning"
            :closable="false"
            show-icon
          >
            <template #default>
              <span>{{ missingFields.join('、') }}</span>
            </template>
          </el-alert>
        </div>
      </template>
      <template v-else>
        <!-- Manual mode: editable textarea -->
        <el-input
          type="textarea"
          :rows="12"
          :model-value="row?.memo_text ?? ''"
          :disabled="readonly"
          placeholder="手动编写备忘录内容"
          @update:model-value="handleManualEdit"
        />
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { FollowupRow } from './followupTypes'
import { useMemoCompose } from './composables/useMemoCompose'

const props = defineProps<{
  row: FollowupRow | null
  readonly: boolean
}>()

const emit = defineEmits<{
  (e: 'update', field: string, value: any): void
  (e: 'regenerate'): void
}>()

const { compose } = useMemoCompose()

// Mode: auto (template-driven) / manual (free text)
const mode = ref<'auto' | 'manual'>('auto')

// Watch row.memo_overridden to sync mode
watch(
  () => props.row?.memo_overridden,
  (overridden) => {
    mode.value = overridden ? 'manual' : 'auto'
  },
  { immediate: true }
)

// Watch mode change to update memo_overridden
watch(mode, (newMode) => {
  if (!props.row) return
  if (newMode === 'manual' && !props.row.memo_overridden) {
    emit('update', 'memo_overridden', true)
  } else if (newMode === 'auto' && props.row.memo_overridden) {
    emit('update', 'memo_overridden', false)
  }
})

// Composed memo result
const composedResult = computed(() => {
  if (!props.row) return { text: '', missingFields: [] }
  return compose(props.row)
})

const missingFields = computed(() => composedResult.value.missingFields)

// Highlighted text: replace 〔field〕 with orange spans
const highlightedText = computed(() => {
  const text = composedResult.value.text
  return text
    .replace(/〔(\w+)〕/g, '<span class="followup-memo-preview__placeholder">〔$1〕</span>')
    .replace(/\n/g, '<br>')
})

function handleRegenerate() {
  emit('regenerate')
}

function handleManualEdit(value: string) {
  emit('update', 'memo_text', value)
}

function handleCopy() {
  const text = composedResult.value.text || props.row?.memo_text || ''
  navigator.clipboard.writeText(text)
}
</script>

<style scoped>
.followup-memo-preview {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 12px;
  background: #fff;
}

.followup-memo-preview__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}

.followup-memo-preview__title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.followup-memo-preview__actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.followup-memo-preview__text {
  line-height: 1.8;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  white-space: pre-wrap;
}

.followup-memo-preview__missing {
  margin-top: 12px;
}

:deep(.followup-memo-preview__placeholder) {
  color: #e6a23c;
  font-weight: 600;
  background: #fdf6ec;
  padding: 1px 4px;
  border-radius: 3px;
}
</style>
