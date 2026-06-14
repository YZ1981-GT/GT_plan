/**
 * 附注 per-table guidance 显示逻辑单测 + 属性测试
 *
 * 覆盖 spec note-per-table-guidance Phase 2：
 * - 2.1/2.4 activeTableGuidance 降级逻辑：per-table 优先 → 章节级 guidance_text 降级
 * - 2.3 dismiss 粒度：`note_section:tabIdx`，关闭一个 Tab 不影响另一个
 *
 * Validates: Requirements R3
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  resolveActiveTableGuidance,
  guidanceDismissKey,
  isGuidanceVisible,
} from '@/utils/noteGuidance'

describe('resolveActiveTableGuidance — per-table 优先 / 章节级降级', () => {
  it('per-table guidance 非空时优先返回表格 guidance', () => {
    const result = resolveActiveTableGuidance(
      { guidance: '（注：该表特有提示）' },
      { note_section: '八、1', guidance_text: '章节级提示' },
    )
    expect(result).toBe('（注：该表特有提示）')
  })

  it('per-table guidance 缺省时降级到章节级 guidance_text', () => {
    const result = resolveActiveTableGuidance(
      { guidance: undefined },
      { note_section: '八、1', guidance_text: '章节级提示' },
    )
    expect(result).toBe('章节级提示')
  })

  it('per-table guidance 为纯空白时降级到章节级（trim 判定）', () => {
    const result = resolveActiveTableGuidance(
      { guidance: '   \n  ' },
      { note_section: '八、1', guidance_text: '章节级提示' },
    )
    expect(result).toBe('章节级提示')
  })

  it('per-table guidance 为 null 时降级到章节级', () => {
    const result = resolveActiveTableGuidance(
      { guidance: null },
      { guidance_text: '章节级提示' },
    )
    expect(result).toBe('章节级提示')
  })

  it('两者皆空返回空串', () => {
    expect(resolveActiveTableGuidance({ guidance: '' }, { guidance_text: '' })).toBe('')
    expect(resolveActiveTableGuidance(null, null)).toBe('')
    expect(resolveActiveTableGuidance(undefined, undefined)).toBe('')
  })

  it('单表章节（无 per-table guidance）行为不变：始终走章节级降级', () => {
    // 模拟单表场景：activeTableData 没有 guidance 字段
    const singleTable = { headers: ['项目', '期末余额'], rows: [] } as any
    const result = resolveActiveTableGuidance(singleTable, {
      note_section: '八、5',
      guidance_text: '单表章节的章节级提示',
    })
    expect(result).toBe('单表章节的章节级提示')
  })

  /**
   * 属性：只要 per-table guidance 含非空白字符，结果必然 === per-table guidance，
   * 与章节级 guidance_text 取值无关（优先级不变量）。
   */
  it('(属性) per-table 非空白 → 结果恒等于 per-table，与章节级无关', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1 }).filter((s) => s.trim().length > 0),
        fc.string(),
        (tableG, sectionG) => {
          const r = resolveActiveTableGuidance(
            { guidance: tableG },
            { guidance_text: sectionG },
          )
          expect(r).toBe(tableG)
        },
      ),
      { numRuns: 20 },
    )
  })

  /**
   * 属性：per-table 为空白/缺省 → 结果恒等于章节级 guidance_text（或''），
   * 即降级路径稳定。
   */
  it('(属性) per-table 空白/缺省 → 结果恒等于章节级降级值', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('', '   ', '\n\t', null, undefined),
        fc.string(),
        (blankTableG, sectionG) => {
          const r = resolveActiveTableGuidance(
            { guidance: blankTableG as any },
            { guidance_text: sectionG },
          )
          expect(r).toBe(sectionG || '')
        },
      ),
      { numRuns: 20 },
    )
  })
})

describe('dismiss 粒度 — section:tabIdx 各 Tab 独立', () => {
  it('guidanceDismissKey 拼接 note_section 与 tabIdx', () => {
    expect(guidanceDismissKey('八、1', '0')).toBe('八、1:0')
    expect(guidanceDismissKey('八、1', 1)).toBe('八、1:1')
    expect(guidanceDismissKey(null, '0')).toBe(':0')
    expect(guidanceDismissKey(undefined, 2)).toBe(':2')
  })

  it('关闭一个 Tab 不影响同章节另一个 Tab', () => {
    const dismissed = new Set<string>()
    const guidance = '（提示：某些表的提示）'
    const sec = '八、1'

    // 初始两 Tab 均可见
    expect(isGuidanceVisible(guidance, sec, '0', dismissed)).toBe(true)
    expect(isGuidanceVisible(guidance, sec, '1', dismissed)).toBe(true)

    // 关闭 Tab 0
    dismissed.add(guidanceDismissKey(sec, '0'))

    // Tab 0 被关闭，Tab 1 仍可见
    expect(isGuidanceVisible(guidance, sec, '0', dismissed)).toBe(false)
    expect(isGuidanceVisible(guidance, sec, '1', dismissed)).toBe(true)
  })

  it('不同章节同 tabIdx 互不影响', () => {
    const dismissed = new Set<string>()
    const guidance = '提示'
    dismissed.add(guidanceDismissKey('八、1', '0'))

    expect(isGuidanceVisible(guidance, '八、1', '0', dismissed)).toBe(false)
    // 不同章节同样是 tab 0，应仍可见
    expect(isGuidanceVisible(guidance, '八、2', '0', dismissed)).toBe(true)
  })

  it('guidance 为空白时即便未关闭也不显示', () => {
    const dismissed = new Set<string>()
    expect(isGuidanceVisible('', '八、1', '0', dismissed)).toBe(false)
    expect(isGuidanceVisible('   ', '八、1', '0', dismissed)).toBe(false)
  })

  /**
   * 属性：对任意一组被关闭的 (section, tab) 键集合，
   * isGuidanceVisible 当且仅当 guidance 非空白 且 当前键不在集合中 时为 true。
   */
  it('(属性) 可见性 = 非空白 ∧ 当前键未被关闭', () => {
    fc.assert(
      fc.property(
        fc.string(),
        fc.string({ minLength: 1, maxLength: 6 }),
        fc.integer({ min: 0, max: 9 }),
        fc.boolean(),
        (guidance, sec, tab, preDismiss) => {
          const dismissed = new Set<string>()
          if (preDismiss) dismissed.add(guidanceDismissKey(sec, String(tab)))

          const visible = isGuidanceVisible(guidance, sec, String(tab), dismissed)
          const expected = !!guidance.trim() && !preDismiss
          expect(visible).toBe(expected)
        },
      ),
      { numRuns: 30 },
    )
  })
})
