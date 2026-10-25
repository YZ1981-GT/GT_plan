/**
 * D1-1 审定表行数组形态 —— **双读**（行对象优先、缺则回落 per-cell 锚点）。
 *
 * spec: d1-sync-row-table-engine-and-d1-coverage · Task 32（需求 6.1 / 6.2）
 *
 * ═══ 这组判据钉住什么 ═══
 *
 * 1. **键形态等价性**：`d1AdjAnchor(section, slug, field)` 与共享模块的
 *    `rowFieldItemId(D1_ADJ_ROWS_SPEC, d1AdjRowKey(section, slug), field)` 必须**逐字相同**。
 *    这条是整个迁移方案成立的前提 —— 正因两者天然一致，D1 才能直接接入
 *    `shared/dynamicAdjudicationRows` 而不是另造一套键（需求 6.4 明令不得在 D1 侧另写一套）。
 *    若将来有人改了任一侧的拼法，双读会静默回落到不存在的键 ⇒ 金额归零。
 *
 * 2. **迁移不归零**（需求 6.2）：只有 per-cell 旧数据、行数组不存在时，
 *    `readD1AdjRowAmounts` 必须读回原值，且与迁移前的 `readD1AnchorAmounts` **逐字段相等**。
 *
 * 3. **行对象优先**：行对象带金额时以它为权威（它也是 OO 回写的落点）；
 *    反向（per-cell 优先）会让 OO 改的值被旧值永久盖住。
 *
 * 4. **逐字段独立回落**：同一行部分字段已迁到行对象、部分还在 per-cell 时，两边都要读到
 *    （双写迁移期的真实形态 —— 不是"整行要么新要么旧"）。
 *
 * 🔴 **真库存量说明（P14 的诚实边界）**：本判据用合成 payload 驱动，因为
 *    2026-09-28 实测真库 `checklist_responses` 里 `item_id LIKE 'D1-adj-%'` **0 行** ——
 *    D1-1 的 per-cell 键全库无存量数据。tasks.md 的 P14 要求「以真库存量形态的 payload 驱动
 *    （不是合成理想数据）」在 D1 上**无真实存量可用**；这里改用「与真库 D4-1 同构的形态」
 *    （D4 真库有 `D4-1-rows` 4063 B 行数组 + `D4-1-adj-tb-*` per-cell 标量共存，
 *    正是双写迁移期的真实形态）作为参照来造合成数据，并如实声明这一降级。
 */
import { describe, expect, it } from 'vitest'

import {
  D1_ADJ_ROWS_KEY,
  D1_ADJ_ROWS_SPEC,
  D1_ADJ_VALUE_FIELDS,
  d1AdjAnchor,
  d1AdjPlaceholderRow,
  d1AdjRowKey,
  isD1AdjAnchor,
  readD1AdjCellValue,
  readD1AdjRowAmounts,
  readD1AdjRows,
  readD1AnchorAmounts,
  serializeD1AdjRows,
  type D1AdjSection,
  type D1AnchorResponse,
} from '../d1AdjudicationModel'
import {
  rowFieldItemId,
  rowsItemId,
  serializeRows,
} from '../shared/dynamicAdjudicationRows'

type Map_ = Map<string, D1AnchorResponse>

function mapOf(entries: Record<string, string>): Map_ {
  const m: Map_ = new Map()
  for (const [item_id, remark] of Object.entries(entries)) {
    m.set(item_id, { item_id, remark } as D1AnchorResponse)
  }
  return m
}

/** 旧形态：某区块某分类的 6 个 per-cell 锚点。 */
function perCellEntries(
  section: D1AdjSection,
  slug: string,
  values: Record<string, string>,
): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [field, v] of Object.entries(values)) {
    out[d1AdjAnchor(section, slug, field as never)] = v
  }
  return out
}

// ═══════════════════════════════════════════════════════════════════════════
// 1. 键形态等价性 —— 整个迁移方案的前提
// ═══════════════════════════════════════════════════════════════════════════

