/**
 * F1 预付账款注册契约测试
 *
 * 验证：
 * 1. htmlRendererRegistry 中 'f1-prepayment' 已注册且配置正确
 * 2. VALID_COMPONENT_TYPES 契约（后端 pytest 验证，此处验证前端侧）
 * 3. wp_code_overrides 契约：F1/F1-1~F1-7/F1-note-* 共 10 个映射
 *
 * **Validates: Requirements 1.5, 1.6, 1.7**
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
  getRendererEntry,
} from '../htmlRendererRegistry'

describe('F1 预付账款 — htmlRendererRegistry 注册契约', () => {
  it('f1-prepayment 已注册且配置正确', () => {
    const entry = HTML_RENDERER_REGISTRY.get('f1-prepayment')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('f1-prepayment')
    expect(entry?.icon).toBeTruthy()
    expect(entry?.label).toBeTruthy()
    expect(entry?.emits).toContain('save')
    expect(entry?.component).toBeDefined()
  })

  it('isHtmlComponentType 识别 f1-prepayment', () => {
    expect(isHtmlComponentType('f1-prepayment')).toBe(true)
  })

  it('getRendererEntry 返回 f1-prepayment 条目', () => {
    const entry = getRendererEntry('f1-prepayment')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('f1-prepayment')
  })

  it('f1-prepayment 组件可被懒加载（defineAsyncComponent）', () => {
    const entry = HTML_RENDERER_REGISTRY.get('f1-prepayment')
    expect(entry?.component).toBeDefined()
    expect(typeof entry?.component === 'function' || typeof entry?.component === 'object').toBe(true)
  })
})

describe('F1 预付账款 — wp_code_overrides 契约', () => {
  const overridesPath = resolve(__dirname, '../../../../../../backend/app/data/wp_code_overrides.json')
  let overrides: Record<string, string>

  try {
    overrides = JSON.parse(readFileSync(overridesPath, 'utf-8'))
  } catch {
    overrides = {}
  }

  const expectedMappings = [
    'F1', 'F1-1', 'F1-2', 'F1-3', 'F1-4', 'F1-5', 'F1-6', 'F1-7',
    'F1-note-listed', 'F1-note-soe',
  ]

  it('wp_code_overrides.json 可读取', () => {
    expect(Object.keys(overrides).length).toBeGreaterThan(0)
  })

  for (const wpCode of expectedMappings) {
    it(`${wpCode} 映射为 'f1-prepayment'`, () => {
      expect(overrides[wpCode]).toBe('f1-prepayment')
    })
  }
})
