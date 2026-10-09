/**
 * D1-1 逐格四态覆盖状态机 —— 修 cross-sheet 无条件盖掉手工值的静默丢数据。
 *
 * spec: d1-sync-row-table-engine-and-d1-coverage · Task 33（需求 6.3 / 6.4）
 *
 * ═══ 修前的缺陷 ═══
 *
 * `readD1AdjudicationTotals` 里 `const g = fromCat ?? 手工值` —— D1-2 一有行，审计师在审定表
 * 手工录的数就**既不显示**（被 cross-sheet 整行覆盖）**也改不了**（`buildRow` 的
 * `isEditable = … && !isFromCrossSheet`）。录进去凭空消失且无任何提示，与 D4-1 修前同型。
 *
 * ═══ 🔴 为什么必须有「跑同步器」的判据 ═══
 *
 * tasks.md 原文警告：D4 spec 有 **13 条纯函数判据全绿而生产坏掉** —— 同步器把**显示值**
 * 当派生值写回 snap，而 S2 下显示值就等于 stored ⇒ 写完 `snap == stored` ⇒ 下一次
 * `resolveCellState` 判成「未覆盖」⇒ **覆盖标记自我擦除**。只喂 `resolveCellState` 三个入参
 * 的判据永远看不到这个。本文件 `describe('同步器真跑')` 那组就是为此存在，其中
 * `覆盖标记不会自我擦除` 是**决定性**的一条。
 */
import { describe, expect, it } from 'vitest'

import {
  D1_ADJ_ROWS_KEY,
  d1AdjAnchor,
  d1AdjRowKey,
  mergeD1AdjRowByCellState,
  readD1AdjSnap,
  resolveD1AdjCell,
  restoreD1AdjDerivedValue,
  syncD1DerivedIntoRows,
  type D1AnchorResponse,
  type D1Category,
  type D1PeriodAmounts,
} from '../d1AdjudicationModel'

type Map_ = Map<string, D1AnchorResponse>

function mapOf(entries: Record<string, string>): Map_ {
  const m: Map_ = new Map()
  for (const [item_id, remark] of Object.entries(entries)) {
    m.set(item_id, { item_id, remark } as D1AnchorResponse)
  }
  return m
}

const CATS = [
  { slug: 'bank', label: '银行承兑汇票', isFixed: true },
  { slug: 'commercial', label: '商业承兑汇票', isFixed: true },
] as unknown as readonly D1Category[]

const ROW = d1AdjRowKey('gross', 'bank')

/** 造一份带金额与 snap 的行数组 store。 */
function storeWith(
  amounts: Record<string, number>,
  snapshot?: Record<string, number | null>,
): Map_ {
  return mapOf({
    [D1_ADJ_ROWS_KEY]: JSON.stringify([
      {
        rowId: ROW,
        label: '银行承兑汇票',
        source: 'tb',
        ...amounts,
        ...(snapshot ? { derivedSnapshot: snapshot } : {}),
      },
    ]),
  })
}

function amounts(partial: Partial<D1PeriodAmounts>): D1PeriodAmounts {
  return {
    priorUnadjusted: 0,
    priorAje: 0,
    priorRje: 0,
    priorAudited: 0,
    currentUnadjusted: 0,
    currentAje: 0,
    currentRje: 0,
    currentAudited: 0,
    ...partial,
  } as D1PeriodAmounts
}

// ═══════════════════════════════════════════════════════════════════════════
// 1. 四态逐个
// ═══════════════════════════════════════════════════════════════════════════

