/**
 * H5 油气资产 — 注册契约测试
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/ Task 1.2
 * Validates: Requirements 1.6, 1.7, 1.8
 *
 * 验证 'h5-oil-gas-assets' componentType 在三个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（H5/H5A/H5-1~H5-19 共21个映射）
 * 4. DEDICATED_COMPONENT_TYPES（整册专属组件列表）
 */
import { describe, it, expect, beforeAll } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
  getRendererEntry,
} from '../htmlRendererRegistry'

describe('H5 油气资产 — 注册契约测试', () => {
  describe('htmlRendererRegistry 注册', () => {
    it('h5-oil-gas-assets 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get('h5-oil-gas-assets')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('h5-oil-gas-assets')
      expect(entry?.icon).toBe('🛢️')
      expect(entry?.label).toBe('H5 油气资产')
      expect(entry?.emits).toContain('save')
      expect(entry?.emits).toContain('completed')
      expect(entry?.contextProps).toBe('standard')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 h5-oil-gas-assets', () => {
      expect(isHtmlComponentType('h5-oil-gas-assets')).toBe(true)
    })

    it('getRendererEntry 返回正确 entry', () => {
      const entry = getRendererEntry('h5-oil-gas-assets')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('h5-oil-gas-assets')
    })

    it('组件 lazy 加载定义存在', () => {
      const entry = HTML_RENDERER_REGISTRY.get('h5-oil-gas-assets')
      expect(entry?.component).toBeDefined()
      // lazy component 是一个函数或对象（defineAsyncComponent 结果）
      expect(typeof entry?.component === 'function' || typeof entry?.component === 'object').toBe(true)
    })
  })

  describe('VALID_COMPONENT_TYPES 契约', () => {
    it('后端 wp_classification_service.py 包含 h5-oil-gas-assets', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"h5-oil-gas-assets"')
    })

    it('后端 dedicated_component_types.py 包含 h5-oil-gas-assets', () => {
      const dedicatedPath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/dedicated_component_types.py'
      )
      const content = fs.readFileSync(dedicatedPath, 'utf-8')
      expect(content).toContain('"h5-oil-gas-assets"')
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

    // H5 主编码
    it('H5 映射为 h5-oil-gas-assets', () => {
      expect(overrides['H5']).toBe('h5-oil-gas-assets')
    })

    // H5A 程序表
    it('H5A 映射为 h5-oil-gas-assets', () => {
      expect(overrides['H5A']).toBe('h5-oil-gas-assets')
    })

    // H5-1 ~ H5-19 逐一验证
    it('H5-1 映射为 h5-oil-gas-assets', () => {
      expect(overrides['H5-1']).toBe('h5-oil-gas-assets')
    })

    it('H5-2 映射为 h5-oil-gas-assets', () => {
      expect(overrides['H5-2']).toBe('h5-oil-gas-assets')
    })

    it('H5-3 映射为 h5-oil-gas-assets', () => {
      expect(overrides['H5-3']).toBe('h5-oil-gas-assets')
    })

    it('H5-4 映射为 h5-oil-gas-assets', () => {
      expect(overrides['H5-4']).toBe('h5-oil-gas-assets')
    })

    it('H5-5 映射为 h5-oil-gas-assets', () => {
      expect(overrides['H5-5']).toBe('h5-oil-gas-assets')
    })

    it('H5-6 映射为 h5-oil-gas-assets', () => {
      expect(overrides['H5-6']).toBe('h5-oil-gas-assets')
    })

    it('H5-7 映射为 h5-oil-gas-assets', () => {
      expect(overrides['H5-7']).toBe('h5-oil-gas-assets')
    })

    it('H5-8 映射为 h5-oil-gas-assets', () => {
      expect(overrides['H5-8']).toBe('h5-oil-gas-assets')
    })

    it('H5-9 映射为 h5-oil-gas-assets', () => {
      expect(overrides['H5-9']).toBe('h5-oil-gas-assets')
    })

    it('H5-10 映射为 h5-oil-gas-assets', () => {
      expect(overrides['H5-10']).toBe('h5-oil-gas-assets')
    })

    it('H5-11 映射为 h5-oil-gas-assets', () => {
      expect(overrides['H5-11']).toBe('h5-oil-gas-assets')
    })

    it('H5-12 映射为 h5-oil-gas-assets', () => {
      expect(overrides['H5-12']).toBe('h5-oil-gas-assets')
    })

    it('H5-13 映射为 h5-oil-gas-assets', () => {
      expect(overrides['H5-13']).toBe('h5-oil-gas-assets')
    })

    it('H5-14 映射为 h5-oil-gas-assets', () => {
      expect(overrides['H5-14']).toBe('h5-oil-gas-assets')
    })

    it('H5-15 映射为 h5-oil-gas-assets', () => {
      expect(overrides['H5-15']).toBe('h5-oil-gas-assets')
    })

    it('H5-16 映射为 h5-oil-gas-assets', () => {
      expect(overrides['H5-16']).toBe('h5-oil-gas-assets')
    })

    it('H5-17 映射为 h5-oil-gas-assets', () => {
      expect(overrides['H5-17']).toBe('h5-oil-gas-assets')
    })

    it('H5-18 映射为 h5-oil-gas-assets', () => {
      expect(overrides['H5-18']).toBe('h5-oil-gas-assets')
    })

    it('H5-19 映射为 h5-oil-gas-assets', () => {
      expect(overrides['H5-19']).toBe('h5-oil-gas-assets')
    })

    // 完整性校验：共21个wp_code映射到h5-oil-gas-assets
    it('h5-oil-gas-assets 共有21个wp_code映射', () => {
      const expectedCodes = [
        'H5', 'H5A',
        'H5-1', 'H5-2', 'H5-3', 'H5-4', 'H5-5',
        'H5-6', 'H5-7', 'H5-8', 'H5-9', 'H5-10',
        'H5-11', 'H5-12', 'H5-13', 'H5-14', 'H5-15',
        'H5-16', 'H5-17', 'H5-18', 'H5-19',
      ]
      for (const code of expectedCodes) {
        expect(overrides[code]).toBe('h5-oil-gas-assets')
      }
      // 验证映射总数
      const actualCount = Object.entries(overrides)
        .filter(([, v]) => v === 'h5-oil-gas-assets')
        .length
      expect(actualCount).toBe(expectedCodes.length)
    })
  })

  describe('RENDERER_DISPATCH 注册（Task 5.1 前置验证）', () => {
    it('h5-oil-gas-assets 在 _ONLYOFFICE_HTML_WHITELIST 中（render策略待Task 5.1）', () => {
      const renderConfigPath = path.resolve(
        __dirname,
        '../../../../../../backend/app/routers/wp_render_config.py'
      )
      const content = fs.readFileSync(renderConfigPath, 'utf-8')
      // 在白名单中注册（RENDERER_DISPATCH 注册在 Task 5.1 完成）
      expect(content).toContain('"h5-oil-gas-assets"')
    })
  })
})
