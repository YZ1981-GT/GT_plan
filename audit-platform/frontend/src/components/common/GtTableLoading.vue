<!--
  表格加载状态统一组件 (UI-2)

  统一规则：
  - 首次加载（无数据）：显示骨架屏 (el-skeleton)
  - 刷新/翻页（已有数据）：显示 v-loading overlay

  使用方式：
    <GtTableLoading :loading="loading" :has-data="tableData.length > 0">
      <el-table :data="tableData" ...>
        ...
      </el-table>
    </GtTableLoading>
-->
<template>
  <div class="gt-table-loading">
    <!-- 首次加载：骨架屏 -->
    <el-skeleton
      v-if="loading && !hasData"
      :rows="skeletonRows"
      animated
      class="gt-table-loading__skeleton"
    />
    <!-- 有数据时的刷新/翻页：v-loading overlay -->
    <div
      v-else
      v-loading="loading && hasData"
      element-loading-text="加载中..."
      class="gt-table-loading__content"
    >
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * Props:
 * - loading: 是否正在加载
 * - hasData: 是否已有数据（用于区分首次加载和刷新）
 * - skeletonRows: 骨架屏行数（默认 5）
 */
withDefaults(defineProps<{
  loading: boolean
  hasData: boolean
  skeletonRows?: number
}>(), {
  skeletonRows: 5,
})
</script>

<style scoped>
.gt-table-loading {
  width: 100%;
  min-height: 120px;
}
.gt-table-loading__skeleton {
  padding: 16px;
}
.gt-table-loading__content {
  width: 100%;
}
</style>
