/**
 * H9 租赁负债 — 注册契约测试
 *
 * Spec: .kiro/specs/h9-lease-liabilities/ Task 1.2
 * Validates: Requirements 1.6, 1.7, 1.8
 *
 * 验证 'h9-lease-liabilities' componentType 在三个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（H9/H9A/H9-1~H9-4 共6个映射）
 * 4. RENDERER_DISPATCH（Phase 5 创建后验证）
 */
import { describe, it, expect, beforeAll } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
  getRendererEntry,
} from '../htmlRendererRegistry'

describe('H9 租赁负债 — 注册契约测试', () => {
  describe('htmlRendererRegistry 注册', () => {
    it('h9-lease-liabilities 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get('h9-lease-liabilities')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('h9-lease-liabilities')
      expect(entry?.icon).toBeTruthy()
      expect(entry?.label).toBeTruthy()
      expect(entry?.emits).toContain('save')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 h9-lease-liabilities', () => {
      expect(isHtmlComponentType('h9-lease-liabilities')).toBe(true)
    })

    it('getRendererEntry 返回正确 entry', () => {
      const entry = getRendererEntry('h9-lease-liabilities')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('h9-lease-liabilities')
    })

    it('组件 lazy 加载定义存在', () => {
      const entry = HTML_RENDERER_REGISTRY.get('h9-lease-liabilities')
      expect(entry?.component).toBeDefined()
      // lazy component 是一个函数或对象
      expect(typeof entry?.component === 'function' || typeof entry?.component === 'object').toBe(true)
    })

    it('contextProps 为 standard', () => {
      const entry = HTML_RENDERER_REGISTRY.get('h9-lease-liabilities')
      expect(entry?.contextProps).toBe('standard')
    })
  })

  describe('VALID_COMPONENT_TYPES 契约', () => {
    it('后端 wp_classification_service.py 包含 h9-lease-liabilities', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"h9-lease-liabilities"')
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

    it('H9 映射为 h9-lease-liabilities', () => {
      expect(overrides['H9']).toBe('h9-lease-liabilities')
    })

    it('H9A 映射为 h9-lease-liabilities', () => {
      expect(overrides['H9A']).toBe('h9-lease-liabilities')
    })

    it('H9-1 映射为 h9-lease-liabilities', () => {
      expect(overrides['H9-1']).toBe('h9-lease-liabilities')
    })

    it('H9-2 映射为 h9-lease-liabilities', () => {
      expect(overrides['H9-2']).toBe('h9-lease-liabilities')
    })

    it('H9-3 映射为 h9-lease-liabilities', () => {
      expect(overrides['H9-3']).toBe('h9-lease-liabilities')
    })

    it('H9-4 映射为 h9-lease-liabilities', () => {
      expect(overrides['H9-4']).toBe('h9-lease-liabilities')
    })

    // 完整性校验：核心 6 码必映射；披露前缀等可多于 6
    it('h9-lease-liabilities 至少含核心6码映射', () => {
      const expectedCodes = ['H9', 'H9A', 'H9-1', 'H9-2', 'H9-3', 'H9-4']
      for (const code of expectedCodes) {
        expect(overrides[code]).toBe('h9-lease-liabilities')
      }
      const actualCount = Object.entries(overrides)
        .filter(([, v]) => v === 'h9-lease-liabilities')
        .length
      expect(actualCount).toBeGreaterThanOrEqual(expectedCodes.length)
      // 披露路由也应落到同一组件
      expect(overrides['H9-disc-L'] || overrides['H9-附注披露信息（上市公司）']).toBe('h9-lease-liabilities')
    })
  })

  describe('RENDERER_DISPATCH 契约（Phase 5）', () => {
    it('后端 wp_render_strategies 包存在（Phase 5 创建后完成注册）', () => {
      // RENDERER_DISPATCH 将在 Phase 5 (task 5.1) 注册 h9-lease-liabilities
      // 此测试通过读取后端目录验证模块存在
      const strategiesDir = path.resolve(
        __dirname,
        '../../../../../../backend/app/routers/wp_render_strategies'
      )
      const exists = fs.existsSync(strategiesDir)
      expect(exists).toBe(true)
    })
  })
})
