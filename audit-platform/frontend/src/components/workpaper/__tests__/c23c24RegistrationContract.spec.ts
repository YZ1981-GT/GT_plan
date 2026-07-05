/**
 * C23/C24 会计分录测试 — 前端注册契约测试
 *
 * Spec: .kiro/specs/c23-c24-journal-entry-testing/ Task 2.3
 * Validates: Requirements 1.1, 1.3
 *
 * 验证：
 *  1. c23-journal-entry-control 已注册于 htmlRendererRegistry
 *  2. c24-journal-entry-detail 已注册于 htmlRendererRegistry
 *  3. 两类型在 HTML_COMPONENT_TYPE_SET 中存在
 *  4. isHtmlComponentType 正确识别
 *  5. 配置字段（icon / label / contextProps / emits）正确
 */
import { describe, it, expect } from 'vitest'

import {
  HTML_RENDERER_REGISTRY,
  HTML_COMPONENT_TYPE_SET,
  isHtmlComponentType,
  getRendererEntry,
} from '../htmlRendererRegistry'

describe('C23/C24 注册契约 — htmlRendererRegistry', () => {
  // ─── C23 c23-journal-entry-control ──────────────────────────────────────────

  it('c23-journal-entry-control 已注册于 HTML_RENDERER_REGISTRY', () => {
    expect(HTML_RENDERER_REGISTRY.has('c23-journal-entry-control')).toBe(true)
  })

  it('c23-journal-entry-control 在 HTML_COMPONENT_TYPE_SET 中存在', () => {
    expect(HTML_COMPONENT_TYPE_SET.has('c23-journal-entry-control')).toBe(true)
  })

  it('isHtmlComponentType 识别 c23-journal-entry-control', () => {
    expect(isHtmlComponentType('c23-journal-entry-control')).toBe(true)
  })

  it('c23-journal-entry-control 配置字段正确', () => {
    const entry = getRendererEntry('c23-journal-entry-control')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('c23-journal-entry-control')
    expect(entry?.icon).toBeTruthy()
    expect(entry?.label).toContain('C23')
    expect(entry?.contextProps).toBe('standard')
    expect(entry?.emits).toContain('save')
    expect(entry?.emits).toContain('completed')
    expect(entry?.component).toBeDefined()
  })

  // ─── C24 c24-journal-entry-detail ──────────────────────────────────────────

  it('c24-journal-entry-detail 已注册于 HTML_RENDERER_REGISTRY', () => {
    expect(HTML_RENDERER_REGISTRY.has('c24-journal-entry-detail')).toBe(true)
  })

  it('c24-journal-entry-detail 在 HTML_COMPONENT_TYPE_SET 中存在', () => {
    expect(HTML_COMPONENT_TYPE_SET.has('c24-journal-entry-detail')).toBe(true)
  })

  it('isHtmlComponentType 识别 c24-journal-entry-detail', () => {
    expect(isHtmlComponentType('c24-journal-entry-detail')).toBe(true)
  })

  it('c24-journal-entry-detail 配置字段正确', () => {
    const entry = getRendererEntry('c24-journal-entry-detail')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('c24-journal-entry-detail')
    expect(entry?.icon).toBeTruthy()
    expect(entry?.label).toContain('C24')
    expect(entry?.contextProps).toBe('standard')
    expect(entry?.emits).toContain('save')
    expect(entry?.emits).toContain('completed')
    expect(entry?.component).toBeDefined()
  })
})
