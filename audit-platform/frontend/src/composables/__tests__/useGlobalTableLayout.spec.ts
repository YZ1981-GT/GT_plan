/**
 * useGlobalTableLayout 单元测试
 *
 * 验收点（task 1.2 D-5）：
 * - 切换 displayPrefs.fontSize 后，所有 .el-table 的 doLayout 被调用一次
 * - 同时支持 Vue 3 (__vueParentComponent.exposed) 与 Vue 2 (__vue__) 两条路径
 * - 找不到 doLayout 的元素静默跳过，不抛异常
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import {
  useGlobalTableLayout,
  relayoutAllElTables,
  relayoutElTableElement,
} from '../useGlobalTableLayout'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

function withSetup(composable: () => any) {
  let result: any
  const Comp = defineComponent({
    setup() {
      result = composable()
      return {}
    },
    template: '<div />',
  })
  const wrapper = mount(Comp)
  return { result, wrapper }
}

/**
 * 在 document.body 上挂一个伪 .el-table，并在元素上挂载 mock 的
 * `__vueParentComponent.exposed.doLayout`（模拟 Element Plus 3 的内部结构）。
 */
function mountFakeElTableV3(doLayoutSpy: ReturnType<typeof vi.fn>): HTMLElement {
  const el = document.createElement('div')
  el.className = 'el-table'
  document.body.appendChild(el)
  ;(el as any).__vueParentComponent = {
    exposed: { doLayout: doLayoutSpy },
    proxy: null,
    parent: null,
  }
  return el
}

/** Vue 2 / Element UI 旧版风格 fallback */
function mountFakeElTableV2(doLayoutSpy: ReturnType<typeof vi.fn>): HTMLElement {
  const el = document.createElement('div')
  el.className = 'el-table'
  document.body.appendChild(el)
  ;(el as any).__vue__ = { doLayout: doLayoutSpy }
  return el
}

/** 一个不带任何 doLayout 钩子的 .el-table（如 stub 或 jsdom 测试环境）*/
function mountBareElTable(): HTMLElement {
  const el = document.createElement('div')
  el.className = 'el-table'
  document.body.appendChild(el)
  return el
}

describe('useGlobalTableLayout', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  afterEach(() => {
    document.querySelectorAll('.el-table').forEach((el) => el.remove())
  })

  describe('relayoutElTableElement', () => {
    it('应通过 Vue 3 __vueParentComponent.exposed.doLayout 调用', () => {
      const spy = vi.fn()
      const el = mountFakeElTableV3(spy)
      const ok = relayoutElTableElement(el)
      expect(ok).toBe(true)
      expect(spy).toHaveBeenCalledTimes(1)
    })

    it('应回退到 proxy.doLayout（Options API 风格）', () => {
      const spy = vi.fn()
      const el = document.createElement('div')
      el.className = 'el-table'
      document.body.appendChild(el)
      ;(el as any).__vueParentComponent = {
        exposed: null,
        proxy: { doLayout: spy },
        parent: null,
      }
      expect(relayoutElTableElement(el)).toBe(true)
      expect(spy).toHaveBeenCalledTimes(1)
    })

    it('应回退到 Vue 2 __vue__.doLayout', () => {
      const spy = vi.fn()
      const el = mountFakeElTableV2(spy)
      expect(relayoutElTableElement(el)).toBe(true)
      expect(spy).toHaveBeenCalledTimes(1)
    })

    it('元素不带任何 doLayout 钩子时返回 false 且不抛异常', () => {
      const el = mountBareElTable()
      expect(() => relayoutElTableElement(el)).not.toThrow()
      expect(relayoutElTableElement(el)).toBe(false)
    })

    it('单个表 doLayout 抛异常时不影响整体流程', () => {
      const spy = vi.fn(() => {
        throw new Error('boom')
      })
      const el = mountFakeElTableV3(spy)
      // 失败应被吞掉并返回 false（继续向上回溯也找不到，最终 false）
      expect(() => relayoutElTableElement(el)).not.toThrow()
    })
  })

  describe('relayoutAllElTables', () => {
    it('应遍历 document 中所有 .el-table 并调用 doLayout', () => {
      const spy1 = vi.fn()
      const spy2 = vi.fn()
      const spy3 = vi.fn()
      mountFakeElTableV3(spy1)
      mountFakeElTableV3(spy2)
      mountFakeElTableV2(spy3)
      mountBareElTable() // 无 hook 的也存在

      const ok = relayoutAllElTables()

      expect(spy1).toHaveBeenCalledTimes(1)
      expect(spy2).toHaveBeenCalledTimes(1)
      expect(spy3).toHaveBeenCalledTimes(1)
      expect(ok).toBe(3) // 3 个成功调用，1 个 bare 静默跳过
    })

    it('页面无任何 el-table 时返回 0 不抛异常', () => {
      expect(() => relayoutAllElTables()).not.toThrow()
      expect(relayoutAllElTables()).toBe(0)
    })
  })

  describe('useGlobalTableLayout (watcher)', () => {
    it('字号切换后应触发所有 el-table 的 doLayout', async () => {
      const spy1 = vi.fn()
      const spy2 = vi.fn()
      mountFakeElTableV3(spy1)
      mountFakeElTableV3(spy2)

      withSetup(() => useGlobalTableLayout())
      const prefs = useDisplayPrefsStore()

      // 初始字号 sm，切换为 md
      prefs.setFontSize('md')
      await nextTick()
      // useGlobalTableLayout 内部用 nextTick，等一次让 watcher flush
      await nextTick()

      expect(spy1).toHaveBeenCalledTimes(1)
      expect(spy2).toHaveBeenCalledTimes(1)
    })

    it('字号未变化时不应调用 doLayout', async () => {
      const spy = vi.fn()
      mountFakeElTableV3(spy)

      withSetup(() => useGlobalTableLayout())
      const prefs = useDisplayPrefsStore()

      // 切换为当前值（sm → sm），watch 不会触发
      prefs.setFontSize(prefs.fontSize)
      await nextTick()
      await nextTick()

      expect(spy).not.toHaveBeenCalled()
    })

    it('多次切换字号应每次都触发 doLayout', async () => {
      const spy = vi.fn()
      mountFakeElTableV3(spy)

      withSetup(() => useGlobalTableLayout())
      const prefs = useDisplayPrefsStore()

      prefs.setFontSize('md')
      await nextTick(); await nextTick()
      prefs.setFontSize('lg')
      await nextTick(); await nextTick()
      prefs.setFontSize('xs')
      await nextTick(); await nextTick()

      expect(spy).toHaveBeenCalledTimes(3)
    })
  })
})
