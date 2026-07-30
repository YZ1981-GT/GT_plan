/**
 * 孤儿子表名差集契约。
 *
 * spec: disclosure-columns-coverage-rollout R7 — Property 9（差集正确且不误删）
 */
import { describe, expect, it } from 'vitest'
import {
  buildRemovedTableKeys,
  dataTableNames,
  isOwnedTableName,
  noteExistingTableNames,
  seedSyncedTableBaseline,
} from '../composables/disclosureSyncedTables'
import {
  buildD2SyncPayload,
  D2_LISTED_OBSOLETE_TABLE_KEYS,
  D2_PORTFOLIO_TABLE_PREFIX,
  D2_SOE_PRIOR_SUFFIX,
  D2_TABLE_NAMES,
  D2_TABLE_NAMESPACE,
  portfolioTableName,
  type D2DisclosureSnapshot,
} from '../composables/d2NoteSectionMap'

/** 最小快照：只为跑通载荷构建，金额一律 0（本文件只断言表名，不断言数值） */
const EMPTY_SNAPSHOT: D2DisclosureSnapshot = {
  agingRows: [],
  classRows: [],
  classWideEndRows: [],
  classWidePriorRows: [],
  individualRows: [],
  portfolios: [],
  otherPortfolioRows: [],
  movement: { priorBalance: 0, provision: 0, reversal: 0, writeOff: 0, transfer: 0, other: 0, endBalance: 0 },
  movementByCategory: [],
  reversalRows: [],
  writeOffAmount: 0,
  writeOffRows: [],
  top5Rows: [],
  derecognizedRows: [],
  continuedInvolvementRows: [],
  notes: {},
}

describe('dataTableNames', () => {
  it('排除 `_` 元数据键，保留顺序', () => {
    expect(dataTableNames({
      表A: [],
      _note_texts: [],
      表B: [],
      _removed_table_keys: [],
      _manual_override: true,
    })).toEqual(['表A', '表B'])
  })

  it('空 / 非对象入参返回空数组', () => {
    expect(dataTableNames(null)).toEqual([])
    expect(dataTableNames(undefined)).toEqual([])
    expect(dataTableNames({})).toEqual([])
  })
})

describe('buildRemovedTableKeys', () => {
  it('Property 9 上次已同步 − 本次推送 = 待删除（改名场景）', () => {
    expect(buildRemovedTableKeys({
      previouslySynced: ['组合计提项目：应收中央企业客户', '（1）按账龄披露应收账款'],
      pushed: ['组合计提项目：应收政府客户', '（1）按账龄披露应收账款'],
    })).toEqual(['组合计提项目：应收中央企业客户'])
  })

  it('Property 9 删除场景：整张分表消失', () => {
    expect(buildRemovedTableKeys({
      previouslySynced: ['组合计提项目：A', '组合计提项目：B'],
      pushed: ['组合计提项目：A'],
    })).toEqual(['组合计提项目：B'])
  })

  it('Property 9 结果与本次推送无交集（绝不误删现存表）', () => {
    const pushed = ['表A', '表B', '表C']
    const removed = buildRemovedTableKeys({
      previouslySynced: ['表A', '表B', '表旧'],
      legacyObsolete: ['表C', '表遗留'],
      pushed,
    })
    for (const k of removed) expect(pushed).not.toContain(k)
    expect(removed).toEqual(['表旧', '表遗留'])
  })

  it('Property 9 R7.4 首次启用（无持久化）仍清理历史遗留静态种子', () => {
    expect(buildRemovedTableKeys({
      previouslySynced: [],
      legacyObsolete: ['按坏账计提方法分类披露（上年年末金额）', '按单项计提坏账准备的应收账款（上年年末金额）'],
      pushed: ['按坏账计提方法分类披露'],
    })).toEqual([
      '按坏账计提方法分类披露（上年年末金额）',
      '按单项计提坏账准备的应收账款（上年年末金额）',
    ])
  })

  it('Property 9 去重且顺序稳定（先 previouslySynced 后 legacyObsolete）', () => {
    expect(buildRemovedTableKeys({
      previouslySynced: ['X', 'Y', 'X'],
      legacyObsolete: ['Y', 'Z'],
      pushed: [],
    })).toEqual(['X', 'Y', 'Z'])
  })

  it('Property 9 稳态：上次已同步 = 本次推送 → 无待删除', () => {
    const names = ['表A', '表B']
    expect(buildRemovedTableKeys({ previouslySynced: names, pushed: names })).toEqual([])
  })

  it('过滤空白与元数据键，容忍 null 入参', () => {
    expect(buildRemovedTableKeys({
      previouslySynced: ['', '  ', '_note_texts', '表旧'],
      legacyObsolete: null,
      pushed: [],
    })).toEqual(['表旧'])
  })
})

