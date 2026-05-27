<!--
  GtLoadingOverlay — 加载蒙层组件

  锚定 spec workpaper-editor-refactor Req 5 + global-refinement-v3 Req 8.2.3

  使用模式：放在容器内部，作为 absolute-positioned 蒙层覆盖父容器。
  父容器需 position: relative。

  典型场景：替代顶层 v-if="loading" 守卫，避免拦住 template ref 挂载导致的 init 死锁。
  超时提示：超过 slowThresholdMs（默认 5000ms）后显示「加载较慢」附加提示。

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
    <p v-if="showSlowHint" class="gt-loading-overlay__slow-hint">
      {{ slowHintText }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'
import { Loading } from '@element-plus/icons-vue'

const props = withDefaults(defineProps<{
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
  /** 超时阈值（ms），超过后显示慢加载提示。0 表示禁用 */
  slowThresholdMs?: number
  /** 慢加载提示文本 */
  slowHintText?: string
}>(), {
  slowThresholdMs: 5000,
  slowHintText: '加载较慢，请耐心等待',
})

const showSlowHint = ref(false)
let slowTimer: ReturnType<typeof setTimeout> | null = null

function clearSlowTimer() {
  if (slowTimer !== null) {
    clearTimeout(slowTimer)
    slowTimer = null
  }
}

function startSlowTimer() {
  clearSlowTimer()
  showSlowHint.value = false
  if (props.slowThresholdMs > 0) {
    slowTimer = setTimeout(() => {
      showSlowHint.value = true
    }, props.slowThresholdMs)
  }
}

watch(
  () => props.visible,
  (val) => {
    if (val) {
      startSlowTimer()
    } else {
      clearSlowTimer()
      showSlowHint.value = false
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  clearSlowTimer()
})
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

.gt-loading-overlay__slow-hint {
  margin: 0;
  font-size: 12px;
  color: var(--gt-color-warning, #e6a23c);
  animation: gt-fade-in 0.3s ease-in;
}

@keyframes gt-fade-in {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
