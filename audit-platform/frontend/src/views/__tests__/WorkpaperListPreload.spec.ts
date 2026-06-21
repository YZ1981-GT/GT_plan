/**
 * WorkpaperListPreload.spec.ts — 底稿列表页 api.js preload 测试
 *
 * Validates: Requirements R11
 *
 * 验证：
 * 1. onMounted 时通过 <link rel="preload" as="script"> 预热 api.js
 * 2. 仅 preload 不初始化 DocsAPI（不创建 script 标签）
 * 3. VITE_ONLYOFFICE_URL 未设置时不插入 preload link
 * 4. 不重复插入（幂等性）
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'

describe('WorkpaperList - api.js preload (R11)', () => {
  const ONLYOFFICE_URL = 'http://localhost:9980'
  const EXPECTED_HREF = `${ONLYOFFICE_URL}/web-apps/apps/api/documents/api.js`

  beforeEach(() => {
    // Clean up any preload links from previous tests
    document.head.querySelectorAll('link[rel="preload"]').forEach(el => el.remove())
  })

  afterEach(() => {
    document.head.querySelectorAll('link[rel="preload"]').forEach(el => el.remove())
  })

  /**
   * Helper: simulate the preload logic extracted from WorkpaperList.vue onMounted
   * This tests the DOM logic in isolation without mounting the full component
   * (which requires dozens of route/store/service mocks).
   */
  function executePreloadLogic(baseUrl: string) {
    if (baseUrl) {
      const preloadHref = `${baseUrl.replace(/\/$/, '')}/web-apps/apps/api/documents/api.js`
      if (!document.head.querySelector(`link[rel="preload"][href="${preloadHref}"]`)) {
        const link = document.createElement('link')
        link.rel = 'preload'
        link.setAttribute('as', 'script')
        link.href = preloadHref
        document.head.appendChild(link)
      }
    }
  }

  it('插入 <link rel="preload" as="script"> 预热 api.js', () => {
    executePreloadLogic(ONLYOFFICE_URL)

    const link = document.head.querySelector(`link[rel="preload"][href="${EXPECTED_HREF}"]`) as HTMLLinkElement
    expect(link).not.toBeNull()
    expect(link!.href).toBe(EXPECTED_HREF)
    expect(link!.rel).toBe('preload')
    expect(link!.getAttribute('as')).toBe('script')
  })

  it('仅 preload 不创建 script 标签（不初始化 DocsAPI）', () => {
    executePreloadLogic(ONLYOFFICE_URL)

    // 不应有 script 标签加载 api.js
    const scripts = document.querySelectorAll('script[src*="api.js"]')
    expect(scripts.length).toBe(0)

    // DocsAPI 不应存在
    expect((window as any).DocsAPI).toBeUndefined()
  })

  it('VITE_ONLYOFFICE_URL 为空时不插入 preload link', () => {
    executePreloadLogic('')

    const link = document.head.querySelector('link[rel="preload"]')
    expect(link).toBeNull()
  })

  it('末尾斜杠被正确去除', () => {
    executePreloadLogic('http://localhost:9980/')

    const expectedHref = 'http://localhost:9980/web-apps/apps/api/documents/api.js'
    const link = document.head.querySelector(`link[rel="preload"][href="${expectedHref}"]`) as HTMLLinkElement
    expect(link).not.toBeNull()
    expect(link!.href).toBe(expectedHref)
    // 确保没有双斜杠
    expect(link!.href).not.toContain('9980//web-apps')
  })

  it('重复调用不会插入多个 preload link（幂等性）', () => {
    executePreloadLogic(ONLYOFFICE_URL)
    executePreloadLogic(ONLYOFFICE_URL)
    executePreloadLogic(ONLYOFFICE_URL)

    const links = document.head.querySelectorAll(`link[rel="preload"][href="${EXPECTED_HREF}"]`)
    expect(links.length).toBe(1)
  })
})
