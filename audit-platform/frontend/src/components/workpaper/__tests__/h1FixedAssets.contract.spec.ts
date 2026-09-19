/**
 * H1 固定资产 — 注册契约测试
 *
 * Spec: .kiro/specs/h1-fixed-assets/ Task 1.2
 * Validates: Requirements 1.6, 1.7, 1.8
 *
 * 验证 'h1-fixed-assets' componentType 在三个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（H1/H1A/H1-1~H1-20 共22个映射）
 */
import { describe, it, expect, beforeAll } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
  getRendererEntry,
} from '../htmlRendererRegistry'

describe('H1 固定资产 — 注册契约测试', () => {
  describe('htmlRendererRegistry 注册', () => {
    it('h1-fixed-assets 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get('h1-fixed-assets')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('h1-fixed-assets')
      expect(entry?.icon).toBeTruthy()
      expect(entry?.label).toBeTruthy()
      expect(entry?.emits).toContain('save')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 h1-fixed-assets', () => {
      expect(isHtmlComponentType('h1-fixed-assets')).toBe(true)
    })

    it('getRendererEntry 返回正确 entry', () => {
      const entry = getRendererEntry('h1-fixed-assets')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('h1-fixed-assets')
    })

    it('组件 lazy 加载定义存在', () => {
      const entry = HTML_RENDERER_REGISTRY.get('h1-fixed-assets')
      expect(entry?.component).toBeDefined()
      // lazy component 是一个函数或对象
      expect(typeof entry?.component === 'function' || typeof entry?.component === 'object').toBe(true)
    })
  })

  describe('VALID_COMPONENT_TYPES 契约', () => {
    it('后端 wp_classification_service.py 包含 h1-fixed-assets', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"h1-fixed-assets"')
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

    // H1 主编码
    it('H1 映射为 h1-fixed-assets', () => {
      expect(overrides['H1']).toBe('h1-fixed-assets')
    })

    // H1A 程序表
    it('H1A 映射为 h1-fixed-assets', () => {
      expect(overrides['H1A']).toBe('h1-fixed-assets')
    })

    // H1-1 ~ H1-20 逐一验证
    it('H1-1 映射为 h1-fixed-assets', () => {
      expect(overrides['H1-1']).toBe('h1-fixed-assets')
    })

    it('H1-2 映射为 h1-fixed-assets', () => {
      expect(overrides['H1-2']).toBe('h1-fixed-assets')
    })

    it('H1-3 映射为 h1-fixed-assets', () => {
      expect(overrides['H1-3']).toBe('h1-fixed-assets')
    })

    it('H1-4 映射为 h1-fixed-assets', () => {
      expect(overrides['H1-4']).toBe('h1-fixed-assets')
    })

    it('H1-5 映射为 h1-fixed-assets', () => {
      expect(overrides['H1-5']).toBe('h1-fixed-assets')
    })

    it('H1-6 映射为 h1-fixed-assets', () => {
      expect(overrides['H1-6']).toBe('h1-fixed-assets')
    })

    it('H1-7 映射为 h1-fixed-assets', () => {
      expect(overrides['H1-7']).toBe('h1-fixed-assets')
    })

    it('H1-8 映射为 h1-fixed-assets', () => {
      expect(overrides['H1-8']).toBe('h1-fixed-assets')
    })

    it('H1-9 映射为 h1-fixed-assets', () => {
      expect(overrides['H1-9']).toBe('h1-fixed-assets')
    })

    it('H1-10 映射为 h1-fixed-assets', () => {
      expect(overrides['H1-10']).toBe('h1-fixed-assets')
    })

    it('H1-11 映射为 h1-fixed-assets', () => {
      expect(overrides['H1-11']).toBe('h1-fixed-assets')
    })

    it('H1-12 映射为 h1-fixed-assets', () => {
      expect(overrides['H1-12']).toBe('h1-fixed-assets')
    })

    it('H1-13 映射为 h1-fixed-assets', () => {
      expect(overrides['H1-13']).toBe('h1-fixed-assets')
    })

    it('H1-14 映射为 h1-fixed-assets', () => {
      expect(overrides['H1-14']).toBe('h1-fixed-assets')
    })

    it('H1-15 映射为 h1-fixed-assets', () => {
      expect(overrides['H1-15']).toBe('h1-fixed-assets')
    })

    it('H1-16 映射为 h1-fixed-assets', () => {
      expect(overrides['H1-16']).toBe('h1-fixed-assets')
    })

    it('H1-17 映射为 h1-fixed-assets', () => {
      expect(overrides['H1-17']).toBe('h1-fixed-assets')
    })

    it('H1-18 映射为 h1-fixed-assets', () => {
      expect(overrides['H1-18']).toBe('h1-fixed-assets')
    })

    it('H1-19 映射为 h1-fixed-assets', () => {
      expect(overrides['H1-19']).toBe('h1-fixed-assets')
    })

    it('H1-20 映射为 h1-fixed-assets', () => {
      expect(overrides['H1-20']).toBe('h1-fixed-assets')
    })

    // 完整性校验：共22个wp_code映射到h1-fixed-assets
    it('h1-fixed-assets 共有22个wp_code映射', () => {
      const expectedCodes = [
        'H1', 'H1A',
        'H1-1', 'H1-2', 'H1-3', 'H1-4', 'H1-5',
        'H1-6', 'H1-7', 'H1-8', 'H1-9', 'H1-10',
        'H1-11', 'H1-12', 'H1-13', 'H1-14', 'H1-15',
        'H1-16', 'H1-17', 'H1-18', 'H1-19', 'H1-20',
      ]
      for (const code of expectedCodes) {
        expect(overrides[code]).toBe('h1-fixed-assets')
      }
      // 验证映射总数
      const actualCount = Object.entries(overrides)
        .filter(([, v]) => v === 'h1-fixed-assets')
        .length
      expect(actualCount).toBe(expectedCodes.length)
    })
  })
})
