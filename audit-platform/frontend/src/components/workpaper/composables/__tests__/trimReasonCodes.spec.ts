/**
 * 裁剪理由码真源统一守卫（Task 12）。
 *
 * spec: procedure-trimming-and-delegation-intelligence
 * Requirements: 8.1 / 8.2 / 8.3 / 8.4 / 8.5 / 8.7 / 8.8 / 8.9 / 14.5
 *
 * ## 判据设计
 *
 * 理由码有两份实现（后端 enum 是真源，前端是展示镜像），故核心判据是**跨前后端
 * 交叉锁死**：读后端 `.py` 源码抽 enum 全部取值，与前端常量逐值比对。任一侧新增
 * 而另一侧未跟进 ⇒ 打红。
 *
 * 另三组判据针对「additive 扩展是否真的零回归」：
 *
 * 1. **契约扩展存在性**：canonical trim scope entry 的 `reason_code?` 三处齐备
 *    （router pydantic 模型 / service 归一 / 前端 commonApi 类型）。
 * 2. **零回归的结构性保证**：归一函数对不含 `reason_code` 的 entry 必须**不产生**
 *    该键 —— 否则 preview/apply 的 request payload 会变（payload 参与防篡改 hash，
 *    多一个 `"reason_code": null` 就会让存量调用方 409）。
 * 3. **禁两次写入**：理由码必须与 `target_status` 同一次请求提交，不得「先 apply
 *    状态再补写理由码」（一次性 preview 凭证不覆盖第二次写入，且会产生「状态已改、
 *    理由码未写」的中间态）。
 *
 * ## 反向自检
 *
 * 每组判据都配替身：正则失效时断言会空转，故先断言「扫描面非空」，再用构造的
 * 坏样本证明判据确实会打红。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

import {
  TRIM_REASON_CODES,
  TRIM_REASON_LABELS,
  MACHINE_REASON_CODES,
  isTrimReasonCode,
  reasonCodeLabel,
  formatTrimReason,
  isMachineReasonCode,
  trimReasonOptions,
} from '../trimReasonCodes'

// ────────────────────────── 仓库根定位（双哨兵） ──────────────────────────

function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i += 1) {
    const a = path.join(dir, 'backend', 'app', 'services', 'procedure_trim_engine.py')
    const b = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    if (fs.existsSync(a) && fs.existsSync(b)) return dir
    dir = path.dirname(dir)
  }
  throw new Error('repoRoot 定位失败：未同时找到两个哨兵文件')
}

const ROOT = repoRoot()

function readRepo(rel: string): string {
  const p = path.join(ROOT, rel)
  if (!fs.existsSync(p)) throw new Error(`文件不存在：${rel}`)
  return fs.readFileSync(p, 'utf-8')
}

/**
 * 剥 Python `#` 行注释（带字符串状态，不被字符串里的 `#` 骗）。
 *
 * 必须剥：本 spec 的说明注释里会写出被禁的形态（如「禁 `suggestion_state` 二次写入」），
 * 不剥会把说明文字数成真实代码。
 */
function stripPyComments(src: string): string {
  const out: string[] = []
  for (const line of src.split('\n')) {
    let inS: string | null = null
    let cut = -1
    for (let i = 0; i < line.length; i += 1) {
      const ch = line[i]
      if (inS) {
        if (ch === '\\') { i += 1; continue }
        if (ch === inS) inS = null
        continue
      }
      if (ch === '"' || ch === "'") { inS = ch; continue }
      if (ch === '#') { cut = i; break }
    }
    out.push(cut >= 0 ? line.slice(0, cut) : line)
  }
  return out.join('\n')
}

/** 剥 TS 注释（带字符串/模板串状态）。 */
function stripTsComments(src: string): string {
  let out = ''
  let i = 0
  let state: 'code' | 'line' | 'block' | 'sq' | 'dq' | 'tpl' = 'code'
  while (i < src.length) {
    const c = src[i]
    const n = src[i + 1]
    if (state === 'code') {
      if (c === '/' && n === '/') { state = 'line'; i += 2; continue }
      if (c === '/' && n === '*') { state = 'block'; i += 2; continue }
      if (c === "'") { state = 'sq'; out += c; i += 1; continue }
      if (c === '"') { state = 'dq'; out += c; i += 1; continue }
      if (c === '`') { state = 'tpl'; out += c; i += 1; continue }
      out += c; i += 1; continue
    }
    if (state === 'line') {
      if (c === '\n') { state = 'code'; out += c }
      i += 1; continue
    }
    if (state === 'block') {
      if (c === '*' && n === '/') { state = 'code'; i += 2; continue }
      if (c === '\n') out += c
      i += 1; continue
    }
    // 字符串内
    if (c === '\\') { out += c + (n ?? ''); i += 2; continue }
    out += c
    if ((state === 'sq' && c === "'") || (state === 'dq' && c === '"') || (state === 'tpl' && c === '`')) {
      state = 'code'
    }
    i += 1
  }
  return out
}

