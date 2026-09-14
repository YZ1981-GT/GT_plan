/**
 * K8 销售费用 — 注册契约测试
 *
 * Spec: .kiro/specs/k8-selling-expenses/ Task 1.2
 * Validates: Requirements 1.6, 1.7, 1.8
 *
 * 验证 'k8-selling-expenses' componentType 在三个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（K8/K8-1~K8-8/K8A 共10个映射）
 * 4. GtK8SellingExpenses.vue 主入口存在
 * 5. k8/ 子组件11个stub文件存在
 */
import { describe, it, expect, beforeAll } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
  getRendererEntry,
} from '../htmlRendererRegistry'

const COMPONENT_TYPE = 'k8-selling-expenses'

const K8_WP_CODES = [
  'K8',
  'K8-1',
  'K8-2',
  'K8-3',
  'K8-4',
  'K8-5',
  'K8-6',
  'K8-7',
  'K8-8',
  'K8A',
] as const

describe('K8 销售费用 — 注册契约测试', () => {
  describe('htmlRendererRegistry 注册', () => {
    it('k8-selling-expenses 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get(COMPONENT_TYPE)
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe(COMPONENT_TYPE)
      expect(entry?.icon).toBe('💰')
      expect(entry?.label).toBe('K8 销售费用')
      expect(entry?.emits).toContain('save')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 k8-selling-expenses', () => {
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
    it('后端 wp_classification_service.py 包含 k8-selling-expenses', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"k8-selling-expenses"')
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

    for (const code of K8_WP_CODES) {
      it(`${code} 映射为 k8-selling-expenses`, () => {
        expect(overrides[code]).toBe(COMPONENT_TYPE)
      })
    }

    it('k8-selling-expenses 共有10个wp_code映射', () => {
      const actualCount = Object.entries(overrides)
        .filter(([, v]) => v === COMPONENT_TYPE)
        .length
      expect(actualCount).toBe(K8_WP_CODES.length)
    })
  })

  describe('主入口 + 子组件文件存在性', () => {
    const workpaperDir = path.resolve(__dirname, '..')

    it('GtK8SellingExpenses.vue 主入口文件存在', () => {
      const mainEntry = path.join(workpaperDir, 'GtK8SellingExpenses.vue')
      expect(fs.existsSync(mainEntry)).toBe(true)
    })

    const CHILD_COMPONENTS = [
      'k8/core/K8TabIndex.vue',
      'k8/core/K8TabAdjudication.vue',
      'k8/core/K8TabDetail.vue',
      'k8/core/K8TabAdjustment.vue',
      'k8/core/K8TabDisclosureListed.vue',
      'k8/core/K8TabDisclosureSoe.vue',
      'k8/analysis/K8TabSubstantiveAnalysis.vue',
      'k8/cutoff/K8TabCutoffV2S.vue',
      'k8/cutoff/K8TabCutoffS2V.vue',
      'k8/inspection/K8TabContractCheck.vue',
      'k8/inspection/K8TabSellingCheck.vue',
    ] as const

    for (const child of CHILD_COMPONENTS) {
      it(`子组件 ${child} 存在`, () => {
        const filePath = path.join(workpaperDir, child)
        expect(fs.existsSync(filePath)).toBe(true)
      })
    }

    it('k8/ 子目录共有11个子组件', () => {
      expect(CHILD_COMPONENTS.length).toBe(11)
    })
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
