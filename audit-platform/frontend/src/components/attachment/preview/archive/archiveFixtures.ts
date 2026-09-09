/**
 * Archive 恶意/边界夹具生成器 — 固定算法，digest 可复核
 * Spec Task 6
 *
 * 不把巨型炸弹物化进版本库；测试按需生成并断言 sha256。
 */
import { deflateSync, gzipSync, strToU8 } from 'fflate'

const te = new TextEncoder()

export function crc32(buf: Uint8Array): number {
  let c = ~0
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i]
    for (let k = 0; k < 8; k++) c = c & 1 ? (0xedb88320 ^ (c >>> 1)) : c >>> 1
  }
  return ~c >>> 0
}

function u16(n: number): Uint8Array {
  const b = new Uint8Array(2)
  b[0] = n & 0xff
  b[1] = (n >>> 8) & 0xff
  return b
}

function u32(n: number): Uint8Array {
  const b = new Uint8Array(4)
  b[0] = n & 0xff
  b[1] = (n >>> 8) & 0xff
  b[2] = (n >>> 16) & 0xff
  b[3] = (n >>> 24) & 0xff
  return b
}

function concat(...parts: Uint8Array[]): Uint8Array {
  const n = parts.reduce((s, p) => s + p.length, 0)
  const out = new Uint8Array(n)
  let o = 0
  for (const p of parts) {
    out.set(p, o)
    o += p.length
  }
  return out
}

export interface ZipEntrySpec {
  name: string
  data: Uint8Array
  method?: 0 | 8
  /** 覆盖 central/local 写入的声明解压大小（用于结构门夹具） */
  declaredUncompressed?: number
  /** 覆盖 central/local 声明压缩大小 */
  declaredCompressed?: number
  generalPurposeBitFlag?: number
  /** bit 3 时默认生成带签名的 classic data descriptor。 */
  dataDescriptorSignature?: boolean
  descriptorCrc?: number
  descriptorCompressed?: number
  descriptorUncompressed?: number
  /** 构造 DEFLATE 尾随垃圾或 entry 间隙的结构反例。 */
  compressedSuffix?: Uint8Array
  gapAfterEntry?: Uint8Array
  /** 以下仅覆盖 local header，用于 local/central 一致性夹具。 */
  localName?: string
  localMethod?: number
  localGeneralPurposeBitFlag?: number
  localCrc?: number
  localDeclaredUncompressed?: number
  localDeclaredCompressed?: number
  /** EFS UTF-8 bit */
  utf8?: boolean
}

/** 手工组装 classic single-disk ZIP（method 0/8） */
export function buildClassicZip(entries: ZipEntrySpec[], opts?: { comment?: Uint8Array }): Uint8Array {
  const locals: Uint8Array[] = []
  const centrals: Uint8Array[] = []
  let offset = 0

  for (const e of entries) {
    const nameBytes = te.encode(e.name)
    const localNameBytes = te.encode(e.localName ?? e.name)
    const method = e.method ?? 8
    const raw = e.data
    const compressed = method === 0 ? raw : deflateSync(raw, { level: 6 })
    const encodedCompressed = e.compressedSuffix
      ? concat(compressed, e.compressedSuffix)
      : compressed
    const crc = crc32(raw)
    const gp = (e.generalPurposeBitFlag ?? 0) | (e.utf8 ? 0x800 : 0)
    const usesDescriptor = !!(gp & 0x8)
    const compSize = e.declaredCompressed ?? encodedCompressed.length
    const uncompSize = e.declaredUncompressed ?? raw.length
    const localGp = e.localGeneralPurposeBitFlag ?? gp
    const localMethod = e.localMethod ?? method
    const localCrc = e.localCrc ?? (usesDescriptor ? 0 : crc)
    const localCompSize = e.localDeclaredCompressed ?? (usesDescriptor ? 0 : compSize)
    const localUncompSize = e.localDeclaredUncompressed ?? (usesDescriptor ? 0 : uncompSize)
    const descriptor = usesDescriptor
      ? concat(
          e.dataDescriptorSignature === false ? new Uint8Array(0) : u32(0x08074b50),
          u32(e.descriptorCrc ?? crc),
          u32(e.descriptorCompressed ?? compSize),
          u32(e.descriptorUncompressed ?? uncompSize),
        )
      : new Uint8Array(0)

    const local = concat(
      u32(0x04034b50),
      u16(20),
      u16(localGp),
      u16(localMethod),
      u16(0),
      u16(0),
      u32(localCrc),
      u32(localCompSize),
      u32(localUncompSize),
      u16(localNameBytes.length),
      u16(0),
      localNameBytes,
      encodedCompressed,
      descriptor,
      e.gapAfterEntry ?? new Uint8Array(0),
    )
    const central = concat(
      u32(0x02014b50),
      u16(20),
      u16(20),
      u16(gp),
      u16(method),
      u16(0),
      u16(0),
      u32(crc),
      u32(compSize),
      u32(uncompSize),
      u16(nameBytes.length),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(0),
      u32(offset),
      nameBytes,
    )
    locals.push(local)
    centrals.push(central)
    offset += local.length
  }

  const centralDir = concat(...centrals)
  const comment = opts?.comment ?? new Uint8Array(0)
  const eocd = concat(
    u32(0x06054b50),
    u16(0),
    u16(0),
    u16(entries.length),
    u16(entries.length),
    u32(centralDir.length),
    u32(offset),
    u16(comment.length),
    comment,
  )
  return concat(...locals, centralDir, eocd)
}

