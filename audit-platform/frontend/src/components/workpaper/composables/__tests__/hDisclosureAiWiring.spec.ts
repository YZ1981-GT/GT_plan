/**
 * H 循环披露 Tab 的 AI / 复核接线守卫（Property 6 / 7）
 *
 * 三种「按钮可见可点但零网络请求」的形态（平台已各实测过）：
 * 1. **marker stub 空转**：只 `emit('save', 'X-ai-trigger')`（K5/K7 曾中招）；
 * 2. **孤儿事件**：`emit('open-ai', …)` 而宿主未声明处理器（**H8/H9 四个 Tab**，本 spec 修）；
 * 3. **context 传字符串**：`/ai/generate-text` 要 `dict[str,str]` → 422 被 catch 静默吞（K3 曾中招）。
 *
 * 三者 `get_diagnostics` 与 vitest 都查不出，只有浏览器实测才暴露 → 本守卫按源码形态拦。
 *
 * spec: .kiro/specs/h-cycle-legacy-cleanup-and-platform-hygiene/ R2 / R3
 */
import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { resolve } from 'node:path'

import { H_CYCLE_NOTE_AI_SECTIONS } from '../hCycleNoteAiSections'
import { H8_NOTE_AI_SECTIONS, h8NoteAiSectionId } from '../h8NoteAiSections'
import { H9_NOTE_AI_SECTIONS, h9NoteAiSectionId } from '../h9NoteAiSections'

const WP_ROOT = resolve(__dirname, '../..')

/** 剥离注释：守卫注释里通常会写反例，不剥会把说明文字数成真实调用 */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
    .replace(/<!--[\s\S]*?-->/g, '')
}

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name === '__tests__') continue
    const full = resolve(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else out.push(full)
  }
  return out
}

const allFiles = walk(WP_ROOT)

/** H 循环披露 Tab（H3/H7/H10 已自有正确实现，也纳入检查） */
const hDisclosureTabs = allFiles.filter((f) => /[\\/]H\d+TabDisclosure[^\\/]*\.vue$/.test(f))

function read(file: string): string {
  return stripComments(readFileSync(file, 'utf-8'))
}

function baseName(file: string): string {
  return file.split(/[\\/]/).pop() ?? file
}

