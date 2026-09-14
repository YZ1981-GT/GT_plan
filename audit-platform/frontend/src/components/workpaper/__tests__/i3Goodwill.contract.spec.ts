/**
 * I3 商誉 — 注册契约测试
 *
 * Spec: .kiro/specs/i3-goodwill/ Task 1.2
 * Validates: Requirements 1.6, 1.7, 1.8
 *
 * 验证 'i3-goodwill' componentType 在三个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（I3/I3-1~I3-8/I3A 共10个映射）
 * 4. 主入口 GtI3Goodwill.vue 可被导入
 */
import { describe, it, expect, beforeAll } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
  getRendererEntry,
} from '../htmlRendererRegistry'

const COMPONENT_TYPE = 'i3-goodwill'

// I3 + I3A + I3-1~I3-8 共10个wp_code
const EXPECTED_WP_CODES = [
  'I3',
  'I3-1',
  'I3-2',
  'I3-3',
  'I3-4',
  'I3-5',
  'I3-6',
  'I3-7',
  'I3-8',
  'I3A',
]

describe('I3 商誉 — 注册契约测试', () => {
  describe('htmlRendererRegistry 注册', () => {
    it('i3-goodwill 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get(COMPONENT_TYPE)
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe(COMPONENT_TYPE)
      expect(entry?.icon).toBeTruthy()
      expect(entry?.label).toBeTruthy()
      expect(entry?.emits).toContain('save')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 i3-goodwill', () => {
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
    it('后端 wp_classification_service.py 包含 i3-goodwill', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"i3-goodwill"')
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

    // I3 主编码
    it('I3 映射为 i3-goodwill', () => {
      expect(overrides['I3']).toBe(COMPONENT_TYPE)
    })

    // I3A 程序表
    it('I3A 映射为 i3-goodwill', () => {
      expect(overrides['I3A']).toBe(COMPONENT_TYPE)
    })

    // I3-1 ~ I3-8 逐一验证
    it.each([
      'I3-1', 'I3-2', 'I3-3', 'I3-4',
      'I3-5', 'I3-6', 'I3-7', 'I3-8',
    ])('%s 映射为 i3-goodwill', (code) => {
      expect(overrides[code]).toBe(COMPONENT_TYPE)
    })

    // 完整性校验：共10个wp_code映射到i3-goodwill
    it('i3-goodwill 共有10个wp_code映射', () => {
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
    it('GtI3Goodwill.vue 文件存在', () => {
      const vuePath = path.resolve(
        __dirname,
        '../GtI3Goodwill.vue'
      )
      expect(fs.existsSync(vuePath)).toBe(true)
    })
  })
})
