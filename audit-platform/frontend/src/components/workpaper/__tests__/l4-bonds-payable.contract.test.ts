/**
 * L4 应付债券 — 注册契约测试
 *
 * 验证 'l4-bonds-payable' componentType 在四个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（L4/L4-1~L4-9/L4A 共11个映射）
 * 4. RENDERER_DISPATCH（后端渲染策略）
 *
 * Spec: .kiro/specs/l4-bonds-payable/
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

const COMPONENT_TYPE = 'l4-bonds-payable'

// L4/L4-1~L4-9/L4A 共11个wp_code应映射到l4-bonds-payable
const EXPECTED_WP_CODES = [
  'L4',
  'L4-1',
  'L4-2',
  'L4-3',
  'L4-4',
  'L4-5',
  'L4-6',
  'L4-7',
  'L4-8',
  'L4-9',
  'L4A',
]

describe('L4 应付债券 — 注册契约测试', () => {
  // ═══════════════════════════════════════════════════════════════════════════
  // 1. htmlRendererRegistry 契约
  // ═══════════════════════════════════════════════════════════════════════════

  describe('htmlRendererRegistry 注册', () => {
    it('l4-bonds-payable 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get(COMPONENT_TYPE)
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe(COMPONENT_TYPE)
      expect(entry?.icon).toBe('📜')
      expect(entry?.label).toBe('L4 应付债券')
      expect(entry?.emits).toContain('save')
      expect(entry?.emits).toContain('completed')
      expect(entry?.contextProps).toBe('standard')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 l4-bonds-payable', () => {
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
    it('后端 wp_classification_service.py 包含 l4-bonds-payable', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"l4-bonds-payable"')
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

    it.each(EXPECTED_WP_CODES)('%s 映射为 l4-bonds-payable', (wpCode) => {
      expect(overrides[wpCode]).toBe(COMPONENT_TYPE)
    })

    it('覆盖完整性：共11个映射无遗漏', () => {
      const l4Mappings = Object.entries(overrides).filter(
        ([, v]) => v === COMPONENT_TYPE
      )
      expect(l4Mappings.length).toBe(EXPECTED_WP_CODES.length)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 4. RENDERER_DISPATCH 契约
  // ═══════════════════════════════════════════════════════════════════════════

  describe('RENDERER_DISPATCH 契约', () => {
    it('后端 wp_render_strategies/__init__.py 包含 l4-bonds-payable', () => {
      const initPath = path.resolve(
        __dirname,
        '../../../../../../backend/app/routers/wp_render_strategies/__init__.py'
      )
      const content = fs.readFileSync(initPath, 'utf-8')
      expect(content).toContain('"l4-bonds-payable"')
    })
  })
})
