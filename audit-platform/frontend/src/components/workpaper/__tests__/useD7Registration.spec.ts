/**
 * D7 合同负债 — 注册契约测试
 *
 * 验证'd7-contract-liabilities' componentType 在三个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（D7/D7-1~D7-7 共8个映射）
 *
 * Spec: .kiro/specs/d7-contract-liabilities/
 * Task: 1.2
 *
 * **Validates: Requirements 1.5, 1.6, 1.7**
 */
import { describe, it, expect, beforeAll } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
  getRendererEntry,
} from '../htmlRendererRegistry'

describe('D7 合同负债 — 注册契约测试', () => {
  describe('htmlRendererRegistry 注册', () => {
    it('d7-contract-liabilities 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get('d7-contract-liabilities')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('d7-contract-liabilities')
      expect(entry?.icon).toBe('📋')
      expect(entry?.label).toBe('D7 合同负债')
      expect(entry?.emits).toContain('save')
      expect(entry?.emits).toContain('completed')
      expect(entry?.contextProps).toBe('standard')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 d7-contract-liabilities', () => {
      expect(isHtmlComponentType('d7-contract-liabilities')).toBe(true)
    })

    it('getRendererEntry 返回正确 entry', () => {
      const entry = getRendererEntry('d7-contract-liabilities')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('d7-contract-liabilities')
    })
  })

  describe('VALID_COMPONENT_TYPES 契约', () => {
    it('后端 wp_classification_service.py 包含 d7-contract-liabilities', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"d7-contract-liabilities"')
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

    it('D7 映射为 d7-contract-liabilities', () => {
      expect(overrides['D7']).toBe('d7-contract-liabilities')
    })

    it('D7-1 映射为 d7-contract-liabilities', () => {
      expect(overrides['D7-1']).toBe('d7-contract-liabilities')
    })

    it('D7-2 映射为 d7-contract-liabilities', () => {
      expect(overrides['D7-2']).toBe('d7-contract-liabilities')
    })

    it('D7-3 映射为 d7-contract-liabilities', () => {
      expect(overrides['D7-3']).toBe('d7-contract-liabilities')
    })

    it('D7-4 映射为 d7-contract-liabilities', () => {
      expect(overrides['D7-4']).toBe('d7-contract-liabilities')
    })

    it('D7-5 映射为 d7-contract-liabilities', () => {
      expect(overrides['D7-5']).toBe('d7-contract-liabilities')
    })

    it('D7-6 映射为 d7-contract-liabilities', () => {
      expect(overrides['D7-6']).toBe('d7-contract-liabilities')
    })

    it('D7-7 映射为 d7-contract-liabilities', () => {
      expect(overrides['D7-7']).toBe('d7-contract-liabilities')
    })
  })
})
