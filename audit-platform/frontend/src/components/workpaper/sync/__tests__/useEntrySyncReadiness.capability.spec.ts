import { effectScope } from 'vue'
import { describe, expect, it, vi } from 'vitest'
vi.mock('../workpaperSyncManifest.generated', async importOriginal => {
  const actual = await importOriginal<typeof import('../workpaperSyncManifest.generated')>()
  const capabilities = ['single_html', 'single_onlyoffice', 'bidirectional', 'unreachable', null] as const
  const entries: import('../workpaperSyncManifest.generated').WorkpaperSyncManifestEntry[] = capabilities.map(capability => ({
    ...actual.WORKPAPER_SYNC_MANIFEST[0],
    entryId: `test/${capability}`, effectiveEntryId: `test/${capability}`,
    capability, adjudicationState: capability === null ? 'pending' : 'terminal',
    htmlCounterpartVerdict: 'exists',
  }))
  return { ...actual, WORKPAPER_SYNC_MANIFEST: entries }
})
import { useEntrySyncReadiness } from '../useEntrySyncReadiness'
describe('完整能力合同的静态投影', () => {
  it.each([
    ['single_html', ['html'], true, 'not_applicable'],
    ['single_onlyoffice', ['oo'], true, 'not_applicable'],
    ['bidirectional', ['html', 'oo'], false, 'missing'],
    ['unreachable', [], false, 'missing'],
    [null, ['html', 'oo'], false, 'missing'],
  ] as const)('%s 按合同保留真实分支', (capability, allowed, ready, acceptance) => {
    const scope = effectScope()
    try {
      const state = scope.run(() => useEntrySyncReadiness({ projectId: '', wpId: '', entryId: `test/${capability}` }))!
      expect(state.readiness.value?.capability).toBe(capability)
      expect(state.readiness.value?.allowed_modes).toEqual([...allowed])
      expect(state.readiness.value?.runtime.ready).toBe(ready)
      expect(state.readiness.value?.acceptance.state).toBe(acceptance)
      expect(state.readiness.value?.can_claim_bidirectional).toBe(false)
    } finally { scope.stop() }
  })
})
