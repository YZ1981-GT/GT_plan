<script setup lang="ts">
/** D5A — 应收款项融资审计程序表（GtAProgramConsole 中控台） */
import CycleProgramConsoleTab from '../shared/CycleProgramConsoleTab.vue'
import { D_CYCLE_PROCEDURE_SHEETS } from '../composables/cycleProcedureSheets'

const cfg = D_CYCLE_PROCEDURE_SHEETS.D5A

defineProps<{
  htmlData?: any
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
    root-class="d5-tab-procedure"
  />
</template>
