/**
 * E1 外币货币性项目 → 附注 `五、73`/`八、92` 行级合并载荷契约。
 *
 * **Validates: disclosure-note-row-level-merge Requirements 7.1~7.3, 8.2, 8.3
 * / Properties 15, 16**
 *
 * 三向锁死：
 * 1. 章节号 / 表名 / 列定义 逐字命中 `note_template_{listed,soe}.json`
 * 2. `owner_row_code` 必须是该表模板里**真实存在**的段首 `report_row_code`
 * 3. 载荷必须带 `_row_scope`（否则表级覆盖会清掉 D2/K/L 的段）
 *
 * 含反向自检：去掉 `_row_scope` 的载荷必须被本文件的判定函数认定为「危险」。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  aggregateE1FxByCurrency,
  buildE1FxColumns,
  buildE1FxSyncPayload,
  E1_FX_DETAIL_PREFIX,
  E1_FX_DISCLOSURE_SHEET_NAME,
  E1_FX_NOTE_SECTION,
  E1_FX_OWNER_ROW_CODE,
  E1_FX_SEGMENT_LABEL,
  E1_FX_TABLE,
  type E1FxRowLike,
} from '../e1FxNoteSectionMap'

const REPO_ROOT = resolve(__dirname, '../../../../../../..')
const TEMPLATE = {
  listed: resolve(REPO_ROOT, 'backend/data/note_template_listed.json'),
  soe: resolve(REPO_ROOT, 'backend/data/note_template_soe.json'),
} as const

function loadTable(variant: 'listed' | 'soe') {
  const doc = JSON.parse(readFileSync(TEMPLATE[variant], 'utf-8'))
  const sec = (doc.sections || []).find(
    (s: any) => String(s.section_number || '').trim() === E1_FX_NOTE_SECTION[variant],
  )
  expect(sec, `模板缺章节 ${E1_FX_NOTE_SECTION[variant]}（${variant}）`).toBeTruthy()
  const tbl = (sec.tables || []).find((t: any) => String(t.name || '').trim() === E1_FX_TABLE)
  expect(tbl, `模板缺表「${E1_FX_TABLE}」（${variant} ${E1_FX_NOTE_SECTION[variant]}）`).toBeTruthy()
  return { sec, tbl }
}

/** 该表模板行集里的段首 `report_row_code`（保序去重）—— 与后端切段口径一致。 */
function segmentRowCodes(rows: any[]): string[] {
  const out: string[] = []
  for (const r of rows || []) {
    const code = String(r?.report_row_code || '').trim()
    if (code && !out.includes(code)) out.push(code)
  }
  return out
}

const VARIANTS = ['listed', 'soe'] as const

/** 底稿外币行样本（详细版：两个分组 × 人民币/美元/欧元）。 */
function fxRows(): E1FxRowLike[] {
  const mk = (
    groupId: string,
    currency: string,
    isGroup: boolean,
    endForeign = 0,
    endRate = 0,
    endRmb = 0,
  ): E1FxRowLike => ({ groupId, currency, isGroup, endForeign, endRate, endRmb })
  return [
    mk('g-cash', '', true),
    mk('g-cash', '人民币', false, 500, 1, 500),
    mk('g-cash', '美元', false, 100, 7.1884, 718.84),
    mk('g-bank', '', true),
    mk('g-bank', '人民币', false, 1000, 1, 1000),
    mk('g-bank', '美元', false, 200, 7.1884, 1437.68),
    mk('g-bank', '欧元', false, 50, 7.8592, 392.96),
  ]
}

