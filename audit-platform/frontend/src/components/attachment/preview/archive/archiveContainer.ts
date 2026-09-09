import { Inflate } from 'fflate'
import {
  ARCHIVE_LIMITS,
  checkArchiveLimits,
  classifyZipFlags,
  normalizeArchivePath,
  type ArchiveLimitKey,
  type ArchiveLimits,
} from './archiveLimits'

/**
 * 输入按 4KiB 喂给 fflate；回调可能一次交付其内部缓冲的一整块输出。
 * 我们再按同样大小切分计数，因此单次 callback 已分配的内存不可撤销，但逻辑限额
 * 最多超调 4KiB；命中后当前 callback 立即停止消费，且绝不再 push 后续输入。
 */
export const ARCHIVE_STREAM_CHUNK_BYTES = 4 * 1024

export interface ArchiveEntryMeta {
  name: string
  size: number
  declaredSize: number | null
  mtime: string | null
  isDirectory: boolean
  suspicious: boolean
  suspiciousReasons: string[]
  unparsable: boolean
  method: number | null
}

export type ArchiveParseStatus =
  | 'ok'
  | 'encrypted'
  | 'format_mismatch'
  | 'container_unsupported'
  | 'limit_reached'
  | 'parse_failed'

export interface ArchiveParseResult {
  status: ArchiveParseStatus
  limitKey?: ArchiveLimitKey
  entries: ArchiveEntryMeta[]
  message?: string
}

interface ZipCentralEntry {
  flags: number
  method: number
  dosTime: number
  dosDate: number
  crc: number
  compressedSize: number
  uncompressedSize: number
  nameBytes: Uint8Array
  name: string
  localOffset: number
}

interface ZipStreamState {
  entries: ArchiveEntryMeta[]
  entryUncompressed: number
  totalUncompressed: number
  compressedConsumed: number
  entryCompressedStart: number
  crc: number
  terminal: ArchiveParseResult | null
}

function readU16(view: DataView, offset: number): number {
  return view.getUint16(offset, true)
}

function readU32(view: DataView, offset: number): number {
  return view.getUint32(offset, true)
}

function rangeFits(start: number, length: number, endExclusive: number): boolean {
  return start >= 0 && length >= 0 && start <= endExclusive && length <= endExclusive - start
}

function parseFailure(entries: ArchiveEntryMeta[], message: string): ArchiveParseResult {
  return { status: 'parse_failed', entries, message }
}

function unsupported(entries: ArchiveEntryMeta[], message: string): ArchiveParseResult {
  return { status: 'container_unsupported', entries, message }
}

function findEocd(buf: Uint8Array): { offset: number; malformedComment: boolean } {
  const maxBack = Math.min(buf.length, 0xffff + 22)
  let malformedComment = false
  for (let i = buf.length - 22; i >= buf.length - maxBack; i--) {
    if (i < 0) break
    if (buf[i] !== 0x50 || buf[i + 1] !== 0x4b || buf[i + 2] !== 0x05 || buf[i + 3] !== 0x06) continue
    const commentLength = buf[i + 20] | (buf[i + 21] << 8)
    if (i + 22 + commentLength === buf.length) return { offset: i, malformedComment }
    malformedComment = true
  }
  return { offset: -1, malformedComment }
}

function decodeZipName(bytes: Uint8Array, utf8Flag: boolean): string {
  if (utf8Flag) {
    try {
      return new TextDecoder('utf-8', { fatal: true }).decode(bytes)
    } catch {
      /* fall through to the legacy-name fallback */
    }
  }
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes)
  } catch {
    try {
      return new TextDecoder('gbk' as any, { fatal: false }).decode(bytes)
    } catch {
      return new TextDecoder('utf-8', { fatal: false }).decode(bytes)
    }
  }
}

const CRC32_TABLE = (() => {
  const table = new Uint32Array(256)
  for (let n = 0; n < table.length; n++) {
    let c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    table[n] = c >>> 0
  }
  return table
})()

function updateCrc32(crc: number, chunk: Uint8Array): number {
  let c = crc
  for (let i = 0; i < chunk.length; i++) c = CRC32_TABLE[(c ^ chunk[i]) & 0xff] ^ (c >>> 8)
  return c >>> 0
}

function sameBytes(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false
  return true
}

interface InflateRuntimeProbe {
  p?: Uint8Array
  s?: { p?: number }
}

/**
 * fflate@0.8.3 会把尚未消费的整字节留在 `p`，若当前 DEFLATE block 停在
 * 字节中间则还会保留该字节。产品依赖已精确锁版；字段形态漂移时返回 null 并
 * fail closed，而不是把 callback 的 final 参数误当成“输入已完整消费”。
 */
function unreadDeflateWholeBytes(inflater: Inflate): number | null {
  const probe = inflater as unknown as InflateRuntimeProbe
  if (!(probe.p instanceof Uint8Array) || typeof probe.s?.p !== 'number') return null
  return Math.max(0, probe.p.length - (probe.s.p > 0 ? 1 : 0))
}

function crc32Of(bytes: Uint8Array): number {
  return ~updateCrc32(0xffffffff, bytes) >>> 0
}

interface GzipFrame {
  payloadStart: number
  payloadEnd: number
  expectedCrc: number
  expectedSize: number
  fileName: string | null
  mtime: string | null
}

