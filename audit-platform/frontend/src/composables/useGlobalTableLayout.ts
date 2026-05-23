/**
 * useGlobalTableLayout
 * ─────────────────────────────────────────────────────────────────────────────
 * 全局表格列宽自适应（Phase 1 D-5）
 *
 * 当用户在显示偏好里切换"表格字号"时，所有页面已挂载的 `<el-table>` 应当
 * 立即重新计算列宽，否则窄字号下列宽过宽 / 宽字号下列宽过窄会出现错位。
 *
 * 设计要点：
 * - **全局单点接入**：在 `DefaultLayout.vue` setup 阶段调用一次即可，
 *   不再需要每个页面单独 watch / 拿 ref。
 * - **DOM 侧反查 ElTable 实例**：用 Vue 3 内部的 `__vueParentComponent`
 *   从 `.el-table` 根元素回溯到组件实例，再调 `exposed.doLayout()`。
 *   兼容 Vue 2 风格的 `__vue__.doLayout()` 作为最终 fallback。
 * - **不破坏既有 watcher**：`GtEditableTable.vue` 内部已有针对自身 ref 的
 *   `tableRef.value?.doLayout?.()`，本 composable 与之并行（doLayout 是
 *   幂等操作，多次调用无副作用）。
 *
 * 用法：
 * ```ts
 * // DefaultLayout.vue
 * import { useGlobalTableLayout } from '@/composables/useGlobalTableLayout'
 * useGlobalTableLayout()
 * ```
 */
import { watch, nextTick } from 'vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

/**
 * 从 DOM 元素回溯到 ElTable 组件实例，并调用其 `doLayout` 方法。
 *
 * Vue 3 + Element Plus 路径：
 *   `el.__vueParentComponent` → `ComponentInternalInstance`
 *     → `exposed.doLayout`（ElTable 通过 defineExpose 暴露）
 *     → `proxy.doLayout`（Options API 风格 fallback）
 * Vue 2 fallback：
 *   `el.__vue__.doLayout`
 *
 * 如果都找不到（比如 mount 测试环境下表格只是空 stub），静默返回 false。
 *
 * @returns 是否成功调用了 doLayout
 */
export function relayoutElTableElement(el: Element): boolean {
  // Vue 3 路径：从 DOM 节点反查组件实例 + 向上回溯 ≤ 5 层
  // 注意：`__vueParentComponent` 是 Vue 3 暴露在根元素上的内部字段
  // 直接挂载这个元素的组件实例就是 ElTable 自身
  let current: any = (el as any).__vueParentComponent
  const visited = new Set<any>()
  let depth = 0
  while (current && !visited.has(current) && depth < 5) {
    visited.add(current)
    const target = current.exposed ?? current.proxy
    const fn = target?.doLayout
    if (typeof fn === 'function') {
      try {
        fn.call(target)
        return true
      } catch {
        // 单个表 doLayout 失败不应阻断其他表
      }
    }
    current = current.parent
    depth++
  }

  // Vue 2 / 旧版 Element UI fallback
  const legacy = (el as any).__vue__
  if (legacy && typeof legacy.doLayout === 'function') {
    try {
      legacy.doLayout()
      return true
    } catch {
      /* ignore */
    }
  }

  return false
}

/**
 * 遍历 document 内所有 `.el-table` 调用 doLayout，返回成功调用的实例数。
 * 暴露为独立函数以便测试 / 其他场景（如窗口 resize 后强制重排）复用。
 */
export function relayoutAllElTables(): number {
  const tables = document.querySelectorAll<HTMLElement>('.el-table')
  let count = 0
  tables.forEach((el) => {
    if (relayoutElTableElement(el)) count++
  })
  return count
}

/**
 * 注册全局字号变更监听器：
 * - 监听 `displayPrefs.fontSize` 变化
 * - `nextTick` 等 Vue 完成 :class 重渲染（gt-tb-font-* class 切换会触发
 *   行高/单元格 padding 变化）后再 doLayout
 *
 * 在 `DefaultLayout.vue` setup 中调用一次即可。
 */
export function useGlobalTableLayout(): void {
  const displayPrefs = useDisplayPrefsStore()

  watch(
    () => displayPrefs.fontSize,
    () => {
      nextTick(() => {
        relayoutAllElTables()
      })
    },
  )
}
