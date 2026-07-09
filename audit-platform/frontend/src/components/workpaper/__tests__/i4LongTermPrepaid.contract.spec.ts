/**
 * I4 长期待摊费用 — 注册契约测试
 *
 * Spec: .kiro/specs/i4-long-term-prepaid/ Task 1.2
 * Validates: Requirements 1.6, 1.7, 1.8
 *
 * 验证 'i4-long-term-prepaid' componentType 在三个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（I4/I4-1~I4-7/I4A 共9个映射）
 * 4. 主入口 GtI4LongTermPrepaid.vue 可被导入
 */
import { describe, it, expect, beforeAll } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
  getRendererEntry,
} from '../htmlRendererRegistry'

const COMPONENT_TYPE = 'i4-long-term-prepaid'

// I4 + I4A + I4-1~I4-7 共9个wp_code
const EXPECTED_WP_CODES = [
  'I4',
  'I4-1',
  'I4-2',
  'I4-3',
  'I4-4',
  'I4-5',
  'I4-6',
  'I4-7',
  'I4A',
]

describe('I4 长期待摊费用 — 注册契约测试', () => {
  describe('htmlRendererRegistry 注册', () => {
    it('i4-long-term-prepaid 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get(COMPONENT_TYPE)
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe(COMPONENT_TYPE)
      expect(entry?.icon).toBeTruthy()
      expect(entry?.label).toBeTruthy()
      expect(entry?.emits).toContain('save')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 i4-long-term-prepaid', () => {
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
    it('后端 wp_classification_service.py 包含 i4-long-term-prepaid', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"i4-long-term-prepaid"')
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

    // I4 主编码
    it('I4 映射为 i4-long-term-prepaid', () => {
      expect(overrides['I4']).toBe(COMPONENT_TYPE)
    })

    // I4A 程序表
    it('I4A 映射为 i4-long-term-prepaid', () => {
      expect(overrides['I4A']).toBe(COMPONENT_TYPE)
    })

    // I4-1 ~ I4-7 逐一验证
    it.each([
      'I4-1', 'I4-2', 'I4-3', 'I4-4',
      'I4-5', 'I4-6', 'I4-7',
    ])('%s 映射为 i4-long-term-prepaid', (code) => {
      expect(overrides[code]).toBe(COMPONENT_TYPE)
    })

    // 完整性校验：共9个wp_code映射到i4-long-term-prepaid
    it('i4-long-term-prepaid 共有9个wp_code映射', () => {
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

  describe('主入口组件存在性', () => {
    it('GtI4LongTermPrepaid.vue 文件存在', () => {
      const vuePath = path.resolve(
        __dirname,
        '../GtI4LongTermPrepaid.vue'
      )
      expect(fs.existsSync(vuePath)).toBe(true)
    })
  })
})
