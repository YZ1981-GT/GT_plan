/**
 * F3 应付票据 — 注册契约测试
 *
 * 验证 'f3-notes-payable' componentType 在三个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（F3/F3-1~F3-7/F3A/F3-note-listed/F3-note-soe 共10个映射）
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

describe('F3 应付票据 — 注册契约测试', () => {
  describe('htmlRendererRegistry 注册', () => {
    it('f3-notes-payable 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get('f3-notes-payable')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('f3-notes-payable')
      expect(entry?.icon).toBe('📄')
      expect(entry?.label).toBe('F3 应付票据')
      expect(entry?.emits).toContain('save')
      expect(entry?.emits).toContain('completed')
      expect(entry?.contextProps).toBe('standard')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 f3-notes-payable', () => {
      expect(isHtmlComponentType('f3-notes-payable')).toBe(true)
    })

    it('getRendererEntry 返回正确 entry', () => {
      const entry = getRendererEntry('f3-notes-payable')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('f3-notes-payable')
    })
  })

  describe('VALID_COMPONENT_TYPES 契约', () => {
    it('后端 wp_classification_service.py 包含 f3-notes-payable', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"f3-notes-payable"')
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

    // F3A 程序表
    it('F3A 映射为 f3-notes-payable', () => {
      expect(overrides['F3A']).toBe('f3-notes-payable')
    })

    // F3 主编码
    it('F3 映射为 f3-notes-payable', () => {
      expect(overrides['F3']).toBe('f3-notes-payable')
    })

    // F3-1 审定表
    it('F3-1 映射为 f3-notes-payable', () => {
      expect(overrides['F3-1']).toBe('f3-notes-payable')
    })

    // F3-2 明细表
    it('F3-2 映射为 f3-notes-payable', () => {
      expect(overrides['F3-2']).toBe('f3-notes-payable')
    })

    // F3-3 调整分录
    it('F3-3 映射为 f3-notes-payable', () => {
      expect(overrides['F3-3']).toBe('f3-notes-payable')
    })

    // F3-4 带息票据利息测算表
    it('F3-4 映射为 f3-notes-payable', () => {
      expect(overrides['F3-4']).toBe('f3-notes-payable')
    })

    // F3-5 逾期票据检查
    it('F3-5 映射为 f3-notes-payable', () => {
      expect(overrides['F3-5']).toBe('f3-notes-payable')
    })

    // F3-6 关联方检查表
    it('F3-6 映射为 f3-notes-payable', () => {
      expect(overrides['F3-6']).toBe('f3-notes-payable')
    })

    // F3-7 应付票据检查表
    it('F3-7 映射为 f3-notes-payable', () => {
      expect(overrides['F3-7']).toBe('f3-notes-payable')
    })

    // 附注披露(上市)
    it('F3-note-listed 映射为 f3-notes-payable', () => {
      expect(overrides['F3-note-listed']).toBe('f3-notes-payable')
    })

    // 附注披露(国企)
    it('F3-note-soe 映射为 f3-notes-payable', () => {
      expect(overrides['F3-note-soe']).toBe('f3-notes-payable')
    })

    // 完整性校验：共10个wp_code映射到f3-notes-payable
    it('f3-notes-payable 共有10个wp_code映射', () => {
      const expectedCodes = [
        'F3', 'F3-1', 'F3-2', 'F3-3', 'F3-4', 'F3-5', 'F3-6', 'F3-7',
        'F3A', 'F3-note-listed', 'F3-note-soe',
      ]
      for (const code of expectedCodes) {
        expect(overrides[code]).toBe('f3-notes-payable')
      }
      // 验证映射总数
      const actualCount = Object.entries(overrides)
        .filter(([, v]) => v === 'f3-notes-payable')
        .length
      expect(actualCount).toBe(expectedCodes.length)
    })
  })
})