/** 最小 ustar TAR */
export function buildUstarTar(
  entries: Array<{ name: string; data: Uint8Array; typeflag?: string; mtime?: number }>,
): Uint8Array {
  const blocks: Uint8Array[] = []
  for (const e of entries) {
    const header = new Uint8Array(512)
    const name = e.name.slice(0, 100)
    header.set(te.encode(name), 0)
    const mode = te.encode('0000644\0')
    header.set(mode, 100)
    header.set(te.encode('0000000\0'), 108) // uid
    header.set(te.encode('0000000\0'), 116) // gid
    const sizeOct = e.data.length.toString(8).padStart(11, '0') + '\0'
    header.set(te.encode(sizeOct), 124)
    const mtimeOct = (e.mtime ?? 0).toString(8).padStart(11, '0') + '\0'
    header.set(te.encode(mtimeOct), 136)
    header.set(te.encode('        '), 148) // checksum blank
    header[156] = (e.typeflag ?? '0').charCodeAt(0)
    header.set(te.encode('ustar\0'), 257)
    header.set(te.encode('00'), 263)
    // checksum
    let sum = 0
    for (let i = 0; i < 512; i++) sum += header[i]
    const chk = (sum.toString(8).padStart(6, '0') + '\0 ').slice(0, 8)
    header.set(te.encode(chk), 148)
    blocks.push(header)
    blocks.push(e.data)
    const pad = (512 - (e.data.length % 512)) % 512
    if (pad) blocks.push(new Uint8Array(pad))
  }
  blocks.push(new Uint8Array(1024)) // two zero blocks
  return concat(...blocks)
}

export type FixtureId =
  | 'zip_utf8_ok'
  | 'zip_traversal_dotdot'
  | 'zip_drive_path'
  | 'zip_absolute'
  | 'zip_encrypted_flag'
  | 'zip_fake_declared_size'
  | 'zip_method99_aes'
  | 'zip_method9_deflate64'
  | 'zip_truncated_eocd'
  | 'zip_bad_crc'
  | 'zip_local_central_mismatch'
  | 'zip_path_depth_9'
  | 'zip_many_entries_over'
  | 'tar_ok'
  | 'tar_bad_checksum'
  | 'tgz_ok'
  | 'zip_ratio_bomb_small'
  | 'zip_zip64_marker'
  | 'zip_long_comment'
  | 'zip_gbk_name'
  | 'zip_entry_uncompressed_over'
  | 'zip_total_uncompressed_over'

export interface FixtureMeta {
  id: FixtureId
  triggers?: string
  description: string
}

