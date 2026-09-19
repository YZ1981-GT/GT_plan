/**
 * Task 24 守卫：披露主表三个无科目码行接语义槽预填（Property 35）。
 *
 * 判据分四组：
 * 1. 键名契约与真源一致性（`E1_MAIN_ROW_SLOTS` 的行 key 必须真的是 `crossKey === ''` 的行）
 * 2. 写入侧（审定表）：三值全 0 不写键 = 「不写 0」
 * 3. 读取侧（披露表）：优先级 / null 与 0 可区分 / 扣减不双算 / 合计恒等
 * 4. 反向自检：删掉预填链后三行恒空必红；扣减映射失效时合计必双算
 *
 * 🔴 断言全部落在纯函数上（不挂载组件）—— 组件层接线由 `e1MainRowPrefillWiring.spec.ts`
 *    读源码交叉锁死，两者分工不重叠。
 */
import { describe, it, expect } from 'vitest'
import {
  E1_MAIN_ROW_SLOTS,
  E1_PREFILL_ROW_KEYS,
  E1_MAIN_ROW_DEDUCTIONS,
  e1MainRowSlotKey,
  e1MainRowAmountKey,
  e1MainRowDeductionKeys,
  resolveE1MainRowAmount,
  isE1MainRowSlotPrefilled,
  isE1MainRowDeducted,
  buildE1MainRowSlotWrites,
  type E1AdjRowLike,
  type E1MainRowKeyed,
} from '../e1MainRowPrefill'
import {
  E1_MAIN_ROWS_LISTED,
  E1_MAIN_ROWS_SOE,
  e1MainRows,
  e1SummableRows,
} from '../e1DisclosureScope'

// ── helpers ───────────────────────────────────────────────────────────────────

function getterOf(map: Record<string, string | number>) {
  return (k: string) => {
    const v = map[k]
    return v === undefined ? undefined : String(v)
  }
}

function adjRow(itemKey: string, ending: number, opening = 0): E1AdjRowLike {
  return {
    itemKey,
    openingUnaudited: opening,
    openingAdjustment: 0,
    openingAudited: opening,
    endingUnaudited: ending,
    endingAdjustment: 0,
    endingAudited: ending,
  }
}

/** 复现披露表合计口径（`e1SummableRows` + `resolveE1MainRowAmount`）。 */
function totalOf(
  variant: 'listed' | 'soe',
  get: (k: string) => string | null | undefined,
): number {
  return e1SummableRows(variant).reduce(
    (sum, r) => sum + (resolveE1MainRowAmount(r, get) ?? 0),
    0,
  )
}

// ── 组 1：键名契约与真源一致性 ────────────────────────────────────────────────

