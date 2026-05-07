<!--
  WorkpaperSidePanel — 底稿/报表编辑器统一右栏面板 [R7-S3-05 Task 24]

  8 Tab 容器：AI / 附件 / 版本 / 批注 / 程序要求 / 依赖 / 一致性 / 智能提示
  所有编辑器（WorkpaperEditor/WorkpaperWorkbench/DisclosureEditor/AuditReportEditor/ReportConfigEditor）
  统一使用此组件作为右栏，禁止各自自建独立面板。

  用法：
    <WorkpaperSidePanel :project-id="projectId" :wp-id="wpId" :wp-code="wpCode" />
-->
<template>
  <div class="gt-wp-side-panel">
    <el-tabs v-model="activeTab" type="border-card" stretch class="gt-wp-side-tabs">
      <el-tab-pane label="AI" name="ai" lazy>
        <slot name="ai">
          <AiAssistantSidebar v-if="wpId" :project-id="projectId" :wp-id="wpId" />
          <div v-else class="gt-wp-side-placeholder">请先选择底稿</div>
        </slot>
      </el-tab-pane>
      <el-tab-pane label="附件" name="attachments" lazy>
        <slot name="attachments">
          <AttachmentDropZone v-if="wpId" :project-id="projectId" :wp-id="wpId" />
          <div v-else class="gt-wp-side-placeholder">请先选择底稿</div>
        </slot>
      </el-tab-pane>
      <el-tab-pane label="版本" name="versions" lazy>
        <slot name="versions">
          <div class="gt-wp-side-placeholder">版本历史（待接入）</div>
        </slot>
      </el-tab-pane>
      <el-tab-pane label="批注" name="annotations" lazy>
        <slot name="annotations">
          <div class="gt-wp-side-placeholder">批注列表（待接入）</div>
        </slot>
      </el-tab-pane>
      <el-tab-pane label="程序要求" name="requirements" lazy>
        <slot name="requirements">
          <ProgramRequirementsSidebar v-if="wpCode && wpId" :project-id="projectId" :wp-id="wpId" />
          <div v-else class="gt-wp-side-placeholder">无底稿信息</div>
        </slot>
      </el-tab-pane>
      <el-tab-pane label="依赖" name="dependencies" lazy>
        <slot name="dependencies">
          <DependencyGraph v-if="wpId" :project-id="projectId" :wp-id="wpId" />
          <div v-else class="gt-wp-side-placeholder">请先选择底稿</div>
        </slot>
      </el-tab-pane>
      <el-tab-pane label="一致性" name="consistency" lazy>
        <slot name="consistency">
          <div class="gt-wp-side-placeholder">一致性监控（由父组件通过 slot 注入）</div>
        </slot>
      </el-tab-pane>
      <el-tab-pane label="提示" name="tips" lazy>
        <slot name="tips">
          <div class="gt-wp-side-placeholder">智能提示（由父组件通过 slot 注入）</div>
        </slot>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import AiAssistantSidebar from '@/components/workpaper/AiAssistantSidebar.vue'
import AttachmentDropZone from '@/components/workpaper/AttachmentDropZone.vue'
import ProgramRequirementsSidebar from '@/components/workpaper/ProgramRequirementsSidebar.vue'
import DependencyGraph from '@/components/workpaper/DependencyGraph.vue'

defineProps<{
  /** 项目 ID */
  projectId: string
  /** 底稿 ID（可选，非底稿编辑器可不传） */
  wpId?: string
  /** 底稿编码（可选，用于程序要求 Tab） */
  wpCode?: string
}>()

const activeTab = ref('ai')
</script>

<style scoped>
.gt-wp-side-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--gt-color-border-light);
  background: var(--gt-color-bg-white);
}
.gt-wp-side-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.gt-wp-side-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow-y: auto;
  padding: var(--gt-space-2);
}
.gt-wp-side-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}
.gt-wp-side-tabs :deep(.el-tabs__item) {
  font-size: var(--gt-font-size-xs);
  padding: 0 8px;
}
.gt-wp-side-placeholder {
  padding: var(--gt-space-8);
  text-align: center;
  color: var(--gt-color-text-tertiary);
  font-size: var(--gt-font-size-sm);
}
</style>
