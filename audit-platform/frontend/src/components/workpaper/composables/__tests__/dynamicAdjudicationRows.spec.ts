/**
 * 平台级共享件 `shared/dynamicAdjudicationRows.ts` 纯函数守卫（Property 5~8）。
 *
 * 🔴 刻意使用**与任何真实循环无关的替身 spec**（前缀 `XX-9`、虚构历史行），
 * 证明共享件不含循环专属常量 —— 若哪天有人把 K2 的键写进共享件，本文件必红。
 *
 * spec: .kiro/specs/k2-four-table-extraction-and-dynamic-rows/ Task 3.1 / 3.4
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  appendManualRow,
  collectRowItemIds,
  deserializeRows,
  dropRow,
  findDuplicateLabel,
  foreignRowWarning,
  hasLegacyRowData,
  labelKey,
  migrateLegacyFixedRows,
  nextRowId,
  normalizeLabel,
  readNum,
  readRaw,
  renameRowLabel,
  resolveInitialRows,
  rowFieldItemId,
  rowKeyPrefix,
  rowsItemId,
  seedRowsFromPrefill,
  serializeRows,
  type DynamicAdjRow,
  type DynamicRowsSpec,
} from '../shared/dynamicAdjudicationRows'

// ─── 替身 spec（与任何真实循环无关） ────────────────────────────────────────

const SPEC: DynamicRowsSpec = {
  prefix: 'XX-9',
  legacyRows: [
    { key: 'alpha', label: '甲项目' },
    { key: 'beta', label: '乙项目', foreignWarning: '乙项目属于别的报表行' },
    { key: 'gamma', label: '丙项目' },
  ],
  valueFields: ['begin', 'unadj', 'aje'],
}

function mapOf(entries: Record<string, string>): Map<string, unknown> {
  const m = new Map<string, unknown>()
  for (const [k, v] of Object.entries(entries)) {
    m.set(k, { item_id: k, conclusion: null, remark: v })
  }
  return m
}

function row(rowId: string, label: string, source: DynamicAdjRow['source'] = 'manual'): DynamicAdjRow {
  return { rowId, label, source }
}

/** 确定性伪随机（PBT / 唯一性断言可复现） */
function seededRand(seed = 1): () => number {
  let s = seed
  return () => {
    s = (s * 1103515245 + 12345) % 2147483648
    return s / 2147483648
  }
}

// ─── itemId 拼装 ────────────────────────────────────────────────────────────

describe('itemId 拼装', () => {
  it('行清单键 / 字段键 / 删除前缀三者一致', () => {
    expect(rowsItemId(SPEC)).toBe('XX-9-rows')
    expect(rowFieldItemId(SPEC, 'r-1', 'unadj')).toBe('XX-9-r-1-unadj')
    expect(rowKeyPrefix(SPEC, 'r-1')).toBe('XX-9-r-1-')
    expect(rowFieldItemId(SPEC, 'r-1', 'unadj').startsWith(rowKeyPrefix(SPEC, 'r-1'))).toBe(true)
  })
})

// ─── Property 5：行名规范化 + 撞名 + rowId 唯一 ─────────────────────────────

