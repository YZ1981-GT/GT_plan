<!--
  GtPageShell — 页面骨架统一容器
  [platform-ui-editing-consistency P0-2]

  统一页面布局：GtPageHeader + ProjectContextBar + StatusBanners + Toolbar + Content
  非项目页（登录、系统管理、首页）不使用此组件，继续用 GtPageHeader 或无 header。

  Slots:
    - header: 页面标题区（默认渲染 GtPageHeader，可通过 props 配置）
    - context: 项目上下文条（ProjectContextBar）
    - toolbar: 工具栏区域（GtToolbar 或业务域 toolbar）
    - banners: 状态横幅（归档/锁定/stale/conflict）
    - default: 页面主内容

  适用边界：
    - 项目内业务页面（试算表、底稿、报表、附注、合并等）应使用
    - 非项目页（登录、系统管理、首页）不使用
    - 纯弹窗页不使用
-->
<template>
  <div
    class="gt-page-shell"
    :class="{
      'gt-page-shell--fullscreen': fullscreen,
      'gt-page-shell--compact': compact,
    }"
  >
    <!-- Header 区：默认渲染 GtPageHeader，支持自定义 -->
    <div class="gt-page-shell__header">
      <slot name="header">
        <GtPageHeader v-bind="headerProps" />
      </slot>
    </div>

    <!-- 项目上下文条：仅在提供 slot 时渲染 -->
    <div v-if="$slots.context" class="gt-page-shell__context">
      <slot name="context" />
    </div>

    <!-- 工具栏：仅在提供 slot 时渲染 -->
    <div v-if="$slots.toolbar" class="gt-page-shell__toolbar">
      <slot name="toolbar" />
    </div>

    <!-- 状态横幅（归档/锁定/stale/conflict）：仅在提供 slot 时渲染 -->
    <div v-if="$slots.banners" class="gt-page-shell__banners">
      <slot name="banners" />
    </div>

    <!-- 页面主内容 -->
    <div class="gt-page-shell__content">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import GtPageHeader from './GtPageHeader.vue'

defineOptions({ name: 'GtPageShell', inheritAttrs: false })

const props = withDefaults(
  defineProps<{
    /** 是否全屏模式 */
    fullscreen?: boolean
    /** 是否紧凑模式（减少间距） */
    compact?: boolean
    /** 透传给默认 GtPageHeader 的 props（title / showSyncStatus 等） */
    headerProps?: Record<string, any>
  }>(),
  {
    fullscreen: false,
    compact: false,
    headerProps: () => ({}),
  },
)
</script>

<style scoped>
.gt-page-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--gt-color-bg-page, #f5f5f5);
}

.gt-page-shell--fullscreen {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: var(--gt-color-bg-page, #fff);
}

.gt-page-shell__header {
  flex-shrink: 0;
}

.gt-page-shell__context {
  flex-shrink: 0;
  padding: 0 16px;
  background: var(--gt-color-primary-bg, #f4f0fa);
  border-bottom: 1px solid var(--gt-color-border-purple-light, #d8b8ee);
}

.gt-page-shell__toolbar {
  flex-shrink: 0;
  padding: 8px 16px;
  border-bottom: 1px solid var(--gt-color-border-light, #ebeef5);
  background: var(--gt-color-bg-overlay, #fff);
}

.gt-page-shell__banners {
  flex-shrink: 0;
}

.gt-page-shell__content {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 16px;
}

/* 紧凑模式 */
.gt-page-shell--compact .gt-page-shell__content {
  padding: 8px 12px;
}

.gt-page-shell--compact .gt-page-shell__toolbar {
  padding: 4px 12px;
}
</style>
