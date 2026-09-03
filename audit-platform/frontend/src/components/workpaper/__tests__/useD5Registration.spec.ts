/**
 * D5 应收款项融资 — 注册契约测试
 *
 * 验证'd5-receivables-financing' componentType 在三个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（D5/D5-1/D5-2/D5-3/D5-4 映射）
 */
import { beforeAll, describe, it, expect } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
  getRendererEntry,
} from '../htmlRendererRegistry'

describe('D5 应收款项融资 — 注册契约测试', () => {
  describe('htmlRendererRegistry 注册', () => {
    it('d5-receivables-financing 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get('d5-receivables-financing')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('d5-receivables-financing')
      expect(entry?.icon).toBe('📈')
      expect(entry?.label).toBe('D5 应收款项融资')
      expect(entry?.emits).toContain('save')
      expect(entry?.emits).toContain('completed')
      expect(entry?.emits).toContain('jump-to-section')
      expect(entry?.contextProps).toBe('standard')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 d5-receivables-financing', () => {
      expect(isHtmlComponentType('d5-receivables-financing')).toBe(true)
    })

    it('getRendererEntry 返回正确 entry', () => {
      const entry = getRendererEntry('d5-receivables-financing')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('d5-receivables-financing')
    })
  })

  describe('VALID_COMPONENT_TYPES 契约', () => {
    it('后端 wp_classification_service.py 包含 d5-receivables-financing', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"d5-receivables-financing"')
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

    it('D5 映射为 d5-receivables-financing', () => {
      expect(overrides['D5']).toBe('d5-receivables-financing')
    })

    it('D5-1 映射为 d5-receivables-financing', () => {
      expect(overrides['D5-1']).toBe('d5-receivables-financing')
    })

    it('D5-2 映射为 d5-receivables-financing', () => {
      expect(overrides['D5-2']).toBe('d5-receivables-financing')
    })

    it('D5-3 映射为 d5-receivables-financing', () => {
      expect(overrides['D5-3']).toBe('d5-receivables-financing')
    })

    it('D5-4 映射为 d5-receivables-financing', () => {
      expect(overrides['D5-4']).toBe('d5-receivables-financing')
    })

    it('D5A 映射为 d5-receivables-financing', () => {
      expect(overrides['D5A']).toBe('d5-receivables-financing')
    })
  })
})
