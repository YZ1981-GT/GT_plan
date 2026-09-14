/**
 * N2 应交税费 — 注册契约测试
 *
 * 验证 'n2-taxes-payable' componentType 在四个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（N2/N2-1~N2-11/N2A 共13个映射）
 * 4. RENDERER_DISPATCH（后端渲染策略）
 *
 * Spec: .kiro/specs/n2-taxes-payable/
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

const COMPONENT_TYPE = 'n2-taxes-payable'

// N2/N2-1~N2-11/N2A 共13个wp_code应映射到n2-taxes-payable
const EXPECTED_WP_CODES = [
  'N2',
  'N2-1',
  'N2-2',
  'N2-3',
  'N2-4',
  'N2-5',
  'N2-6',
  'N2-7',
  'N2-8',
  'N2-9',
  'N2-10',
  'N2-11',
  'N2A',
]

describe('N2 应交税费 — 注册契约测试', () => {
  // ═══════════════════════════════════════════════════════════════════════════
  // 1. htmlRendererRegistry 契约
  // ═══════════════════════════════════════════════════════════════════════════

  describe('htmlRendererRegistry 注册', () => {
    it('n2-taxes-payable 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get(COMPONENT_TYPE)
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe(COMPONENT_TYPE)
      expect(entry?.icon).toBe('🧾')
      expect(entry?.label).toBe('N2 应交税费')
      expect(entry?.emits).toContain('save')
      expect(entry?.emits).toContain('completed')
      expect(entry?.contextProps).toBe('standard')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 n2-taxes-payable', () => {
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
    it('后端 wp_classification_service.py 包含 n2-taxes-payable', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"n2-taxes-payable"')
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

    it.each(EXPECTED_WP_CODES)('%s 映射为 n2-taxes-payable', (wpCode) => {
      expect(overrides[wpCode]).toBe(COMPONENT_TYPE)
    })

    it('覆盖完整性：共13个映射无遗漏', () => {
      const n2Mappings = Object.entries(overrides).filter(
        ([, v]) => v === COMPONENT_TYPE
      )
      expect(n2Mappings.length).toBe(EXPECTED_WP_CODES.length)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 4. RENDERER_DISPATCH 契约
  // ═══════════════════════════════════════════════════════════════════════════

  describe('RENDERER_DISPATCH 契约', () => {
    it('后端 wp_render_strategies/__init__.py 包含 n2-taxes-payable', () => {
      const initPath = path.resolve(
        __dirname,
        '../../../../../../backend/app/routers/wp_render_strategies/__init__.py'
      )
      const content = fs.readFileSync(initPath, 'utf-8')
      expect(content).toContain('"n2-taxes-payable"')
    })
  })
})