function parseSingleGzipFrame(buf: Uint8Array): GzipFrame | string {
  if (buf.length < 18) return 'gzip_truncated'
  if (buf[0] !== 0x1f || buf[1] !== 0x8b || buf[2] !== 8) return 'gzip_header'
  const flags = buf[3]
  if (flags & 0xe0) return 'gzip_reserved_flags'

  const trailerStart = buf.length - 8
  const view = new DataView(buf.buffer, buf.byteOffset, buf.byteLength)
  let offset = 10
  let fileName: string | null = null
  if (flags & 0x04) {
    if (!rangeFits(offset, 2, trailerStart)) return 'gzip_extra_truncated'
    const xlen = buf[offset] | (buf[offset + 1] << 8)
    offset += 2
    if (!rangeFits(offset, xlen, trailerStart)) return 'gzip_extra_truncated'
    offset += xlen
  }
  const skipNulTerminated = (message: string): { error: string | null; start: number; end: number } => {
    const start = offset
    while (offset < trailerStart && buf[offset] !== 0) offset += 1
    if (offset >= trailerStart) return { error: message, start, end: offset }
    const end = offset
    offset += 1
    return { error: null, start, end }
  }
  if (flags & 0x08) {
    const field = skipNulTerminated('gzip_filename_truncated')
    if (field.error) return field.error
    fileName = new TextDecoder('latin1').decode(buf.subarray(field.start, field.end)) || null
  }
  if (flags & 0x10) {
    const field = skipNulTerminated('gzip_comment_truncated')
    if (field.error) return field.error
  }
  if (flags & 0x02) {
    if (!rangeFits(offset, 2, trailerStart)) return 'gzip_fhcrc_truncated'
    const expectedHeaderCrc = buf[offset] | (buf[offset + 1] << 8)
    if ((crc32Of(buf.subarray(0, offset)) & 0xffff) !== expectedHeaderCrc) {
      return 'gzip_fhcrc_mismatch'
    }
    offset += 2
  }
  if (offset >= trailerStart) return 'gzip_payload_missing'

  const mtimeSeconds = readU32(view, 4)
  return {
    payloadStart: offset,
    payloadEnd: trailerStart,
    expectedCrc: readU32(view, trailerStart),
    expectedSize: readU32(view, trailerStart + 4),
    fileName,
    mtime: mtimeSeconds === 0 ? null : unixSecondsToIso(mtimeSeconds),
  }
}

function detectContainer(buf: Uint8Array): 'zip' | 'gzip' | 'tar' | 'unknown' {
  if (
    buf.length >= 4 &&
    buf[0] === 0x50 &&
    buf[1] === 0x4b &&
    (buf[2] === 0x03 || buf[2] === 0x05 || buf[2] === 0x07)
  ) {
    return 'zip'
  }
  if (buf.length >= 2 && buf[0] === 0x1f && buf[1] === 0x8b) return 'gzip'
  if (buf.length >= 512) {
    const magic = String.fromCharCode(...buf.subarray(257, 262))
    if (magic === 'ustar') return 'tar'
  }
  return 'unknown'
}

export function parseArchiveBytes(
  input: ArrayBuffer,
  limits: ArchiveLimits = ARCHIVE_LIMITS,
  hintExt?: string,
): ArchiveParseResult {
  const buf = new Uint8Array(input)
  const kind = detectContainer(buf)
  if (kind === 'unknown') {
    return { status: 'format_mismatch', entries: [], message: 'unrecognized_container' }
  }
  if (kind === 'zip') return parseZip(buf, limits)
  if (kind === 'gzip') {
    return hintExt?.toLowerCase().replace(/^\./, '') === 'gz'
      ? parseGzipFile(buf, limits)
      : parseGzipTar(buf, limits)
  }
  return parseTar(buf, limits)
}