describe('E1 主表槽预填 · 键名契约', () => {
  it('E1_PREFILL_ROW_KEYS 与 E1_MAIN_ROW_SLOTS 的键集完全一致且字典序冻结', () => {
    expect(E1_PREFILL_ROW_KEYS).toEqual(['accrued', 'digital', 'finance_co'])
    expect(Object.keys(E1_MAIN_ROW_SLOTS).sort()).toEqual([...E1_PREFILL_ROW_KEYS])
  })

  it('三个预填行在 listed 真源里确实是 crossKey === "" 的行', () => {
    const byKey = new Map(E1_MAIN_ROWS_LISTED.map((r) => [r.key, r]))
    for (const k of E1_PREFILL_ROW_KEYS) {
      const row = byKey.get(k)
      expect(row, `listed 真源缺少行 ${k}`).toBeTruthy()
      expect(row!.crossKey, `${k} 应无 crossKey（有的话不该走槽预填）`).toBe('')
    }
  })

  it('crossKey 为空的 listed 行 = 三个预填行 + 合计 + 备注行（无遗漏无多余）', () => {
    const blanks = E1_MAIN_ROWS_LISTED.filter((r) => !r.crossKey).map((r) => r.key)
    expect(new Set(blanks)).toEqual(
      new Set([...E1_PREFILL_ROW_KEYS, 'total', 'overseas']),
    )
  })

  it('扣减映射的被扣行必须有 crossKey，扣减源必须是预填行', () => {
    const byKey = new Map(E1_MAIN_ROWS_LISTED.map((r) => [r.key, r]))
    for (const [rowKey, slots] of Object.entries(E1_MAIN_ROW_DEDUCTIONS)) {
      expect(byKey.get(rowKey)?.crossKey, `${rowKey} 必须有 crossKey`).toBeTruthy()
      for (const s of slots) {
        expect(E1_PREFILL_ROW_KEYS).toContain(s)
      }
    }
  })

  it('扣减映射恰为 bank←finance_co / other_mf←digital（口径来自审定表科目归集）', () => {
    expect(E1_MAIN_ROW_DEDUCTIONS.bank).toEqual(['finance_co'])
    expect(E1_MAIN_ROW_DEDUCTIONS.other_mf).toEqual(['digital'])
    // accrued 不属任何科目码 ⇒ 不出现在任何扣减清单里
    const allSlots = Object.values(E1_MAIN_ROW_DEDUCTIONS).flat()
    expect(allSlots).not.toContain('accrued')
  })

  it('e1MainRowSlotKey 形态固定，非预填行返空串', () => {
    expect(e1MainRowSlotKey('finance_co')).toBe('E1-adj-slot-finance_co')
    expect(e1MainRowSlotKey('finance_co', 'opening')).toBe('E1-adj-slot-finance_co-opening')
    expect(e1MainRowSlotKey('accrued')).toBe('E1-adj-slot-accrued')
    expect(e1MainRowSlotKey('digital')).toBe('E1-adj-slot-digital')
    expect(e1MainRowSlotKey('bank')).toBe('')
    expect(e1MainRowSlotKey('total')).toBe('')
    expect(e1MainRowSlotKey('overseas')).toBe('')
  })

  it('槽键不与既有 E1-adj-total-* 键空间撞名', () => {
    for (const k of E1_PREFILL_ROW_KEYS) {
      for (const p of ['ending', 'opening'] as const) {
        const key = e1MainRowSlotKey(k, p)
        expect(key.startsWith('E1-adj-slot-')).toBe(true)
        expect(key.startsWith('E1-adj-total-')).toBe(false)
      }
    }
  })

  it('槽键仍在 flushSave 收集的 E1-adj- 前缀内（否则只改内存刷新即丢）', () => {
    for (const k of E1_PREFILL_ROW_KEYS) {
      expect(e1MainRowSlotKey(k).startsWith('E1-adj-')).toBe(true)
      expect(e1MainRowSlotKey(k, 'opening').startsWith('E1-adj-')).toBe(true)
    }
  })

  it('槽映射指向审定表 ROW_MATRIX 真实存在的 itemKey', () => {
    // 审定表 ROW_MATRIX 的 itemKey（口径真源在 useE1Adjudication）
    const matrixKeys = new Set([
      'cash', 'bank_principal', 'finance_co', 'bank_institution',
      'other_mf', 'digital', 'accrued_interest',
      'accrued_finance', 'accrued_bank', 'accrued_other', 'accrued_digital',
      'total', 'overseas', 'tb_amount', 'diff',
    ])
    for (const [rowKey, itemKey] of Object.entries(E1_MAIN_ROW_SLOTS)) {
      expect(matrixKeys.has(itemKey), `${rowKey} → ${itemKey} 不在 ROW_MATRIX 里`).toBe(true)
    }
  })

  it('accrued 映射到合计行 accrued_interest 而非某个子项', () => {
    // 源模板 E1-1 R13 = SUM(G14:G17) 四子项 ⇒ 披露主表取的是合计
    expect(E1_MAIN_ROW_SLOTS.accrued).toBe('accrued_interest')
  })
})

// ── 组 2：写入侧（审定表）「不写 0」 ─────────────────────────────────────────

