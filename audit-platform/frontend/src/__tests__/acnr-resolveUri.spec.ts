/**
 * ACNR resolveUri — URI 规范化辅助单元测试
 *
 * 覆盖：parseUri / isValidUri / extractDomain / normalizeUri / parseIndexRef / isValidIndexRef
 *
 * Requirements: R9, R14.1
 */
import { describe, it, expect } from 'vitest'
import {
  parseUri,
  isValidUri,
  extractDomain,
  normalizeUri,
  parseIndexRef,
  isValidIndexRef,
} from '@/services/acnr/resolveUri'

// ─── parseUri ─────────────────────────────────────────────────────────────────

describe('parseUri — standard profile', () => {
  it('parses wp://{parent}/{sheet_name}#{cell}', () => {
    const r = parseUri('wp://D2/明细表D2-2#E100')
    expect(r).toEqual({
      profile: 'standard',
      domain: 'wp',
      parent: 'D2',
      sheetName: '明细表D2-2',
      cell: 'E100',
    })
  })

  it('parses wp:// without cell fragment', () => {
    const r = parseUri('wp://D2/明细表D2-2')
    expect(r).toEqual({
      profile: 'standard',
      domain: 'wp',
      parent: 'D2',
      sheetName: '明细表D2-2',
      cell: undefined,
    })
  })

  it('handles hyphenated parent codes', () => {
    const r = parseUri('wp://G5/长期股权投资G5-1#B3')
    expect(r).toEqual({
      profile: 'standard',
      domain: 'wp',
      parent: 'G5',
      sheetName: '长期股权投资G5-1',
      cell: 'B3',
    })
  })
})

describe('parseUri — custom_flat profile', () => {
  it('parses wp://{wp_code}/{cell} (A1 cell)', () => {
    const r = parseUri('wp://CUST-01/B7')
    expect(r).toEqual({
      profile: 'custom_flat',
      domain: 'wp',
      wpCode: 'CUST-01',
      cell: 'B7',
    })
  })
})

describe('parseUri — non-wp domains', () => {
  it('parses tb://', () => {
    const r = parseUri('tb://1001#审定数')
    expect(r).toEqual({
      profile: 'tb',
      domain: 'tb',
      code: '1001',
      cell: '审定数',
    })
  })

  it('parses report://', () => {
    const r = parseUri('report://BS#A1')
    expect(r).toEqual({
      profile: 'report',
      domain: 'report',
      code: 'BS',
      cell: 'A1',
    })
  })

  it('parses note://', () => {
    const r = parseUri('note://五、3')
    expect(r).toEqual({
      profile: 'note',
      domain: 'note',
      code: '五、3',
    })
  })

  it('parses aux://', () => {
    const r = parseUri('aux://dept#cost_center')
    expect(r).toEqual({
      profile: 'aux',
      domain: 'aux',
      code: 'dept',
      cell: 'cost_center',
    })
  })
})

describe('parseUri — invalid inputs', () => {
  it('returns null for empty string', () => {
    expect(parseUri('')).toBeNull()
  })

  it('returns null for invalid scheme', () => {
    expect(parseUri('http://example.com')).toBeNull()
  })

  it('returns null for malformed URI', () => {
    expect(parseUri('wp://')).toBeNull()
  })
})

// ─── isValidUri ───────────────────────────────────────────────────────────────

describe('isValidUri', () => {
  it('returns true for valid standard URI', () => {
    expect(isValidUri('wp://D2/明细表D2-2#E100')).toBe(true)
  })

  it('returns false for invalid URI', () => {
    expect(isValidUri('random string')).toBe(false)
  })
})

// ─── extractDomain ────────────────────────────────────────────────────────────

describe('extractDomain', () => {
  it('extracts wp domain', () => {
    expect(extractDomain('wp://D2/sheet#A1')).toBe('wp')
  })

  it('extracts tb domain', () => {
    expect(extractDomain('tb://1001')).toBe('tb')
  })

  it('returns null for invalid URI', () => {
    expect(extractDomain('not-a-uri')).toBeNull()
  })
})

// ─── normalizeUri ─────────────────────────────────────────────────────────────

describe('normalizeUri', () => {
  it('trims whitespace', () => {
    expect(normalizeUri('  wp://D2/sheet  ')).toBe('wp://D2/sheet')
  })

  it('removes trailing slash', () => {
    expect(normalizeUri('wp://D2/sheet/')).toBe('wp://D2/sheet')
  })

  it('returns empty for empty input', () => {
    expect(normalizeUri('')).toBe('')
  })
})

// ─── parseIndexRef ────────────────────────────────────────────────────────────

describe('parseIndexRef', () => {
  it('parses cell:D2-2!E100', () => {
    expect(parseIndexRef('cell:D2-2!E100')).toEqual({
      namespace: 'cell',
      target: 'D2-2!E100',
    })
  })

  it('parses TB:1001', () => {
    expect(parseIndexRef('TB:1001')).toEqual({
      namespace: 'TB',
      target: '1001',
    })
  })

  it('parses wp:D2-2', () => {
    expect(parseIndexRef('wp:D2-2')).toEqual({
      namespace: 'wp',
      target: 'D2-2',
    })
  })

  it('parses Note:五、3', () => {
    expect(parseIndexRef('Note:五、3')).toEqual({
      namespace: 'Note',
      target: '五、3',
    })
  })

  it('parses external module namespace Adj:001', () => {
    expect(parseIndexRef('Adj:001')).toEqual({
      namespace: 'Adj',
      target: '001',
    })
  })

  it('returns null for invalid namespace', () => {
    expect(parseIndexRef('invalid:target')).toBeNull()
  })

  it('returns null for empty string', () => {
    expect(parseIndexRef('')).toBeNull()
  })
})

// ─── isValidIndexRef ──────────────────────────────────────────────────────────

describe('isValidIndexRef', () => {
  it('returns true for valid cell: ref', () => {
    expect(isValidIndexRef('cell:D2-2!E100')).toBe(true)
  })

  it('returns false for invalid ref', () => {
    expect(isValidIndexRef('badns:target')).toBe(false)
  })
})
