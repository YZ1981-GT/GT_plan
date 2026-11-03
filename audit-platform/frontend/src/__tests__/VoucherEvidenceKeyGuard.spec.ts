/**
 * 凭证证据键守卫（spec attachment-voucher-evidence-binding 需求 4.5，design §6）
 *
 * 用户诉求：抽凭检查行上传 / 识别的原件按凭证身份挂（`evidence_voucher_key` / `voucher_key`），
 * 别的底稿抽到同一张凭证时能查到并引用。漏带凭证键不会报错，只是附件退回成普通行内证据 —— 只能靠守卫拦。
 *
 * 扫描范围 = 凭证检查宿主（模板渲染 VoucherRowMetaCell，或脚本调 useVoucherCheckFill）、宿主的兄弟组件里以 `:row="…"`
 * 渲染的组件（逐笔核对弹窗），以及它们直接 import 的组件 / 组合式函数。判据只看行级位置（表页级上传没有行，不带凭证键是对的）：
 *  A. `appendRowEvidence(form, sheet, cell, row)` 与 `useRowEvidence()` 返回值的 `.append(…)`：带了单元格就必须带第四参数（行）；
 *  B. `buildLinkedOcrFormData` / `appendOcrLinkageFields` / `uploadWorkpaperEvidence` / `runWorkpaperOcr` 的选项对象：
 *     有 `evidenceCell` / `cellRef` 就必须有 `voucherKey`（选项不是对象字面量 ⇒ 核对不了，同样算违规）；
 *  C. 模板里的 `<ItemAttachment>`（行级附件槽位）必须带 `voucher-key`；
 *  D. 交给组合式函数的位置对象（有 `sheet` 与非空 `cell` 键）必须带 `row`（J1 / K1 这类把位置转交 appendRowEvidence 的写法）。
 * 豁免 voucherEvidenceKeyExemptions.json 只许删：文件存在、确实违规、带按实情核对的 verify。
 * 扫描器自检：合成源码里的违规写法必须被抓到（含扫描器只认 `appendRowEvidence(` 的退化）；扫描面不得塌缩。
 */
import { describe, it, expect } from 'vitest'
import { existsSync } from 'fs'
import { posix } from 'path'
import {
  FRONTEND_SRC,
  readSource,
  stripHtmlComments,
  stripJsComments,
  toSrcRelative,
  walkSourceFiles,
} from './_helpers/frontendSourceScan'
import exemptionsJson from './voucherEvidenceKeyExemptions.json'

type Rule = 'append' | 'linkage' | 'item-attachment' | 'position'
type Verify = { type: 'itemAttachmentOutsideRows' }
interface Exemption {
  file: string
  rule: Rule
  owner: string
  reason: string
  verify: Verify
}
const EXEMPTIONS = exemptionsJson as Exemption[]

/** 相对 src 的 posix 路径 → 原文 */
type Sources = Map<string, string>
interface Violation { file: string; rule: Rule; why: string }

/** 定义这些共享函数 / 组件的文件本身不在判据内（它们就是被判的对象） */
const DEFINITION_FILES = new Set([
  'components/attachment/rowEvidence.ts',
  'components/attachment/workpaperEvidence.ts',
  'components/workpaper/composables/ocrAttachmentLinkage.ts',
  'components/workpaper/ItemAttachment.vue',
])

// ─── 源码切分 ─────────────────────────────────────────────────────────────────

function templateOf(rel: string, text: string): string {
  if (!rel.endsWith('.vue')) return ''
  const m = /<template[^>]*>([\s\S]*)<\/template>/.exec(stripHtmlComments(text))
  return m ? m[1] : ''
}

