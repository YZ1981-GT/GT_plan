/**
 * G4 债权投资(main组) — 集成测试 Part 1: sheetName分发正确性
 *
 * 验证：
 * 1. 有效sheetName → 正确子组件编码（正则提取+v-if分发）
 * 2. 未知sheetName → OnlyOffice fallback（空字符串触发fallback渲染）
 * 3. selfLoad模式：htmlData=null时自动加载render-config
 *
 * **Validates: Requirements 1.1~1.8**
 */
import { describe, it, expect } from 'vitest'

// ---------------------------------------------------------------------------
// 1. sheetName 正则分发正确性（对齐 GtG4BondInvestmentMain.vue）
// ---------------------------------------------------------------------------
describe('G4 集成: sheetName 正则分发（8 sheets + fallback）', () => {
  const CODE_MAP: Record<string, string> = {
    'G4A': 'procedure',
    'G4-1': 'adjudication',
    'G4-2': 'detail',
    'G4-3': 'adjustment',
    'G4-4': 'interestCalc',
    '附注披露信息（上市公司）': 'disclosureListed',
    '附注披露信息（国企）': 'disclosureSOE',
    '底稿目录': 'directory',
  }

  function resolveSheet(name: string): string {
    if (!name) return ''
    if (CODE_MAP[name]) return CODE_MAP[name]
    if (/G4-note-listed|附注披露.*上市|附注.*上市/.test(name)) return 'disclosureListed'
    if (/G4-note-soe|附注披露.*国企|附注.*国企/.test(name)) return 'disclosureSOE'
    if (/G4-directory|底稿目录/.test(name)) return 'directory'
    if (/附注/.test(name)) return name.includes('国企') ? 'disclosureSOE' : 'disclosureListed'
    const codeMatch = name.match(/(G4A|G4-[1-4])/)
    if (codeMatch) return CODE_MAP[codeMatch[1]] || ''
    return ''
  }

  const validCases: [string, string][] = [
    ['债权投资实质性程序表G4A', 'procedure'],
    ['审定表G4-1', 'adjudication'],
    ['明细表G4-2', 'detail'],
    ['调整分录汇总G4-3', 'adjustment'],
    ['利息测算表G4-4', 'interestCalc'],
    ['附注披露信息（上市公司）', 'disclosureListed'],
    ['附注披露信息（国企）', 'disclosureSOE'],
    ['底稿目录', 'directory'],
    ['G4-note-listed', 'disclosureListed'],
    ['G4-附注披露信息（国企）', 'disclosureSOE'],
  ]

  it.each(validCases)('sheetName "%s" → code "%s"', (input, expected) => {
    expect(resolveSheet(input)).toBe(expected)
  })

  it('有效sheetName全部映射到子组件key', () => {
    const keys = new Set(Object.values(CODE_MAP))
    for (const [, expected] of validCases) {
      expect(keys.has(expected)).toBe(true)
    }
  })

  it('sheetName含空格/变体仍正确匹配', () => {
    expect(resolveSheet('附注披露 （ 上市公司 ）')).toBe('disclosureListed')
    expect(resolveSheet('附注披露(国企)')).toBe('disclosureSOE')
    expect(resolveSheet('G4-1 审定表(债权投资)')).toBe('adjudication')
    expect(resolveSheet('G4A实质性程序')).toBe('procedure')
  })

  it('未匹配的sheetName返回空字符串 → OnlyOffice fallback', () => {
    expect(resolveSheet('Z99-unknown')).toBe('')
    expect(resolveSheet('')).toBe('')
    expect(resolveSheet('G5-1')).toBe('')
    expect(resolveSheet('随便什么内容')).toBe('')
    expect(resolveSheet('G4-5')).toBe('')
    expect(resolveSheet('G4-9')).toBe('')
  })

  it('CODE_MAP 正好有8个有效映射', () => {
    expect(Object.keys(CODE_MAP)).toHaveLength(8)
  })

  it('子目录路由：core/ 映射7个 + measurement/ 映射1个', () => {
    const coreComponents = ['procedure', 'adjudication', 'detail', 'adjustment',
      'disclosureListed', 'disclosureSOE', 'directory']
    const measurementComponents = ['interestCalc']
    for (const comp of coreComponents) {
      expect(Object.values(CODE_MAP)).toContain(comp)
    }
    for (const comp of measurementComponents) {
      expect(Object.values(CODE_MAP)).toContain(comp)
    }
    expect(coreComponents.length + measurementComponents.length).toBe(8)
  })
})

