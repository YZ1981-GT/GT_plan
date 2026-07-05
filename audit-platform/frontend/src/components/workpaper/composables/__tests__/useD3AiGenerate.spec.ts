import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

vi.mock('@/utils/http', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
  },
}))

import http from '@/utils/http'
import { useD3AiGenerate } from '../useD3AiGenerate'

describe('useD3AiGenerate', () => {
  const wpId = ref('wp-d3')

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(http.get).mockResolvedValue({ data: { data: { status: 'healthy' } } })
  })

  it('generate calls d3 ai-generate endpoint', async () => {
    vi.mocked(http.post).mockResolvedValue({
      data: { data: { content: '测试文本' } },
    })
    const { generate, checkAiHealth } = useD3AiGenerate(wpId)
    await checkAiHealth()
    const text = await generate({
      section: 'adj-conclusion',
      existingContent: '',
      relatedContext: { task: 'test' },
    })
    expect(text).toBe('测试文本')
    expect(http.post).toHaveBeenCalledWith(
      '/api/workpapers/wp-d3/d3/ai-generate',
      expect.objectContaining({ section: 'adj-conclusion' }),
      expect.any(Object),
    )
  })
})
