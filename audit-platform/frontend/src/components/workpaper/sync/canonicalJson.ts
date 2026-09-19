/**
 * canonical JSON bytes —— 与后端 `canonical_json_bytes` 逐字节等价的 TS 实现。
 *
 * spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` Task 13
 * Requirements 6.2（「同一 semantic payload 在不同环境必须得到相同 SHA」）
 *
 * 后端真源：
 *   `backend/app/services/workpaper_sync/definitions.py::canonical_json_bytes`
 *   = `json.dumps(payload, sort_keys=True, ensure_ascii=False,
 *                 separators=(",", ":"), allow_nan=False).encode("utf-8")`
 *
 * golden 用例真源（两侧读同一份）：
 *   `backend/data/workpaper_sync_canonical_golden.json`
 *
 * ## 为什么不能直接用 `JSON.stringify`
 *
 * 1. **键序**：Python 的 `sort_keys=True` 按 Unicode **code point** 排序；
 *    JS 的 `Array.prototype.sort()` 默认按 **UTF-16 code unit** 排序。对星平面字符
 *    两者相反（`Ｚ` U+FF3A vs `𝐀` U+1D400），golden 用例 `astral_key_order` 就是
 *    这条的反例锚点。本模块因此自己做 code-point 比较。
 * 2. **数值域**：JS 的 `-0` 序列化成 `0`、超过 `Number.MAX_SAFE_INTEGER` 的整数丢
 *    精度、非整数浮点的 repr 规则与 Python 不同（`1e-7` → Python `1e-07`、
 *    JS `1e-7`；`1e16` → Python `1e+16`、JS `10000000000000000`）。
 *    ⇒ canonical payload **一律不允许非整数浮点**，小数/金额以字符串承载。
 * 3. **NaN/Infinity**：`JSON.stringify` 静默输出 `null`，Python 侧直接抛。
 * 4. **孤立代理项**：ES2019 well-formed stringify 会转义成 `\udXXX`，Python 侧
 *    UTF-8 编码直接报错。
 *
 * 以上四类一律在**编码之前**拒绝（`CanonicalJsonError`），而不是「尽力序列化」。
 */

/** JS `Number.MAX_SAFE_INTEGER`，与后端 `canonical_interop.MAX_SAFE_INTEGER` 同值。 */
export const MAX_SAFE_INTEGER = Number.MAX_SAFE_INTEGER

export type CanonicalJsonValue =
  | null
  | boolean
  | number
  | string
  | CanonicalJsonValue[]
  | { [key: string]: CanonicalJsonValue }

export class CanonicalJsonError extends Error {
  readonly path: string

  constructor(message: string, path: string) {
    super(`${path}: ${message}`)
    this.name = 'CanonicalJsonError'
    this.path = path
  }
}

function describe(path: readonly (string | number)[]): string {
  return '$' + path.map((part) => `[${JSON.stringify(part)}]`).join('')
}

/**
 * code point 序比较。
 *
 * `Array.from(s)` 按 code point 切分（代理对合并成一个元素），再逐位比较
 * `codePointAt(0)`。这与 Python `sorted()` 对 `str` 的行为一致。
 * **不要**换成 `a < b` 或 `a.localeCompare(b)`：前者是 UTF-16 code unit 序，
 * 后者受 locale 影响。
 */
export function compareByCodePoint(a: string, b: string): number {
  const left = Array.from(a)
  const right = Array.from(b)
  const shared = Math.min(left.length, right.length)
  for (let index = 0; index < shared; index += 1) {
    const lc = left[index].codePointAt(0) as number
    const rc = right[index].codePointAt(0) as number
    if (lc !== rc) return lc < rc ? -1 : 1
  }
  if (left.length === right.length) return 0
  return left.length < right.length ? -1 : 1
}

const ESCAPES: Record<string, string> = {
  '"': '\\"',
  '\\': '\\\\',
  '\b': '\\b',
  '\f': '\\f',
  '\n': '\\n',
  '\r': '\\r',
  '\t': '\\t',
}

/**
 * 字符串字面量编码，与 Python `json.dumps(..., ensure_ascii=False)` 一致：
 * 只转义 `"` `\` 与 `\b \f \n \r \t`，其余 <0x20 用 4 位小写 `\uXXXX`；
 * 中文、emoji、U+2028/U+2029 一律原样输出。
 */
function encodeString(value: string, path: readonly (string | number)[]): string {
  assertNoLoneSurrogate(value, path)
  let out = '"'
  for (const char of value) {
    const escape = ESCAPES[char]
    if (escape !== undefined) {
      out += escape
      continue
    }
    const code = char.codePointAt(0) as number
    if (code < 0x20) {
      out += `\\u${code.toString(16).padStart(4, '0')}`
      continue
    }
    out += char
  }
  return out + '"'
}

