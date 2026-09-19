/**
 * H8 使用权资产 — 注册契约测试
 *
 * Spec: .kiro/specs/h8-right-of-use-assets/ Task 1.2
 * Validates: Requirements 1.6, 1.7, 1.8
 *
 * 验证 'h8-right-of-use-assets' componentType 在四个注册表中正确注册：
 * 1. htmlRendererRegistry（前端组件映射，defineAsyncComponent）
 * 2. VALID_COMPONENT_TYPES（后端 wp_classification_service.py）
 * 3. wp_code_overrides（H8/H8A/H8-1~H8-14 共16个映射）
 * 4. RENDERER_DISPATCH（后端渲染策略分发）
 */
import { describe, it, expect, beforeAll } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

import {
  HTML_RENDERER_REGISTRY,
  isHtmlComponentType,
  getRendererEntry,
} from '../htmlRendererRegistry'

const COMPONENT_TYPE = 'h8-right-of-use-assets'

describe('H8 使用权资产 — 注册契约测试', () => {
  describe('htmlRendererRegistry 注册', () => {
    it('h8-right-of-use-assets 已注册且配置正确', () => {
      const entry = HTML_RENDERER_REGISTRY.get(COMPONENT_TYPE)
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe(COMPONENT_TYPE)
      expect(entry?.icon).toBeTruthy()
      expect(entry?.label).toContain('H8')
      expect(entry?.emits).toContain('save')
      expect(entry?.emits).toContain('completed')
      expect(entry?.component).toBeDefined()
    })

    it('isHtmlComponentType 识别 h8-right-of-use-assets', () => {
      expect(isHtmlComponentType(COMPONENT_TYPE)).toBe(true)
    })

    it('getRendererEntry 返回正确 entry', () => {
      const entry = getRendererEntry(COMPONENT_TYPE)
      expect(entry).toBeDefined()
      expect(entry?.componentType).toBe(COMPONENT_TYPE)
    })

    it('组件 lazy 加载定义存在（defineAsyncComponent）', () => {
      const entry = HTML_RENDERER_REGISTRY.get(COMPONENT_TYPE)
      expect(entry?.component).toBeDefined()
      // lazy component 是一个函数或对象
      expect(typeof entry?.component === 'function' || typeof entry?.component === 'object').toBe(true)
    })

    it('contextProps 策略为 standard', () => {
      const entry = getRendererEntry(COMPONENT_TYPE)
      expect(entry?.contextProps).toBe('standard')
    })
  })

  describe('VALID_COMPONENT_TYPES 契约', () => {
    it('后端 wp_classification_service.py 包含 h8-right-of-use-assets', () => {
      const servicePath = path.resolve(
        __dirname,
        '../../../../../../backend/app/services/wp_classification_service.py'
      )
      const content = fs.readFileSync(servicePath, 'utf-8')
      expect(content).toContain('"h8-right-of-use-assets"')
    })
  })

  describe('wp_code_overrides 契约', () => {
    let overrides: Record<string, string>

    // H8/H8A/H8-1~H8-14 共16个映射
    const EXPECTED_WP_CODES = [
      'H8',
      'H8A',
      'H8-1',
      'H8-2',
      'H8-3',
      'H8-4',
      'H8-5',
      'H8-6',
      'H8-7',
      'H8-8',
      'H8-9',
      'H8-10',
      'H8-11',
      'H8-12',
      'H8-13',
      'H8-14',
      // 两个披露 sheet 的映射（短码 + 源模板中文 tab 名各一份）。
      // 2026-07-30：`wp_code_overrides.json` 已提交 20 条映射，而本文件当时仍写死 16
      // → 计数断言长期为红。补进期望清单而**不是**放宽计数，守卫依旧有约束力。
      'H8-disc-L',
      'H8-disc-S',
      'H8-附注披露信息（上市公司）',
      'H8-附注披露信息（国企）',
    ]

    beforeAll(() => {
      const overridesPath = path.resolve(
        __dirname,
        '../../../../../../backend/app/data/wp_code_overrides.json'
      )
      overrides = JSON.parse(fs.readFileSync(overridesPath, 'utf-8'))
    })

    it.each(EXPECTED_WP_CODES)(
      '%s 映射为 h8-right-of-use-assets',
      (wpCode) => {
        expect(overrides[wpCode]).toBe(COMPONENT_TYPE)
      }
    )

    it('h8-right-of-use-assets 的 wp_code 映射与期望清单完全一致（不多不少）', () => {
      const actualMappings = Object.entries(overrides)
        .filter(([, v]) => v === COMPONENT_TYPE)
        .map(([k]) => k)
      // 双向断言：既不许漏（漏了该 sheet 挂不上组件），也不许多（多了会把别的底稿抢过来）
      expect([...actualMappings].sort()).toEqual([...EXPECTED_WP_CODES].sort())
      expect(actualMappings).toHaveLength(EXPECTED_WP_CODES.length)
    })
  })

  describe('RENDERER_DISPATCH 契约', () => {
    it('后端 wp_render_strategies __init__.py 包含 h8-right-of-use-assets 分发', () => {
      const initPath = path.resolve(
        __dirname,
        '../../../../../../backend/app/routers/wp_render_strategies/__init__.py'
      )
      const content = fs.readFileSync(initPath, 'utf-8')
      // 验证 RENDERER_DISPATCH dict 中有 h8-right-of-use-assets key
      expect(content).toContain('"h8-right-of-use-assets"')
      // 验证 render 函数已导入
      expect(content).toContain('_h8_right_of_use_assets')
    })

    it('后端 _h8_right_of_use_assets.py render策略文件存在', () => {
      const renderFile = path.resolve(
        __dirname,
        '../../../../../../backend/app/routers/wp_render_strategies/_h8_right_of_use_assets.py'
      )
      expect(fs.existsSync(renderFile)).toBe(true)
    })
  })
})
