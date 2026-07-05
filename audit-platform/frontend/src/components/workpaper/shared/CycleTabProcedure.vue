<script setup lang="ts">
/**
 * 循环底稿 *A 程序表通用壳 — 对齐 D4A（CycleProgramConsoleTab）
 * 各科目主入口传入 sheetCode（如 G3A、F4A）即可，无需重复建 TabProcedure 文件。
 */
import { computed } from 'vue'
import CycleProgramConsoleTab from './CycleProgramConsoleTab.vue'
import { getCycleProcedureSheetConfig } from '../composables/cycleProcedureSheets'

const props = defineProps<{
  sheetCode: string
  wpId: string
  projectId: string
  htmlData?: any
  isReadonly?: boolean
  readonly?: boolean
}>()

const cfg = computed(() => getCycleProcedureSheetConfig(props.sheetCode))
const rootClass = computed(() => `${props.sheetCode.toLowerCase()}-tab-procedure`)
</script>

<template>
  <CycleProgramConsoleTab
    v-if="cfg"
    :html-data="htmlData"
    :wp-id="wpId"
    :project-id="projectId"
    :is-readonly="isReadonly"
    :readonly="readonly"
    :sheet-code="cfg.sheetCode"
    :sheet-label="cfg.sheetLabel"
    :review-section-id="cfg.reviewSectionId"
    :root-class="rootClass"
  />
  <el-empty v-else :description="`未注册程序表 ${sheetCode}`" />
</template>
