/**
 * useAcnrCatalogIndex — 单元测试（Task 25.4 / P23 支撑单测）
 *
 * 验证 catalog 索引构建与降级：
 * - listSheets 返回条目 → 正确构建 Map<sheet_code,{sheet_name,addr_id,order}>
 * - order 优先取 import_export.import_order，缺失回退列表位置索引
 * - 缺 sheet_code 的条目跳过
 * - listSheets 抛异常 / 返回空数组 → 空 Map（调用方回退硬编码，Req 18.7）
 * - loading 状态在加载前后正确切换
 *
 * Validates: Requirements 18.1, 18.7
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// ─── 用 vi.hoisted 让 mock 变量在 vi.mock 工厂内可用 ───
const { mockListSheets } = vi.hoisted(() => ({
  mockListSheets: vi.fn(),
}))

vi.mock('@/services/acnr/useAcnr', () => ({
  useAcnr: () => ({
    listSheets: mockListSheets,
  }),
}))

import { useAcnrCatalogIndex } from '../useAcnrCatalogIndex'

function sheet(overrides: Record<string, any> = {}) {
  return {
    addr_id: 'D2/D2-2/_sheet',
    domain: 'wp',
    cycle: 'D',
    parent_wp_code: 'D2',
    sheet_code: 'D2-2',
    sheet_name: '应收账款明细表',
    ...overrides,
  }
}

describe('useAcnrCatalogIndex — catalog 索引构建', () => {
  beforeEach(() => {
    mockListSheets.mockReset()
  })

  it('从 listSheets 条目构建 Map（sheet_name/addr_id/order）', async () => {
    mockListSheets.mockResolvedValue([
      sheet({
        sheet_code: 'D2A',
        sheet_name: '应收账款实质性程序表',
        addr_id: 'D2/D2A/_sheet',
        import_export: { enabled: true, import_order: 5 },
      }),
      sheet({
        sheet_code: 'D2-1',
        sheet_name: '应收账款审定表',
        addr_id: 'D2/D2-1/_sheet',
        import_export: { enabled: true, import_order: 7 },
      }),
    ])

    const { loadCatalogIndex } = useAcnrCatalogIndex()
    const map = await loadCatalogIndex('D')

    expect(mockListSheets).toHaveBeenCalledWith('D')
    expect(map.size).toBe(2)
    expect(map.get('D2A')).toEqual({
      sheet_name: '应收账款实质性程序表',
      addr_id: 'D2/D2A/_sheet',
      order: 5,
    })
    expect(map.get('D2-1')).toEqual({
      sheet_name: '应收账款审定表',
      addr_id: 'D2/D2-1/_sheet',
      order: 7,
    })
  })

  it('order 缺失 import_order 时回退列表位置索引', async () => {
    mockListSheets.mockResolvedValue([
      sheet({ sheet_code: 'D2A', sheet_name: 'A', addr_id: 'D2/D2A/_sheet' }),
      sheet({ sheet_code: 'D2-1', sheet_name: 'B', addr_id: 'D2/D2-1/_sheet' }),
      sheet({
        sheet_code: 'D2-2',
        sheet_name: 'C',
        addr_id: 'D2/D2-2/_sheet',
        import_export: { enabled: true, import_order: 99 },
      }),
    ])

    const { loadCatalogIndex } = useAcnrCatalogIndex()
    const map = await loadCatalogIndex('D')

    // 无 import_order → 位置索引 0 / 1
    expect(map.get('D2A')?.order).toBe(0)
    expect(map.get('D2-1')?.order).toBe(1)
    // 有 import_order → 采用之
    expect(map.get('D2-2')?.order).toBe(99)
  })

  it('sheet_name 为空时用 sheet_code 兜底', async () => {
    mockListSheets.mockResolvedValue([
      sheet({ sheet_code: 'D2-9', sheet_name: '', addr_id: 'D2/D2-9/_sheet' }),
    ])
    const { loadCatalogIndex } = useAcnrCatalogIndex()
    const map = await loadCatalogIndex('D')
    expect(map.get('D2-9')?.sheet_name).toBe('D2-9')
  })

  it('缺 sheet_code 的条目被跳过', async () => {
    mockListSheets.mockResolvedValue([
      sheet({ sheet_code: '', sheet_name: '无编码' }),
      { sheet_name: '无字段' } as any,
      sheet({ sheet_code: 'D2-3', sheet_name: '坏账准备明细表', addr_id: 'D2/D2-3/_sheet' }),
    ])
    const { loadCatalogIndex } = useAcnrCatalogIndex()
    const map = await loadCatalogIndex('D')
    expect(map.size).toBe(1)
    expect(map.has('D2-3')).toBe(true)
  })

  it('listSheets 抛异常 → 空 Map（降级回退，Req 18.7）', async () => {
    mockListSheets.mockRejectedValue(new Error('network'))
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const { loadCatalogIndex, catalogIndex } = useAcnrCatalogIndex()
    const map = await loadCatalogIndex('D')

    expect(map.size).toBe(0)
    expect(catalogIndex.value.size).toBe(0)
    warnSpy.mockRestore()
  })

  it('listSheets 返回空数组 → 空 Map', async () => {
    mockListSheets.mockResolvedValue([])
    const { loadCatalogIndex } = useAcnrCatalogIndex()
    const map = await loadCatalogIndex('D')
    expect(map.size).toBe(0)
  })

  it('loading 在加载前后正确切换', async () => {
    let resolveFn: (v: any) => void = () => {}
    mockListSheets.mockReturnValue(
      new Promise((res) => {
        resolveFn = res
      }),
    )
    const { loading, loadCatalogIndex } = useAcnrCatalogIndex()

    expect(loading.value).toBe(false)
    const p = loadCatalogIndex('D')
    expect(loading.value).toBe(true)
    resolveFn([])
    await p
    expect(loading.value).toBe(false)
  })

  it('不传 cycle 时透传 undefined（加载所有循环）', async () => {
    mockListSheets.mockResolvedValue([])
    const { loadCatalogIndex } = useAcnrCatalogIndex()
    await loadCatalogIndex()
    expect(mockListSheets).toHaveBeenCalledWith(undefined)
  })
})
