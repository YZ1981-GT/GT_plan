/**
 * b22aRowIdentity 守卫 — B22A 稳定行身份（BC-53 行身份缺陷族）。
 *
 * spec: b-cycle-sync-foundation-and-first-canary
 *
 * 🔴 核心判据：删中间行后，剩余行的身份与内容**必须**保持绑定。
 *    legacy shift 搬迁实现下这条必红（值搬家 ⇒ 身份与内容脱钩）。
 */
import { describe, it, expect } from 'vitest'
import {
  ROW_IDENTITY_KEY,
  B22A_ROW_FIELDS,
  rowScope,
  rowsItemId,
  makeRowId,
  legacyRowId,
  legacyFieldItemId,
  legacyCountItemId,
  parseRows,
  normalizeRow,
  serializeRows,
  resequence,
  isBlankRow,
  migrateLegacyGroup,
  type B22ARow,
  type LegacyReader,
} from '../composables/b22aRowIdentity'

describe('行身份字段名与 D4 后端一致', () => {
  it('ROW_IDENTITY_KEY 必须是 rowId（后端 ROW_IDENTITY_STORE_KEY 同名）', () => {
    // 🔴 改这个常量 = 与后端 store_row_identity() 脱钩 ⇒ 投影必拒
    expect(ROW_IDENTITY_KEY).toBe('rowId')
  })

  it('受管字段集恰 6 项（与 legacy generateItemId 的 field 联合类型一致）', () => {
    expect([...B22A_ROW_FIELDS]).toEqual([
      'point', 'desc', 'method', 'conclusion', 'ref', 'nochange',
    ])
  })
})

describe('scope 与 item_id 生成', () => {
  it('无 subPanel → T{tab}', () => {
    expect(rowScope(1)).toBe('T1')
    expect(rowsItemId(1)).toBe('B22A-T1-rows')
  })

  it('有 subPanel → T{tab}-{subPanel}', () => {
    expect(rowScope(4, 'itgc')).toBe('T4-itgc')
    expect(rowsItemId(4, 'itgc')).toBe('B22A-T4-IT-itgc-rows')
  })

  it('item_id 保持 B22A- 前缀（真库既有 LIKE 查询仍命中）', () => {
    expect(rowsItemId(2)).toMatch(/^B22A-/)
    expect(rowsItemId(2, 'mo')).toMatch(/^B22A-/)
  })
})

describe('makeRowId — 稳定且唯一', () => {
  it('含 scope，可从 id 读出归属', () => {
    const id = makeRowId('T1')
    expect(id).toContain('T1')
    expect(id.startsWith('B22A-')).toBe(true)
  })

  it('连续生成不碰撞（同毫秒也靠短随机区分）', () => {
    const ids = new Set<string>()
    for (let i = 0; i < 200; i++) ids.add(makeRowId('T1'))
    expect(ids.size).toBe(200)
  })
})

describe('parseRows / normalizeRow — legacy 兼容不白屏', () => {
  it('空/非法 remark → 空数组（渲染侧 fail soft）', () => {
    expect(parseRows(null, 'T1')).toEqual([])
    expect(parseRows('', 'T1')).toEqual([])
    expect(parseRows('not json', 'T1')).toEqual([])
    expect(parseRows('{"a":1}', 'T1')).toEqual([]) // 非数组
  })

  it('缺 rowId 的行按下标补发稳定串（对齐 D4 legacy 兜底）', () => {
    const rows = parseRows('[{"point":"甲"},{"point":"乙"}]', 'T1')
    expect(rows).toHaveLength(2)
    expect(rows[0].rowId).toBe(legacyRowId('T1', 0))
    expect(rows[1].rowId).toBe(legacyRowId('T1', 1))
    // 🔴 补的是稳定串，不是留空、也不是裸下标
    expect(rows[0].rowId).toContain('legacy')
  })

  it('已有 rowId 的行原样保留（不被覆盖）', () => {
    const rows = parseRows('[{"rowId":"KEEP-ME","point":"甲"}]', 'T1')
    expect(rows[0].rowId).toBe('KEEP-ME')
  })

  it('seq 缺失或非法时按位置补（1-based）', () => {
    const rows = parseRows('[{"point":"甲"},{"seq":"x","point":"乙"}]', 'T1')
    expect(rows[0].seq).toBe(1)
    expect(rows[1].seq).toBe(2)
  })

  it('normalizeRow 对非对象输入不抛', () => {
    expect(normalizeRow(null, 'T1', 0).rowId).toBe(legacyRowId('T1', 0))
    expect(normalizeRow(42, 'T1', 1).seq).toBe(2)
  })
})

