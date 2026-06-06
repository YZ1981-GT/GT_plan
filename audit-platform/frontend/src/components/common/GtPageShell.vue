<!--
  GtPageShell — 页面骨架统一容器
  [platform-ui-editing-consistency MVP-1]

  Wraps GtPageHeader + ProjectContextBar + StatusBanners + content 为统一骨架。
  非项目页（登录、系统管理）不使用此组件，继续用 GtPageHeader 或无 header。

  Slots:
    - header: 页面标题区（默认渲染 GtPageHeader）
    - context: 项目上下文条（ProjectContextBar）
    - toolbar: 工具栏区域
    - banners: 状态横幅（归档/锁定/stale/conflict）
    - default: 页面主内容
-->
<template>
  <div class="gt-page-shell">
    <div class="gt-page-shell__header">
      <slot name="header">
        <GtPageHeader v-bind="$attrs" />
      </slot>
    </div>
    <div v-if="$slots.context" class="gt-page-shell__context">
      <slot name="context" />
    </div>
    <div v-if="$slots.toolbar" class="gt-page-shell__toolbar">
      <slot name="toolbar" />
    </div>
    <div v-if="$slots.banners" class="gt-page-shell__banners">
      <slot name="banners" />
    </div>
    <div class="gt-page-shell__content">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import GtPageHeader from './GtPageHeader.vue'

defineOptions({ name: 'GtPageShell', inheritAttrs: false })
</script>
