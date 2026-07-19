<template>
  <div class="g10-audit-text-cards">
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
import { useG10AiGenerate, type G10AiSection } from '../composables/useG10AiGenerate'

const props = withDefaults(defineProps<{
  wpId?: string
  isReadonly?: boolean
  note?: string
  conclusion?: string
  showNote?: boolean
  showConclusion?: boolean
  noteTitle?: string
  conclusionTitle?: string
  noteHint?: string
  conclusionHint?: string
  notePlaceholder?: string
  conclusionPlaceholder?: string
  noteAiSection?: G10AiSection | ''
  conclusionAiSection?: G10AiSection | ''
  relatedContext?: Record<string, unknown>
  noteMinRows?: number
  conclusionMinRows?: number
}>(), {
  wpId: '',
  isReadonly: false,
  note: '',
  conclusion: '',
  showNote: true,
  showConclusion: true,
  noteTitle: '审计说明',
  conclusionTitle: '审计结论',
  noteHint: '',
  conclusionHint: '按 A/B/C 口径表述程序结果与总体结论。',
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
}>()

const wpIdRef = computed(() => props.wpId ?? '')
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useG10AiGenerate(wpIdRef)

async function runAi(kind: 'note' | 'conclusion') {
  const section = kind === 'note' ? props.noteAiSection : props.conclusionAiSection
  if (!section) return
  const existing = kind === 'note' ? (props.note ?? '') : (props.conclusion ?? '')
  const title = kind === 'note' ? 'AI 审计说明' : 'AI 审计结论'
  const text = await generateAndConfirm(section, existing, props.relatedContext ?? {}, title)
  if (!text) return
  if (kind === 'note') emit('update:note', text)
  else emit('update:conclusion', text)
}
</script>

<style scoped>
.g10-audit-text-cards { display: flex; flex-direction: column; gap: 0; }
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
.card-title { font-size: 14px; font-weight: 600; color: #1f2a37; }
.card-hint { margin-top: 2px; font-size: 12px; color: #86909c; line-height: 1.4; }
</style>