function parseZip(buf: Uint8Array, limits: ArchiveLimits): ArchiveParseResult {
  const view = new DataView(buf.buffer, buf.byteOffset, buf.byteLength)
  const found = findEocd(buf)
  if (found.offset < 0) {
    return parseFailure([], found.malformedComment ? 'eocd_comment_length' : 'eocd_missing')
  }
  const eocd = found.offset
  const disk = readU16(view, eocd + 4)
  const centralDisk = readU16(view, eocd + 6)
  if (disk !== 0 || centralDisk !== 0) return unsupported([], 'multi_disk')

  const diskEntries = readU16(view, eocd + 8)
  const totalEntries = readU16(view, eocd + 10)
  const centralSize = readU32(view, eocd + 12)
  const centralOffset = readU32(view, eocd + 16)
  if (diskEntries !== totalEntries) return parseFailure([], 'disk_entry_count_mismatch')
  if (totalEntries === 0xffff || centralSize === 0xffffffff || centralOffset === 0xffffffff) {
    return unsupported([], 'zip64')
  }
  if (totalEntries > limits.maxEntries) {
    return {
      status: 'limit_reached',
      limitKey: 'maxEntries',
      entries: [],
      message: 'maxEntries',
    }
  }
  if (!rangeFits(centralOffset, centralSize, eocd)) return parseFailure([], 'central_dir_oob')
  if (centralOffset + centralSize !== eocd) return parseFailure([], 'central_layout')

  const records: ZipCentralEntry[] = []
  let offset = centralOffset
  const centralEnd = centralOffset + centralSize
  for (let i = 0; i < totalEntries; i++) {
    if (!rangeFits(offset, 46, centralEnd)) return parseFailure([], 'central_header_truncated')
    if (readU32(view, offset) !== 0x02014b50) return parseFailure([], 'central_sig')

    const flags = readU16(view, offset + 8)
    const method = readU16(view, offset + 10)
    const crc = readU32(view, offset + 16)
    const compressedSize = readU32(view, offset + 20)
    const uncompressedSize = readU32(view, offset + 24)
    const nameLength = readU16(view, offset + 28)
    const extraLength = readU16(view, offset + 30)
    const commentLength = readU16(view, offset + 32)
    const startDisk = readU16(view, offset + 34)
    const localOffset = readU32(view, offset + 42)
    if (
      compressedSize === 0xffffffff ||
      uncompressedSize === 0xffffffff ||
      localOffset === 0xffffffff
    ) {
      return unsupported([], 'zip64')
    }
    if (startDisk !== 0) return unsupported([], 'multi_disk')

    const recordLength = 46 + nameLength + extraLength + commentLength
    if (!rangeFits(offset, recordLength, centralEnd)) return parseFailure([], 'central_record_oob')
    const nameBytes = buf.subarray(offset + 46, offset + 46 + nameLength)
    records.push({
      flags,
      method,
      dosTime: readU16(view, offset + 12),
      dosDate: readU16(view, offset + 14),
      crc,
      compressedSize,
      uncompressedSize,
      nameBytes,
      name: decodeZipName(nameBytes, !!(flags & 0x800)),
      localOffset,
    })
    offset += recordLength
  }
  if (offset !== centralEnd) return parseFailure([], 'central_consumption_mismatch')

  const localOrder = [...records].sort((a, b) => a.localOffset - b.localOffset)
  for (let i = 0; i < localOrder.length; i++) {
    const current = localOrder[i]
    if (current.localOffset >= centralOffset) return parseFailure([], 'local_offset_oob')
    if (i > 0 && current.localOffset === localOrder[i - 1].localOffset) {
      return parseFailure([], 'local_offset_duplicate')
    }
  }
  const nextStructureByOffset = new Map<number, number>()
  for (let i = 0; i < localOrder.length; i++) {
    nextStructureByOffset.set(
      localOrder[i].localOffset,
      i + 1 < localOrder.length ? localOrder[i + 1].localOffset : centralOffset,
    )
  }

  const entries: ArchiveEntryMeta[] = []
  const streamState: ZipStreamState = {
    entries,
    entryUncompressed: 0,
    totalUncompressed: 0,
    compressedConsumed: 0,
    entryCompressedStart: 0,
    crc: 0xffffffff,
    terminal: null,
  }

  for (const record of records) {
    const support = classifyZipFlags(record.flags, record.method)
    if (support === 'encrypted') return { status: 'encrypted', entries, message: 'encrypted' }
    if (support === 'container_unsupported') {
      return unsupported(entries, `unsupported_method_${record.method}`)
    }

    const path = normalizeArchivePath(record.name, limits.maxPathDepth)
    const entryLimit = checkArchiveLimits(
      {
        entries: entries.length + 1,
        entryUncompressed: 0,
        totalUncompressed: streamState.totalUncompressed,
        compressedConsumed: streamState.compressedConsumed,
        pathDepth: path.depth,
      },
      limits,
    )
    if (entryLimit) {
      return { status: 'limit_reached', limitKey: entryLimit, entries, message: entryLimit }
    }

    streamState.entryUncompressed = 0
    streamState.entryCompressedStart = streamState.compressedConsumed
    streamState.crc = 0xffffffff
    streamState.terminal = null
    const structureEnd = nextStructureByOffset.get(record.localOffset) ?? centralOffset
    const consumed = consumeZipEntry(buf, view, record, structureEnd, streamState, limits)
    if (consumed) return consumed

    entries.push({
      name: record.name,
      size: streamState.entryUncompressed,
      declaredSize: record.uncompressedSize,
      mtime: dosToIso(record.dosDate, record.dosTime),
      isDirectory: record.name.endsWith('/'),
      suspicious: path.suspicious,
      suspiciousReasons: path.reasons,
      unparsable: false,
      method: record.method,
    })
  }

  return { status: 'ok', entries }
}

