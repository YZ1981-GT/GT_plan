/**
 * D6 合同资产 — 注册契约测试
 *
 * 验证'd6-contract-assets' componentType 在三个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（D6/D6-1~D6-9 共10个映射）
 */
import { describe, it, expect, beforeAll } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
  getRendererEntry,
} from '../htmlRendererRegistry'

describe('D6 合同资产 — 注册契约测试', () => {
  describe('htmlRendererRegistry 注册', () => {
    it('d6-contract-assets 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get('d6-contract-assets')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('d6-contract-assets')
      expect(entry?.icon).toBe('📋')
      expect(entry?.label).toBe('D6 合同资产')
      expect(entry?.emits).toContain('save')
      expect(entry?.emits).toContain('completed')
      expect(entry?.contextProps).toBe('standard')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 d6-contract-assets', () => {
      expect(isHtmlComponentType('d6-contract-assets')).toBe(true)
    })

    it('getRendererEntry 返回正确 entry', () => {
      const entry = getRendererEntry('d6-contract-assets')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('d6-contract-assets')
    })
  })

  describe('VALID_COMPONENT_TYPES 契约', () => {
    it('后端 wp_classification_service.py 包含 d6-contract-assets', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"d6-contract-assets"')
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

    it('D6 映射为 d6-contract-assets', () => {
      expect(overrides['D6']).toBe('d6-contract-assets')
    })

    it('D6-1 映射为 d6-contract-assets', () => {
      expect(overrides['D6-1']).toBe('d6-contract-assets')
    })

    it('D6-2 映射为 d6-contract-assets', () => {
      expect(overrides['D6-2']).toBe('d6-contract-assets')
    })

    it('D6-3 映射为 d6-contract-assets', () => {
      expect(overrides['D6-3']).toBe('d6-contract-assets')
    })

    it('D6-4 映射为 d6-contract-assets', () => {
      expect(overrides['D6-4']).toBe('d6-contract-assets')
    })

    it('D6-5 映射为 d6-contract-assets', () => {
      expect(overrides['D6-5']).toBe('d6-contract-assets')
    })

    it('D6-6 映射为 d6-contract-assets', () => {
      expect(overrides['D6-6']).toBe('d6-contract-assets')
    })

    it('D6-7 映射为 d6-contract-assets', () => {
      expect(overrides['D6-7']).toBe('d6-contract-assets')
    })

    it('D6-8 映射为 d6-contract-assets', () => {
      expect(overrides['D6-8']).toBe('d6-contract-assets')
    })

    it('D6-9 映射为 d6-contract-assets', () => {
      expect(overrides['D6-9']).toBe('d6-contract-assets')
    })
  })
})
