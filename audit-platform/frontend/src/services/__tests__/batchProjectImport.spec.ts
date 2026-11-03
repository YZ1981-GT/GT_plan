import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  get: vi.fn(),
  download: vi.fn(),
}))

vi.mock('@/utils/http', () => ({
  default: { post: mocks.post, get: mocks.get },
  downloadFile: mocks.download,
}))

import {
  applyBatchProjectPlan,
  batchErrorMessage,
  canBatchCreateProjects,
  downloadGroupImportTemplate,
  validateBatchProjectFile,
} from '../batchProjectImport'

describe('batchProjectImport', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it.each([
    ['admin', true], ['partner', true], ['manager', true],
    ['auditor', false], ['qc', false], ['eqcr', false], ['readonly', false],
  ])('角色 %s 的批量建项可用性为 %s', (role, allowed) => {
    expect(canBatchCreateProjects(role)).toBe(allowed)
  })

  it('预校验只上传一次文件并带场景和幂等键', async () => {
    const response = { valid: true, validation_id: 'plan-1' }
    mocks.post.mockResolvedValue({ data: response })
    const file = new File(['xlsx'], '建项.xlsx')
    await expect(validateBatchProjectFile(file, 'consolidation', 'operation-1')).resolves.toBe(response)
    expect(mocks.post).toHaveBeenCalledTimes(1)
    const [url, body, config] = mocks.post.mock.calls[0]
    expect(url).toBe('/api/projects/batch-validate?mode=consolidation')
    expect(body).toBeInstanceOf(FormData)
    expect(body.get('file')).toBe(file)
    expect(body.get('idempotency_key')).toBe('operation-1')
    expect(config._silent).toBe(true)
  })

  it('确认阶段只发送计划身份，不再携带文件', async () => {
    const receipt = { created_count: 2 }
    mocks.post.mockResolvedValue({ data: receipt })
    await expect(applyBatchProjectPlan('plan-1', 'operation-1')).resolves.toBe(receipt)
    expect(mocks.post).toHaveBeenCalledWith('/api/projects/batch-apply', {
      validation_id: 'plan-1', idempotency_key: 'operation-1',
    }, { _silent: true })
  })

  it('合并树导出走服务端根项目端点', async () => {
    mocks.download.mockResolvedValue(undefined)
    await downloadGroupImportTemplate('root-1')
    expect(mocks.download).toHaveBeenCalledWith(
      '/api/projects/root-1/group-import-template',
      expect.objectContaining({ silent: true }),
    )
  })

  it('优先展示后端中文错误而不是统一文件格式提示', () => {
    expect(batchErrorMessage({ response: { data: { detail: '预校验结果已过期' } } }, '失败'))
      .toBe('预校验结果已过期')
    expect(batchErrorMessage(new Error('网络中断'), '失败')).toBe('网络中断')
  })
})