function consumeZipEntry(
  buf: Uint8Array,
  view: DataView,
  record: ZipCentralEntry,
  structureEnd: number,
  state: ZipStreamState,
  limits: ArchiveLimits,
): ArchiveParseResult | null {
  const localOffset = record.localOffset
  if (!rangeFits(localOffset, 30, structureEnd)) return parseFailure(state.entries, 'local_header_truncated')
  if (readU32(view, localOffset) !== 0x04034b50) return parseFailure(state.entries, 'local_sig')

  const localFlags = readU16(view, localOffset + 6)
  const localMethod = readU16(view, localOffset + 8)
  if (localFlags !== record.flags) return parseFailure(state.entries, 'local_flags_mismatch')
  if (localMethod !== record.method) return parseFailure(state.entries, 'local_method_mismatch')

  const localCrc = readU32(view, localOffset + 14)
  const localCompressedSize = readU32(view, localOffset + 18)
  const localUncompressedSize = readU32(view, localOffset + 22)

  const localNameLength = readU16(view, localOffset + 26)
  const localExtraLength = readU16(view, localOffset + 28)
  const localVariableLength = localNameLength + localExtraLength
  if (!rangeFits(localOffset + 30, localVariableLength, structureEnd)) {
    return parseFailure(state.entries, 'local_record_oob')
  }
  const localName = buf.subarray(localOffset + 30, localOffset + 30 + localNameLength)
  if (!sameBytes(localName, record.nameBytes)) return parseFailure(state.entries, 'local_name_mismatch')

  const usesDescriptor = !!(record.flags & 0x8)
  if (usesDescriptor) {
    if (localCrc !== 0 && localCrc !== record.crc) {
      return parseFailure(state.entries, 'local_crc_mismatch')
    }
    if (localCompressedSize !== 0 && localCompressedSize !== record.compressedSize) {
      return parseFailure(state.entries, 'local_compressed_size_mismatch')
    }
    if (localUncompressedSize !== 0 && localUncompressedSize !== record.uncompressedSize) {
      return parseFailure(state.entries, 'local_uncompressed_size_mismatch')
    }
  } else {
    if (localCrc !== record.crc) return parseFailure(state.entries, 'local_crc_mismatch')
    if (localCompressedSize !== record.compressedSize) {
      return parseFailure(state.entries, 'local_compressed_size_mismatch')
    }
    if (localUncompressedSize !== record.uncompressedSize) {
      return parseFailure(state.entries, 'local_uncompressed_size_mismatch')
    }
  }

  const dataStart = localOffset + 30 + localVariableLength
  if (!rangeFits(dataStart, record.compressedSize, structureEnd)) {
    return parseFailure(state.entries, 'entry_data_overlaps_structure')
  }
  const dataEnd = dataStart + record.compressedSize
  if (usesDescriptor) {
    const descriptorBytes = structureEnd - dataEnd
    let descriptorOffset = dataEnd
    if (descriptorBytes === 16 && readU32(view, descriptorOffset) === 0x08074b50) {
      descriptorOffset += 4
    } else if (descriptorBytes !== 12) {
      return parseFailure(state.entries, 'data_descriptor_layout')
    }
    if (
      readU32(view, descriptorOffset) !== record.crc ||
      readU32(view, descriptorOffset + 4) !== record.compressedSize ||
      readU32(view, descriptorOffset + 8) !== record.uncompressedSize
    ) {
      return parseFailure(state.entries, 'data_descriptor_mismatch')
    }
  } else if (dataEnd !== structureEnd) {
    return parseFailure(state.entries, 'entry_layout')
  }

  if (record.method === 0) {
    for (let offset = dataStart; offset < dataEnd && !state.terminal; offset += ARCHIVE_STREAM_CHUNK_BYTES) {
      const chunk = buf.subarray(offset, Math.min(dataEnd, offset + ARCHIVE_STREAM_CHUNK_BYTES))
      state.compressedConsumed += chunk.length
      consumeZipOutput(chunk, state, limits)
    }
  } else if (record.method === 8) {
    let inflateFinal = false
    let pushedBytes = 0
    const compressedBase = state.compressedConsumed
    const pendingOutput: Uint8Array[] = []
    const inflater = new Inflate((chunk, final) => {
      pendingOutput.push(chunk)
      if (final) inflateFinal = true
    })
    try {
      const pushChunk = (start: number, end: number, final: boolean): ArchiveParseResult | null => {
        pushedBytes += end - start
        inflater.push(buf.subarray(start, end), final)
        const unread = unreadDeflateWholeBytes(inflater)
        if (unread === null) return parseFailure(state.entries, 'deflate_runtime_shape')
        state.compressedConsumed = compressedBase + pushedBytes - unread
        for (const output of pendingOutput.splice(0)) {
          if (!state.terminal) consumeZipOutput(output, state, limits)
        }
        return null
      }
      if (dataStart === dataEnd) {
        const runtimeFailure = pushChunk(dataStart, dataEnd, true)
        if (runtimeFailure) return runtimeFailure
      } else {
        for (let offset = dataStart; offset < dataEnd && !state.terminal; offset += ARCHIVE_STREAM_CHUNK_BYTES) {
          const end = Math.min(dataEnd, offset + ARCHIVE_STREAM_CHUNK_BYTES)
          const runtimeFailure = pushChunk(offset, end, end === dataEnd)
          if (runtimeFailure) return runtimeFailure
        }
      }
    } catch {
      if (!state.terminal) return parseFailure(state.entries, 'deflate_inflate')
    }
    if (state.terminal) return state.terminal
    if (!inflateFinal) return parseFailure(state.entries, 'deflate_truncated')
    const unread = unreadDeflateWholeBytes(inflater)
    if (unread === null) return parseFailure(state.entries, 'deflate_runtime_shape')
    if (unread !== 0) return parseFailure(state.entries, 'deflate_trailing_data')
  } else {
    return unsupported(state.entries, `unsupported_method_${record.method}`)
  }

  if (state.terminal) return state.terminal
  if (state.entryUncompressed !== record.uncompressedSize) {
    return parseFailure(state.entries, 'uncompressed_size_mismatch')
  }
  if ((~state.crc >>> 0) !== record.crc) return parseFailure(state.entries, 'crc_mismatch')
  return null
}

function consumeZipOutput(chunk: Uint8Array, state: ZipStreamState, limits: ArchiveLimits): void {
  for (let offset = 0; offset < chunk.length && !state.terminal; offset += ARCHIVE_STREAM_CHUNK_BYTES) {
    const piece = chunk.subarray(offset, Math.min(chunk.length, offset + ARCHIVE_STREAM_CHUNK_BYTES))
    state.crc = updateCrc32(state.crc, piece)
    state.entryUncompressed += piece.length
    state.totalUncompressed += piece.length
    const limitKey = checkArchiveLimits(
      {
        entries: state.entries.length + 1,
        entryUncompressed: state.entryUncompressed,
        totalUncompressed: state.totalUncompressed,
        compressedConsumed: state.compressedConsumed,
        entryCompressedConsumed: state.compressedConsumed - state.entryCompressedStart,
        pathDepth: 0,
      },
      limits,
    )
    if (limitKey) {
      state.terminal = {
        status: 'limit_reached',
        limitKey,
        entries: state.entries,
        message: limitKey,
      }
    }
  }
}

