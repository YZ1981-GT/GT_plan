/**
 * F4 应付账款 — 注册契约测试
 *
 * 验证 'f4-accounts-payable' componentType 在三个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（F4A/F4-1~F4-9/F4-note-listed/F4-note-soe 共12个映射）
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

describe('F4 应付账款 — 注册契约测试', () => {
  describe('htmlRendererRegistry 注册', () => {
    it('f4-accounts-payable 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get('f4-accounts-payable')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('f4-accounts-payable')
      expect(entry?.icon).toBe('📋')
      expect(entry?.label).toBe('F4 应付账款')
      expect(entry?.emits).toContain('save')
      expect(entry?.emits).toContain('completed')
      expect(entry?.contextProps).toBe('standard')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 f4-accounts-payable', () => {
      expect(isHtmlComponentType('f4-accounts-payable')).toBe(true)
    })

    it('getRendererEntry 返回正确 entry', () => {
      const entry = getRendererEntry('f4-accounts-payable')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('f4-accounts-payable')
    })
  })

  describe('VALID_COMPONENT_TYPES 契约', () => {
    it('后端 wp_classification_service.py 包含 f4-accounts-payable', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"f4-accounts-payable"')
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

    // F4A 程序表
    it('F4A 映射为 f4-accounts-payable', () => {
      expect(overrides['F4A']).toBe('f4-accounts-payable')
    })

    // F4-1 审定表
    it('F4-1 映射为 f4-accounts-payable', () => {
      expect(overrides['F4-1']).toBe('f4-accounts-payable')
    })

    // F4-2 明细表
    it('F4-2 映射为 f4-accounts-payable', () => {
      expect(overrides['F4-2']).toBe('f4-accounts-payable')
    })

    // F4-3 调整分录
    it('F4-3 映射为 f4-accounts-payable', () => {
      expect(overrides['F4-3']).toBe('f4-accounts-payable')
    })

    // F4-4 实质性分析
    it('F4-4 映射为 f4-accounts-payable', () => {
      expect(overrides['F4-4']).toBe('f4-accounts-payable')
    })

    // F4-5 长期挂账检查
    it('F4-5 映射为 f4-accounts-payable', () => {
      expect(overrides['F4-5']).toBe('f4-accounts-payable')
    })

    // F4-6 关联方检查表
    it('F4-6 映射为 f4-accounts-payable', () => {
      expect(overrides['F4-6']).toBe('f4-accounts-payable')
    })

    // F4-7 未入账检查表
    it('F4-7 映射为 f4-accounts-payable', () => {
      expect(overrides['F4-7']).toBe('f4-accounts-payable')
    })

    // F4-8 应付账款检查表
    it('F4-8 映射为 f4-accounts-payable', () => {
      expect(overrides['F4-8']).toBe('f4-accounts-payable')
    })

    // F4-9 供应商融资检查表
    it('F4-9 映射为 f4-accounts-payable', () => {
      expect(overrides['F4-9']).toBe('f4-accounts-payable')
    })

    // 附注披露(上市)
    it('F4-note-listed 映射为 f4-accounts-payable', () => {
      expect(overrides['F4-note-listed']).toBe('f4-accounts-payable')
    })

    // 附注披露(国企)
    it('F4-note-soe 映射为 f4-accounts-payable', () => {
      expect(overrides['F4-note-soe']).toBe('f4-accounts-payable')
    })

    // 完整性校验：共12个wp_code映射到f4-accounts-payable
    it('f4-accounts-payable 共有12个wp_code映射', () => {
      const expectedCodes = [
        'F4A', 'F4-1', 'F4-2', 'F4-3', 'F4-4', 'F4-5',
        'F4-6', 'F4-7', 'F4-8', 'F4-9',
        'F4-note-listed', 'F4-note-soe',
      ]
      for (const code of expectedCodes) {
        expect(overrides[code]).toBe('f4-accounts-payable')
      }
      // 验证映射总数
      const actualCount = Object.entries(overrides)
        .filter(([, v]) => v === 'f4-accounts-payable')
        .length
      expect(actualCount).toBe(expectedCodes.length)
    })
  })
})
