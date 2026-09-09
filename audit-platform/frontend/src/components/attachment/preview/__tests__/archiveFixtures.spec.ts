import { describe, it, expect, vi } from 'vitest'
import { Inflate, gzipSync, strToU8 } from 'fflate'
import {
  ALL_FIXTURE_IDS,
  buildClassicZip,
  buildUstarTar,
  generateFixture,
  type ZipEntrySpec,
} from '../archive/archiveFixtures'
import {
  ARCHIVE_STREAM_CHUNK_BYTES,
  parseArchiveBytes,
} from '../archive/archiveContainer'
import { ARCHIVE_LIMITS } from '../archive/archiveLimits'

/** 稳定短 digest，避免依赖 node:crypto（jsdom） */
function digest(buf: Uint8Array): string {
  let h = 2166136261
  for (let i = 0; i < buf.length; i++) {
    h ^= buf[i]
    h = Math.imul(h, 16777619)
  }
  return (h >>> 0).toString(16).padStart(8, '0') + ':' + buf.length
}

function toAb(bytes: Uint8Array): ArrayBuffer {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
}

function concatBytes(...parts: Uint8Array[]): Uint8Array {
  const out = new Uint8Array(parts.reduce((sum, part) => sum + part.length, 0))
  let offset = 0
  for (const part of parts) {
    out.set(part, offset)
    offset += part.length
  }
  return out
}

function paxRecord(key: string, value: string): Uint8Array {
  const encoder = new TextEncoder()
  let length = encoder.encode(` ${key}=${value}\n`).length + 1
  while (true) {
    const record = encoder.encode(`${length} ${key}=${value}\n`)
    if (record.length === length) return record
    length = record.length
  }
}

function writeU16(bytes: Uint8Array, offset: number, value: number): void {
  bytes[offset] = value & 0xff
  bytes[offset + 1] = (value >>> 8) & 0xff
}

function writeU32(bytes: Uint8Array, offset: number, value: number): void {
  bytes[offset] = value & 0xff
  bytes[offset + 1] = (value >>> 8) & 0xff
  bytes[offset + 2] = (value >>> 16) & 0xff
  bytes[offset + 3] = (value >>> 24) & 0xff
}

function deterministicBytes(length: number): Uint8Array {
  const out = new Uint8Array(length)
  let state = 0x6d2b79f5
  for (let i = 0; i < out.length; i++) {
    state ^= state << 13
    state ^= state >>> 17
    state ^= state << 5
    out[i] = state & 0xff
  }
  return out
}

const unlimitedRatio = {
  ...ARCHIVE_LIMITS,
  maxEntryUncompressedBytes: 1,
  maxTotalUncompressedBytes: Number.MAX_SAFE_INTEGER,
  maxCompressionRatio: Number.MAX_SAFE_INTEGER,
}

