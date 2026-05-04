/**
 * 全屏切换 composable
 *
 * 统一 17+ 个组件各自实现的全屏逻辑：
 * - const isFullscreen = ref(false)
 * - ESC 键退出
 * - 自动注册/注销键盘监听
 *
 * 用法：
 * ```ts
 * const { isFullscreen, toggleFullscreen } = useFullscreen()
 * ```
 *
 * 模板中：
 * ```html
 * <div :class="{ 'gt-fullscreen': isFullscreen }">
 *   <el-button @click="toggleFullscreen">{{ isFullscreen ? '退出全屏' : '⛶ 全屏' }}</el-button>
 * </div>
 * ```
 */
import { ref, onMounted, onUnmounted } from 'vue'

export function useFullscreen() {
  const isFullscreen = ref(false)

  function toggleFullscreen() {
    isFullscreen.value = !isFullscreen.value
  }

  function enterFullscreen() {
    isFullscreen.value = true
  }

  function exitFullscreen() {
    isFullscreen.value = false
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape' && isFullscreen.value) {
      isFullscreen.value = false
    }
  }

  onMounted(() => document.addEventListener('keydown', onKeydown))
  onUnmounted(() => document.removeEventListener('keydown', onKeydown))

  return {
    isFullscreen,
    toggleFullscreen,
    enterFullscreen,
    exitFullscreen,
  }
}
