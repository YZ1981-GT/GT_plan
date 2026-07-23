/**
 * B23 业务层面控制 — 契约测试 (Task 5.6)
 *
 * 验证:
 * 1. htmlRendererRegistry 含 'b23-process-control' componentType
 * 2. wp_code_overrides.json: B23 → b23-process-control; B23-1~B23-15 + B23-XX-5 → skip
 * 3. B23_CYCLES 恰好 16 条（14 标准 + 2 特殊）
 * 4. 附件入口编码/标签 ≡ B23_CYCLES（Property 3: 同源保证）
 *
 * **Validates: Requirements 2.3, 12.4, 13.1, 13.2**
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
} from '../htmlRendererRegistry'

import {
  B23_CYCLES,
  attachmentEntries,
  type B23CycleDef,
} from '../composables/b23CycleConfig'

// ─── 1. htmlRendererRegistry 含 'b23-process-control' ───

describe('B23 Registry Contract — htmlRendererRegistry (Req 13.1)', () => {
  it('registry 注册了 b23-process-control', () => {
    const entry = HTML_RENDERER_REGISTRY.get('b23-process-control')
    expect(entry).toBeDefined()
    expect(entry!.componentType).toBe('b23-process-control')
  })

  it('isHtmlComponentType 识别 b23-process-control', () => {
    expect(isHtmlComponentType('b23-process-control')).toBe(true)
  })

  it('b23-process-control 有图标和组件', () => {
    const entry = HTML_RENDERER_REGISTRY.get('b23-process-control')!
    expect(entry.icon).toBeTruthy()
    expect(entry.component).toBeDefined()
  })
})

// ─── 2. wp_code_overrides 映射 ───

describe('B23 Registry Contract — wp_code_overrides (Req 13.2)', () => {
  const overridesPath = resolve(
    __dirname,
    '../../../../../../backend/app/data/wp_code_overrides.json',
  )
  let overrides: Record<string, string> = {}

  try {
    overrides = JSON.parse(readFileSync(overridesPath, 'utf-8'))
  } catch {
    // fallback: empty (test will fail naturally)
  }

  it('overrides 文件可读', () => {
    expect(Object.keys(overrides).length).toBeGreaterThan(0)
  })

  it('B23 → b23-process-control', () => {
    expect(overrides['B23']).toBe('b23-process-control')
  })

  const subWpCodes = [
    'B23-1', 'B23-2', 'B23-3', 'B23-4', 'B23-5',
    'B23-6', 'B23-7', 'B23-8', 'B23-9', 'B23-10',
    'B23-11', 'B23-12', 'B23-13', 'B23-14', 'B23-15',
    'B23-XX-5',
  ]

  it.each(subWpCodes)('%s → skip', (code) => {
    expect(overrides[code]).toBe('skip')
  })

  it('B23-* skip 映射恰好 16 条', () => {
    const skipEntries = Object.entries(overrides).filter(
      ([k, v]) => k.startsWith('B23-') && v === 'skip',
    )
    expect(skipEntries.length).toBe(16)
  })
})

// ─── 3. B23_CYCLES 恰好 16 条 ───

describe('B23 Registry Contract — B23_CYCLES 结构 (Req 2.3)', () => {
  it('B23_CYCLES 包含 16 条定义（14 标准 + 2 特殊）', () => {
    expect(B23_CYCLES.length).toBe(16)
  })

  it('14 标准循环 + 2 特殊循环', () => {
    const standard = B23_CYCLES.filter((c) => !c.isSpecial)
    const special = B23_CYCLES.filter((c) => c.isSpecial)
    expect(standard.length).toBe(14)
    expect(special.length).toBe(2)
  })

  it('特殊循环为 B23-15 和 B23-XX-5', () => {
    const specialCodes = B23_CYCLES.filter((c) => c.isSpecial).map((c) => c.wpCode)
    expect(specialCodes).toContain('B23-15')
    expect(specialCodes).toContain('B23-XX-5')
  })

  it('每个循环 code 唯一', () => {
    const codes = B23_CYCLES.map((c) => c.code)
    expect(new Set(codes).size).toBe(16)
  })

  it('每个循环 wpCode 唯一', () => {
    const wpCodes = B23_CYCLES.map((c) => c.wpCode)
    expect(new Set(wpCodes).size).toBe(16)
  })

  it('每个循环有非空 name', () => {
    for (const c of B23_CYCLES) {
      expect(c.name.length).toBeGreaterThan(0)
    }
  })
})

// ─── 4. Property 3: 附件配置 ≡ B23_CYCLES ───

describe('B23 Registry Contract — Property 3: attachment ≡ B23_CYCLES (Req 12.4)', () => {
  const entries = attachmentEntries()

  it('attachmentEntries 数量 = B23_CYCLES 数量', () => {
    expect(entries.length).toBe(B23_CYCLES.length)
  })

  it('附件 wpCode 集合 = B23_CYCLES wpCode 集合（顺序一致）', () => {
    const expected = B23_CYCLES.map((c) => c.wpCode)
    const actual = entries.map((e) => e.wpCode)
    expect(actual).toEqual(expected)
  })

  it('附件 label = B23_CYCLES name（同源保证，无标签错位）', () => {
    for (let i = 0; i < B23_CYCLES.length; i++) {
      expect(entries[i].label).toBe(B23_CYCLES[i].name)
    }
  })

  it('附件 code = B23_CYCLES code', () => {
    for (let i = 0; i < B23_CYCLES.length; i++) {
      expect(entries[i].code).toBe(B23_CYCLES[i].code)
    }
  })

  it('wp_code_overrides skip 集合与 B23_CYCLES.wpCode 集合完全一致', () => {
    const overridesPath = resolve(
      __dirname,
      '../../../../../../backend/app/data/wp_code_overrides.json',
    )
    let overrides: Record<string, string> = {}
    try {
      overrides = JSON.parse(readFileSync(overridesPath, 'utf-8'))
    } catch {
      // empty
    }

    const skipKeys = Object.entries(overrides)
      .filter(([k, v]) => k.startsWith('B23-') && v === 'skip')
      .map(([k]) => k)
      .sort()

    const configWpCodes = B23_CYCLES.map((c) => c.wpCode).slice().sort()
    expect(skipKeys).toEqual(configWpCodes)
  })
})