/** 确定性夹具表（大炸弹用小样本模拟 ratio/entry 门，避免仓库膨胀） */
export function generateFixture(id: FixtureId): { bytes: Uint8Array; meta: FixtureMeta } {
  switch (id) {
    case 'zip_utf8_ok':
      return {
        bytes: buildClassicZip([{ name: '凭证/发票.txt', data: strToU8('hello'), utf8: true }]),
        meta: { id, description: 'UTF-8 EFS 正常 ZIP' },
      }
    case 'zip_traversal_dotdot':
      return {
        bytes: buildClassicZip([{ name: '../evil.txt', data: strToU8('x'), method: 0 }]),
        meta: { id, triggers: 'path_traversal', description: '路径含 ..' },
      }
    case 'zip_drive_path':
      return {
        bytes: buildClassicZip([{ name: 'C:\\Windows\\a.txt', data: strToU8('x'), method: 0 }]),
        meta: { id, triggers: 'path_traversal', description: '盘符路径' },
      }
    case 'zip_absolute':
      return {
        bytes: buildClassicZip([{ name: '/etc/passwd', data: strToU8('x'), method: 0 }]),
        meta: { id, triggers: 'path_traversal', description: '绝对路径' },
      }
    case 'zip_encrypted_flag':
      return {
        bytes: buildClassicZip([
          { name: 'secret.txt', data: strToU8('x'), method: 0, generalPurposeBitFlag: 0x1 },
        ]),
        meta: { id, triggers: 'encrypted', description: '加密 bit0' },
      }
    case 'zip_fake_declared_size':
      return {
        bytes: buildClassicZip([
          {
            name: 'fake.txt',
            data: strToU8('tiny'),
            method: 0,
            declaredUncompressed: 50 * 1024 * 1024,
          },
        ]),
        meta: { id, triggers: 'fake_size', description: '声明解压大小远大于实际' },
      }
    case 'zip_method99_aes': {
      const raw = strToU8('x')
      const name = te.encode('aes.bin')
      const local = concat(
        u32(0x04034b50),
        u16(20),
        u16(0),
        u16(99),
        u16(0),
        u16(0),
        u32(crc32(raw)),
        u32(raw.length),
        u32(raw.length),
        u16(name.length),
        u16(0),
        name,
        raw,
      )
      const central = concat(
        u32(0x02014b50),
        u16(20),
        u16(20),
        u16(0),
        u16(99),
        u16(0),
        u16(0),
        u32(crc32(raw)),
        u32(raw.length),
        u32(raw.length),
        u16(name.length),
        u16(0),
        u16(0),
        u16(0),
        u16(0),
        u32(0),
        u32(0),
        name,
      )
      const eocd = concat(
        u32(0x06054b50),
        u16(0),
        u16(0),
        u16(1),
        u16(1),
        u32(central.length),
        u32(local.length),
        u16(0),
      )
      return {
        bytes: concat(local, central, eocd),
        meta: { id, triggers: 'container_unsupported', description: 'method 99 AES' },
      }
    }
    case 'zip_method9_deflate64': {
      const raw = strToU8('x')
      const name = te.encode('d64.bin')
      const local = concat(
        u32(0x04034b50),
        u16(20),
        u16(0),
        u16(9),
        u16(0),
        u16(0),
        u32(crc32(raw)),
        u32(raw.length),
        u32(raw.length),
        u16(name.length),
        u16(0),
        name,
        raw,
      )
      const central = concat(
        u32(0x02014b50),
        u16(20),
        u16(20),
        u16(0),
        u16(9),
        u16(0),
        u16(0),
        u32(crc32(raw)),
        u32(raw.length),
        u32(raw.length),
        u16(name.length),
        u16(0),
        u16(0),
        u16(0),
        u16(0),
        u32(0),
        u32(0),
        name,
      )
      const eocd = concat(
        u32(0x06054b50),
        u16(0),
        u16(0),
        u16(1),
        u16(1),
        u32(central.length),
        u32(local.length),
        u16(0),
      )
      return {
        bytes: concat(local, central, eocd),
        meta: { id, triggers: 'container_unsupported', description: 'method 9 Deflate64' },
      }
    }
    case 'zip_truncated_eocd': {
      const ok = buildClassicZip([{ name: 'a.txt', data: strToU8('a'), method: 0 }])
      return {
        bytes: ok.slice(0, Math.max(4, ok.length - 12)),
        meta: { id, triggers: 'container_error', description: '截断 EOCD' },
      }
    }
    case 'zip_bad_crc': {
      const raw = strToU8('hello')
      const name = te.encode('badcrc.txt')
      const local = concat(
        u32(0x04034b50),
        u16(20),
        u16(0),
        u16(0),
        u16(0),
        u16(0),
        u32(0xdeadbeef),
        u32(raw.length),
        u32(raw.length),
        u16(name.length),
        u16(0),
        name,
        raw,
      )
      const central = concat(
        u32(0x02014b50),
        u16(20),
        u16(20),
        u16(0),
        u16(0),
        u16(0),
        u16(0),
        u32(0xdeadbeef),
        u32(raw.length),
        u32(raw.length),
        u16(name.length),
        u16(0),
        u16(0),
        u16(0),
        u16(0),
        u32(0),
        u32(0),
        name,
      )
      const eocd = concat(
        u32(0x06054b50),
        u16(0),
        u16(0),
        u16(1),
        u16(1),
        u32(central.length),
        u32(local.length),
        u16(0),
      )
      return {
        bytes: concat(local, central, eocd),
        meta: { id, triggers: 'crc_error', description: 'CRC 错误' },
      }
    }
    case 'zip_local_central_mismatch':
      return {
        bytes: buildClassicZip([
          {
            name: 'central-name.txt',
            localName: 'local-name.txt',
            data: strToU8('mismatch'),
            method: 0,
          },
        ]),
        meta: {
          id,
          triggers: 'container_error',
          description: 'local/central 文件名不一致',
        },
      }
    case 'zip_path_depth_9': {
      const name = Array.from({ length: 9 }, (_, i) => `d${i}`).join('/') + '/f.txt'
      return {
        bytes: buildClassicZip([{ name, data: strToU8('x'), method: 0 }]),
        meta: { id, triggers: 'maxPathDepth', description: '路径深度 9' },
      }
    }
    case 'zip_many_entries_over': {
      const entries: ZipEntrySpec[] = []
      for (let i = 0; i < 2001; i++) {
        entries.push({ name: `e${i}.txt`, data: strToU8('x'), method: 0 })
      }
      return {
        bytes: buildClassicZip(entries),
        meta: { id, triggers: 'maxEntries', description: '2001 条目触发 maxEntries' },
      }
    }
    case 'tar_ok':
      return {
        bytes: buildUstarTar([{ name: 'a.txt', data: strToU8('tar-ok') }]),
        meta: { id, description: '正常 ustar' },
      }
    case 'tar_bad_checksum': {
      const tar = buildUstarTar([{ name: 'a.txt', data: strToU8('x') }])
      const broken = new Uint8Array(tar)
      // 改名首字节，使已写入的 checksum 与 header 内容不一致
      broken[0] = (broken[0] ^ 0xff) || 0x41
      return {
        bytes: broken,
        meta: { id, triggers: 'container_error', description: 'TAR checksum 错' },
      }
    }
    case 'tgz_ok': {
      const tar = buildUstarTar([{ name: 'a.txt', data: strToU8('tgz') }])
      return {
        bytes: gzipSync(tar),
        meta: { id, description: '正常 tgz' },
      }
    }
    case 'zip_ratio_bomb_small': {
      // 高压缩比：大量零用 deflate；实际输出计数应触发 ratio 门（测试侧用降低后的门或小阈值断言逻辑）
      const zeros = new Uint8Array(200_000)
      return {
        bytes: buildClassicZip([{ name: 'zeros.bin', data: zeros, method: 8 }]),
        meta: {
          id,
          triggers: 'maxCompressionRatio',
          description: '高压缩比样本（配合测试用降低 ratio 门验证）',
        },
      }
    }
    case 'zip_zip64_marker': {
      // EOCD totalEntries=0xffff → ZIP64 指示，必须判 container_unsupported，不得按普通损坏或强解
      const raw = strToU8('x')
      const name = te.encode('z64.bin')
      const local = concat(
        u32(0x04034b50), u16(20), u16(0), u16(0), u16(0), u16(0),
        u32(crc32(raw)), u32(raw.length), u32(raw.length), u16(name.length), u16(0), name, raw,
      )
      const central = concat(
        u32(0x02014b50), u16(20), u16(20), u16(0), u16(0), u16(0), u16(0),
        u32(crc32(raw)), u32(raw.length), u32(raw.length), u16(name.length),
        u16(0), u16(0), u16(0), u16(0), u32(0), u32(0), name,
      )
      const eocd = concat(
        u32(0x06054b50), u16(0), u16(0),
        u16(0xffff), u16(0xffff), // totalEntries = 0xffff → ZIP64 marker
        u32(central.length), u32(local.length), u16(0),
      )
      return {
        bytes: concat(local, central, eocd),
        meta: { id, triggers: 'container_unsupported', description: 'ZIP64 marker (0xffff entries)' },
      }
    }
    case 'zip_long_comment': {
      // EOCD 尾部超长 comment：EOCD 定位窗口必须能跨过 300 字节 comment 找到签名
      const comment = new Uint8Array(300).fill(0x41)
      return {
        bytes: buildClassicZip([{ name: 'c.txt', data: strToU8('ok'), method: 0 }], { comment }),
        meta: { id, description: '超长 EOCD comment（EOCD 定位鲁棒性）' },
      }
    }
    case 'zip_gbk_name': {
      // 非 UTF-8 bit + GBK 编码名「发票.txt」→ 编码回退链应产出可读或替换名，不中断整包
      const gbkName = new Uint8Array([0xb7, 0xa2, 0xc6, 0xb1, 0x2e, 0x74, 0x78, 0x74]) // 发票.txt (GBK)
      const raw = strToU8('gbk')
      const local = concat(
        u32(0x04034b50), u16(20), u16(0), u16(0), u16(0), u16(0),
        u32(crc32(raw)), u32(raw.length), u32(raw.length), u16(gbkName.length), u16(0), gbkName, raw,
      )
      const central = concat(
        u32(0x02014b50), u16(20), u16(20), u16(0), u16(0), u16(0), u16(0),
        u32(crc32(raw)), u32(raw.length), u32(raw.length), u16(gbkName.length),
        u16(0), u16(0), u16(0), u16(0), u32(0), u32(0), gbkName,
      )
      const eocd = concat(
        u32(0x06054b50), u16(0), u16(0), u16(1), u16(1),
        u32(central.length), u32(local.length), u16(0),
      )
      return {
        bytes: concat(local, central, eocd),
        meta: { id, description: 'GBK 名（非 UTF-8 bit，编码回退）' },
      }
    }
    case 'zip_entry_uncompressed_over': {
      // 单条 deflate 出 34 MiB 零；测试注入高 ratio 上限以隔离并验证单条 32MiB 门。
      const big = new Uint8Array(34 * 1024 * 1024)
      return {
        bytes: buildClassicZip([{ name: 'big-entry.bin', data: big, method: 8 }]),
        meta: { id, triggers: 'maxEntryUncompressedBytes', description: '单条实际解压 34MiB（隔离 ratio 后触发单条门）' },
      }
    }
    case 'zip_total_uncompressed_over': {
      // 3 条各 24 MiB stored(method 0)：单条不超 32MiB、压缩比=1（不触发 ratio 门），合计 72MiB
      // → 只触发总量门 maxTotalUncompressedBytes(64MiB)。用 stored 避免零块高压缩比抢先触发 ratio 门。
      const chunk = new Uint8Array(24 * 1024 * 1024)
      return {
        bytes: buildClassicZip([
          { name: 't1.bin', data: chunk, method: 0 },
          { name: 't2.bin', data: chunk, method: 0 },
          { name: 't3.bin', data: chunk, method: 0 },
        ]),
        meta: { id, triggers: 'maxTotalUncompressedBytes', description: '合计 72MiB stored 触发总量门（各条不超单条门、ratio=1）' },
      }
    }
    default: {
      const _exhaustive: never = id
      throw new Error(`unknown fixture ${_exhaustive}`)
    }
  }
}

export const ALL_FIXTURE_IDS: FixtureId[] = [
  'zip_utf8_ok',
  'zip_traversal_dotdot',
  'zip_drive_path',
  'zip_absolute',
  'zip_encrypted_flag',
  'zip_fake_declared_size',
  'zip_method99_aes',
  'zip_method9_deflate64',
  'zip_truncated_eocd',
  'zip_bad_crc',
  'zip_local_central_mismatch',
  'zip_path_depth_9',
  'zip_many_entries_over',
  'tar_ok',
  'tar_bad_checksum',
  'tgz_ok',
  'zip_ratio_bomb_small',
  'zip_zip64_marker',
  'zip_long_comment',
  'zip_gbk_name',
  'zip_entry_uncompressed_over',
  'zip_total_uncompressed_over',
]
