<script setup lang="ts">
/** D6A — 合同资产实质性程序表（GtAProgramConsole 中控台） */
import CycleProgramConsoleTab from '../shared/CycleProgramConsoleTab.vue'
import { D_CYCLE_PROCEDURE_SHEETS } from '../composables/cycleProcedureSheets'

const cfg = D_CYCLE_PROCEDURE_SHEETS.D6A

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
    root-class="d6-tab-procedure"
  />
</template>
