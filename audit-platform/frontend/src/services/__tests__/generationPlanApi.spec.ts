/** 生成计划 API 写入恰好一次与 confirmations 强制新读（spec trim-generation-plan-linkage 复盘）。 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: mocks }))

import {
  generateWorkpapers, getGenerationOperation, getScopeConfirmations, listGenerationTemplateSets, planErrorText,
  runGenerationOperation,
} from '@/services/generationPlanApi'

describe('generationPlanApi', () => {
  beforeEach(() => {
    mocks.get.mockReset()
    mocks.post.mockReset()
  })

  it('生成只调用模板集写端点一次；5xx 原样抛出，不改调第二个写端点', async () => {
    const error = { response: { status: 504, data: { detail: '响应丢失，执行状态未知' } } }
    mocks.post.mockRejectedValue(error)
    await expect(generateWorkpapers('p1', {
      templateSetId: 's1', year: 2025, codes: ['A1', 'D2'], operationId: 'op-1',
    }))
      .rejects.toBe(error)
    expect(mocks.post).toHaveBeenCalledTimes(1)
    expect(mocks.post).toHaveBeenCalledWith('/api/projects/p1/working-papers/generate', {
      template_set_id: 's1', year: 2025, selected_templates: ['A1', 'D2'], operation_id: 'op-1',
    }, { _silent: true })
  })

  it('常见权限 / 归档错误给出中文原因', () => {
    expect(planErrorText({ response: { status: 401 } })).toContain('重新登录')
    expect(planErrorText({ response: { status: 403 } })).toContain('查看权限')
    expect(planErrorText({ response: { status: 423 } })).toContain('项目已归档')
    expect(planErrorText({})).toContain('网络不通')
  })

  it('operation 状态读取禁用 GET 去重', async () => {
    mocks.get.mockResolvedValue({ operation_id: 'op-1', status: 'materializing' })
    await getGenerationOperation('p1', 'op-1')
    expect(mocks.get).toHaveBeenCalledWith(
      '/api/projects/p1/working-papers/generation-operations/op-1',
      { _silent: true, _dedupe: false },
    )
  })

  it('写请求响应丢失后按同 operation id 取回原 terminal 回执', async () => {
    const error = new Error('network lost')
    const receipt = { created: 1, created_codes: ['D2'], operation_id: 'op-1', status: 'succeeded' } as any
    mocks.post.mockRejectedValueOnce(error)
    mocks.get.mockResolvedValueOnce({
      operation_id: 'op-1', status: 'succeeded', terminal: true, receipt,
    })
    await expect(runGenerationOperation('p1', {
      templateSetId: 's1', year: 2025, codes: ['D2'], operationId: 'op-1',
    }, { sleepFn: vi.fn() })).resolves.toEqual(receipt)
    expect(mocks.post).toHaveBeenCalledTimes(1)
    expect(mocks.get).toHaveBeenCalledTimes(1)
  })

  it('operation id 载荷冲突原样抛 409，不查询并误领旧回执', async () => {
    const conflict = { response: { status: 409, data: { detail: 'operation_id 已用于不同的生成请求' } } }
    mocks.post.mockRejectedValueOnce(conflict)
    await expect(runGenerationOperation('p1', {
      templateSetId: 's1', year: 2025, codes: ['D2'], operationId: 'op-conflict',
    })).rejects.toBe(conflict)
    expect(mocks.get).not.toHaveBeenCalled()
  })

  it('租约过期只以同 id 同载荷重入同一写端点', async () => {
    const receipt = { created: 1, created_codes: ['D2'], operation_id: 'op-2', status: 'succeeded' } as any
    mocks.post
      .mockResolvedValueOnce({ operation_id: 'op-2', status: 'materializing', terminal: false, resumable: false })
      .mockResolvedValueOnce(receipt)
    mocks.get.mockResolvedValueOnce({
      operation_id: 'op-2', status: 'materializing', terminal: false, resumable: true,
    })
    await expect(runGenerationOperation('p1', {
      templateSetId: 's1', year: 2025, codes: ['D2'], operationId: 'op-2',
    }, { pollMs: 0, sleepFn: async () => {} })).resolves.toEqual(receipt)
    expect(mocks.post).toHaveBeenCalledTimes(2)
    expect(mocks.post.mock.calls[0]).toEqual(mocks.post.mock.calls[1])
  })

  it('粗裁确认状态禁用 GET 在途合并，保存后的读取必须发新请求', async () => {
    mocks.get.mockResolvedValue({ cycles: [] })
    await getScopeConfirmations('p1')
    expect(mocks.get).toHaveBeenCalledWith('/api/projects/p1/procedure-scope/confirmations', {
      _silent: true, _dedupe: false,
    })
  })

  it('列模板集只发一次 GET、不再先 POST seed（内置集由后端启动任务初始化）', async () => {
    mocks.get.mockResolvedValue([
      { id: 's1', set_name: '标准年审' }, { id: 's2', set_name: 'IPO' }, { id: 's3', set_name: '自建集' },
    ])
    const sets = await listGenerationTemplateSets()
    expect(mocks.post).not.toHaveBeenCalled()
    expect(mocks.get).toHaveBeenCalledTimes(1)
    expect(mocks.get).toHaveBeenCalledWith('/api/template-sets', { _silent: true })
    expect(sets.map((s) => s.set_name)).toEqual(['标准年审', '自建集'])
  })
})
