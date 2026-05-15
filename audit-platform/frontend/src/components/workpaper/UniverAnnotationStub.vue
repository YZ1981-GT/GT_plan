<script setup lang="ts">
/**
 * Univer 右键菜单"添加复核意见" + 单元格红色三角标记渲染（Stub）
 * Sprint 10 Task 10.4
 *
 * 完整 Univer 集成需要 @univerjs/sheets-ui 的 ContextMenu 扩展 API。
 * 此文件为占位实现，提供接口定义和基本逻辑框架。
 */
import { ref } from 'vue'

export interface CellAnnotationMark {
  sheetName: string
  row: number
  col: number
  hasAnnotation: boolean
}

const marks = ref<CellAnnotationMark[]>([])

/**
 * 注册右键菜单项（需在 Univer 初始化后调用）
 * 实际实现需要 univerAPI.registerContextMenuItem
 */
function registerContextMenu(_univerAPI: unknown) {
  // Stub: 实际实现需要 Univer ContextMenu API
  // univerAPI.registerContextMenuItem({
  //   id: 'add-review-annotation',
  //   title: '添加复核意见',
  //   handler: () => { /* open annotation dialog */ }
  // })
}

/**
 * 渲染红色三角标记（需在 sheet 渲染后调用）
 * 实际实现需要 Univer CellRender 扩展
 */
function renderAnnotationMarks(_sheetId: string, _annotations: CellAnnotationMark[]) {
  marks.value = _annotations
  // Stub: 实际实现需要 Univer 自定义渲染层
  // 在单元格右上角绘制红色三角形
}

defineExpose({ registerContextMenu, renderAnnotationMarks, marks })
</script>

<template>
  <!-- Stub: 实际渲染由 Univer Canvas 层完成 -->
  <div class="univer-annotation-stub" style="display: none;" />
</template>
