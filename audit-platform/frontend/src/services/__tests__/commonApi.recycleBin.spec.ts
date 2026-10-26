/**
 * 回收站恢复 / 永久删除 / 清空带 _silent（spec procedure-trim-generation-delegation-chain 任务 22 浏览器实测发现）：
 * 回收站页自己用 handleApiError 提示失败原因；原先请求不带 _silent，全局拦截器先弹一次 ⇒ 恢复仍在程序裁剪中
 * 标为不执行的底稿（409）时同一句话提示两遍。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ put: vi.fn(), post: vi.fn(), get: vi.fn(), delete: vi.fn(), patch: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: http }))

import { emptyRecycleBin, permanentDeleteItem, restoreRecycleBinItem } from '../commonApi'

beforeEach(() => {
  vi.clearAllMocks()
  http.post.mockResolvedValue({ data: { message: 'ok' } })
  http.delete.mockResolvedValue({ data: { message: 'ok' } })
})

describe('回收站操作请求', () => {
  it('恢复：POST 恢复地址、不带请求体、_silent', async () => {
    expect(await restoreRecycleBinItem('working_paper/w1')).toEqual({ message: 'ok' })
    expect(http.post).toHaveBeenCalledWith('/api/recycle-bin/working_paper/w1/restore', null, { _silent: true })
  })

  it('永久删除：DELETE、_silent', async () => {
    await permanentDeleteItem('attachment/a1')
    expect(http.delete).toHaveBeenCalledWith('/api/recycle-bin/attachment/a1', { _silent: true })
  })

  it('清空：POST 清空地址、_silent', async () => {
    await emptyRecycleBin()
    expect(http.post).toHaveBeenCalledWith('/api/recycle-bin/empty', null, { _silent: true })
  })
})
