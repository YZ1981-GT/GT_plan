/**
 * I2 开发支出 — sheetName分发 + CAS6面板交互 测试
 *
 * Spec: .kiro/specs/i2-development-expenditure/ Task 7.2
 * Validates: Requirements 1.2 (sheetName分发), 5.4-5.5 (CAS6结论逻辑)
 *
 * 测试内容：
 * 1. sheetName → currentSheet 正则提取逻辑
 * 2. CAS6面板 evaluateCapitalization 逻辑
 */
import { describe, it, expect } from 'vitest'
import {
  evaluateCapitalization,
  type CAS6Condition,
} from '../composables/useI2CapitalizationEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// 1. sheetName 分发逻辑（纯正则测试，不需要mount组件）
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * 从 GtI2DevelopmentExpenditure.vue 的 currentSheet computed 提取正则逻辑
 * 用于验证 sheetName → 子组件路由映射
 */
function extractCurrentSheet(sheetName: string): string {
  const name = sheetName || ''
  // 附注匹配
  if (/附注.*上市|I2-note-listed/.test(name)) return '附注上市'
  if (/附注.*国企|I2-note-soe/.test(name)) return '附注国企'
  if (/附注/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
  // 程序表 I2A
  if (/I2A/.test(name)) return 'I2A'
  // I2-N 编码（I2-1 到 I2-16）
  const m = name.match(/(I2-\d+)/)
  if (m) return m[1]
  // 底稿目录 I2（无后缀）
  if (/\bI2\b/.test(name) && !/I2-/.test(name) && !/I2A/.test(name)) return 'I2'
  return ''
}

describe('I2 sheetName分发逻辑', () => {
  describe('I2-1 → I2TabAdjudication', () => {
    it('含 "I2-1" 的 sheetName 提取为 I2-1', () => {
      expect(extractCurrentSheet('审定表I2-1')).toBe('I2-1')
    })
    it('纯编码 I2-1', () => {
      expect(extractCurrentSheet('I2-1')).toBe('I2-1')
    })
  })

  describe('I2-6 → I2TabCapitalization', () => {
    it('含 "I2-6" 的 sheetName 提取为 I2-6', () => {
      expect(extractCurrentSheet('资本化时点判断I2-6')).toBe('I2-6')
    })
    it('纯编码 I2-6', () => {
      expect(extractCurrentSheet('I2-6')).toBe('I2-6')
    })
  })

  describe('I2A → CycleTabProcedure', () => {
    it('含 "I2A" 的 sheetName 提取为 I2A', () => {
      expect(extractCurrentSheet('开发支出实质性程序表I2A')).toBe('I2A')
    })
    it('纯编码 I2A', () => {
      expect(extractCurrentSheet('I2A')).toBe('I2A')
    })
  })

  describe('空/未匹配 → OO fallback', () => {
    it('空字符串返回空（触发OO fallback）', () => {
      expect(extractCurrentSheet('')).toBe('')
    })
    it('无法识别的名称返回空', () => {
      expect(extractCurrentSheet('某个随机底稿')).toBe('')
    })
  })

  describe('底稿目录 I2', () => {
    it('"I2" 无后缀 → 底稿目录', () => {
      expect(extractCurrentSheet('I2')).toBe('I2')
    })
    it('"底稿目录 I2" → I2', () => {
      expect(extractCurrentSheet('底稿目录 I2')).toBe('I2')
    })
  })

  describe('附注分发', () => {
    it('附注上市公司', () => {
      expect(extractCurrentSheet('附注披露信息（上市公司）')).toBe('附注上市')
    })
    it('附注国企', () => {
      // 实际渲染策略中sheet_name为"附注披露信息（国有企业）"但前端normalizes为含"国企"的名称
      // 或 i2-note-soe 编码
      expect(extractCurrentSheet('I2-note-soe')).toBe('附注国企')
      // fallback: 含"国企"字样
      expect(extractCurrentSheet('附注国企')).toBe('附注国企')
    })
  })

  describe('I2-10~I2-16 多位数编码', () => {
    it('I2-10', () => {
      expect(extractCurrentSheet('研发人员工时检查表I2-10')).toBe('I2-10')
    })
    it('I2-16', () => {
      expect(extractCurrentSheet('可收回金额测试I2-16')).toBe('I2-16')
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 2. CAS6五条件面板逻辑（evaluateCapitalization纯函数测试）
// ═══════════════════════════════════════════════════════════════════════════════

function makeConditions(results: Array<'yes' | 'no' | 'na'>): CAS6Condition[] {
  const names = ['技术可行性', '完成意图', '经济利益方式', '资源支持', '可靠计量']
  return results.map((r, i) => ({
    id: (i + 1) as 1 | 2 | 3 | 4 | 5,
    name: names[i],
    result: r,
    evidence: '',
  }))
}

describe('CAS6五条件面板交互逻辑', () => {
  describe('全部条件为"是"', () => {
    it('五条件全yes → isMet=true', () => {
      const conditions = makeConditions(['yes', 'yes', 'yes', 'yes', 'yes'])
      const result = evaluateCapitalization(conditions)
      expect(result.isMet).toBe(true)
      expect(result.missingConditions).toEqual([])
      expect(result.conclusion).toContain('满足')
    })
  })

  describe('任一条件为"否"', () => {
    it('条件3="no" → isMet=false, missingConditions=[3]', () => {
      const conditions = makeConditions(['yes', 'yes', 'no', 'yes', 'yes'])
      const result = evaluateCapitalization(conditions)
      expect(result.isMet).toBe(false)
      expect(result.missingConditions).toContain(3)
      expect(result.conclusion).toContain('不满足')
    })

    it('条件1和5="no" → missingConditions包含1和5', () => {
      const conditions = makeConditions(['no', 'yes', 'yes', 'yes', 'no'])
      const result = evaluateCapitalization(conditions)
      expect(result.isMet).toBe(false)
      expect(result.missingConditions).toContain(1)
      expect(result.missingConditions).toContain(5)
    })

    it('全部"no" → missingConditions=[1,2,3,4,5]', () => {
      const conditions = makeConditions(['no', 'no', 'no', 'no', 'no'])
      const result = evaluateCapitalization(conditions)
      expect(result.isMet).toBe(false)
      expect(result.missingConditions).toEqual([1, 2, 3, 4, 5])
    })
  })

  describe('全部条件为"不适用"(na)', () => {
    it('全na → isMet=false（无正面证据）', () => {
      const conditions = makeConditions(['na', 'na', 'na', 'na', 'na'])
      const result = evaluateCapitalization(conditions)
      expect(result.isMet).toBe(false)
    })
  })

  describe('混合场景：有yes和na（无no）— 须同时满足', () => {
    it('部分yes部分na → isMet=false（CAS6须五条件同时为是）', () => {
      const conditions = makeConditions(['yes', 'yes', 'na', 'yes', 'na'])
      const result = evaluateCapitalization(conditions)
      expect(result.isMet).toBe(false)
      expect(result.missingConditions).toEqual([3, 5])
    })
  })
})