describe('🔴 删中间行：身份与内容保持绑定（legacy shift 实现下必红）', () => {
  function threeRows(): B22ARow[] {
    return [
      { rowId: 'R-A', seq: 1, point: '甲', conclusion: '有效' },
      { rowId: 'R-B', seq: 2, point: '乙', conclusion: '设计无效' },
      { rowId: 'R-C', seq: 3, point: '丙', conclusion: '未实施' },
    ]
  }

  it('摘除中间行后，剩余两行的 rowId ↔ point 对应关系不变', () => {
    const rows = threeRows()
    const after = resequence(rows.filter((r) => r.rowId !== 'R-B'))

    expect(after).toHaveLength(2)
    // 身份保持
    expect(after.map((r) => r.rowId)).toEqual(['R-A', 'R-C'])
    // 内容跟着身份走，没有"搬家"
    expect(after.find((r) => r.rowId === 'R-A')?.point).toBe('甲')
    expect(after.find((r) => r.rowId === 'R-C')?.point).toBe('丙')
    // conclusion 同样不串台（legacy shift 下 R-C 会拿到 R-B 的值）
    expect(after.find((r) => r.rowId === 'R-C')?.conclusion).toBe('未实施')
  })

  it('seq 重排为连续，但不参与身份判定', () => {
    const after = resequence(threeRows().filter((r) => r.rowId !== 'R-A'))
    expect(after.map((r) => r.seq)).toEqual([1, 2])
    // seq 变了，身份没变
    expect(after[0].rowId).toBe('R-B')
    expect(after[0].point).toBe('乙')
  })

  it('插入中间行不影响既有行身份', () => {
    const rows = threeRows()
    const inserted: B22ARow = { rowId: 'R-NEW', seq: 0, point: '新' }
    const after = resequence([rows[0], inserted, rows[1], rows[2]])

    expect(after.map((r) => r.rowId)).toEqual(['R-A', 'R-NEW', 'R-B', 'R-C'])
    expect(after.find((r) => r.rowId === 'R-B')?.point).toBe('乙')
    expect(after.find((r) => r.rowId === 'R-C')?.point).toBe('丙')
  })
})

describe('serializeRows ↔ parseRows 往返', () => {
  it('往返后行身份与字段值逐值一致', () => {
    const rows: B22ARow[] = [
      { rowId: 'R-1', seq: 1, point: '甲', desc: '描述', conclusion: '有效' },
      { rowId: 'R-2', seq: 2, point: '乙', attrs: { frequency: '每月' } },
    ]
    const back = parseRows(serializeRows(rows), 'T1')
    expect(back).toHaveLength(2)
    expect(back[0].rowId).toBe('R-1')
    expect(back[0].conclusion).toBe('有效')
    expect(back[1].attrs).toEqual({ frequency: '每月' })
  })
})

describe('isBlankRow — 占位空行识别', () => {
  it('除 rowId/seq 外全空 → true', () => {
    expect(isBlankRow({ rowId: 'R', seq: 1 })).toBe(true)
    expect(isBlankRow({ rowId: 'R', seq: 1, point: '   ' })).toBe(true)
  })

  it('任一受管字段非空 → false', () => {
    expect(isBlankRow({ rowId: 'R', seq: 1, point: '甲' })).toBe(false)
    expect(isBlankRow({ rowId: 'R', seq: 1, conclusion: '有效' })).toBe(false)
  })
})

