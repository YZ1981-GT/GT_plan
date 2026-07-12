<script setup lang="ts">
/**
 * WpFormulaCell — 公式列统一单元格组件（Wp_Kit）
 *
 * 显示值 + 虚线下划线 + cursor:help + 来源 tooltip
 * 替代底稿中散落的 `.formula-cell` / `title=` 内联 tooltip 等手写结构
 *
 * @example
 * <WpFormulaCell
 *   :value="row.auditedAmount"
 *   formula="=TB(1122, audited)"
 *   source="试算平衡表"
 * />
 *
 * Feature: platform-global-hardening
 * Requirements: 4.2
 */

defineProps<{
  /** 显示值（格式化后的文本或数字） */
  value: string | number | null | undefined
  /** 公式表达式（如 =TB(1122, audited)） */
  formula?: string
  /** 数据来源描述（如"试算平衡表"、"其他底稿 D2-1"） */
  source?: string
}>()

/**
 * 构建 tooltip 内容
 */
function buildTooltipContent(formula?: string, source?: string): string {
  const parts: string[] = []
  if (formula) parts.push(`公式: ${formula}`)
  if (source) parts.push(`来源: ${source}`)
  return parts.join('\n') || '公式列'
}
</script>

<template>
  <el-tooltip
    :content="buildTooltipContent(formula, source)"
    placement="top"
    :show-after="300"
    :disabled="!formula && !source"
    raw-content
  >
    <span class="wp-formula-cell">
      {{ value ?? '—' }}
    </span>
  </el-tooltip>
</template>

<style scoped>
.wp-formula-cell {
  display: inline-block;
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
</style>
