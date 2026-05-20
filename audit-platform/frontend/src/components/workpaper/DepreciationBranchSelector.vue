<!--
  DepreciationBranchSelector.vue — H 循环折旧/减值分支选择器组件

  spec workpaper-h-fixed-assets-cycle ADR-H3（Task 2.1）

  当 active sheet 的 wp_code 有多版本时渲染（el-radio-group 样式）。
  5 个位置：H1-12(3版) / H3-7(2版) / H5-12(2版) / H7-11(2版) / H8-8(2版)

  切换分支 = 调用 sheetNav.switchTo(targetSheetName)，不清空前一分支数据。
-->
<template>
  <div v-if="branches.length > 1" class="gt-branch-selector">
    <span class="gt-branch-selector__label">版本切换：</span>
    <el-radio-group
      :model-value="activeBranch"
      size="small"
      @change="onBranchChange"
    >
      <el-radio-button
        v-for="branch in branches"
        :key="branch.sheetName"
        :value="branch.sheetName"
      >
        <span :class="{ 'gt-branch-main': branch.isMain }">
          {{ branch.label }}
        </span>
      </el-radio-button>
    </el-radio-group>
  </div>
</template>

<script setup lang="ts">
import type { BranchOption } from '@/composables/useDepreciationBranchSelector'

const props = defineProps<{
  branches: BranchOption[]
  activeBranch: string
}>()

const emit = defineEmits<{
  (e: 'switch', sheetName: string): void
}>()

function onBranchChange(val: string | number | boolean | undefined) {
  if (typeof val === 'string') {
    emit('switch', val)
  }
}
</script>

<style scoped>
.gt-branch-selector {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: var(--gt-color-bg-light, #f5f7fa);
  border-bottom: 1px solid var(--gt-color-border, #e4e7ed);
  font-size: var(--gt-font-size-sm, 13px);
}

.gt-branch-selector__label {
  color: var(--gt-color-text-secondary, #606266);
  white-space: nowrap;
  font-weight: 500;
}

.gt-branch-main {
  font-weight: 600;
}
</style>
