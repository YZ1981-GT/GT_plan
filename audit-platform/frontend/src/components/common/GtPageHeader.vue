<!--
  GtPageHeader — 通用页面横幅组件 [R5.4]
  紫色渐变横幅，统一各模块的页面头部样式。
  包含返回按钮、标题、信息栏插槽（GtInfoBar）、操作按钮插槽（GtToolbar）。

  用法：
    <GtPageHeader title="试算表" @back="router.push('/projects')">
      <GtInfoBar ... />
      <template #actions>
        <GtToolbar ... />
      </template>
    </GtPageHeader>
-->
<template>
  <div class="gt-page-header">
    <div class="gt-page-header__row1">
      <el-button
        v-if="showBack"
        text
        class="gt-page-header__back"
        @click="$emit('back')"
      >← 返回</el-button>
      <h2 class="gt-page-header__title">{{ title }}</h2>
      <!-- 默认插槽：放 GtInfoBar -->
      <slot />
    </div>
    <!-- actions 插槽：放 GtToolbar -->
    <slot name="actions" />
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  /** 页面标题 */
  title: string
  /** 是否显示返回按钮 */
  showBack?: boolean
}>(), {
  showBack: true,
})

defineEmits<{
  (e: 'back'): void
}>()
</script>

<style scoped>
.gt-page-header {
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: var(--gt-gradient-primary);
  border-radius: var(--gt-radius-lg);
  padding: 16px 24px;
  margin-bottom: var(--gt-space-5);
  color: #fff;
  position: relative;
  overflow: hidden;
  box-shadow: 0 4px 20px rgba(75, 45, 119, 0.2);
  /* 网格纹理 */
  background-image:
    var(--gt-gradient-primary),
    linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px);
  background-size: 100% 100%, 20px 20px, 20px 20px;
}

/* 径向光晕装饰 */
.gt-page-header::before {
  content: '';
  position: absolute;
  top: -40%;
  right: -10%;
  width: 45%;
  height: 180%;
  background: radial-gradient(ellipse, rgba(255, 255, 255, 0.07) 0%, transparent 65%);
  pointer-events: none;
}

.gt-page-header__row1 {
  display: flex;
  align-items: center;
  gap: 16px;
  position: relative;
  z-index: 1;
  flex-wrap: wrap;
}

.gt-page-header__back {
  color: #fff !important;
  font-size: 13px;
  padding: 0;
  margin-right: 8px;
}

.gt-page-header__title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  white-space: nowrap;
  flex-shrink: 0;
}
</style>