describe('行名规范化与撞名判定（Property 5）', () => {
  it('压缩内部空白 —— 源模板「合 计」「合　计」视为同名', () => {
    expect(normalizeLabel('  合  计 ')).toBe('合 计')
    expect(normalizeLabel('合\u3000计')).toBe('合 计')
    expect(labelKey('合 计')).toBe('合计')
    expect(labelKey('合\u3000计')).toBe('合计')
    expect(normalizeLabel(null)).toBe('')
    expect(normalizeLabel(undefined)).toBe('')
  })

  it('撞名判定忽略空白差异，且可排除自身（改名场景）', () => {
    const rows = [row('r-1', '待摊费用'), row('r-2', '待抵扣进项税')]
    expect(findDuplicateLabel(rows, '待 摊 费 用')?.rowId).toBe('r-1')
    expect(findDuplicateLabel(rows, '待摊费用', 'r-1')).toBeNull()
    expect(findDuplicateLabel(rows, '新项目')).toBeNull()
    expect(findDuplicateLabel(rows, '   ')).toBeNull()
  })

  it('nextRowId 在现有清单内唯一', () => {
    const rand = seededRand(7)
    let rows: DynamicAdjRow[] = []
    const ids = new Set<string>()
    for (let i = 0; i < 50; i++) {
      const id = nextRowId(rows, rand)
      expect(ids.has(id)).toBe(false)
      ids.add(id)
      rows = [...rows, row(id, `项目${i}`)]
    }
    expect(ids.size).toBe(50)
  })

  it('随机源恒返同值时仍能产出唯一 id（线性探测兜底）', () => {
    const rows = [row('r-0', 'a')]
    const a = nextRowId(rows, () => 0)
    const b = nextRowId([...rows, row(a, 'b')], () => 0)
    expect(a).not.toBe('r-0')
    expect(b).not.toBe(a)
  })
})

// ─── Property 5：序列化往返 ─────────────────────────────────────────────────

describe('行清单序列化往返（Property 5）', () => {
  it('往返一致（含中文/空格/特殊字符/来源/科目码）', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            rowId: fc.string({ minLength: 1, maxLength: 8 }).filter((s) => !!s.trim()),
            label: fc.oneof(
              fc.constantFrom('待摊费用', '合 计', '预缴企业所得税', 'A/B-C', '项目①'),
              fc.string({ maxLength: 12 }),
            ),
            source: fc.constantFrom('tb' as const, 'manual' as const, 'legacy' as const),
          }),
          { maxLength: 20 },
        ),
        (raw) => {
          // 去重 rowId（反序列化保留首次出现者，是有意的容错行为）
          const seen = new Set<string>()
          const rows: DynamicAdjRow[] = []
          for (const r of raw) {
            const id = r.rowId.trim()
            if (!id || seen.has(id)) continue
            seen.add(id)
            rows.push({ rowId: id, label: normalizeLabel(r.label), source: r.source })
          }
          expect(deserializeRows(serializeRows(rows))).toEqual(rows)
        },
      ),
      { numRuns: 40 },
    )
  })

  it('accountCode 仅在有值时保留', () => {
    const rows: DynamicAdjRow[] = [
      { rowId: 'r-1', label: '待摊费用', source: 'tb', accountCode: '1901.01' },
      { rowId: 'r-2', label: '手工行', source: 'manual' },
    ]
    const back = deserializeRows(serializeRows(rows))
    expect(back[0].accountCode).toBe('1901.01')
    expect('accountCode' in back[1]).toBe(false)
  })

  it('损坏载荷不白屏：非 JSON / 非数组 / 缺字段一律跳过', () => {
    expect(deserializeRows('not json')).toEqual([])
    expect(deserializeRows('{"a":1}')).toEqual([])
    expect(deserializeRows('[]')).toEqual([])
    expect(deserializeRows(null)).toEqual([])
    expect(deserializeRows(123 as unknown)).toEqual([])
    expect(deserializeRows('[{"label":"无 id"},{"rowId":"r-1","label":"有"}]')).toEqual([
      { rowId: 'r-1', label: '有', source: 'manual' },
    ])
  })

  it('未知 source 归一为 manual（前向兼容）', () => {
    expect(deserializeRows('[{"rowId":"r-1","label":"x","source":"weird"}]')[0].source).toBe('manual')
  })

  it('rowId 重复时保留首次出现者', () => {
    const back = deserializeRows('[{"rowId":"r-1","label":"先"},{"rowId":"r-1","label":"后"}]')
    expect(back).toHaveLength(1)
    expect(back[0].label).toBe('先')
  })
})

// ─── 读值助手 ───────────────────────────────────────────────────────────────

