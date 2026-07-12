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
        :ai-section="aiSection"
        :existing-content="fields.auditNote.value"
        :related-context="aiContext"
        :ai-title="aiTitle"
        @ai-filled="(t: string) => { fields.auditNote.value = t }"
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
        <label
          v-else
          class="field"
          :class="{ indent: f.indent, 'full-width': f.fullWidth }"
        >
          <span>{{ f.label }}</span>
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
        </label>
      </template>
    </div>
    <template v-if="showAuditNote">
      <h4>{{ auditNoteLabel }}</h4>
      <el-input v-model="fields.auditNote.value" type="textarea" :rows="3" :disabled="isReadonly" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, toRef } from 'vue'
import { useF2StocktakeFields } from '../../composables/useF2StocktakeSheet'
import type { ChecklistResponse } from '../../composables/useF2StocktakeFormData'
import type { F2StAiSection } from '../../composables/useF2StocktakeAiGenerate'
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

const aiContext = computed(() => {
  const filled = Object.fromEntries(
    Object.entries(fields.fields.value).filter(([, v]) => v),
  )
  return { sheet: props.sheetCode, fieldCount: Object.keys(filled).length, ...filled }
})
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
.field.indent span { padding-left: 12px; color: #606266; }
h4 { margin: 12px 0 6px; font-size: var(--wp-font-size, 13px); }
</style>
