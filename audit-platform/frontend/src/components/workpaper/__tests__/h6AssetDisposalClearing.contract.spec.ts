/**
 * H6 固定资产清理 — 注册契约测试
 *
 * Spec: .kiro/specs/h6-asset-disposal-clearing/ Task 1.2
 * Validates: Requirements 1.6, 1.7, 1.8
 *
 * 验证 'h6-asset-disposal-clearing' componentType 在三个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（H6/H6A/H6-1~H6-4 共6个映射）
 */
import { describe, it, expect, beforeAll } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
  getRendererEntry,
} from '../htmlRendererRegistry'

describe('H6 固定资产清理 — 注册契约测试', () => {
  describe('htmlRendererRegistry 注册', () => {
    it('h6-asset-disposal-clearing 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get('h6-asset-disposal-clearing')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('h6-asset-disposal-clearing')
      expect(entry?.icon).toBeTruthy()
      expect(entry?.label).toBeTruthy()
      expect(entry?.emits).toContain('save')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 h6-asset-disposal-clearing', () => {
      expect(isHtmlComponentType('h6-asset-disposal-clearing')).toBe(true)
    })

    it('getRendererEntry 返回正确 entry', () => {
      const entry = getRendererEntry('h6-asset-disposal-clearing')
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe('h6-asset-disposal-clearing')
    })

    it('组件 lazy 加载定义存在', () => {
      const entry = HTML_RENDERER_REGISTRY.get('h6-asset-disposal-clearing')
      expect(entry?.component).toBeDefined()
      // lazy component 是一个函数或对象
      expect(typeof entry?.component === 'function' || typeof entry?.component === 'object').toBe(true)
    })
  })

  describe('VALID_COMPONENT_TYPES 契约', () => {
    it('后端 wp_classification_service.py 包含 h6-asset-disposal-clearing', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"h6-asset-disposal-clearing"')
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

    it('H6 映射为 h6-asset-disposal-clearing', () => {
      expect(overrides['H6']).toBe('h6-asset-disposal-clearing')
    })

    it('H6A 映射为 h6-asset-disposal-clearing', () => {
      expect(overrides['H6A']).toBe('h6-asset-disposal-clearing')
    })

    it('H6-1 映射为 h6-asset-disposal-clearing', () => {
      expect(overrides['H6-1']).toBe('h6-asset-disposal-clearing')
    })

    it('H6-2 映射为 h6-asset-disposal-clearing', () => {
      expect(overrides['H6-2']).toBe('h6-asset-disposal-clearing')
    })

    it('H6-3 映射为 h6-asset-disposal-clearing', () => {
      expect(overrides['H6-3']).toBe('h6-asset-disposal-clearing')
    })

    it('H6-4 映射为 h6-asset-disposal-clearing', () => {
      expect(overrides['H6-4']).toBe('h6-asset-disposal-clearing')
    })

    // 完整性校验：共6个wp_code映射到h6-asset-disposal-clearing
    it('h6-asset-disposal-clearing 共有6个wp_code映射', () => {
      const expectedCodes = ['H6', 'H6A', 'H6-1', 'H6-2', 'H6-3', 'H6-4']
      for (const code of expectedCodes) {
        expect(overrides[code]).toBe('h6-asset-disposal-clearing')
      }
      // 验证映射总数
      const actualCount = Object.entries(overrides)
        .filter(([, v]) => v === 'h6-asset-disposal-clearing')
        .length
      expect(actualCount).toBe(expectedCodes.length)
    })
  })

  describe('RENDERER_DISPATCH 契约（Phase 5）', () => {
    it('后端 wp_render_strategies 包存在（Phase 5 创建后完成注册）', () => {
      // RENDERER_DISPATCH 将在 Phase 5 (task 5.1) 注册 h6-asset-disposal-clearing
      // 此测试通过读取后端目录验证模块存在
      const strategiesDir = path.resolve(
        __dirname,
        '../../../../../../backend/app/routers/wp_render_strategies'
      )
      const exists = fs.existsSync(strategiesDir)
      expect(exists).toBe(true)
    })
  })
})
