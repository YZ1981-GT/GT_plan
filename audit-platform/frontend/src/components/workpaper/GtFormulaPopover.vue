<!--
  GtFormulaPopover.vue — 公式溯源 Popover

  按 design §3.11 实现：
  - 触发元素挂插槽（slot），用户 hover/click 显示公式与依赖列表
  - 显示原始公式、计算结果、所有依赖项（cell + 当前值）
  - 适用 sheet 内联动（Layer 1）：行/列合计、子表合计 → 主表行等

  锚定 spec workpaper-html-renderer Task 12.5
  Validates: Requirements 3.11.5 Layer 1（sheet 内联动）
-->
<template>
  <el-popover
    :placement="placement"
    :width="width"
    :trigger="trigger"
    :show-after="showAfter"
    :hide-after="hideAfter"
    popper-class="gt-formula-popover-popper"
  >
    <template #reference>
      <span class="gt-formula-popover__trigger">
        <slot />
      </span>
    </template>

    <div class="gt-formula-popover">
      <header v-if="formula || cellValue !== undefined" class="gt-formula-popover__header">
        <div v-if="formula" class="gt-formula-popover__formula">
          <span class="gt-formula-popover__prefix">ƒ</span>
          <code>{{ formula }}</code>
        </div>
        <div v-if="cellValue !== undefined && cellValue !== null" class="gt-formula-popover__result">
          <span class="gt-formula-popover__result-label">结果：</span>
          <span class="gt-formula-popover__result-value">{{ formatValue(cellValue) }}</span>
        </div>
      </header>

      <div v-if="dependencies && dependencies.length" class="gt-formula-popover__deps">
        <div class="gt-formula-popover__deps-title">依赖项（{{ dependencies.length }}）</div>
        <ul class="gt-formula-popover__deps-list">
          <li
            v-for="(dep, idx) in dependencies"
            :key="idx"
            class="gt-formula-popover__dep"
          >
            <span class="gt-formula-popover__dep-name">{{ dep.name }}</span>
            <span class="gt-formula-popover__dep-value">= {{ formatValue(dep.value) }}</span>
          </li>
        </ul>
      </div>

      <div
        v-if="!formula && (!dependencies || !dependencies.length) && cellValue === undefined"
        class="gt-formula-popover__empty"
      >
        暂无公式信息
      </div>
    </div>
  </el-popover>
</template>

<script setup lang="ts">
// ─── Props ───
const props = withDefaults(defineProps<{
  /** 公式字符串（如 "=SUM(K10:K20)" 或 "X+Y"） */
  formula?: string
  /** 当前 cell 计算结果 */
  cellValue?: number | string | null
  /** 依赖项列表 */
  dependencies?: { name: string; value: number | string | null | undefined }[]
  /** popover 触发方式 */
  trigger?: 'hover' | 'click' | 'focus'
  /** popover 出现位置 */
  placement?: 'top' | 'top-start' | 'top-end' | 'bottom' | 'bottom-start' | 'bottom-end' | 'left' | 'right'
  /** popover 宽度 */
  width?: number | string
  /** 显示延迟（ms） */
  showAfter?: number
  /** 隐藏延迟（ms） */
  hideAfter?: number
}>(), {
  trigger: 'hover',
  placement: 'top',
  width: 320,
  showAfter: 300,
  hideAfter: 200,
})

// ─── Methods ───
function formatValue(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') {
    return value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
  }
  return String(value)
}
</script>

<style scoped>
.gt-formula-popover__trigger {
  display: inline-flex;
  align-items: center;
  cursor: help;
}

.gt-formula-popover {
  display: flex;
  flex-direction: column;
  gap: 10px;
  font-size: 12px;
  color: var(--gt-color-text-primary, #303133);
}

.gt-formula-popover__header {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-bottom: 8px;
  border-bottom: 1px dashed var(--gt-color-border-light, #ebeef5);
}

.gt-formula-popover__formula {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.gt-formula-popover__prefix {
  color: var(--gt-color-warning, #e6a23c);
  font-weight: 600;
  font-style: italic;
}

.gt-formula-popover__formula code {
  flex: 1;
  padding: 2px 6px;
  background: var(--gt-color-bg-page, #f5f5f5);
  border-radius: 3px;
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 12px;
  color: var(--gt-color-text-regular, #606266);
  word-break: break-all;
}

.gt-formula-popover__result {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.gt-formula-popover__result-label {
  color: var(--gt-color-text-tertiary, #909399);
}

.gt-formula-popover__result-value {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-weight: 600;
  color: var(--gt-color-primary, #6750a4);
}

.gt-formula-popover__deps {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.gt-formula-popover__deps-title {
  font-size: 11px;
  color: var(--gt-color-text-tertiary, #909399);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.gt-formula-popover__deps-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 220px;
  overflow-y: auto;
}

.gt-formula-popover__dep {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 8px;
  background: var(--gt-color-bg-page, #fafafa);
  border-radius: 3px;
}

.gt-formula-popover__dep-name {
  color: var(--gt-color-text-regular, #606266);
  font-family: 'JetBrains Mono', Consolas, monospace;
}

.gt-formula-popover__dep-value {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-weight: 500;
  color: var(--gt-color-success, #67c23a);
}

.gt-formula-popover__empty {
  padding: 8px;
  text-align: center;
  color: var(--gt-color-text-tertiary, #909399);
  font-style: italic;
}
</style>
