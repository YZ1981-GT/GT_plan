/**
 * E1-1「从四表库带入未审数」守卫
 *
 * 三条设计约束（对应 spec Requirements 2.4 / 2.7 / Task 10）：
 * 1. `found === false` 的槽整槽跳过 —— 「本项目无此科目」≠「该科目为 0」
 *    （`finance_co` / `digital` 按准则解释15号是可增设项目，多数项目没有）
 * 2. 已有值且与四表不同 → 进 `conflicts` 交调用方确认，**不静默覆盖**
 * 3. 写入目标必须是**跨 sheet 聚合键**，且这些键与 `useE1Adjudication` 里
 *    `getVal(...)` 读的键**逐字一致** —— 写 `E1-adj-*` 只会静默无效（审定表读不到）
 *
 * 反向自检：从 `useE1Adjudication.ts` 源码抽出它真正读的跨 sheet 键集合，
 * 与本模块声明的绑定表交叉比对 —— 任一侧改名另一侧必红。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import {
  E1_SLOT_CROSS_SHEET_KEYS,
  E1_SLOT_ORDER,
  describeE1PrefillPlan,
  normalizeE1AdjudicationPrefill,
  planE1AdjudicationPrefill,
  resolveE1PrefillWrites,
  type E1AdjudicationPrefill,
} from '../e1AdjudicationPrefill'

const COMPOSABLE = resolve(__dirname, '../useE1Adjudication.ts')

function fullPrefill(): E1AdjudicationPrefill {
  return {
    cash: { opening: 100, closing: 120, accountCode: '1001', accountCodes: ['1001'], found: true },
    bank: { opening: 900, closing: 950, accountCode: '1002', accountCodes: ['1002'], found: true },
    other: { opening: 10, closing: 12, accountCode: '1012', accountCodes: ['1012'], found: true },
    // 本项目没有这两个科目（准则解释15号「可增设」）
    finance_co: { opening: 0, closing: 0, accountCode: '', accountCodes: [], found: false },
    digital: { opening: 0, closing: 0, accountCode: '', accountCodes: [], found: false },
  }
}

/** 全空读取器 */
const readBlank = () => null

describe('planE1AdjudicationPrefill', () => {
  it('空表：命中槽的期初/期末全部进 writes，未命中槽进 skippedSlots', () => {
    const plan = planE1AdjudicationPrefill(fullPrefill(), readBlank)
    // cash 1+1、bank 2+2（本金 + 银行机构）、other 1+1 = 8
    expect(plan.writes).toHaveLength(8)
    expect(plan.conflicts).toHaveLength(0)
    expect(plan.skippedSlots.map((s) => s.slotKey)).toEqual(['finance_co', 'digital'])
  })

  it('🔴 found=false 的槽绝不写 0（「无此科目」不能伪装成「已核实为零」）', () => {
    const plan = planE1AdjudicationPrefill(fullPrefill(), readBlank)
    const ids = plan.writes.map((w) => w.itemId)
    expect(ids).not.toContain('E1-bank-detail-finance-total-unaudited')
    expect(ids).not.toContain('E1-digital-total-unaudited')
    expect(ids).not.toContain('E1-digital-opening-unaudited')
  })

  it('found=true 但金额为 0 时仍然写（0 是核实结果，与「无科目」不同）', () => {
    const p = fullPrefill()
    p.digital = { opening: 0, closing: 0, accountCode: '1012.09', accountCodes: ['1012.09'], found: true }
    const plan = planE1AdjudicationPrefill(p, readBlank)
    const ids = plan.writes.map((w) => w.itemId)
    expect(ids).toContain('E1-digital-total-unaudited')
    expect(plan.writes.find((w) => w.itemId === 'E1-digital-total-unaudited')?.value).toBe('0')
  })

  it('已有值且不同 → conflicts；相等 → 幂等不写', () => {
    const store: Record<string, string> = {
      'E1-cash-detail-total-unaudited': '999',   // 不同 → conflict
      'E1-cash-detail-opening-unaudited': '100', // 相等 → 跳过
    }
    const plan = planE1AdjudicationPrefill(fullPrefill(), (id) => store[id] ?? null)
    expect(plan.conflicts.map((c) => c.itemId)).toEqual(['E1-cash-detail-total-unaudited'])
    expect(plan.conflicts[0].current).toBe(999)
    expect(plan.conflicts[0].numeric).toBe(120)
    expect(plan.writes.map((w) => w.itemId)).not.toContain('E1-cash-detail-opening-unaudited')
    expect(plan.writes.map((w) => w.itemId)).not.toContain('E1-cash-detail-total-unaudited')
  })

  it('容差 0.005：分位以内视为相等', () => {
    const store: Record<string, string> = { 'E1-cash-detail-total-unaudited': '120.004' }
    const plan = planE1AdjudicationPrefill(fullPrefill(), (id) => store[id] ?? null)
    expect(plan.conflicts).toHaveLength(0)
  })

  it('空串 / 空白视为未填（不是「已录入 0」）', () => {
    const store: Record<string, string> = { 'E1-cash-detail-total-unaudited': '   ' }
    const plan = planE1AdjudicationPrefill(fullPrefill(), (id) => store[id] ?? null)
    expect(plan.writes.map((w) => w.itemId)).toContain('E1-cash-detail-total-unaudited')
  })

  it('非数字旧值按冲突处理（不静默覆盖脏数据）', () => {
    const store: Record<string, string> = { 'E1-cash-detail-total-unaudited': 'N/A' }
    const plan = planE1AdjudicationPrefill(fullPrefill(), (id) => store[id] ?? null)
    expect(plan.conflicts.map((c) => c.itemId)).toContain('E1-cash-detail-total-unaudited')
  })

  it('prefill 整体缺失 → 空计划（不崩、不写任何键）', () => {
    const plan = planE1AdjudicationPrefill(normalizeE1AdjudicationPrefill(undefined), readBlank)
    expect(plan.writes).toHaveLength(0)
    expect(plan.conflicts).toHaveLength(0)
    expect(plan.skippedSlots).toHaveLength(E1_SLOT_ORDER.length)
  })

  it('纯函数：同输入同输出', () => {
    const a = planE1AdjudicationPrefill(fullPrefill(), readBlank)
    const b = planE1AdjudicationPrefill(fullPrefill(), readBlank)
    expect(a).toEqual(b)
  })
})