describe('H 循环披露 AI / 复核接线', () => {
  it('扫到的披露 Tab 数量合理（防路径失效导致断言空转）', () => {
    expect(hDisclosureTabs.length, `未扫到 H*TabDisclosure*.vue（root=${WP_ROOT}）`).toBeGreaterThan(15)
  })

  it('反向自检：stripComments 确实剥掉注释里的反例', () => {
    const fixture = "// emit('open-ai', 'x')\n/* emit('open-review', 'y') */\nconst a = 1\n"
    const stripped = stripComments(fixture)
    expect(fixture).toContain("emit('open-ai'")
    expect(stripped).not.toContain("emit('open-ai'")
    expect(stripped).not.toContain("emit('open-review'")
    expect(stripped).toContain('const a = 1')
  })

  it('Property 7: 禁止 `emit(\'open-ai\'|\'open-review\')` 孤儿事件', () => {
    const bad: string[] = []
    for (const file of hDisclosureTabs) {
      const src = read(file)
      if (/emit\(\s*['"]open-(ai|review)['"]/.test(src)) bad.push(baseName(file))
    }
    expect(
      bad,
      `以下披露 Tab 仍用 emit 打开 AI/复核，但宿主未声明对应处理器 → 死按钮：${bad.join(' / ')}。`
        + '改接 useHCycleDisclosureAi（AI）与 GtReviewTrigger / openReview（复核）',
    ).toHaveLength(0)
  })

  it('禁止 marker stub 空转（只写 `*-ai-trigger` checklist 标记不发请求）', () => {
    const bad: string[] = []
    for (const file of hDisclosureTabs) {
      const src = read(file)
      if (/['"][\w-]*ai-trigger['"]/.test(src)) bad.push(baseName(file))
    }
    expect(bad, `以下 Tab 仍有 ai-trigger marker stub：${bad.join(' / ')}`).toHaveLength(0)
  })

  it('Property 6: AI context 不得是字符串字面量（后端要 dict[str,str]，否则 422）', () => {
    const bad: string[] = []
    for (const file of hDisclosureTabs) {
      const src = read(file)
      // `context: '…'` / `context: \`…\`` 均是错误形态
      if (/context\s*:\s*['"`]/.test(src)) bad.push(baseName(file))
    }
    expect(bad, `以下 Tab 的 AI context 传字符串：${bad.join(' / ')}`).toHaveLength(0)
  })

  it('接入 useHCycleDisclosureAi 的 Tab 必须绑 :ai-loading 与 :disabled', () => {
    const wired = hDisclosureTabs.filter((f) => read(f).includes('useHCycleDisclosureAi'))
    expect(wired.length, '应有 13 个 Tab 接入统一 helper').toBeGreaterThanOrEqual(13)
    const missing: string[] = []
    for (const file of wired) {
      const src = read(file)
      if (!src.includes(':ai-loading=')) missing.push(`${baseName(file)}(缺 :ai-loading)`)
      // WpNoteTextArea 的 disabled 透传给 AI 按钮
      if (!/:disabled="(isReadonly|props\.isReadonly)/.test(src)) {
        missing.push(`${baseName(file)}(缺 :disabled)`)
      }
    }
    expect(missing, missing.join(' / ')).toHaveLength(0)
  })

  it('每个接入 Tab 的 runAi 键都在对应键集常量里声明（防拼错导致回退通用 prompt）', () => {
    const declared = new Set<string>()
    for (const variants of Object.values(H_CYCLE_NOTE_AI_SECTIONS)) {
      for (const entries of Object.values(variants)) {
        for (const key of Object.keys(entries)) declared.add(key)
      }
    }
    for (const entries of Object.values(H8_NOTE_AI_SECTIONS)) {
      for (const key of Object.keys(entries)) declared.add(key)
    }
    for (const entries of Object.values(H9_NOTE_AI_SECTIONS)) {
      for (const key of Object.keys(entries)) declared.add(key)
    }
    expect(declared.size, '键集常量为空').toBeGreaterThan(10)

    const bad: string[] = []
    for (const file of hDisclosureTabs.filter((f) => read(f).includes('useHCycleDisclosureAi'))) {
      const src = read(file)
      for (const m of src.matchAll(/runAi\(\s*'([\w-]+)'\s*\)/g)) {
        if (!declared.has(m[1])) bad.push(`${baseName(file)}::${m[1]}`)
      }
    }
    expect(bad, `以下 runAi 键未在键集常量声明：${bad.join(' / ')}`).toHaveLength(0)
  })

  it('sectionId 构造函数与统一 helper 口径一致', () => {
    // helper 内部为 `${wpCode}-disclosure-${variant}-${key}`
    expect(h8NoteAiSectionId('listed', 'impairment')).toBe('H8-disclosure-listed-impairment')
    expect(h9NoteAiSectionId('soe', 'auditNote')).toBe('H9-disclosure-soe-auditNote')
  })

  it('WpNoteTextArea 本身真的渲染 AI 与复核按钮（防共享件被改空）', () => {
    const src = readFileSync(
      resolve(WP_ROOT, 'shared/disclosure/WpNoteTextArea.vue'),
      'utf-8',
    )
    expect(src).toContain("emit('ai')")
    expect(src).toContain("emit('review')")
    expect(src).toContain(':loading="aiLoading"')
    expect(src).toContain(':disabled="disabled"')
  })

  it('统一 helper 走 useDisclosureNoteAi（真调 review-dialog/ai-generate）', () => {
    const src = readFileSync(resolve(WP_ROOT, 'composables/useHCycleDisclosureAi.ts'), 'utf-8')
    expect(src).toContain('useDisclosureNoteAi')
    const ai = readFileSync(resolve(WP_ROOT, 'composables/useDisclosureNoteAi.ts'), 'utf-8')
    expect(ai).toContain('review-dialog/ai-generate')
    expect(ai).toContain('section_id')
  })

  it('H5 两版不再用字符串签名调 openReviewDialog（平台签名是对象入参）', () => {
    for (const name of ['h5/core/H5TabDisclosureListed.vue', 'h5/core/H5TabDisclosureSoe.vue']) {
      const src = read(resolve(WP_ROOT, name))
      expect(src, `${name} 仍以字符串调 openReviewDialog`).not.toMatch(
        /openReviewDialog\(\s*['"]/,
      )
    }
  })

  it('H5 两版补上文本持久化（原本录入刷新即丢）', () => {
    for (const [name, item] of [
      ['h5/core/H5TabDisclosureListed.vue', 'H5-disc-listed-text'],
      ['h5/core/H5TabDisclosureSoe.vue', 'H5-disc-soe-text'],
    ] as const) {
      const src = read(resolve(WP_ROOT, name))
      expect(src, `${name} 缺持久化 item id`).toContain(item)
      expect(src, `${name} 缺 saveResponse`).toContain('saveResponse')
    }
  })
})
