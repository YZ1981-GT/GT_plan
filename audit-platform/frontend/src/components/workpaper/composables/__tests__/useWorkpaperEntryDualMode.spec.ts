import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useWorkpaperEntryDualMode } from '../useWorkpaperEntryDualMode'

describe('useWorkpaperEntryDualMode', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: { healthy: true } }),
    }))
  })

  it('delegates resolveOoSheetName to caller', () => {
    const { resolveOoSheetName } = useWorkpaperEntryDualMode({
      reloadAllResponses: async () => {},
      resolveOoSheetName: () => 'custom-sheet',
    })
    expect(resolveOoSheetName()).toBe('custom-sheet')
  })

  it('switchMode to html reloads responses', async () => {
    const reload = vi.fn().mockResolvedValue(undefined)
    const { switchMode, mode } = useWorkpaperEntryDualMode({
      reloadAllResponses: reload,
      resolveOoSheetName: () => 'x',
    })
    mode.value = 'onlyoffice'
    await switchMode('html')
    expect(reload).toHaveBeenCalledOnce()
    expect(mode.value).toBe('html')
  })
})
