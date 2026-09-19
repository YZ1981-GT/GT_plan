/**
 * L5 长期应付款 — 注册契约测试
 *
 * 验证 'l5-long-term-payables' componentType 在四个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（L5/L5-1~L5-7/L5A 共9个映射）
 * 4. RENDERER_DISPATCH（后端渲染策略，Phase 5添加）
 *
 * Spec: .kiro/specs/l5-long-term-payables/
 * Task: 1.2
 *
 * **Validates: Requirements 1.6, 1.7, 1.8**
 */
import { describe, it, expect, beforeAll } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
  getRendererEntry,
} from '../htmlRendererRegistry'

const COMPONENT_TYPE = 'l5-long-term-payables'

// L5/L5-1~L5-7/L5A 共9个wp_code应映射到l5-long-term-payables
const EXPECTED_WP_CODES = [
  'L5',
  'L5-1',
  'L5-2',
  'L5-3',
  'L5-4',
  'L5-5',
  'L5-6',
  'L5-7',
  'L5A',
]

describe('L5 长期应付款 — 注册契约测试', () => {
  // ═══════════════════════════════════════════════════════════════════════════
  // 1. htmlRendererRegistry 契约
  // ═══════════════════════════════════════════════════════════════════════════

  describe('htmlRendererRegistry 注册', () => {
    it('l5-long-term-payables 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get(COMPONENT_TYPE)
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe(COMPONENT_TYPE)
      expect(entry?.icon).toBe('💳')
      expect(entry?.label).toBe('L5 长期应付款')
      expect(entry?.emits).toContain('save')
      expect(entry?.emits).toContain('completed')
      expect(entry?.contextProps).toBe('standard')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 l5-long-term-payables', () => {
      expect(isHtmlComponentType(COMPONENT_TYPE)).toBe(true)
    })

    it('getRendererEntry 返回正确 entry', () => {
      const entry = getRendererEntry(COMPONENT_TYPE)
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe(COMPONENT_TYPE)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 2. VALID_COMPONENT_TYPES 契约
  // ═══════════════════════════════════════════════════════════════════════════

  describe('VALID_COMPONENT_TYPES 契约', () => {
    it('后端 wp_classification_service.py 包含 l5-long-term-payables', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"l5-long-term-payables"')
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 3. wp_code_overrides 契约
  // ═══════════════════════════════════════════════════════════════════════════

  describe('wp_code_overrides 契约', () => {
    let overrides: Record<string, string>

    beforeAll(() => {
      const overridesPath = path.resolve(
        __dirname,
        '../../../../../../backend/app/data/wp_code_overrides.json'
      )
      overrides = JSON.parse(fs.readFileSync(overridesPath, 'utf-8'))
    })

    it.each(EXPECTED_WP_CODES)('%s 映射为 l5-long-term-payables', (wpCode) => {
      expect(overrides[wpCode]).toBe(COMPONENT_TYPE)
    })

    it('覆盖完整性：共9个映射无遗漏', () => {
      const l5Mappings = Object.entries(overrides).filter(
        ([, v]) => v === COMPONENT_TYPE
      )
      expect(l5Mappings.length).toBe(EXPECTED_WP_CODES.length)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 4. RENDERER_DISPATCH 契约
  // ═══════════════════════════════════════════════════════════════════════════

  describe('RENDERER_DISPATCH 契约', () => {
    it('后端 wp_render_strategies/__init__.py 包含 l5-long-term-payables', () => {
      const initPath = path.resolve(
        __dirname,
        '../../../../../../backend/app/routers/wp_render_strategies/__init__.py'
      )
      const content = fs.readFileSync(initPath, 'utf-8')
      expect(content).toContain('"l5-long-term-payables"')
    })
  })
})
