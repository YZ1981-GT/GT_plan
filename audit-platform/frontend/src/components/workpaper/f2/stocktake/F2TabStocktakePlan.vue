<template>
  <F2StocktakeSectionForm
    title="监盘计划 F2-22"
    sheet-code="F2-22"
    fields-key="F2-22-fields"
    note-key="F2-22-note"
    :field-defs="F2_22_FIELDS"
    :wp-id="wpId"
    :project-id="projectId"
    :all-responses="allResponses"
    :is-readonly="isReadonly"
    ai-section="stocktake-plan"
    ai-title="AI 生成 · 监盘计划"
    audit-note-label="监盘计划结论"
  />
</template>

<script setup lang="ts">
import F2StocktakeSectionForm from './F2StocktakeSectionForm.vue'
import { F2_22_FIELDS } from './f2StocktakeConfigs'
import type { ChecklistResponse } from '../../composables/useF2StocktakeFormData'

defineProps<{
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()
</script>
