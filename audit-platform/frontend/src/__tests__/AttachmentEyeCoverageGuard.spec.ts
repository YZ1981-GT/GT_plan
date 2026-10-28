/**
 * 底稿附件小眼睛覆盖守卫（spec attachment-inline-preview ADR-AIP-06）
 *
 * 用户诉求：每个底稿里有附件的地方都有小眼睛，点开就能预览。判据：
 *  A. 识别站点：`components/workpaper/**`、`composables/**` 里调用识别端点（`/api/…-ocr` / `…/ocr`）的文件
 *     ① 识别请求带位置（rowEv.append / appendRowEvidence / evidence_sheet / evidenceSheet:）或读回附件编号；
 *     ② 有小眼睛：.vue 本身或它渲染的一层子组件里有 RowEvidenceEye / AttachmentEyeButton / ItemAttachment /
 *        AttachmentPreviewDrawer；.ts（composable）看 import 它的 .vue 宿主。
 *  B. 展示站点：`components/workpaper/**` 的 .vue 模板里出现下载调用或附件编号绑定 ⇒ 必须有小眼睛。
 *  C. 小眼睛不能藏在只编辑态的列（`v-if` 与 `!isReadonly` 相与）或上传组件里（复核人看不到 / 点了弹选文件）。
 *  D. 豁免清单 attachmentEyeExemptions.json 只许删：条目文件须存在、须确实违规（否则是失效条目），
 *     带 verify 的条目逐条按实情核对（零挂载 / 宿主未接线 / 识别只在指定函数里 / 无底稿宿主）。
 *  E. 扫描器自检：合成源码里的违规写法必须被抓到；扫描面不得塌缩（识别站点 ≥ 90、展示站点 ≥ 15）。
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
import exemptionsJson from './attachmentEyeExemptions.json'

type Verify =
  | { type: 'zeroMounts'; component: string }
  | { type: 'absent'; file: string; text: string }
  | { type: 'ocrOnlyInFunction'; fn: string }
  | { type: 'noWorkpaperHost' }
interface Exemption {
  file: string
  kind: 'concurrent' | 'spec-c' | 'not-workpaper' | 'no-ui' | 'by-design' | 'dormant'
  owner: string
  reason: string
  verify?: Verify
}
const EXEMPTIONS = exemptionsJson as Exemption[]

/** 相对 src 的 posix 路径 → 原文 */
type Sources = Map<string, string>

