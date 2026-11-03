/**
 * openWorkpaperCell（spec wp-deeplink-locate-coverage-closure 需求 3.1 / 3.3）：
 * UUID 直接用；编码经 wp-id-by-code 取实例；sheet 级编码没有独立底稿时回落父底稿并把原编码当 sheet；取不到给中文原因。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { resolveMock } = vi.hoisted(() => ({ resolveMock: vi.fn() }))
vi.mock('../resolveWorkpaperByCode', () => ({ resolveWorkpaperByCode: resolveMock }))
vi.mock('@/composables/useWorkpaperNavigation', () => ({
  workpaperEditorRoute: (projectId: string, wpId: string, query?: Record<string, string>) =>
    (query ? { name: 'WorkpaperEditor', params: { projectId, wpId }, query } : { name: 'WorkpaperEditor', params: { projectId, wpId } }),
}))

import { OPEN_WORKPAPER_MESSAGES, openWorkpaperCell, workpaperCellQuery } from '../openWorkpaperCell'

const PID = 'p-1'
const WP = '8c8cd491-2d21-48ce-9622-e2d9bca0d499'

function router() {
  return { push: vi.fn().mockResolvedValue(undefined) }
}

beforeEach(() => { resolveMock.mockReset() })

describe('openWorkpaperCell', () => {
  it('wpId 是 UUID：不查编码，直接打开编辑器并带 ?sheet=&cell=', async () => {
    const r = router()
    expect(await openWorkpaperCell(r, { projectId: PID, wpId: WP, wpCode: 'E1', sheet: 'E1-14', cell: 'C16' })).toBeNull()
    expect(resolveMock).not.toHaveBeenCalled()
    expect(r.push).toHaveBeenCalledWith({ name: 'WorkpaperEditor', params: { projectId: PID, wpId: WP }, query: { sheet: 'E1-14', cell: 'C16' } })
  })

  it('wpId 不是 UUID（溯源节点把编码放在 wp_code）：按编码取本项目实例', async () => {
    resolveMock.mockResolvedValueOnce({ wpId: WP })
    const r = router()
    expect(await openWorkpaperCell(r, { projectId: PID, wpId: 'E1', wpCode: 'E1', cell: 'A50' })).toBeNull()
    expect(resolveMock).toHaveBeenCalledWith(PID, 'E1', true)
    expect(r.push.mock.calls[0][0]).toMatchObject({ params: { wpId: WP }, query: { cell: 'A50' } })
  })

  it('sheet 级编码没有独立底稿：回落父底稿，原编码作 sheet（已给 sheet 时不覆盖）', async () => {
    resolveMock.mockResolvedValueOnce(null).mockResolvedValueOnce({ wpId: WP })
    const r = router()
    expect(await openWorkpaperCell(r, { projectId: PID, wpCode: 'D2-1', cell: 'B5' })).toBeNull()
    expect(resolveMock.mock.calls.map((c) => c[1])).toEqual(['D2-1', 'D2'])
    expect(r.push.mock.calls[0][0].query).toEqual({ sheet: 'D2-1', cell: 'B5' })

    resolveMock.mockReset()
    resolveMock.mockResolvedValueOnce(null).mockResolvedValueOnce({ wpId: WP })
    const r2 = router()
    await openWorkpaperCell(r2, { projectId: PID, wpCode: 'D2-1', sheet: '明细表D2-1', cell: 'B5' })
    expect(r2.push.mock.calls[0][0].query).toEqual({ sheet: '明细表D2-1', cell: 'B5' })
  })

  it('取不到底稿 / 缺编码 / 缺项目：返回中文原因，不跳转', async () => {
    resolveMock.mockResolvedValue(null)
    const r = router()
    expect(await openWorkpaperCell(r, { projectId: PID, wpCode: 'Z9' })).toBe(OPEN_WORKPAPER_MESSAGES.notFound('Z9'))
    expect(await openWorkpaperCell(r, { projectId: PID })).toBe(OPEN_WORKPAPER_MESSAGES.noCode)
    expect(await openWorkpaperCell(r, { projectId: '', wpId: WP })).toBe(OPEN_WORKPAPER_MESSAGES.noProject)
    expect(r.push).not.toHaveBeenCalled()
  })

  it('workpaperCellQuery：空值不带', () => {
    expect(workpaperCellQuery({ sheet: ' ', cell: null })).toBeUndefined()
    expect(workpaperCellQuery({ sheet: 'E1-14' })).toEqual({ sheet: 'E1-14' })
  })
})
