import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: http }))

import {
  bindStaffToUser,
  listStaffBindings,
  searchUnboundStaff,
  unbindStaffFromUser,
} from '../staffBindingApi'

describe('staffBindingApi', () => {
  beforeEach(() => {
    http.get.mockReset()
    http.post.mockReset()
  })

  it('读取绑定列表；返回体不是数组时按空列表', async () => {
    const rows = [{ user_id: 'u-m', staff_id: 's-m' }]
    http.get.mockResolvedValueOnce({ data: rows })
    await expect(listStaffBindings()).resolves.toEqual(rows)
    expect(http.get).toHaveBeenCalledWith('/api/users/staff-bindings')

    http.get.mockResolvedValueOnce({ data: null })
    await expect(listStaffBindings()).resolves.toEqual([])
  })

  it('绑定与解除都带档案 id（解除按当前档案校验，防止误解他人的新绑定）', async () => {
    http.post.mockResolvedValueOnce({ data: { changed: true, project_count: 1 } })
    await expect(bindStaffToUser('u-m', 's-m')).resolves.toEqual({ changed: true, project_count: 1 })
    expect(http.post).toHaveBeenNthCalledWith(1, '/api/users/u-m/staff-binding', { staff_id: 's-m' })

    http.post.mockResolvedValueOnce({ data: { changed: true } })
    await unbindStaffFromUser('u-m', 's-m')
    expect(http.post).toHaveBeenNthCalledWith(2, '/api/users/u-m/staff-binding/unbind', { staff_id: 's-m' })
  })

  it('搜索只取未绑定档案、去掉离职人员；空关键字不传 search', async () => {
    http.get.mockResolvedValueOnce({
      data: {
        items: [
          { id: 's-1', name: '王经理', status: 'active' },
          { id: 's-2', name: '王离职', status: 'resigned' },
        ],
        total: 2,
      },
    })
    await expect(searchUnboundStaff('  王 ')).resolves.toEqual([{ id: 's-1', name: '王经理', status: 'active' }])
    expect(http.get).toHaveBeenLastCalledWith('/api/staff', {
      params: { search: '王', unbound_only: true, limit: 20 },
    })

    http.get.mockResolvedValueOnce({ data: {} })
    await expect(searchUnboundStaff('')).resolves.toEqual([])
    expect(http.get).toHaveBeenLastCalledWith('/api/staff', {
      params: { search: undefined, unbound_only: true, limit: 20 },
    })
  })
})