describe('resolveE1PrefillWrites', () => {
  const store: Record<string, string> = { 'E1-cash-detail-total-unaudited': '999' }
  const plan = planE1AdjudicationPrefill(fullPrefill(), (id) => store[id] ?? null)

  it('fill-blank（默认）不含冲突项 —— 已录入数据永不被覆盖', () => {
    const w = resolveE1PrefillWrites(plan)
    expect(w.map((x) => x.itemId)).not.toContain('E1-cash-detail-total-unaudited')
    expect(w).toHaveLength(plan.writes.length)
  })

  it('overwrite 才含冲突项', () => {
    const w = resolveE1PrefillWrites(plan, 'overwrite')
    expect(w.map((x) => x.itemId)).toContain('E1-cash-detail-total-unaudited')
    expect(w).toHaveLength(plan.writes.length + plan.conflicts.length)
  })
})

describe('describeE1PrefillPlan（中文化摘要）', () => {
  it('如实说明补填数、冲突数与「本项目无此科目」的槽', () => {
    const text = describeE1PrefillPlan(planE1AdjudicationPrefill(fullPrefill(), readBlank))
    expect(text).toContain('补填 8 项')
    expect(text).toContain('存放财务公司款项')
    expect(text).toContain('数字货币')
    expect(text).toContain('本项目无此科目')
  })

  it('无事可做时给明确文案而不是空串', () => {
    const text = describeE1PrefillPlan({ writes: [], conflicts: [], skippedSlots: [] })
    expect(text.length).toBeGreaterThan(0)
    expect(text).toContain('无需带入')
  })
})

describe('🔴 跨 sheet 键与 useE1Adjudication 交叉锁死', () => {
  const src = readFileSync(COMPOSABLE, 'utf-8')

  /** 抽 composable 里 `getVal('...')` 读的所有跨 sheet 聚合键 */
  const readKeys = new Set(
    [...src.matchAll(/getVal\(\s*['"`]([^'"`]+)['"`]\s*\)/g)].map((m) => m[1]),
  )

  it('反向自检：确实从 composable 抽到了跨 sheet 键（否则断言空转）', () => {
    expect(readKeys.size).toBeGreaterThan(8)
    expect(readKeys.has('E1-cash-detail-total-unaudited')).toBe(true)
  })

  it('绑定表里每个键都是 composable 真正会读的键', () => {
    const declared: string[] = []
    for (const b of Object.values(E1_SLOT_CROSS_SHEET_KEYS)) {
      declared.push(...b.openingKeys, ...b.endingKeys)
    }
    // 5 槽 ×（期初 + 期末），其中 bank 双写「本金」与「银行机构存款」两行 → 2+4+2+2+2 = 12
    expect(declared.length).toBe(12)
    for (const key of declared) {
      expect(readKeys.has(key), `${key} 不在 useE1Adjudication 的读取键集里 → 带入后审定表读不到`).toBe(true)
    }
  })

  it('🔴 绑定表不得写成 E1-adj-* 前缀（那些键审定表未审数列不读）', () => {
    for (const b of Object.values(E1_SLOT_CROSS_SHEET_KEYS)) {
      for (const key of [...b.openingKeys, ...b.endingKeys]) {
        expect(key.startsWith('E1-adj-'), `${key} 用了 E1-adj- 前缀`).toBe(false)
      }
    }
  })

  it('composable 暴露了 applyFourTablePrefill 且显式提交这些键（flushSave 只收 E1-adj-）', () => {
    expect(src).toContain('applyFourTablePrefill')
    // flushSave 的过滤条件仍只收 E1-adj-（故跨 sheet 键必须另行提交）
    expect(src).toMatch(/startsWith\(['"]E1-adj-['"]\)/)
    // applyFourTablePrefill 内必须真的 await 保存
    const body = src.slice(src.indexOf('async function applyFourTablePrefill'))
    expect(body.slice(0, 900)).toContain('debouncedSave')
  })

  it('槽顺序覆盖全部绑定（不漏槽）', () => {
    expect([...E1_SLOT_ORDER].sort()).toEqual(Object.keys(E1_SLOT_CROSS_SHEET_KEYS).sort())
  })
})