describe('E1 主表槽预填 · 写入侧', () => {
  it('三值全 0 的行不产生写入（保持空白而非 0）', () => {
    const writes = buildE1MainRowSlotWrites([
      adjRow('finance_co', 0, 0),
      adjRow('digital', 0, 0),
      adjRow('accrued_interest', 0, 0),
    ])
    expect(writes).toEqual([])
  })

  it('有值的期写入、无值的期不写入（期末有期初无）', () => {
    const writes = buildE1MainRowSlotWrites([adjRow('finance_co', 1234.5, 0)])
    expect(writes).toEqual([
      { itemId: 'E1-adj-slot-finance_co', value: '1234.5' },
    ])
  })

  it('两期都有值时各写一条', () => {
    const writes = buildE1MainRowSlotWrites([adjRow('digital', 200, 100)])
    expect(writes.map((w) => w.itemId).sort()).toEqual([
      'E1-adj-slot-digital',
      'E1-adj-slot-digital-opening',
    ])
  })

  it('未审数为 0 但有调整额时仍写入（三值全 0 才算空白）', () => {
    const writes = buildE1MainRowSlotWrites([
      {
        itemKey: 'accrued_interest',
        openingUnaudited: 0, openingAdjustment: 0, openingAudited: 0,
        endingUnaudited: 0, endingAdjustment: 500, endingAudited: 500,
      },
    ])
    expect(writes).toEqual([{ itemId: 'E1-adj-slot-accrued', value: '500' }])
  })

  it('审定表缺该行时跳过而不抛', () => {
    expect(buildE1MainRowSlotWrites([])).toEqual([])
    expect(buildE1MainRowSlotWrites([adjRow('cash', 999)])).toEqual([])
  })

  it('写入顺序按 E1_PREFILL_ROW_KEYS 冻结（便于 diff 比对）', () => {
    const writes = buildE1MainRowSlotWrites([
      adjRow('digital', 3),
      adjRow('accrued_interest', 1),
      adjRow('finance_co', 2),
    ])
    expect(writes.map((w) => w.itemId)).toEqual([
      'E1-adj-slot-accrued',
      'E1-adj-slot-digital',
      'E1-adj-slot-finance_co',
    ])
  })

  it('负值如实写入（不 abs）', () => {
    const writes = buildE1MainRowSlotWrites([adjRow('finance_co', -8888.88)])
    expect(writes).toEqual([{ itemId: 'E1-adj-slot-finance_co', value: '-8888.88' }])
  })
})

// ── 组 3：读取侧（披露表） ───────────────────────────────────────────────────

