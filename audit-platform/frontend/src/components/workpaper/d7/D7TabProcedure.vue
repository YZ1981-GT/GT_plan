<script setup lang="ts">
/** D7A — 合同负债审计程序表（GtAProgramConsole 中控台） */
import CycleProgramConsoleTab from '../shared/CycleProgramConsoleTab.vue'
import { D_CYCLE_PROCEDURE_SHEETS } from '../composables/cycleProcedureSheets'

const cfg = D_CYCLE_PROCEDURE_SHEETS.D7A

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
    root-class="d7-tab-procedure"
  />
</template>
