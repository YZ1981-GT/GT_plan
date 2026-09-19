/**
 * I1 无形资产 — 注册契约测试
 *
 * Spec: .kiro/specs/i1-intangible-assets/ Task 1.2
 * Validates: Requirements 1.6, 1.7, 1.8
 *
 * 验证 'i1-intangible-assets' componentType 在三个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（I1/I1A/I1-1~I1-13 共15个映射）
 */
import { describe, it, expect, beforeAll } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
  getRendererEntry,
} from '../htmlRendererRegistry'

const COMPONENT_TYPE = 'i1-intangible-assets'

// I1 + I1A + I1-1~I1-13 共15个wp_code
const EXPECTED_WP_CODES = [
  'I1',
  'I1A',
  'I1-1',
  'I1-2',
  'I1-3',
  'I1-4',
  'I1-5',
  'I1-6',
  'I1-7',
  'I1-8',
  'I1-9',
  'I1-10',
  'I1-11',
  'I1-12',
  'I1-13',
]

describe('I1 无形资产 — 注册契约测试', () => {
  describe('htmlRendererRegistry 注册', () => {
    it('i1-intangible-assets 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get(COMPONENT_TYPE)
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe(COMPONENT_TYPE)
      expect(entry?.icon).toBeTruthy()
      expect(entry?.label).toBeTruthy()
      expect(entry?.emits).toContain('save')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 i1-intangible-assets', () => {
      expect(isHtmlComponentType(COMPONENT_TYPE)).toBe(true)
    })

    it('getRendererEntry 返回正确 entry', () => {
      const entry = getRendererEntry(COMPONENT_TYPE)
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe(COMPONENT_TYPE)
    })

    it('组件 lazy 加载定义存在', () => {
      const entry = HTML_RENDERER_REGISTRY.get(COMPONENT_TYPE)
      expect(entry?.component).toBeDefined()
      // lazy component 是一个函数或对象
      expect(typeof entry?.component === 'function' || typeof entry?.component === 'object').toBe(true)
    })
  })

  describe('VALID_COMPONENT_TYPES 契约', () => {
    it('后端 wp_classification_service.py 包含 i1-intangible-assets', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"i1-intangible-assets"')
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

    // I1 主编码
    it('I1 映射为 i1-intangible-assets', () => {
      expect(overrides['I1']).toBe(COMPONENT_TYPE)
    })

    // I1A 程序表
    it('I1A 映射为 i1-intangible-assets', () => {
      expect(overrides['I1A']).toBe(COMPONENT_TYPE)
    })

    // I1-1 ~ I1-13 逐一验证
    it.each([
      'I1-1', 'I1-2', 'I1-3', 'I1-4', 'I1-5',
      'I1-6', 'I1-7', 'I1-8', 'I1-9', 'I1-10',
      'I1-11', 'I1-12', 'I1-13',
    ])('%s 映射为 i1-intangible-assets', (code) => {
      expect(overrides[code]).toBe(COMPONENT_TYPE)
    })

    // 完整性校验：共15个wp_code映射到i1-intangible-assets
    it('i1-intangible-assets 共有15个wp_code映射', () => {
      for (const code of EXPECTED_WP_CODES) {
        expect(overrides[code]).toBe(COMPONENT_TYPE)
      }
      // 验证映射总数
      const actualCount = Object.entries(overrides)
        .filter(([, v]) => v === COMPONENT_TYPE)
        .length
      expect(actualCount).toBe(EXPECTED_WP_CODES.length)
    })
  })
})
