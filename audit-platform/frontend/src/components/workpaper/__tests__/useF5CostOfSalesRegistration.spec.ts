/**
 * F5 营业成本 — 注册契约测试
 *
 * 验证 'f5-cost-of-sales' componentType 在三个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（F5A/F5/F5-1~F5-8 共10个映射）
 *
 * **Validates: Requirements 1.3, 1.4, 1.5**
 */
import { describe, it, expect, beforeAll } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
  getRendererEntry,
} from '../htmlRendererRegistry'

describe('F5 营业成本 — 注册契约测试', () => {
  describe('htmlRendererRegistry 注册', () => {
    it('f5-cost-of-sales 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get('f5-cost-of-sales')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('f5-cost-of-sales')
      expect(entry?.icon).toBe('📊')
      expect(entry?.label).toBe('F5 营业成本')
      expect(entry?.emits).toContain('save')
      expect(entry?.emits).toContain('completed')
      expect(entry?.contextProps).toBe('standard')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 f5-cost-of-sales', () => {
      expect(isHtmlComponentType('f5-cost-of-sales')).toBe(true)
    })

    it('getRendererEntry 返回正确 entry', () => {
      const entry = getRendererEntry('f5-cost-of-sales')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('f5-cost-of-sales')
    })
  })

  describe('VALID_COMPONENT_TYPES 契约', () => {
    it('后端 wp_classification_service.py 包含 f5-cost-of-sales', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"f5-cost-of-sales"')
    })
  })

  describe('wp_code_overrides 契约', () => {
    let overrides: Record<string, string>

    beforeAll(() => {
      const overridesPath = path.resolve(
        __dirname,
        '../../../../../../backend/app/data/wp_code_overrides.json'
      )
      overrides = JSON.parse(fs.readFileSync(overridesPath, 'utf-8'))
    })

    it('F5A 映射为 f5-cost-of-sales', () => {
      expect(overrides['F5A']).toBe('f5-cost-of-sales')
    })

    it('F5 映射为 f5-cost-of-sales', () => {
      expect(overrides['F5']).toBe('f5-cost-of-sales')
    })

    it('F5-1 映射为 f5-cost-of-sales', () => {
      expect(overrides['F5-1']).toBe('f5-cost-of-sales')
    })

    it('F5-2 映射为 f5-cost-of-sales', () => {
      expect(overrides['F5-2']).toBe('f5-cost-of-sales')
    })

    it('F5-3 映射为 f5-cost-of-sales', () => {
      expect(overrides['F5-3']).toBe('f5-cost-of-sales')
    })

    it('F5-4 映射为 f5-cost-of-sales', () => {
      expect(overrides['F5-4']).toBe('f5-cost-of-sales')
    })

    it('F5-5 映射为 f5-cost-of-sales', () => {
      expect(overrides['F5-5']).toBe('f5-cost-of-sales')
    })

    it('F5-6 映射为 f5-cost-of-sales', () => {
      expect(overrides['F5-6']).toBe('f5-cost-of-sales')
    })

    it('F5-7 映射为 f5-cost-of-sales', () => {
      expect(overrides['F5-7']).toBe('f5-cost-of-sales')
    })

    it('F5-8 映射为 f5-cost-of-sales', () => {
      expect(overrides['F5-8']).toBe('f5-cost-of-sales')
    })

    it('f5-cost-of-sales 共有10个wp_code映射', () => {
      const expectedCodes = [
        'F5A', 'F5', 'F5-1', 'F5-2', 'F5-3', 'F5-4', 'F5-5', 'F5-6', 'F5-7', 'F5-8',
      ]
      for (const code of expectedCodes) {
        expect(overrides[code]).toBe('f5-cost-of-sales')
      }
      const actualCount = Object.entries(overrides)
        .filter(([, v]) => v === 'f5-cost-of-sales')
        .length
      expect(actualCount).toBe(expectedCodes.length)
    })
  })
})