describe('migrateLegacyGroup — 存量迁移只改键形状不改值', () => {
  /** 造一个 legacy 读取器：3 行 × 各字段。 */
  function makeReader(): LegacyReader {
    const store = new Map<string, {
      conclusion?: string | null
      remark?: string | null
      wp_ref?: string | null
    }>()
    // 第 1 行
    store.set('B22A-T1-item-1-point', { remark: '管理层诚信' })
    store.set('B22A-T1-item-1-conclusion', { conclusion: '有效' })
    store.set('B22A-T1-item-1-attrs', { remark: '{"frequency":"每月"}' })
    // 第 2 行
    store.set('B22A-T1-item-2-point', { remark: '治理层独立性' })
    store.set('B22A-T1-item-2-conclusion', { conclusion: '设计无效' })
    store.set('B22A-T1-item-2-desc', { remark: '未设置独立董事' })
    // 第 3 行（只有 point）
    store.set('B22A-T1-item-3-point', { remark: '组织架构' })

    return {
      getCount: () => 3,
      getField: (id) => store.get(id),
    }
  }

  it('迁移后行数等于 legacy count', () => {
    const rows = migrateLegacyGroup(makeReader(), 1)
    expect(rows).toHaveLength(3)
  })

  it('每行获得稳定 rowId，且按原顺序', () => {
    const rows = migrateLegacyGroup(makeReader(), 1)
    expect(rows[0].rowId).toBe(legacyRowId('T1', 1))
    expect(rows[2].rowId).toBe(legacyRowId('T1', 3))
    expect(rows.map((r) => r.seq)).toEqual([1, 2, 3])
  })

  it('remark 型字段取 remark，conclusion 型取 conclusion（语义不混）', () => {
    const rows = migrateLegacyGroup(makeReader(), 1)
    expect(rows[0].point).toBe('管理层诚信')
    expect(rows[0].conclusion).toBe('有效')
    expect(rows[1].desc).toBe('未设置独立董事')
    expect(rows[1].conclusion).toBe('设计无效')
  })

  it('attrs 从 -attrs 的 remark 解析为对象', () => {
    const rows = migrateLegacyGroup(makeReader(), 1)
    expect(rows[0].attrs).toEqual({ frequency: '每月' })
  })

  it('缺字段的行不报错，只是该字段缺省', () => {
    const rows = migrateLegacyGroup(makeReader(), 1)
    expect(rows[2].point).toBe('组织架构')
    expect(rows[2].conclusion).toBeUndefined()
    expect(rows[2].attrs).toBeUndefined()
  })

  it('非法 attrs JSON 不影响其余字段迁移', () => {
    const reader: LegacyReader = {
      getCount: () => 1,
      getField: (id) => {
        if (id === 'B22A-T1-item-1-point') return { remark: '甲' }
        if (id === 'B22A-T1-item-1-attrs') return { remark: '{坏JSON' }
        return undefined
      },
    }
    const rows = migrateLegacyGroup(reader, 1)
    expect(rows[0].point).toBe('甲')
    expect(rows[0].attrs).toBeUndefined()
  })

  it('subPanel 组走 IT 命名空间', () => {
    const reader: LegacyReader = {
      getCount: () => 1,
      getField: (id) =>
        id === 'B22A-T4-IT-itgc-1-point' ? { remark: 'ITGC项' } : undefined,
    }
    const rows = migrateLegacyGroup(reader, 4, 'itgc')
    expect(rows[0].point).toBe('ITGC项')
    expect(rows[0].rowId).toBe(legacyRowId('T4-itgc', 1))
  })

  it('count=0 → 空数组（零分母不抛）', () => {
    const reader: LegacyReader = { getCount: () => 0, getField: () => undefined }
    expect(migrateLegacyGroup(reader, 1)).toEqual([])
  })
})

describe('legacy 键生成器（迁移读取用）', () => {
  it('legacyFieldItemId 复现改造前的键形状', () => {
    expect(legacyFieldItemId(1, 3, 'point')).toBe('B22A-T1-item-3-point')
    expect(legacyFieldItemId(4, 2, 'conclusion', 'itgc')).toBe(
      'B22A-T4-IT-itgc-2-conclusion',
    )
  })

  it('legacyCountItemId 复现 count 键', () => {
    expect(legacyCountItemId(1)).toBe('B22A-T1-count')
    expect(legacyCountItemId(4, 'sod')).toBe('B22A-T4-IT-sod-count')
  })
})
