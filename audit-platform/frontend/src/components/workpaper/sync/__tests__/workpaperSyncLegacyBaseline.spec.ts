import { describe, expect, it } from 'vitest'
import { WORKPAPER_SYNC_MANIFEST } from '../workpaperSyncManifest.generated'
import {
  WORKPAPER_SYNC_LEGACY_BASELINE_DIGEST,
  WORKPAPER_SYNC_LEGACY_ENTRIES,
  WORKPAPER_SYNC_LEGACY_STATS,
} from '../workpaperSyncLegacyBaseline.generated'

describe('workpaper sync false-bidirectional baseline', () => {
  it('covers the exact generated manifest entry denominator', () => {
    expect(WORKPAPER_SYNC_LEGACY_BASELINE_DIGEST).toMatch(/^[0-9a-f]{64}$/)
    expect(WORKPAPER_SYNC_LEGACY_ENTRIES.map((entry) => entry.entryId)).toEqual(
      WORKPAPER_SYNC_MANIFEST.map((entry) => entry.entryId),
    )
    expect(WORKPAPER_SYNC_LEGACY_STATS.entry_count).toBe(WORKPAPER_SYNC_LEGACY_ENTRIES.length)
  })

  it('keeps current fake bidirectionality explicit instead of treating it as success', () => {
    const openEntries = WORKPAPER_SYNC_LEGACY_ENTRIES.filter(
      (entry) => entry.independentEntry && entry.capability !== 'unreachable',
    )
    expect(openEntries.length).toBeGreaterThan(0)
    for (const entry of openEntries) {
      expect(entry.reasonCodes.length, entry.entryId).toBeGreaterThan(0)
      expect(entry.reasonCodes, entry.entryId).toContain('no_durable_forcesave_ack')
      expect(entry.reasonCodes, entry.entryId).toContain('missing_adapter')
    }
  })

  it('records a real source location for every visible single-mode switch debt', () => {
    const switchDebts = WORKPAPER_SYNC_LEGACY_ENTRIES.filter(
      (entry) => entry.independentEntry && entry.modeSwitchVisible,
    )
    expect(switchDebts.length).toBe(WORKPAPER_SYNC_LEGACY_STATS.single_mode_switch_visible_count)
    expect(switchDebts.length).toBeGreaterThan(0)
    for (const entry of switchDebts) {
      expect(entry.modeSwitchEvidence.length, entry.entryId).toBeGreaterThan(0)
      for (const evidence of entry.modeSwitchEvidence) {
        expect(evidence.file).toMatch(/\.vue$/)
        expect(evidence.line).toBeGreaterThan(0)
        expect(evidence.snippet.length).toBeGreaterThan(0)
      }
    }
  })
})
