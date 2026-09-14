<template>
  <div class="f2-stocktake-section" :class="{ compact }">
    <h3 v-if="title" class="title">{{ title }}</h3>
    <div v-if="wpId && showToolbar" class="toolbar">
      <F2SheetToolbar
        :wp-id="wpId"
        :project-id="projectId"
        api-prefix="f2-st"
        :sheet="sheetCode"
        :disabled="isReadonly"
        :show-import-export="showImportExport"
        :review-section="`${sheetCode}-conclusion`"
        :ai-section="perFieldAi ? undefined : aiSection"
        :existing-content="fields.auditNote.value"
        :related-context="aiContext"
        :ai-title="aiTitle"
        @ai-filled="onBulkAiFilled"
      />
    </div>
    <F2StocktakeSheetAttachments
      v-if="wpId && showAttachments"
      :project-id="projectId"
      :wp-id="wpId"
      :sheet-code="sheetCode"
    />
    <div class="fields" :class="{ stack: layout === 'stack' }">
      <template v-for="f in fieldDefs" :key="f.id">
        <h4 v-if="f.isSection" class="section-head">{{ f.label }}</h4>
        <div
          v-else
          class="field"
          :class="{ indent: f.indent, 'full-width': f.fullWidth }"
        >
          <div class="field-label-row">
            <span>{{ f.label }}</span>
            <el-button
              v-if="perFieldAi && wpId"
              text
              type="primary"
              size="small"
              :disabled="isReadonly || !aiAvailable"
              :loading="aiLoadingId === f.id"
              :aria-label="`AI 起草${f.label}`"
              @click="aiFillField(f.id, f.label)"
            >
              🤖 AI
            </el-button>
          </div>
          <el-input
            v-if="f.multiline"
            :model-value="fields.fields.value[f.id] || ''"
            type="textarea"
            :rows="3"
            size="small"
            :disabled="isReadonly"
            @update:model-value="(v: string) => fields.updateField(f.id, v)"
          />
          <el-input
            v-else
            :model-value="fields.fields.value[f.id] || ''"
            size="small"
            :disabled="isReadonly"
            @update:model-value="(v: string) => fields.updateField(f.id, v)"
          />
        </div>
      </template>
    </div>
    <template v-if="showAuditNote">
      <div class="note-head">
        <h4>{{ auditNoteLabel }}</h4>
        <el-button
          v-if="perFieldAi && wpId"
          text
          type="primary"
          size="small"
          :disabled="isReadonly || !aiAvailable"
          :loading="aiLoadingId === '__note__'"
          :aria-label="`AI 起草${auditNoteLabel || '结论'}`"
          @click="aiFillNote"
        >
          🤖 AI
        </el-button>
      </div>
      <el-input v-model="fields.auditNote.value" type="textarea" :rows="3" :disabled="isReadonly" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, toRef } from 'vue'
import { ElMessage } from 'element-plus'
import { useF2StocktakeFields } from '../../composables/useF2StocktakeSheet'
import { useF2StocktakeAiGenerate, type F2StAiSection } from '../../composables/useF2StocktakeAiGenerate'
import type { ChecklistResponse } from '../../composables/useF2StocktakeFormData'
import type { StocktakeSectionField } from './f2StocktakeConfigs'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'
import F2StocktakeSheetAttachments from './F2StocktakeSheetAttachments.vue'

const props = withDefaults(defineProps<{
  title?: string
  sheetCode: string
  fieldsKey: string
  noteKey: string
  fieldDefs: StocktakeSectionField[]
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  aiSection?: F2StAiSection
  aiTitle?: string
  /** 每个文本框独立 AI（关闭顶部整页 AI） */
  perFieldAi?: boolean
  showToolbar?: boolean
  showAttachments?: boolean
  showAuditNote?: boolean
  showImportExport?: boolean
  auditNoteLabel?: string
  layout?: 'grid' | 'stack'
  compact?: boolean
}>(), {
  showToolbar: true,
  showAttachments: true,
  showAuditNote: true,
  showImportExport: false,
  perFieldAi: false,
  auditNoteLabel: '审计说明',
  layout: 'stack',
  compact: false,
})

