/**
 * v-tab-wheel — 为 el-tabs 添加鼠标滚轮切换 tab 功能
 *
 * 用法：在 el-tabs 上加 v-tab-wheel 即可
 * <el-tabs v-model="activeTab" v-tab-wheel>
 *
 * 原理：监听 el-tabs__nav-wrap 上的 wheel 事件，
 * 滚轮向下/右 → 切到下一个 tab，向上/左 → 切到上一个 tab
 */
import type { Directive, DirectiveBinding } from 'vue'

interface TabWheelEl extends HTMLElement {
  _tabWheelHandler?: (e: WheelEvent) => void
}

const vTabWheel: Directive = {
  mounted(el: TabWheelEl, binding: DirectiveBinding) {
    // 延迟绑定，确保 el-tabs DOM 已渲染
    setTimeout(() => {
      const navWrap = el.querySelector('.el-tabs__nav-wrap') || el.querySelector('.el-tabs__header') || el
      if (!navWrap) return

      const handler = (e: WheelEvent) => {
        // 仅在 tabs 导航区域触发（不拦截内容区滚动）
        const delta = e.deltaY || e.deltaX
        if (delta === 0) return

        // 找到所有可见 tab
        const tabs = el.querySelectorAll<HTMLElement>('.el-tabs__item')
        if (tabs.length <= 1) return

        // 找当前激活的 tab
        const activeTab = el.querySelector<HTMLElement>('.el-tabs__item.is-active')
        if (!activeTab) return

        const tabsArr = Array.from(tabs)
        const currentIdx = tabsArr.indexOf(activeTab)
        if (currentIdx < 0) return

        let nextIdx: number
        if (delta > 0) {
          // 向下/右滚 → 下一个
          nextIdx = Math.min(currentIdx + 1, tabsArr.length - 1)
        } else {
          // 向上/左滚 → 上一个
          nextIdx = Math.max(currentIdx - 1, 0)
        }

        if (nextIdx !== currentIdx) {
          e.preventDefault()
          e.stopPropagation()
          tabsArr[nextIdx].click()
        }
      }

      navWrap.addEventListener('wheel', handler as EventListener, { passive: false })
      el._tabWheelHandler = handler
      ;(el as any)._tabWheelNavWrap = navWrap
    }, 100)
  },

  unmounted(el: TabWheelEl) {
    if (el._tabWheelHandler && (el as any)._tabWheelNavWrap) {
      ;(el as any)._tabWheelNavWrap.removeEventListener('wheel', el._tabWheelHandler as EventListener)
    }
  },
}

export default vTabWheel
