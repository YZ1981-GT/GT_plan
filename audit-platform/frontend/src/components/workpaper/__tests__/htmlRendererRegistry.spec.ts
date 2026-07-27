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
      'confirmation-alternative-f05',
      'confirmation-alternative-f06',
      'confirmation-diff-securities',
      'confirmation-alternative-g06',
      'confirmation-alternative-h05',
      'confirmation-alternative-k05',
      'confirmation-alternative-k06',
      'confirmation-alternative-l05',
      'h10-asset-disposal-income',
      'g14-credit-impairment-loss',
      'g13-fair-value-changes',
      'g12-net-hedge-gains',
      'g11-investment-income',
      'g10-trading-financial-liabilities',
      'g9-other-noncurrent-financial',
      'g8-other-equity-instruments',
      'g7-long-term-equity-subsidiary',
      'g7-long-term-equity-method',
      'g7-long-term-equity-main',
      'g6-other-bond-investment-ecl',
      'g6-other-bond-investment-sppi',
      'g6-other-bond-investment-main',
      'g5-long-term-receivable',
      'g4-bond-investment-ecl',
      'g4-bond-investment-sppi',
      'g4-bond-investment-main',
      'g3-dividend-receivable',
      'g2-interest-receivable',
      'g1-trading-financial-assets',
      'f5-cost-of-sales',
      'f4-accounts-payable',
      'f3-notes-payable',
      'f2-inventory-valuation-impairment',
      'f2-inventory-special',
      'f2-inventory-main',
      'f1-prepayment',
      'confirmation-diff-checklist',
      'confirmation-fraud-risk',
      'confirmation-reliability',
      'b50-risk-assessment',
      'b22a-control-matrix',
      'b22b-deficiency-evaluation',
      'b22c-design-effectiveness',
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
      'c1-entity-level-control',
      'c22-itgc-bundle',
      'c23-journal-entry-control',
      'c24-journal-entry-detail',
      'c25-internal-audit-reliance',
      'c26-info-processing-control',
      'l1-short-term-loans',
      'l2-interest-payable',
      'l3-long-term-loans',
      'l4-bonds-payable',
      'l5-long-term-payables',
      'l6-special-payables',
      'l7-other-noncurrent-liabilities',
      'l8-financial-expenses',
      'm1-dividends-payable',
      'm2-paid-in-capital',
      'm3-treasury-stock',
      'm4-capital-reserve',
      'm5-surplus-reserve',
      'm6-retained-earnings',
      'm7-special-reserve',
      'm8-general-risk-reserve',
      'm9-other-comprehensive-income',
      'm10-other-equity-instruments',
      'n1-deferred-tax-assets',
      'n2-taxes-payable',
      'n3-deferred-tax-liabilities',
      'n4-taxes-and-surcharges',
      'n5-income-tax-expense',
      's3-policy-change',
      's4-nonmonetary-exchange',
      's5-debt-restructuring',
      's6-fund-occupation',
      's12-cpa-expert',
      's13-mgmt-expert',
      's14-accounting-estimate',
      's15-eps-roe',
      's20-revenue-deduction',
      's21-data-asset',
      's32-fraud-bundle',
      's33-ann14-bundle',
      's34-ipo-bundle',
      's35-refinance-bundle',
      'h1-fixed-assets',
      'h5-oil-gas-assets',
      'h2-construction-in-progress',
      'h3-investment-property',
      'h4-engineering-materials',
      'h6-asset-disposal-clearing',
      'h8-right-of-use-assets',
      'h9-lease-liabilities',
      'i1-intangible-assets',
      'i2-development-expenditure',
      'i3-goodwill',
      'i4-long-term-prepaid',
      'i5-other-noncurrent-assets',
      'i6-research-development-expense',
      'j1-employee-compensation',
      'j2-defined-benefit-plan',
      'j3-share-based-payment',
      'k1-other-receivables',
      'k2-other-current-assets',
      'k3-other-payables',
      'k4-other-current-liabilities',
      'k5-provisions',
      'k6-held-for-sale',
      'k7-deferred-income',
      'k8-selling-expenses',
      'k9-admin-expenses',
      'k10-other-income',
      'k11-asset-impairment-loss',
      'k12-non-operating-income',
      'k13-non-operating-expense',
      'review-bundle',
    ]
    expect(HTML_RENDERER_REGISTRY.size).toBeGreaterThanOrEqual(expected.length)
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

  it('HTML_RENDERER_ROUTE_SET = registry + skip + confirmation-hub', () => {
    // 两个 placeholder 不在 registry 中但需走 GtWpRenderer：
    // - skip：内部分支渲染 SkippedSheetPlaceholder
    // - confirmation-hub：D0/E0/F0/G0/H0/K0/L0 函证枢纽的 workbook 级类型，
    //   其各 sheet（X0A/X0-1~X0-8）自身 componentType 已注册，按 per-sheet 分发
    expect(HTML_RENDERER_ROUTE_SET.size).toBe(HTML_COMPONENT_TYPE_SET.size + 2)
    expect(HTML_RENDERER_ROUTE_SET.has('a-program-console')).toBe(true)
    expect(HTML_RENDERER_ROUTE_SET.has('skip')).toBe(true)
    expect(HTML_RENDERER_ROUTE_SET.has('confirmation-hub')).toBe(true)
    expect(HTML_RENDERER_ROUTE_SET.has('univer')).toBe(false)
    // confirmation-hub 仍不在 registry（不渲染组件，仅路由判定）
    expect(HTML_COMPONENT_TYPE_SET.has('confirmation-hub' as any)).toBe(false)
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


describe('htmlRendererRegistry — H0-5 固定资产循环替代程序注册契约', () => {
  it('confirmation-alternative-h05 已注册且映射 GtConfirmationAlternativeH05', () => {
    const entry = HTML_RENDERER_REGISTRY.get('confirmation-alternative-h05')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('confirmation-alternative-h05')
    expect(entry?.icon).toBe('🔄')
    expect(entry?.label).toBe('替代程序(固定资产循环)')
    expect(entry?.emits).toContain('save')
    expect(entry?.component).toBeDefined()
  })

  it('isHtmlComponentType 识别 confirmation-alternative-h05', () => {
    expect(isHtmlComponentType('confirmation-alternative-h05')).toBe(true)
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


describe('htmlRendererRegistry — H2 在建工程注册契约', () => {
  it('h2-construction-in-progress 已注册且配置正确', () => {
    const entry = HTML_RENDERER_REGISTRY.get('h2-construction-in-progress')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('h2-construction-in-progress')
    expect(entry?.icon).toBe('🚧')
    expect(entry?.label).toBe('H2 在建工程')
    expect(entry?.emits).toContain('save')
    expect(entry?.emits).toContain('completed')
    expect(entry?.contextProps).toBe('standard')
    expect(entry?.component).toBeDefined()
  })

  it('isHtmlComponentType 识别 h2-construction-in-progress', () => {
    expect(isHtmlComponentType('h2-construction-in-progress')).toBe(true)
  })

  it('getRendererEntry 返回 h2-construction-in-progress 条目', () => {
    const entry = getRendererEntry('h2-construction-in-progress')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('h2-construction-in-progress')
  })
})

describe('htmlRendererRegistry — H3 投资性房地产注册契约', () => {
  it('h3-investment-property 已注册且配置正确', () => {
    const entry = HTML_RENDERER_REGISTRY.get('h3-investment-property')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('h3-investment-property')
    expect(entry?.icon).toBe('🏠')
    expect(entry?.label).toBe('H3 投资性房地产')
    expect(entry?.emits).toContain('save')
    expect(entry?.emits).toContain('completed')
    expect(entry?.contextProps).toBe('standard')
    expect(entry?.component).toBeDefined()
  })

  it('isHtmlComponentType 识别 h3-investment-property', () => {
    expect(isHtmlComponentType('h3-investment-property')).toBe(true)
  })

  it('getRendererEntry 返回 h3-investment-property 条目', () => {
    const entry = getRendererEntry('h3-investment-property')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('h3-investment-property')
  })

  it('h3-investment-property 组件可被懒加载（defineAsyncComponent）', () => {
    const entry = HTML_RENDERER_REGISTRY.get('h3-investment-property')
    expect(entry?.component).toBeDefined()
    // component 应为函数或对象（defineAsyncComponent 结果）
    expect(typeof entry?.component === 'function' || typeof entry?.component === 'object').toBe(true)
  })
})


describe('htmlRendererRegistry — H4 工程物资注册契约', () => {
  it('h4-engineering-materials 已注册且配置正确', () => {
    const entry = HTML_RENDERER_REGISTRY.get('h4-engineering-materials')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('h4-engineering-materials')
    expect(entry?.icon).toBe('🧱')
    expect(entry?.label).toBe('H4 工程物资')
    expect(entry?.emits).toContain('save')
    expect(entry?.emits).toContain('completed')
    expect(entry?.contextProps).toBe('standard')
    expect(entry?.component).toBeDefined()
  })

  it('isHtmlComponentType 识别 h4-engineering-materials', () => {
    expect(isHtmlComponentType('h4-engineering-materials')).toBe(true)
  })

  it('getRendererEntry 返回 h4-engineering-materials 条目', () => {
    const entry = getRendererEntry('h4-engineering-materials')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('h4-engineering-materials')
  })

  it('h4-engineering-materials 组件可被懒加载（defineAsyncComponent）', () => {
    const entry = HTML_RENDERER_REGISTRY.get('h4-engineering-materials')
    expect(entry?.component).toBeDefined()
    // component 应为函数或对象（defineAsyncComponent 结果）
    expect(typeof entry?.component === 'function' || typeof entry?.component === 'object').toBe(true)
  })
})


describe('htmlRendererRegistry — I6 研发费用注册契约', () => {
  it('i6-research-development-expense 已注册且配置正确', () => {
    const entry = HTML_RENDERER_REGISTRY.get('i6-research-development-expense')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('i6-research-development-expense')
    expect(entry?.icon).toBe('🔬')
    expect(entry?.label).toBe('I6 研发费用')
    expect(entry?.emits).toContain('save')
    expect(entry?.emits).toContain('completed')
    expect(entry?.emits).toContain('navigate-sheet')
    expect(entry?.contextProps).toBe('standard')
    expect(entry?.component).toBeDefined()
  })

  it('isHtmlComponentType 识别 i6-research-development-expense', () => {
    expect(isHtmlComponentType('i6-research-development-expense')).toBe(true)
  })

  it('getRendererEntry 返回 i6-research-development-expense 条目', () => {
    const entry = getRendererEntry('i6-research-development-expense')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('i6-research-development-expense')
  })

  it('i6-research-development-expense 组件可被懒加载（defineAsyncComponent）', () => {
    const entry = HTML_RENDERER_REGISTRY.get('i6-research-development-expense')
    expect(entry?.component).toBeDefined()
    // component 应为函数或对象（defineAsyncComponent 结果）
    expect(typeof entry?.component === 'function' || typeof entry?.component === 'object').toBe(true)
  })
})


describe('htmlRendererRegistry — K7 递延收益注册契约', () => {
  it('k7-deferred-income 已注册且配置正确', () => {
    const entry = HTML_RENDERER_REGISTRY.get('k7-deferred-income')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('k7-deferred-income')
    expect(entry?.icon).toBe('📋')
    expect(entry?.label).toBe('K7 递延收益')
    expect(entry?.emits).toContain('save')
    expect(entry?.emits).toContain('completed')
    expect(entry?.emits).toContain('navigate-sheet')
    expect(entry?.contextProps).toBe('standard')
    expect(entry?.component).toBeDefined()
  })

  it('isHtmlComponentType 识别 k7-deferred-income', () => {
    expect(isHtmlComponentType('k7-deferred-income')).toBe(true)
  })

  it('getRendererEntry 返回 k7-deferred-income 条目', () => {
    const entry = getRendererEntry('k7-deferred-income')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('k7-deferred-income')
  })

  it('k7-deferred-income 组件可被懒加载（defineAsyncComponent）', () => {
    const entry = HTML_RENDERER_REGISTRY.get('k7-deferred-income')
    expect(entry?.component).toBeDefined()
    // component 应为函数或对象（defineAsyncComponent 结果）
    expect(typeof entry?.component === 'function' || typeof entry?.component === 'object').toBe(true)
  })
})


describe('htmlRendererRegistry — K10 其他收益注册契约', () => {
  it('k10-other-income 已注册且配置正确', () => {
    const entry = HTML_RENDERER_REGISTRY.get('k10-other-income')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('k10-other-income')
    expect(entry?.icon).toBe('🏛️')
    expect(entry?.label).toBe('K10 其他收益')
    expect(entry?.emits).toContain('save')
    expect(entry?.emits).toContain('completed')
    expect(entry?.emits).toContain('navigate-sheet')
    expect(entry?.contextProps).toBe('standard')
    expect(entry?.component).toBeDefined()
  })

  it('isHtmlComponentType 识别 k10-other-income', () => {
    expect(isHtmlComponentType('k10-other-income')).toBe(true)
  })

  it('getRendererEntry 返回 k10-other-income 条目', () => {
    const entry = getRendererEntry('k10-other-income')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('k10-other-income')
  })

  it('k10-other-income 组件可被懒加载（defineAsyncComponent）', () => {
    const entry = HTML_RENDERER_REGISTRY.get('k10-other-income')
    expect(entry?.component).toBeDefined()
    // component 应为函数或对象（defineAsyncComponent 结果）
    expect(typeof entry?.component === 'function' || typeof entry?.component === 'object').toBe(true)
  })
})


describe('htmlRendererRegistry — N4 税金及附加注册契约', () => {
  it('n4-taxes-and-surcharges 已注册且配置正确', () => {
    const entry = HTML_RENDERER_REGISTRY.get('n4-taxes-and-surcharges')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('n4-taxes-and-surcharges')
    expect(entry?.icon).toBe('🧾')
    expect(entry?.label).toBe('N4 税金及附加')
    expect(entry?.emits).toContain('save')
    expect(entry?.emits).toContain('completed')
    expect(entry?.contextProps).toBe('standard')
    expect(entry?.component).toBeDefined()
  })

  it('isHtmlComponentType 识别 n4-taxes-and-surcharges', () => {
    expect(isHtmlComponentType('n4-taxes-and-surcharges')).toBe(true)
  })

  it('getRendererEntry 返回 n4-taxes-and-surcharges 条目', () => {
    const entry = getRendererEntry('n4-taxes-and-surcharges')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('n4-taxes-and-surcharges')
  })

  it('n4-taxes-and-surcharges 组件可被懒加载（defineAsyncComponent）', () => {
    const entry = HTML_RENDERER_REGISTRY.get('n4-taxes-and-surcharges')
    expect(entry?.component).toBeDefined()
    expect(typeof entry?.component === 'function' || typeof entry?.component === 'object').toBe(true)
  })
})
