/**
 * htmlRendererRegistry 单测 — V3 收尾 2026-05-28
 *
 * 验证：
 *  1. registry 注册了所有 13 个真实 HTML 组件类型（不含 skip placeholder）
 *  2. HTML_RENDERER_ROUTE_SET 含 14 个（13 + skip）
 *  3. icon / label / emits 字段非空
 *  4. D 5 子模式共享同一组件（GtDForm）
 *  5. isHtmlComponentType / getRendererEntry / getSheetIcon 行为正确
 */
import { describe, it, expect } from 'vitest'

import {
  HTML_RENDERER_REGISTRY,
  HTML_COMPONENT_TYPE_SET,
  HTML_RENDERER_ROUTE_SET,
  PLACEHOLDER_ICONS,
  isHtmlComponentType,
  getRendererEntry,
  getSheetIcon,
  type HtmlComponentType,
} from '../htmlRendererRegistry'

describe('htmlRendererRegistry — 注册表完整性', () => {
  it('注册表包含全部真实 HTML 组件类型（不含 skip）', () => {
    const expected: HtmlComponentType[] = [
      'a1-dashboard',
      'a2-adjustment-console',
      'a3-consolidation-console',
      'a-program-console',
      'b-index',
      'c-note-table',
      'd-form-table',
      'd-form-paragraph',
      'd-form-qa',
      'd-form-confirmation',
      'd-form-review',
      'e-control-test',
      'h-static-doc',
      'custom',
      'audit-sheet',
      'bad-debt-sheet',
      'cf-verification',
      'procedure-table',
      'report-analysis',
      'misstatement-summary',
      'review-checklist',
      'word-template',
      'independence-signing',
      'wp-popup-signing',
      'a1-11-signing-form',
      'audit-legend',
      'checklist-table',
      'analytical-review',
      'kam-workpaper',
      'goodwill-impairment',
      'segment-report',
      'contingent-liability',
      'discontinued-operations',
      'misstatement-workpaper',
      'a14-3-workbook',
      'a17-summary',
      'regulatory-letter',
      'a10-bundle',
      'a11-bundle',
      'a12-bundle',
      'a15-bundle',
      'confirmation-summary',
      'confirmation-entity-verify',
      'confirmation-followup',
      'confirmation-diff-reconcile',
      'confirmation-alternative-d05',
      'confirmation-alternative-d06',
      'confirmation-diff-checklist',
      'confirmation-fraud-risk',
      'confirmation-reliability',
      'b50-risk-assessment',
      'b22a-control-matrix',
      'b22b-deficiency-evaluation',
      'b23-process-control',
      'b30-group-audit',
      'b2-bundle',
      'b13-bundle',
      'b19-bundle',
      'b51-bundle',
      'f2-stocktake-bundle',
      'c-control-test',
      'd1-notes-receivable',
      'd2-accounts-receivable',
      'a1-12-dual-checklist',
      'a1-15-disclosure-checklist',
      'a16-bundle',
      'a17-bundle',
      'a1-17-corresponding-data',
      'a17-6-closing-meeting',
      'a18-1-regulatory-submission',
      'a18-2-regulatory-communication',
      'a8-1-other-info-representation',
      'a11-1-subsequent-events-inquiry',
      'a17-3-consultation-record',
      'a17-3-1-consultation-execution',
      'a17-4-disagreement-record',
      'a17-7-independence-declaration',
      'a9-1-deficiency-letter',
      'a9-2-deficiency-letter-governance',
      'a27-1-it-audit-memo',
      'a12-1-legal-confirmation',
      'a10-1-governance-communication',
      'a17-1-audit-summary',
      'a17-2-1-kam',
      'a5-1-cashflow-audit',
      'a3-8-goodwill-impairment',
      'b1-4-due-diligence-report',
      'd4-operating-revenue',
      'd3-prepaid-accounts',
      'd5-receivables-financing',
      'd6-contract-assets',
      'd7-contract-liabilities',
      'e1-monetary-fund',
      'review-bundle',
    ]
    expect(HTML_RENDERER_REGISTRY.size).toBe(expected.length)
    for (const ct of expected) {
      expect(HTML_RENDERER_REGISTRY.has(ct)).toBe(true)
    }
    expect(HTML_RENDERER_REGISTRY.has('skip' as any)).toBe(false)
  })

  it('每个条目 icon / label / emits 字段非空', () => {
    for (const [ct, entry] of HTML_RENDERER_REGISTRY) {
      expect(entry.componentType).toBe(ct)
      expect(entry.icon).toBeTruthy()
      expect(entry.label).toBeTruthy()
      expect(entry.label.length).toBeGreaterThan(0)
      expect(Array.isArray(entry.emits)).toBe(true)
      expect(entry.component).toBeDefined()
    }
  })

  it('D 5 子模式共享同一 component 引用（lazy GtDForm）', () => {
    const dEntries = ['d-form-table', 'd-form-paragraph', 'd-form-qa', 'd-form-confirmation', 'd-form-review']
      .map((ct) => HTML_RENDERER_REGISTRY.get(ct as HtmlComponentType))
    const components = dEntries.map((e) => e?.component)
    // 所有 D 子模式 component 引用一致
    const first = components[0]
    expect(first).toBeDefined()
    for (const comp of components) {
      expect(comp).toBe(first)
    }
  })

  it('A/B/C/E/H 各使用独立 component', () => {
    const entries = ['a-program-console', 'b-index', 'c-note-table', 'e-control-test', 'h-static-doc']
      .map((ct) => HTML_RENDERER_REGISTRY.get(ct as HtmlComponentType)?.component)
    const unique = new Set(entries)
    expect(unique.size).toBe(5)
  })
})

