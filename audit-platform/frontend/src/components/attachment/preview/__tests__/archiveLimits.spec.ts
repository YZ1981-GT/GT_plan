import { describe, it, expect } from 'vitest'
import {
  ARCHIVE_LIMITS,
  checkArchiveLimits,
  normalizeArchivePath,
  classifyZipFlags,
} from '../archive/archiveLimits'

const baseState = {
  entries: 1,
  entryUncompressed: 1,
  totalUncompressed: 1,
  compressedConsumed: 1,
  pathDepth: 1,
}

describe('ARCHIVE_LIMITS', () => {
  it('五项单一真源数值', () => {
    expect(ARCHIVE_LIMITS.maxEntries).toBe(2000)
    expect(ARCHIVE_LIMITS.maxEntryUncompressedBytes).toBe(32 * 1024 * 1024)
    expect(ARCHIVE_LIMITS.maxTotalUncompressedBytes).toBe(64 * 1024 * 1024)
    expect(ARCHIVE_LIMITS.maxCompressionRatio).toBe(100)
    expect(ARCHIVE_LIMITS.maxPathDepth).toBe(8)
  })

  it('各限可独立触发', () => {
    expect(checkArchiveLimits({ ...baseState, entries: 2001 })).toBe('maxEntries')
    expect(checkArchiveLimits({ ...baseState, entryUncompressed: 33 * 1024 * 1024 })).toBe(
      'maxEntryUncompressedBytes',
    )
    expect(checkArchiveLimits({ ...baseState, totalUncompressed: 65 * 1024 * 1024 })).toBe(
      'maxTotalUncompressedBytes',
    )
    expect(checkArchiveLimits({ ...baseState, totalUncompressed: 101 })).toBe(
      'maxCompressionRatio',
    )
    expect(checkArchiveLimits({ ...baseState, pathDepth: 9 })).toBe('maxPathDepth')
  })

  it('接受注入 limits，边界相等不触发、增加 1 立即触发', () => {
    const limits = {
      maxEntries: 2,
      maxEntryUncompressedBytes: 10,
      maxTotalUncompressedBytes: 20,
      maxCompressionRatio: 4,
      maxPathDepth: 3,
    }
    expect(
      checkArchiveLimits(
        {
          entries: 2,
          entryUncompressed: 10,
          totalUncompressed: 20,
          compressedConsumed: 5,
          pathDepth: 3,
        },
        limits,
      ),
    ).toBeNull()
    expect(checkArchiveLimits({ ...baseState, entries: 3 }, limits)).toBe('maxEntries')
    expect(checkArchiveLimits({ ...baseState, entryUncompressed: 11 }, limits)).toBe(
      'maxEntryUncompressedBytes',
    )
    expect(
      checkArchiveLimits(
        { ...baseState, entryUncompressed: 1, totalUncompressed: 21, compressedConsumed: 100 },
        limits,
      ),
    ).toBe('maxTotalUncompressedBytes')
    expect(
      checkArchiveLimits(
        { ...baseState, totalUncompressed: 5, compressedConsumed: 0 },
        limits,
      ),
    ).toBe('maxCompressionRatio')
    expect(checkArchiveLimits({ ...baseState, pathDepth: 4 }, limits)).toBe('maxPathDepth')
  })

  it('路径穿越与注入深度', () => {
    expect(normalizeArchivePath('../etc/passwd').suspicious).toBe(true)
    expect(normalizeArchivePath('C:\\Windows\\a.txt').suspicious).toBe(true)
    expect(normalizeArchivePath('/abs/a').suspicious).toBe(true)
    expect(normalizeArchivePath('a/b/c').suspicious).toBe(false)
    expect(normalizeArchivePath('a/b/c', 2).reasons).toContain('path_depth')
  })

  it('加密与 unsupported method', () => {
    expect(classifyZipFlags(0x1, 8)).toBe('encrypted')
    expect(classifyZipFlags(0, 8)).toBe('entry_ok')
    expect(classifyZipFlags(0, 99)).toBe('container_unsupported')
  })
})
