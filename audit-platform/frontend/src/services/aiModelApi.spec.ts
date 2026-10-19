import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
}))

vi.mock('@/utils/http', () => ({ default: mocks }))

import {
  activateAIModel,
  createAIModel,
  deactivateAIModel,
  getAIProviders,
  getAIRoutes,
  testAIModel,
  updateAIModel,
} from './aiModelApi'

describe('aiModelApi 企业模型配置契约', () => {
  beforeEach(() => {
    mocks.get.mockReset()
    mocks.post.mockReset()
    mocks.put.mockReset()
    mocks.delete.mockReset()
  })

  it('读取后端 provider registry 投影', async () => {
    const providers = [{
      value: 'custom', label: '自定义', default_endpoint: '',
      requires_api_key: false, supported_types: ['chat'], description: 'test',
    }]
    mocks.get.mockResolvedValue({ data: { providers } })
    await expect(getAIProviders()).resolves.toEqual(providers)
    expect(mocks.get).toHaveBeenCalledWith('/api/ai-models/providers', { _silent: true })
  })

  it('不丢失 qwen3.8 reasoning_effort 与 256K 配置', async () => {
    const payload = {
      model_name: 'qwen3.8', model_type: 'chat' as const, provider: 'custom' as const,
      endpoint_url: 'https://ai.gt-china.com.cn:10010/v1', api_key: 'placeholder',
      context_window: 262144, reasoning_effort: 'low' as const,
    }
    mocks.post.mockResolvedValue({ data: { id: 'model-id' } })
    await createAIModel(payload)
    expect(mocks.post).toHaveBeenCalledWith('/api/ai-models', payload, { _silent: true })
  })

  it('不丢失 PaddleX capability/path/auth 配置', async () => {
    const payload = {
      provider: 'paddleocr' as const, endpoint_url: 'https://ai.gt-china.com.cn:10080',
      ocr_capability: 'layout_parsing' as const, ocr_protocol: 'paddlex_json' as const,
      api_path: '/layout-parsing', auth_scheme: 'bearer' as const,
      request_timeout_seconds: 120,
    }
    mocks.put.mockResolvedValue({ data: { id: 'ocr-id' } })
    await updateAIModel('ocr-id', payload)
    expect(mocks.put).toHaveBeenCalledWith('/api/ai-models/ocr-id', payload, { _silent: true })
  })

  it('连接测试使用 silent 请求且返回稳定结果', async () => {
    const result = { status: 'ok', error_code: null, message: '连接正常' }
    mocks.post.mockResolvedValue({ data: result })
    await expect(testAIModel('model-id')).resolves.toEqual(result)
    expect(mocks.post).toHaveBeenCalledWith(
      '/api/ai-models/model-id/test', undefined, { _silent: true },
    )
  })

  it('启用返回部署位置与本机不可用提示', async () => {
    const result = {
      message: '已启用', model_name: 'paddleocr', provider: 'paddleocr',
      deployment: 'local', warning: '本机模型当前不可用（未安装），已启用；调用时会自动使用已启用的服务器模型兜底',
    }
    mocks.post.mockResolvedValue({ data: result })
    await expect(activateAIModel('ocr-local')).resolves.toEqual(result)
    expect(mocks.post).toHaveBeenCalledWith('/api/ai-models/ocr-local/activate', undefined, { _silent: true })
  })

  it('停用走独立端点', async () => {
    mocks.post.mockResolvedValue({ data: { message: '已停用', model_name: 'qwen3.8' } })
    await deactivateAIModel('chat-server')
    expect(mocks.post).toHaveBeenCalledWith('/api/ai-models/chat-server/deactivate', undefined, { _silent: true })
  })

  it('调用路由默认复用检测结果，检测状态时强制重探', async () => {
    const status = { routes: [], checked_at: '2026-10-19T08:00:00+00:00' }
    mocks.get.mockResolvedValue({ data: status })
    await expect(getAIRoutes()).resolves.toEqual(status)
    expect(mocks.get).toHaveBeenLastCalledWith('/api/ai-models/routes', { params: {}, _silent: true })
    await getAIRoutes(true)
    expect(mocks.get).toHaveBeenLastCalledWith('/api/ai-models/routes', { params: { refresh: true }, _silent: true })
  })
})
