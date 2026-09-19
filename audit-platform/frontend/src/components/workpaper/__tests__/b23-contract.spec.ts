/**
 * B23 业务层面控制 — 契约测试（Task 5.6）
 *
 * 验证：
 * 1. htmlRendererRegistry 注册 b23-process-control componentType
 * 2. wp_code_overrides.json B23 → b23-process-control；B23-1~B23-15 + B23-XX-5 → skip
 * 3. Property 3：附件入口编码/标签恒等于 B23_CYCLES 单一配置源（无硬编码偏离）
 *
 * **Validates: Requirements 2.3, 12.4, 13.1, 13.2**
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
  getRendererEntry,
} from '../htmlRendererRegistry'

import {
  B23_CYCLES,
  attachmentEntries,
} from '../composables/b23CycleConfig'

// ---------- 1. htmlRendererRegistry 注册 ----------

describe('B23 契约测试 — htmlRendererRegistry 注册 (Req 13.1)', () => {
  it('b23-process-control 已注册且配置正确', () => {
    const entry = HTML_RENDERER_REGISTRY.get('b23-process-control')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('b23-process-control')
    expect(entry?.icon).toBeTruthy()
    expect(entry?.component).toBeDefined()
  })

  it('isHtmlComponentType 识别 b23-process-control', () => {
    expect(isHtmlComponentType('b23-process-control')).toBe(true)
  })

  it('getRendererEntry 返回 b23-process-control 条目', () => {
    const entry = getRendererEntry('b23-process-control')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('b23-process-control')
  })

  it('b23-process-control 组件可懒加载', () => {
    const entry = HTML_RENDERER_REGISTRY.get('b23-process-control')
    expect(entry?.component).toBeDefined()
    expect(typeof entry?.component === 'function' || typeof entry?.component === 'object').toBe(true)
  })
})

// ---------- 2. wp_code_overrides 映射 ----------

describe('B23 契约测试 — wp_code_overrides 映射 (Req 13.2)', () => {
  const overridesPath = resolve(__dirname, '../../../../../../backend/app/data/wp_code_overrides.json')
  let overrides: Record<string, string>

  try {
    overrides = JSON.parse(readFileSync(overridesPath, 'utf-8'))
  } catch {
    overrides = {}
  }

  it('wp_code_overrides.json 可读取', () => {
    expect(Object.keys(overrides).length).toBeGreaterThan(0)
  })

  it('B23 主底稿映射为 b23-process-control', () => {
    expect(overrides['B23']).toBe('b23-process-control')
  })

  // B23-1 ~ B23-15 全部映射为 skip
  const skipCodes = [
    'B23-1', 'B23-2', 'B23-3', 'B23-4', 'B23-5',
    'B23-6', 'B23-7', 'B23-8', 'B23-9', 'B23-10',
    'B23-11', 'B23-12', 'B23-13', 'B23-14', 'B23-15',
    'B23-XX-5',
  ]

  for (const code of skipCodes) {
    it(`${code} 映射为 skip`, () => {
      expect(overrides[code]).toBe('skip')
    })
  }

  it('skip 映射数量正确（15 + XX-5 = 16 条）', () => {
    const b23SkipEntries = Object.entries(overrides).filter(
      ([k, v]) => k.startsWith('B23-') && v === 'skip'
    )
    expect(b23SkipEntries.length).toBe(16)
  })
})

// ---------- 3. Property 3：附件配置 ≡ B23_CYCLES ----------

describe('B23 契约测试 — Property 3：附件配置 ≡ B23_CYCLES (Req 2.3, 12.4)', () => {
  const entries = attachmentEntries()
  const cycleWpCodes = B23_CYCLES.map((c) => c.wpCode)
  const cycleNames = B23_CYCLES.map((c) => c.name)

  it('B23_CYCLES 包含 16 个循环定义（14 + B23-15 + B23-XX-5）', () => {
    expect(B23_CYCLES.length).toBe(16)
  })

  it('attachmentEntries 数量与 B23_CYCLES 完全一致', () => {
    expect(entries.length).toBe(B23_CYCLES.length)
  })

  it('附件入口 wpCode 集合与 B23_CYCLES.wpCode 完全一致（顺序相同）', () => {
    const entryWpCodes = entries.map((e) => e.wpCode)
    expect(entryWpCodes).toEqual(cycleWpCodes)
  })

  it('附件入口 label 集合与 B23_CYCLES.name 完全一致（顺序相同）', () => {
    const entryLabels = entries.map((e) => e.label)
    expect(entryLabels).toEqual(cycleNames)
  })

  it('附件入口覆盖 B23-1 ~ B23-15 + B23-XX-5 全部编码', () => {
    const expectedWpCodes = [
      'B23-1', 'B23-2', 'B23-3', 'B23-4', 'B23-5',
      'B23-6', 'B23-7', 'B23-8', 'B23-9', 'B23-10',
      'B23-11', 'B23-12', 'B23-13', 'B23-14', 'B23-15',
      'B23-XX-5',
    ]
    const entryWpCodes = entries.map((e) => e.wpCode)
    for (const code of expectedWpCodes) {
      expect(entryWpCodes).toContain(code)
    }
  })

  it('无硬编码偏离：每个 attachmentEntry 的 label 与其循环配置的 name 完全一致', () => {
    for (let i = 0; i < B23_CYCLES.length; i++) {
      const cycle = B23_CYCLES[i]
      const entry = entries[i]
      expect(entry.wpCode).toBe(cycle.wpCode)
      expect(entry.label).toBe(cycle.name)
      expect(entry.code).toBe(cycle.code)
    }
  })

  it('B23_CYCLES 各 wpCode 唯一（无重复）', () => {
    const wpCodeSet = new Set(cycleWpCodes)
    expect(wpCodeSet.size).toBe(B23_CYCLES.length)
  })

  it('B23_CYCLES 各 code 唯一（无重复）', () => {
    const codeSet = new Set(B23_CYCLES.map((c) => c.code))
    expect(codeSet.size).toBe(B23_CYCLES.length)
  })

  it('wp_code_overrides skip 集合与 B23_CYCLES.wpCode 集合完全一致', () => {
    const overridesPath = resolve(__dirname, '../../../../../../backend/app/data/wp_code_overrides.json')
    let overrides: Record<string, string> = {}
    try {
      overrides = JSON.parse(readFileSync(overridesPath, 'utf-8'))
    } catch {
      // fallback empty
    }
    const b23SkipKeys = Object.entries(overrides)
      .filter(([k, v]) => k.startsWith('B23-') && v === 'skip')
      .map(([k]) => k)
      .sort()

    const configWpCodes = [...cycleWpCodes].sort()

    expect(b23SkipKeys).toEqual(configWpCodes)
  })
})
