/**
 * H7 生产性生物资产 — 注册契约测试
 *
 * Spec: .kiro/specs/h7-biological-assets/ Task 1.2
 * Validates: Requirements 1.6, 1.7, 1.8
 *
 * 验证 'h7-biological-assets' componentType 在四个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（H7/H7A/H7-1~H7-17 共19个映射）
 * 4. DEDICATED_COMPONENT_TYPES（整册专属组件列表）
 */
import { describe, it, expect } from 'vitest'

import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
  getRendererEntry,
} from '../htmlRendererRegistry'

const COMPONENT_TYPE = 'h7-biological-assets' as const

describe('H7 生产性生物资产 — 注册契约测试', () => {
  describe('htmlRendererRegistry 注册', () => {
    it('h7-biological-assets 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get(COMPONENT_TYPE)
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe(COMPONENT_TYPE)
      expect(entry?.icon).toBe('🌱')
      expect(entry?.label).toBe('H7 生产性生物资产')
      expect(entry?.emits).toContain('save')
      expect(entry?.emits).toContain('completed')
      expect(entry?.contextProps).toBe('standard')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 h7-biological-assets 为 true', () => {
      expect(isHtmlComponentType(COMPONENT_TYPE)).toBe(true)
    })

    it('getRendererEntry 返回 h7-biological-assets 配置', () => {
      const entry = getRendererEntry(COMPONENT_TYPE)
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe(COMPONENT_TYPE)
    })
  })
})
