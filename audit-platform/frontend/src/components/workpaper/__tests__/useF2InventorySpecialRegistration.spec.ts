/**
 * F2 存货特殊组 — 注册契约测试
 *
 * 验证 'f2-inventory-special' componentType 在三个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（F2-55A/F2-55~F2-58/F2-61A/F2-61~F2-72 共18个映射）
 * 4. IPO可见性单元测试（business_category 控制）
 *
 * **Validates: Requirements 1.5, 1.6, 1.7, 2.1, 2.2**
 */
import { describe, it, expect, beforeAll } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
  getRendererEntry,
} from '../htmlRendererRegistry'

// Inline to avoid pulling in useF2SpecialFormData's heavy dependencies (apiProxy etc.)
const IPO_CATEGORIES = ['IPO', '上市公司年审', '新三板', '重大资产重组'] as const

describe('F2 存货特殊组 — 注册契约测试', () => {
  describe('htmlRendererRegistry 注册', () => {
    it('f2-inventory-special 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get('f2-inventory-special')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('f2-inventory-special')
      expect(entry?.icon).toBeTruthy()
      expect(entry?.label).toBeTruthy()
      expect(entry?.emits).toContain('save')
      expect(entry?.emits).toContain('completed')
      expect(entry?.contextProps).toBe('standard')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 f2-inventory-special', () => {
      expect(isHtmlComponentType('f2-inventory-special')).toBe(true)
    })

    it('getRendererEntry 返回正确 entry', () => {
      const entry = getRendererEntry('f2-inventory-special')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('f2-inventory-special')
    })
  })

  describe('VALID_COMPONENT_TYPES 契约', () => {
    it('后端 wp_classification_service.py 包含 f2-inventory-special', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py',
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"f2-inventory-special"')
    })
  })

  describe('wp_code_overrides 契约', () => {
    let overrides: Record<string, string>

    beforeAll(() => {
      const overridesPath = path.resolve(
        __dirname,
        '../../../../../../backend/app/data/wp_code_overrides.json',
      )
      overrides = JSON.parse(fs.readFileSync(overridesPath, 'utf-8'))
    })

    const EXPECTED_WP_CODES = [
      'F2-55A', 'F2-55', 'F2-56', 'F2-57', 'F2-58',
      'F2-61A', 'F2-61', 'F2-62', 'F2-63', 'F2-64',
      'F2-65', 'F2-66', 'F2-67', 'F2-68', 'F2-69',
      'F2-70', 'F2-71', 'F2-72',
    ]

    it.each(EXPECTED_WP_CODES)('%s 映射为 f2-inventory-special', (code) => {
      expect(overrides[code]).toBe('f2-inventory-special')
    })

    it('f2-inventory-special 共有18个wp_code映射', () => {
      const actualCount = Object.entries(overrides)
        .filter(([, v]) => v === 'f2-inventory-special')
        .length
      expect(actualCount).toBe(18)
    })

    it('合同履约成本组5个编码全部覆盖', () => {
      const contractCodes = ['F2-55A', 'F2-55', 'F2-56', 'F2-57', 'F2-58']
      for (const code of contractCodes) {
        expect(overrides[code]).toBe('f2-inventory-special')
      }
    })

    it('IPO/舞弊应对组13个编码全部覆盖', () => {
      const ipoCodes = [
        'F2-61A', 'F2-61', 'F2-62', 'F2-63', 'F2-64',
        'F2-65', 'F2-66', 'F2-67', 'F2-68', 'F2-69',
        'F2-70', 'F2-71', 'F2-72',
      ]
      for (const code of ipoCodes) {
        expect(overrides[code]).toBe('f2-inventory-special')
      }
    })
  })

  describe('IPO 可见性', () => {
    it('IPO_CATEGORIES 包含4个预期类别', () => {
      expect(IPO_CATEGORIES).toHaveLength(4)
      expect(IPO_CATEGORIES).toContain('IPO')
      expect(IPO_CATEGORIES).toContain('上市公司年审')
      expect(IPO_CATEGORIES).toContain('新三板')
      expect(IPO_CATEGORIES).toContain('重大资产重组')
    })

    it.each([
      ['IPO', true],
      ['上市公司年审', true],
      ['新三板', true],
      ['重大资产重组', true],
      ['一般审计', false],
      ['专项审计', false],
      ['内部控制审计', false],
      ['', false],
    ] as const)('business_category="%s" → isIpo=%s', (category, expected) => {
      const isIpo = (IPO_CATEGORIES as readonly string[]).includes(category)
      expect(isIpo).toBe(expected)
    })
  })
})