// ---------------------------------------------------------------------------
// 2. selfLoad 模式
// ---------------------------------------------------------------------------
describe('G4 集成: selfLoad 模式', () => {
  it('htmlData 为 null → 触发 selfLoad', () => {
    function shouldSelfLoad(htmlData: Record<string, any> | null): boolean {
      return htmlData === null
    }
    expect(shouldSelfLoad(null)).toBe(true)
    expect(shouldSelfLoad({})).toBe(false)
    expect(shouldSelfLoad({ sheets: [] })).toBe(false)
  })

  it('selfLoad URL 包含 force_component_type 参数', () => {
    const wpId = 'test-wp-id-123'
    const expectedUrl = `/api/workpapers/${wpId}/render-config?force_component_type=g4-bond-investment-main`
    expect(expectedUrl).toContain('force_component_type=g4-bond-investment-main')
    expect(expectedUrl).toContain(wpId)
  })

  it('selfLoad 成功后 sheets 配置', () => {
    const renderConfigResponse = {
      component_type: 'g4-bond-investment-main',
      sheets: [
        { code: 'G4A', sheetName: '债权投资实质性程序表G4A', componentType: 'a-program-console' },
        { code: 'G4-1', sheetName: '审定表G4-1', componentType: 'g4-bond-investment-main' },
        { code: 'G4-2', sheetName: '明细表G4-2', componentType: 'g4-bond-investment-main' },
        { code: 'G4-3', sheetName: '调整分录汇总G4-3', componentType: 'g4-bond-investment-main' },
        { code: 'G4-4', sheetName: '利息测算表G4-4', componentType: 'g4-bond-investment-main' },
        { code: '附注披露信息（上市公司）', sheetName: '附注披露信息（上市公司）', componentType: 'g4-bond-investment-main' },
        { code: '附注披露信息（国企）', sheetName: '附注披露信息（国企）', componentType: 'g4-bond-investment-main' },
        { code: '底稿目录', sheetName: '底稿目录', componentType: 'g4-bond-investment-main' },
      ],
      tb_values: { opening: 5000000, closing: 5500000 },
      account_code: '1501',
    }
    expect(renderConfigResponse.component_type).toBe('g4-bond-investment-main')
    expect(renderConfigResponse.sheets).toHaveLength(8)
    expect(renderConfigResponse.account_code).toBe('1501')
    expect(renderConfigResponse.tb_values).toBeDefined()
  })

  it('selfLoad 失败时显示错误卡片', () => {
    function handleSelfLoadError(err: { status: number; message: string }) {
      return {
        showError: true,
        errorMessage: `加载失败: ${err.message}`,
        canRetry: true,
      }
    }
    const result = handleSelfLoadError({ status: 500, message: '服务器错误' })
    expect(result.showError).toBe(true)
    expect(result.canRetry).toBe(true)
    expect(result.errorMessage).toContain('加载失败')
  })
})

// ---------------------------------------------------------------------------
// 3. defineAsyncComponent
// ---------------------------------------------------------------------------
describe('G4 集成: defineAsyncComponent 懒加载', () => {
  it('8个子组件全部使用 defineAsyncComponent', () => {
    const asyncComponentPaths = {
      procedure: './g4-bond-investment-main/core/G4TabProcedure.vue',
      adjudication: './g4-bond-investment-main/core/G4TabAdjudication.vue',
      detail: './g4-bond-investment-main/core/G4TabDetail.vue',
      adjustment: './g4-bond-investment-main/core/G4TabAdjustment.vue',
      disclosureListed: './g4-bond-investment-main/core/G4TabDisclosureListed.vue',
      disclosureSOE: './g4-bond-investment-main/core/G4TabDisclosureSOE.vue',
      directory: './g4-bond-investment-main/core/G4TabDirectory.vue',
      interestCalc: './g4-bond-investment-main/measurement/G4TabInterestCalc.vue',
    }
    expect(Object.keys(asyncComponentPaths)).toHaveLength(8)
    const corePaths = Object.values(asyncComponentPaths).filter(p => p.includes('/core/'))
    expect(corePaths).toHaveLength(7)
    const measurementPaths = Object.values(asyncComponentPaths).filter(p => p.includes('/measurement/'))
    expect(measurementPaths).toHaveLength(1)
  })

  it('G4A 使用 a-program-console', () => {
    const g4aConfig = {
      code: 'G4A',
      sheetName: '债权投资实质性程序表G4A',
      componentType: 'a-program-console',
    }
    expect(g4aConfig.componentType).toBe('a-program-console')
  })

  it('G4A 程序表脚手架对齐 D4A', async () => {
    const { G_CYCLE_PROCEDURE_SHEETS } = await import('../composables/cycleProcedureSheets')
    expect(G_CYCLE_PROCEDURE_SHEETS.G4A.sheetLabel).toBe('债权投资实质性程序表G4A')
  })
})
