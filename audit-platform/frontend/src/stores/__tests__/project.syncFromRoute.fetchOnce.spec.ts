/**
 * 项目 store 切换项目时只取一次项目详情（spec procedure-chain-hardening-and-java-contracts R16）。
 *
 * 原先路由没带年度时先取一次只为年度、再整份取一次：同一项目连发两条 /api/projects/{id}（顺序发出，在途共享也合并不了）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const getProject = vi.fn()
vi.mock('@/services/auditPlatformApi', () => ({ getProject: (...a: unknown[]) => getProject(...a) }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn().mockResolvedValue({ years: [] }) } }))
vi.mock('@/utils/eventBus', () => ({ eventBus: { emit: vi.fn() } }))

import { useProjectStore } from '@/stores/project'

const route = (pid: string, query: Record<string, string> = {}) => ({ params: { projectId: pid }, query }) as any

beforeEach(() => {
  setActivePinia(createPinia())
  getProject.mockReset()
})

describe('syncFromRoute', () => {
  it('路由没带年度：切换项目只取一次，年度与项目信息都来自这一次', async () => {
    getProject.mockResolvedValue({ client_name: '【测试】甲', status: 'active', audit_year: 2025 })
    const store = useProjectStore()
    await store.syncFromRoute(route('p1'))
    expect(getProject).toHaveBeenCalledTimes(1)
    expect(store.year).toBe(2025)
    expect(store.auditYear).toBe(2025)
    expect(store.clientName).toBe('【测试】甲')
    expect(store.projectStatus).toBe('active')
  })

  it('路由带年度：同样只取一次（只为项目信息），年度用路由的', async () => {
    getProject.mockResolvedValue({ client_name: '【测试】乙', audit_year: 2025 })
    const store = useProjectStore()
    await store.syncFromRoute(route('p2', { year: '2024' }))
    expect(getProject).toHaveBeenCalledTimes(1)
    expect(store.year).toBe(2024)
    expect(store.clientName).toBe('【测试】乙')
  })

  it('取年度那一次失败：加载项目信息时再取一次（与原来同样两次机会）', async () => {
    getProject.mockRejectedValueOnce(new Error('HTTP 500')).mockResolvedValueOnce({ client_name: '【测试】丙', audit_year: 2025 })
    const store = useProjectStore()
    await store.syncFromRoute(route('p3'))
    expect(getProject).toHaveBeenCalledTimes(2)
    expect(store.clientName).toBe('【测试】丙')
    expect(store.year).toBe(2025)
  })

  it('同一项目再次同步：不再取', async () => {
    getProject.mockResolvedValue({ client_name: '【测试】甲', audit_year: 2025 })
    const store = useProjectStore()
    await store.syncFromRoute(route('p1'))
    await store.syncFromRoute(route('p1'))
    expect(getProject).toHaveBeenCalledTimes(1)
  })
})