function unixSecondsToIso(seconds: number): string | null {
  if (!Number.isFinite(seconds) || seconds < 0) return null
  const millis = seconds * 1000
  if (!Number.isFinite(millis)) return null
  try {
    return new Date(millis).toISOString()
  } catch {
    return null
  }
}

function dosToIso(dosDate: number, dosTime: number): string | null {
  if (!dosDate && !dosTime) return null
  const year = ((dosDate >> 9) & 0x7f) + 1980
  const month = (dosDate >> 5) & 0x0f
  const day = dosDate & 0x1f
  const hour = (dosTime >> 11) & 0x1f
  const min = (dosTime >> 5) & 0x3f
  const sec = (dosTime & 0x1f) * 2
  if (month < 1 || month > 12 || day < 1) return null
  return `${year.toString().padStart(4, '0')}-${month.toString().padStart(2, '0')}-${day
    .toString()
    .padStart(2, '0')}T${hour.toString().padStart(2, '0')}:${min.toString().padStart(2, '0')}:${sec
    .toString()
    .padStart(2, '0')}`
}

const TAR_EXTENSION_MAX_BYTES = 64 * 1024

type TarExtensionKind = 'pax_local' | 'pax_global' | 'gnu_long_name' | 'gnu_long_link'

interface TarOverrides {
  path?: string
  linkpath?: string
  mtime?: string
}

interface PendingTarEntry {
  meta: ArchiveEntryMeta | null
  bodyCountsTowardLimits: boolean
  extensionKind?: TarExtensionKind
  extensionData?: Uint8Array
  extensionUsed: number
}

interface TarStreamState {
  entries: ArchiveEntryMeta[]
  limits: ArchiveLimits
  requireUstarFirst: boolean
  header: Uint8Array
  headerUsed: number
  phase: 'header' | 'data' | 'padding' | 'done'
  dataRemaining: number
  paddingRemaining: number
  currentEntryRead: number
  totalUncompressed: number
  compressedConsumed: number
  zeroBlocks: number
  sawNonZeroHeader: boolean
  pending: PendingTarEntry | null
  globalPax: TarOverrides
  nextPax: TarOverrides
  nextLongName: string | null
  nextLongLink: string | null
  terminal: ArchiveParseResult | null
}

function createTarStreamState(limits: ArchiveLimits, requireUstarFirst: boolean): TarStreamState {
  return {
    entries: [],
    limits,
    requireUstarFirst,
    header: new Uint8Array(512),
    headerUsed: 0,
    phase: 'header',
    dataRemaining: 0,
    paddingRemaining: 0,
    currentEntryRead: 0,
    totalUncompressed: 0,
    compressedConsumed: 0,
    zeroBlocks: 0,
    sawNonZeroHeader: false,
    pending: null,
    globalPax: {},
    nextPax: {},
    nextLongName: null,
    nextLongLink: null,
    terminal: null,
  }
}

function feedTarOutput(state: TarStreamState, chunk: Uint8Array): void {
  let offset = 0
  while (offset < chunk.length && !state.terminal) {
    if (state.phase === 'done') {
      for (; offset < chunk.length; offset++) {
        if (chunk[offset] !== 0) {
          state.terminal = parseFailure(state.entries, 'tar_trailing_data')
          return
        }
      }
      return
    }

    if (state.phase === 'header') {
      const take = Math.min(512 - state.headerUsed, chunk.length - offset)
      state.header.set(chunk.subarray(offset, offset + take), state.headerUsed)
      state.headerUsed += take
      offset += take
      if (state.headerUsed === 512) parseTarHeader(state)
      continue
    }

    if (state.phase === 'padding') {
      const take = Math.min(state.paddingRemaining, chunk.length - offset)
      state.paddingRemaining -= take
      offset += take
      if (state.paddingRemaining === 0) {
        state.phase = 'header'
        state.headerUsed = 0
      }
      continue
    }

    const step = Math.min(
      state.dataRemaining,
      chunk.length - offset,
      ARCHIVE_STREAM_CHUNK_BYTES,
    )
    if (step <= 0) {
      finishTarEntry(state)
      continue
    }
    if (state.pending?.extensionData) {
      state.pending.extensionData.set(
        chunk.subarray(offset, offset + step),
        state.pending.extensionUsed,
      )
      state.pending.extensionUsed += step
    } else if (state.pending?.bodyCountsTowardLimits) {
      state.currentEntryRead += step
      state.totalUncompressed += step
      const limitKey = checkArchiveLimits(
        {
          entries: state.entries.length + 1,
          entryUncompressed: state.currentEntryRead,
          totalUncompressed: state.totalUncompressed,
          compressedConsumed: state.compressedConsumed,
          pathDepth: 0,
        },
        state.limits,
      )
      if (limitKey) {
        state.terminal = {
          status: 'limit_reached',
          limitKey,
          entries: state.entries,
          message: limitKey,
        }
        return
      }
    }
    state.dataRemaining -= step
    offset += step
    if (state.dataRemaining === 0) finishTarEntry(state)
  }
}