function scriptOf(rel: string, text: string): string {
  if (!rel.endsWith('.vue')) return stripJsComments(text)
  const parts = [...text.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map((m) => m[1])
  return stripJsComments(parts.join('\n'))
}

/** 模板属性表达式与脚本一样按代码切参数（模板里的箭头函数、调用也要看） */
function codeOf(rel: string, text: string): string {
  return `${scriptOf(rel, text)}\n${templateOf(rel, text)}`
}

// ─── 括号 / 字符串感知的切分 ──────────────────────────────────────────────────

function skipQuoted(code: string, i: number): number {
  const q = code[i]
  i += 1
  while (i < code.length && code[i] !== q) i += code[i] === '\\' ? 2 : 1
  return i + 1
}

function skipTemplate(code: string, i: number): number {
  i += 1
  while (i < code.length) {
    const c = code[i]
    if (c === '\\') { i += 2; continue }
    if (c === '`') return i + 1
    if (c === '$' && code[i + 1] === '{') {
      let depth = 1
      i += 2
      while (i < code.length && depth > 0) {
        const d = code[i]
        if (d === '"' || d === "'") { i = skipQuoted(code, i); continue }
        if (d === '`') { i = skipTemplate(code, i); continue }
        if (d === '{') depth += 1
        else if (d === '}') depth -= 1
        i += 1
      }
      continue
    }
    i += 1
  }
  return i
}

/** 从开括号（`(` 或 `{`）起切出顶层逗号分隔的各段；括号不配平返回 null */
function splitTopLevel(code: string, open: number): string[] | null {
  const parts: string[] = []
  let depth = 0
  let start = open + 1
  let i = open
  while (i < code.length) {
    const c = code[i]
    if (c === '"' || c === "'") { i = skipQuoted(code, i); continue }
    if (c === '`') { i = skipTemplate(code, i); continue }
    if (c === '(' || c === '[' || c === '{') depth += 1
    else if (c === ')' || c === ']' || c === '}') {
      depth -= 1
      if (depth === 0) {
        parts.push(code.slice(start, i))
        const trimmed = parts.map((p) => p.trim())
        if (trimmed.length && trimmed[trimmed.length - 1] === '') trimmed.pop() // 尾逗号
        return trimmed
      }
    } else if (c === ',' && depth === 1) {
      parts.push(code.slice(start, i))
      start = i + 1
    }
    i += 1
  }
  return null
}

/** `name(` 的全部调用（排除 `function name(` 定义与 `.name(` 方法调用），返回各次调用的参数段 */
function callsOf(code: string, name: string): string[][] {
  const out: string[][] = []
  const re = new RegExp(`(^|[^\\w.$])${name}\\s*\\(`, 'g')
  let m: RegExpExecArray | null
  while ((m = re.exec(code)) !== null) {
    const before = code.slice(Math.max(0, m.index - 12), m.index + m[1].length)
    if (/function\s*$/.test(before)) continue
    const args = splitTopLevel(code, m.index + m[0].length - 1)
    if (args) out.push(args)
  }
  return out
}

/** `recv.method(` 的全部调用参数段 */
function methodCallsOf(code: string, recv: string, method: string): string[][] {
  const out: string[][] = []
  const re = new RegExp(`(^|[^\\w.$])${recv}\\s*\\.\\s*${method}\\s*\\(`, 'g')
  let m: RegExpExecArray | null
  while ((m = re.exec(code)) !== null) {
    const args = splitTopLevel(code, m.index + m[0].length - 1)
    if (args) out.push(args)
  }
  return out
}

const EMPTY_ARG = /^(|null|undefined|''|""|``)$/

/** 对象字面量 `{ … }` 的顶层键（`key: v` / 简写 `key` / `'key': v`）；含展开 `...x` 时 spread=true */
function objectKeys(literal: string): { keys: Map<string, string>; spread: boolean } | null {
  const text = literal.trim()
  if (!text.startsWith('{')) return null
  const props = splitTopLevel(text, 0)
  return props ? keysOfProps(props) : null
}

function keysOfProps(props: string[]): { keys: Map<string, string>; spread: boolean } {
  const keys = new Map<string, string>()
  let spread = false
  for (const p of props) {
    if (p.startsWith('...')) { spread = true; continue }
    const m = /^['"]?([A-Za-z_$][\w$]*)['"]?\s*(?::([\s\S]*))?$/.exec(p)
    if (m) keys.set(m[1], (m[2] ?? m[1]).trim())
  }
  return { keys, spread }
}

// ─── 扫描范围：凭证检查宿主 + 一层直接依赖 ────────────────────────────────────

const kebab = (name: string) => name.replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase()
const rendersTag = (tpl: string, name: string) => new RegExp(`<(${name}|${kebab(name)})\\b`).test(tpl)

function isVoucherHost(rel: string, text: string): boolean {
  if (rendersTag(templateOf(rel, text), 'VoucherRowMetaCell')) return true
  return /(^|[^\w.$])useVoucherCheckFill\s*\(/.test(scriptOf(rel, text))
}

const IMPORT_RE = /(?:import\s+[^;'"]*?from\s*|import\s*\(\s*)['"]([^'"]+)['"]/g

function resolveImport(fromRel: string, spec: string, sources: Sources): string | null {
  if (!spec.startsWith('.') && !spec.startsWith('@/')) return null
  const base = spec.startsWith('@/') ? posix.normalize(spec.slice(2)) : posix.normalize(posix.join(posix.dirname(fromRel), spec))
  for (const cand of [base, `${base}.ts`, `${base}.vue`, `${base}/index.ts`]) if (sources.has(cand)) return cand
  return null
}

const IMPORT_VUE_RES = [
  /import\s+(\w+)\s+from\s+['"]([^'"]+\.vue)['"]/g,
  /(\w+)\s*=\s*defineAsyncComponent\(\s*\(\)\s*=>\s*import\(\s*['"]([^'"]+\.vue)['"]/g,
]

/**
 * 拿到凭证检查行的子组件：import 了宿主的页面里、以 `:row="…"` 渲染的组件（逐笔单据核对弹窗这类 ——
 * 表格是宿主，弹窗是表格的兄弟，只看宿主的直接依赖会漏掉）。
 */
function rowReceivers(hosts: Set<string>, sources: Sources): string[] {
  const out = new Set<string>()
  for (const [rel, text] of sources) {
    if (!rel.endsWith('.vue')) continue
    const script = scriptOf(rel, text)
    const imports = IMPORT_VUE_RES.flatMap((re) => [...script.matchAll(re)])
      .map((m) => ({ name: m[1], file: resolveImport(rel, m[2], sources) }))
    if (!imports.some((i) => i.file && hosts.has(i.file))) continue
    const tpl = templateOf(rel, text)
    for (const { name, file } of imports) {
      if (!file || hosts.has(file)) continue
      for (const m of tpl.matchAll(new RegExp(`<(${name}|${kebab(name)})\\b`, 'g'))) {
        if (/\s:row="/.test(tpl.slice(m.index!, tagEnd(tpl, m.index!) + 1))) out.add(file)
      }
    }
  }
  return [...out]
}

function scanScope(sources: Sources): { hosts: string[]; files: string[] } {
  const hostList = [...sources.entries()].filter(([rel, text]) => isVoucherHost(rel, text)).map(([rel]) => rel)
  const hosts = [...hostList, ...rowReceivers(new Set(hostList), sources)]
  const files = new Set(hosts)
  for (const host of hosts) {
    for (const m of scriptOf(host, sources.get(host)!).matchAll(IMPORT_RE)) {
      const dep = resolveImport(host, m[1], sources)
      if (dep) files.add(dep)
    }
  }
  for (const d of DEFINITION_FILES) files.delete(d)
  return { hosts, files: [...files].sort() }
}

// ─── 判据 ─────────────────────────────────────────────────────────────────────

const short = (args: string[]) => args.join(', ').replace(/\s+/g, ' ').slice(0, 120)

function appendViolations(code: string): string[] {
  const calls = callsOf(code, 'appendRowEvidence')
  for (const m of code.matchAll(/(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*useRowEvidence\s*\(/g)) {
    calls.push(...methodCallsOf(code, m[1], 'append'))
  }
  return calls
    .filter((args) => args.length >= 3 && !EMPTY_ARG.test(args[2]) && (args.length < 4 || EMPTY_ARG.test(args[3])))
    .map((args) => `行级位置没带行（凭证键）：append(${short(args)})`)
}

/** [函数名, 选项参数下标, 行级位置的键] */
const LINKAGE_CALLS: Array<[string, number, string]> = [
  ['buildLinkedOcrFormData', 1, 'evidenceCell'],
  ['appendOcrLinkageFields', 1, 'evidenceCell'],
  ['uploadWorkpaperEvidence', 0, 'cellRef'],
  ['runWorkpaperOcr', 2, 'evidenceCell'], // I2 检查表的行内识别（i2EnhancementHelpers）
]

function linkageViolations(code: string): string[] {
  const out: string[] = []
  for (const [name, idx, cellKey] of LINKAGE_CALLS) {
    for (const args of callsOf(code, name)) {
      const opt = args[idx]
      if (opt === undefined) continue
      const obj = objectKeys(opt)
      if (!obj) { out.push(`${name} 的选项不是对象字面量，核对不了凭证键：${short(args)}`); continue }
      const cell = obj.keys.get(cellKey)
      if (cell === undefined || EMPTY_ARG.test(cell)) continue
      if (!obj.keys.has('voucherKey')) out.push(`${name} 带了 ${cellKey} 却没带 voucherKey：${short(args)}`)
    }
  }
  return out
}

/** 起始标签结束位置（引号内的 `>` 不算） */
function tagEnd(tpl: string, from: number): number {
  let quote: string | null = null
  for (let i = from; i < tpl.length; i++) {
    const c = tpl[i]
    if (quote) { if (c === quote) quote = null } else if (c === '"' || c === "'") quote = c
    else if (c === '>') return i
  }
  return tpl.length
}

function itemAttachmentTags(tpl: string): string[] {
  const out: string[] = []
  for (const m of tpl.matchAll(/<(ItemAttachment|item-attachment)\b/g)) out.push(tpl.slice(m.index!, tagEnd(tpl, m.index!) + 1))
  return out
}

function itemAttachmentViolations(rel: string, text: string): string[] {
  return itemAttachmentTags(templateOf(rel, text))
    .filter((tag) => !/\s:?(voucher-key|voucherKey)=/.test(tag))
    .map((tag) => `附件槽位没带 voucher-key：${tag.replace(/\s+/g, ' ').slice(0, 120)}`)
}

/**
 * 交给组合式函数的位置对象 `{ sheet: …, cell: … }`（cell 非空）必须带 row。
 * `return { sheet, cell }` 是位置计算函数的返回值（小眼睛也按它读），不是上传，不算。
 */
function positionViolations(code: string): string[] {
  const out: string[] = []
  for (const m of code.matchAll(/\{\s*sheet\s*:/g)) {
    if (/\breturn\s*$/.test(code.slice(Math.max(0, m.index! - 20), m.index!))) continue
    const props = splitTopLevel(code, m.index!)
    if (!props) continue
    const obj = keysOfProps(props)
    if (obj.spread) continue
    const cell = obj.keys.get('cell')
    if (cell === undefined || EMPTY_ARG.test(cell)) continue
    if (!obj.keys.has('row')) out.push(`位置对象没带 row：{ ${short(props)} }`)
  }
  return out
}

function scan(sources: Sources): { violations: Violation[]; hosts: string[]; files: string[] } {
  const { hosts, files } = scanScope(sources)
  const violations: Violation[] = []
  for (const rel of files) {
    const text = sources.get(rel)!
    const code = codeOf(rel, text)
    for (const why of appendViolations(code)) violations.push({ file: rel, rule: 'append', why })
    for (const why of linkageViolations(code)) violations.push({ file: rel, rule: 'linkage', why })
    for (const why of itemAttachmentViolations(rel, text)) violations.push({ file: rel, rule: 'item-attachment', why })
    for (const why of positionViolations(code)) violations.push({ file: rel, rule: 'position', why })
  }
  return { violations, hosts, files }
}

function loadSources(): Sources {
  const map: Sources = new Map()
  for (const abs of walkSourceFiles(FRONTEND_SRC)) {
    if (!/\.(vue|ts)$/.test(abs)) continue
    map.set(toSrcRelative(abs), readSource(abs))
  }
  return map
}

/** 附件槽位不在表格行里：每个 ItemAttachment 的槽位号是数字字面量，且属性不引用行（row / $index / scope） */
function itemAttachmentOutsideRows(rel: string, sources: Sources): string | null {
  const tags = itemAttachmentTags(templateOf(rel, sources.get(rel) ?? ''))
  if (!tags.length) return '文件里没有 ItemAttachment'
  const rowBound = tags.filter((t) => {
    const idx = /\s:?item-index="([^"]*)"/.exec(t)?.[1]?.trim() ?? ''
    return !/^\d+$/.test(idx) || /[:@][\w-]+="[^"]*(?<![\w$])(row|\$index|scope)(?![\w$])/.test(t)
  })
  return rowBound.length ? `声称附件槽位不在行上，但 ${rowBound.length} 处按行编号或绑定了行` : null
}

function verifyExemption(ex: Exemption, sources: Sources): string | null {
  if (ex.verify?.type === 'itemAttachmentOutsideRows') return itemAttachmentOutsideRows(ex.file, sources)
  return '缺 verify（豁免必须能按实情核对）'
}

// ─── 真实源码 ─────────────────────────────────────────────────────────────────

describe('凭证检查宿主的行级证据带凭证键', () => {
  const sources = loadSources()
  const { violations, hosts, files } = scan(sources)
  const exempt = new Set(EXEMPTIONS.map((e) => `${e.file}|${e.rule}`))

  // 现值（2026-10）：宿主 80、扫描文件 361、用到这些调用的文件 47；下限取约九成，防判据静默变窄
  it('扫描面不塌缩（宿主 ≥ 72、扫描文件 ≥ 320；用到上传 / 识别调用的文件 ≥ 42）', () => {
    expect(hosts.length).toBeGreaterThanOrEqual(72)
    expect(files.length).toBeGreaterThanOrEqual(320)
    const using = files.filter((rel) => {
      const code = codeOf(rel, sources.get(rel)!)
      return /appendRowEvidence\s*\(|useRowEvidence\s*\(|buildLinkedOcrFormData\s*\(|uploadWorkpaperEvidence\s*\(|runWorkpaperOcr\s*\(|<ItemAttachment\b/
        .test(code)
    })
    expect(using.length).toBeGreaterThanOrEqual(42)
  })

  it('未豁免的行级上传 / 识别都带凭证键', () => {
    const open = violations.filter((v) => !exempt.has(`${v.file}|${v.rule}`)).map((v) => `${v.file}：${v.why}`)
    expect(open, `以下行级位置没带凭证键：\n${open.join('\n')}`).toEqual([])
  })

  it('豁免条目：文件存在、确实违规、核对项与实情一致', () => {
    const problems: string[] = []
    const violating = new Set(violations.map((v) => `${v.file}|${v.rule}`))
    for (const ex of EXEMPTIONS) {
      if (!existsSync(`${FRONTEND_SRC}/${ex.file}`)) { problems.push(`${ex.file}：文件不存在`); continue }
      if (!files.includes(ex.file)) problems.push(`${ex.file}：已不在扫描范围，请从豁免清单删除`)
      if (!violating.has(`${ex.file}|${ex.rule}`)) problems.push(`${ex.file}（${ex.rule}）：已不违规，请从豁免清单删除`)
      const bad = verifyExemption(ex, sources)
      if (bad) problems.push(`${ex.file}：${bad}`)
      if (!ex.owner?.trim() || !ex.reason?.trim()) problems.push(`${ex.file}：缺归属或原因`)
    }
    expect(problems, `豁免清单有问题：\n${problems.join('\n')}`).toEqual([])
  })

  it('豁免清单无重复', () => {
    expect(new Set(EXEMPTIONS.map((e) => `${e.file}|${e.rule}`)).size).toBe(EXEMPTIONS.length)
  })
})

// ─── 扫描器自检（合成源码）────────────────────────────────────────────────────

describe('扫描器自检', () => {
  const vue = (tpl: string, script: string) => `<template>\n${tpl}\n</template>\n<script setup lang="ts">\n${script}\n</script>\n`
  /** 凭证检查宿主：渲染「来源」列 */
  const host = (tpl: string, script: string) => vue(`<VoucherRowMetaCell :row="row" />\n${tpl}`, script)
  const run = (entries: Record<string, string>) => scan(new Map(Object.entries(entries))).violations
  const whys = (entries: Record<string, string>) => run(entries).map((v) => v.why)
  const H = 'components/workpaper/x/H.vue'
  /** 扫描器应抓到：违规清单里有一条含 want（抓不到时报「扫描器没抓到」与实际清单，不对 undefined 断言） */
  const expectCaught = (entries: Record<string, string>, want: string) =>
    expect(whys(entries), `扫描器没抓到「${want}」`).toEqual(expect.arrayContaining([expect.stringContaining(want)]))

  it('appendRowEvidence：行级不带行 ⇒ 抓到；带行 / 表页级 / 单元格为空 ⇒ 放行', () => {
    expectCaught({ [H]: host('', "appendRowEvidence(fd, 'S', rowEvidenceCell(r.id))") }, '没带行')
    expect(run({ [H]: host('', "appendRowEvidence(fd, 'S', rowEvidenceCell(r.id), r)") })).toEqual([])
    expect(run({ [H]: host('', "appendRowEvidence(fd, 'S')\nappendRowEvidence(fd, 'S', null)") })).toEqual([])
    expectCaught({ [H]: host('', "appendRowEvidence(fd, 'S', c, undefined)") }, '没带行')
  })

  it('useRowEvidence 返回值的 .append（任意变量名）同样要带行 —— 扫描器不能只认 appendRowEvidence(', () => {
    const script = (call: string) => `const ev = useRowEvidence(() => props.wpId)\n${call}`
    expectCaught({ [H]: host('', script("ev.append(fd, SHEET, rowEvidenceCell(`${s}-${r.id}`))")) }, '没带行')
    expect(run({ [H]: host('', script('ev.append(fd, SHEET, rowEvidenceCell(r.id), rows[idx])')) })).toEqual([])
    expect(run({ [H]: host('', script('ev.append(fd, SHEET)')) })).toEqual([])
  })

  it('模板里的调用也看（箭头函数里的行内识别）', () => {
    const tpl = `<el-upload :before-upload="(f: File) => appendRowEvidence(fd, 'S', rowEvidenceCell(row.id))" />`
    expectCaught({ [H]: host(tpl, '') }, '没带行')
  })

  it('识别 / 上传选项：有单元格无 voucherKey ⇒ 抓到；选项不是字面量 ⇒ 抓到；表页级 ⇒ 放行', () => {
    expectCaught({ [H]: host('', 'buildLinkedOcrFormData(file, { evidenceSheet: S, evidenceCell: c })') }, '没带 voucherKey')
    expect(run({ [H]: host('', 'buildLinkedOcrFormData(file, { evidenceSheet: S, evidenceCell: c, voucherKey: vk })') })).toEqual([])
    expect(run({ [H]: host('', 'buildLinkedOcrFormData(file, { evidenceSheet: S })') })).toEqual([])
    expectCaught({ [H]: host('', 'buildLinkedOcrFormData(file, opts)') }, '不是对象字面量')
    expectCaught({ [H]: host('', 'appendOcrLinkageFields(form, { evidenceSheet: S, evidenceCell: c })') }, '没带 voucherKey')
    expectCaught({ [H]: host('', 'await uploadWorkpaperEvidence({ projectId, wpId, file, sheetKey: S, cellRef: c })') }, '没带 voucherKey')
    expect(run({ [H]: host('', 'await uploadWorkpaperEvidence({ projectId, wpId, file, sheetKey: S, cellRef: c, voucherKey })') })).toEqual([])
    expectCaught({ [H]: host('', 'await runWorkpaperOcr(w, file, { projectId, evidenceSheet: S, evidenceCell: c })') }, '没带 voucherKey')
  })

  it('ItemAttachment 不带 voucher-key ⇒ 抓到；带了 ⇒ 放行', () => {
    expectCaught({ [H]: host('<ItemAttachment :wp-id="w" sheet-key="S" :item-index="i" />', '') }, 'voucher-key')
    expect(run({ [H]: host('<ItemAttachment :wp-id="w" sheet-key="S" :item-index="i" :voucher-key="rowVoucherKey(row)" />', '') }))
      .toEqual([])
  })

  it('位置对象：有单元格无 row ⇒ 抓到；带 row / 表页级 / 位置函数的返回值 ⇒ 放行', () => {
    expectCaught({ [H]: host('', 'uploadAndMerge(id, f, d, cb, { sheet: S, cell: rowEvidenceCell(id) })') }, '没带 row')
    expect(run({ [H]: host('', 'uploadAndMerge(id, f, d, cb, { sheet: S, cell: rowEvidenceCell(id), row })') })).toEqual([])
    expect(run({ [H]: host('', 'uploadAndMerge(id, f, d, cb, { sheet: S, cell: null })') })).toEqual([])
    expect(run({ [H]: host('', 'function pos(id) { return { sheet: S, cell: rowEvidenceCell(id) } }') })).toEqual([])
    expectCaught({ [H]: host('', 'open ? { sheet: S, cell: c } : undefined') }, '没带 row')
  })

  it('注释里的调用不算', () => {
    expect(run({ [H]: host('<!-- <ItemAttachment :item-index="i" /> -->', "// appendRowEvidence(fd, 'S', c)") })).toEqual([])
  })

  it('范围：非宿主不看；宿主的直接依赖要看；调 useVoucherCheckFill 的组合式函数也是宿主', () => {
    const bad = "export function useX() { appendRowEvidence(fd, 'S', rowEvidenceCell(id)) }"
    expect(run({ 'components/workpaper/x/N.vue': vue('<span />', "appendRowEvidence(fd, 'S', c)") })).toEqual([])
    expect(run({
      [H]: host('', "import { useX } from '../composables/useX'"),
      'components/workpaper/composables/useX.ts': bad,
    }).map((v) => v.file)).toEqual(['components/workpaper/composables/useX.ts'])
    expect(run({ 'components/workpaper/composables/useY.ts': `useVoucherCheckFill({})\n${bad}` }).map((v) => v.file))
      .toEqual(['components/workpaper/composables/useY.ts'])
  })

  it('范围：宿主的兄弟组件里以 `:row="…"` 渲染的（逐笔核对弹窗）也要看；不带行渲染的不算', () => {
    const page = (tpl: string) => vue(tpl, "import Table from './Table.vue'\nimport Dialog from './Dialog.vue'")
    const files = {
      'components/workpaper/x/Table.vue': host('', ''),
      'components/workpaper/x/Dialog.vue': vue('<span />', "appendRowEvidence(fd, 'S', c)"),
    }
    expect(run({ ...files, 'components/workpaper/x/Page.vue': page('<Table /><Dialog :row="active" />') }).map((v) => v.file))
      .toEqual(['components/workpaper/x/Dialog.vue'])
    expect(run({ ...files, 'components/workpaper/x/Page.vue': page('<Table /><Dialog />') })).toEqual([])
  })

  it('豁免核对：声称附件槽位不在行上、实际绑定了行 ⇒ 报出', () => {
    const rel = 'components/workpaper/x/S.vue'
    const ex: Exemption = { file: rel, rule: 'item-attachment', owner: 'o', reason: 'r', verify: { type: 'itemAttachmentOutsideRows' } }
    const tag = (attrs: string) => new Map([[rel, vue(`<ItemAttachment sheet-key="S" ${attrs} />`, '')]])
    expect(verifyExemption(ex, tag(':item-index="0"'))).toBeNull()
    for (const attrs of [':item-index="$index"', ':item-index="i"', ':item-index="0" :title="row.name"']) {
      expect(verifyExemption(ex, tag(attrs)) ?? '（核对通过）', attrs).toContain('绑定了行')
    }
  })
})
