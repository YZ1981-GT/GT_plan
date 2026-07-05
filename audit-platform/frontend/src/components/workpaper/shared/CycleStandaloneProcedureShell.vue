<script setup lang="ts">
/**
 * 无科目主入口的循环 *A 程序表壳 — 双模式 + CycleTabProcedure（对齐 D4A）
 * 由 GtCycleAProgramRouter 在 sheet 命中 cycleProcedureSheets 时挂载。
 */
import { computed, defineAsyncComponent, toRef } from 'vue'
import CycleTabProcedure from './CycleTabProcedure.vue'
import { useCycleHtmlOoDualMode } from '../composables/useCycleHtmlOoDualMode'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('../GtOnlyOfficeSheet.vue'))

const props = defineProps<{
  wpId: string
  projectId?: string
  sheetName: string
  sheetCode: string
  htmlData?: any
  readonly?: boolean
}>()

const dualMode = useCycleHtmlOoDualMode({
  wpId: toRef(props, 'wpId'),
  storagePrefix: `cycle-proc-${props.sheetCode}:`,
})

const projectId = computed(() => props.projectId || '')
</script>

<template>
  <div class="cycle-standalone-procedure">
    <div class="cycle-standalone-procedure__toolbar">
      <el-segmented
        v-model="dualMode.currentMode.value"
        :options="dualMode.modeOptions"
        size="small"
        @change="dualMode.onModeChange"
      />
      <el-tag v-if="!dualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
    </div>

    <GtOnlyOfficeSheet
      v-if="dualMode.currentMode.value === 'onlyoffice'"
      :wp-id="wpId"
      :project-id="projectId"
      :sheet-name="sheetName"
      :readonly="readonly"
      style="height: calc(100vh - 180px)"
    />

    <CycleTabProcedure
      v-else
      :sheet-code="sheetCode"
      :html-data="htmlData"
      :wp-id="wpId"
      :project-id="projectId"
      :readonly="readonly"
    />
  </div>
</template>

<style scoped>
.cycle-standalone-procedure {
  padding: 12px;
  font-size: 13px;
}

.cycle-standalone-procedure__toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
</style>
