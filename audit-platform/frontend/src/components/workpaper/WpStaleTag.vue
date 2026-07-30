<!--
  WpStaleTag — 底稿「预填待重算」标记（单一文案来源）
  ==================================================================
  底稿列表/工作台目录/看板等处统一用它渲染 `prefill_stale` 状态，避免同一句
  解释文案在多处复制漂移。

  语义（与后端 stale-summary 的 stale_reason 一致）：
  - stale=true  → 上游数据变更后预填待重算；若底稿正文已保存，试算表重算不会
                  覆盖持久化值，需打开底稿刷新后重新保存。
  - stale=false → 数据为最新（弱化显示，不与待重算抢注意力）。

  用法：
    <WpStaleTag :stale="row.prefill_stale" />
    <WpStaleTag :stale="row.prefill_stale" hide-fresh />   仅在过期时占位
-->
<template>
  <el-tooltip v-if="stale" :content="STALE_HINT" placement="top" :show-after="300">
    <el-tag type="warning" size="small" effect="light">待重算</el-tag>
  </el-tooltip>
  <span v-else-if="!hideFresh" class="gt-wp-stale-tag__fresh">最新</span>
</template>

<script setup lang="ts">
// 注意：`<script setup>` 不允许 export，文案作为组件内常量维护（这里就是单一来源）
const STALE_HINT =
  '上游数据变更后预填待重算；若底稿正文已保存，试算表重算不覆盖持久化值，需打开底稿刷新后重新保存'

defineProps<{
  /** prefill_stale */
  stale?: boolean
  /** 非过期时不渲染「最新」占位（空间紧张的目录行用） */
  hideFresh?: boolean
}>()
</script>

<style scoped>
.gt-wp-stale-tag__fresh {
  color: var(--gt-color-text-secondary, #909399);
}
</style>
