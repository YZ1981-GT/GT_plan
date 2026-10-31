import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: http }))

import {
  creationDeniedMessage,
  grantProjectCreation,
  listProjectCreationGrants,
  revokeProjectCreationGrant,
} from '../projectCreationGrantApi'

describe('projectCreationGrantApi', () => {
  beforeEach(() => {
    http.get.mockReset()
    http.post.mockReset()
  })

  it('按经理筛选授权列表', async () => {
    const rows = [{ id: 'g-1' }]
    http.get.mockResolvedValue({ data: rows })
    await expect(listProjectCreationGrants('u-m')).resolves.toEqual(rows)
    expect(http.get).toHaveBeenCalledWith('/api/users/project-creation-grants', {
      params: { manager_user_id: 'u-m' },
    })
  })

  it('批量授权与撤销使用静态授权路由', async () => {
    http.post.mockResolvedValueOnce({ data: [{ id: 'g-1' }] })
    await grantProjectCreation('u-m', {
      company_codes: ['91110000300000000G'],
      valid_until: null,
      reason: '客户承接授权',
    })
    expect(http.post).toHaveBeenNthCalledWith(
      1,
      '/api/users/project-creation-grants/u-m',
      expect.objectContaining({ reason: '客户承接授权' }),
    )
    http.post.mockResolvedValueOnce({ data: { id: 'g-1', revoked: true } })
    await expect(revokeProjectCreationGrant('g-1', 3, '负责人调整')).resolves.toEqual({
      id: 'g-1', revoked: true,
    })
    expect(http.post).toHaveBeenNthCalledWith(
      2,
      '/api/users/project-creation-grants/g-1/revoke',
      { expected_version: 3, reason: '负责人调整' },
    )
  })

  it('建项被拒的原因：对象 / 字符串信封都取后端原文，取不到给兜底', () => {
    // 授权门的真实 403（http 拦截器已把 message 复制到 detail）
    const denied = { error_code: 'COMPANY_CREATION_NOT_AUTHORIZED', message: '有 1 个企业代码暂无建项授权，请联系管理员授权' }
    expect(creationDeniedMessage({ response: { status: 403, data: { code: 403, message: denied, detail: denied } } }))
      .toBe('有 1 个企业代码暂无建项授权，请联系管理员授权')
    // 拦截器未归一时只有 message
    expect(creationDeniedMessage({ response: { data: { message: denied } } }))
      .toBe('有 1 个企业代码暂无建项授权，请联系管理员授权')
    // 角色检查是字符串 detail
    expect(creationDeniedMessage({ response: { data: { detail: '  当前角色无项目创建权限 ' } } }))
      .toBe('当前角色无项目创建权限')
    expect(creationDeniedMessage({ response: { data: {} } })).toBe('没有建项权限，请联系管理员')
    expect(creationDeniedMessage(new Error('x'))).toBe('没有建项权限，请联系管理员')
  })
})
