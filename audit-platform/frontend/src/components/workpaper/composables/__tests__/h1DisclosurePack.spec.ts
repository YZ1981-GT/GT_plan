/**
 * H1 附注 JSON 包 / 国企键迁移 守卫测试
 */
import { describe, expect, it } from 'vitest'
import {
  buildListedDisclosurePack,
  buildSoeDisclosurePack,
  listedPackPersistEntries,
  parseListedDisclosurePack,
  parseSoeDisclosurePack,
  soePackPersistEntries,
} from '../h1DisclosurePack'
import {
  H1_SOE_KEYS,
  H1_SOE_KEYS_LEGACY,
  readSoeRemark,
} from '../h1SoeDisclosureModel'
import { H1_LISTED_ITEM } from '../h1ListedDisclosureModel'
import { SOE_SECTIONS } from '../h1DisclosureSections'

describe('h1DisclosurePack', () => {
  it('listed pack round-trip parse', () => {
    const pack = buildListedDisclosurePack({
      summary: [{ key: 'fixed_assets', endBalance: 1, priorBalance: 0 }],
      categories: [{ key: 'buildings', label: '房屋及建筑物' }],
      movement: {},
      idle: [],
      leaseOut: [],
      titleCert: [],
      clearing: [],
      mortgage: [],
      govSubsidy: { amount: 0 },
      notes: { impairment: 'a', mortgage: 'b', sale: 'c', clearing: 'd' },
    })
    const parsed = parseListedDisclosurePack(pack)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return
    const entries = listedPackPersistEntries(parsed.pack)
    expect(entries.some((e) => e.itemId === H1_LISTED_ITEM.summary)).toBe(true)
    expect(entries.some((e) => e.itemId === H1_LISTED_ITEM.noteImpairment)).toBe(true)
    expect(entries.every((e) => !String(e.itemId).includes('disc-listed'))).toBe(true)
  })

  it('soe pack round-trip uses H1-soe-* keys', () => {
    const pack = buildSoeDisclosurePack({
      summary: { faEnd: 10, clearingEnd: 0 },
      movement: {},
      idle: [],
      title: [],
      clearing: [],
      clearingNote: '超1年说明',
    })
    const parsed = parseSoeDisclosurePack(pack)
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return
    const entries = soePackPersistEntries(parsed.pack)
    expect(entries.map((e) => e.itemId)).toEqual([
      H1_SOE_KEYS.summary,
      H1_SOE_KEYS.movement,
      H1_SOE_KEYS.idle,
      H1_SOE_KEYS.title,
      H1_SOE_KEYS.clearing,
      H1_SOE_KEYS.clearingNote,
    ])
  })

  it('rejects wrong version', () => {
    expect(parseListedDisclosurePack({ version: 2 }).ok).toBe(false)
    expect(parseSoeDisclosurePack({ version: 99, variant: 'soe' }).ok).toBe(false)
  })
})

describe('H1 SOE key migration', () => {
  it('keys are H1-soe-* with disc-soe legacy map', () => {
    expect(H1_SOE_KEYS.summary).toBe('H1-soe-summary')
    expect(H1_SOE_KEYS_LEGACY.summary).toBe('H1-disc-soe-summary')
  })

  it('readSoeRemark prefers new key then legacy', () => {
    const map = new Map<string, { remark?: string | null }>([
      [H1_SOE_KEYS_LEGACY.summary, { remark: JSON.stringify({ legacy: true }) }],
    ])
    expect(JSON.parse(readSoeRemark((id) => map.get(id), 'summary')!)).toEqual({ legacy: true })

    map.set(H1_SOE_KEYS.summary, { remark: JSON.stringify({ neu: true }) })
    expect(JSON.parse(readSoeRemark((id) => map.get(id), 'summary')!)).toEqual({ neu: true })
  })

  it('SOE_SECTIONS still five blocks', () => {
    expect(SOE_SECTIONS.map((s) => s.key)).toEqual(['summary', 'overview', 'idle', 'title', 'clearing'])
  })
})
