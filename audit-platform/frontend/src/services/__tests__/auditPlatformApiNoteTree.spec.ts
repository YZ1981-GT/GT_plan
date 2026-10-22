/**
 * getDisclosureNoteTree 把调用方的请求配置传给 http（spec formula-governance-coverage-closure R5 走查）：
 * 原先只收两个参数，公式管理中心 / AI 采纳目标传的 `{ _silent: true }` 被丢弃 ⇒ 附注未生成的项目每次都弹全局错误。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get, post: vi.fn(), put: vi.fn(), delete: vi.fn() } }))

import { getDisclosureNoteTree } from '../auditPlatformApi'

describe('getDisclosureNoteTree', () => {
  beforeEach(() => { get.mockReset(); get.mockResolvedValue({ data: [{ note_section: '五、1' }] }) })

  it('第三参原样传给 http.get（静默由调用方决定）', async () => {
    const rows = await getDisclosureNoteTree('p1', 2025, { _silent: true } as any)
    expect(get).toHaveBeenCalledWith('/api/disclosure-notes/p1/2025', { _silent: true })
    expect(rows).toEqual([{ note_section: '五、1' }])
  })

  it('不传配置时与原先一致', async () => {
    await getDisclosureNoteTree('p1', 2025)
    expect(get).toHaveBeenCalledWith('/api/disclosure-notes/p1/2025', undefined)
  })
})