/** 孤立代理项检测（XL-4）。合法代理对必须成对且高位在前。 */
function assertNoLoneSurrogate(value: string, path: readonly (string | number)[]): void {
  for (let index = 0; index < value.length; index += 1) {
    const unit = value.charCodeAt(index)
    if (unit < 0xd800 || unit > 0xdfff) continue
    if (unit >= 0xdc00) {
      throw new CanonicalJsonError(
        '字符串含孤立低位代理项（lone low surrogate）—— Python 侧无法 UTF-8 编码（XL-4）',
        describe(path),
      )
    }
    const next = index + 1 < value.length ? value.charCodeAt(index + 1) : NaN
    if (!(next >= 0xdc00 && next <= 0xdfff)) {
      throw new CanonicalJsonError(
        '字符串含孤立高位代理项（lone high surrogate）—— Python 侧无法 UTF-8 编码（XL-4）',
        describe(path),
      )
    }
    index += 1
  }
}

/** 数值域校验（XL-1 / XL-2 / XL-3 / XL-6）。三条子判据文案刻意可区分。 */
function encodeNumber(value: number, path: readonly (string | number)[]): string {
  if (Number.isNaN(value) || !Number.isFinite(value)) {
    throw new CanonicalJsonError(
      'NaN/Infinity 不是合法 JSON —— JS 会静默输出 null，Python 侧直接抛（XL-1）',
      describe(path),
    )
  }
  if (Object.is(value, -0)) {
    throw new CanonicalJsonError(
      '负零 `-0` 在 JS 序列化为 `0`、在 Python 为 `-0.0` ⇒ 两侧 digest 不同（XL-2）。请写 `0`',
      describe(path),
    )
  }
  if (!Number.isInteger(value)) {
    throw new CanonicalJsonError(
      'canonical payload 不允许非整数浮点 —— Python 与 JS 的浮点 repr 在 `1e-7` 与 `1e16` ' +
        '等处分叉（XL-6）。小数/金额请以字符串承载',
      describe(path),
    )
  }
  if (Math.abs(value) > MAX_SAFE_INTEGER) {
    throw new CanonicalJsonError(
      `整数 ${value} 超出 Number.MAX_SAFE_INTEGER (${MAX_SAFE_INTEGER})，JS 侧已丢精度（XL-3）`,
      describe(path),
    )
  }
  return String(value)
}

function encode(value: unknown, path: readonly (string | number)[]): string {
  if (value === null) return 'null'
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'number') return encodeNumber(value, path)
  if (typeof value === 'string') return encodeString(value, path)
  if (Array.isArray(value)) {
    // 数组顺序是语义，不排序。
    return '[' + value.map((item, index) => encode(item, [...path, index])).join(',') + ']'
  }
  if (typeof value === 'object') {
    if (Object.getPrototypeOf(value) !== Object.prototype && Object.getPrototypeOf(value) !== null) {
      throw new CanonicalJsonError(
        `类型 ${value.constructor?.name ?? 'object'} 不是 JSON 基本类型 —— canonical payload ` +
          '只允许 null/boolean/number/string/Array/plain object',
        describe(path),
      )
    }
    const keys = Object.keys(value as Record<string, unknown>).sort(compareByCodePoint)
    const parts = keys.map((key) => {
      const child = (value as Record<string, unknown>)[key]
      if (child === undefined) {
        throw new CanonicalJsonError(
          '值为 undefined —— Python 侧没有对应形态，`JSON.stringify` 会静默丢键',
          describe([...path, key]),
        )
      }
      return `${encodeString(key, [...path, key])}:${encode(child, [...path, key])}`
    })
    return '{' + parts.join(',') + '}'
  }
  throw new CanonicalJsonError(
    `类型 ${typeof value} 不是 JSON 基本类型`,
    describe(path),
  )
}

/** canonical JSON 文本（UTF-8 编码前）。 */
export function canonicalJsonText(payload: CanonicalJsonValue): string {
  return encode(payload, [])
}

/** canonical JSON bytes —— 与后端 `canonical_json_bytes` 逐字节相同。 */
export function canonicalJsonBytes(payload: CanonicalJsonValue): Uint8Array {
  return new TextEncoder().encode(canonicalJsonText(payload))
}

/** canonical bytes 的 SHA-256（小写 hex）。浏览器/Node 均走 WebCrypto。 */
export async function canonicalDigest(payload: CanonicalJsonValue): Promise<string> {
  const bytes = canonicalJsonBytes(payload)
  const digest = await crypto.subtle.digest('SHA-256', bytes as unknown as ArrayBuffer)
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('')
}

/** 便于与 golden fixture 的 `canonical_utf8_hex` 直接比对。 */
export function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes)
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('')
}