describe('e1FxNoteSectionMap — 章节 / 表名 / 列定义三向对齐模板', () => {
  it.each(VARIANTS)('%s：章节号与表名逐字命中模板', (variant) => {
    const { tbl } = loadTable(variant)
    expect(String(tbl.name)).toBe(E1_FX_TABLE)
  })

  it.each(VARIANTS)('%s：列定义与模板 columns 逐字段相同（key/label/flat/format）', (variant) => {
    const { tbl } = loadTable(variant)
    const pushed = buildE1FxColumns()[E1_FX_TABLE]
    const tplCols = tbl.columns || []
    expect(tplCols.length, '模板必须已有 columns（否则投影会退化）').toBe(4)
    expect(pushed.map((c) => c.key)).toEqual(tplCols.map((c: any) => c.key))
    expect(pushed.map((c) => c.label)).toEqual(tplCols.map((c: any) => c.label))
    expect(pushed.map((c) => c.format ?? null)).toEqual(
      tplCols.map((c: any) => c.format ?? null),
    )
    // 🔴 flat 必须 seed 与推送两处都在（H8 踩过只加一侧的坑）
    expect(pushed.some((c) => c.flat)).toBe(true)
    expect(tplCols.some((c: any) => c.flat)).toBe(true)
    expect(pushed.some((c) => c.group)).toBe(false)
  })

  it.each(VARIANTS)('%s：列头与模板 headers 一致且为纯文本', (variant) => {
    const { tbl } = loadTable(variant)
    const pushed = buildE1FxColumns()[E1_FX_TABLE]
    expect(pushed.map((c) => c.label)).toEqual(tbl.headers)
    for (const h of tbl.headers as string[]) {
      expect(h).not.toMatch(/[<>]/)
    }
  })

  it('buildE1FxColumns 可零入参调用（覆盖率 sweep 用空参）', () => {
    const cols = buildE1FxColumns()
    expect(Object.keys(cols)).toEqual([E1_FX_TABLE])
    expect(cols[E1_FX_TABLE].length).toBe(4)
  })

  it.each(VARIANTS)('%s：owner_row_code 是该表模板里真实存在的段首 code', (variant) => {
    const { tbl } = loadTable(variant)
    const codes = segmentRowCodes(tbl.rows || [])
    expect(codes.length, '共享表必须 ≥2 段（否则不需要行级合并）').toBeGreaterThanOrEqual(2)
    expect(codes).toContain(E1_FX_OWNER_ROW_CODE)
    // 段首行标签与常量一致（便于与他段对照）
    const head = (tbl.rows || []).find(
      (r: any) => String(r?.report_row_code || '').trim() === E1_FX_OWNER_ROW_CODE,
    )
    expect(String(head.label).trim()).toBe(E1_FX_SEGMENT_LABEL)
  })

  it('两变体章节号必须不同（撞号会让变体解析失效）', () => {
    expect(E1_FX_NOTE_SECTION.listed).not.toBe(E1_FX_NOTE_SECTION.soe)
  })

  it('sheet 名是源 xlsx 真实 tab 名（半角括号，不得用合成标识）', () => {
    expect(E1_FX_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息(上市公司)')
    expect(E1_FX_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息(国企)')
    for (const v of VARIANTS) {
      expect(E1_FX_DISCLOSURE_SHEET_NAME[v]).not.toMatch(/E1|note|listed|soe/i)
    }
  })
})

describe('aggregateE1FxByCurrency — 源模板 R29 口径', () => {
  it('按币种跨分组求和，排除记账本位币，保持首现顺序', () => {
    const agg = aggregateE1FxByCurrency(fxRows())
    expect(agg.map((a) => a.currency)).toEqual(['美元', '欧元'])
    expect(agg[0].endForeign).toBe(300)             // 100 + 200
    expect(agg[0].endRmb).toBeCloseTo(2156.52, 2)   // 718.84 + 1437.68
    expect(agg[0].rate).toBeCloseTo(7.1884, 4)
    expect(agg[1].endForeign).toBe(50)
  })

  it('分组行不参与聚合；空/无效输入返回空数组', () => {
    expect(aggregateE1FxByCurrency([])).toEqual([])
    expect(aggregateE1FxByCurrency(null)).toEqual([])
    const onlyGroups: E1FxRowLike[] = [
      { groupId: 'g', currency: '', isGroup: true, endForeign: 9, endRate: 9, endRmb: 9 },
    ]
    expect(aggregateE1FxByCurrency(onlyGroups)).toEqual([])
  })

  it('🔴 金额取 2 位，消除 `原币 × 折算率` 的浮点噪声', () => {
    // 实测底稿 14000 × 7.1884 = 100637.59999999999（浏览器落库原值）
    const rows: E1FxRowLike[] = [
      {
        groupId: 'g',
        currency: '美元',
        isGroup: false,
        endForeign: 14000,
        endRate: 7.1884,
        endRmb: 14000 * 7.1884,
      },
    ]
    const agg = aggregateE1FxByCurrency(rows)
    expect(agg[0].endRmb).toBe(100637.6)
    const payload = buildE1FxSyncPayload('soe', 'wp-1', [], { fxRows: rows })!
    const pushed = (payload.sub_table_data as any)[E1_FX_TABLE] as any[]
    expect(pushed[0].end_rmb).toBe(100637.6)
    expect(pushed[1].end_rmb).toBe(100637.6)
    // 汇率不取 2 位（4 位小数）
    expect(pushed[1].rate).toBe(7.1884)
  })

  it('汇率取该币种首个非零值（源 R29 列 C = C46，取某一段折算率）', () => {
    const rows: E1FxRowLike[] = [
      { groupId: 'a', currency: '美元', isGroup: false, endForeign: 1, endRate: 0, endRmb: 0 },
      { groupId: 'b', currency: '美元', isGroup: false, endForeign: 1, endRate: 7.2, endRmb: 7.2 },
    ]
    expect(aggregateE1FxByCurrency(rows)[0].rate).toBeCloseTo(7.2, 4)
  })
})

describe('buildE1FxSyncPayload — 行级合并载荷', () => {
  it.each(VARIANTS)('%s：声明 _row_scope 且 owner 正确', (variant) => {
    const payload = buildE1FxSyncPayload(variant, 'wp-1', [`${variant}_standalone`], {
      fxRows: fxRows(),
    })!
    expect(payload).toBeTruthy()
    expect(payload.section_id).toBe(E1_FX_NOTE_SECTION[variant])
    expect(payload.sheet_name).toBe(E1_FX_DISCLOSURE_SHEET_NAME[variant])
    expect(payload.current_standard).toBe(`${variant}_standalone`)
    const scope = (payload.sub_table_data as any)._row_scope
    expect(scope).toEqual({ [E1_FX_TABLE]: { owner_row_code: E1_FX_OWNER_ROW_CODE } })
    expect(Object.keys(payload.columns)).toEqual([E1_FX_TABLE])
  })

  it('段内行 = 段首「货币资金」+ 各币种「其中：」明细，且合计自洽', () => {
    const payload = buildE1FxSyncPayload('soe', 'wp-1', ['soe_standalone'], {
      fxRows: fxRows(),
    })!
    const rows = (payload.sub_table_data as any)[E1_FX_TABLE] as any[]
    expect(rows.map((r) => r.label)).toEqual([
      E1_FX_SEGMENT_LABEL,
      `${E1_FX_DETAIL_PREFIX}美元`,
      '欧元',
    ])
    // 段首：币种混合 → 外币余额/汇率必须留空（不能把不同币种相加）
    expect(rows[0].end_fc).toBeNull()
    expect(rows[0].rate).toBeNull()
    expect(rows[0].end_rmb).toBeCloseTo(2549.48, 2) // 2156.52 + 392.96
    expect(rows[1].end_rmb + rows[2].end_rmb).toBeCloseTo(rows[0].end_rmb, 6)
  })

  it('行对象的键 ⊆ columns 的键（单向 P1；不得出现孤儿字段）', () => {
    const payload = buildE1FxSyncPayload('listed', 'wp-1', ['listed_standalone'], {
      fxRows: fxRows(),
    })!
    const keys = new Set(buildE1FxColumns()[E1_FX_TABLE].map((c) => c.key))
    keys.add('is_total')
    for (const row of (payload.sub_table_data as any)[E1_FX_TABLE] as any[]) {
      for (const k of Object.keys(row)) expect(keys.has(k), `孤儿字段 ${k}`).toBe(true)
    }
  })

  it('🔴 无外币明细 / 全零骨架 → 返回 null（不推空段）', () => {
    expect(buildE1FxSyncPayload('soe', 'wp-1', [], { fxRows: [] })).toBeNull()
    const skeleton = fxRows().map((r) => ({ ...r, endForeign: 0, endRmb: 0 }))
    expect(
      buildE1FxSyncPayload('soe', 'wp-1', [], { fxRows: skeleton }),
      '默认骨架全零时推空段会把段恢复成模板骨架 → 清掉附注模块手填的货币资金段',
    ).toBeNull()
  })

  it('不推 _note_texts（外币章节的文字说明不属 E1 单方所有）', () => {
    const payload = buildE1FxSyncPayload('soe', 'wp-1', [], { fxRows: fxRows() })!
    expect((payload.sub_table_data as any)._note_texts).toBeUndefined()
    expect((payload.sub_table_data as any)._removed_table_keys).toBeUndefined()
  })
})

describe('🔴 反向自检 + 组件接线', () => {
  it('去掉 _row_scope 的载荷会被判为危险（证明 Property 15 的判定不空转）', () => {
    const payload = buildE1FxSyncPayload('soe', 'wp-1', [], { fxRows: fxRows() })!
    const sub = { ...(payload.sub_table_data as any) }
    delete sub._row_scope
    const isSafe = (s: Record<string, unknown>) =>
      !!(s._row_scope as any)?.[E1_FX_TABLE]?.owner_row_code
    expect(isSafe(payload.sub_table_data as any)).toBe(true)
    expect(isSafe(sub)).toBe(false)
  })

  it('E1TabDisclosure 已接第二个 payload 且监听外币行', () => {
    const src = readFileSync(resolve(__dirname, '../../e1/E1TabDisclosure.vue'), 'utf-8')
      .replace(/<!--[\s\S]*?-->/g, '')
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
    // 反向自检：注释确实被剥掉了（否则下面的断言可能命中说明文字）
    expect(readFileSync(resolve(__dirname, '../../e1/E1TabDisclosure.vue'), 'utf-8')).toContain(
      '跨循环共享表',
    )
    expect(src).not.toContain('跨循环共享表')

    expect(src).toContain('buildE1FxSyncPayload')
    expect(src).toMatch(/syncFxSectionToNote\s*\(/)
    // 自动同步监听源必须含外币行（否则「改了外币不同步」）
    expect(src).toMatch(/watch\(\s*\[[^\]]*foreignCurrencyRows[^\]]*\]/)
    // fail closed 的返回字段必须被消费（否则又是一个 dead path）
    expect(src).toContain('row_scope_unresolved')
  })
})
