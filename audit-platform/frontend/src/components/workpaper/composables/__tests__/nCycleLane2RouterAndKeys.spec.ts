/**
 * nCycleLane2RouterAndKeys.spec.ts — N1 / N3 共享路由采纳 + N1-1 持久化键改模板行 key
 *
 * spec: n1-n3-host-inline-router-and-shared-adoption · Task 2 / 8
 *
 * 1. 等价性：对源模板**全部真实 sheet 名**（按原始字面量，含「表的{码}」形态），
 *    新路由的分发键与原宿主内联实现逐一相等 —— 换实现不换分发契约。
 * 2. BP-10 的防护价值：披露 tab 名尾部带 wp_code 时，原实现判成明细表，新实现仍判披露。
 * 3. N1-1：写入键 = 模板行 key（A7~A13）；旧位置键只读兼容。
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'

import { isN1HtmlSheet, normalizeN1SheetName } from '../n1SheetRouting'
import { isN3HtmlSheet, normalizeN3SheetName } from '../n3SheetRouting'
import {
  N1_ADJUDICATION_CATEGORIES,
  N1_ADJUDICATION_TEMPLATE_ROW,
  n1AdjudicationItemId,
  useN1Adjudication,
} from '../useN1Adjudication'
import { useN1LossCheck } from '../useN1LossCheck'

vi.mock('element-plus', () => ({
  ElMessageBox: { confirm: vi.fn(async () => 'confirm') },
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

// ─── 原宿主内联实现（逐字搬来作等价性基准） ───────────────────────────────
function legacyN1(name: string): string {
  if (name === 'GT_Custom') return 'skip'
  const codeMatch = name.match(/N1-[1-5]/)
  if (codeMatch) return codeMatch[0]
  if (name.match(/N1A/) || name.includes('程序表')) return 'procedure'
  if (name.includes('上市公司')) return 'disclosure-listed'
  if (name.includes('国企') || name.includes('国有企业')) return 'disclosure-soe'
  if (name.includes('底稿目录') || name === 'N1' || name === '') return 'index'
  return name
}
function legacyN1Html(s: string): boolean {
  return /^N1-\d+$/.test(s) || s === 'index' || s === 'disclosure-listed' || s === 'disclosure-soe'
}
function legacyN3(name: string): string {
  const m = name.match(/(N3A|N3-\d+|N3)/)
  if (m) return m[1]
  if (name.includes('底稿目录')) return '底稿目录'
  return name
}
function legacyN3Html(s: string): boolean {
  return /^N3-\d+$/.test(s) || s === 'N3' || s === '底稿目录'
}

// 源模板真实 sheet 名（原始字面量，见 slice authoritative_templates）
const N1_SHEETS = [
  '底稿目录', '递延所得税资产审计程序表的N1A', '递延所得税资产审定表N1-1',
  '附注披露信息（上市公司）', '附注披露信息（国企）', '递延所得税资产明细表N1-2',
  '调整分录汇总N1-3', '递延所得税资产（负债）测算表N1-4',
  '可用以后年度税前利润弥补的亏损检查表的N1-5', 'GT_Custom', '', 'N1',
]
const N3_SHEETS = [
  '底稿目录', '递延所得税负债审计程序表的N3A', '递延所得税负债审定表N3-1',
  '递延所得税负债明细表N3-2', '调整分录汇总表N3-3', 'GT_Custom', 'N3',
]

describe('N1 路由（Task 2）', () => {
  it.each(N1_SHEETS)('等价：%s', (name) => {
    const k = normalizeN1SheetName(name)
    expect(k).toBe(legacyN1(name))
    expect(isN1HtmlSheet(k)).toBe(legacyN1Html(legacyN1(name)))
  })

  it('BP-10 防护：披露 tab 名带 wp_code 后缀时仍判为披露（原实现会判成明细表）', () => {
    const name = '附注披露信息（国企）N1-2'
    expect(legacyN1(name)).toBe('N1-2')
    expect(normalizeN1SheetName(name)).toBe('disclosure-soe')
  })

  it('国企多写法全认（含繁体）', () => {
    expect(normalizeN1SheetName('附注披露信息（國企）')).toBe('disclosure-soe')
    expect(normalizeN1SheetName('附注披露信息（国有企业）')).toBe('disclosure-soe')
  })
})

describe('N3 路由（Task 2）', () => {
  it.each(N3_SHEETS)('等价：%s', (name) => {
    const k = normalizeN3SheetName(name)
    expect(k).toBe(legacyN3(name))
    expect(isN3HtmlSheet(k)).toBe(legacyN3Html(legacyN3(name)))
  })

  it('N3 无披露 sheet：含「附注」的 tab 不渲染空白 HTML，落 OO 兜底', () => {
    const k = normalizeN3SheetName('附注披露信息（上市公司）')
    expect(isN3HtmlSheet(k)).toBe(false)
  })
})

describe('N1-1 持久化键（Task 8）', () => {
  function make(initial: Record<string, any>) {
    const all = ref(new Map<string, any>(Object.entries(initial)))
    const saved: Record<string, any> = {}
    const formData: any = {
      debouncedSave: (id: string, v: any) => { saved[id] = v },
      getField: () => null,
      setField: vi.fn(),
      writebackTB: vi.fn(),
    }
    const adj = useN1Adjudication({ allResponses: all as any, formData, wpId: ref('w'), projectId: ref('p') } as any)
    return { adj, saved }
  }

  it('7 类 ↔ 模板行 A7~A13 一一对应，键不含数组下标', () => {
    expect(Object.values(N1_ADJUDICATION_TEMPLATE_ROW)).toEqual(['A7', 'A8', 'A9', 'A10', 'A11', 'A12', 'A13'])
    for (const c of N1_ADJUDICATION_CATEGORIES) {
      expect(n1AdjudicationItemId(c)).toMatch(/^N1-1-adj-A\d+$/)
    }
  })

  it('旧位置键数据仍能读出（只读兼容）', () => {
    const { adj } = make({ 'N1-1-adj-1': { conclusion: JSON.stringify({ endUnadjusted: 88 }) } })
    expect(adj.rows.value[1].category).toBe('可抵扣亏损')
    expect(adj.rows.value[1].endUnadjusted).toBe(88)
  })

  it('新键优先于旧键', () => {
    const { adj } = make({
      'N1-1-adj-1': { conclusion: JSON.stringify({ endUnadjusted: 1 }) },
      'N1-1-adj-A8': { conclusion: JSON.stringify({ endUnadjusted: 2 }) },
    })
    expect(adj.rows.value[1].endUnadjusted).toBe(2)
  })

  it('写入只走新键（模板行 key），不再写位置键', () => {
    const { adj, saved } = make({})
    adj.removeAdjustment('可抵扣亏损', 'end', 'aje')
    expect(Object.keys(saved)).toContain('N1-1-adj-A8')
    expect(Object.keys(saved).some((k) => /^N1-1-adj-\d+$/.test(k))).toBe(false)
  })
})


describe('N1-5 leadRows 运行时契约（真浏览器缺陷回归）', () => {
  function make(leadPayload?: any) {
    const entries: Array<[string, any]> = leadPayload
      ? [['N1-5-lead-rows', { conclusion: JSON.stringify(leadPayload) }]]
      : []
    return useN1LossCheck({
      allResponses: ref(new Map(entries)) as any,
      formData: {
        debouncedSave: vi.fn(),
        getField: vi.fn(),
        setField: vi.fn(),
      } as any,
      auditYear: ref(2025),
    })
  }

  it('leadRows 是按业务键读取的字典，不是数组（旧实现打开 N1-5 即 undefined.bookAmount）', () => {
    const loss = make()
    expect(Array.isArray(loss.leadRows.value)).toBe(false)
    expect(loss.leadRows.value.retainedEarnings).toMatchObject({ bookAmount: 0, auditAdjustment: 0, auditedAmount: 0 })
    expect(loss.leadRows.value.deductibleLoss).toMatchObject({ bookAmount: 0, auditAdjustment: 0, auditedAmount: 0 })
  })

  it('旧版不完整 lead payload 逐字段补默认值，不产生 NaN', () => {
    const loss = make({ retainedEarnings: { bookAmount: 12 } })
    expect(loss.leadRows.value.retainedEarnings.auditedAmount).toBe(12)
    expect(loss.leadRows.value.deductibleLoss.auditedAmount).toBe(0)
    expect(Number.isNaN(loss.leadRows.value.retainedEarnings.auditedAmount)).toBe(false)
  })

  it('不同 composable 实例不共享可变默认对象', () => {
    const a = make()
    const b = make()
    a.updateLead('retainedEarnings', 'bookAmount', 99)
    expect(a.leadRows.value.retainedEarnings.bookAmount).toBe(99)
    expect(b.leadRows.value.retainedEarnings.bookAmount).toBe(0)
  })
})
