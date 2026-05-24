<!--
  TemplateLibraryButton.vue — 模板页「📊 高级查询」按钮
  Task 7.1 (Req 14 AC 1)

  用于 3 个模板页面：WpTemplateDetail / ReportConfigTab / NoteTemplateTab
  点击后 emit open-custom-query 事件，自动预填当前模板对应 source 打开高级查询
-->
<template>
  <el-button
    type="primary"
    size="default"
    plain
    class="gt-template-query-btn"
    @click="onOpenQuery"
  >
    📊 高级查询
  </el-button>
</template>

<script setup lang="ts">
import { eventBus } from '@/utils/eventBus'

interface Props {
  /** source URI，如 "workpaper:D2|审定表D2-1" / "report:balance_sheet" / "note:五-1-1" */
  source: string
  /** 可选项目 ID，用于项目级查询 */
  projectId?: string
}

const props = defineProps<Props>()

function onOpenQuery() {
  eventBus.emit('open-custom-query', {
    tab: 'basic',
    source: props.source,
    project_id: props.projectId,
  })
}
</script>

<style scoped>
.gt-template-query-btn {
  font-weight: 500;
}
</style>
