<script setup lang="ts">
/** G11A — 投资收益实质性程序表（对齐 D4A） */
import CycleProgramConsoleTab from '../../shared/CycleProgramConsoleTab.vue'
import { G_CYCLE_PROCEDURE_SHEETS } from '../../composables/cycleProcedureSheets'

const cfg = G_CYCLE_PROCEDURE_SHEETS.G11A

defineProps<{
  htmlData?: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly?: boolean
  readonly?: boolean
}>()
</script>

<template>
  <CycleProgramConsoleTab
    :html-data="htmlData"
    :wp-id="wpId"
    :project-id="projectId"
    :is-readonly="isReadonly"
    :readonly="readonly"
    :sheet-code="cfg.sheetCode"
    :sheet-label="cfg.sheetLabel"
    :review-section-id="cfg.reviewSectionId"
    root-class="g11-tab-procedure"
  />
</template>
