/**
 * K5 预计负债 — 注册契约测试
 *
 * Spec: .kiro/specs/k5-provisions/ Task 1.2
 * Validates: Requirements 1.6, 1.7, 1.8
 *
 * 验证 'k5-provisions' componentType 在三个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（K5/K5-1~K5-7/K5A 共9个映射）
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

const COMPONENT_TYPE = 'k5-provisions'

const K5_WP_CODES = [
  'K5',
  'K5-1',
  'K5-2',
  'K5-3',
  'K5-4',
  'K5-5',
  'K5-6',
  'K5-7',
  'K5A',
] as const

describe('K5 预计负债 — 注册契约测试', () => {
  describe('htmlRendererRegistry 注册', () => {
    it('k5-provisions 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get(COMPONENT_TYPE)
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe(COMPONENT_TYPE)
      expect(entry?.icon).toBe('⚖️')
      expect(entry?.label).toBe('K5 预计负债')
      expect(entry?.emits).toContain('save')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 k5-provisions', () => {
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
    it('后端 wp_classification_service.py 包含 k5-provisions', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"k5-provisions"')
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

    for (const code of K5_WP_CODES) {
      it(`${code} 映射为 k5-provisions`, () => {
        expect(overrides[code]).toBe(COMPONENT_TYPE)
      })
    }

    it('k5-provisions 共有9个wp_code映射', () => {
      const actualCount = Object.entries(overrides)
        .filter(([, v]) => v === COMPONENT_TYPE)
        .length
      expect(actualCount).toBe(K5_WP_CODES.length)
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
