import { describe, expect, it } from 'vitest'
import {
  WORKPAPER_SYNC_MANIFEST,
  WORKPAPER_SYNC_MANIFEST_DIGEST,
  WORKPAPER_SYNC_MANIFEST_STATS,
  WORKPAPER_SYNC_PROFILE_SOURCE_DIGEST,
} from '../workpaperSyncManifest.generated'

const CAPABILITIES = new Set([
  'bidirectional',
  'single_html',
  'single_onlyoffice',
  'unreachable',
])

// source-backed profile 的封闭域，与 V151 `working_paper_sync_test_run` 的 CHECK 同域。
const EDITABILITY = new Set(['editable', 'readonly', 'unreachable'])
const ROOM_MODELS = new Set(['shared', 'exclusive', 'none'])

describe('workpaper sync generated manifest', () => {
  it('keeps a non-empty, unique and closed capability projection', () => {
    expect(WORKPAPER_SYNC_MANIFEST.length).toBeGreaterThan(0)
    expect(WORKPAPER_SYNC_MANIFEST_DIGEST).toMatch(/^[0-9a-f]{64}$/)

    const ids = WORKPAPER_SYNC_MANIFEST.map((entry) => entry.entryId)
    expect(new Set(ids).size).toBe(ids.length)
    expect(WORKPAPER_SYNC_MANIFEST.every((entry) => CAPABILITIES.has(entry.capability))).toBe(true)
    expect(WORKPAPER_SYNC_MANIFEST.every((entry) => entry.hostPath.endsWith('.vue'))).toBe(true)
  })

  it('derives all statistics from the projected entries', () => {
    expect(WORKPAPER_SYNC_MANIFEST_STATS.entry_count).toBe(WORKPAPER_SYNC_MANIFEST.length)
    expect(WORKPAPER_SYNC_MANIFEST_STATS.independent_entry_count).toBe(
      WORKPAPER_SYNC_MANIFEST.filter((entry) => entry.independentEntry).length,
    )
    expect(WORKPAPER_SYNC_MANIFEST_STATS.parent_duplicate_count).toBe(
      WORKPAPER_SYNC_MANIFEST.filter((entry) => entry.parentEntryId !== null).length,
    )
    expect(WORKPAPER_SYNC_MANIFEST_STATS.unreachable_count).toBe(
      WORKPAPER_SYNC_MANIFEST.filter((entry) => entry.capability === 'unreachable').length,
    )
  })

  it('keeps duplicate mounts linked to one independent parent', () => {
    const byId = new Map(WORKPAPER_SYNC_MANIFEST.map((entry) => [entry.entryId, entry]))
    const duplicates = WORKPAPER_SYNC_MANIFEST.filter((entry) => entry.parentEntryId !== null)
    expect(duplicates.length).toBeGreaterThan(0)

    for (const duplicate of duplicates) {
      const parent = byId.get(duplicate.parentEntryId!)
      expect(duplicate.independentEntry).toBe(false)
      expect(parent, duplicate.entryId).toBeDefined()
      expect(parent?.independentEntry).toBe(true)
      expect(parent?.parentEntryId).toBeNull()
      expect(parent?.documentType).toBe(duplicate.documentType)
    }
  })

  it('projects the source-backed profile with closed domains and one spelling', () => {
    expect(WORKPAPER_SYNC_PROFILE_SOURCE_DIGEST).toMatch(/^[0-9a-f]{64}$/)
    for (const entry of WORKPAPER_SYNC_MANIFEST) {
      expect(EDITABILITY.has(entry.editability), entry.entryId).toBe(true)
      expect(ROOM_MODELS.has(entry.roomModel), entry.entryId).toBe(true)
      // profile_id 必须是稳定 key：required scenarios 不得由自由文本/可漂移布尔决定。
      expect(entry.scenarioProfileId, entry.entryId).toMatch(/^[a-z0-9_.-]+$/)
      expect(entry.scenarioProfileId).toContain(entry.editability)
      expect(entry.scenarioProfileId).toContain(entry.roomModel)
      // 唯一拼写：不得同时投影一个可漂移的布尔 `editable`。
      expect(entry).not.toHaveProperty('editable')
      expect(entry.roomServiceState.length).toBeGreaterThan(0)
    }
  })

  it('never claims a room protocol the backend has not wired yet', () => {
    // Task 21 的 room service 接线前，UI 不得以为存在 shared room 协议（doc_key 仍与
    // mtime/客户端本地值耦合、没有 participant lease）。接线后这条判据会自然翻转。
    const states = new Set(WORKPAPER_SYNC_MANIFEST.map((entry) => entry.roomServiceState))
    expect(states.size).toBe(1)
    expect([...states][0]).toBe(WORKPAPER_SYNC_MANIFEST_STATS.room_service_state)
    for (const entry of WORKPAPER_SYNC_MANIFEST) {
      if (entry.capability === 'unreachable') {
        expect(entry.editability, entry.entryId).toBe('unreachable')
        expect(entry.roomModel, entry.entryId).toBe('none')
      }
    }
  })

  it('does not project an ambiguous dual boolean or unsupported legacy success state', () => {
    for (const entry of WORKPAPER_SYNC_MANIFEST) {
      expect(entry).not.toHaveProperty('dual')
      if (entry.migrationState === 'legacy_fake_bidirectional') {
        expect(entry.reasonCodes.length, entry.entryId).toBeGreaterThan(0)
        expect(entry.hasContractEvidence).toBe(false)
        expect(entry.hasBrowserEvidence).toBe(false)
      }
    }
  })
})
