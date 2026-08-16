/**
 * l2NoteSectionMap 守卫 —— L2 应付利息推送到 K3 章节的载荷契约。
 *
 * spec: .kiro/specs/l-cycle-extraction-formula-and-disclosure-completion/
 *       Property 9, 10, 14, 27
 *
 * 🔴 本文件由 2026-08-15 收口复盘新增：Task 16 接线后从未验证载荷 label 是否
 *    与附注模板行字面匹配，实测发现两处不一致（半角斜杠 vs 反斜杠 / 其他 vs 其他利息）
 *    ⇒ 推过去会让附注表凭空多行。加判据钉死归一化与过滤。
 */
import { describe, it, expect } from 'vitest'
import {
  L2_NOTE_SECTION,
  L2_DISCLOSURE_SHEET_NAME,
  L2_LISTED_SUBTABLE,
  L2_SOE_SUBTABLE,
  L2_LISTED_INTEREST_ROWS,
  L2_SOE_INTEREST_ROWS,
  buildL2SyncPayload,
  buildL2ListedColumns,
  buildL2SoeColumns,
} from '../l2NoteSectionMap'

/** 底稿侧 useL2Disclosure 的真实行标签（半角斜杠 + 「其他」，逐字复刻） */
const WORKPAPER_LABELS = [
  '分期付息到期还本的长期借款利息',
  '企业债券利息',
  '短期借款应付利息',
  '划分为金融负债的优先股/永续债利息', // ← 半角斜杠，与模板反斜杠不同
  '其中：工具1',
  '工具2',
  '其他', // ← soe 模板叫「其他利息」，listed 模板无此行
  '合计',
]

function wpRows() {
  return WORKPAPER_LABELS.map((label, i) => ({
    label,
    endAmount: (i + 1) * 100,
    priorAmount: (i + 1) * 50,
  }))
}