describe('archive fixtures corpus', () => {
  it('全部夹具可生成且 digest 稳定', () => {
    const digests: Record<string, string> = {}
    const heavy = new Set(['zip_many_entries_over', 'zip_entry_uncompressed_over', 'zip_total_uncompressed_over'])
    for (const id of ALL_FIXTURE_IDS) {
      if (heavy.has(id)) continue
      const a = generateFixture(id)
      const b = generateFixture(id)
      expect(digest(a.bytes)).toBe(digest(b.bytes))
      digests[id] = digest(a.bytes)
      expect(a.bytes.byteLength).toBeGreaterThan(0)
    }
    expect(Object.keys(digests).length).toBeGreaterThan(10)
  })

  it('utf8 zip 可解析且 size 为实际值', () => {
    const { bytes } = generateFixture('zip_utf8_ok')
    const r = parseArchiveBytes(toAb(bytes))
    expect(r.status).toBe('ok')
    expect(r.entries[0].name).toContain('发票')
    expect(r.entries[0].size).toBe(5)
  })

  it('穿越路径标记 suspicious', () => {
    for (const id of ['zip_traversal_dotdot', 'zip_drive_path', 'zip_absolute'] as const) {
      const { bytes } = generateFixture(id)
      const r = parseArchiveBytes(toAb(bytes))
      expect(r.entries.some((e) => e.suspicious)).toBe(true)
    }
  })

  it('加密 bit → encrypted', () => {
    const { bytes } = generateFixture('zip_encrypted_flag')
    expect(parseArchiveBytes(toAb(bytes)).status).toBe('encrypted')
  })

  it('伪声明 size 是容器结构失败，不接受歧义元数据', () => {
    const { bytes } = generateFixture('zip_fake_declared_size')
    const r = parseArchiveBytes(toAb(bytes))
    expect(r.status).toBe('parse_failed')
    expect(r.message).toBe('uncompressed_size_mismatch')
  })

  it('unsupported method → container_unsupported', () => {
    const { bytes } = generateFixture('zip_method99_aes')
    expect(parseArchiveBytes(toAb(bytes)).status).toBe('container_unsupported')
  })

  it('classic data descriptor 有/无签名、stored/deflate 均安全解析', () => {
    for (const method of [0, 8] as const) {
      for (const dataDescriptorSignature of [true, false]) {
        const bytes = buildClassicZip([
          {
            name: `descriptor-${method}-${dataDescriptorSignature}.txt`,
            data: strToU8('descriptor payload'),
            method,
            generalPurposeBitFlag: 0x8,
            dataDescriptorSignature,
          },
        ])
        expect(parseArchiveBytes(toAb(bytes))).toMatchObject({ status: 'ok' })
      }
    }
  })

  it('classic data descriptor 字段、布局或边界不闭合时 fail closed', () => {
    const mismatch = buildClassicZip([
      {
        name: 'descriptor.txt',
        data: strToU8('x'),
        method: 0,
        generalPurposeBitFlag: 0x8,
        descriptorCrc: 0x12345678,
      },
    ])
    expect(parseArchiveBytes(toAb(mismatch))).toMatchObject({
      status: 'parse_failed',
      message: 'data_descriptor_mismatch',
    })

    const gap = buildClassicZip([
      {
        name: 'descriptor-gap.txt',
        data: strToU8('x'),
        method: 0,
        generalPurposeBitFlag: 0x8,
        gapAfterEntry: new Uint8Array([0]),
      },
    ])
    expect(parseArchiveBytes(toAb(gap))).toMatchObject({
      status: 'parse_failed',
      message: 'data_descriptor_layout',
    })
  })

  it('截断 EOCD → parse_failed', () => {
    const { bytes } = generateFixture('zip_truncated_eocd')
    expect(parseArchiveBytes(toAb(bytes)).status).toBe('parse_failed')
  })

  it('EOCD comment 必须精确闭合，disk entry 数必须一致', () => {
    const base = buildClassicZip([{ name: 'a.txt', data: strToU8('x'), method: 0 }])
    const malformedComment = new Uint8Array(base)
    writeU16(malformedComment, malformedComment.length - 2, 1)
    const commentResult = parseArchiveBytes(toAb(malformedComment))
    expect(commentResult.status).toBe('parse_failed')
    expect(commentResult.message).toBe('eocd_comment_length')

    const countMismatch = new Uint8Array(base)
    const eocd = countMismatch.length - 22
    writeU16(countMismatch, eocd + 8, 0)
    const countResult = parseArchiveBytes(toAb(countMismatch))
    expect(countResult.status).toBe('parse_failed')
    expect(countResult.message).toBe('disk_entry_count_mismatch')
  })

  it('central 区间与消费长度必须精确', () => {
    const base = buildClassicZip([{ name: 'a.txt', data: strToU8('x'), method: 0 }])
    const layout = new Uint8Array(base)
    const layoutEocd = layout.length - 22
    const centralSize = layout[layoutEocd + 12] | (layout[layoutEocd + 13] << 8)
    writeU32(layout, layoutEocd + 12, centralSize - 1)
    const layoutResult = parseArchiveBytes(toAb(layout))
    expect(layoutResult.status).toBe('parse_failed')
    expect(layoutResult.message).toBe('central_layout')

    const consumption = new Uint8Array(base)
    const consumptionEocd = consumption.length - 22
    writeU16(consumption, consumptionEocd + 8, 0)
    writeU16(consumption, consumptionEocd + 10, 0)
    const consumptionResult = parseArchiveBytes(toAb(consumption))
    expect(consumptionResult.status).toBe('parse_failed')
    expect(consumptionResult.message).toBe('central_consumption_mismatch')
  })

  it('local/central flags、method、name、CRC、size 任一不一致均容器级失败', () => {
    const cases: Array<{ override: Partial<ZipEntrySpec>; message: string }> = [
      { override: { localGeneralPurposeBitFlag: 0x800 }, message: 'local_flags_mismatch' },
      { override: { localMethod: 8 }, message: 'local_method_mismatch' },
      { override: { localName: 'other.txt' }, message: 'local_name_mismatch' },
      { override: { localCrc: 0x12345678 }, message: 'local_crc_mismatch' },
      { override: { localDeclaredCompressed: 2 }, message: 'local_compressed_size_mismatch' },
      { override: { localDeclaredUncompressed: 2 }, message: 'local_uncompressed_size_mismatch' },
    ]
    for (const testCase of cases) {
      const bytes = buildClassicZip([
        { name: 'a.txt', data: strToU8('x'), method: 0, ...testCase.override },
      ])
      const r = parseArchiveBytes(toAb(bytes))
      expect(r.status, testCase.message).toBe('parse_failed')
      expect(r.message).toBe(testCase.message)
    }

    const fixture = generateFixture('zip_local_central_mismatch')
    expect(parseArchiveBytes(toAb(fixture.bytes)).message).toBe('local_name_mismatch')
  })

  it('local/data 不得覆盖下一 local 或 central', () => {
    const overCentral = buildClassicZip([
      { name: 'a.txt', data: strToU8('x'), method: 0, declaredCompressed: 100 },
    ])
    expect(parseArchiveBytes(toAb(overCentral))).toMatchObject({
      status: 'parse_failed',
      message: 'entry_data_overlaps_structure',
    })

    const overNextLocal = buildClassicZip([
      { name: 'a.txt', data: strToU8('x'), method: 0, declaredCompressed: 100 },
      { name: 'b.txt', data: strToU8('y'), method: 0 },
    ])
    expect(parseArchiveBytes(toAb(overNextLocal))).toMatchObject({
      status: 'parse_failed',
      message: 'entry_data_overlaps_structure',
    })
  })

  it('entry 数据跨度必须与下一结构精确闭合', () => {
    const hiddenGap = buildClassicZip([
      {
        name: 'gap.txt',
        data: strToU8('x'),
        method: 0,
        gapAfterEntry: new Uint8Array([0xde, 0xad]),
      },
    ])
    expect(parseArchiveBytes(toAb(hiddenGap))).toMatchObject({
      status: 'parse_failed',
      message: 'entry_layout',
    })

    const deflateTrailingGarbage = buildClassicZip([
      {
        name: 'trailing.bin',
        data: deterministicBytes(128),
        method: 8,
        compressedSuffix: new Uint8Array([0xde, 0xad, 0xbe, 0xef]),
      },
    ])
    expect(parseArchiveBytes(toAb(deflateTrailingGarbage))).toMatchObject({
      status: 'parse_failed',
      message: 'deflate_trailing_data',
    })
  })

  it('复用 zip_bad_crc：实际 CRC 失败必须容器级 parse_failed', () => {
    const { bytes } = generateFixture('zip_bad_crc')
    const r = parseArchiveBytes(toAb(bytes))
    expect(r.status).toBe('parse_failed')
    expect(r.message).toBe('crc_mismatch')
    expect(r.entries).toHaveLength(0)
  })

  it('stored 命中限额后不进入最终 CRC 校验', () => {
    const { bytes } = generateFixture('zip_bad_crc')
    const r = parseArchiveBytes(toAb(bytes), unlimitedRatio)
    expect(r.status).toBe('limit_reached')
    expect(r.limitKey).toBe('maxEntryUncompressedBytes')
  })

  it('path depth 9 在 ZIP/TAR 真实解析中触发 maxPathDepth', () => {
    const { bytes } = generateFixture('zip_path_depth_9')
    expect(parseArchiveBytes(toAb(bytes))).toMatchObject({
      status: 'limit_reached',
      limitKey: 'maxPathDepth',
    })

    const tar = buildUstarTar([
      { name: 'a/b/c/d/e/f/g/h/i.txt', data: strToU8('x') },
    ])
    expect(parseArchiveBytes(toAb(tar))).toMatchObject({
      status: 'limit_reached',
      limitKey: 'maxPathDepth',
    })
  })

  it('TAR 路径门不被头阶段 ratio 遮蔽，普通/PAX/GNU 大正文均 fail closed', () => {
    const deepPath = 'a/b/c/d/e/f/g/h/i.txt'
    const body = new Uint8Array(1024 * 1024)
    const variants = [
      buildUstarTar([{ name: deepPath, data: body }]),
      buildUstarTar([
        { name: 'PaxHeader', data: paxRecord('path', deepPath), typeflag: 'x' },
        { name: 'short.txt', data: body },
      ]),
      buildUstarTar([
        { name: '././@LongLink', data: concatBytes(strToU8(deepPath), new Uint8Array([0])), typeflag: 'L' },
        { name: 'short.txt', data: body },
      ]),
    ]
    for (const bytes of variants) {
      expect(parseArchiveBytes(toAb(bytes))).toMatchObject({
        status: 'limit_reached',
        limitKey: 'maxPathDepth',
      })
    }
  })

  it('maxEntries 触发', () => {
    const { bytes } = generateFixture('zip_many_entries_over')
    const r = parseArchiveBytes(toAb(bytes))
    expect(r.status).toBe('limit_reached')
    expect(r.limitKey).toBe('maxEntries')
  })

  it('ratio 门可用降低阈值触发', () => {
    const { bytes } = generateFixture('zip_ratio_bomb_small')
    const r = parseArchiveBytes(toAb(bytes), { ...ARCHIVE_LIMITS, maxCompressionRatio: 2 })
    expect(r.status).toBe('limit_reached')
    expect(r.limitKey).toBe('maxCompressionRatio')
  })

  it('前置 stored 条目不能稀释后续单条 deflate bomb 的压缩比', () => {
    const bytes = buildClassicZip([
      { name: 'padding.bin', data: deterministicBytes(1024 * 1024), method: 0 },
      { name: 'bomb.bin', data: new Uint8Array(256 * 1024), method: 8 },
    ])
    expect(parseArchiveBytes(toAb(bytes))).toMatchObject({
      status: 'limit_reached',
      limitKey: 'maxCompressionRatio',
    })
  })

  it('deflate 越限后停止继续 push；callback 逻辑超调有界为 4KiB', () => {
    const raw = deterministicBytes(256 * 1024)
    const bytes = buildClassicZip([{ name: 'random.bin', data: raw, method: 8 }])
    const pushSpy = vi.spyOn(Inflate.prototype, 'push')
    try {
      const r = parseArchiveBytes(toAb(bytes), unlimitedRatio)
      expect(r.status).toBe('limit_reached')
      expect(r.limitKey).toBe('maxEntryUncompressedBytes')
      expect(pushSpy.mock.calls.length).toBeLessThan(
        Math.ceil(bytes.length / ARCHIVE_STREAM_CHUNK_BYTES),
      )
    } finally {
      pushSpy.mockRestore()
    }
  })

  it('tar/tgz ok', () => {
    for (const id of ['tar_ok', 'tgz_ok'] as const) {
      const { bytes } = generateFixture(id)
      const r = parseArchiveBytes(toAb(bytes))
      expect(r.status).toBe('ok')
      expect(r.entries.length).toBeGreaterThan(0)
    }
  })

  it('受限 PAX/GNU long-name 只作用于真实条目，并解析 header/PAX mtime', () => {
    const paxPath = '审计/长期/证据/来自-pax.txt'
    const pax = buildUstarTar([
      {
        name: 'PaxHeader',
        data: concatBytes(paxRecord('path', paxPath), paxRecord('mtime', '1700000000.5')),
        typeflag: 'x',
      },
      { name: 'short.txt', data: strToU8('pax') },
    ])
    const paxResult = parseArchiveBytes(toAb(pax))
    expect(paxResult).toMatchObject({ status: 'ok' })
    expect(paxResult.entries).toHaveLength(1)
    expect(paxResult.entries[0]).toMatchObject({
      name: paxPath,
      mtime: '2023-11-14T22:13:20.500Z',
    })

    const longName = `${'long/'.repeat(7)}evidence.txt`
    const gnu = buildUstarTar([
      { name: '././@LongLink', data: concatBytes(strToU8(longName), new Uint8Array([0])), typeflag: 'L' },
      { name: 'short.txt', data: strToU8('gnu'), mtime: 1_700_000_000 },
    ])
    const gnuResult = parseArchiveBytes(toAb(gnu))
    expect(gnuResult).toMatchObject({ status: 'ok' })
    expect(gnuResult.entries).toHaveLength(1)
    expect(gnuResult.entries[0]).toMatchObject({
      name: longName,
      mtime: '2023-11-14T22:13:20.000Z',
    })
  })

  it('TAR sparse、PAX sparse 与异常扩展均 fail closed 为 container_unsupported', () => {
    const sparseType = buildUstarTar([
      { name: 'sparse.bin', data: new Uint8Array(0), typeflag: 'S' },
    ])
    expect(parseArchiveBytes(toAb(sparseType))).toMatchObject({
      status: 'container_unsupported',
      message: 'tar_sparse',
    })

    const sparsePax = buildUstarTar([
      { name: 'PaxHeader', data: paxRecord('GNU.sparse.size', '1000'), typeflag: 'x' },
      { name: 'body.bin', data: strToU8('x') },
    ])
    expect(parseArchiveBytes(toAb(sparsePax))).toMatchObject({
      status: 'container_unsupported',
      message: 'tar_sparse',
    })

    const abnormal = buildUstarTar([
      { name: 'acl', data: new Uint8Array(0), typeflag: 'A' },
    ])
    expect(parseArchiveBytes(toAb(abnormal))).toMatchObject({
      status: 'container_unsupported',
      message: 'tar_extension_type',
    })
  })

  it('gzip trailer CRC、ISIZE、截断与拼接 member 均 fail closed', () => {
    const tar = buildUstarTar([{ name: 'safe.txt', data: strToU8('safe') }])
    const valid = gzipSync(tar)

    const badCrc = new Uint8Array(valid)
    badCrc[badCrc.length - 8] ^= 0xff
    expect(parseArchiveBytes(toAb(badCrc))).toMatchObject({
      status: 'parse_failed',
      message: 'gzip_crc_mismatch',
    })

    const badSize = new Uint8Array(valid)
    badSize[badSize.length - 4] ^= 0xff
    expect(parseArchiveBytes(toAb(badSize))).toMatchObject({
      status: 'parse_failed',
      message: 'gzip_isize_mismatch',
    })

    expect(parseArchiveBytes(toAb(valid.subarray(0, valid.length - 1))).status).toBe('parse_failed')
    expect(parseArchiveBytes(toAb(concatBytes(valid, valid))).status).toBe('parse_failed')
  })

  it('gzip 可选 header 不计入压缩比分母', () => {
    const tar = buildUstarTar([{ name: 'zeros.bin', data: new Uint8Array(32 * 1024) }])
    const base = gzipSync(tar)
    const longName = new Uint8Array(32 * 1024)
    longName.fill(0x61)
    const withLongName = concatBytes(base.subarray(0, 10), longName, new Uint8Array([0]), base.subarray(10))
    withLongName[3] |= 0x08

    const result = parseArchiveBytes(toAb(withLongName), {
      ...ARCHIVE_LIMITS,
      maxCompressionRatio: 2,
    })
    expect(result).toMatchObject({
      status: 'limit_reached',
      limitKey: 'maxCompressionRatio',
    })
  })

  it('TAR 目录条目不得携带正文绕过实际量门', () => {
    const bytes = buildUstarTar([
      { name: 'bad-dir/', data: new Uint8Array(4096), typeflag: '5' },
    ])
    expect(parseArchiveBytes(toAb(bytes))).toMatchObject({
      status: 'parse_failed',
      message: 'tar_directory_size',
    })
  })

  it('普通 .gz 按 hint 返回单条实际元数据；tgz/无 hint 仍要求 TAR', () => {
    const raw = strToU8('not a tar stream')
    const bytes = gzipSync(raw)
    const gzipResult = parseArchiveBytes(toAb(bytes), ARCHIVE_LIMITS, 'gz')
    expect(gzipResult).toMatchObject({ status: 'ok' })
    expect(gzipResult.entries).toEqual([
      expect.objectContaining({
        name: 'compressed-data',
        size: raw.length,
        declaredSize: raw.length,
        isDirectory: false,
        method: 8,
      }),
    ])

    for (const hint of [undefined, 'tgz']) {
      const result = parseArchiveBytes(toAb(bytes), ARCHIVE_LIMITS, hint)
      expect(result).toMatchObject({ status: 'format_mismatch', message: 'gzip_not_tar' })
    }
  })

  it('TGZ Inflate 越限后停止继续 push，不聚合后续 TAR 正文', () => {
    const tar = buildUstarTar([{ name: 'random.bin', data: deterministicBytes(256 * 1024) }])
    const bytes = gzipSync(tar)
    const pushSpy = vi.spyOn(Inflate.prototype, 'push')
    try {
      const r = parseArchiveBytes(toAb(bytes), unlimitedRatio)
      expect(r.status).toBe('limit_reached')
      expect(r.limitKey).toBe('maxEntryUncompressedBytes')
      expect(pushSpy.mock.calls.length).toBeLessThan(
        Math.ceil(bytes.length / ARCHIVE_STREAM_CHUNK_BYTES),
      )
    } finally {
      pushSpy.mockRestore()
    }
  })

  it('tar bad checksum fail closed', () => {
    const { bytes } = generateFixture('tar_bad_checksum')
    expect(parseArchiveBytes(toAb(bytes)).status).toBe('parse_failed')
  })

  it('ZIP64 marker → container_unsupported（不按普通损坏或强解）', () => {
    const { bytes } = generateFixture('zip_zip64_marker')
    const r = parseArchiveBytes(toAb(bytes))
    expect(r.status).toBe('container_unsupported')
    expect(r.message).toBe('zip64')
  })

  it('超长 EOCD comment 不影响 EOCD 定位', () => {
    const { bytes } = generateFixture('zip_long_comment')
    const r = parseArchiveBytes(toAb(bytes))
    expect(r.status).toBe('ok')
    expect(r.entries[0].name).toContain('c.txt')
  })

  it('GBK 名单条坏名不中断整包（编码回退产出条目）', () => {
    const { bytes } = generateFixture('zip_gbk_name')
    const r = parseArchiveBytes(toAb(bytes))
    expect(r.status).toBe('ok')
    expect(r.entries).toHaveLength(1)
    expect(r.entries[0].name.length).toBeGreaterThan(0)
    expect(r.entries[0].name).toContain('.txt')
  })

  it('单条实际解压超 32MiB → 在隔离 ratio 门时触发 maxEntryUncompressedBytes', () => {
    const { bytes } = generateFixture('zip_entry_uncompressed_over')
    const r = parseArchiveBytes(toAb(bytes), {
      ...ARCHIVE_LIMITS,
      maxCompressionRatio: Number.MAX_SAFE_INTEGER,
    })
    expect(r.status).toBe('limit_reached')
    expect(r.limitKey).toBe('maxEntryUncompressedBytes')
  })

  it('合计实际解压超 64MiB → 只触发 maxTotalUncompressedBytes 门', () => {
    const { bytes } = generateFixture('zip_total_uncompressed_over')
    const r = parseArchiveBytes(toAb(bytes))
    expect(r.status).toBe('limit_reached')
    expect(r.limitKey).toBe('maxTotalUncompressedBytes')
  })
})