/**
 * 解析 canonical trim entry 的**类型声明文本**。
 *
 * 🔴 不能「从 `canonicalTrimPreview` 往后切一段固定字符窗口」：entry 类型既可能是
 * 内联类型字面量（首版形态），也可能被抽成具名 interface **声明在函数之前**
 * （当前形态）—— 往后切会一个字段都看不到，从而在**正确实现**上打红。
 *
 * 故先取函数签名里 `entries:` 的类型引用，若是具名类型（`Xxx[]`）再回到文件里
 * 找该 interface 的声明体；是内联字面量则直接返回该字面量。
 */
function resolveTrimEntryType(src: string): string {
  const fnIdx = src.indexOf('canonicalTrimPreview')
  if (fnIdx < 0) throw new Error('扫描面失效：未找到 canonicalTrimPreview')

  // 签名区 = 函数名之后到第一个 `)` 为止（圆括号配对，容忍内联类型字面量里的括号）
  let i = src.indexOf('(', fnIdx)
  if (i < 0) throw new Error('canonicalTrimPreview 无参数列表')
  let depth = 0
  let end = -1
  for (let k = i; k < src.length; k += 1) {
    if (src[k] === '(') depth += 1
    else if (src[k] === ')') {
      depth -= 1
      if (depth === 0) { end = k; break }
    }
  }
  if (end < 0) throw new Error('canonicalTrimPreview 参数列表括号未配平')
  const sig = src.slice(i, end + 1)

  const m = /entries\s*:\s*([A-Za-z_$][\w$]*)\s*\[\s*\]/.exec(sig)
  if (m) {
    // 具名类型 → 回文件里取 interface / type 声明体
    const name = m[1]
    const decl = new RegExp(`(?:interface|type)\\s+${name}\\b[^{]*\\{`).exec(src)
    if (!decl) throw new Error(`未找到类型 ${name} 的声明`)
    const braceStart = src.indexOf('{', decl.index)
    let d = 0
    for (let k = braceStart; k < src.length; k += 1) {
      if (src[k] === '{') d += 1
      else if (src[k] === '}') {
        d -= 1
        if (d === 0) return src.slice(braceStart, k + 1)
      }
    }
    throw new Error(`类型 ${name} 声明体花括号未配平`)
  }
  // 内联类型字面量形态：直接返回签名（字段就写在里面）
  return sig
}

/** 按缩进截取 Python 函数体（先用圆括号配对跳过参数列表与返回类型注解）。 */
function pyFuncBody(src: string, name: string): string {
  const m = new RegExp(`^([ \\t]*)def\\s+${name}\\s*\\(`, 'm').exec(src)
  if (!m) throw new Error(`未找到 def ${name}`)
  const indent = m[1].length
  // 圆括号配对跳过签名
  let i = src.indexOf('(', m.index)
  let depth = 0
  for (; i < src.length; i += 1) {
    if (src[i] === '(') depth += 1
    else if (src[i] === ')') { depth -= 1; if (depth === 0) { i += 1; break } }
  }
  const colon = src.indexOf(':', i)
  const lines = src.slice(colon + 1).split('\n')
  const body: string[] = []
  for (let k = 1; k < lines.length; k += 1) {
    const ln = lines[k]
    if (ln.trim() === '') { body.push(ln); continue }
    const ind = ln.length - ln.trimStart().length
    if (ind <= indent) break
    body.push(ln)
  }
  return body.join('\n')
}

// ═══════════════════════════════════════════════════════════════════════════
// A. 跨前后端交叉锁死（R8.1 / R14.5）
// ═══════════════════════════════════════════════════════════════════════════

