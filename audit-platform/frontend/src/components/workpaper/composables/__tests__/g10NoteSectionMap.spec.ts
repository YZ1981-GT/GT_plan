import { describe, expect, it, vi } from 'vitest'
import { fetchG10CentralNoteText, G10_NOTE_SECTION } from '../g10NoteSectionMap'

describe('g10NoteSectionMap', () => {
  it('fetchG10CentralNoteText 解析 text_content', async () => {
    const fetchFn = vi.fn().mockResolvedValue({
      data: { text_content: '  附注正文  ' },
    })
    const text = await fetchG10CentralNoteText(fetchFn, 'proj-1', 2025, 'listed')
    expect(text).toBe('附注正文')
    expect(fetchFn).toHaveBeenCalledWith(
      `/api/disclosure-notes/proj-1/2025/${encodeURIComponent(G10_NOTE_SECTION.listed.trading)}`,
      { _silent: true },
    )
  })

  it('fetchG10CentralNoteText 无文本返回 null', async () => {
    const fetchFn = vi.fn().mockResolvedValue({ data: { text_content: '' } })
    expect(await fetchG10CentralNoteText(fetchFn, 'p', 2025, 'soe')).toBeNull()
  })
})
