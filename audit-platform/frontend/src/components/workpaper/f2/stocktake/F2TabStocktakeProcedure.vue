<script setup lang="ts">
/**
 * F2-21A — 存货监盘程序表（灵魂表：程序控制台 + 裁剪 + 常规★/备选分类）
 */
import CycleProgramConsoleTab from '../../shared/CycleProgramConsoleTab.vue'
import { FH_CYCLE_PROCEDURE_SHEETS } from '../../composables/cycleProcedureSheets'
import GtIndexChip from '../../GtIndexChip.vue'

const cfg = FH_CYCLE_PROCEDURE_SHEETS['F2-21A']

defineProps<{
  htmlData?: any
  wpId: string
  projectId: string
  isReadonly: boolean
}>()
</script>

<template>
  <CycleProgramConsoleTab
    :html-data="htmlData"
    :wp-id="wpId"
    :project-id="projectId"
    :is-readonly="isReadonly"
    :sheet-code="cfg.sheetCode"
    :sheet-label="cfg.sheetLabel"
    :hide-categories="false"
    root-class="f2-tab-stocktake-procedure"
  >
    <template #toolbar>
      <div class="f2-tab-stocktake-procedure__hint">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="根据被审计单位实际情况和风险评估情况裁剪、修改或增加审计程序"
        />
        <div class="f2-tab-stocktake-procedure__chips">
          <GtIndexChip value="wp:F2-21" :context-project-id="projectId" label="F2-21 问卷" />
          <GtIndexChip value="wp:F2-22" :context-project-id="projectId" label="F2-22 计划" />
          <GtIndexChip value="wp:F2-23" :context-project-id="projectId" label="F2-23 小结" />
          <GtIndexChip value="wp:F2-24" :context-project-id="projectId" label="F2-24 核对" />
          <GtIndexChip value="wp:F2-25" :context-project-id="projectId" label="F2-25 抽盘" />
          <GtIndexChip value="wp:F2-26" :context-project-id="projectId" label="F2-26 倒轧" />
        </div>
      </div>
    </template>
  </CycleProgramConsoleTab>
</template>

<style scoped>
.f2-tab-stocktake-procedure__hint {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.f2-tab-stocktake-procedure__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>
