/**
 * K11 资产减值损失 — 注册契约测试
 *
 * Spec: .kiro/specs/k11-asset-impairment-loss/ Task 1.2
 * Validates: Requirements 1.6, 1.7, 1.8
 *
 * 验证 'k11-asset-impairment-loss' componentType 四件套注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（K11/K11-1~K11-3/K11A 共5个映射）
 * 4. render schema YAML 文件存在
 */
import { describe, it, expect, beforeAll } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
  getRendererEntry,
} from '../htmlRendererRegistry'

const COMPONENT_TYPE = 'k11-asset-impairment-loss'

const K11_WP_CODES = [
  'K11',
  'K11-1',
  'K11-2',
  'K11-3',
  'K11A',
] as const

describe('K11 资产减值损失 — 注册契约测试', () => {
  describe('htmlRendererRegistry 注册', () => {
    it('k11-asset-impairment-loss 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get(COMPONENT_TYPE)
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe(COMPONENT_TYPE)
      expect(entry?.icon).toBe('📉')
      expect(entry?.label).toBe('K11 资产减值损失')
      expect(entry?.emits).toContain('save')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 k11-asset-impairment-loss', () => {
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
      expect(typeof entry?.component === 'function' || typeof entry?.component === 'object').toBe(true)
    })

    it('contextProps 配置为 standard', () => {
      const entry = HTML_RENDERER_REGISTRY.get(COMPONENT_TYPE)
      expect(entry?.contextProps).toBe('standard')
    })

    it('emits 包含 navigate-sheet', () => {
      const entry = HTML_RENDERER_REGISTRY.get(COMPONENT_TYPE)
      expect(entry?.emits).toContain('navigate-sheet')
    })
  })

  describe('VALID_COMPONENT_TYPES 契约', () => {
    it('后端 wp_classification_service.py 包含 k11-asset-impairment-loss', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"k11-asset-impairment-loss"')
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

    for (const code of K11_WP_CODES) {
      it(`${code} 映射为 k11-asset-impairment-loss`, () => {
        expect(overrides[code]).toBe(COMPONENT_TYPE)
      })
    }

    it('k11-asset-impairment-loss 共有5个wp_code映射', () => {
      const actualCount = Object.entries(overrides)
        .filter(([, v]) => v === COMPONENT_TYPE)
        .length
      expect(actualCount).toBe(K11_WP_CODES.length)
    })
  })

  describe('render schema YAML 存在性', () => {
    it('K11.yaml 渲染配置文件存在', () => {
      const yamlPath = path.resolve(
        __dirname,
        '../../../../../../backend/data/ledger_adapters/wp_render_schema/generated/K11.yaml'
      )
      expect(fs.existsSync(yamlPath)).toBe(true)
    })

    it('K11.yaml 包含 wp_code: K11', () => {
      const yamlPath = path.resolve(
        __dirname,
        '../../../../../../backend/data/ledger_adapters/wp_render_schema/generated/K11.yaml'
      )
      const content = fs.readFileSync(yamlPath, 'utf-8')
      expect(content).toContain('wp_code: K11')
    })
  })

  describe('主入口 + 子目录结构存在性', () => {
    const workpaperDir = path.resolve(__dirname, '..')

    it('GtK11AssetImpairmentLoss.vue 主入口文件存在', () => {
      const mainEntry = path.join(workpaperDir, 'GtK11AssetImpairmentLoss.vue')
      expect(fs.existsSync(mainEntry)).toBe(true)
    })

    it('子目录 k11/core/ 存在', () => {
      const dirPath = path.join(workpaperDir, 'k11/core')
      expect(fs.existsSync(dirPath)).toBe(true)
    })
  })

  describe('RENDERER_DISPATCH 契约（Phase 5）', () => {
    it('后端 wp_render_strategies 包存在', () => {
      const strategiesDir = path.resolve(
        __dirname,
        '../../../../../../backend/app/routers/wp_render_strategies'
      )
      expect(fs.existsSync(strategiesDir)).toBe(true)
    })
  })
})
