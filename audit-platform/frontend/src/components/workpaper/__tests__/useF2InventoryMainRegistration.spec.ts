/**
 * F2 存货核心组 — 注册契约测试
 *
 * 验证 'f2-inventory-main' componentType 在三个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（F2/F2-1~F2-14/F2-16/F2-18~F2-20/F2-29~F2-32/F2A/F2-note-listed/F2-note-soe 共26个映射）
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

describe('F2 存货核心组 — 注册契约测试', () => {
  describe('htmlRendererRegistry 注册', () => {
    it('f2-inventory-main 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get('f2-inventory-main')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('f2-inventory-main')
      expect(entry?.icon).toBe('📦')
      expect(entry?.label).toBe('F2 存货核心')
      expect(entry?.emits).toContain('save')
      expect(entry?.emits).toContain('completed')
      expect(entry?.contextProps).toBe('standard')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 f2-inventory-main', () => {
      expect(isHtmlComponentType('f2-inventory-main')).toBe(true)
    })

    it('getRendererEntry 返回正确 entry', () => {
      const entry = getRendererEntry('f2-inventory-main')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('f2-inventory-main')
    })
  })

  describe('VALID_COMPONENT_TYPES 契约', () => {
    it('后端 wp_classification_service.py 包含 f2-inventory-main', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"f2-inventory-main"')
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

    // F2 程序表
    it('F2A 映射为 f2-inventory-main', () => {
      expect(overrides['F2A']).toBe('f2-inventory-main')
    })

    it('F2 映射为 f2-inventory-main', () => {
      expect(overrides['F2']).toBe('f2-inventory-main')
    })

    // F2-1~F2-14 连续编码（审定表+明细+调整）
    it('F2-1 映射为 f2-inventory-main', () => {
      expect(overrides['F2-1']).toBe('f2-inventory-main')
    })

    it('F2-2 映射为 f2-inventory-main', () => {
      expect(overrides['F2-2']).toBe('f2-inventory-main')
    })

    it('F2-3 映射为 f2-inventory-main', () => {
      expect(overrides['F2-3']).toBe('f2-inventory-main')
    })

    it('F2-4 映射为 f2-inventory-main', () => {
      expect(overrides['F2-4']).toBe('f2-inventory-main')
    })

    it('F2-5 映射为 f2-inventory-main', () => {
      expect(overrides['F2-5']).toBe('f2-inventory-main')
    })

    it('F2-6 映射为 f2-inventory-main', () => {
      expect(overrides['F2-6']).toBe('f2-inventory-main')
    })

    it('F2-7 映射为 f2-inventory-main', () => {
      expect(overrides['F2-7']).toBe('f2-inventory-main')
    })

    it('F2-8 映射为 f2-inventory-main', () => {
      expect(overrides['F2-8']).toBe('f2-inventory-main')
    })

    it('F2-9 映射为 f2-inventory-main', () => {
      expect(overrides['F2-9']).toBe('f2-inventory-main')
    })

    it('F2-10 映射为 f2-inventory-main', () => {
      expect(overrides['F2-10']).toBe('f2-inventory-main')
    })

    it('F2-11 映射为 f2-inventory-main', () => {
      expect(overrides['F2-11']).toBe('f2-inventory-main')
    })

    it('F2-12 映射为 f2-inventory-main', () => {
      expect(overrides['F2-12']).toBe('f2-inventory-main')
    })

    it('F2-13 映射为 f2-inventory-main', () => {
      expect(overrides['F2-13']).toBe('f2-inventory-main')
    })

    it('F2-14 映射为 f2-inventory-main', () => {
      expect(overrides['F2-14']).toBe('f2-inventory-main')
    })

    // F2-16 会计政策
    it('F2-16 映射为 f2-inventory-main', () => {
      expect(overrides['F2-16']).toBe('f2-inventory-main')
    })

    // F2-18~F2-20 分析类
    it('F2-18 映射为 f2-inventory-main', () => {
      expect(overrides['F2-18']).toBe('f2-inventory-main')
    })

    it('F2-19 映射为 f2-inventory-main', () => {
      expect(overrides['F2-19']).toBe('f2-inventory-main')
    })

    it('F2-20 映射为 f2-inventory-main', () => {
      expect(overrides['F2-20']).toBe('f2-inventory-main')
    })

    // F2-29~F2-32 截止测试
    it('F2-29 映射为 f2-inventory-main', () => {
      expect(overrides['F2-29']).toBe('f2-inventory-main')
    })

    it('F2-30 映射为 f2-inventory-main', () => {
      expect(overrides['F2-30']).toBe('f2-inventory-main')
    })

    it('F2-31 映射为 f2-inventory-main', () => {
      expect(overrides['F2-31']).toBe('f2-inventory-main')
    })

    it('F2-32 映射为 f2-inventory-main', () => {
      expect(overrides['F2-32']).toBe('f2-inventory-main')
    })

    // 附注披露
    it('F2-note-listed 映射为 f2-inventory-main', () => {
      expect(overrides['F2-note-listed']).toBe('f2-inventory-main')
    })

    it('F2-note-soe 映射为 f2-inventory-main', () => {
      expect(overrides['F2-note-soe']).toBe('f2-inventory-main')
    })

    // 完整性校验：共26个wp_code映射到f2-inventory-main
    it('f2-inventory-main 共有26个wp_code映射', () => {
      const expectedCodes = [
        'F2', 'F2-1', 'F2-2', 'F2-3', 'F2-4', 'F2-5', 'F2-6', 'F2-7',
        'F2-8', 'F2-9', 'F2-10', 'F2-11', 'F2-12', 'F2-13', 'F2-14',
        'F2-16', 'F2-18', 'F2-19', 'F2-20',
        'F2-29', 'F2-30', 'F2-31', 'F2-32',
        'F2A', 'F2-note-listed', 'F2-note-soe',
      ]
      for (const code of expectedCodes) {
        expect(overrides[code]).toBe('f2-inventory-main')
      }
      // 验证映射总数
      const actualCount = Object.entries(overrides)
        .filter(([, v]) => v === 'f2-inventory-main')
        .length
      expect(actualCount).toBe(expectedCodes.length)
    })
  })
})
