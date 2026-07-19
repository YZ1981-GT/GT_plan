<script setup lang="ts">
/** G5A — 长期应收款审计程序表（对齐 D4A / G2A） */
import { inject } from 'vue'
import CycleProgramConsoleTab from '../../shared/CycleProgramConsoleTab.vue'
import { G_CYCLE_PROCEDURE_SHEETS } from '../../composables/cycleProcedureSheets'

const cfg = G_CYCLE_PROCEDURE_SHEETS.G5A

defineProps<{
  htmlData?: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly?: boolean
  readonly?: boolean
}>()

const openG5Handbook = inject<(tab?: 'preparation' | 'usage') => void>('openG5Handbook', () => {})
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
    root-class="g5-tab-procedure"
  >
    <template #toolbar>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="g5a-handbook-tip"
        title="本表为程序控制台：勾选拟执行程序并填索引。不熟悉编制逻辑？请打开手册。"
      />
      <el-button type="primary" size="small" @click="openG5Handbook('preparation')">
        📖 编制手册
      </el-button>
      <el-button size="small" @click="openG5Handbook('usage')">
        使用手册
      </el-button>
    </template>
  </CycleProgramConsoleTab>
</template>

<style scoped>
.g5a-handbook-tip { flex: 1; min-width: 240px; }
</style>
