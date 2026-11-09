/**
 * 批 7 任务 7.4：合并签字快照 API 契约（列表 / 创建 / 完整性还原 / 对比 / 下载）。
 * 锁定端点路径、参数、静默标记与 authed 下载助手调用。
 */
const { api, downloadFile } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  downloadFile: vi.fn(),
}))
vi.mock('@/services/apiProxy', () => ({ api }))
vi.mock('@/utils/http', () => ({ downloadFile }))

import {
  compareConsolSnapshot,
  createConsolSnapshot,
  downloadConsolSnapshot,
  listConsolSnapshots,
  restoreConsolSnapshot,
} from '@/services/consolidationApi'

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset())
  downloadFile.mockReset()
})

describe('合并快照 API 契约', () => {
  it('列表走基础 snapshots 路径，静默抑制全局 toast', async () => {
    api.get.mockResolvedValue([{ id: 's1', locked: true }])
    await expect(listConsolSnapshots('p1')).resolves.toHaveLength(1)
    expect(api.get).toHaveBeenCalledWith('/api/consolidation/p1/snapshots', { _silent: true })
  })

  it('创建默认 manual，带年度；签字用 sign reason', async () => {
    api.post.mockResolvedValue({ id: 's2' })
    await createConsolSnapshot('p1', { year: 2025 })
    expect(api.post).toHaveBeenLastCalledWith(
      '/api/consolidation/p1/snapshots', undefined,
      { params: { reason: 'manual', year: 2025 }, _silent: true },
    )
    await createConsolSnapshot('p1', { year: 2025, reason: 'sign' })
    expect(api.post).toHaveBeenLastCalledWith(
      '/api/consolidation/p1/snapshots', undefined,
      { params: { reason: 'sign', year: 2025 }, _silent: true },
    )
  })

  it('创建省略年度时不带 year 参数', async () => {
    api.post.mockResolvedValue({ id: 's3' })
    await createConsolSnapshot('p1', {})
    expect(api.post).toHaveBeenLastCalledWith(
      '/api/consolidation/p1/snapshots', undefined,
      { params: { reason: 'manual' }, _silent: true },
    )
  })

  it('完整性还原 / 对比走各自子路径', async () => {
    api.get.mockResolvedValue({ hash_valid: true })
    await restoreConsolSnapshot('p1', 's1')
    expect(api.get).toHaveBeenLastCalledWith('/api/consolidation/p1/snapshots/s1/restore', { _silent: true })
    await compareConsolSnapshot('p1', 's1')
    expect(api.get).toHaveBeenLastCalledWith('/api/consolidation/p1/snapshots/s1/compare', { _silent: true })
  })

  it('下载走 authed 下载助手（GET + 文件名 + silent），不经 iframe/原生导航', async () => {
    downloadFile.mockResolvedValue(undefined)
    await downloadConsolSnapshot('p1', 'snapshot-abcdef12', 2025)
    expect(downloadFile).toHaveBeenCalledWith(
      '/api/consolidation/p1/snapshots/snapshot-abcdef12/download',
      { method: 'get', fileName: 'consol-snapshot-2025-snapshot.json', silent: true },
    )
  })
})