function parseTarHeader(state: TarStreamState): void {
  const header = state.header
  let allZero = true
  for (let i = 0; i < header.length; i++) {
    if (header[i] !== 0) {
      allZero = false
      break
    }
  }
  if (allZero) {
    state.zeroBlocks += 1
    state.headerUsed = 0
    state.header.fill(0)
    if (state.zeroBlocks >= 2) state.phase = 'done'
    return
  }
  if (state.zeroBlocks > 0) {
    state.terminal = parseFailure(state.entries, 'tar_end_blocks')
    return
  }

  const magic = String.fromCharCode(...header.subarray(257, 262))
  if (!state.sawNonZeroHeader && state.requireUstarFirst && magic !== 'ustar') {
    state.terminal = { status: 'format_mismatch', entries: [], message: 'gzip_not_tar' }
    return
  }

  let checksumSum = 0
  for (let i = 0; i < 512; i++) checksumSum += i >= 148 && i < 156 ? 32 : header[i]
  const checksum = parseTarOctal(header.subarray(148, 156))
  if (checksum === null || checksum !== checksumSum) {
    state.terminal = parseFailure(state.entries, 'tar_checksum')
    return
  }
  const size = parseTarOctal(header.subarray(124, 136))
  if (size === null) {
    state.terminal = parseFailure(state.entries, 'tar_size')
    return
  }

  const name = decodeTarText(header.subarray(0, 100))
  const prefix = decodeTarText(header.subarray(345, 500))
  const headerName = prefix ? `${prefix}/${name}` : name
  const typeflag = String.fromCharCode(header[156] || 0x30)
  const extensionKinds: Partial<Record<string, TarExtensionKind>> = {
    x: 'pax_local',
    g: 'pax_global',
    L: 'gnu_long_name',
    K: 'gnu_long_link',
  }
  const extensionKind = extensionKinds[typeflag]
  if (typeflag === 'S') {
    state.terminal = unsupported(state.entries, 'tar_sparse')
    return
  }
  if (!extensionKind && !['0', '1', '2', '5', '7'].includes(typeflag)) {
    state.terminal = unsupported(state.entries, 'tar_extension_type')
    return
  }
  if (extensionKind) {
    if (size > TAR_EXTENSION_MAX_BYTES) {
      state.terminal = unsupported(state.entries, 'tar_extension_too_large')
      return
    }
    state.pending = {
      meta: null,
      bodyCountsTowardLimits: false,
      extensionKind,
      extensionData: new Uint8Array(size),
      extensionUsed: 0,
    }
    state.sawNonZeroHeader = true
    beginTarBody(state, size)
    return
  }

  const fullName = state.nextPax.path ?? state.nextLongName ?? state.globalPax.path ?? headerName
  const headerMtime = parseTarOctal(header.subarray(136, 148))
  if (headerMtime === null) {
    state.terminal = parseFailure(state.entries, 'tar_mtime')
    return
  }
  const mtime = parsePaxMtime(state.nextPax.mtime ?? state.globalPax.mtime) ?? unixSecondsToIso(headerMtime)
  const isDirectory = typeflag === '5' || fullName.endsWith('/')
  if (isDirectory && size !== 0) {
    state.terminal = parseFailure(state.entries, 'tar_directory_size')
    return
  }
  const path = normalizeArchivePath(fullName, state.limits.maxPathDepth)
  const initialLimit = checkArchiveLimits(
    {
      entries: state.entries.length + 1,
      entryUncompressed: size,
      totalUncompressed: state.totalUncompressed + size,
      compressedConsumed: Math.max(1, state.compressedConsumed),
      pathDepth: path.depth,
    },
    state.limits,
  )
  if (initialLimit && initialLimit !== 'maxCompressionRatio') {
    state.terminal = {
      status: 'limit_reached',
      limitKey: initialLimit,
      entries: state.entries,
      message: initialLimit,
    }
    return
  }

  state.pending = {
    bodyCountsTowardLimits: true,
    extensionUsed: 0,
    meta: {
      name: fullName,
      size: isDirectory ? 0 : size,
      declaredSize: size,
      mtime,
      isDirectory,
      suspicious: path.suspicious || typeflag === '2' || typeflag === '1',
      suspiciousReasons: [
        ...path.reasons,
        ...(typeflag === '2' || typeflag === '1' ? ['link_not_followed'] : []),
      ],
      unparsable: false,
      method: null,
    },
  }
  state.nextPax = {}
  state.nextLongName = null
  state.nextLongLink = null
  state.sawNonZeroHeader = true
  beginTarBody(state, size)
}

function beginTarBody(state: TarStreamState, size: number): void {
  state.currentEntryRead = 0
  state.dataRemaining = size
  state.paddingRemaining = (512 - (size % 512)) % 512
  state.headerUsed = 0
  state.header.fill(0)
  state.phase = 'data'
  if (state.dataRemaining === 0) finishTarEntry(state)
}

function finishTarEntry(state: TarStreamState): void {
  const pending = state.pending
  if (!pending) {
    state.terminal = parseFailure(state.entries, 'tar_state')
    return
  }
  if (pending.extensionKind) {
    applyTarExtension(state, pending)
  } else if (pending.meta) {
    state.entries.push(pending.meta)
  } else {
    state.terminal = parseFailure(state.entries, 'tar_state')
  }
  state.pending = null
  if (state.terminal) return
  state.phase = state.paddingRemaining > 0 ? 'padding' : 'header'
  state.headerUsed = 0
}

