/**
 * K6 持有待售 — 注册契约测试
 *
 * Spec: .kiro/specs/k6-held-for-sale/ Task 1.2
 * Validates: Requirements 1.6, 1.7, 1.8
 *
 * 验证 'k6-held-for-sale' componentType 在三个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（K6/K6-1~K6-7/K6A 共9个映射）
 * 4. RENDERER_DISPATCH（Phase 5 task 5.1 注册后生效）
 */
import { describe, it, expect, beforeAll } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
  getRendererEntry,
} from '../htmlRendererRegistry'

const COMPONENT_TYPE = 'k6-held-for-sale'

const K6_WP_CODES = [
  'K6',
  'K6-1',
  'K6-2',
  'K6-3',
  'K6-4',
  'K6-5',
  'K6-6',
  'K6-7',
  'K6A',
] as const

describe('K6 持有待售 — 注册契约测试', () => {
  describe('htmlRendererRegistry 注册', () => {
    it('k6-held-for-sale 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get(COMPONENT_TYPE)
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe(COMPONENT_TYPE)
      expect(entry?.icon).toBe('🏷️')
      expect(entry?.label).toBe('K6 持有待售')
      expect(entry?.emits).toContain('save')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 k6-held-for-sale', () => {
      expect(isHtmlComponentType(COMPONENT_TYPE)).toBe(true)
    })

    it('getRendererEntry 返回正确 entry', () => {
      const entry = getRendererEntry(COMPONENT_TYPE)
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe(COMPONENT_TYPE)
    })

    it('组件 lazy 加载定义存在', () => {
      const entry = HTML_RENDERER_REGISTRY.get(COMPONENT_TYPE)
      expect(entry?.component).toBeDefined()
      expect(typeof entry?.component === 'function' || typeof entry?.component === 'object').toBe(true)
    })

    it('contextProps 配置为 standard', () => {
      const entry = HTML_RENDERER_REGISTRY.get(COMPONENT_TYPE)
      expect(entry?.contextProps).toBe('standard')
    })

    it('emits 包含 navigate-sheet', () => {
      const entry = HTML_RENDERER_REGISTRY.get(COMPONENT_TYPE)
      expect(entry?.emits).toContain('navigate-sheet')
    })
  })

  describe('VALID_COMPONENT_TYPES 契约', () => {
    it('后端 wp_classification_service.py 包含 k6-held-for-sale', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"k6-held-for-sale"')
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

    for (const code of K6_WP_CODES) {
      it(`${code} 映射为 k6-held-for-sale`, () => {
        expect(overrides[code]).toBe(COMPONENT_TYPE)
      })
    }

    it('k6-held-for-sale 共有9个wp_code映射', () => {
      const actualCount = Object.entries(overrides)
        .filter(([, v]) => v === COMPONENT_TYPE)
        .length
      expect(actualCount).toBe(K6_WP_CODES.length)
    })
  })

  describe('RENDERER_DISPATCH 契约（Phase 5）', () => {
    it('后端 wp_render_strategies 包存在（Task 5.1 创建后完成注册）', () => {
      const strategiesDir = path.resolve(
        __dirname,
        '../../../../../../backend/app/routers/wp_render_strategies'
      )
      const exists = fs.existsSync(strategiesDir)
      expect(exists).toBe(true)
    })
  })
})
