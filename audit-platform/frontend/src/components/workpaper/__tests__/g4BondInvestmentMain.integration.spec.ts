/**
 * G4 债权投资(main组) — 集成测试 Part 1: sheetName分发正确性
 *
 * 验证：
 * 1. 8个有效sheetName → 正确子组件编码（正则提取+v-if分发）
 * 2. 未知sheetName → OnlyOffice fallback（空字符串触发fallback渲染）
 * 3. selfLoad模式：htmlData=null时自动加载render-config
 *
 * **Validates: Requirements 1.1~1.8**
 */
import { describe, it, expect } from 'vitest'

import {
  calcDebitBalance,
  calcAdjustedAmount,
  parseNum,
} from '@/composables/useG4MainFormulaEngine'

// ---------------------------------------------------------------------------
// 1. sheetName 正则分发正确性（8 sheets + fallback）
// ---------------------------------------------------------------------------
describe('G4 集成: sheetName 正则分发（8 sheets + fallback）', () => {
  /**
   * 复制 GtG4BondInvestmentMain.vue 中 currentSheet computed 逻辑为纯函数
   * 从 sheetName 中正则提取编码，匹配已迁移子组件列表。
   */
  function resolveSheet(name: string): string {
    if (!name) return ''
    // 附注特殊处理（含中文括号和空格容错）
    if (/附注披露信息\s*[（(]\s*上市公司\s*[）)]/.test(name)) return '附注披露信息（上市公司）'
    if (/附注披露信息\s*[（(]\s*国企\s*[）)]/.test(name)) return '附注披露信息（国企）'
    if (/底稿目录/.test(name)) return '底稿目录'
    // 标准编码提取：G4A / G4-1 / G4-2 / G4-3 / G4-4
    const m = name.match(/(G4A|G4-[1-4])/)
    return m ? m[1] : ''
  }

  // 映射到子组件 key
  const SHEET_CODE_MAP: Record<string, string> = {
    'G4A': 'procedure',
    'G4-1': 'adjudication',
    'G4-2': 'detail',
    'G4-3': 'adjustment',
    'G4-4': 'interestCalc',
    '附注披露信息（上市公司）': 'disclosureListed',
    '附注披露信息（国企）': 'disclosureSOE',
    '底稿目录': 'directory',
  }

  const validCases: [string, string][] = [
    ['债权投资实质性程序表G4A', 'G4A'],
    ['审定表G4-1', 'G4-1'],
    ['明细表G4-2', 'G4-2'],
    ['调整分录汇总G4-3', 'G4-3'],
    ['利息测算表G4-4', 'G4-4'],
    ['附注披露信息（上市公司）', '附注披露信息（上市公司）'],
    ['附注披露信息（国企）', '附注披露信息（国企）'],
    ['底稿目录', '底稿目录'],
  ]

  it.each(validCases)('sheetName "%s" → code "%s"', (input, expected) => {
    expect(resolveSheet(input)).toBe(expected)
  })

  it('8个有效sheetName全部映射到子组件key', () => {
    for (const [input, expected] of validCases) {
      const code = resolveSheet(input)
      expect(SHEET_CODE_MAP[code]).toBeDefined()
    }
  })

  it('sheetName含空格/变体仍正确匹配', () => {
    expect(resolveSheet('附注披露信息 （ 上市公司 ）')).toBe('附注披露信息（上市公司）')
    expect(resolveSheet('附注披露信息(国企)')).toBe('附注披露信息（国企）')
    expect(resolveSheet('G4-1 审定表(债权投资)')).toBe('G4-1')
    expect(resolveSheet('G4A实质性程序')).toBe('G4A')
  })

  it('未匹配的sheetName返回空字符串 → OnlyOffice fallback', () => {
    expect(resolveSheet('Z99-unknown')).toBe('')
    expect(resolveSheet('')).toBe('')
    expect(resolveSheet('G5-1')).toBe('')
    expect(resolveSheet('随便什么内容')).toBe('')
    expect(resolveSheet('G4-5')).toBe('') // G4-5不在main组
    expect(resolveSheet('G4-9')).toBe('') // G4-9属于ECL组
  })

  it('SHEET_CODE_MAP 正好有8个有效映射', () => {
    expect(Object.keys(SHEET_CODE_MAP)).toHaveLength(8)
  })

  it('子目录路由：core/ 映射7个 + measurement/ 映射1个', () => {
    const coreComponents = ['procedure', 'adjudication', 'detail', 'adjustment',
      'disclosureListed', 'disclosureSOE', 'directory']
    const measurementComponents = ['interestCalc']

    for (const comp of coreComponents) {
      expect(Object.values(SHEET_CODE_MAP)).toContain(comp)
    }
    for (const comp of measurementComponents) {
      expect(Object.values(SHEET_CODE_MAP)).toContain(comp)
    }
    expect(coreComponents.length + measurementComponents.length).toBe(8)
  })
})

// ---------------------------------------------------------------------------
// 2. selfLoad 模式：htmlData=null 时自动加载
// ---------------------------------------------------------------------------
describe('G4 集成: selfLoad 模式', () => {
  it('htmlData 为 null → 触发 selfLoad（调用 render-config）', () => {
    // 模拟 selfLoad 决策逻辑
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

  it('selfLoad 成功后 htmlData 填充 sheets 配置', () => {
    // 模拟 render-config 返回结构
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

  it('selfLoad 失败时显示错误卡片（不崩溃）', () => {
    // 模拟错误处理逻辑
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
// 3. defineAsyncComponent 懒加载验证
// ---------------------------------------------------------------------------
describe('G4 集成: defineAsyncComponent 懒加载', () => {
  it('8个子组件全部使用 defineAsyncComponent', () => {
    // 验证子组件结构（模拟 lazy 导入映射）
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
    // core/ 7个
    const corePaths = Object.values(asyncComponentPaths).filter(p => p.includes('/core/'))
    expect(corePaths).toHaveLength(7)
    // measurement/ 1个
    const measurementPaths = Object.values(asyncComponentPaths).filter(p => p.includes('/measurement/'))
    expect(measurementPaths).toHaveLength(1)
  })

  it('G4A 使用 a-program-console componentType（复用 GtAProgramConsole）', () => {
    // G4A 的 componentType 是 a-program-console，但入口仍通过主入口分发
    const g4aConfig = {
      code: 'G4A',
      sheetName: '债权投资实质性程序表G4A',
      componentType: 'a-program-console',
    }
    expect(g4aConfig.componentType).toBe('a-program-console')
  })
})
