/**
 * G3 应收股利 — 注册契约测试
 *
 * 验证 'g3-dividend-receivable' componentType 在三个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（G3A/G3/G3-1~G3-5/note/附注/目录 共12个映射）
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

describe('G3 应收股利 — 注册契约测试', () => {
  describe('htmlRendererRegistry 注册', () => {
    it('g3-dividend-receivable 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get('g3-dividend-receivable')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('g3-dividend-receivable')
      expect(entry?.icon).toBe('💰')
      expect(entry?.label).toBe('G3 应收股利')
      expect(entry?.emits).toContain('save')
      expect(entry?.emits).toContain('completed')
      expect(entry?.contextProps).toBe('standard')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 g3-dividend-receivable', () => {
      expect(isHtmlComponentType('g3-dividend-receivable')).toBe(true)
    })

    it('getRendererEntry 返回正确 entry', () => {
      const entry = getRendererEntry('g3-dividend-receivable')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('g3-dividend-receivable')
    })
  })

  describe('VALID_COMPONENT_TYPES 契约', () => {
    it('后端 wp_classification_service.py 包含 g3-dividend-receivable', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"g3-dividend-receivable"')
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

    it('G3A 映射为 g3-dividend-receivable', () => {
      expect(overrides['G3A']).toBe('g3-dividend-receivable')
    })

    it('G3-1 映射为 g3-dividend-receivable', () => {
      expect(overrides['G3-1']).toBe('g3-dividend-receivable')
    })

    it('G3-2 映射为 g3-dividend-receivable', () => {
      expect(overrides['G3-2']).toBe('g3-dividend-receivable')
    })

    it('G3-3 映射为 g3-dividend-receivable', () => {
      expect(overrides['G3-3']).toBe('g3-dividend-receivable')
    })

    it('G3-4 映射为 g3-dividend-receivable', () => {
      expect(overrides['G3-4']).toBe('g3-dividend-receivable')
    })

    it('G3-5 映射为 g3-dividend-receivable', () => {
      expect(overrides['G3-5']).toBe('g3-dividend-receivable')
    })

    it('G3-note-listed 映射为 g3-dividend-receivable', () => {
      expect(overrides['G3-note-listed']).toBe('g3-dividend-receivable')
    })

    it('G3-note-soe 映射为 g3-dividend-receivable', () => {
      expect(overrides['G3-note-soe']).toBe('g3-dividend-receivable')
    })

    it('g3-dividend-receivable 共有12个wp_code映射', () => {
      const expectedCodes = [
        'G3A', 'G3', 'G3-1', 'G3-2', 'G3-3', 'G3-4', 'G3-5',
        'G3-note-listed', 'G3-note-soe',
        'G3-附注披露信息（上市公司）', 'G3-附注披露信息（国企）', 'G3-底稿目录',
      ]
      for (const code of expectedCodes) {
        expect(overrides[code]).toBe('g3-dividend-receivable')
      }
      const actualCount = Object.entries(overrides)
        .filter(([, v]) => v === 'g3-dividend-receivable')
        .length
      expect(actualCount).toBe(12)
    })
  })
})