const OCR_CALL_RE = /[`'"]\/api\/[^`'"]*?(?:-ocr|\/ocr)[`'"?]/g
const EYE_TAG_RE = /<(RowEvidenceEye|AttachmentEyeButton|ItemAttachment|AttachmentPreviewDrawer)\b/
const POS_RE = /rowEv\.append\(|appendRowEvidence\(|evidence_sheet|evidenceSheet:|\{ sheet: /
/** 读回 / 带上附件编号（识别已在本底稿的附件，或回执编号记进行数据） */
const KEEP_RE = /\battachment_id\b|appendOcrLinkageFields\(/
const DISPLAY_RE = /downloadAttachment\(|download[A-Z]\w*Attachment\(|\battachment_?[Ii]d\b|\battachmentIds\b|\bocrAttachmentId\b/
const IMPORT_VUE_RE = /import\s+(\w+)\s+from\s+['"]([^'"]+\.vue)['"]/g
const ASYNC_VUE_RE = /(\w+)\s*=\s*defineAsyncComponent\(\s*\(\)\s*=>\s*import\(\s*['"]([^'"]+\.vue)['"]/g

// ─── 解析 ─────────────────────────────────────────────────────────────────────

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

function ocrCalls(rel: string, text: string): string[] {
  return (scriptOf(rel, text).match(OCR_CALL_RE) ?? []).filter(
    (c) => !c.includes('/api/attachments/') && !c.includes('knowledge'),
  )
}

function resolveRel(fromRel: string, spec: string): string {
  if (spec.startsWith('@/')) return posix.normalize(spec.slice(2))
  return posix.normalize(posix.join(posix.dirname(fromRel), spec))
}

const kebab = (name: string) => name.replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase()

function rendersTag(tpl: string, name: string): boolean {
  return new RegExp(`<(${name}|${kebab(name)})\\b`).test(tpl)
}

/** .vue 本身或它渲染的一层子组件里有小眼睛 */
function hasEye(rel: string, sources: Sources): boolean {
  const text = sources.get(rel) ?? ''
  const tpl = templateOf(rel, text)
  if (EYE_TAG_RE.test(tpl)) return true
  const script = scriptOf(rel, text)
  for (const re of [IMPORT_VUE_RE, ASYNC_VUE_RE]) {
    for (const m of script.matchAll(re)) {
      const child = resolveRel(rel, m[2])
      const childText = sources.get(child)
      if (childText && EYE_TAG_RE.test(templateOf(child, childText)) && rendersTag(tpl, m[1])) return true
    }
  }
  return false
}

/** import 了该 composable 的 .vue 宿主 */
function hostsOf(rel: string, sources: Sources): string[] {
  const stem = posix.basename(rel).replace(/\.ts$/, '')
  const re = new RegExp(`from\\s+['"][^'"]*/${stem}['"]`)
  return [...sources.keys()].filter((h) => h !== rel && h.endsWith('.vue') && re.test(scriptOf(h, sources.get(h)!)))
}

/** 起始标签结束位置（引号内的 `>` 不算，如 `(f) => x`） */
function tagEnd(tpl: string, from: number): number {
  let quote: string | null = null
  for (let i = from; i < tpl.length; i++) {
    const c = tpl[i]
    if (quote) {
      if (c === quote) quote = null
    } else if (c === '"' || c === "'") {
      quote = c
    } else if (c === '>') {
      return i
    }
  }
  return tpl.length
}

/** 「只编辑态」条件：v-if 里与 !isReadonly / !readonly 相与，或 canOcr / canEdit 这类编辑态开关 */
const EDIT_ONLY_RE = /(^|&&)\s*!\s*(props\.)?(isReadonly|readonly)\s*(&&|$)|\bcan(Ocr|Edit)\b/
/**
 * 判据 C 认的小眼睛：两个小眼睛组件 + 恒带小眼睛的行内附件组件（函证替代程序 / 差异调节，
 * spec attachment-confirmation-evidence-loop），后者被放进只编辑态的列同样让复核人看不到。
 */
const EYE_CARRIERS = new Set(['RowEvidenceEye', 'AttachmentEyeButton', 'AlternativeRowEvidence', 'DiffRowEvidenceCell'])
const VOID_TAGS = new Set(['input', 'br', 'img', 'hr', 'col', 'meta', 'link'])

/**
 * 小眼睛藏起来的位置：放在上传组件里，或某个祖先元素（含自身）的 v-if 是只编辑态条件。
 * v-else / v-else-if 分支不计条件（通常就是只读分支）；同一位置（属性相同）在别处另有可见的小眼睛则放行
 * （如「编辑态输入框旁 / 只读态文本旁」各放一个）。
 */
function hiddenEyes(tpl: string): string[] {
  const eyes: Array<{ key: string; why: string | null }> = []
  const stack: Array<{ name: string; cond: string }> = []
  const re = /<(\/?)([A-Za-z][\w-]*)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(tpl)) !== null) {
    const [, closing, name] = m
    const end = tagEnd(tpl, m.index)
    re.lastIndex = end + 1
    if (closing) {
      while (stack.length && stack.pop()!.name !== name) { /* 跳过未闭合的子元素 */ }
      continue
    }
    const attrs = tpl.slice(m.index, end)
    const vif = /\sv-if="([^"]*)"/.exec(attrs)?.[1] ?? ''
    if (EYE_CARRIERS.has(name)) {
      const inUpload = stack.some((s) => s.name === 'el-upload')
      const cond = [...stack.map((s) => s.cond), vif].find((c) => c && EDIT_ONLY_RE.test(c))
      const why = inUpload
        ? '小眼睛放在上传组件里（点小眼睛会弹出选文件；上传组件只读时不渲染）'
        : cond ? `小眼睛在只编辑态条件 v-if="${cond}" 之下（复核人看不到）` : null
      eyes.push({ key: attrs.replace(/\sv-if="[^"]*"/, '').replace(/\s+/g, ' ').trim(), why })
    }
    if (attrs.trimEnd().endsWith('/') || VOID_TAGS.has(name.toLowerCase())) continue
    stack.push({ name, cond: /\sv-else(-if)?\b/.test(attrs) ? '' : vif })
  }
  const visible = new Set(eyes.filter((e) => !e.why).map((e) => e.key))
  return eyes.filter((e) => e.why && !visible.has(e.key)).map((e) => e.why!)
}

interface Violation { file: string; why: string }

function scan(sources: Sources): { violations: Violation[]; ocrFiles: string[]; displayFiles: string[] } {
  const violations: Violation[] = []
  const ocrFiles: string[] = []
  const displayFiles: string[] = []
  for (const [rel, text] of sources) {
    const inScope = rel.startsWith('components/workpaper/') || rel.startsWith('composables/')
    if (!inScope) continue
    const calls = ocrCalls(rel, text)
    const script = scriptOf(rel, text)
    if (calls.length) {
      ocrFiles.push(rel)
      const placed = POS_RE.test(script) || KEEP_RE.test(script)
      if (!placed) violations.push({ file: rel, why: '识别请求既不带位置也不读回附件编号（附件找不到挂在哪）' })
      if (rel.endsWith('.vue')) {
        if (!hasEye(rel, sources)) violations.push({ file: rel, why: '调用识别端点的页面没有小眼睛' })
      } else if (!hostsOf(rel, sources).some((h) => hasEye(h, sources))) {
        violations.push({ file: rel, why: '识别 composable 的宿主页面都没有小眼睛' })
      }
    }
    if (rel.endsWith('.vue') && rel.startsWith('components/workpaper/')) {
      const tpl = templateOf(rel, text)
      if (DISPLAY_RE.test(tpl)) {
        displayFiles.push(rel)
        if (!hasEye(rel, sources)) violations.push({ file: rel, why: '模板展示附件（下载 / 附件编号）却没有小眼睛' })
      }
      for (const why of hiddenEyes(tpl)) violations.push({ file: rel, why })
    }
  }
  return { violations, ocrFiles, displayFiles }
}

function loadSources(): Sources {
  const map: Sources = new Map()
  for (const abs of walkSourceFiles(FRONTEND_SRC)) {
    if (!/\.(vue|ts)$/.test(abs)) continue
    map.set(toSrcRelative(abs), readSource(abs))
  }
  return map
}

function verifyExemption(ex: Exemption, sources: Sources): string | null {
  const v = ex.verify
  if (!v) return null
  if (v.type === 'zeroMounts') {
    const users = [...sources.entries()]
      .filter(([rel, text]) => rel !== ex.file && rel.endsWith('.vue') && rendersTag(templateOf(rel, text), v.component))
      .map(([rel]) => rel)
    return users.length ? `声称零挂载，但被 ${users.join('、')} 渲染` : null
  }
  if (v.type === 'absent') {
    const text = sources.get(v.file)
    if (text == null) return `核对文件 ${v.file} 不存在`
    return stripJsComments(text).includes(v.text) ? `声称 ${v.file} 未接线，但已出现「${v.text}」` : null
  }
  if (v.type === 'ocrOnlyInFunction') {
    const script = scriptOf(ex.file, sources.get(ex.file) ?? '')
    const start = script.indexOf(`function ${v.fn}(`)
    if (start < 0) return `找不到函数 ${v.fn}`
    const end = script.indexOf('\n}', start)
    const outside = [...script.matchAll(OCR_CALL_RE)].filter((m) => m.index! < start || m.index! > end)
    return outside.length ? `声称识别只在 ${v.fn} 里，但函数外还有 ${outside.length} 处` : null
  }
  if (v.type === 'noWorkpaperHost') {
    const hosts = hostsOf(ex.file, sources).filter((h) => h.startsWith('components/workpaper/') || h.startsWith('views/workpaper'))
    return hosts.length ? `声称不在底稿页上，但被 ${hosts.join('、')} 使用` : null
  }
  return null
}

// ─── 真实源码 ─────────────────────────────────────────────────────────────────

describe('底稿附件小眼睛覆盖', () => {
  const sources = loadSources()
  const { violations, ocrFiles, displayFiles } = scan(sources)
  const exempt = new Set(EXEMPTIONS.map((e) => e.file))

  it('扫描面不塌缩（识别站点 ≥ 90、展示站点 ≥ 15）', () => {
    expect(ocrFiles.length).toBeGreaterThanOrEqual(90)
    expect(displayFiles.length).toBeGreaterThanOrEqual(15)
  })

  it('未豁免的识别 / 展示站点都有小眼睛，且小眼睛不藏在只编辑态位置', () => {
    const open = violations.filter((v) => !exempt.has(v.file)).map((v) => `${v.file}：${v.why}`)
    expect(open, `以下位置缺小眼睛或藏起来了：\n${open.join('\n')}`).toEqual([])
  })

  it('豁免条目：文件存在、确实未接入、核对项与实情一致', () => {
    const problems: string[] = []
    const violating = new Set(violations.map((v) => v.file))
    for (const ex of EXEMPTIONS) {
      if (!existsSync(`${FRONTEND_SRC}/${ex.file}`)) { problems.push(`${ex.file}：文件不存在`); continue }
      if (!violating.has(ex.file)) problems.push(`${ex.file}：已接入，请从豁免清单删除`)
      const bad = verifyExemption(ex, sources)
      if (bad) problems.push(`${ex.file}：${bad}`)
      if (!ex.owner?.trim() || !ex.reason?.trim()) problems.push(`${ex.file}：缺归属或原因`)
    }
    expect(problems, `豁免清单有问题：\n${problems.join('\n')}`).toEqual([])
  })

  it('豁免清单无重复', () => {
    expect(new Set(EXEMPTIONS.map((e) => e.file)).size).toBe(EXEMPTIONS.length)
  })
})

// ─── 扫描器自检（合成源码）────────────────────────────────────────────────────

describe('扫描器自检', () => {
  const OCR = "await http.post(`/api/workpapers/${wpId}/d4/contract-ocr`, fd)"
  const vue = (tpl: string, script: string) => `<template>\n${tpl}\n</template>\n<script setup lang="ts">\n${script}\n</script>\n`
  const run = (entries: Record<string, string>) => scan(new Map(Object.entries(entries))).violations

  it('识别页面没有小眼睛 ⇒ 抓到；有小眼睛且带位置 ⇒ 放行', () => {
    expect(run({ 'components/workpaper/x/A.vue': vue('<el-button>📎</el-button>', `rowEv.append(fd, S, c)\n${OCR}`) })
      .map((v) => v.why)).toEqual(['调用识别端点的页面没有小眼睛'])
    expect(run({ 'components/workpaper/x/A.vue': vue('<RowEvidenceEye :wp-id="w" sheet-key="S" />', `rowEv.append(fd, S, c)\n${OCR}`) }))
      .toEqual([])
  })

  it('识别不带位置也不读回编号 ⇒ 抓到', () => {
    expect(run({ 'components/workpaper/x/A.vue': vue('<RowEvidenceEye :wp-id="w" sheet-key="S" />', OCR) }).map((v) => v.why))
      .toEqual(['识别请求既不带位置也不读回附件编号（附件找不到挂在哪）'])
  })

  it('注释里的识别地址不算调用', () => {
    expect(run({ 'components/workpaper/x/A.vue': vue('<span />', `// ${OCR}`) })).toEqual([])
  })

  it('composable 看宿主：宿主有小眼睛放行，没有抓到', () => {
    const ts = `import http from '@/utils/http'\nexport function useX() { appendRowEvidence(fd, 'S'); ${OCR} }`
    const host = (tpl: string) => vue(tpl, "import { useX } from '../composables/useX'")
    expect(run({ 'components/workpaper/composables/useX.ts': ts, 'components/workpaper/x/H.vue': host('<RowEvidenceEye sheet-key="S" />') }))
      .toEqual([])
    expect(run({ 'components/workpaper/composables/useX.ts': ts, 'components/workpaper/x/H.vue': host('<span />') }).map((v) => v.why))
      .toEqual(['识别 composable 的宿主页面都没有小眼睛'])
  })

  it('子组件里的小眼睛算数（须真的渲染该子组件）', () => {
    const child = vue('<AttachmentEyeButton attachment-id="a" />', '')
    const parent = (tpl: string) => vue(tpl, `import Card from './Card.vue'\nrowEv.append(fd, S)\n${OCR}`)
    expect(run({ 'components/workpaper/x/Card.vue': child, 'components/workpaper/x/P.vue': parent('<Card />') })).toEqual([])
    expect(run({ 'components/workpaper/x/Card.vue': child, 'components/workpaper/x/P.vue': parent('<span />') }).map((v) => v.file))
      .toEqual(['components/workpaper/x/P.vue'])
  })

  it('展示附件编号 / 下载却没有小眼睛 ⇒ 抓到', () => {
    expect(run({ 'components/workpaper/x/D.vue': vue('<a @click="downloadAttachment(row.attachmentId)">下载</a>', '') }).map((v) => v.why))
      .toEqual(['模板展示附件（下载 / 附件编号）却没有小眼睛'])
  })

  it('小眼睛在只编辑态列里 ⇒ 抓到；列条件与 wpId 相或 ⇒ 放行', () => {
    const eye = '<RowEvidenceEye :wp-id="wpId" sheet-key="S" />'
    const hidden = `<el-table-column v-if="wpId && !isReadonly" label="OCR"><template #default="{ row }">${eye}</template></el-table-column>`
    const shown = `<el-table-column v-if="!isReadonly || wpId" label="OCR"><template #default="{ row }">${eye}</template></el-table-column>`
    expect(run({ 'components/workpaper/x/T.vue': vue(hidden, '') }).map((v) => v.why)[0]).toContain('只编辑态条件')
    expect(run({ 'components/workpaper/x/T.vue': vue(shown, '') })).toEqual([])
  })

  it('任意祖先元素只编辑态 ⇒ 抓到；只读分支（v-else）另有同一位置的小眼睛 ⇒ 放行', () => {
    const eye = '<RowEvidenceEye sheet-key="S" :cell-ref="c" />'
    const hidden = `<div v-if="!isReadonly && wpId"><el-upload><el-button>📎</el-button></el-upload>${eye}</div>`
    const paired = `<div v-if="!row.isSubtotal && !isReadonly"><el-input />${eye}</div><span v-else>文本${eye}</span>`
    expect(run({ 'components/workpaper/x/G.vue': vue(hidden, '') }).map((v) => v.why)[0]).toContain('只编辑态条件')
    expect(run({ 'components/workpaper/x/G.vue': vue(paired, '') })).toEqual([])
  })

  it('恒带小眼睛的行内附件组件放进只编辑态列 ⇒ 同样抓到（函证替代程序 / 差异调节）', () => {
    for (const tag of ['AlternativeRowEvidence', 'DiffRowEvidenceCell']) {
      const cell = `<${tag} v-if="row._row_id" :wp-id="wpId" :row-id="row._row_id" :readonly="readonly" />`
      const hidden = `<el-table-column v-if="wpId && evidenceSheet && !readonly" label="附件"><template #default="{ row }">${cell}</template></el-table-column>`
      const shown = `<el-table-column v-if="wpId && evidenceSheet" label="附件"><template #default="{ row }">${cell}</template></el-table-column>`
      expect(run({ 'components/workpaper/x/A.vue': vue(hidden, '') }).map((v) => v.why)[0]).toContain('只编辑态条件')
      expect(run({ 'components/workpaper/x/A.vue': vue(shown, '') })).toEqual([])
    }
  })

  it('小眼睛在上传组件里 ⇒ 抓到；属性里的箭头函数不打断标签解析', () => {
    const inUpload = '<el-upload :before-upload="(f: File) => onOcr(row, f)"><el-button>📎</el-button><RowEvidenceEye sheet-key="S" /></el-upload>'
    const after = '<el-upload :before-upload="(f: File) => onOcr(row, f)"><el-button>📎</el-button></el-upload><RowEvidenceEye sheet-key="S" />'
    expect(run({ 'components/workpaper/x/U.vue': vue(inUpload, '') }).map((v) => v.why)[0]).toContain('上传组件里')
    expect(run({ 'components/workpaper/x/U.vue': vue(after, '') })).toEqual([])
  })
})
