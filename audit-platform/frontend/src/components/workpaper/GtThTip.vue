<script setup lang="ts">
/**
 * GtThTip — 表头省略号 + 鼠标悬停显示完整内容
 *
 * 用于宽表 el-table-column 的 #header 插槽，解决表头文字过长被截断看不全的问题。
 * 用法：<el-table-column ...><template #header><GtThTip text="完整表头文字" /></template>...</el-table-column>
 */
defineProps<{ text: string }>()
</script>

<template>
  <el-tooltip :content="text" placement="top" :show-after="200" effect="dark">
    <span class="gt-th-tip">{{ text }}</span>
  </el-tooltip>
</template>

<style scoped>
.gt-th-tip {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
  cursor: help;
}
</style>
