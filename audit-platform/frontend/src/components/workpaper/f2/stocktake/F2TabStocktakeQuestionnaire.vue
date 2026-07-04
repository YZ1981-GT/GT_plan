<template>
  <F2StocktakeSectionForm
    title="盘点计划问卷 F2-21"
    sheet-code="F2-21"
    fields-key="F2-21-fields"
    note-key="F2-21-note"
    :field-defs="F2_21_FIELDS"
    :wp-id="wpId"
    :project-id="projectId"
    :all-responses="allResponses"
    :is-readonly="isReadonly"
    ai-section="stocktake-questionnaire"
    ai-title="AI 生成 · 盘点问卷结论"
    audit-note-label="问卷结论"
  />
</template>

<script setup lang="ts">
import F2StocktakeSectionForm from './F2StocktakeSectionForm.vue'
import { F2_21_FIELDS } from './f2StocktakeConfigs'
import type { ChecklistResponse } from '../../composables/useF2StocktakeFormData'

defineProps<{
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()
</script>
