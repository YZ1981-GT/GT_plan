const MiB = 1024 * 1024

export const ARCHIVE_LIMITS = Object.freeze({
  maxEntries: 2000,
  maxEntryUncompressedBytes: 32 * MiB,
  maxTotalUncompressedBytes: 64 * MiB,
  maxCompressionRatio: 100,
  /** 归一化路径段深度，不是嵌套归档递归深度 */
  maxPathDepth: 8,
})

export type ArchiveLimits = typeof ARCHIVE_LIMITS
export type ArchiveLimitKey = keyof ArchiveLimits

export type ContainerSupport =
  | 'supported'
  | 'container_unsupported'
  | 'encrypted'

export const ZIP_METHOD_SUPPORT: Readonly<Record<number, ContainerSupport | 'entry_ok'>> = Object.freeze({
  0: 'entry_ok', // stored
  8: 'entry_ok', // deflate
  9: 'container_unsupported', // Deflate64
  12: 'container_unsupported', // BZip2
  14: 'container_unsupported', // LZMA
  93: 'container_unsupported', // Zstd
  99: 'container_unsupported', // AES
})

export function classifyZipFlags(generalPurposeBitFlag: number, method: number): ContainerSupport | 'entry_ok' {
  if (generalPurposeBitFlag & 0x1) return 'encrypted'
  const m = ZIP_METHOD_SUPPORT[method]
  return m ?? 'container_unsupported'
}

export function normalizeArchivePath(
  name: string,
  maxPathDepth = ARCHIVE_LIMITS.maxPathDepth,
): {
  normalized: string
  depth: number
  suspicious: boolean
  reasons: string[]
} {
  const reasons: string[] = []
  const n = name.replace(/\\/g, '/')
  if (n.includes('\0')) reasons.push('nul')
  if (/^[a-zA-Z]:/.test(n) || n.startsWith('/')) reasons.push('absolute_or_drive')
  const parts = n.split('/').filter((p) => p.length > 0)
  if (parts.some((p) => p === '..')) reasons.push('dotdot')
  const depth = parts.length
  if (depth > maxPathDepth) reasons.push('path_depth')
  return {
    normalized: n,
    depth,
    suspicious: reasons.length > 0,
    reasons,
  }
}

export function checkArchiveLimits(
  state: {
    entries: number
    entryUncompressed: number
    totalUncompressed: number
    compressedConsumed: number
    entryCompressedConsumed?: number
    pathDepth: number
  },
  limits: ArchiveLimits = ARCHIVE_LIMITS,
): ArchiveLimitKey | null {
  if (state.entries > limits.maxEntries) return 'maxEntries'
  if (state.entryUncompressed > limits.maxEntryUncompressedBytes) return 'maxEntryUncompressedBytes'
  if (state.totalUncompressed > limits.maxTotalUncompressedBytes) return 'maxTotalUncompressedBytes'
  if (state.pathDepth > limits.maxPathDepth) return 'maxPathDepth'
  const denom = Math.max(1, state.compressedConsumed)
  if (state.totalUncompressed / denom > limits.maxCompressionRatio) return 'maxCompressionRatio'
  if (
    state.entryCompressedConsumed !== undefined &&
    state.entryUncompressed / Math.max(1, state.entryCompressedConsumed) > limits.maxCompressionRatio
  ) {
    return 'maxCompressionRatio'
  }
  return null
}
