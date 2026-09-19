/**
 * M10 其他权益工具 — 注册契约测试
 *
 * 验证 'm10-other-equity-instruments' componentType 在四个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（M10/M10-1~M10-5/M10A 共7个映射）
 * 4. RENDERER_DISPATCH（后端渲染策略，Phase 5添加）
 *
 * Spec: .kiro/specs/m10-other-equity-instruments/
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

const COMPONENT_TYPE = 'm10-other-equity-instruments'

// M10/M10-1~M10-5/M10A 共7个wp_code应映射到m10-other-equity-instruments
const EXPECTED_WP_CODES = [
  'M10',
  'M10-1',
  'M10-2',
  'M10-3',
  'M10-4',
  'M10-5',
  'M10A',
]

describe('M10 其他权益工具 — 注册契约测试', () => {
  // ═══════════════════════════════════════════════════════════════════════════
  // 1. htmlRendererRegistry 契约
  // ═══════════════════════════════════════════════════════════════════════════

  describe('htmlRendererRegistry 注册', () => {
    it('m10-other-equity-instruments 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get(COMPONENT_TYPE)
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe(COMPONENT_TYPE)
      expect(entry?.icon).toBe('📜')
      expect(entry?.label).toBe('M10 其他权益工具')
      expect(entry?.emits).toContain('save')
      expect(entry?.emits).toContain('completed')
      expect(entry?.contextProps).toBe('standard')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 m10-other-equity-instruments', () => {
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
    it('后端 wp_classification_service.py 包含 m10-other-equity-instruments', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"m10-other-equity-instruments"')
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

    it.each(EXPECTED_WP_CODES)('%s 映射为 m10-other-equity-instruments', (wpCode) => {
      expect(overrides[wpCode]).toBe(COMPONENT_TYPE)
    })

    it('覆盖完整性：共7个映射无遗漏', () => {
      const m10Mappings = Object.entries(overrides).filter(
        ([, v]) => v === COMPONENT_TYPE
      )
      expect(m10Mappings.length).toBe(EXPECTED_WP_CODES.length)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 4. RENDERER_DISPATCH 契约（Phase 5 task 5.1 完成后生效）
  // ═══════════════════════════════════════════════════════════════════════════

  describe('RENDERER_DISPATCH 契约', () => {
    it.todo('后端 wp_render_strategies/__init__.py 包含 m10-other-equity-instruments（Phase 5添加）')
  })
})
