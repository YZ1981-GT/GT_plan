<script setup lang="ts">
/** G4A — 债权投资实质性程序表（GtAProgramConsole 中控台，对齐 D4A） */
import CycleProgramConsoleTab from '../../shared/CycleProgramConsoleTab.vue'
import { G_CYCLE_PROCEDURE_SHEETS } from '../../composables/cycleProcedureSheets'

const cfg = G_CYCLE_PROCEDURE_SHEETS.G4A

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
    root-class="g4-tab-procedure"
  />
</template>