describe('E1 主表槽预填 · 读取侧', () => {
  const listed = new Map(E1_MAIN_ROWS_LISTED.map((r) => [r.key, r as E1MainRowKeyed]))

  it('crossKey 优先于槽键（有 crossKey 的行不读槽）', () => {
    const row = listed.get('bank')!
    expect(e1MainRowAmountKey(row)).toBe('E1-adj-total-1002')
    expect(e1MainRowAmountKey(row, 'opening')).toBe('E1-adj-total-1002-opening')
  })

  it('无 crossKey 的行读槽键', () => {
    expect(e1MainRowAmountKey(listed.get('finance_co')!)).toBe('E1-adj-slot-finance_co')
    expect(e1MainRowAmountKey(listed.get('accrued')!, 'opening')).toBe(
      'E1-adj-slot-accrued-opening',
    )
  })

  it('合计行与备注行不读槽（返空串）', () => {
    expect(e1MainRowAmountKey(listed.get('total')!)).toBe('')
    expect(e1MainRowAmountKey(listed.get('overseas')!)).toBe('')
  })

  it('🔴 取不到值返 null 不返 0（「无此科目」与「余额为 0」可区分）', () => {
    const get = getterOf({})
    expect(resolveE1MainRowAmount(listed.get('finance_co')!, get)).toBeNull()
    expect(resolveE1MainRowAmount(listed.get('digital')!, get)).toBeNull()
    expect(resolveE1MainRowAmount(listed.get('accrued')!, get)).toBeNull()
  })

  it('落库为 0 时返 0（与「取不到」区分开）', () => {
    const get = getterOf({ 'E1-adj-slot-digital': '0' })
    expect(resolveE1MainRowAmount(listed.get('digital')!, get)).toBe(0)
  })

  it('空串按「取不到」处理', () => {
    const get = getterOf({ 'E1-adj-slot-digital': '' })
    expect(resolveE1MainRowAmount(listed.get('digital')!, get)).toBeNull()
  })

  it('非数字文本按「取不到」处理（不产出 NaN）', () => {
    const get = getterOf({ 'E1-adj-slot-accrued': '待确认' })
    expect(resolveE1MainRowAmount(listed.get('accrued')!, get)).toBeNull()
  })

  it('🔴 扣减生效：bank = TB(1002) − slot(finance_co)', () => {
    const get = getterOf({
      'E1-adj-total-1002': '1000000',
      'E1-adj-slot-finance_co': '300000',
    })
    expect(resolveE1MainRowAmount(listed.get('bank')!, get)).toBe(700000)
    expect(resolveE1MainRowAmount(listed.get('finance_co')!, get)).toBe(300000)
  })

  it('🔴 扣减生效：other_mf = TB(1012) − slot(digital)', () => {
    const get = getterOf({
      'E1-adj-total-1012': '50000',
      'E1-adj-slot-digital': '8000',
    })
    expect(resolveE1MainRowAmount(listed.get('other_mf')!, get)).toBe(42000)
  })

  it('槽无值时扣减额为 0（零回归支点：与改造前逐字节相同）', () => {
    const get = getterOf({ 'E1-adj-total-1002': '1000000' })
    expect(resolveE1MainRowAmount(listed.get('bank')!, get)).toBe(1000000)
    expect(e1MainRowDeductionKeys(listed.get('bank')!)).toEqual([
      'E1-adj-slot-finance_co',
    ])
  })

  it('期初列同样走扣减（键带 -opening 后缀）', () => {
    expect(e1MainRowDeductionKeys(listed.get('bank')!, 'opening')).toEqual([
      'E1-adj-slot-finance_co-opening',
    ])
    const get = getterOf({
      'E1-adj-total-1002-opening': '900000',
      'E1-adj-slot-finance_co-opening': '100000',
    })
    expect(resolveE1MainRowAmount(listed.get('bank')!, get, 'opening')).toBe(800000)
  })

  it('无 crossKey 的行不参与扣减（避免自减）', () => {
    expect(e1MainRowDeductionKeys(listed.get('finance_co')!)).toEqual([])
    expect(e1MainRowDeductionKeys(listed.get('digital')!)).toEqual([])
  })

  it('🔴 合计恒等式：三科目合计 + 应计利息 == 参与合计行之和', () => {
    const get = getterOf({
      'E1-adj-total-1001': '5000',
      'E1-adj-total-1002': '1000000',
      'E1-adj-total-1012': '50000',
      'E1-adj-slot-finance_co': '300000',
      'E1-adj-slot-digital': '8000',
      'E1-adj-slot-accrued': '1200',
    })
    const total = totalOf('listed', get)
    // 1001 + (1002−fc) + fc + (1012−dg) + dg + accrued
    expect(total).toBe(5000 + 1000000 + 50000 + 1200)
  })

  it('槽全空时合计 == 三科目合计（改造前口径）', () => {
    const get = getterOf({
      'E1-adj-total-1001': '5000',
      'E1-adj-total-1002': '1000000',
      'E1-adj-total-1012': '50000',
    })
    expect(totalOf('listed', get)).toBe(1055000)
  })

  it('预填标记：无 crossKey 且槽有值 → true', () => {
    const get = getterOf({ 'E1-adj-slot-digital': '8000' })
    expect(isE1MainRowSlotPrefilled(listed.get('digital')!, get)).toBe(true)
    expect(isE1MainRowSlotPrefilled(listed.get('finance_co')!, get)).toBe(false)
    // 有 crossKey 的行永不标「槽预填」
    expect(isE1MainRowSlotPrefilled(listed.get('bank')!, get)).toBe(false)
  })

  it('扣减标记：仅当扣减槽真有值时为 true', () => {
    expect(isE1MainRowDeducted(listed.get('bank')!, getterOf({}))).toBe(false)
    expect(
      isE1MainRowDeducted(listed.get('bank')!, getterOf({ 'E1-adj-slot-finance_co': '1' })),
    ).toBe(true)
  })
})

// ── 组 4：soe 无落点 + 反向自检 ──────────────────────────────────────────────

