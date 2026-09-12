<!--
  GtWpToolbar — 底稿统一功能工具栏

  所有底稿渲染页面的公共操作区域（放在 GtWpRenderer 层），
  避免每个底稿子组件重复实现导出/导入/全屏等功能。
-->
<template>
  <div class="gt-wp-toolbar">
    <div class="gt-wp-toolbar__left">
      <el-button size="small" @click="$emit('export-template')">
        <el-icon><Download /></el-icon> 导出模板
      </el-button>
      <el-button size="small" @click="$emit('export-data')">
        <el-icon><Document /></el-icon> 导出数据
      </el-button>
      <el-button size="small" @click="$emit('import-data')">
        <el-icon><Upload /></el-icon> 导入
      </el-button>
    </div>
    <!-- 中间插槽：放 AI 复核工具栏（本页/批量），占用左右按钮之间的空档 -->
    <div v-if="$slots.center" class="gt-wp-toolbar__center">
      <slot name="center" />
    </div>
    <div class="gt-wp-toolbar__right">
      <!-- Task 5: real named compatibility outlet (CSS class remains styling only) -->
      <span
        class="gt-wp-toolbar__compat-outlet"
        data-toolbar-outlet="page-capabilities-compatibility"
        data-testid="page-capabilities-compatibility"
      >
        <slot name="page-capabilities-compatibility" />
      </span>
      <el-button size="small" @click="$emit('open-attachments')">
        <el-icon><Paperclip /></el-icon> 关联附件
      </el-button>
      <el-button size="small" @click="$emit('add-row')">
        <el-icon><Plus /></el-icon> 增行
      </el-button>
      <el-button
        size="small"
        :type="fullscreen ? 'primary' : ''"
        @click="$emit('toggle-fullscreen')"
      >
        <el-icon><FullScreen /></el-icon> {{ fullscreen ? '退出全屏' : '全屏' }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Download, Document, Upload, Plus, FullScreen, Paperclip } from '@element-plus/icons-vue'

defineProps<{
  fullscreen?: boolean
  wpId?: string
}>()

defineEmits<{
  'export-template': []
  'export-data': []
  'import-data': []
  'add-row': []
  'toggle-fullscreen': []
  'open-attachments': []
}>()
</script>

<style scoped>
.gt-wp-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 12px;
  border-bottom: 1px solid #ebeef5;
  background: #fafafa;
  flex-shrink: 0;
}
.gt-wp-toolbar__left,
.gt-wp-toolbar__right,
.gt-wp-toolbar__center {
  display: flex;
  gap: 6px;
  align-items: center;
}
.gt-wp-toolbar__compat-outlet {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
</style>