describe('htmlRendererRegistry — emit 列表', () => {
  it('A 程序控制台仅 emit save', () => {
    expect(HTML_RENDERER_REGISTRY.get('a-program-console')?.emits).toEqual(['save'])
  })

  it('C 附注表 emit 5 个事件（含穿透/同步/标准切换）', () => {
    const emits = HTML_RENDERER_REGISTRY.get('c-note-table')?.emits ?? []
    expect(emits).toContain('save')
    expect(emits).toContain('subtable-toggle')
    expect(emits).toContain('standard-switch')
    expect(emits).toContain('sync-to-disclosure-notes')
    expect(emits).toContain('jump-to-reference')
  })

  it('E 控制测试 emit 4 个事件（含 trimming/conclusion/step）', () => {
    const emits = HTML_RENDERER_REGISTRY.get('e-control-test')?.emits ?? []
    expect(emits).toContain('save')
    expect(emits).toContain('trigger-procedure-trimming-suggestion')
    expect(emits).toContain('conclusion-change')
    expect(emits).toContain('step-advance')
  })

  it('H 静态文档无 emit（只读）', () => {
    expect(HTML_RENDERER_REGISTRY.get('h-static-doc')?.emits).toEqual([])
  })

  it('checklist-table 核对表仅 emit save', () => {
    const entry = HTML_RENDERER_REGISTRY.get('checklist-table')
    expect(entry).toBeDefined()
    expect(entry?.icon).toBe('✅')
    expect(entry?.label).toBe('核对表')
    expect(entry?.emits).toEqual(['save'])
  })

  it('analytical-review 分析性复核 emit save + 图标/标签正确', () => {
    const entry = HTML_RENDERER_REGISTRY.get('analytical-review')
    expect(entry).toBeDefined()
    expect(entry?.icon).toBe('📊')
    expect(entry?.label).toBe('分析性复核')
    expect(entry?.emits).toEqual(['save'])
  })
})

describe('htmlRendererRegistry — 路由集合', () => {
  it('HTML_COMPONENT_TYPE_SET 仅含 registry 注册类型（不含 skip）', () => {
    // 数量随注册表增长，断言 = registry 条目数（动态派生，避免硬编码 stale）
    expect(HTML_COMPONENT_TYPE_SET.size).toBe(HTML_RENDERER_REGISTRY.size)
    expect(HTML_COMPONENT_TYPE_SET.has('a-program-console')).toBe(true)
    expect(HTML_COMPONENT_TYPE_SET.has('audit-legend')).toBe(true)
    expect(HTML_COMPONENT_TYPE_SET.has('skip' as any)).toBe(false)
  })

  it('HTML_RENDERER_ROUTE_SET = registry + skip', () => {
    expect(HTML_RENDERER_ROUTE_SET.size).toBe(HTML_COMPONENT_TYPE_SET.size + 1)
    expect(HTML_RENDERER_ROUTE_SET.has('a-program-console')).toBe(true)
    expect(HTML_RENDERER_ROUTE_SET.has('skip')).toBe(true)
    expect(HTML_RENDERER_ROUTE_SET.has('univer')).toBe(false)
  })

  it('PLACEHOLDER_ICONS 含 univer + skip 不含 HTML 类', () => {
    expect(PLACEHOLDER_ICONS.univer).toBeDefined()
    expect(PLACEHOLDER_ICONS.skip).toBeDefined()
    expect((PLACEHOLDER_ICONS as any)['a-program-console']).toBeUndefined()
  })
})

describe('htmlRendererRegistry — 工具函数', () => {
  it('isHtmlComponentType 命中 / 未命中', () => {
    expect(isHtmlComponentType('a-program-console')).toBe(true)
    expect(isHtmlComponentType('h-static-doc')).toBe(true)
    expect(isHtmlComponentType('checklist-table')).toBe(true)
    expect(isHtmlComponentType('univer')).toBe(false)
    expect(isHtmlComponentType('skip')).toBe(false)
    expect(isHtmlComponentType('unknown-type')).toBe(false)
  })

  it('getRendererEntry 已注册类型返回 entry / 未注册返回 undefined', () => {
    expect(getRendererEntry('a-program-console')).toBeDefined()
    expect(getRendererEntry('univer')).toBeUndefined()
    expect(getRendererEntry('skip')).toBeUndefined()
    expect(getRendererEntry('unknown-type')).toBeUndefined()
  })

  it('getSheetIcon HTML 类型从 registry / placeholder 类型从 PLACEHOLDER_ICONS / fallback 默认图标', () => {
    expect(getSheetIcon('a-program-console')).toBe('📋')
    expect(getSheetIcon('c-note-table')).toBe('📝')
    expect(getSheetIcon('e-control-test')).toBe('🧪')
    expect(getSheetIcon('univer')).toBe('📊')
    expect(getSheetIcon('skip')).toBe('⏭️')
    expect(getSheetIcon('unknown')).toBe('📄')
  })
})


describe('htmlRendererRegistry — D3 预收账款注册契约', () => {
  it('d3-prepaid-accounts 已注册且配置正确', () => {
    const entry = HTML_RENDERER_REGISTRY.get('d3-prepaid-accounts')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('d3-prepaid-accounts')
    expect(entry?.icon).toBe('💰')
    expect(entry?.label).toBe('D3 预收账款')
    expect(entry?.emits).toContain('save')
    expect(entry?.emits).toContain('completed')
    expect(entry?.contextProps).toBe('standard')
    expect(entry?.component).toBeDefined()
  })

  it('isHtmlComponentType 识别 d3-prepaid-accounts', () => {
    expect(isHtmlComponentType('d3-prepaid-accounts')).toBe(true)
  })
})
