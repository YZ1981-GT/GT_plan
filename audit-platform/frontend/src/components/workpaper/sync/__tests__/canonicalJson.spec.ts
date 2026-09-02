/**
 * Task 13 守卫：canonical bytes 跨 Python/TypeScript 逐字节一致。
 *
 * spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` Task 13
 * Requirements 6.2 / Property 21 / Property 28
 *
 * 判据不是「TS 侧自洽」，而是**两侧读同一份 golden fixture**：
 *   `backend/data/workpaper_sync_canonical_golden.json`
 * 由 `backend/scripts/gen/generate_workpaper_sync_canonical_golden.py --apply`
 * 用后端 `canonical_json_bytes` 生成，期望字节以 hex 存放。
 * 任一侧 canonicalizer 漂移 ⇒ 本文件打红。
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

import {
  MAX_SAFE_INTEGER,
  CanonicalJsonError,
  bytesToHex,
  canonicalJsonBytes,
  canonicalJsonText,
  compareByCodePoint,
  type CanonicalJsonValue,
} from '../canonicalJson'

// 本文件位于 audit-platform/frontend/src/components/workpaper/sync/__tests__/
// → 仓库根需上溯 7 层。
const here = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(here, '../../../../../../..')
const GOLDEN_PATH = resolve(REPO_ROOT, 'backend/data/workpaper_sync_canonical_golden.json')

interface GoldenCase {
  case_id: string
  note: string
  payload: CanonicalJsonValue
  canonical_utf8_hex: string
  canonical_sha256: string
}

interface RejectCase {
  case_id: string
  note: string
  languages: string[]
}

interface GoldenDocument {
  schema_version: number
  max_safe_integer: number
  typescript_canonicalizer: string
  cases: GoldenCase[]
  reject_cases: RejectCase[]
}

function loadGolden(): GoldenDocument {
  const raw = readFileSync(GOLDEN_PATH, 'utf-8')
  return JSON.parse(raw) as GoldenDocument
}

const golden = loadGolden()

describe('canonical golden fixture 自身完整性', () => {
  it('fixture 存在、版本化、并指向本模块', () => {
    expect(golden.schema_version).toBe(1)
    expect(golden.cases.length).toBeGreaterThan(0)
    expect(golden.typescript_canonicalizer).toBe(
      'audit-platform/frontend/src/components/workpaper/sync/canonicalJson.ts',
    )
  })

  it('MAX_SAFE_INTEGER 两侧同值', () => {
    expect(golden.max_safe_integer).toBe(MAX_SAFE_INTEGER)
  })

  it('每条用例都有非空期望字节与 digest，且 case_id 唯一', () => {
    const ids = golden.cases.map((item) => item.case_id)
    expect(new Set(ids).size).toBe(ids.length)
    for (const item of golden.cases) {
      expect(item.canonical_utf8_hex.length).toBeGreaterThan(0)
      expect(item.canonical_sha256).toMatch(/^[0-9a-f]{64}$/)
    }
  })
})

describe('TS canonicalizer 与后端逐字节一致', () => {
  it.each(golden.cases.map((item) => [item.case_id, item] as const))(
    'golden 用例 %s',
    (_caseId, item) => {
      const bytes = canonicalJsonBytes(item.payload)
      expect(bytesToHex(bytes)).toBe(item.canonical_utf8_hex)
    },
  )

  it('每条用例的 payload 都能反序列化回同一 canonical 文本（自反）', () => {
    for (const item of golden.cases) {
      const text = canonicalJsonText(item.payload)
      const roundTripped = JSON.parse(text) as CanonicalJsonValue
      expect(canonicalJsonText(roundTripped)).toBe(text)
    }
  })
})

describe('键序：code point 而非 UTF-16 code unit', () => {
  it('星平面字符的 code point 序与默认 sort() 相反', () => {
    const bmp = '\uff3a' // Ｚ  U+FF3A
    const astral = '\u{1d400}' // 𝐀 U+1D400
    // code point 序：U+FF3A (65338) < U+1D400 (119808)
    expect(compareByCodePoint(bmp, astral)).toBeLessThan(0)
    // JS 默认（UTF-16 code unit）序恰好相反 —— 这正是不能用 sort() 的原因
    expect([astral, bmp].sort().indexOf(astral)).toBe(0)
  })

  it('canonical 输出把 Ｚ 排在 𝐀 之前', () => {
    const text = canonicalJsonText({ '\uff3a': 1, '\u{1d400}': 2, a: 3 })
    expect(text.indexOf('\uff3a')).toBeLessThan(text.indexOf('\u{1d400}'))
    expect(text.indexOf('"a"')).toBeLessThan(text.indexOf('\uff3a'))
  })

  it('输入键序扰动不改变输出', () => {
    const a = canonicalJsonText({ z: 1, a: 2, m: 3 })
    const b = canonicalJsonText({ a: 2, m: 3, z: 1 })
    const c = canonicalJsonText({ m: 3, z: 1, a: 2 })
    expect(a).toBe(b)
    expect(b).toBe(c)
  })

  it('数组顺序是语义，不排序', () => {
    expect(canonicalJsonText({ x: [3, 1, 2] })).toBe('{"x":[3,1,2]}')
  })
})

describe('分隔符与转义规则与 Python 一致', () => {
  it('无多余空白', () => {
    expect(canonicalJsonText({ a: 1, b: [1, 2] })).toBe('{"a":1,"b":[1,2]}')
  })

  it('中文不转义（ensure_ascii=False）', () => {
    expect(canonicalJsonText({ u: '元' })).toBe('{"u":"元"}')
  })

  it('U+2028 / U+2029 不转义', () => {
    expect(canonicalJsonText({ s: '\u2028' })).toBe('{"s":"\u2028"}')
  })

  it('控制字符用 4 位小写 \\uXXXX', () => {
    expect(canonicalJsonText({ s: '\u0001' })).toBe('{"s":"\\u0001"}')
  })

  it('短转义序列覆盖 " \\ \\b \\f \\n \\r \\t', () => {
    expect(canonicalJsonText({ s: '"\\\b\f\n\r\t' })).toBe('{"s":"\\"\\\\\\b\\f\\n\\r\\t"}')
  })
})

describe('跨语言不安全输入一律拒绝（XL-1 ~ XL-6）', () => {
  const rejectKinds = new Set(
    golden.reject_cases.filter((item) => item.languages.includes('typescript')).map((item) => item.case_id),
  )

  function payloadFor(kind: string): unknown {
    switch (kind) {
      case 'nan':
        return { v: Number.NaN }
      case 'positive_infinity':
        return { v: Number.POSITIVE_INFINITY }
      case 'negative_infinity':
        return { v: Number.NEGATIVE_INFINITY }
      case 'negative_zero':
        return { v: -0 }
      case 'unsafe_integer':
        return { v: MAX_SAFE_INTEGER + 2 }
      case 'lone_surrogate':
        return { v: '\ud800' }
      case 'undefined_value':
        return { v: undefined }
      case 'non_json_type':
        return { v: new Date(0) }
      case 'plain_float':
        return { v: 1.5 }
      case 'exponential_float':
        return { v: 1e-7 }
      default:
        throw new Error(`未登记的 reject kind: ${kind}`)
    }
  }

  it('fixture 声明的 TS 侧反例种类非空，且不含只属 Python 的形态', () => {
    expect(rejectKinds.size).toBeGreaterThan(0)
    expect(rejectKinds.has('non_string_key')).toBe(false)
  })

  it.each([...rejectKinds].map((kind) => [kind] as const))('拒绝 %s', (kind) => {
    expect(() => canonicalJsonText(payloadFor(kind) as CanonicalJsonValue)).toThrow(
      CanonicalJsonError,
    )
  })

  // 每个 kind 归属的 XL 分类标记。同一分类共用一句文案是正确的（NaN 与 ±Infinity
  // 本来就是同一个原因），但**不同分类必须有不同文案** —— 否则「到底哪条判据在起
  // 作用」不可分辨，把其中一条删掉会被另一条遮蔽（变异检验判 GREEN）。
  const XL_CLASS: Record<string, string> = {
    nan: 'XL-1',
    positive_infinity: 'XL-1',
    negative_infinity: 'XL-1',
    negative_zero: 'XL-2',
    unsafe_integer: 'XL-3',
    lone_surrogate: 'XL-4',
    plain_float: 'XL-6',
    exponential_float: 'XL-6',
    undefined_value: 'undefined',
    non_json_type: 'JSON 基本类型',
  }

  it('fixture 的每个 TS 侧 kind 都已登记 XL 分类', () => {
    for (const kind of rejectKinds) {
      expect(XL_CLASS[kind], `kind ${kind} 未登记 XL 分类`).toBeTruthy()
    }
  })

  it('每条反例的文案带自己的 XL 分类标记', () => {
    for (const kind of rejectKinds) {
      try {
        canonicalJsonText(payloadFor(kind) as CanonicalJsonValue)
        throw new Error(`${kind} 未被拒绝`)
      } catch (error) {
        expect(error).toBeInstanceOf(CanonicalJsonError)
        expect((error as CanonicalJsonError).message).toContain(XL_CLASS[kind])
      }
    }
  })

  it('不同 XL 分类的文案互不相同', () => {
    const byClass = new Map<string, Set<string>>()
    for (const kind of rejectKinds) {
      try {
        canonicalJsonText(payloadFor(kind) as CanonicalJsonValue)
        throw new Error(`${kind} 未被拒绝`)
      } catch (error) {
        const cls = XL_CLASS[kind]
        const bucket = byClass.get(cls) ?? new Set<string>()
        bucket.add((error as CanonicalJsonError).message)
        byClass.set(cls, bucket)
      }
    }
    // 同类内部文案一致（同一原因同一句话）
    for (const [cls, messages] of byClass) {
      expect(messages.size, `XL 分类 ${cls} 内部文案不一致`).toBe(1)
    }
    // 跨类文案互不相同
    const flattened = [...byClass.values()].map((set) => [...set][0])
    expect(new Set(flattened).size).toBe(byClass.size)
  })

  it('合法代理对不受影响', () => {
    expect(() => canonicalJsonText({ v: '📊' })).not.toThrow()
  })

  it('边界整数 ±MAX_SAFE_INTEGER 可用', () => {
    expect(canonicalJsonText({ v: MAX_SAFE_INTEGER })).toBe(`{"v":${MAX_SAFE_INTEGER}}`)
    expect(canonicalJsonText({ v: -MAX_SAFE_INTEGER })).toBe(`{"v":-${MAX_SAFE_INTEGER}}`)
  })
})
