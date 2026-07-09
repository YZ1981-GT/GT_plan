/**
 * I2 开发支出 — 注册契约测试
 *
 * Spec: .kiro/specs/i2-development-expenditure/ Task 1.2
 * Validates: Requirements 1.6, 1.7, 1.8
 *
 * 验证 'i2-development-expenditure' componentType 在三个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（I2/I2A/I2-1~I2-16 共18个映射）
 * 4. 主入口 GtI2DevelopmentExpenditure.vue 可被导入
 */
import { describe, it, expect, beforeAll } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
  getRendererEntry,
} from '../htmlRendererRegistry'

const COMPONENT_TYPE = 'i2-development-expenditure'

// I2 + I2A + I2-1~I2-16 共18个wp_code
const EXPECTED_WP_CODES = [
  'I2',
  'I2A',
  'I2-1',
  'I2-2',
  'I2-3',
  'I2-4',
  'I2-5',
  'I2-6',
  'I2-7',
  'I2-8',
  'I2-9',
  'I2-10',
  'I2-11',
  'I2-12',
  'I2-13',
  'I2-14',
  'I2-15',
  'I2-16',
]

describe('I2 开发支出 — 注册契约测试', () => {
  describe('htmlRendererRegistry 注册', () => {
    it('i2-development-expenditure 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get(COMPONENT_TYPE)
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe(COMPONENT_TYPE)
      expect(entry?.icon).toBeTruthy()
      expect(entry?.label).toBeTruthy()
      expect(entry?.emits).toContain('save')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 i2-development-expenditure', () => {
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
    it('后端 wp_classification_service.py 包含 i2-development-expenditure', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"i2-development-expenditure"')
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

    // I2 主编码
    it('I2 映射为 i2-development-expenditure', () => {
      expect(overrides['I2']).toBe(COMPONENT_TYPE)
    })

    // I2A 程序表
    it('I2A 映射为 i2-development-expenditure', () => {
      expect(overrides['I2A']).toBe(COMPONENT_TYPE)
    })

    // I2-1 ~ I2-16 逐一验证
    it.each([
      'I2-1', 'I2-2', 'I2-3', 'I2-4', 'I2-5',
      'I2-6', 'I2-7', 'I2-8', 'I2-9', 'I2-10',
      'I2-11', 'I2-12', 'I2-13', 'I2-14', 'I2-15',
      'I2-16',
    ])('%s 映射为 i2-development-expenditure', (code) => {
      expect(overrides[code]).toBe(COMPONENT_TYPE)
    })

    // 完整性校验：共18个wp_code映射到i2-development-expenditure
    it('i2-development-expenditure 共有18个wp_code映射', () => {
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
    it('GtI2DevelopmentExpenditure.vue 文件存在', () => {
      const vuePath = path.resolve(
        __dirname,
        '../GtI2DevelopmentExpenditure.vue'
      )
      expect(fs.existsSync(vuePath)).toBe(true)
    })
  })
})
