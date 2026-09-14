/**
 * K 系负债/递延类披露 Tab 的 AI 辅助接线契约（K3/K4/K5/K7 共 8 个 Tab）
 *
 * 背景（2026-07-31 复盘，三类实质缺陷）：
 * - 🔴 **空转 stub**：K5 两版 / K7 两版的 `handleAiGenerate` 只 `emit('save', ...ai-trigger)`
 *   写一个 marker、从不调 AI 端点 → 按钮可见可点、什么都不会发生（无网络请求）。
 * - 🔴 **`context` 传字符串 → 422**：后端 `AiGenerateTextRequest.context` 是
 *   `dict[str, str]`，K3 两版传的是模板字符串 → 必然 422，被 `catch` 静默吞成失败。
 * - 🔴 **prompt 过短无约束**：18~19 字的笼统 prompt 会诱导模型自造披露内容
 *   （平台已有 F2 同款教训）→ 每条必须写明源模板/附注模版口径 + 「不得虚构」。
 *
 * 本守卫**读源码**（正则），因此必须先 `stripComments()`：被守卫文件的注释里就写着
 * 「原实现只 emit('save', ...ai-trigger)」这类说明文字，不剥离会被数成真实调用
 * （J1 接线守卫首版即因此误报 4 例）。
 *
 * spec: .kiro/specs/k-cycle-disclosure-alignment/ Task 8
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const WP_ROOT = resolve(__dirname, '../..')

/** 8 个披露 Tab（K3/K4/K5/K7 × listed/soe） */
const TABS = [
  'k3/core/K3TabDisclosureListed.vue',
  'k3/core/K3TabDisclosureSoe.vue',
  'k4/core/K4TabDisclosureListed.vue',
  'k4/core/K4TabDisclosureSoe.vue',
  'k5/core/K5TabDisclosureListed.vue',
  'k5/core/K5TabDisclosureSoe.vue',
  'k7/core/K7TabDisclosureListed.vue',
  'k7/core/K7TabDisclosureSoe.vue',
] as const

/** 去掉 `//` 行注释与 `/* *\/` 块注释，避免把说明文字当代码统计 */
export function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:'"`\\])\/\/[^\n]*/g, '$1')
}

function readTab(rel: string): string {
  return stripComments(readFileSync(resolve(WP_ROOT, rel), 'utf-8'))
}

const AI_ENDPOINT_RE = /\/ai\/generate-text/
/** marker-only stub：`emit('save', 'X-ai-trigger'` / `...ai-narrative'` */
const MARKER_STUB_RE = /emit\(\s*'save'\s*,\s*'[^']*ai-(?:trigger|narrative)'/
/** `context:` 后紧跟反引号/引号 = 传了字符串（后端要 dict[str,str] → 422） */
const STRING_CONTEXT_RE = /context:\s*[`'"]/

describe('K 系披露 Tab AI 辅助接线', () => {
  it('守卫自检：stripComments 不会把注释里的示例当代码', () => {
    const sample = `
      /* 原实现只 emit('save', 'K5-disclosure-soe-ai-trigger', ...) */
      // context: \`科目:xxx\`
      const x = 1
    `
    const cleaned = stripComments(sample)
    expect(MARKER_STUB_RE.test(cleaned)).toBe(false)
    expect(STRING_CONTEXT_RE.test(cleaned)).toBe(false)
    // 反向：真代码必须被检出
    expect(MARKER_STUB_RE.test("emit('save', 'K5-x-ai-trigger', {})")).toBe(true)
    expect(STRING_CONTEXT_RE.test('context: `科目:xxx`')).toBe(true)
  })

  it.each(TABS)('%s 真调 /ai/generate-text（非 marker stub）', (rel) => {
    const src = readTab(rel)
    expect(AI_ENDPOINT_RE.test(src), '披露 Tab 的 AI 按钮必须真调端点，否则纯空转').toBe(true)
    expect(MARKER_STUB_RE.test(src), "残留 emit('save', ...ai-trigger) 空转 stub").toBe(false)
  })

  it.each(TABS)('%s context 是对象而非字符串（后端要 dict[str,str]，字符串必 422）', (rel) => {
    expect(STRING_CONTEXT_RE.test(readTab(rel))).toBe(false)
  })

  it.each(TABS)('%s 每条 prompt 都写明源模板口径 + 「不得虚构」约束', (rel) => {
    const src = readTab(rel)
    // 一个文件里可能有多条 prompt（整体说明 / 叙述说明 / 逐段说明）
    const promptCount = (src.match(/\bprompt:/g) ?? []).length
    expect(promptCount, '未找到 prompt 字面量（正则失效或改了写法）').toBeGreaterThan(0)
    const constraintCount = (src.match(/不得虚构/g) ?? []).length
    expect(constraintCount, `${promptCount} 条 prompt 但只有 ${constraintCount} 条「不得虚构」约束`)
      .toBeGreaterThanOrEqual(promptCount)
    expect(/源模板|附注模版/.test(src), 'prompt 必须写明源模板 / 附注模版口径').toBe(true)
  })

  it.each(TABS)('%s AI 按钮带 loading 与只读禁用（防重复提交）', (rel) => {
    const src = readTab(rel)
    expect(/aiLoading|isAiGenerating|:loading=/.test(src), 'AI 按钮缺 loading 反馈').toBe(true)
    expect(/:disabled="isReadonly"/.test(src), '只读态未禁用交互按钮').toBe(true)
  })
})
