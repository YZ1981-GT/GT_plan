/**
 * F2 披露 Tab 的 AI 辅助 / 复核 chip 接线契约
 *
 * Spec: .kiro/specs/f2-inventory-disclosure-template-alignment/ Task 13.5
 *
 * 采用源码断言范式（同 g8~g14ReviewFixes.spec.ts）：两个披露 Tab 依赖 api / store /
 * router / SSE，重型挂载成本高且脆弱，而本任务要守的是「接线是否存在且自洽」，
 * 源码级断言足够且不会假绿。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const CORE = resolve(__dirname, '../f2/core')
const COMPOSABLES = resolve(__dirname, '../composables')

const listed = readFileSync(resolve(CORE, 'F2TabDisclosureListed.vue'), 'utf8')
const soe = readFileSync(resolve(CORE, 'F2TabDisclosureSoe.vue'), 'utf8')
const aiComposable = readFileSync(resolve(COMPOSABLES, 'useF2AiGenerate.ts'), 'utf8')

/** 从 useF2AiGenerate.ts 的 F2AiSection 联合类型提取全部合法 section */
function declaredSections(): Set<string> {
  const start = aiComposable.indexOf('export type F2AiSection')
  expect(start).toBeGreaterThan(-1)
  const end = aiComposable.indexOf('export function useF2AiGenerate', start)
  expect(end).toBeGreaterThan(start)
  const block = aiComposable.slice(start, end)
  const out = new Set<string>()
  for (const m of block.matchAll(/\|\s*'([a-z0-9-]+)'/g)) out.add(m[1])
  return out
}

/** 从 SFC 模板提取全部 runAi('x') 调用的 section */
function invokedSections(src: string): string[] {
  return [...src.matchAll(/runAi\('([a-z0-9-]+)'\)/g)].map((m) => m[1])
}

/** 从 SFC 的 AI_TARGETS 字面量提取已映射的 section 键 */
function mappedTargets(src: string): Set<string> {
  const start = src.indexOf('const AI_TARGETS')
  expect(start).toBeGreaterThan(-1)
  const end = src.indexOf('async function runAi', start)
  expect(end).toBeGreaterThan(start)
  const block = src.slice(start, end)
  const out = new Set<string>()
  for (const m of block.matchAll(/'([a-z0-9-]+)'\s*:/g)) out.add(m[1])
  return out
}

describe('F2 披露 Tab —— AI 辅助接线', () => {
  const declared = declaredSections()

  it.each([
    ['上市', listed, 6, 'listed-note-'],
    ['国企', soe, 5, 'soe-note'],
  ])('%s Tab 每个文本域都有 AI 按钮', (_label, src, minCount, prefix) => {
    expect(src).toContain("from '../../composables/useF2AiGenerate'")
    expect(src).toContain('useF2AiGenerate(wpIdRef)')

    const invoked = invokedSections(src)
    expect(invoked.length).toBeGreaterThanOrEqual(minCount)
    expect(new Set(invoked).size).toBe(invoked.length) // 无重复绑定
    for (const s of invoked) expect(s.startsWith(prefix)).toBe(true)

    // 按钮数量与 runAi 调用数量一致（每个 AI 按钮都真的接了 handler）
    const btnCount = (src.match(/class="ai-btn"/g) ?? []).length
    expect(btnCount).toBe(invoked.length)
  })

  it.each([
    ['上市', listed],
    ['国企', soe],
  ])('%s Tab 的 runAi section 全部在 F2AiSection 中声明', (_label, src) => {
    for (const s of invokedSections(src)) expect(declared.has(s)).toBe(true)
  })

  it.each([
    ['上市', listed],
    ['国企', soe],
  ])('%s Tab 的 runAi section 全部有 AI_TARGETS 映射', (_label, src) => {
    const mapped = mappedTargets(src)
    for (const s of invokedSections(src)) expect(mapped.has(s)).toBe(true)
  })

  it.each([
    ['上市', listed, 'listed-note-category'],
    ['国企', soe, 'soe-note-category'],
  ])('%s Tab 的 AI 按钮带 loading 与当前 section 绑定', (_label, src, sample) => {
    expect(src).toContain(`aiActiveSection === '${sample}'`)
    expect(src).toContain(':disabled="isReadonly || !aiAvailable"')
  })

  it('AI 按钮右对齐（UI 铁律：AI + 复核按钮右对齐在 section 标题同行）', () => {
    expect(listed).toContain('.ai-btn { margin-left: auto; }')
    expect(soe).toContain('.ai-btn { margin-left: auto; }')
  })
})

describe('F2 披露 Tab —— 复核 chip 接线', () => {
  it.each([
    ['上市', listed, 'F2-note-listed'],
    ['国企', soe, 'F2-note-soe'],
  ])('%s Tab 挂载 F2ReviewChip 且 section-id 为 %s', (_label, src, sectionId) => {
    expect(src).toContain("import F2ReviewChip from '../shared/F2ReviewChip.vue'")
    expect(src).toContain(`<F2ReviewChip section-id="${sectionId}" />`)
  })
})

describe('F2 披露 Tab —— 多区块导入导出接线', () => {
  it.each([
    ['上市', listed, 'F2-note-listed'],
    ['国企', soe, 'F2-note-soe'],
  ])('%s Tab 挂载 CycleImportExportDropdown 且 sheet 为 %s', (_label, src, sheet) => {
    expect(src).toContain("import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'")
    expect(src).toContain('<CycleImportExportDropdown')
    expect(src).toContain(`sheet="${sheet}"`)
    expect(src).toContain('api-prefix="f2"')
    // 只读时禁用，避免只读角色写库
    expect(src).toMatch(/<CycleImportExportDropdown[\s\S]{0,240}:disabled="isReadonly"/)
  })

  it.each([
    ['上市', listed],
    ['国企', soe],
  ])('%s Tab 导入后重载 allResponses（否则界面停留在旧值）', (_label, src) => {
    expect(src).toContain("inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)")
    expect(src).toMatch(/async function onImported\(\): Promise<void> \{\s*await reloadWorkpaperData\?\.\(\)/)
    expect(src).toContain('@imported="onImported"')
  })

  it.each([
    ['上市', listed],
    ['国企', soe],
  ])('%s Tab 不再残留 Task 13.4 的未实现 TODO', (_label, src) => {
    expect(src).not.toContain('Task 13.4')
    expect(src).not.toContain('导入导出待后端支持')
  })
})
