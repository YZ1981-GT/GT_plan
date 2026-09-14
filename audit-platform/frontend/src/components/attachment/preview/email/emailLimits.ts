/**
 * Email limits + CID helpers
 */
export const MiB = 1024 * 1024

export const EMAIL_LIMITS = Object.freeze({
  maxInputBytes: 50 * MiB,
  maxParts: 500,
  maxHeaderBytes: 2 * MiB,
  maxBoundaryBytes: 70,
  maxMimeNestingDepth: 32,
  maxRfc822NestingDepth: 0,
  maxInlineRasterBytes: 10 * MiB,
  maxInlineTotalBytes: 32 * MiB,
  deadlineMs: 15_000,
})

export function canonicalizeCid(raw: string | null | undefined): string | null {
  if (raw == null) return null
  let s = String(raw).trim()
  if (s.startsWith('<') && s.endsWith('>')) s = s.slice(1, -1)
  try {
    s = decodeURIComponent(s)
  } catch {
    /* keep */
  }
  s = s.toLowerCase()
  return s || null
}

export type RasterMime = 'image/png' | 'image/jpeg' | 'image/gif' | 'image/webp'

export function detectRasterMime(bytes: ArrayBuffer): RasterMime | null {
  const u8 = new Uint8Array(bytes)
  if (
    u8.length >= 8 &&
    u8[0] === 0x89 && u8[1] === 0x50 && u8[2] === 0x4e && u8[3] === 0x47 &&
    u8[4] === 0x0d && u8[5] === 0x0a && u8[6] === 0x1a && u8[7] === 0x0a
  ) return 'image/png'
  if (u8.length >= 3 && u8[0] === 0xff && u8[1] === 0xd8 && u8[2] === 0xff) return 'image/jpeg'
  if (
    u8.length >= 6 &&
    u8[0] === 0x47 && u8[1] === 0x49 && u8[2] === 0x46 && u8[3] === 0x38 &&
    (u8[4] === 0x37 || u8[4] === 0x39) && u8[5] === 0x61
  ) return 'image/gif'
  if (
    u8.length >= 12 &&
    u8[0] === 0x52 && u8[1] === 0x49 && u8[2] === 0x46 && u8[3] === 0x46 &&
    u8[8] === 0x57 && u8[9] === 0x45 && u8[10] === 0x42 && u8[11] === 0x50
  ) return 'image/webp'
  return null
}

export type EmailLimitError =
  | 'email_input_limit'
  | 'email_part_limit'
  | 'email_header_limit'
  | 'email_boundary_limit'
  | 'email_nesting_limit'
  | 'email_inline_raster_limit'
  | 'email_inline_total_limit'
