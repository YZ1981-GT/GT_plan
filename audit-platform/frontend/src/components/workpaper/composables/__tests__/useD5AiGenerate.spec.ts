import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

vi.mock('@/utils/http', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
  },
}))

import http from '@/utils/http'
import { useD5AiGenerate } from '../useD5AiGenerate'

describe('useD5AiGenerate', () => {
  const wpId = ref('wp-d5')

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(http.get).mockResolvedValue({ data: { data: { status: 'healthy' } } })
  })

  it('generate calls d5 ai-generate endpoint', async () => {
    vi.mocked(http.post).mockResolvedValue({
      data: { data: { content: '测试文本' } },
    })
    const { generate, checkAiHealth } = useD5AiGenerate(wpId)
    await checkAiHealth()
    const text = await generate({
      section: 'adj-conclusion',
      existingContent: '',
      relatedContext: { task: 'test' },
    })
    expect(text).toBe('测试文本')
    expect(http.post).toHaveBeenCalledWith(
      '/api/workpapers/wp-d5/d5/ai-generate',
      expect.objectContaining({ section: 'adj-conclusion' }),
      expect.any(Object),
    )
  })
})