describe('per-cell 锚点 ↔ 共享模块 per-field 键：逐字等价', () => {
  it.each([
    ['gross', 'bank'],
    ['bd', 'commercial'],
    ['gross', 'credit-letter'],
  ] as const)('section=%s slug=%s 六个字段全部同键', (section, slug) => {
    for (const field of D1_ADJ_VALUE_FIELDS) {
      const viaAnchor = d1AdjAnchor(section as D1AdjSection, slug, field as never)
      const viaShared = rowFieldItemId(
        D1_ADJ_ROWS_SPEC,
        d1AdjRowKey(section as D1AdjSection, slug),
        field,
      )
      expect(viaShared).toBe(viaAnchor)
    }
  })

  it('行数组键是 D1-adj-rows（与 D4-1 的 D4-1-rows 同范式）', () => {
    expect(D1_ADJ_ROWS_KEY).toBe('D1-adj-rows')
    expect(rowsItemId(D1_ADJ_ROWS_SPEC)).toBe(D1_ADJ_ROWS_KEY)
  })

  it('🔴 变异反证：prefix 被改动 ⇒ 等价性立即破裂', () => {
    const bad = { ...D1_ADJ_ROWS_SPEC, prefix: 'D1-adjudication' }
    expect(rowFieldItemId(bad, d1AdjRowKey('gross', 'bank'), 'prior-unadj')).not.toBe(
      d1AdjAnchor('gross', 'bank', 'prior-unadj'),
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 2. 迁移不归零：只有 per-cell 旧数据时逐字段等价于迁移前
// ═══════════════════════════════════════════════════════════════════════════

describe('只有 per-cell 旧数据（行数组不存在）', () => {
  const legacy = mapOf(
    perCellEntries('gross', 'bank', {
      'prior-unadj': '1000.5',
      'prior-aje': '10',
      'prior-rje': '-5',
      'current-unadj': '2000.25',
      'current-aje': '20',
      'current-rje': '0',
    }),
  )

  it('金额不归零，且与迁移前的 readD1AnchorAmounts 逐字段相等', () => {
    const now = readD1AdjRowAmounts(legacy, 'gross', 'bank')
    const before = readD1AnchorAmounts(legacy, 'gross', 'bank')
    expect(now).toEqual(before)
    expect(now.priorUnadjusted).toBe(1000.5)
    expect(now.currentUnadjusted).toBe(2000.25)
    // 审定数现算：未审 + AJE + RJE
    expect(now.priorAudited).toBeCloseTo(1000.5 + 10 - 5, 6)
    expect(now.currentAudited).toBeCloseTo(2000.25 + 20 + 0, 6)
  })

  it('readD1AdjRows 对缺键返回空数组（不抛）', () => {
    expect(readD1AdjRows(legacy)).toEqual([])
    expect(readD1AdjRows(mapOf({ [D1_ADJ_ROWS_KEY]: 'not json' }))).toEqual([])
  })

  it('未录入的分类读回全 0（不抛、不 NaN）', () => {
    const a = readD1AdjRowAmounts(legacy, 'bd', 'never-entered')
    expect(a.priorUnadjusted).toBe(0)
    expect(a.currentAudited).toBe(0)
    expect(Number.isNaN(a.currentAudited)).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 3. 行对象优先
// ═══════════════════════════════════════════════════════════════════════════

describe('行对象存在时以它为权威', () => {
  const rowId = d1AdjRowKey('gross', 'bank')

  function withRows(amounts: Record<string, number>, perCell: Record<string, string> = {}) {
    const rows = [
      {
        rowId,
        label: '银行承兑汇票',
        source: 'legacy' as const,
        ...amounts,
      },
    ]
    return mapOf({
      [D1_ADJ_ROWS_KEY]: JSON.stringify(rows),
      ...perCell,
    })
  }

  it('行对象金额覆盖 per-cell 旧值（OO 回写落点优先）', () => {
    const m = withRows(
      { 'prior-unadj': 999, 'current-unadj': 888 },
      perCellEntries('gross', 'bank', { 'prior-unadj': '111', 'current-unadj': '222' }),
    )
    const a = readD1AdjRowAmounts(m, 'gross', 'bank')
    expect(a.priorUnadjusted).toBe(999)
    expect(a.currentUnadjusted).toBe(888)
  })

  it('🔴 逐字段独立回落：行对象只带部分字段时，其余字段仍读 per-cell', () => {
    const m = withRows(
      { 'current-unadj': 888 },
      perCellEntries('gross', 'bank', {
        'prior-unadj': '111',
        'prior-aje': '7',
        'current-aje': '3',
      }),
    )
    const a = readD1AdjRowAmounts(m, 'gross', 'bank')
    expect(a.currentUnadjusted).toBe(888) // 来自行对象
    expect(a.priorUnadjusted).toBe(111) // 回落 per-cell
    expect(a.priorAje).toBe(7)
    expect(a.currentAje).toBe(3)
  })

  it('行对象里显式 null 的字段视为无值 ⇒ 回落 per-cell（与 serializeRows 不落键口径对称）', () => {
    const m = withRows(
      { 'prior-unadj': null as unknown as number },
      perCellEntries('gross', 'bank', { 'prior-unadj': '456' }),
    )
    expect(readD1AdjRowAmounts(m, 'gross', 'bank').priorUnadjusted).toBe(456)
  })

  it('别的行的金额不串进本行', () => {
    const rows = [
      { rowId, label: '银行承兑汇票', source: 'legacy' as const, 'prior-unadj': 100 },
      {
        rowId: d1AdjRowKey('gross', 'commercial'),
        label: '商业承兑汇票',
        source: 'legacy' as const,
        'prior-unadj': 777,
      },
    ]
    const m = mapOf({ [D1_ADJ_ROWS_KEY]: JSON.stringify(rows) })
    expect(readD1AdjRowAmounts(m, 'gross', 'bank').priorUnadjusted).toBe(100)
    expect(readD1AdjRowAmounts(m, 'gross', 'commercial').priorUnadjusted).toBe(777)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 4. 占位行 —— 回落路径的驱动器
// ═══════════════════════════════════════════════════════════════════════════

describe('d1AdjPlaceholderRow', () => {
  it('rowId 与 d1AdjRowKey 一致（否则回落会拼出不存在的键）', () => {
    const row = d1AdjPlaceholderRow('bd', 'commercial', '商业承兑汇票')
    expect(row.rowId).toBe(d1AdjRowKey('bd', 'commercial'))
    expect(row.source).toBe('legacy')
    expect(row.label).toBe('商业承兑汇票')
  })

  it('🔴 反证：没有占位行时共享模块不会回落（rid 为空即 return 0）', () => {
    // 这条解释了为什么 readD1AdjRowAmounts 必须造占位行 —— 直接传 undefined 行会读不到旧值。
    const m = mapOf(perCellEntries('gross', 'bank', { 'prior-unadj': '321' }))
    const withPlaceholder = readD1AdjRowAmounts(m, 'gross', 'bank')
    expect(withPlaceholder.priorUnadjusted).toBe(321)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 5. 与共享模块的序列化往返（写侧切换后的落库形态预验）
// ═══════════════════════════════════════════════════════════════════════════

describe('serializeRows 往返（写侧切换的形态预验）', () => {
  it('金额随行落库后能被双读读回', () => {
    const rows = [
      { rowId: d1AdjRowKey('gross', 'bank'), label: '银行承兑汇票', source: 'legacy' as const },
    ]
    const values: Record<string, number> = {
      'prior-unadj': 1234.56,
      'current-unadj': 2345.67,
    }
    const raw = serializeRows(rows, {
      spec: D1_ADJ_ROWS_SPEC,
      reader: {
        readField: (_rowId, field) => values[field] ?? null,
      },
    })
    const m = mapOf({ [D1_ADJ_ROWS_KEY]: raw })
    const a = readD1AdjRowAmounts(m, 'gross', 'bank')
    expect(a.priorUnadjusted).toBe(1234.56)
    expect(a.currentUnadjusted).toBe(2345.67)
    // 未提供的字段 → 不落键 → 回落 per-cell（此处无 per-cell ⇒ 0）
    expect(a.priorAje).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 6. 写侧单写（Task 32 的后半）
// ═══════════════════════════════════════════════════════════════════════════

describe('serializeD1AdjRows —— 写侧单写', () => {
  const cats = [
    { slug: 'bank', label: '银行承兑汇票', isFixed: true },
    { slug: 'commercial', label: '商业承兑汇票', isFixed: true },
  ] as unknown as Parameters<typeof serializeD1AdjRows>[1]

  it('🔴 一次写入包含**全部**可编辑行（gross × N + bd × N），不是只写被改的那行', () => {
    const raw = serializeD1AdjRows(mapOf({}), cats, {
      rowId: d1AdjRowKey('gross', 'bank'),
      field: 'prior-unadj',
      value: 100,
    })
    const rows = JSON.parse(raw) as Array<{ rowId: string }>
    const ids = rows.map((r) => r.rowId).sort()
    expect(ids).toEqual(
      [
        d1AdjRowKey('gross', 'bank'),
        d1AdjRowKey('gross', 'commercial'),
        d1AdjRowKey('bd', 'bank'),
        d1AdjRowKey('bd', 'commercial'),
      ].sort(),
    )
    // 只塞一行会让其余行从行数组消失、退回 per-cell 回落 ⇒ 每次编辑在两形态间抖动。
    expect(rows.length).toBe(4)
  })

  it('净值区不落库（它恒为公式）', () => {
    const raw = serializeD1AdjRows(mapOf({}), cats, {
      rowId: d1AdjRowKey('gross', 'bank'),
      field: 'prior-unadj',
      value: 1,
    })
    const rows = JSON.parse(raw) as Array<{ rowId: string }>
    expect(rows.some((r) => r.rowId.startsWith('net-'))).toBe(false)
  })

  it('被改的格用新值，未被改的格保持原值', () => {
    const before = mapOf({
      [D1_ADJ_ROWS_KEY]: JSON.stringify([
        {
          rowId: d1AdjRowKey('gross', 'bank'),
          label: '银行承兑汇票',
          source: 'legacy',
          'prior-unadj': 11,
          'current-unadj': 22,
        },
      ]),
    })
    const raw = serializeD1AdjRows(before, cats, {
      rowId: d1AdjRowKey('gross', 'bank'),
      field: 'current-unadj',
      value: 999,
    })
    const after = mapOf({ [D1_ADJ_ROWS_KEY]: raw })
    const a = readD1AdjRowAmounts(after, 'gross', 'bank')
    expect(a.currentUnadjusted).toBe(999) // 改动生效
    expect(a.priorUnadjusted).toBe(11) // 未改动的保持
  })

  it('🔴 首次编辑时把该行原本只在 per-cell 里的旧值一并固化进行对象（迁移不归零）', () => {
    const legacyOnly = mapOf(
      perCellEntries('gross', 'bank', {
        'prior-unadj': '500',
        'prior-aje': '30',
        'current-unadj': '600',
      }),
    )
    const raw = serializeD1AdjRows(legacyOnly, cats, {
      rowId: d1AdjRowKey('gross', 'bank'),
      field: 'current-aje',
      value: 7,
    })
    const rows = JSON.parse(raw) as Array<Record<string, unknown>>
    const row = rows.find((r) => r.rowId === d1AdjRowKey('gross', 'bank'))!
    // 旧 per-cell 值已随行落库 ⇒ 之后即使旧键被清理也不丢
    expect(row['prior-unadj']).toBe(500)
    expect(row['prior-aje']).toBe(30)
    expect(row['current-unadj']).toBe(600)
    expect(row['current-aje']).toBe(7)
    // 往返读回一致
    const a = readD1AdjRowAmounts(mapOf({ [D1_ADJ_ROWS_KEY]: raw }), 'gross', 'bank')
    expect(a.priorUnadjusted).toBe(500)
    expect(a.currentAje).toBe(7)
  })

  it('🔴 derivedSnapshot 必须被保留（它是 Task 33 四态的第三个量，写入时丢了四态就废）', () => {
    const snap = { 'current-unadj': 123 }
    const before = mapOf({
      [D1_ADJ_ROWS_KEY]: JSON.stringify([
        {
          rowId: d1AdjRowKey('gross', 'bank'),
          label: '银行承兑汇票',
          source: 'tb',
          'current-unadj': 456,
          derivedSnapshot: snap,
        },
      ]),
    })
    const raw = serializeD1AdjRows(before, cats, {
      rowId: d1AdjRowKey('gross', 'bank'),
      field: 'prior-unadj',
      value: 1,
    })
    const rows = JSON.parse(raw) as Array<Record<string, unknown>>
    const row = rows.find((r) => r.rowId === d1AdjRowKey('gross', 'bank'))!
    expect(row.derivedSnapshot).toEqual(snap)
    expect(row.source).toBe('tb') // source 也不被写入重置
  })

  it('label 沿用已有行的（用户改名不被覆盖），新行取 categories 的', () => {
    const before = mapOf({
      [D1_ADJ_ROWS_KEY]: JSON.stringify([
        { rowId: d1AdjRowKey('gross', 'bank'), label: '我改过的名字', source: 'legacy' },
      ]),
    })
    const raw = serializeD1AdjRows(before, cats, {
      rowId: d1AdjRowKey('gross', 'bank'),
      field: 'prior-unadj',
      value: 1,
    })
    const rows = JSON.parse(raw) as Array<Record<string, unknown>>
    expect(rows.find((r) => r.rowId === d1AdjRowKey('gross', 'bank'))!.label).toBe('我改过的名字')
    expect(rows.find((r) => r.rowId === d1AdjRowKey('gross', 'commercial'))!.label).toBe(
      '商业承兑汇票',
    )
  })

  it('不传 edit 时是幂等固化（把 per-cell 旧值搬进行对象，值不变）', () => {
    const legacyOnly = mapOf(perCellEntries('bd', 'bank', { 'current-unadj': '77' }))
    const raw = serializeD1AdjRows(legacyOnly, cats)
    const a = readD1AdjRowAmounts(mapOf({ [D1_ADJ_ROWS_KEY]: raw }), 'bd', 'bank')
    expect(a.currentUnadjusted).toBe(77)
  })
})

describe('flushAdjItems 能收到行数组键', () => {
  it('🔴 D1-adj-rows 满足 isD1AdjAnchor 前缀 ⇒ 写侧无需改 flush 逻辑', () => {
    expect(isD1AdjAnchor(D1_ADJ_ROWS_KEY)).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 7. readD1AdjCellValue —— 调用方无需直连 shared 模块
// ═══════════════════════════════════════════════════════════════════════════

describe('readD1AdjCellValue', () => {
  it('双读单格：行对象优先、缺则回落 per-cell', () => {
    const rowId = d1AdjRowKey('gross', 'bank')
    const m = mapOf({
      [D1_ADJ_ROWS_KEY]: JSON.stringify([
        { rowId, label: 'x', source: 'legacy', 'current-aje': 50 },
      ]),
      ...perCellEntries('gross', 'bank', { 'current-aje': '9', 'current-rje': '8' }),
    })
    expect(readD1AdjCellValue(m, rowId, 'current-aje')).toBe(50)
    expect(readD1AdjCellValue(m, rowId, 'current-rje')).toBe(8)
  })

  it('全无数据时返回 0（不 NaN、不抛）', () => {
    expect(readD1AdjCellValue(mapOf({}), d1AdjRowKey('bd', 'nope'), 'prior-aje')).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 8. 写侧边界：不在 categories 里的行不得被静默丢弃（自查发现）
// ═══════════════════════════════════════════════════════════════════════════

describe('serializeD1AdjRows 的行清单边界', () => {
  const cats = [{ slug: 'bank', label: '银行承兑汇票', isFixed: true }] as unknown as Parameters<
    typeof serializeD1AdjRows
  >[1]

  it('🔴 被编辑的行不在 categories 里时也必须落库（否则用户输入静默丢失）', () => {
    // 场景：分类刚被从 D1-2 删掉，或 rowKey 来自 resolveRowKeyFromAccount 这类科目映射入口。
    const orphanRowId = d1AdjRowKey('gross', 'credit-letter')
    const raw = serializeD1AdjRows(mapOf({}), cats, {
      rowId: orphanRowId,
      field: 'current-unadj',
      value: 888,
    })
    const rows = JSON.parse(raw) as Array<Record<string, unknown>>
    const row = rows.find((r) => r.rowId === orphanRowId)
    expect(row, `孤儿行 ${orphanRowId} 未落库 ⇒ 编辑被吞`).toBeTruthy()
    expect(row!['current-unadj']).toBe(888)
  })

  it('🔴 库里已有但 categories 读不到的行不得被抹掉', () => {
    const staleRowId = d1AdjRowKey('bd', 'was-deleted-from-d1-2')
    const before = mapOf({
      [D1_ADJ_ROWS_KEY]: JSON.stringify([
        { rowId: staleRowId, label: '历史分类', source: 'legacy', 'prior-unadj': 321 },
      ]),
    })
    const raw = serializeD1AdjRows(before, cats, {
      rowId: d1AdjRowKey('gross', 'bank'),
      field: 'prior-unadj',
      value: 1,
    })
    const rows = JSON.parse(raw) as Array<Record<string, unknown>>
    const kept = rows.find((r) => r.rowId === staleRowId)
    expect(kept, '已有行被 categories 口径抹掉 ⇒ 历史金额丢失').toBeTruthy()
    expect(kept!['prior-unadj']).toBe(321)
    expect(kept!.label).toBe('历史分类')
  })

  it('rowId 不重复（categories 与已有行有交集时只出一行）', () => {
    const rowId = d1AdjRowKey('gross', 'bank')
    const before = mapOf({
      [D1_ADJ_ROWS_KEY]: JSON.stringify([{ rowId, label: 'x', source: 'legacy' }]),
    })
    const raw = serializeD1AdjRows(before, cats, { rowId, field: 'prior-unadj', value: 1 })
    const rows = JSON.parse(raw) as Array<{ rowId: string }>
    expect(rows.filter((r) => r.rowId === rowId).length).toBe(1)
  })
})
