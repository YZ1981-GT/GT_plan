/**
 * Task 8/9 共享件金额随行落库 + 单源读判据。
 *
 * spec: d4-html-to-oo-store-contract-alignment · Task 8, 9
 * Requirements 4.1, 4.2 · Property 6（迁移不归零）
 *
 * 覆盖：
 *   1. serializeRows(rows, {reader}) 把 valueFields 平铺进行对象顶层（number），
 *      null/undefined 字段不落键；source==='tb' 且提供 readDerivedSnapshot 时落 derivedSnapshot。
 *   2. deserializeRows 透传金额顶层键 + derivedSnapshot（写得进读得回）。
 *   3. readRowFieldWithFallback：行对象顶层值优先，缺则回落 per-field item。
 *   4. P6 迁移不归零：只有 per-field 旧数据、行对象无金额键 → 读回等于 per-field 值。
 *   5. 行对象值优先于 per-field（OO 回写落行对象后不被旧 per-field 盖住）。
 */
import { describe, it, expect } from 'vitest'
import {
  serializeRows,
  deserializeRows,
  readRowFieldWithFallback,
  rowFieldItemId,
  type DynamicAdjRow,
  type DynamicRowsSpec,
} from '../shared/dynamicAdjudicationRows'

const SPEC: DynamicRowsSpec = {
  prefix: 'D4-1',
  legacyRows: [],
  valueFields: [
    'currentUnadjusted',
    'currentAje',
    'currentRje',
    'priorUnadjusted',
    'priorAje',
    'priorRje',
  ],
}

const ROWS: DynamicAdjRow[] = [
  { rowId: 'r-1', label: '批发收入', source: 'tb', accountCode: '6001' },
  { rowId: 'r-2', label: '手工行', source: 'manual' },
]

function makeReader(
  values: Record<string, Record<string, number | null>>,
  snapshots?: Record<string, Record<string, number | null>>,
) {
  return {
    readField: (rowId: string, field: string) => values[rowId]?.[field] ?? null,
    readDerivedSnapshot: snapshots
      ? (rowId: string) => snapshots[rowId] ?? null
      : undefined,
  }
}

describe('Task 8：serializeRows 金额随行落库', () => {
  it('传 reader 时把 valueFields 平铺进行对象顶层（number）', () => {
    const reader = makeReader({
      'r-1': { currentUnadjusted: 153431246.16, currentAje: 0 },
      'r-2': { currentUnadjusted: 100 },
    })
    const parsed = JSON.parse(serializeRows(ROWS, { spec: SPEC, reader })) as Array<
      Record<string, unknown>
    >
    expect(parsed[0].currentUnadjusted).toBe(153431246.16)
    expect(parsed[0].currentAje).toBe(0)
    // r-1 未提供的字段不落键（reader 返回 null）。
    expect(parsed[0]).not.toHaveProperty('priorRje')
    expect(parsed[1].currentUnadjusted).toBe(100)
    // 四个结构键仍在。
    expect(parsed[0].rowId).toBe('r-1')
    expect(parsed[0].accountCode).toBe('6001')
  })

  it('source===tb 且提供 readDerivedSnapshot 时落 derivedSnapshot（manual 行不落）', () => {
    const reader = makeReader(
      { 'r-1': { currentUnadjusted: 153431246.16 }, 'r-2': { currentUnadjusted: 100 } },
      { 'r-1': { currentUnadjusted: 153431246.16, currentAje: 0 } },
    )
    const parsed = JSON.parse(serializeRows(ROWS, { spec: SPEC, reader })) as Array<
      Record<string, unknown>
    >
    expect(parsed[0].derivedSnapshot).toEqual({ currentUnadjusted: 153431246.16, currentAje: 0 })
    // r-2 是 manual，即便有 reader 也不落 snapshot。
    expect(parsed[1]).not.toHaveProperty('derivedSnapshot')
  })

  it('非有限值不落键（NaN/Infinity/字符串）', () => {
    const reader = {
      readField: (_rid: string, field: string) =>
        (({ currentUnadjusted: NaN, currentAje: Infinity } as Record<string, number>)[field] ??
          null),
    }
    const parsed = JSON.parse(serializeRows([ROWS[0]], { spec: SPEC, reader })) as Array<
      Record<string, unknown>
    >
    expect(parsed[0]).not.toHaveProperty('currentUnadjusted')
    expect(parsed[0]).not.toHaveProperty('currentAje')
  })
})

describe('Task 8：deserializeRows 透传金额与 derivedSnapshot（写得进读得回）', () => {
  it('往返：serialize→deserialize 保留金额顶层键与 snapshot', () => {
    const reader = makeReader(
      { 'r-1': { currentUnadjusted: 153431246.16, currentAje: 5 } },
      { 'r-1': { currentUnadjusted: 153431200 } },
    )
    const json = serializeRows([ROWS[0]], { spec: SPEC, reader })
    const back = deserializeRows(json)
    expect(back).toHaveLength(1)
    expect((back[0] as Record<string, unknown>).currentUnadjusted).toBe(153431246.16)
    expect((back[0] as Record<string, unknown>).currentAje).toBe(5)
    expect(back[0].derivedSnapshot).toEqual({ currentUnadjusted: 153431200 })
    // 结构键完好。
    expect(back[0].rowId).toBe('r-1')
    expect(back[0].source).toBe('tb')
  })
})

describe('Task 9：readRowFieldWithFallback 行对象优先、缺则回落 per-field', () => {
  it('行对象有顶层值 → 用它（忽略 per-field）', () => {
    const row: DynamicAdjRow = { rowId: 'r-1', label: 'x', source: 'tb', currentUnadjusted: 999 }
    const responses = new Map<string, unknown>([
      [rowFieldItemId(SPEC, 'r-1', 'currentUnadjusted'), { remark: '111' }],
    ])
    expect(readRowFieldWithFallback(row, responses, SPEC, 'currentUnadjusted')).toBe(999)
  })

  it('P6 迁移不归零：行对象无金额键 → 回落 per-field 值', () => {
    const row: DynamicAdjRow = { rowId: 'r-1', label: 'x', source: 'manual' } // 无金额键
    const responses = new Map<string, unknown>([
      [rowFieldItemId(SPEC, 'r-1', 'currentUnadjusted'), { remark: '238921879.36' }],
    ])
    expect(readRowFieldWithFallback(row, responses, SPEC, 'currentUnadjusted')).toBe(238921879.36)
  })

  it('行对象值为 null → 视为无值、回落 per-field', () => {
    const row = { rowId: 'r-1', label: 'x', source: 'tb', currentAje: null } as unknown as DynamicAdjRow
    const responses = new Map<string, unknown>([
      [rowFieldItemId(SPEC, 'r-1', 'currentAje'), { remark: '42' }],
    ])
    expect(readRowFieldWithFallback(row, responses, SPEC, 'currentAje')).toBe(42)
  })

  it('两处都没有 → 0（既有 readNum 语义）', () => {
    const row: DynamicAdjRow = { rowId: 'r-9', label: 'x', source: 'manual' }
    expect(readRowFieldWithFallback(row, new Map(), SPEC, 'currentRje')).toBe(0)
  })

  it('row 为空 → 0（不抛）', () => {
    expect(readRowFieldWithFallback(null, new Map(), SPEC, 'currentRje')).toBe(0)
  })
})
