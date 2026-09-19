<script setup lang="ts">
/**
 * a-program-console 路由：循环 *A 程序表走 CycleStandaloneProcedureShell，其余走 GtAProgramConsole
 */
import { computed, defineAsyncComponent } from 'vue'
import {
  extractCycleProcedureSheetCode,
  getCycleProcedureSheetConfig,
} from './composables/cycleProcedureSheets'

const GtAProgramConsole = defineAsyncComponent(() => import('./GtAProgramConsole.vue'))
const CycleStandaloneProcedureShell = defineAsyncComponent(
  () => import('./shared/CycleStandaloneProcedureShell.vue'),
)

const props = defineProps<{
  wpId: string
  projectId?: string
  sheetName: string
  schema?: Record<string, unknown>
  htmlData?: Record<string, unknown>
  readonly?: boolean
}>()

const sheetCode = computed(() => extractCycleProcedureSheetCode(props.sheetName))
const cycleCfg = computed(() => {
  const code = sheetCode.value
  return code ? getCycleProcedureSheetConfig(code) : undefined
})
</script>

<template>
  <CycleStandaloneProcedureShell
    v-if="cycleCfg && sheetCode"
    :wp-id="wpId"
    :project-id="projectId"
    :sheet-name="sheetName"
    :sheet-code="sheetCode"
    :html-data="htmlData"
    :readonly="readonly"
  />
  <GtAProgramConsole
    v-else
    :wp-id="wpId"
    :sheet-name="sheetName"
    :schema="schema || { columns: [], rows: [] }"
    :html-data="htmlData || { programs: [], trim_decisions: [] }"
    :readonly="readonly"
  />
</template>
