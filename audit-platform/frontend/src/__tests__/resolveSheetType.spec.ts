/**
 * resolveSheetType 前端测试
 *
 * 覆盖 Task 2.4:
 * - 优先级: schema 显式(sheet_type) > 前端启发式 > 'unknown'
 * - Property 2: schema 显式值不被启发式覆盖
 * - Property 5: 缺失 sheet_type 时回退启发式
 *
 * Validates: Requirements 1.2, 1.3, 5.1, 5.2
 */

import { describe, it, expect } from 'vitest'
import { resolveSheetType, type SheetRenderConfig } from '@/composables/useWpRenderer'

function makeSheet(overrides: Partial<SheetRenderConfig> = {}): SheetRenderConfig {
  return {
    sheet_name: 'Sheet1',
    componentType: 'univer',
    schema: {},
    html_data: {},
    cross_refs: [],
    ...overrides,
  }
}

describe('resolveSheetType', () => {
  // ─── 优先级测试 ──────────────────────────────────────────────────────────

  describe('优先级: schema 显式 > 启发式 > unknown', () => {
    it('schema 显式 sheet_type 直接返回', () => {
      const sheet = makeSheet({ sheet_type: 'audit_sheet' })
      expect(resolveSheetType(sheet)).toBe('audit_sheet')
    })

    it('schema sheet_type 优先于启发式（Property 2）', () => {
      // sheet_name 含「明细」会被启发式推断为 detail_table
      // 但 schema 已标记为 disclosure，应返回 disclosure
      const sheet = makeSheet({
        sheet_name: '应收账款明细表',
        sheet_type: 'disclosure',
      })
      expect(resolveSheetType(sheet)).toBe('disclosure')
    })

    it('无 schema sheet_type 时回退启发式', () => {
      const sheet = makeSheet({ sheet_name: '应收账款审定表D1-1' })
      expect(resolveSheetType(sheet)).toBe('audit_sheet')
    })

    it('启发式也无法推断时返回 unknown', () => {
      const sheet = makeSheet({ sheet_name: 'Sheet1' })
      expect(resolveSheetType(sheet)).toBe('unknown')
    })
  })

  // ─── 启发式关键词覆盖 ────────────────────────────────────────────────────

  describe('前端启发式关键词', () => {
    const cases: [string, string][] = [
      ['应收账款审定表D1-1', 'audit_sheet'],
      ['D1-2 应收账款明细表', 'detail_table'],
      ['账龄分析表', 'analysis'],
      ['应收账款实质性程序表D2A', 'procedure'],
      ['审计调整分录', 'adjustment'],
      ['附注披露信息（上市公司）', 'disclosure'],
      ['内控了解', 'control_understanding'],
      ['控制测试', 'control_test'],
      ['函证汇总', 'confirmation_summary'],
      ['科目结论', 'conclusion'],
      ['底稿目录', 'control_panel'],
      ['科目驾驶舱', 'control_panel'],
    ]

    it.each(cases)('"%s" → %s', (name, expected) => {
      const sheet = makeSheet({ sheet_name: name })
      expect(resolveSheetType(sheet)).toBe(expected)
    })
  })

  // ─── Property 5: 缺失 sheet_type 时不破坏渲染 ────────────────────────────

  describe('迁移兼容', () => {
    it('sheet_type 为 undefined 时走启发式', () => {
      const sheet = makeSheet({
        sheet_name: '应收账款审定表D1-1',
        sheet_type: undefined,
      })
      expect(resolveSheetType(sheet)).toBe('audit_sheet')
    })

    it('空 sheet_name + 无 sheet_type 返回 unknown', () => {
      const sheet = makeSheet({ sheet_name: '', sheet_type: undefined })
      expect(resolveSheetType(sheet)).toBe('unknown')
    })
  })
})
