/**
 * useLazySheetLoader.spec.ts — proposal-remaining-18 task 0.4 (D-1)
 *
 * 验证 D-1 大底稿懒加载 composable：
 * - markAllInitialLoaded: 仅标记非 _lazy 的 sheet 为已加载
 * - ensureSheetLoaded: 调 GET /sheet/{name} 拉取并注入 Univer
 * - 重复切换不重复 fetch（缓存 + 并发去重）
 * - sheet 不存在时返回 false 不抛错
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock httpApi before composable import
vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn(),
  },
}))

import httpApi from '@/utils/http'
import { useLazySheetLoader } from '../useLazySheetLoader'

const mockHttpGet = httpApi.get as unknown as ReturnType<typeof vi.fn>

beforeEach(() => {
  mockHttpGet.mockReset()
})

function buildMockUniverAPI(sheetNames: string[]) {
  const setValuesMock = vi.fn()
  const sheets = sheetNames.map((name) => ({
    _name: name,
    getRange: vi.fn(() => ({
      setValues: setValuesMock,
      merge: vi.fn(),
    })),
    setFreeze: vi.fn(),
  }))
  const wb = {
    getSheetByName: vi.fn((n: string) => sheets.find((s) => s._name === n) || null),
  }
  return {
    api: {
      getActiveWorkbook: () => wb,
    },
    setValuesMock,
    sheets,
  }
}

describe('useLazySheetLoader — markAllInitialLoaded', () => {
  it('标记所有非 _lazy sheet 为已加载（active sheet 完整加载场景）', () => {
    const loader = useLazySheetLoader({ projectId: () => 'p1', wpId: () => 'w1' })
    const workbookData = {
      sheets: {
        sheet0: { name: 'Sheet_0', custom: {} },  // 完整加载
        sheet1: { name: 'Sheet_1', custom: { _lazy: true } },  // 懒加载
        sheet2: { name: 'Sheet_2', custom: { _lazy: true } },
      },
    }
    loader.markAllInitialLoaded(workbookData)
    expect(loader.isLoaded('Sheet_0')).toBe(true)
    expect(loader.isLoaded('Sheet_1')).toBe(false)
    expect(loader.isLoaded('Sheet_2')).toBe(false)
  })

  it('全量数据场景：所有 sheet 都标记为已加载', () => {
    const loader = useLazySheetLoader({ projectId: () => 'p1', wpId: () => 'w1' })
    const workbookData = {
      sheets: {
        sheet0: { name: 'Sheet_0' },
        sheet1: { name: 'Sheet_1' },
      },
    }
    loader.markAllInitialLoaded(workbookData)
    expect(loader.isLoaded('Sheet_0')).toBe(true)
    expect(loader.isLoaded('Sheet_1')).toBe(true)
  })

  it('空 / 损坏的 workbookData 不抛错', () => {
    const loader = useLazySheetLoader({ projectId: () => 'p1', wpId: () => 'w1' })
    expect(() => loader.markAllInitialLoaded(null)).not.toThrow()
    expect(() => loader.markAllInitialLoaded({})).not.toThrow()
    expect(() => loader.markAllInitialLoaded({ sheets: {} })).not.toThrow()
  })
})

describe('useLazySheetLoader — ensureSheetLoaded', () => {
  it('未加载 sheet 触发 GET /sheet/{name} 并注入 Univer cellData', async () => {
    mockHttpGet.mockResolvedValueOnce({
      id: 'sheet1',
      name: 'Sheet_1',
      cellData: {
        '0': { '0': { v: 'X' }, '1': { v: 'Y' } },
        '1': { '0': { v: 'Z' } },
      },
    })
    const loader = useLazySheetLoader({ projectId: () => 'p1', wpId: () => 'w1' })
    const { api, setValuesMock } = buildMockUniverAPI(['Sheet_0', 'Sheet_1'])

    const ok = await loader.ensureSheetLoaded('Sheet_1', api)

    expect(ok).toBe(true)
    expect(mockHttpGet).toHaveBeenCalledTimes(1)
    expect(mockHttpGet).toHaveBeenCalledWith(
      '/api/projects/p1/workpapers/w1/template-file/sheet/Sheet_1',
    )
    // setValues 被调用：传入 2x2 cellData 矩阵
    expect(setValuesMock).toHaveBeenCalledTimes(1)
    const matrix = setValuesMock.mock.calls[0][0]
    expect(matrix.length).toBe(2)
    expect(matrix[0][0]?.v).toBe('X')
    expect(matrix[0][1]?.v).toBe('Y')
    expect(matrix[1][0]?.v).toBe('Z')
    // 标记为已加载
    expect(loader.isLoaded('Sheet_1')).toBe(true)
  })

  it('重复切换同一 sheet 不重复 fetch（缓存命中）', async () => {
    mockHttpGet.mockResolvedValueOnce({
      id: 'sheet1',
      name: 'Sheet_1',
      cellData: { '0': { '0': { v: 'first' } } },
    })
    const loader = useLazySheetLoader({ projectId: () => 'p1', wpId: () => 'w1' })
    const { api } = buildMockUniverAPI(['Sheet_0', 'Sheet_1'])

    await loader.ensureSheetLoaded('Sheet_1', api)
    await loader.ensureSheetLoaded('Sheet_1', api)
    await loader.ensureSheetLoaded('Sheet_1', api)

    // 三次切换只触发一次 fetch
    expect(mockHttpGet).toHaveBeenCalledTimes(1)
  })

  it('并发触发同一 sheet 加载也只 fetch 一次（inflight 去重）', async () => {
    let resolver: (data: any) => void = () => {}
    mockHttpGet.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolver = resolve
        }),
    )
    const loader = useLazySheetLoader({ projectId: () => 'p1', wpId: () => 'w1' })
    const { api } = buildMockUniverAPI(['Sheet_0', 'Sheet_1'])

    const p1 = loader.ensureSheetLoaded('Sheet_1', api)
    const p2 = loader.ensureSheetLoaded('Sheet_1', api)
    const p3 = loader.ensureSheetLoaded('Sheet_1', api)

    resolver({ id: 'sheet1', name: 'Sheet_1', cellData: { '0': { '0': { v: 'a' } } } })
    await Promise.all([p1, p2, p3])

    expect(mockHttpGet).toHaveBeenCalledTimes(1)
  })

  it('已 markAllInitialLoaded 的 sheet 切换时不 fetch', async () => {
    const loader = useLazySheetLoader({ projectId: () => 'p1', wpId: () => 'w1' })
    loader.markAllInitialLoaded({
      sheets: { sheet0: { name: 'Sheet_0' } },  // 标记 Sheet_0 为已加载
    })
    const { api } = buildMockUniverAPI(['Sheet_0'])

    const ok = await loader.ensureSheetLoaded('Sheet_0', api)
    expect(ok).toBe(false)  // 跳过 fetch，返回 false
    expect(mockHttpGet).not.toHaveBeenCalled()
  })

  it('网络错误时返回 false 不抛错（UI 保持空白态）', async () => {
    mockHttpGet.mockRejectedValueOnce(new Error('500'))
    const loader = useLazySheetLoader({ projectId: () => 'p1', wpId: () => 'w1' })
    const { api } = buildMockUniverAPI(['Sheet_0', 'Sheet_1'])

    const ok = await loader.ensureSheetLoaded('Sheet_1', api)
    expect(ok).toBe(false)
    // 失败的 sheet 未标记为 loaded（允许后续重试）
    expect(loader.isLoaded('Sheet_1')).toBe(false)
  })

  it('Univer 找不到对应 sheet 时不崩溃（best-effort 注入）', async () => {
    mockHttpGet.mockResolvedValueOnce({
      id: 'sheet99',
      name: 'NotInUniver',
      cellData: { '0': { '0': { v: 'x' } } },
    })
    const loader = useLazySheetLoader({ projectId: () => 'p1', wpId: () => 'w1' })
    const { api } = buildMockUniverAPI(['Sheet_0'])  // 不含 NotInUniver

    const ok = await loader.ensureSheetLoaded('NotInUniver', api)
    expect(ok).toBe(true)  // fetch 成功
    expect(loader.isLoaded('NotInUniver')).toBe(true)
  })

  it('空 sheetName 直接返回 false', async () => {
    const loader = useLazySheetLoader({ projectId: () => 'p1', wpId: () => 'w1' })
    const { api } = buildMockUniverAPI(['Sheet_0'])
    const ok = await loader.ensureSheetLoaded('', api)
    expect(ok).toBe(false)
    expect(mockHttpGet).not.toHaveBeenCalled()
  })

  it('fetchCount 计数正确累加', async () => {
    mockHttpGet
      .mockResolvedValueOnce({ name: 'A', cellData: { '0': { '0': { v: 1 } } } })
      .mockResolvedValueOnce({ name: 'B', cellData: { '0': { '0': { v: 2 } } } })
    const loader = useLazySheetLoader({ projectId: () => 'p1', wpId: () => 'w1' })
    const { api } = buildMockUniverAPI(['A', 'B'])
    await loader.ensureSheetLoaded('A', api)
    await loader.ensureSheetLoaded('B', api)
    await loader.ensureSheetLoaded('A', api)  // 缓存命中，不增加
    expect(loader.fetchCount.value).toBe(2)
  })
})