/** 从后端 py 源码抽 `TrimReasonCode` 的全部取值（按声明顺序）。 */
function backendReasonCodes(): string[] {
  const src = stripPyComments(readRepo('backend/app/services/procedure_trim_engine.py'))
  const start = src.indexOf('class TrimReasonCode')
  expect(start, 'TrimReasonCode 类声明未找到（真源位置变了？）').toBeGreaterThan(0)
  const lines = src.slice(start).split('\n')
  const values: string[] = []
  for (let i = 1; i < lines.length; i += 1) {
    const ln = lines[i]
    if (ln.trim() === '') continue
    const ind = ln.length - ln.trimStart().length
    if (ind === 0) break // 出了类体
    const m = /^\s*[A-Z_][A-Z0-9_]*\s*=\s*["']([a-z_]+)["']/.exec(ln)
    if (m) values.push(m[1])
  }
  return values
}

describe('A. 理由码跨前后端交叉锁死', () => {
  it('A1. 扫描面非空自检：后端至少能抽出 4 个取值', () => {
    const codes = backendReasonCodes()
    expect(codes.length, '抽取器失效（返回过少），后续比对会空转').toBeGreaterThanOrEqual(4)
  })

  it('A2. 前端镜像与后端 enum 取值集合精确相等', () => {
    const be = backendReasonCodes()
    const fe = [...TRIM_REASON_CODES]
    const missingInFe = be.filter((c) => !fe.includes(c as never))
    const missingInBe = fe.filter((c) => !be.includes(c))
    expect(
      missingInFe,
      `后端新增了取值而前端未跟进：${missingInFe.join(', ')} —— `
      + '前端会把它显示成原始英文码。请同步 TRIM_REASON_CODES 与 TRIM_REASON_LABELS。',
    ).toEqual([])
    expect(
      missingInBe,
      `前端有取值而后端 enum 没有：${missingInBe.join(', ')} —— `
      + '提交该码会被后端 422 拒绝。请先在 TrimReasonCode 中登记。',
    ).toEqual([])
  })

  it('A3. 前端镜像顺序与后端声明顺序一致（便于定位漂移）', () => {
    expect([...TRIM_REASON_CODES]).toEqual(backendReasonCodes())
  })

  it('A4. 本 spec 新增的四个取值确实已在后端登记（防被回退）', () => {
    const be = backendReasonCodes()
    for (const code of ['no_data', 'below_trivial', 'below_materiality', 'covered_elsewhere']) {
      expect(be, `后端 TrimReasonCode 缺 ${code}（Task 12 成果被回退？）`).toContain(code)
    }
  })

  it('A5. 既有四个取值一个都不许少（additive 扩展不得改动存量）', () => {
    const be = backendReasonCodes()
    for (const code of [
      'no_related_business', 'low_risk_assessment', 'control_test_effective', 'other',
    ]) {
      expect(be, `既有取值 ${code} 被删除 —— 存量记录的理由码会失去含义`).toContain(code)
    }
  })

  it('A6. 反向自检：抽取器对构造的坏样本能发现差异', () => {
    const be = backendReasonCodes()
    const tampered = be.filter((c) => c !== 'other')
    expect(tampered).not.toEqual([...TRIM_REASON_CODES])
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// B. 标签完备性与三态语义（R8.4 / R8.5）
// ═══════════════════════════════════════════════════════════════════════════

describe('B. 中文标签与三态语义', () => {
  it('B1. 每个取值都有中文标签，无缺无余', () => {
    const labelKeys = Object.keys(TRIM_REASON_LABELS).sort()
    expect(labelKeys).toEqual([...TRIM_REASON_CODES].sort())
  })

  it('B2. 标签非空、非占位、不得是英文码本身', () => {
    for (const code of TRIM_REASON_CODES) {
      const label = TRIM_REASON_LABELS[code]
      expect(label.trim().length, `${code} 标签过短`).toBeGreaterThanOrEqual(4)
      expect(label, `${code} 标签仍是英文码`).not.toBe(code)
      expect(label, `${code} 标签是占位文本`).not.toMatch(/TODO|待补|placeholder/i)
      expect(/[\u4e00-\u9fa5]/.test(label), `${code} 标签无中文（违反 UI 全中文化）`).toBe(true)
    }
  })

  it('B3. 🔴 存量兼容：null/空 返回 null 而不是「未知理由」', () => {
    // 改造前粗裁只有自由文本 skip_reason。返回「未知理由」会把「有理由但没有码」
    // 谎报成「没有理由」，让复核视图的「缺理由」计数虚高。
    expect(reasonCodeLabel(null)).toBeNull()
    expect(reasonCodeLabel(undefined)).toBeNull()
    expect(reasonCodeLabel('')).toBeNull()
    expect(reasonCodeLabel('   ')).toBeNull()
  })

  it('B4. 未登记的码原样回显，不返回空白', () => {
    expect(reasonCodeLabel('brand_new_code')).toBe('brand_new_code')
  })

  it('B5. 已登记的码返回中文标签', () => {
    expect(reasonCodeLabel('below_materiality')).toBe(TRIM_REASON_LABELS.below_materiality)
  })

  it('B6. isTrimReasonCode 三态判定', () => {
    expect(isTrimReasonCode('no_data')).toBe(true)
    expect(isTrimReasonCode('nope')).toBe(false)
    expect(isTrimReasonCode(null)).toBe(false)
    expect(isTrimReasonCode(123)).toBe(false)
  })

  it('B7. formatTrimReason：存量只有自由文本时原文返回', () => {
    expect(formatTrimReason({ skipReason: '本期无该类交易或余额' }))
      .toBe('本期无该类交易或余额')
    expect(formatTrimReason({ reasonCode: null, skipReason: '手工理由' })).toBe('手工理由')
  })

  it('B8. formatTrimReason：有码有文本时拼接，且不重复拼接', () => {
    const label = TRIM_REASON_LABELS.below_trivial
    expect(formatTrimReason({ reasonCode: 'below_trivial', skipReason: '余额 100.00 元' }))
      .toBe(`${label}：余额 100.00 元`)
    // 文本已含标签 → 不重复
    expect(formatTrimReason({ reasonCode: 'below_trivial', skipReason: `${label}，余额 100 元` }))
      .toBe(`${label}，余额 100 元`)
    // 文本为空 → 只返标签
    expect(formatTrimReason({ reasonCode: 'below_trivial', skipReason: '' })).toBe(label)
  })

  it('B9. 机器判据分类：三个决策内核产出的码，人工码不在其中', () => {
    expect([...MACHINE_REASON_CODES].sort())
      .toEqual(['below_materiality', 'below_trivial', 'no_data'])
    expect(isMachineReasonCode('no_data')).toBe(true)
    expect(isMachineReasonCode('other')).toBe(false)
    expect(isMachineReasonCode(null)).toBe(false)
  })

  it('B10. 机器判据码全部在取值域内（防写错字符串）', () => {
    for (const code of MACHINE_REASON_CODES) {
      expect(TRIM_REASON_CODES, `${code} 不在取值域内`).toContain(code as never)
    }
  })

  it('B11. trimReasonOptions 覆盖全部取值且 label 与常量表一致', () => {
    const opts = trimReasonOptions()
    expect(opts.map((o) => o.value)).toEqual([...TRIM_REASON_CODES])
    for (const o of opts) expect(o.label).toBe(TRIM_REASON_LABELS[o.value])
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// C. canonical trim 契约 additive 扩展（R8.7 / R8.8 / R8.9）
// ═══════════════════════════════════════════════════════════════════════════

describe('C. canonical trim scope entry 的 reason_code 扩展', () => {
  it('C1. router pydantic 模型 TrimSchemeEntry 声明了 reason_code', () => {
    const src = stripPyComments(readRepo('backend/app/routers/procedure_trim.py'))
    const start = src.indexOf('class TrimSchemeEntry')
    expect(start, 'TrimSchemeEntry 未找到').toBeGreaterThan(0)
    const block = src.slice(start, start + 2000)
    expect(
      /reason_code\s*:\s*str\s*\|\s*None/.test(block),
      'TrimSchemeEntry 缺 reason_code 字段 ⇒ 理由码无处可落（会被 pydantic 静默丢弃）',
    ).toBe(true)
  })

  it('C2. service 归一函数消费 reason_code', () => {
    const src = stripPyComments(readRepo('backend/app/services/procedure_trim_service.py'))
    const body = pyFuncBody(src, '_normalize_entry')
    expect(body.length, 'pyFuncBody 截取失败，后续断言会空转').toBeGreaterThan(200)
    expect(
      body.includes('reason_code'),
      '_normalize_entry 未处理 reason_code ⇒ 前端传了后端也不认',
    ).toBe(true)
  })

  it('C3. 🔴 零回归结构性保证：不含 reason_code 时归一结果不得产生该键', () => {
    // 归一结果进 request payload，payload 参与 preview/apply 防篡改比对。
    // 多一个 `"reason_code": null` 会让存量调用方（不传该字段）的 apply 409。
    const src = stripPyComments(readRepo('backend/app/services/procedure_trim_service.py'))
    const body = pyFuncBody(src, '_normalize_entry')
    // 必须是条件性写入：出现在 if 之后 / 或经 dict 条件合并，而不是无条件写死在字面量里
    const unconditional = /^\s*"reason_code"\s*:/m.test(body)
    expect(
      unconditional,
      '归一结果里无条件写死 "reason_code" 键 ⇒ 不传该字段的存量调用方 payload 会变（409）。'
      + '必须条件性写入（仅当传入非空时才加该键）。',
    ).toBe(false)
    expect(
      /if\s+reason_code/.test(body) || /reason_code\s+is\s+not\s+None/.test(body),
      '未见 reason_code 的条件判断 ⇒ 无法确认是条件性写入',
    ).toBe(true)
  })

  it('C4. 🔴 理由码与状态同一次请求提交：不存在第二次写入路径', () => {
    const src = stripPyComments(readRepo('backend/app/services/procedure_trim_service.py'))
    // suggestion_state 的写入必须发生在 apply 的同一事务内（与 set_scope_status 相邻），
    // 不得有独立的「补写理由码」端点或方法。
    const routerSrc = stripPyComments(readRepo('backend/app/routers/procedure_trim.py'))
    expect(
      /reason.?code/i.test(routerSrc.replace(/reason_code\s*:\s*str/g, '')) === false
      || /@router\.(post|put|patch)[^\n]*reason/i.test(routerSrc) === false,
      '发现疑似独立的理由码补写端点 ⇒ 会产生「状态已改、理由码未写」中间态',
    ).toBe(true)
    expect(
      src.includes('suggestion_state'),
      'service 未写 suggestion_state ⇒ 理由码没有落库',
    ).toBe(true)
  })

  it('C5. 🔴 理由码不得编码进 skip_reason 文本', () => {
    const src = stripPyComments(readRepo('backend/app/services/procedure_trim_service.py'))
    const body = pyFuncBody(src, '_normalize_entry')
    // 形如 f"[{reason_code}] {skip_reason}" 的拼接
    expect(
      /skip_reason\s*=\s*f?["'][^"']*\{\s*reason_code/.test(body)
      || /reason_code[^\n]*\+[^\n]*skip_reason/.test(body),
      '把理由码拼进 skip_reason 文本 ⇒ 结构化理由码退化为自由文本，无法按码统计',
    ).toBe(false)
  })

  it('C6. 前端 commonApi 的 canonical trim entry 类型含 reason_code', () => {
    const src = stripTsComments(readRepo('audit-platform/frontend/src/services/commonApi.ts'))
    expect(src.includes('canonicalTrimPreview'), '扫描面失效：未找到 canonicalTrimPreview').toBe(true)
    const block = resolveTrimEntryType(src)
    expect(
      block.includes('reason_code'),
      'canonicalTrimPreview/Apply 的 entry 类型缺 reason_code ⇒ TS 层拦住理由码提交',
    ).toBe(true)
  })

  it('C7. 前端 reason_code 为可选字段（存量调用方不传即可）', () => {
    const src = stripTsComments(readRepo('audit-platform/frontend/src/services/commonApi.ts'))
    const block = resolveTrimEntryType(src)
    expect(
      /reason_code\?\s*:/.test(block),
      'reason_code 必须是可选字段（`reason_code?:`）—— 必填会让既有调用点全部 TS 报错',
    ).toBe(true)
  })

  it('C6b. 反向自检：entry 类型解析器确实跟进了具名 interface', () => {
    // 🔴 首版判据是「从 canonicalTrimPreview 处向后 slice 3000 字符」，在把 entry
    //    类型从内联字面量重构成**具名 interface** 后必然假红 —— interface 声明在
    //    函数**之前**，向后 slice 取不到；且 stripTsComments 会把提到 reason_code 的
    //    注释一并剥掉。故解析器必须跟进类型引用。本自检钉死这一点。
    const src = stripTsComments(readRepo('audit-platform/frontend/src/services/commonApi.ts'))
    const resolved = resolveTrimEntryType(src)
    expect(resolved.length, 'entry 类型解析结果为空 ⇒ 解析器失效，C6/C7 变成空转').toBeGreaterThan(20)
    // 解析结果必须真的是「字段声明块」而不是函数签名片段
    expect(/kind\s*:/.test(resolved), '解析结果不含 kind 字段 ⇒ 取到的不是 entry 类型').toBe(true)
    expect(
      /target_status\s*:/.test(resolved),
      '解析结果不含 target_status ⇒ 取到的不是 canonical scope entry',
    ).toBe(true)

    // 复现首版缺陷形态：向后 slice 拿不到具名 interface 的字段
    const naiveStart = src.indexOf('canonicalTrimPreview')
    const naive = src.slice(naiveStart, naiveStart + 3000)
    expect(
      naive.includes('reason_code') === false,
      '朴素向后 slice 在当前源码上未复现缺陷 ⇒ 本自检失去意义，需重新设计',
    ).toBe(true)
  })

  it('C6b. 反向自检：类型解析器对两种声明形态都有效，缺字段时能打红', () => {
    // 形态一：具名 interface 声明在函数之前（当前生产形态）
    const named = [
      'export interface Foo {',
      '  kind: string',
      '  reason_code?: string | null',
      '}',
      'export async function canonicalTrimPreview(pid: string, entries: Foo[]) {}',
    ].join('\n')
    expect(resolveTrimEntryType(named)).toContain('reason_code?')

    // 形态二：内联类型字面量（首版形态，仍须支持）
    const inline = 'export async function canonicalTrimPreview(pid: string, '
      + 'entries: Array<{ kind: string; reason_code?: string | null }>) {}'
    expect(resolveTrimEntryType(inline)).toContain('reason_code?')

    // 缺字段必须能被发现（证明断言不是恒真）
    const missing = [
      'export interface Foo {',
      '  kind: string',
      '}',
      'export async function canonicalTrimPreview(pid: string, entries: Foo[]) {}',
    ].join('\n')
    expect(resolveTrimEntryType(missing).includes('reason_code')).toBe(false)
  })

  it('C8. 后端 _VALID_TRIM_REASON_CODES 由 enum 派生而非手写字面量集合', () => {
    const src = stripPyComments(readRepo('backend/app/services/procedure_trim_service.py'))
    expect(src.includes('_VALID_TRIM_REASON_CODES'), '未找到取值域常量').toBe(true)
    const m = /_VALID_TRIM_REASON_CODES[^\n]*=([^\n]*(?:\n[ \t]+[^\n]*)*)/.exec(src)
    expect(m, '常量声明未找到').not.toBeNull()
    const decl = m![1]
    expect(
      /TrimReasonCode/.test(decl),
      '取值域应从 TrimReasonCode 派生 —— 手写字面量集合会在 enum 新增取值时静默拒绝新码',
    ).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// D. 纯度（无 Vue 依赖、无 IO）
// ═══════════════════════════════════════════════════════════════════════════

describe('D. 模块纯度', () => {
  it('D1. trimReasonCodes.ts 零 Vue 依赖、零 IO', () => {
    const src = readRepo(
      'audit-platform/frontend/src/components/workpaper/composables/trimReasonCodes.ts',
    )
    const code = stripTsComments(src)
    expect(/from\s+['"]vue['"]/.test(code), '不得 import vue').toBe(false)
    expect(/\bfetch\s*\(|axios|http\./.test(code), '不得发请求').toBe(false)
    expect(/localStorage|sessionStorage/.test(code), '不得读写 storage').toBe(false)
  })

  it('D2. 禁用 pm / te / sat 缩写作标识符（术语铁律）', () => {
    const code = stripTsComments(readRepo(
      'audit-platform/frontend/src/components/workpaper/composables/trimReasonCodes.ts',
    ))
    for (const bad of ['pm', 'te', 'sat']) {
      const re = new RegExp(`(?:^|[^\\w$])${bad}\\s*[:=]`, 'm')
      expect(re.test(code), `不得用 ${bad} 作标识符（平台既有命名与审计通用含义相反）`).toBe(false)
    }
  })
})
