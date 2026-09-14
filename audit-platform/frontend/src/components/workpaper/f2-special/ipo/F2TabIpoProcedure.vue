<template>
<div class="f2-ipo-procedure">
  <!-- 编制提示 -->
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 本程序表针对 IPO 存货专项审计，逐条执行采购价格、产能能耗、关联方定价、供应商访谈等程序。</p>
      <p>2. 关注原材料采购价格异常波动（F2-61）、产能与能耗匹配性（F2-63）及关联方采购公允性（F2-65）。</p>
      <p>3. 供应商访谈（F2-71/F2-72）应核实交易真实性，关注是否存在体外循环或利益输送。</p>
      <p>4. 程序执行结论应回填底稿目录（F2-1）并向报表层（A1-13）传递。</p>
    </div>
  </details>

  <!-- 审计目标 -->
  <el-alert type="info" :closable="false" show-icon class="objective-alert">
    <template #title>审计目标：针对 IPO 审计要求，验证存货采购价格、产能能耗及关联方交易的真实性、公允性与完整性。</template>
  </el-alert>

  <!-- 交叉索引 -->
  <div class="procedure-header">
    <div class="index-chips">
      <GtIndexChip value="wp:F2-61" :context-project-id="projectId" />
      <GtIndexChip value="wp:F2-62" :context-project-id="projectId" />
      <GtIndexChip value="wp:F2-63" :context-project-id="projectId" />
      <GtIndexChip value="wp:F2-64" :context-project-id="projectId" />
      <GtIndexChip value="wp:F2-65" :context-project-id="projectId" />
      <GtIndexChip value="wp:F2-68" :context-project-id="projectId" />
      <GtIndexChip value="wp:F2-70" :context-project-id="projectId" />
      <GtIndexChip value="wp:F2-72" :context-project-id="projectId" />
      <GtIndexChip value="wp:F2-1" :context-project-id="projectId" />
      <GtIndexChip value="wp:A1-13" :context-project-id="projectId" />
    </div>
  </div>

  <!-- 程序表主体：复用 GtAProgramConsole -->
  <div class="program-console-wrapper">
    <GtAProgramConsole
      v-if="programData"
      :wp-id="wpId"
      sheet-name="F2-61A"
      :schema="programData.schema || { columns: [], rows: [] }"
      :html-data="programData"
      :readonly="isReadonly"
      cycle-sheet-mode
    />
    <div v-else-if="isLoading" class="loading-placeholder">
      <el-skeleton :rows="6" animated />
    </div>
    <el-empty v-else description="程序表数据加载失败" />
  </div>
</div>
</template>

<script setup lang="ts">
/**
 * F2TabIpoProcedure.vue — F2-61A IPO存货程序表
 *
 * 复用 GtAProgramConsole，加载逻辑对齐 F2-55A：
 * useCycleProcedureConsole 携带 sheet_name 拉取 render-config，
 * 并按 F2-61A 编码匹配目标 sheet（避免误取整本工作簿的第一个 sheet）。
 * 交叉索引：F2-61~F2-72关键sheet + F2-1 + A1-13
 */
import { toRef } from 'vue'

import GtIndexChip from '../../GtIndexChip.vue'
import GtAProgramConsole from '../../GtAProgramConsole.vue'
import { useCycleProcedureConsole } from '../../composables/useCycleProcedureConsole'

const props = defineProps<{
  htmlData?: any
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const { isLoading, programData } = useCycleProcedureConsole({
  wpId: toRef(props, 'wpId'),
  htmlData: toRef(props, 'htmlData'),
  sheetLabel: '程序表F2-61A',
  sheetCode: 'F2-61A',
})
</script>

<style scoped>
.f2-ipo-procedure {
  padding: 16px;
}

.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

.procedure-header {
  margin-bottom: 12px;
}

.index-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
}

.program-console-wrapper {
  min-height: 300px;
}

.loading-placeholder {
  padding: 24px;
}
</style>