describe('E1 主表槽预填 · soe 无落点', () => {
  it('soe 真源没有 finance_co / accrued 两行（准则口径差异，不得对齐）', () => {
    const keys = E1_MAIN_ROWS_SOE.map((r) => r.key)
    expect(keys).not.toContain('finance_co')
    expect(keys).not.toContain('accrued')
    // listed 侧有
    const listedKeys = E1_MAIN_ROWS_LISTED.map((r) => r.key)
    expect(listedKeys).toContain('finance_co')
    expect(listedKeys).toContain('accrued')
  })

  it('soe 的 digital 行仍走槽键（该槽全库恒空 ⇒ 显示空白）', () => {
    const row = E1_MAIN_ROWS_SOE.find((r) => r.key === 'digital')!
    expect(row.crossKey).toBe('')
    expect(e1MainRowAmountKey(row)).toBe('E1-adj-slot-digital')
    expect(resolveE1MainRowAmount(row, getterOf({}))).toBeNull()
  })

  it('soe 的 other_mf 走同一条扣减映射（digital 空时行为不变）', () => {
    const row = E1_MAIN_ROWS_SOE.find((r) => r.key === 'other_mf')!
    const get = getterOf({ 'E1-adj-total-1012': '50000' })
    expect(resolveE1MainRowAmount(row, get)).toBe(50000)
    const get2 = getterOf({ 'E1-adj-total-1012': '50000', 'E1-adj-slot-digital': '8000' })
    expect(resolveE1MainRowAmount(row, get2)).toBe(42000)
  })

  it('soe 合计恒等式成立（无 finance_co / accrued 项）', () => {
    const get = getterOf({
      'E1-adj-total-1001': '5000',
      'E1-adj-total-1002': '1000000',
      'E1-adj-total-1012': '50000',
      'E1-adj-slot-digital': '8000',
    })
    expect(totalOf('soe', get)).toBe(1055000)
  })

  it('两变体 e1MainRows 行数分别为 8 / 6（docx 事实）', () => {
    expect(e1MainRows('listed')).toHaveLength(8)
    expect(e1MainRows('soe')).toHaveLength(6)
  })
})

describe('E1 主表槽预填 · 反向自检', () => {
  it('复现旧行为（三行恒读 crossKey）→ 三行必恒空 = 本任务要修的缺陷形态', () => {
    // 旧实现：effEnding = crossKey ? get(crossKey) : 0，无 crossKey 直接返 0
    const legacyEnding = (row: E1MainRowKeyed, get: (k: string) => string | undefined) =>
      row.crossKey ? Number(get(row.crossKey)) || 0 : 0
    const get = getterOf({
      'E1-adj-slot-finance_co': '300000',
      'E1-adj-slot-digital': '8000',
      'E1-adj-slot-accrued': '1200',
    }) as (k: string) => string | undefined

    for (const k of E1_PREFILL_ROW_KEYS) {
      const row = E1_MAIN_ROWS_LISTED.find((r) => r.key === k)! as E1MainRowKeyed
      expect(legacyEnding(row, get), `旧实现下 ${k} 应恒 0`).toBe(0)
      // 新实现取到真值
      expect(resolveE1MainRowAmount(row, get)).not.toBeNull()
    }
  })

  it('若移除扣减映射 → 合计必双算（证明扣减是必要的）', () => {
    const get = getterOf({
      'E1-adj-total-1001': '5000',
      'E1-adj-total-1002': '1000000',
      'E1-adj-total-1012': '50000',
      'E1-adj-slot-finance_co': '300000',
      'E1-adj-slot-digital': '8000',
      'E1-adj-slot-accrued': '1200',
    })
    // 朴素实现：不扣减
    const naive = (row: E1MainRowKeyed): number => {
      const raw = get(e1MainRowAmountKey(row))
      return raw === undefined || raw === '' ? 0 : Number(raw) || 0
    }
    const naiveTotal = e1SummableRows('listed').reduce((s, r) => s + naive(r), 0)
    const correctTotal = totalOf('listed', get)
    expect(naiveTotal).toBe(correctTotal + 300000 + 8000)
    expect(naiveTotal).not.toBe(correctTotal)
  })

  it('若写入侧无条件写 0 → 「无此科目」与「余额为 0」不可区分（证明「不写 0」必要）', () => {
    // 朴素实现：无条件写
    const naiveWrites = E1_PREFILL_ROW_KEYS.map((k) => ({
      itemId: e1MainRowSlotKey(k),
      value: '0',
    }))
    const get = getterOf(
      Object.fromEntries(naiveWrites.map((w) => [w.itemId, w.value])),
    )
    for (const k of E1_PREFILL_ROW_KEYS) {
      const row = E1_MAIN_ROWS_LISTED.find((r) => r.key === k)! as E1MainRowKeyed
      // 朴素实现下取到 0（看着像「余额为零」）
      expect(resolveE1MainRowAmount(row, get)).toBe(0)
    }
    // 正确实现：三值全 0 不写 ⇒ 读到 null
    expect(buildE1MainRowSlotWrites([
      adjRow('finance_co', 0), adjRow('digital', 0), adjRow('accrued_interest', 0),
    ])).toEqual([])
  })

  it('扣减源与被扣行不得同为一行（防自减死循环）', () => {
    for (const [rowKey, slots] of Object.entries(E1_MAIN_ROW_DEDUCTIONS)) {
      expect(slots).not.toContain(rowKey)
    }
  })
})