function parseTarOctal(bytes: Uint8Array): number | null {
  const value = decodeTarText(bytes).trim()
  if (!value) return 0
  if (!/^[0-7]+$/.test(value)) return null
  const parsed = Number.parseInt(value, 8)
  return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : null
}

function decodeTarText(bytes: Uint8Array): string {
  let end = bytes.indexOf(0)
  if (end < 0) end = bytes.length
  return new TextDecoder('utf-8', { fatal: false }).decode(bytes.subarray(0, end))
}

function parsePaxMtime(value: string | undefined): string | null {
  if (value === undefined) return null
  const seconds = Number(value)
  return unixSecondsToIso(seconds)
}

function parsePaxRecords(bytes: Uint8Array): Record<string, string> | null {
  const values: Record<string, string> = {}
  let offset = 0
  while (offset < bytes.length) {
    let space = offset
    while (space < bytes.length && bytes[space] !== 0x20) space += 1
    if (space === bytes.length) return null
    const lengthText = new TextDecoder('ascii').decode(bytes.subarray(offset, space))
    if (!/^[1-9][0-9]*$/.test(lengthText)) return null
    const length = Number(lengthText)
    if (!Number.isSafeInteger(length) || length <= space - offset + 3) return null
    const end = offset + length
    if (end > bytes.length || bytes[end - 1] !== 0x0a) return null
    const record = bytes.subarray(space + 1, end - 1)
    const equals = record.indexOf(0x3d)
    if (equals <= 0) return null
    let key: string
    let value: string
    try {
      const decoder = new TextDecoder('utf-8', { fatal: true })
      key = decoder.decode(record.subarray(0, equals))
      value = decoder.decode(record.subarray(equals + 1))
    } catch {
      return null
    }
    values[key] = value
    offset = end
  }
  return values
}

function applyTarExtension(state: TarStreamState, pending: PendingTarEntry): void {
  const data = pending.extensionData
  if (!data || data.length !== pending.extensionUsed || !pending.extensionKind) {
    state.terminal = parseFailure(state.entries, 'tar_extension_state')
    return
  }
  if (pending.extensionKind === 'gnu_long_name' || pending.extensionKind === 'gnu_long_link') {
    const value = decodeTarText(data).replace(/\n+$/, '')
    if (!value) {
      state.terminal = parseFailure(state.entries, 'tar_long_name')
      return
    }
    if (pending.extensionKind === 'gnu_long_name') state.nextLongName = value
    else state.nextLongLink = value
    return
  }

  const values = parsePaxRecords(data)
  if (!values) {
    state.terminal = parseFailure(state.entries, 'tar_pax_record')
    return
  }
  if (Object.keys(values).some((key) => key.startsWith('GNU.sparse.') || key === 'SCHILY.realsize')) {
    state.terminal = unsupported(state.entries, 'tar_sparse')
    return
  }
  if ('size' in values) {
    state.terminal = unsupported(state.entries, 'tar_pax_size')
    return
  }
  if (values.mtime !== undefined && parsePaxMtime(values.mtime) === null) {
    state.terminal = parseFailure(state.entries, 'tar_pax_mtime')
    return
  }
  const override: TarOverrides = {}
  if (values.path !== undefined) override.path = values.path
  if (values.linkpath !== undefined) override.linkpath = values.linkpath
  if (values.mtime !== undefined) override.mtime = values.mtime
  if (pending.extensionKind === 'pax_global') {
    state.globalPax = { ...state.globalPax, ...override }
  } else {
    state.nextPax = { ...state.nextPax, ...override }
  }
}

function finishTarStream(state: TarStreamState): ArchiveParseResult {
  if (state.terminal) return state.terminal
  if (state.phase === 'data') return parseFailure(state.entries, 'tar_data_oob')
  if (state.phase === 'padding') return parseFailure(state.entries, 'tar_padding_truncated')
  if (state.phase === 'header' && state.headerUsed > 0) {
    if (state.requireUstarFirst && !state.sawNonZeroHeader) {
      return { status: 'format_mismatch', entries: [], message: 'gzip_not_tar' }
    }
    return parseFailure(state.entries, 'tar_header_truncated')
  }
  if (state.phase !== 'done' || state.zeroBlocks < 2) {
    if (state.requireUstarFirst && !state.sawNonZeroHeader) {
      return { status: 'format_mismatch', entries: [], message: 'gzip_not_tar' }
    }
    return parseFailure(state.entries, 'tar_end_missing')
  }
  return { status: 'ok', entries: state.entries }
}

function parseTar(buf: Uint8Array, limits: ArchiveLimits): ArchiveParseResult {
  const state = createTarStreamState(limits, false)
  for (let offset = 0; offset < buf.length && !state.terminal; offset += ARCHIVE_STREAM_CHUNK_BYTES) {
    const chunk = buf.subarray(offset, Math.min(buf.length, offset + ARCHIVE_STREAM_CHUNK_BYTES))
    state.compressedConsumed += chunk.length
    feedTarOutput(state, chunk)
  }
  return finishTarStream(state)
}

