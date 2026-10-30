// roleContext 首屏只取有真实消费者的 /me（spec runtime-performance-and-reload-hardening-followup R6.2）。
//
// 🔴 判据来自现算而非推测：全仓没有任何组件读 store 的 navItems / homepageContent —— 所有 navItems
// 命中都是各底稿 / 布局组件自己的局部常量，homepageContent 只在本 store 内部出现（state / action /
// reset）。原 initialize() 并发拉 3 个端点，其中 2 条的结果没人消费却挡在首屏关键路径上
// （DefaultLayout 是唯一调用方且 await 它）。
//
// 这里既判「首屏只发 1 条」，也判「两个 action 仍可按需单独调用」（不是删能力，是移出首屏），
// 外加一条源码判据锁住 initialize 不得再并发那两个 action。
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const get = vi.fn()
vi.mock('@/utils/http', () => ({ default: { get: (...args: unknown[]) => get(...args) } }))

import { useRoleContextStore } from '../roleContext'

const ME = {
  system_role: 'manager',
  effective_role: 'manager',
  projects: [{ project_id: 'p1', project_name: 'P', client_name: 'C', role: 'manager', permission_level: 'edit' }],
}

beforeEach(() => {
  setActivePinia(createPinia())
  get.mockReset()
  get.mockImplementation((url: string) => {
    if (url === '/api/role-context/me') return Promise.resolve({ data: ME })
    if (url === '/api/role-context/me/nav') return Promise.resolve({ data: [{ key: 'k', label: 'L', icon: 'I', path: '/' }] })
    if (url === '/api/role-context/me/homepage') return Promise.resolve({ data: { role: 'manager', greeting_type: 'am', quick_actions: [], stats: {} } })
    return Promise.reject(new Error(`unexpected ${url}`))
  })
})

describe('roleContext.initialize', () => {
  it('首屏只请求 /me，不再拉 nav / homepage', async () => {
    const store = useRoleContextStore()
    await store.initialize()
    const urls = get.mock.calls.map((c) => c[0])
    expect(urls).toEqual(['/api/role-context/me'])
    expect(store.loaded).toBe(true)
    expect(store.effectiveRole).toBe('manager')
    expect(store.projects).toHaveLength(1)
  })

  it('nav / homepage 仍保留为按需 action（能力没删）', async () => {
    const store = useRoleContextStore()
    await store.loadNavItems()
    await store.loadHomepageContent()
    expect(get.mock.calls.map((c) => c[0])).toEqual([
      '/api/role-context/me/nav',
      '/api/role-context/me/homepage',
    ])
    expect(store.navItems).toHaveLength(1)
    expect(store.homepageContent?.role).toBe('manager')
  })

  it('/me 失败时 initialize 不抛，且仍只发 1 条请求', async () => {
    get.mockImplementation((url: string) => {
      if (url === '/api/role-context/me') return Promise.reject(new Error('500'))
      return Promise.resolve({ data: [] })
    })
    const store = useRoleContextStore()
    await expect(store.initialize()).resolves.toBeUndefined()
    expect(get.mock.calls.map((c) => c[0])).toEqual(['/api/role-context/me'])
    expect(store.loaded).toBe(true)
  })

  it('源码判据：initialize 体内不得再调 nav / homepage', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const source = fs.readFileSync(path.resolve(__dirname, '../roleContext.ts'), 'utf-8')
    const body = source.slice(source.indexOf('async initialize()'))
    const end = body.indexOf('reset()')
    const initializeBody = body.slice(0, end > 0 ? end : undefined)
    expect(initializeBody).toContain('loadGlobalContext')
    expect(initializeBody).not.toContain('loadNavItems')
    expect(initializeBody).not.toContain('loadHomepageContent')
  })
})
