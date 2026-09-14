/**
 * L1 短期借款 — 注册契约测试
 *
 * 验证'l1-short-term-loans' componentType 在三个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（L1/L1-1~L1-9/L1A 共11个映射）
 * 4. RENDERER_DISPATCH（Phase 5 后端渲染策略）— TODO: Phase 5 完成后取消跳过
 *
 * Spec: .kiro/specs/l1-short-term-loans/
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

const COMPONENT_TYPE = 'l1-short-term-loans'

// L1/L1-1~L1-9/L1A 共11个wp_code应映射到l1-short-term-loans
const EXPECTED_WP_CODES = [
  'L1',
  'L1-1',
  'L1-2',
  'L1-3',
  'L1-4',
  'L1-5',
  'L1-6',
  'L1-7',
  'L1-8',
  'L1-9',
  'L1A',
]

describe('L1 短期借款 — 注册契约测试', () => {
  // ═══════════════════════════════════════════════════════════════════════════
  // 1. htmlRendererRegistry 契约
  // ═══════════════════════════════════════════════════════════════════════════

  describe('htmlRendererRegistry 注册', () => {
    it('l1-short-term-loans 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get(COMPONENT_TYPE)
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe(COMPONENT_TYPE)
      expect(entry?.icon).toBe('🏦')
      expect(entry?.label).toBe('L1 短期借款')
      expect(entry?.emits).toContain('save')
      expect(entry?.emits).toContain('completed')
      expect(entry?.contextProps).toBe('standard')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 l1-short-term-loans', () => {
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
    it('后端 wp_classification_service.py 包含 l1-short-term-loans', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"l1-short-term-loans"')
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

    it.each(EXPECTED_WP_CODES)('%s 映射为 l1-short-term-loans', (wpCode) => {
      expect(overrides[wpCode]).toBe(COMPONENT_TYPE)
    })

    it('覆盖完整性：共11个映射无遗漏', () => {
      const l1Mappings = Object.entries(overrides).filter(
        ([, v]) => v === COMPONENT_TYPE
      )
      expect(l1Mappings.length).toBe(EXPECTED_WP_CODES.length)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 4. RENDERER_DISPATCH 契约（TODO: Phase 5 完成后启用）
  // ═══════════════════════════════════════════════════════════════════════════

  describe('RENDERER_DISPATCH 契约', () => {
    it.todo(
      'l1-short-term-loans 已注册于 RENDERER_DISPATCH — Phase 5 后端渲染策略完成后启用'
    )
  })
})