function parseGzipTar(buf: Uint8Array, limits: ArchiveLimits): ArchiveParseResult {
  const frame = parseSingleGzipFrame(buf)
  if (typeof frame === 'string') return parseFailure([], frame)

  const state = createTarStreamState(limits, true)
  let gzipFinal = false
  let gzipCrc = 0xffffffff
  let gzipOutputBytes = 0
  let pushedBytes = 0
  const pendingOutput: Uint8Array[] = []
  const inflater = new Inflate((chunk, final) => {
    pendingOutput.push(chunk)
    if (final) gzipFinal = true
  })

  try {
    for (
      let offset = frame.payloadStart;
      offset < frame.payloadEnd && !state.terminal;
      offset += ARCHIVE_STREAM_CHUNK_BYTES
    ) {
      const end = Math.min(frame.payloadEnd, offset + ARCHIVE_STREAM_CHUNK_BYTES)
      pushedBytes += end - offset
      inflater.push(buf.subarray(offset, end), end === frame.payloadEnd)
      const unread = unreadDeflateWholeBytes(inflater)
      if (unread === null) return parseFailure(state.entries, 'gzip_runtime_shape')
      state.compressedConsumed = pushedBytes - unread
      for (const output of pendingOutput.splice(0)) {
        if (state.terminal) break
        gzipCrc = updateCrc32(gzipCrc, output)
        gzipOutputBytes += output.length
        feedTarOutput(state, output)
      }
    }
  } catch {
    if (!state.terminal) return parseFailure(state.entries, 'gzip_inflate')
  }
  if (state.terminal) return state.terminal
  if (!gzipFinal) return parseFailure(state.entries, 'gzip_truncated')
  const unread = unreadDeflateWholeBytes(inflater)
  if (unread === null) return parseFailure(state.entries, 'gzip_runtime_shape')
  if (unread !== 0) return parseFailure(state.entries, 'gzip_trailing_data')
  if ((~gzipCrc >>> 0) !== frame.expectedCrc) {
    return parseFailure(state.entries, 'gzip_crc_mismatch')
  }
  if ((gzipOutputBytes >>> 0) !== frame.expectedSize) {
    return parseFailure(state.entries, 'gzip_isize_mismatch')
  }
  return finishTarStream(state)
}

function parseGzipFile(buf: Uint8Array, limits: ArchiveLimits): ArchiveParseResult {
  const frame = parseSingleGzipFrame(buf)
  if (typeof frame === 'string') return parseFailure([], frame)

  const name = frame.fileName || 'compressed-data'
  const path = normalizeArchivePath(name, limits.maxPathDepth)
  const pathLimit = checkArchiveLimits(
    {
      entries: 1,
      entryUncompressed: 0,
      totalUncompressed: 0,
      compressedConsumed: 1,
      entryCompressedConsumed: 1,
      pathDepth: path.depth,
    },
    limits,
  )
  if (pathLimit) {
    return { status: 'limit_reached', limitKey: pathLimit, entries: [], message: pathLimit }
  }

  let finalSeen = false
  let crc = 0xffffffff
  let outputBytes = 0
  let pushedBytes = 0
  let terminal: ArchiveParseResult | null = null
  const pendingOutput: Uint8Array[] = []
  const inflater = new Inflate((chunk, final) => {
    pendingOutput.push(chunk)
    if (final) finalSeen = true
  })

  try {
    for (
      let offset = frame.payloadStart;
      offset < frame.payloadEnd && !terminal;
      offset += ARCHIVE_STREAM_CHUNK_BYTES
    ) {
      const end = Math.min(frame.payloadEnd, offset + ARCHIVE_STREAM_CHUNK_BYTES)
      pushedBytes += end - offset
      inflater.push(buf.subarray(offset, end), end === frame.payloadEnd)
      const unread = unreadDeflateWholeBytes(inflater)
      if (unread === null) return parseFailure([], 'gzip_runtime_shape')
      const compressedConsumed = pushedBytes - unread
      for (const output of pendingOutput.splice(0)) {
        for (let chunkOffset = 0; chunkOffset < output.length && !terminal; chunkOffset += ARCHIVE_STREAM_CHUNK_BYTES) {
          const piece = output.subarray(
            chunkOffset,
            Math.min(output.length, chunkOffset + ARCHIVE_STREAM_CHUNK_BYTES),
          )
          crc = updateCrc32(crc, piece)
          outputBytes += piece.length
          const limitKey = checkArchiveLimits(
            {
              entries: 1,
              entryUncompressed: outputBytes,
              totalUncompressed: outputBytes,
              compressedConsumed,
              entryCompressedConsumed: compressedConsumed,
              pathDepth: path.depth,
            },
            limits,
          )
          if (limitKey) {
            terminal = { status: 'limit_reached', limitKey, entries: [], message: limitKey }
          }
        }
      }
    }
  } catch {
    return terminal ?? parseFailure([], 'gzip_inflate')
  }
  if (terminal) return terminal
  if (!finalSeen) return parseFailure([], 'gzip_truncated')
  const unread = unreadDeflateWholeBytes(inflater)
  if (unread === null) return parseFailure([], 'gzip_runtime_shape')
  if (unread !== 0) return parseFailure([], 'gzip_trailing_data')
  if ((~crc >>> 0) !== frame.expectedCrc) return parseFailure([], 'gzip_crc_mismatch')
  if ((outputBytes >>> 0) !== frame.expectedSize) return parseFailure([], 'gzip_isize_mismatch')

  return {
    status: 'ok',
    entries: [{
      name,
      size: outputBytes,
      declaredSize: frame.expectedSize,
      mtime: frame.mtime,
      isDirectory: false,
      suspicious: path.suspicious,
      suspiciousReasons: path.reasons,
      unparsable: false,
      method: 8,
    }],
  }
}