const fieldIds = props.fieldDefs.filter((f) => !f.isSection).map((f) => f.id)

const fields = useF2StocktakeFields({
  fieldsKey: props.fieldsKey,
  noteKey: props.noteKey,
  fieldIds,
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const wpIdRef = toRef(() => props.wpId || '')
const projectIdRef = toRef(() => props.projectId || '')
const { aiAvailable, generateAndConfirm } = useF2StocktakeAiGenerate({
  wpId: wpIdRef as any,
  projectId: projectIdRef as any,
})
const aiLoadingId = ref('')

const aiContext = computed(() => {
  const filled = Object.fromEntries(
    Object.entries(fields.fields.value).filter(([, v]) => v),
  )
  return { sheet: props.sheetCode, fieldCount: Object.keys(filled).length, ...filled }
})

function fieldAiSection(): F2StAiSection {
  if (props.sheetCode === 'F2-22' || props.aiSection === 'stocktake-plan') {
    return 'stocktake-plan-field'
  }
  if (props.sheetCode === 'F2-23' || props.aiSection === 'stocktake-summary') {
    return 'stocktake-summary-field'
  }
  if (props.sheetCode === 'F2-26' || props.aiSection === 'stocktake-rollforward') {
    return 'stocktake-rollforward-field'
  }
  return 'stocktake-plan-field'
}

async function aiFillField(fieldId: string, fieldLabel: string): Promise<void> {
  if (props.isReadonly || !props.wpId) return
  aiLoadingId.value = fieldId
  try {
    const text = await generateAndConfirm(
      fieldAiSection(),
      fields.fields.value[fieldId] || '',
      {
        ...aiContext.value,
        fieldId,
        fieldLabel,
      },
      `AI · ${fieldLabel}`,
    )
    if (text) {
      fields.updateField(fieldId, text)
      ElMessage.success('已填入，可继续编辑')
    }
  } finally {
    aiLoadingId.value = ''
  }
}

async function aiFillNote(): Promise<void> {
  if (props.isReadonly || !props.wpId) return
  aiLoadingId.value = '__note__'
  try {
    const text = await generateAndConfirm(
      fieldAiSection(),
      fields.auditNote.value || '',
      {
        ...aiContext.value,
        fieldId: 'planConclusion',
        fieldLabel: props.auditNoteLabel || '结论',
      },
      `AI · ${props.auditNoteLabel || '结论'}`,
    )
    if (text) {
      fields.auditNote.value = text
      ElMessage.success('已填入，可继续编辑')
    }
  } finally {
    aiLoadingId.value = ''
  }
}

/** 非 perFieldAi 时保留原整页填入（写入结论框） */
function onBulkAiFilled(text: string): void {
  fields.auditNote.value = text
  ElMessage.success('已填入结论框，可继续二次编辑')
}
</script>

<style scoped>
.f2-stocktake-section { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f2-stocktake-section.compact { padding: 0 0 12px; }
.title { margin: 0 0 8px; }
.toolbar { margin-bottom: 8px; }
.fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 16px;
  margin-bottom: 12px;
}
.fields.stack { grid-template-columns: 1fr; }
.section-head { grid-column: 1 / -1; margin: 12px 0 4px; font-size: var(--wp-font-size, 13px); color: #303133; font-weight: 600; }
.field { display: flex; flex-direction: column; gap: 4px; font-size: 12px; }
.field.full-width { grid-column: 1 / -1; }
.field.indent .field-label-row span { padding-left: 12px; color: #606266; }
.field-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.note-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 12px 0 6px;
}
.note-head h4 { margin: 0; font-size: var(--wp-font-size, 13px); }
h4 { margin: 12px 0 6px; font-size: var(--wp-font-size, 13px); }
</style>
