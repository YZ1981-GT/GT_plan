<!--
  GtLoadingOverlay — 加载蒙层组件

  锚定 spec workpaper-editor-refactor Req 5

  使用模式：放在容器内部，作为 absolute-positioned 蒙层覆盖父容器。
  父容器需 position: relative。

  典型场景：替代顶层 v-if="loading" 守卫，避免拦住 template ref 挂载导致的 init 死锁。

  @example
  <div class="container" style="position: relative">
    <div ref="myContainer">这里需要 ref 挂载触发 init</div>
    <GtLoadingOverlay :visible="loading" text="加载中..." />
  </div>
-->
<template>
  <div v-if="visible" class="gt-loading-overlay" :class="{ 'is-transparent': transparent }">
    <el-icon class="is-loading" :size="size" :color="color">
      <Loading />
    </el-icon>
    <p v-if="text" class="gt-loading-overlay__text">{{ text }}</p>
    <p v-if="hint" class="gt-loading-overlay__hint">{{ hint }}</p>
  </div>
</template>

<script setup lang="ts">
import { Loading } from '@element-plus/icons-vue'

defineProps<{
  /** 是否显示蒙层 */
  visible: boolean
  /** 主文本 */
  text?: string
  /** 提示文本（次级，更小字号） */
  hint?: string
  /** 图标大小 */
  size?: number
  /** 图标颜色 */
  color?: string
  /** 是否半透明（用于不完全遮挡背景） */
  transparent?: boolean
}>()
</script>

<style scoped>
.gt-loading-overlay {
  position: absolute;
  inset: 0;
  z-index: 100;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--gt-color-bg-white, #fff);
  gap: 12px;
}

.gt-loading-overlay.is-transparent {
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(2px);
}

.gt-loading-overlay__text {
  margin: 0;
  font-size: 14px;
  color: var(--gt-color-text-secondary, #606266);
}

.gt-loading-overlay__hint {
  margin: 0;
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}
</style>
