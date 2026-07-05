<script setup lang="ts">
/** H10A — 资产处置损益实质性程序表（对齐 D4A） */
import CycleProgramConsoleTab from '../../shared/CycleProgramConsoleTab.vue'
import { FH_CYCLE_PROCEDURE_SHEETS } from '../../composables/cycleProcedureSheets'

const cfg = FH_CYCLE_PROCEDURE_SHEETS.H10A

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
    root-class="h10-tab-procedure"
  />
</template>
