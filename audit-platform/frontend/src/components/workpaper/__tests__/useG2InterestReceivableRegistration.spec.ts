/**
 * G2 应收利息 — 注册契约测试
 *
 * 验证 'g2-interest-receivable' componentType 在三个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（G2A/G2-1~G2-8/G2-note-listed/G2-note-soe 共11个映射）
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

describe('G2 应收利息 — 注册契约测试', () => {
  describe('htmlRendererRegistry 注册', () => {
    it('g2-interest-receivable 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get('g2-interest-receivable')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('g2-interest-receivable')
      expect(entry?.icon).toBe('💰')
      expect(entry?.label).toBe('G2 应收利息')
      expect(entry?.emits).toContain('save')
      expect(entry?.emits).toContain('completed')
      expect(entry?.contextProps).toBe('standard')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 g2-interest-receivable', () => {
      expect(isHtmlComponentType('g2-interest-receivable')).toBe(true)
    })

    it('getRendererEntry 返回正确 entry', () => {
      const entry = getRendererEntry('g2-interest-receivable')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('g2-interest-receivable')
    })
  })

  describe('VALID_COMPONENT_TYPES 契约', () => {
    it('后端 wp_classification_service.py 包含 g2-interest-receivable', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"g2-interest-receivable"')
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

    it('G2A 映射为 g2-interest-receivable', () => {
      expect(overrides['G2A']).toBe('g2-interest-receivable')
    })

    it('G2-1 映射为 g2-interest-receivable', () => {
      expect(overrides['G2-1']).toBe('g2-interest-receivable')
    })

    it('G2-2 映射为 g2-interest-receivable', () => {
      expect(overrides['G2-2']).toBe('g2-interest-receivable')
    })

    it('G2-3 映射为 g2-interest-receivable', () => {
      expect(overrides['G2-3']).toBe('g2-interest-receivable')
    })

    it('G2-4 映射为 g2-interest-receivable', () => {
      expect(overrides['G2-4']).toBe('g2-interest-receivable')
    })

    it('G2-5 映射为 g2-interest-receivable', () => {
      expect(overrides['G2-5']).toBe('g2-interest-receivable')
    })

    it('G2-6 映射为 g2-interest-receivable', () => {
      expect(overrides['G2-6']).toBe('g2-interest-receivable')
    })

    it('G2-7 映射为 g2-interest-receivable', () => {
      expect(overrides['G2-7']).toBe('g2-interest-receivable')
    })

    it('G2-8 映射为 g2-interest-receivable', () => {
      expect(overrides['G2-8']).toBe('g2-interest-receivable')
    })

    it('G2-note-listed 映射为 g2-interest-receivable', () => {
      expect(overrides['G2-note-listed']).toBe('g2-interest-receivable')
    })

    it('G2-note-soe 映射为 g2-interest-receivable', () => {
      expect(overrides['G2-note-soe']).toBe('g2-interest-receivable')
    })

    it('g2-interest-receivable 至少有11个wp_code映射', () => {
      const expectedCodes = [
        'G2A', 'G2-1', 'G2-2', 'G2-3', 'G2-4',
        'G2-5', 'G2-6', 'G2-7', 'G2-8',
        'G2-note-listed', 'G2-note-soe',
      ]
      for (const code of expectedCodes) {
        expect(overrides[code]).toBe('g2-interest-receivable')
      }
      const actualCount = Object.entries(overrides)
        .filter(([, v]) => v === 'g2-interest-receivable')
        .length
      expect(actualCount).toBeGreaterThanOrEqual(expectedCodes.length)
    })
  })
})