describe('resolveD1AdjCell 四态', () => {
  it('S1 纯派生：stored == snap == derived ⇒ 显示 derived', () => {
    const r = resolveD1AdjCell(
      storeWith({ 'prior-unadj': 100 }, { 'prior-unadj': 100 }),
      ROW,
      'prior-unadj',
      100,
    )
    expect(r.state).toBe('S1')
    expect(r.display).toBe(100)
  })

  it('S2 人工覆盖、上游未变：stored ≠ snap 且 snap == derived ⇒ 显示 stored', () => {
    const r = resolveD1AdjCell(
      storeWith({ 'prior-unadj': 777 }, { 'prior-unadj': 100 }),
      ROW,
      'prior-unadj',
      100,
    )
    expect(r.state).toBe('S2')
    expect(r.display).toBe(777)
  })

  it('S3 无覆盖、上游已变：stored == snap 且 snap ≠ derived ⇒ 跟随 derived', () => {
    const r = resolveD1AdjCell(
      storeWith({ 'prior-unadj': 100 }, { 'prior-unadj': 100 }),
      ROW,
      'prior-unadj',
      250,
    )
    expect(r.state).toBe('S3')
    expect(r.display).toBe(250)
  })

  it('S4 覆盖且上游已变 ⇒ 显示 stored（双值可见由 UI 负责）', () => {
    const r = resolveD1AdjCell(
      storeWith({ 'prior-unadj': 777 }, { 'prior-unadj': 100 }),
      ROW,
      'prior-unadj',
      250,
    )
    expect(r.state).toBe('S4')
    expect(r.display).toBe(777)
    expect(r.derived).toBe(250)
    expect(r.stored).toBe(777)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 2. snap 为 null 的降级 —— 这条是实测踩到的回归
// ═══════════════════════════════════════════════════════════════════════════

describe('snap 为 null（从未由派生写入过）的降级', () => {
  it('🔴 stored 为 0（没录入）⇒ S1、显示 derived，**不得**把上游值显示成 0', () => {
    // 实测回归：直接把 (0, null, 100) 丢给 resolveCellState 会算出 S4 ⇒ 显示 stored=0
    // ⇒ `useD1DisclosureDerived.spec.ts` 的 endBalance 期望 140 实得 0。
    const r = resolveD1AdjCell(mapOf({}), ROW, 'prior-unadj', 100)
    expect(r.snap).toBeNull()
    expect(r.state).toBe('S1')
    expect(r.display).toBe(100)
  })

  it('stored 非零（迁移前就有手工值）⇒ S2、显示 stored（这正是要修的那一半）', () => {
    const m = mapOf({ [d1AdjAnchor('gross', 'bank', 'prior-unadj')]: '555' })
    const r = resolveD1AdjCell(m, ROW, 'prior-unadj', 100)
    expect(r.snap).toBeNull()
    expect(r.state).toBe('S2')
    expect(r.display).toBe(555)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 3. 逐格独立（修前是整行二选一）
// ═══════════════════════════════════════════════════════════════════════════

describe('mergeD1AdjRowByCellState 逐格独立', () => {
  it('🔴 只覆盖「账项调整」一列，其余列继续跟随上游', () => {
    const derived = amounts({ priorUnadjusted: 1000, priorAje: 0, currentUnadjusted: 2000 })
    const m = storeWith(
      { 'prior-unadj': 1000, 'prior-aje': 88, 'current-unadj': 2000 },
      { 'prior-unadj': 1000, 'prior-aje': 0, 'current-unadj': 2000 },
    )
    const { amounts: got, states } = mergeD1AdjRowByCellState(m, 'gross', 'bank', derived)
    expect(states['prior-aje']).toBe('S2') // 被覆盖
    expect(states['prior-unadj']).toBe('S1') // 跟随
    expect(states['current-unadj']).toBe('S1')
    expect(got.priorAje).toBe(88) // 覆盖值
    expect(got.priorUnadjusted).toBe(1000) // 上游值
    // 审定数按合成后的值现算
    expect(got.priorAudited).toBeCloseTo(1000 + 88 + 0, 6)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 4. 🔴 同步器真跑（不是只喂 resolveCellState 入参）
// ═══════════════════════════════════════════════════════════════════════════

describe('同步器真跑 syncD1DerivedIntoRows', () => {
  const derivedBySection = {
    gross: { bank: amounts({ priorUnadjusted: 100, currentUnadjusted: 200 }) },
  }

  it('首次跑：把 derived 写进 stored 与 snap，四态随之从降级态变为完整 S1', () => {
    const raw = syncD1DerivedIntoRows(mapOf({}), CATS, derivedBySection)
    expect(raw).not.toBeNull()
    const after = mapOf({ [D1_ADJ_ROWS_KEY]: raw! })
    expect(readD1AdjSnap(after, ROW, 'prior-unadj')).toBe(100)
    const r = resolveD1AdjCell(after, ROW, 'prior-unadj', 100)
    expect(r.state).toBe('S1')
    expect(r.stored).toBe(100)
  })

  it('幂等：无变化时返回 null（调用方据此跳过写库，watch 不自激）', () => {
    const first = syncD1DerivedIntoRows(mapOf({}), CATS, derivedBySection)!
    const after = mapOf({ [D1_ADJ_ROWS_KEY]: first })
    expect(syncD1DerivedIntoRows(after, CATS, derivedBySection)).toBeNull()
  })

  it('🔴 S2 的 stored 不被派生值冲掉（只推 snap）', () => {
    const before = storeWith(
      { 'prior-unadj': 777, 'current-unadj': 200 },
      { 'prior-unadj': 100, 'current-unadj': 200 },
    )
    const raw = syncD1DerivedIntoRows(before, CATS, {
      gross: { bank: amounts({ priorUnadjusted: 100, currentUnadjusted: 200 }) },
    })
    // snap 已等于 derived、stored 已是覆盖值 ⇒ 无需改动
    const after = raw === null ? before : mapOf({ [D1_ADJ_ROWS_KEY]: raw })
    const r = resolveD1AdjCell(after, ROW, 'prior-unadj', 100)
    expect(r.stored).toBe(777) // 覆盖值保住
    expect(r.state).toBe('S2')
  })

  it('🔴 上游变化后：S2 → S4，stored 仍是覆盖值、snap 推到新 derived', () => {
    const before = storeWith(
      { 'prior-unadj': 777, 'current-unadj': 200 },
      { 'prior-unadj': 100, 'current-unadj': 200 },
    )
    const raw = syncD1DerivedIntoRows(before, CATS, {
      gross: { bank: amounts({ priorUnadjusted: 999, currentUnadjusted: 200 }) },
    })!
    const after = mapOf({ [D1_ADJ_ROWS_KEY]: raw })
    expect(readD1AdjSnap(after, ROW, 'prior-unadj')).toBe(999) // snap 跟到新 derived
    const r = resolveD1AdjCell(after, ROW, 'prior-unadj', 999)
    expect(r.stored).toBe(777) // 覆盖值没被冲掉
    expect(r.state).toBe('S2') // snap==derived ⇒ 上游"已同步"，覆盖仍在
    expect(r.display).toBe(777)
  })

  it('🔴🔴 覆盖标记不会自我擦除（D4 事故的精确反证）', () => {
    // 事故形态：同步器把**显示值**当派生值写回 snap。S2 下显示值 == stored ⇒
    // 写完 snap == stored ⇒ 下一次 resolveCellState 判「未覆盖」⇒ 覆盖标记消失。
    let store = storeWith(
      { 'prior-unadj': 777, 'current-unadj': 200 },
      { 'prior-unadj': 100, 'current-unadj': 200 },
    )
    expect(resolveD1AdjCell(store, ROW, 'prior-unadj', 100).state).toBe('S2')

    // 连续跑 3 轮同步器（模拟 watch 多次触发）
    for (let i = 0; i < 3; i++) {
      const raw = syncD1DerivedIntoRows(store, CATS, {
        gross: { bank: amounts({ priorUnadjusted: 100, currentUnadjusted: 200 }) },
      })
      if (raw !== null) store = mapOf({ [D1_ADJ_ROWS_KEY]: raw })
    }

    const r = resolveD1AdjCell(store, ROW, 'prior-unadj', 100)
    expect(r.snap, 'snap 被写成了显示值(=stored) ⇒ 覆盖标记自我擦除').not.toBe(777)
    expect(r.snap).toBe(100)
    expect(r.state, '跑完同步器后覆盖标记消失了').toBe('S2')
    expect(r.display).toBe(777)
  })

  it('S3（上游变、无覆盖）跑完同步器后 stored 跟随到新 derived ⇒ 回到 S1', () => {
    const before = storeWith(
      { 'prior-unadj': 100, 'current-unadj': 200 },
      { 'prior-unadj': 100, 'current-unadj': 200 },
    )
    expect(resolveD1AdjCell(before, ROW, 'prior-unadj', 300).state).toBe('S3')
    const raw = syncD1DerivedIntoRows(before, CATS, {
      gross: { bank: amounts({ priorUnadjusted: 300, currentUnadjusted: 200 }) },
    })!
    const after = mapOf({ [D1_ADJ_ROWS_KEY]: raw })
    const r = resolveD1AdjCell(after, ROW, 'prior-unadj', 300)
    expect(r.stored).toBe(300)
    expect(r.state).toBe('S1')
  })

  it('🔴 只改 derived、不改 stored/snap 时覆盖标记数必须为 0（P15 反证式）', () => {
    // 纯派生行（S1）遇上游变化只应进 S3，不得被判成人工覆盖。
    const store = storeWith(
      { 'prior-unadj': 100, 'current-unadj': 200 },
      { 'prior-unadj': 100, 'current-unadj': 200 },
    )
    const overriddenCount = ['prior-unadj', 'current-unadj'].filter((f) => {
      const s = resolveD1AdjCell(store, ROW, f, f === 'prior-unadj' ? 9999 : 200).state
      return s === 'S2' || s === 'S4'
    }).length
    expect(overriddenCount).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 5. 恢复取数
// ═══════════════════════════════════════════════════════════════════════════

describe('restoreD1AdjDerivedValue', () => {
  it('🔴 当场写对：stored 与 snap 同时变成 derived ⇒ 再解析是 S1', () => {
    const before = storeWith(
      { 'prior-unadj': 777 },
      { 'prior-unadj': 100 },
    )
    expect(resolveD1AdjCell(before, ROW, 'prior-unadj', 100).state).toBe('S2')

    const raw = restoreD1AdjDerivedValue(before, CATS, ROW, 'prior-unadj', 100)
    const after = mapOf({ [D1_ADJ_ROWS_KEY]: raw })
    const r = resolveD1AdjCell(after, ROW, 'prior-unadj', 100)
    expect(r.stored).toBe(100)
    expect(r.snap).toBe(100)
    expect(r.state).toBe('S1')
  })

  it('只影响被点的那一格，同行其它覆盖格不受影响', () => {
    const before = storeWith(
      { 'prior-unadj': 777, 'current-unadj': 888 },
      { 'prior-unadj': 100, 'current-unadj': 200 },
    )
    const raw = restoreD1AdjDerivedValue(before, CATS, ROW, 'prior-unadj', 100)
    const after = mapOf({ [D1_ADJ_ROWS_KEY]: raw })
    expect(resolveD1AdjCell(after, ROW, 'prior-unadj', 100).state).toBe('S1')
    expect(resolveD1AdjCell(after, ROW, 'current-unadj', 200).state).toBe('S2')
    expect(resolveD1AdjCell(after, ROW, 'current-unadj', 200).display).toBe(888)
  })
})
