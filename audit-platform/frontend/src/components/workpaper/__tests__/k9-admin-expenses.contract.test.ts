/**
 * K9 管理费用 — 注册契约测试
 *
 * Spec: .kiro/specs/k9-admin-expenses/ Task 1.2
 * Validates: Requirements 1.6, 1.7, 1.8
 *
 * 验证 'k9-admin-expenses' componentType 在三个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（K9/K9-1~K9-8/K9A 共10个映射）
 * 4. GtK9AdminExpenses.vue 主入口存在
 * 5. k9/ 子目录结构存在
 */
import { describe, it, expect, beforeAll } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
  getRendererEntry,
} from '../htmlRendererRegistry'

const COMPONENT_TYPE = 'k9-admin-expenses'

const K9_WP_CODES = [
  'K9',
  'K9-1',
  'K9-2',
  'K9-3',
  'K9-4',
  'K9-5',
  'K9-6',
  'K9-7',
  'K9-8',
  'K9A',
] as const

describe('K9 管理费用 — 注册契约测试', () => {
  describe('htmlRendererRegistry 注册', () => {
    it('k9-admin-expenses 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get(COMPONENT_TYPE)
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe(COMPONENT_TYPE)
      expect(entry?.icon).toBe('🏢')
      expect(entry?.label).toBe('K9 管理费用')
      expect(entry?.emits).toContain('save')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 k9-admin-expenses', () => {
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
    it('后端 wp_classification_service.py 包含 k9-admin-expenses', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"k9-admin-expenses"')
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

    for (const code of K9_WP_CODES) {
      it(`${code} 映射为 k9-admin-expenses`, () => {
        expect(overrides[code]).toBe(COMPONENT_TYPE)
      })
    }

    it('k9-admin-expenses 共有10个wp_code映射', () => {
      const actualCount = Object.entries(overrides)
        .filter(([, v]) => v === COMPONENT_TYPE)
        .length
      expect(actualCount).toBe(K9_WP_CODES.length)
    })
  })

  describe('主入口 + 子目录结构存在性', () => {
    const workpaperDir = path.resolve(__dirname, '..')

    it('GtK9AdminExpenses.vue 主入口文件存在', () => {
      const mainEntry = path.join(workpaperDir, 'GtK9AdminExpenses.vue')
      expect(fs.existsSync(mainEntry)).toBe(true)
    })

    const K9_SUBDIRS = [
      'k9/core',
      'k9/analysis',
      'k9/cutoff',
      'k9/inspection',
    ] as const

    for (const subdir of K9_SUBDIRS) {
      it(`子目录 ${subdir}/ 存在`, () => {
        const dirPath = path.join(workpaperDir, subdir)
        expect(fs.existsSync(dirPath)).toBe(true)
      })
    }
  })

  describe('RENDERER_DISPATCH 契约（Phase 5）', () => {
    it('后端 wp_render_strategies 包存在（Task 5.1 创建后完成注册）', () => {
      const strategiesDir = path.resolve(
        __dirname,
        '../../../../../../backend/app/routers/wp_render_strategies'
      )
      const exists = fs.existsSync(strategiesDir)
      expect(exists).toBe(true)
    })
  })
})
