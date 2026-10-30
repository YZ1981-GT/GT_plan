// 项目列表单飞 + 2秒微缓存 + mutation epoch 失效（R6.5）。
import fs from 'node:fs'
import path from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const get = vi.fn()
vi.mock('@/utils/http', () => ({ default: { get: (...args: unknown[]) => get(...args) } }))

import {
  PROJECT_LIST_CACHE_TTL_MS,
  _projectListQueryState,
  invalidateProjectListQuery,
  listProjectsShared,
} from '../projectListQuery'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

beforeEach(() => {
  vi.useRealTimers()
  get.mockReset()
  invalidateProjectListQuery()
})

describe('projectListQuery', () => {
  it('并发调用共享一条 HTTP，返回各自浅拷贝', async () => {
    const gate = deferred<any>()
    get.mockReturnValueOnce(gate.promise)
    const a = listProjectsShared()
    const b = listProjectsShared()
    expect(get).toHaveBeenCalledTimes(1)
    expect(get).toHaveBeenCalledWith('/api/projects')
    gate.resolve({ data: [{ id: 'p1', name: 'A' }] })
    const [ra, rb] = await Promise.all([a, b])
    expect(ra).toEqual(rb)
    expect(ra).not.toBe(rb)
    expect(ra[0]).not.toBe(rb[0])
  })

  it('完成后2秒内复用，过期后重取', async () => {
    expect(PROJECT_LIST_CACHE_TTL_MS).toBe(2_000)
    vi.useFakeTimers()
    get
      .mockResolvedValueOnce({ data: [{ id: 'p1' }] })
      .mockResolvedValueOnce({ data: [{ id: 'p2' }] })
    expect(await listProjectsShared()).toEqual([{ id: 'p1' }])
    expect(await listProjectsShared()).toEqual([{ id: 'p1' }])
    expect(get).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(PROJECT_LIST_CACHE_TTL_MS + 1)
    expect(await listProjectsShared()).toEqual([{ id: 'p2' }])
    expect(get).toHaveBeenCalledTimes(2)
    vi.useRealTimers()
  })

  it('带筛选参数不进共享缓存', async () => {
    get.mockResolvedValue({ data: [] })
    await listProjectsShared({ status: 'execution' })
    await listProjectsShared({ status: 'execution' })
    expect(get).toHaveBeenCalledTimes(2)
    expect(_projectListQueryState().cached).toBe(false)
  })

  it('mutation 失效后不加入旧在途，旧响应也不能回填新缓存', async () => {
    const oldGate = deferred<any>()
    const freshGate = deferred<any>()
    get.mockReturnValueOnce(oldGate.promise).mockReturnValueOnce(freshGate.promise)
    const oldRequest = listProjectsShared()
    invalidateProjectListQuery()
    const freshRequest = listProjectsShared()
    expect(get).toHaveBeenCalledTimes(2)
    // 新请求先返回并填入 fresh；旧请求最后到达也不得凭旧 epoch 覆盖它。
    freshGate.resolve({ data: [{ id: 'fresh' }] })
    expect(await freshRequest).toEqual([{ id: 'fresh' }])
    oldGate.resolve({ data: [{ id: 'old' }] })
    expect(await oldRequest).toEqual([{ id: 'old' }])
    expect(await listProjectsShared()).toEqual([{ id: 'fresh' }])
    expect(get).toHaveBeenCalledTimes(2)
  })

  it('失败不缓存，下一次可重试', async () => {
    get.mockRejectedValueOnce(new Error('down')).mockResolvedValueOnce({ data: [{ id: 'ok' }] })
    await expect(listProjectsShared()).rejects.toThrow('down')
    expect(await listProjectsShared()).toEqual([{ id: 'ok' }])
    expect(get).toHaveBeenCalledTimes(2)
  })
})

describe('项目 mutation 失效接线', () => {
  const ROOT = path.resolve(__dirname, '../../')
  const read = (rel: string) => fs.readFileSync(path.join(ROOT, rel), 'utf-8')

  it('Projects 与 Middle 读同一共享入口', () => {
    expect(read('views/Projects.vue')).toContain("import { listProjects } from '@/services/commonApi'")
    expect(read('services/commonApi.ts')).toContain('return listProjectsShared(params)')
    expect(read('components/layout/MiddleProjectList.vue')).toContain('projects.value = await listProjectsShared()')
  })

  it('创建/编辑/单删/批删/批量导入均失效', () => {
    const wizard = read('stores/wizard.ts')
    expect(wizard.match(/invalidateProjectListQuery\(\)/g)?.length).toBeGreaterThanOrEqual(2)
    const middle = read('components/layout/MiddleProjectList.vue')
    expect(middle).toContain('@success="onBatchImportSuccess"')
    expect(middle.match(/invalidateProjectListQuery\(\)/g)?.length).toBeGreaterThanOrEqual(3)
    const collaboration = read('services/collaborationApi.ts')
    expect(collaboration.match(/invalidateProjectListQuery\(\)/g)?.length).toBeGreaterThanOrEqual(3)
  })

  it('项目回收站恢复/永久删除/清空均失效', () => {
    const common = read('services/commonApi.ts')
    const block = common.slice(common.indexOf('export async function restoreRecycleBinItem'), common.indexOf('// ── 知识库'))
    expect(block.match(/invalidateProjectListQuery\(\)/g)?.length).toBe(3)
    expect(block).toContain("itemId.startsWith('project/')")
  })
})