describe('checklist_responses 三形态读值', () => {
  it('remark / conclusion / 裸字符串都能读', () => {
    const m = new Map<string, unknown>([
      ['a', { remark: '12.5' }],
      ['b', { conclusion: '7' }],
      ['c', '3'],
      ['d', { remark: '', conclusion: '9' }],
    ])
    expect(readNum(m, 'a')).toBe(12.5)
    expect(readNum(m, 'b')).toBe(7)
    expect(readNum(m, 'c')).toBe(3)
    expect(readNum(m, 'd')).toBe(9)
    expect(readNum(m, 'missing')).toBe(0)
    expect(readNum(m, 'a')).not.toBeNaN()
  })

  it('非数值 → 0；空 Map / null 安全', () => {
    const m = new Map<string, unknown>([['a', { remark: 'abc' }]])
    expect(readNum(m, 'a')).toBe(0)
    expect(readRaw(null, 'a')).toBe('')
    expect(readNum(undefined, 'a')).toBe(0)
  })
})

// ─── Property 6：历史固定行迁移不丢数 ───────────────────────────────────────

describe('历史固定行迁移（Property 6）', () => {
  it('rowId 沿用旧 rowKey → 既有字段键原样命中', () => {
    const responses = mapOf({
      'XX-9-alpha-unadj': '1000',
      'XX-9-gamma-remark': '有备注',
    })
    const rows = migrateLegacyFixedRows(SPEC, responses)
    expect(rows.map((r) => r.rowId)).toEqual(['alpha', 'gamma'])
    expect(rows.every((r) => r.source === 'legacy')).toBe(true)
    // 迁移后读值仍命中原键
    expect(readNum(responses, rowFieldItemId(SPEC, 'alpha', 'unadj'))).toBe(1000)
  })

  it('只迁「有数据」的行 —— 从未填过的固定行不占位（宁缺勿造）', () => {
    expect(migrateLegacyFixedRows(SPEC, mapOf({}))).toEqual([])
    // 全零也算无数据
    expect(migrateLegacyFixedRows(SPEC, mapOf({ 'XX-9-alpha-unadj': '0' }))).toEqual([])
    // 备注非空即算有数据
    expect(
      migrateLegacyFixedRows(SPEC, mapOf({ 'XX-9-beta-remark': 'x' })).map((r) => r.rowId),
    ).toEqual(['beta'])
    // 空白备注不算
    expect(migrateLegacyFixedRows(SPEC, mapOf({ 'XX-9-beta-remark': '   ' }))).toEqual([])
  })

  it('valueFields 之外的字段不触发迁移（声明式，非全量扫描）', () => {
    // `debit` 不在替身 spec 的 valueFields 里
    expect(migrateLegacyFixedRows(SPEC, mapOf({ 'XX-9-alpha-debit': '500' }))).toEqual([])
    expect(hasLegacyRowData(SPEC, mapOf({ 'XX-9-alpha-debit': '500' }), 'alpha')).toBe(false)
    expect(hasLegacyRowData(SPEC, mapOf({ 'XX-9-alpha-aje': '500' }), 'alpha')).toBe(true)
  })

  it('PBT：任意旧 rowKey 子集有值 → 每个有值行都出现在迁移结果中', () => {
    fc.assert(
      fc.property(
        fc.uniqueArray(fc.constantFrom('alpha', 'beta', 'gamma'), { maxLength: 3 }),
        fc.integer({ min: 1, max: 99999 }),
        (keys, amount) => {
          const entries: Record<string, string> = {}
          for (const k of keys) entries[`XX-9-${k}-unadj`] = String(amount)
          const rows = migrateLegacyFixedRows(SPEC, mapOf(entries))
          expect(new Set(rows.map((r) => r.rowId))).toEqual(new Set(keys))
        },
      ),
      { numRuns: 20 },
    )
  })

  it('resolveInitialRows：持久化清单优先于迁移', () => {
    const responses = mapOf({
      'XX-9-rows': serializeRows([row('r-x', '手工行')]),
      'XX-9-alpha-unadj': '1000',
    })
    const got = resolveInitialRows(SPEC, responses)
    expect(got.rows.map((r) => r.rowId)).toEqual(['r-x'])
    expect(got.migrated).toBe(false)
  })

  it('resolveInitialRows：无清单时迁移并标记需落库', () => {
    const got = resolveInitialRows(SPEC, mapOf({ 'XX-9-alpha-unadj': '1' }))
    expect(got.rows.map((r) => r.rowId)).toEqual(['alpha'])
    expect(got.migrated).toBe(true)
    // 两者都空 → 不标记（避免空清单反复落库）
    expect(resolveInitialRows(SPEC, mapOf({}))).toEqual({ rows: [], migrated: false })
  })
})

