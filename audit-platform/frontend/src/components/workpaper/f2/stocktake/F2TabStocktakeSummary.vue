<template>
  <F2StocktakeSectionForm
    title="监盘小结 F2-23"
    sheet-code="F2-23"
    fields-key="F2-23-fields"
    note-key="F2-23-note"
    :field-defs="F2_23_FIELDS"
    :wp-id="wpId"
    :project-id="projectId"
    :all-responses="allResponses"
    :is-readonly="isReadonly"
    ai-section="stocktake-summary"
    ai-title="AI 生成 · 监盘小结"
    audit-note-label="监盘小结结论"
  />
</template>

<script setup lang="ts">
import F2StocktakeSectionForm from './F2StocktakeSectionForm.vue'
import { F2_23_FIELDS } from './f2StocktakeConfigs'
import type { ChecklistResponse } from '../../composables/useF2StocktakeFormData'

defineProps<{
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()
</script>
