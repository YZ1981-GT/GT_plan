/**
 * 认证守卫等新标签页的会话接力（spec attachment-confirmation-evidence-loop 浏览器走查实测）
 *
 * 地址栏 / noopener 新开的标签页没有 sessionStorage 里的令牌，启动时向已登录标签页要会话（最多约 2 秒）。
 * 原先 main.ts 挂载与要会话并行：首个导航在回执到达前就被守卫送去登录页，回执到了也停在登录页。
 * 断言：守卫在判「未登录」前等接力结束；接力没拿到会话才跳登录页。另守 main.ts 在 app.use(router) 之前发起接力。
 * 观测方式：在真实守卫之后再挂一个守卫，记下目标并取消导航（不加载页面组件）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('nprogress', () => ({ default: { start: vi.fn(), done: vi.fn(), configure: vi.fn() } }))

let handoff: Promise<void> = Promise.resolve()
vi.mock('@/utils/crossWindowAuth', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/utils/crossWindowAuth')>()),
  awaitSessionHandoff: () => handoff,
}))

import router from '@/router'
import { useAuthStore } from '@/stores/auth'

const seen: string[] = []
router.beforeEach((to) => {
  seen.push(to.fullPath)
  return false
})

beforeEach(() => {
  sessionStorage.clear()
  setActivePinia(createPinia())
  seen.length = 0
})

describe('认证守卫等会话接力', () => {
  it('接力拿到会话：不跳登录页，按原目标继续', async () => {
    const auth = useAuthStore()
    handoff = new Promise((r) => setTimeout(() => { auth.token = 'from-other-tab'; r() }, 30))
    await router.push('/')
    expect(seen).toEqual(['/'])
  })

  it('接力没拿到会话：跳登录页并带回跳地址', async () => {
    handoff = new Promise((r) => setTimeout(r, 30))
    await router.push('/')
    expect(seen).toEqual(['/login?redirect=/'])
  })

  it('main.ts 在 app.use(router) 之前发起接力', () => {
    const main = readFileSync(resolve(__dirname, '../../main.ts'), 'utf-8')
    const start = main.search(/^startSessionHandoff\(/m) // 行首语句（注释里也会提到这两个名字）
    const useRouter = main.search(/^app\.use\(router\)/m)
    expect(start).toBeGreaterThan(0)
    expect(useRouter).toBeGreaterThan(start)
    expect(main).not.toMatch(/\bawait requestSession\(/) // 旧的并行 IIFE 已删
  })
})