// ─── Property 8：四表 seed 宁缺勿造 ─────────────────────────────────────────

describe('四表库 seed（Property 8）', () => {
  it('空预填 → 空结果，绝不产生兜底行', () => {
    expect(seedRowsFromPrefill(SPEC, [])).toEqual({ rows: [], values: {} })
    expect(seedRowsFromPrefill(SPEC, null)).toEqual({ rows: [], values: {} })
    expect(seedRowsFromPrefill(SPEC, undefined, [row('r-1', '既有')]).rows).toHaveLength(1)
  })

  it('无名科目跳过，不塞「其他」兜底行', () => {
    const got = seedRowsFromPrefill(SPEC, [
      { name: '  ', closing_balance: 100 },
      { name: '待摊费用', opening_balance: 10, closing_balance: 20, code: '1901.01' },
    ], [], {}, seededRand(3))
    expect(got.rows).toHaveLength(1)
    expect(got.rows[0].label).toBe('待摊费用')
    expect(got.rows[0].source).toBe('tb')
    expect(got.rows[0].accountCode).toBe('1901.01')
    expect(Object.values(got.values)).toEqual(['10', '20'])
    expect(got.rows.some((r) => r.label === '其他')).toBe(false)
  })

  it('与现有行同名 → 复用该行，不新建（手工优先由调用方判定值覆盖）', () => {
    const existing = [row('legacy-1', '待摊费用', 'legacy')]
    const got = seedRowsFromPrefill(
      SPEC,
      [{ name: '待 摊 费 用', opening_balance: 5, closing_balance: 6 }],
      existing,
      {},
      seededRand(5),
    )
    expect(got.rows).toHaveLength(1)
    expect(got.rows[0].rowId).toBe('legacy-1')
    expect(got.values['XX-9-legacy-1-begin']).toBe('5')
    expect(got.values['XX-9-legacy-1-unadj']).toBe('6')
  })

  it('字段名可由调用方声明（不同循环列名不同）', () => {
    const got = seedRowsFromPrefill(
      SPEC,
      [{ name: '甲', opening_balance: 1, closing_balance: 2 }],
      [],
      { opening: 'open', closing: 'close' },
      seededRand(9),
    )
    const id = got.rows[0].rowId
    expect(got.values[`XX-9-${id}-open`]).toBe('1')
    expect(got.values[`XX-9-${id}-close`]).toBe('2')
  })

  it('缺失金额按 0 处理，不产生 NaN', () => {
    const got = seedRowsFromPrefill(SPEC, [{ name: '甲' }], [], {}, seededRand(11))
    expect(Object.values(got.values)).toEqual(['0', '0'])
  })
})

// ─── Property 7：删除清理干净 ───────────────────────────────────────────────