describe('L2 章节号与 sheet 名', () => {
  it('落点是 K3 章节（五、42 / 八、42）', () => {
    expect(L2_NOTE_SECTION.listed).toBe('五、42')
    expect(L2_NOTE_SECTION.soe).toBe('八、42')
  })

  it('sheet 名逐字取源 xlsx（「信息」在后）', () => {
    expect(L2_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露（上市公司）信息')
    expect(L2_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露（国企）信息')
  })
})

describe('Property 10：两版行集不对称且不得统一', () => {
  it('listed 7 行含「其中：工具1/工具2」', () => {
    expect(L2_LISTED_INTEREST_ROWS).toHaveLength(7)
    expect(L2_LISTED_INTEREST_ROWS).toContain('其中：工具1')
    expect(L2_LISTED_INTEREST_ROWS).toContain('工具2')
    expect(L2_LISTED_INTEREST_ROWS).not.toContain('其他利息')
  })

  it('soe 6 行含「其他利息」、无工具行', () => {
    expect(L2_SOE_INTEREST_ROWS).toHaveLength(6)
    expect(L2_SOE_INTEREST_ROWS).toContain('其他利息')
    expect(L2_SOE_INTEREST_ROWS).not.toContain('其中：工具1')
  })

  it('两版行集不相等（防「顺手对齐」）', () => {
    expect(L2_LISTED_INTEREST_ROWS).not.toEqual(L2_SOE_INTEREST_ROWS)
  })

  it('优先股行用反斜杠（与附注模板 rows[].label 逐字一致）', () => {
    const listedRow = L2_LISTED_INTEREST_ROWS.find((r) => r.includes('优先股'))
    const soeRow = L2_SOE_INTEREST_ROWS.find((r) => r.includes('优先股'))
    expect(listedRow).toBe('划分为金融负债的优先股\\永续债利息')
    expect(soeRow).toBe('划分为金融负债的优先股\\永续债利息')
    // 反向：不得是半角斜杠（那是底稿 UI 字面，投影器匹配不上）
    expect(listedRow).not.toContain('优先股/永续债')
  })
})

describe('label 归一化（2026-08-15 复盘新增）', () => {
  it('半角斜杠 → 反斜杠（两版都要）', () => {
    for (const variant of ['listed', 'soe'] as const) {
      const key = variant === 'listed' ? L2_LISTED_SUBTABLE.interest : L2_SOE_SUBTABLE.interest
      const payload = buildL2SyncPayload(variant, wpRows(), [])
      const labels = payload.sub_table_data[key].map((r) => r.label)
      expect(labels).toContain('划分为金融负债的优先股\\永续债利息')
      expect(labels).not.toContain('划分为金融负债的优先股/永续债利息')
    }
  })

  it('soe：底稿「其他」→ 模板「其他利息」', () => {
    const payload = buildL2SyncPayload('soe', wpRows(), [])
    const labels = payload.sub_table_data[L2_SOE_SUBTABLE.interest].map((r) => r.label)
    expect(labels).toContain('其他利息')
    expect(labels).not.toContain('其他')
  })

  it('listed：模板无「其他」行 ⇒ 该行被丢弃（附注表不多行）', () => {
    const payload = buildL2SyncPayload('listed', wpRows(), [])
    const labels = payload.sub_table_data[L2_LISTED_SUBTABLE.interest].map((r) => r.label)
    expect(labels).not.toContain('其他')
    expect(labels).not.toContain('其他利息')
  })

  it('推送行数不超过模板行数（结构性防多行）', () => {
    const listed = buildL2SyncPayload('listed', wpRows(), [])
    const soe = buildL2SyncPayload('soe', wpRows(), [])
    expect(
      listed.sub_table_data[L2_LISTED_SUBTABLE.interest].length,
    ).toBeLessThanOrEqual(L2_LISTED_INTEREST_ROWS.length)
    expect(soe.sub_table_data[L2_SOE_SUBTABLE.interest].length).toBeLessThanOrEqual(
      L2_SOE_INTEREST_ROWS.length,
    )
  })

  it('每个推送行的 label 都在模板行集内（无孤儿行）', () => {
    const cases: Array<['listed' | 'soe', string, readonly string[]]> = [
      ['listed', L2_LISTED_SUBTABLE.interest, L2_LISTED_INTEREST_ROWS],
      ['soe', L2_SOE_SUBTABLE.interest, L2_SOE_INTEREST_ROWS],
    ]
    for (const [variant, key, allowed] of cases) {
      const payload = buildL2SyncPayload(variant, wpRows(), [])
      for (const row of payload.sub_table_data[key]) {
        expect(allowed, `${variant} 推了模板不存在的行 ${row.label}`).toContain(row.label)
      }
    }
  })
})

describe('Property 9 / 27：只碰自己的两张子表', () => {
  const K3_TABLES = [
    '其他应付款',
    '应付股利',
    '重要的超过1年未支付的应付股利',
    '其他应付款（按款项性质列示）',
    '按款项性质列示',
    '其中，账龄超过1年的重要其他应付款',
    '账龄超过1年的重要其他应付款项',
  ]

  it('载荷键集恰为「应付利息」+ 逾期表', () => {
    const listed = buildL2SyncPayload('listed', wpRows(), [])
    expect(Object.keys(listed.sub_table_data).sort()).toEqual(
      [L2_LISTED_SUBTABLE.interest, L2_LISTED_SUBTABLE.overdue].sort(),
    )
    const soe = buildL2SyncPayload('soe', wpRows(), [])
    expect(Object.keys(soe.sub_table_data).sort()).toEqual(
      [L2_SOE_SUBTABLE.interest, L2_SOE_SUBTABLE.overdue].sort(),
    )
  })

  it('不含任何 K3 负责的子表名（表名零交集）', () => {
    for (const variant of ['listed', 'soe'] as const) {
      const keys = Object.keys(buildL2SyncPayload(variant, wpRows(), []).sub_table_data)
      for (const k3 of K3_TABLES) {
        expect(keys, `${variant} 越权推了 K3 的表 ${k3}`).not.toContain(k3)
      }
    }
  })

  it('不声明 _removed_table_keys（不得删 K3 的表）', () => {
    for (const variant of ['listed', 'soe'] as const) {
      const sub = buildL2SyncPayload(variant, wpRows(), []).sub_table_data as Record<
        string,
        unknown
      >
      expect(sub._removed_table_keys).toBeUndefined()
    }
  })

  it('两版逾期表名不同（soe 带「已」，禁统一）', () => {
    expect(L2_LISTED_SUBTABLE.overdue).toBe('重要的逾期未付利息')
    expect(L2_SOE_SUBTABLE.overdue).toBe('重要的已逾期未支付的利息情况')
    expect(L2_LISTED_SUBTABLE.overdue).not.toBe(L2_SOE_SUBTABLE.overdue)
  })
})

describe('列定义契约', () => {
  it('两版都为单级表头且显式 flat', () => {
    for (const cols of [buildL2ListedColumns(), buildL2SoeColumns()]) {
      for (const [name, defs] of Object.entries(cols)) {
        expect(defs.some((c) => c.flat), `${name} 未表态 flat`).toBe(true)
        expect(defs.some((c) => c.group), `${name} 不应有 group`).toBe(false)
        expect(defs[0].is_label, `${name} 首列缺 is_label`).toBe(true)
      }
    }
  })

  it('列 key 逐字对齐模板（label/end_amount/prior_amount）', () => {
    const listed = buildL2ListedColumns()[L2_LISTED_SUBTABLE.interest]
    expect(listed.map((c) => c.key)).toEqual(['label', 'end_amount', 'prior_amount'])
    const soe = buildL2SoeColumns()[L2_SOE_SUBTABLE.interest]
    expect(soe.map((c) => c.key)).toEqual(['label', 'end_amount', 'prior_amount'])
  })

  it('逾期表列 key 为 label/overdue_amount/overdue_reason', () => {
    for (const [cols, key] of [
      [buildL2ListedColumns(), L2_LISTED_SUBTABLE.overdue],
      [buildL2SoeColumns(), L2_SOE_SUBTABLE.overdue],
    ] as const) {
      expect(cols[key].map((c) => c.key)).toEqual([
        'label',
        'overdue_amount',
        'overdue_reason',
      ])
    }
  })

  it('列定义键集 == 载荷子表键集（无孤儿 columns）', () => {
    for (const variant of ['listed', 'soe'] as const) {
      const payload = buildL2SyncPayload(variant, wpRows(), [])
      expect(Object.keys(payload._sub_table_columns).sort()).toEqual(
        Object.keys(payload.sub_table_data).sort(),
      )
    }
  })
})

describe('逾期表载荷', () => {
  it('借款单位名不归一化（自由文本，不参与模板行匹配）', () => {
    const payload = buildL2SyncPayload('soe', [], [
      { label: '某银行/分行', overdueAmount: 1000, overdueReason: '资金紧张' },
    ])
    const rows = payload.sub_table_data[L2_SOE_SUBTABLE.overdue]
    expect(rows[0].label).toBe('某银行/分行')
    expect(rows[0].overdue_amount).toBe(1000)
    expect(rows[0].overdue_reason).toBe('资金紧张')
  })

  it('无逾期数据时推空数组（不推 undefined）', () => {
    const payload = buildL2SyncPayload('listed', wpRows(), [])
    expect(payload.sub_table_data[L2_LISTED_SUBTABLE.overdue]).toEqual([])
  })
})
