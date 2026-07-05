import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

vi.mock('@/utils/http', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
  },
}))

import http from '@/utils/http'
import { useD1AiGenerate } from '../useD1AiGenerate'

describe('useD1AiGenerate', () => {
  const wpId = ref('wp-d1')

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(http.get).mockResolvedValue({ data: { data: { status: 'healthy' } } })
  })

  it('generate calls d1 ai-generate endpoint', async () => {
    vi.mocked(http.post).mockResolvedValue({
      data: { data: { content: '测试文本' } },
    })
    const { generate, checkAiHealth } = useD1AiGenerate(wpId)
    await checkAiHealth()
    const text = await generate({
      section: 'policy-conclusion',
      existingContent: '',
      relatedContext: { task: 'test' },
    })
    expect(text).toBe('测试文本')
    expect(http.post).toHaveBeenCalledWith(
      '/api/workpapers/wp-d1/d1/ai-generate',
      expect.objectContaining({ section: 'policy-conclusion' }),
      expect.any(Object),
    )
  })
})