describe('删除行（Property 7）', () => {
  const responses = mapOf({
    'XX-9-r-1-begin': '100',
    'XX-9-r-1-unadj': '200',
    'XX-9-r-1-remark': 'x',
    'XX-9-r-2-unadj': '300',
    'XX-9-rows': '[]',
  })

  it('收集该行全部字段键，不误伤其它行与清单键', () => {
    expect(collectRowItemIds(SPEC, responses, 'r-1')).toEqual([
      'XX-9-r-1-begin', 'XX-9-r-1-remark', 'XX-9-r-1-unadj',
    ])
    expect(collectRowItemIds(SPEC, responses, 'r-2')).toEqual(['XX-9-r-2-unadj'])
    expect(collectRowItemIds(SPEC, responses, 'nope')).toEqual([])
  })

  it('删除后清单少一行，返回待清理键；其它行不受影响', () => {
    const rows = [row('r-1', '甲'), row('r-2', '乙')]
    const got = dropRow(SPEC, rows, responses, 'r-1')
    expect(got.rows.map((r) => r.rowId)).toEqual(['r-2'])
    expect(got.removedItemIds).toHaveLength(3)
    expect(got.removedItemIds.every((k) => k.startsWith('XX-9-r-1-'))).toBe(true)
    expect(got.removedItemIds).not.toContain('XX-9-r-2-unadj')
    expect(got.removedItemIds).not.toContain('XX-9-rows')
  })

  it('删除不存在的行 → 幂等空操作', () => {
    const rows = [row('r-1', '甲')]
    expect(dropRow(SPEC, rows, responses, 'nope')).toEqual({ rows, removedItemIds: [] })
  })

  it('🔴 前缀不会跨行误伤：r-1 与 r-10 是不同行', () => {
    const m = mapOf({ 'XX-9-r-1-unadj': '1', 'XX-9-r-10-unadj': '2' })
    // rowKeyPrefix 以 `-` 收尾 → `XX-9-r-1-` 不匹配 `XX-9-r-10-unadj`
    expect(collectRowItemIds(SPEC, m, 'r-1')).toEqual(['XX-9-r-1-unadj'])
    expect(collectRowItemIds(SPEC, m, 'r-10')).toEqual(['XX-9-r-10-unadj'])
  })
})

// ─── 改名 / 追加 / 外来行警示 ───────────────────────────────────────────────

describe('改名 / 追加 / 外来行警示', () => {
  it('改名只影响目标行，空名不改', () => {
    const rows = [row('r-1', '甲'), row('r-2', '乙')]
    expect(renameRowLabel(rows, 'r-1', ' 丙 ').map((r) => r.label)).toEqual(['丙', '乙'])
    expect(renameRowLabel(rows, 'r-1', '   ')).toEqual(rows)
    expect(renameRowLabel(rows, 'nope', '丁')).toEqual(rows)
  })

  it('追加手工行标记 source=manual 且 id 唯一', () => {
    const got = appendManualRow([row('r-1', '甲')], ' 乙 ', seededRand(13))
    expect(got.rows).toHaveLength(2)
    expect(got.row.label).toBe('乙')
    expect(got.row.source).toBe('manual')
    expect(got.row.rowId).not.toBe('r-1')
  })

  it('外来行警示只对迁移来的历史行生效（按 rowId 命中）', () => {
    expect(foreignRowWarning(SPEC, row('beta', '乙项目', 'legacy'))).toBe('乙项目属于别的报表行')
    // 审计师自己新建的同名行不误报
    expect(foreignRowWarning(SPEC, row('r-9', '乙项目', 'manual'))).toBeNull()
    expect(foreignRowWarning(SPEC, row('alpha', '甲项目', 'legacy'))).toBeNull()
    expect(foreignRowWarning(SPEC, null)).toBeNull()
  })
})

// ─── 反向自检：共享件不得含循环专属常量 ─────────────────────────────────────

describe('共享件与循环解耦（反向自检）', () => {
  const src = readFileSync(
    resolve(__dirname, '../shared/dynamicAdjudicationRows.ts'),
    'utf-8',
  )

  it('不得出现具体循环的 itemId 前缀 / 科目码 / 行名', () => {
    // 断言非空防正则空转
    expect(src.length).toBeGreaterThan(1000)
    const body = src.replace(/\/\*\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '')
    for (const forbidden of ["'K2-1'", "'K1-1'", "'1901'", "'1231'", "'其他'", 'contract-cost']) {
      expect(body).not.toContain(forbidden)
    }
  })

  it('不 import Vue（纯函数模块，可在任何上下文调用）', () => {
    expect(src).not.toMatch(/from ['"]vue['"]/)
    expect(src).not.toMatch(/from ['"]element-plus['"]/)
  })
})