describe('isOwnedTableName — 命名空间谓词（R7.5）', () => {
  const spec = {
    known: ['（1）按账龄披露应收账款', '（2）按坏账准备计提方法分类披露应收账款'],
    prefixes: ['组合计提项目：'],
    suffixes: ['（续：期初数）'],
  }

  it('固定表名命中', () => {
    expect(isOwnedTableName('（1）按账龄披露应收账款', spec)).toBe(true)
  })

  it('动态前缀命中（组合分表按审计师命名）', () => {
    expect(isOwnedTableName('组合计提项目：应收中央企业客户', spec)).toBe(true)
    expect(isOwnedTableName('组合计提项目：任意新组合', spec)).toBe(true)
    // 只有前缀没有内容 → 不算（避免把前缀本身当表名）
    expect(isOwnedTableName('组合计提项目：', spec)).toBe(false)
  })

  it('续表 = 已知表名 + 后缀才命中（不吞别的底稿续表）', () => {
    expect(isOwnedTableName('（2）按坏账准备计提方法分类披露应收账款（续：期初数）', spec)).toBe(true)
    expect(isOwnedTableName('别的底稿的表（续：期初数）', spec)).toBe(false)
  })

  it('Property 10 命名空间外的表名一律不认（别的底稿推的表不得被误删）', () => {
    for (const name of [
      '存货跌价准备',
      '固定资产情况',
      '账龄超过1年的重要预收款项',
      '',
      '   ',
      '_note_texts',
      '_sub_table_columns',
    ]) {
      expect(isOwnedTableName(name, spec), `${name} 不应被认领`).toBe(false)
    }
  })

  it('空 spec 不认领任何表名', () => {
    expect(isOwnedTableName('任意表', {})).toBe(false)
  })
})

describe('noteExistingTableNames', () => {
  it('并集 sub_table_data 与 _sub_table_columns 的键，排除元数据', () => {
    expect(noteExistingTableNames({
      sub_table_data: { 表A: [], _note_texts: [], 表B: [] },
      _sub_table_columns: { 表B: [], 表C: [] },
      _tables: [{ name: '表D' }],
      rows: [],
    })).toEqual(['表A', '表B', '表C'])
  })

  it('_tables 快照名不纳入（removed 键删不动它，纳入只会虚报）', () => {
    expect(noteExistingTableNames({ _tables: [{ name: '表快照' }] })).toEqual([])
  })

  it('非法入参返回空数组', () => {
    expect(noteExistingTableNames(null)).toEqual([])
    expect(noteExistingTableNames('x')).toEqual([])
    expect(noteExistingTableNames({ sub_table_data: [] })).toEqual([])
  })
})

describe('seedSyncedTableBaseline — 首次同步基线播种（R7.5）', () => {
  const spec = {
    known: ['（1）按账龄披露应收账款'],
    prefixes: ['组合计提项目：'],
  }

  it('Property 10 只播种命名空间内的现存表名', () => {
    const seeded = seedSyncedTableBaseline({
      sub_table_data: {
        '（1）按账龄披露应收账款': [],
        '组合计提项目：应收中央企业客户': [],
        存货跌价准备: [],
        _note_texts: [],
      },
    }, spec)
    expect(seeded).toEqual(['（1）按账龄披露应收账款', '组合计提项目：应收中央企业客户'])
  })

  it('上线前残留的孤儿表进入基线 → 本轮推送不含它即被清理', () => {
    const baseline = seedSyncedTableBaseline({
      sub_table_data: {
        '（1）按账龄披露应收账款': [],
        '组合计提项目：应收中央企业客户': [],
      },
    }, spec)
    const removed = buildRemovedTableKeys({
      previouslySynced: baseline,
      pushed: ['（1）按账龄披露应收账款', '组合计提项目：应收政府客户'],
    })
    expect(removed).toEqual(['组合计提项目：应收中央企业客户'])
  })

  it('附注为空 / 尚未生成 → 播种空基线（不产出 removed 键）', () => {
    expect(seedSyncedTableBaseline(null, spec)).toEqual([])
    expect(seedSyncedTableBaseline({ rows: [] }, spec)).toEqual([])
  })
})

describe('D2_TABLE_NAMESPACE — D2 命名空间声明', () => {
  it('国企含全部固定表名 + 组合前缀 + 期初数续表后缀', () => {
    expect(D2_TABLE_NAMESPACE.soe.known).toContain(D2_TABLE_NAMES.soe.aging)
    expect(D2_TABLE_NAMESPACE.soe.known).toContain(D2_TABLE_NAMES.soe.continuedInvolvement)
    expect(D2_TABLE_NAMESPACE.soe.prefixes).toEqual([D2_PORTFOLIO_TABLE_PREFIX])
    expect(D2_TABLE_NAMESPACE.soe.suffixes).toEqual([D2_SOE_PRIOR_SUFFIX])
  })

  it('上市把历史遗留静态旧名一并纳入命名空间（否则播不进基线）', () => {
    for (const legacy of D2_LISTED_OBSOLETE_TABLE_KEYS) {
      expect(isOwnedTableName(legacy, D2_TABLE_NAMESPACE.listed)).toBe(true)
    }
  })

  it('本次实际推送的每张表都在自己的命名空间内（谓词不漏认）', () => {
    for (const variant of ['listed', 'soe'] as const) {
      const payload = buildD2SyncPayload(variant, 'wp-1', null, EMPTY_SNAPSHOT)
      for (const name of dataTableNames(payload.sub_table_data as Record<string, unknown>)) {
        expect(
          isOwnedTableName(name, D2_TABLE_NAMESPACE[variant]),
          `${variant} 推送的「${name}」不在命名空间内 → 基线播种会漏掉它`,
        ).toBe(true)
      }
    }
  })

  it('组合分表动态名也在命名空间内', () => {
    const payload = buildD2SyncPayload('soe', 'wp-1', null, {
      ...EMPTY_SNAPSHOT,
      portfolios: [{ name: '应收民营企业客户', rows: [] }],
    })
    const names = dataTableNames(payload.sub_table_data as Record<string, unknown>)
    expect(names).toContain(portfolioTableName('应收民营企业客户'))
    for (const name of names) {
      expect(isOwnedTableName(name, D2_TABLE_NAMESPACE.soe)).toBe(true)
    }
  })
})
