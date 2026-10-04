/**
 * useContainerWidth — 用原生 ResizeObserver 跟踪容器实际可用宽度
 *
 * 配合 useAutoColumnWidth 使用：列宽算完后要知道容器有多宽，才能决定
 * 「剩余空间分给谁」还是「横向滚动」。在此之前各表格都写死 `tableWidth = 1200`
 * 之类的常量，窄屏溢出、宽屏右侧留白。
 *
 * el-table-v2 尤其需要：它的 `:width` 是必填的数字 prop，虚拟滚动靠它算位置，
 * 没法像 el-table 那样 `style="width:100%"` 交给 CSS。
 *
 * 用法：
 * ```vue
 * <div ref="wrapRef">
 *   <el-table-v2 :width="containerWidth" ... />
 * </div>
 * ```
 * ```ts
 * const wrapRef = ref<HTMLElement | null>(null)
 * const { width: containerWidth } = useContainerWidth(wrapRef, { fallback: 1200 })
 * ```
 */
import { onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'

export interface UseContainerWidthOptions {
  /** 测不到时的兜底宽度（SSR / 元素未挂载 / 隐藏 tab），默认 1200 */
  fallback?: number
  /** 最小宽度，避免折叠侧栏瞬间算出 0 导致表格塌掉，默认 320 */
  minWidth?: number
  /** 右侧预留（滚动条 / 边框），默认 2px */
  reserve?: number
}

export function useContainerWidth(
  target: Ref<HTMLElement | null | undefined>,
  options: UseContainerWidthOptions = {},
) {
  const { fallback = 1200, minWidth = 320, reserve = 2 } = options

  const width = ref(fallback)
  let observer: ResizeObserver | null = null

  function measure(el: HTMLElement | null | undefined): void {
    if (!el) return
    // clientWidth 已扣除滚动条，比 getBoundingClientRect 更贴合可布局宽度
    const raw = el.clientWidth - reserve
    // 隐藏容器（display:none / 未激活 tab）会得 0，此时保留上一次有效值
    if (raw <= 0) return
    width.value = Math.max(minWidth, Math.round(raw))
  }

  function attach(el: HTMLElement | null | undefined): void {
    detach()
    if (!el) return
    measure(el)
    // 老环境 / jsdom 里可能没有 ResizeObserver，退化为一次性测量
    if (typeof ResizeObserver === 'undefined') return
    observer = new ResizeObserver(() => measure(el))
    observer.observe(el)
  }

  function detach(): void {
    observer?.disconnect()
    observer = null
  }

  onMounted(() => attach(target.value))
  // ref 挂载时机晚于 onMounted 的场景（v-if 包裹、异步组件）靠 watch 补上
  watch(target, (el) => attach(el))
  onBeforeUnmount(detach)

  return { width, measure: () => measure(target.value) }
}
