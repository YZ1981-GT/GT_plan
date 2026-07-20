<template>
  <div class="g8-audit-text-cards">
    <el-card v-if="showNote" shadow="never" class="audit-text-card">
      <template #header>
        <div class="card-header">
          <div>
            <div class="card-title">{{ noteTitle }}</div>
            <div v-if="noteHint" class="card-hint">{{ noteHint }}</div>
          </div>
          <el-button
            v-if="noteAiSection"
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="runAi('note')"
          >🤖 AI填写说明</el-button>
        </div>
      </template>
      <el-input
        :model-value="note"
        type="textarea"
        :autosize="{ minRows: noteMinRows, maxRows: 14 }"
        :disabled="isReadonly"
        :placeholder="notePlaceholder"
        @update:model-value="(v: string) => emit('update:note', v)"
      />
    </el-card>

    <el-card v-if="showConclusion" shadow="never" class="audit-text-card">
      <template #header>
        <div class="card-header">
          <div>
            <div class="card-title">{{ conclusionTitle }}</div>
            <div v-if="conclusionHint" class="card-hint">{{ conclusionHint }}</div>
          </div>
          <div class="header-actions">
            <el-select
              v-if="showConclusionOptions"
              :model-value="resolvedOption"
              size="small"
              class="conclusion-select"
              clearable
              placeholder="A/B/C"
              :disabled="isReadonly"
              data-testid="g8-conclusion-option"
              @update:model-value="onOptionChange"
            >
              <el-option
                v-for="o in G8_CONCLUSION_OPTIONS"
                :key="o.value"
                :label="o.label"
                :value="o.value"
              />
            </el-select>
            <el-button
              v-if="conclusionAiSection"
              size="small"
              type="primary"
              plain
              :disabled="isReadonly || !aiAvailable"
              :loading="aiLoading"
              @click="runAi('conclusion')"
            >🤖 AI生成结论</el-button>
          </div>
        </div>
      </template>
      <el-input
        :model-value="conclusion"
        type="textarea"
        :autosize="{ minRows: conclusionMinRows, maxRows: 10 }"
        :disabled="isReadonly"
        :placeholder="conclusionPlaceholder"
        @update:model-value="(v: string) => emit('update:conclusion', v)"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useG8AiGenerate, type G8AiSection } from '../composables/useG8AiGenerate'
import {
  G8_CONCLUSION_OPTIONS,
  G8_CONCLUSION_TEMPLATES,
  applyG8ConclusionTemplate,
  inferG8ConclusionOption,
  type G8ConclusionOption,
} from '../composables/g8Conclusion'

const props = withDefaults(defineProps<{
  wpId?: string
  isReadonly?: boolean
  note?: string
  conclusion?: string
  conclusionOption?: string
  showNote?: boolean
  showConclusion?: boolean
  showConclusionOptions?: boolean
  noteTitle?: string
  conclusionTitle?: string
  noteHint?: string
  conclusionHint?: string
  notePlaceholder?: string
  conclusionPlaceholder?: string
  noteAiSection?: G8AiSection | ''
  conclusionAiSection?: G8AiSection | ''
  relatedContext?: Record<string, unknown>
  noteMinRows?: number
  conclusionMinRows?: number
}>(), {
  wpId: '',
  isReadonly: false,
  note: '',
  conclusion: '',
  conclusionOption: '',
  showNote: true,
  showConclusion: true,
  showConclusionOptions: true,
  noteTitle: '审计说明',
  conclusionTitle: '审计结论',
  noteHint: '',
  conclusionHint: '可先选 A/B/C 口径，再按需补充说明。',
  notePlaceholder: '填写审计说明…',
  conclusionPlaceholder: 'A、未见异常。B、除上述重大不符事项应予调整外，其余未见异常。C、由于存在重大未调整事项或审计范围受限，不可确认。',
  noteAiSection: '',
  conclusionAiSection: '',
  relatedContext: () => ({}),
  noteMinRows: 5,
  conclusionMinRows: 3,
})

const emit = defineEmits<{
  'update:note': [string]
  'update:conclusion': [string]
  'update:conclusionOption': [string]
}>()

const wpIdRef = computed(() => props.wpId ?? '')
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useG8AiGenerate(wpIdRef)

const resolvedOption = computed<G8ConclusionOption>(() => {
  const bound = (props.conclusionOption || '') as G8ConclusionOption
  if (bound === 'A' || bound === 'B' || bound === 'C') return bound
  return inferG8ConclusionOption(props.conclusion ?? '')
})

async function onOptionChange(v: string | null) {
  const option = (v || '') as G8ConclusionOption
  emit('update:conclusionOption', option)
  if (!option) return
  const template = G8_CONCLUSION_TEMPLATES[option]
  const current = (props.conclusion ?? '').trim()
  if (current && current !== template) {
    try {
      await ElMessageBox.confirm(
        '当前结论正文与所选模板不同，是否用模板正文覆盖？',
        '替换审计结论',
        { confirmButtonText: '覆盖', cancelButtonText: '仅切换选项', type: 'warning' },
      )
      emit('update:conclusion', template)
    } catch {
      // 保留正文，只切换选项
    }
  } else {
    emit('update:conclusion', applyG8ConclusionTemplate(option, props.conclusion ?? ''))
  }
}

async function runAi(kind: 'note' | 'conclusion') {
  const section = kind === 'note' ? props.noteAiSection : props.conclusionAiSection
  if (!section) return
  const existing = kind === 'note' ? (props.note ?? '') : (props.conclusion ?? '')
  const title = kind === 'note' ? 'AI 审计说明' : 'AI 审计结论'
  const ctx = {
    ...(props.relatedContext ?? {}),
    结论口径: resolvedOption.value || undefined,
  }
  const text = await generateAndConfirm(section, existing, ctx, title)
  if (!text) return
  if (kind === 'note') emit('update:note', text)
  else {
    emit('update:conclusion', text)
    const inferred = inferG8ConclusionOption(text)
    if (inferred) emit('update:conclusionOption', inferred)
  }
}
</script>

<style scoped>
.g8-audit-text-cards { display: flex; flex-direction: column; gap: 0; }
.audit-text-card {
  margin-top: 14px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
}
.audit-text-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafbfc;
  border-bottom: 1px solid #ebeef5;
}
.audit-text-card :deep(.el-card__body) { padding: 12px 16px 16px; }
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}
.header-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.conclusion-select { width: 220px; }
.card-title { font-size: 14px; font-weight: 600; color: #1f2a37; }
.card-hint { margin-top: 2px; font-size: 12px; color: #86909c; line-height: 1.4; }
</style>
