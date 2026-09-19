/**
 * H9 租赁负债 + H10 资产处置损益披露载荷契约守卫。
 *
 * 章节：H10 上市 `三、资产处置收益（损` / 国企 `八、75`；H9 上市 `五、47` / 国企 `八、52`。
 *
 * 固化本 spec 修掉的两个 P0：
 * 1. 上市章节号原写 `三、资产处置收益`，而模板 `section_number` 是 md 截断值
 *    `三、资产处置收益（损` → `sync_from_workpaper` 精确定位落空、会新建垃圾章节。
 * 2. 上市两张表原本同名 `项  目` → `sub_table_data` 以表名为键，同名互相覆盖丢整张表；
 *    载荷用 `项  目__trial` + `_trial_detail` 双写绕过，但那两个键在模板里不存在 = 孤儿，
 *    试运行销售明细永远进不了附注。正名后必须删掉绕过键并把旧名放进 `_removed_table_keys`。
 *
 * spec: h9-h10-remaining-disclosure-alignment (Task 6)
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  H10_DISCLOSURE_SHEET_NAME,
  H10_LEGACY_OBSOLETE_TABLES,
  H10_LISTED_NOTE_SECTION,
  H10_MAIN_SUBTABLE,
  H10_NOTE_SECTION,
  H10_NOTE_SECTION_DISPLAY,
  H10_TRIAL_SUBTABLE,
} from '../h10NoteSectionMap'
import {
  H10_NOTE_TEXT_TITLES,
  buildH10NoteTexts,
  buildH10SyncPayloads,
  type H10SyncSnapshot,
} from '../h10DisclosureSyncPayload'
import { H10_DISCLOSURE_LISTED_ROWS, H10_DISCLOSURE_SOE_ROWS, H10_TRIAL_DETAIL_ROWS } from '../h10Constants'
import {
  H9_DISCLOSURE_SHEET_NAME,
  H9_LISTED_SUBTABLE,
  H9_NOTE_SECTION,
  H9_SOE_SUBTABLE,
} from '../h9NoteSectionMap'
import {
  H9_NOTE_TEXT_TITLES,
  buildH9ListedSyncPayloads,
  buildH9NoteTexts,
  buildH9SoeSyncPayloads,
} from '../h9DisclosureSyncPayload'
import { createDefaultListedState, createDefaultSoeState } from '../h9DisclosureModel'

const REPO_ROOT = resolve(__dirname, '../../../../../../..')

type Section = Record<string, any>

function loadSection(variant: 'listed' | 'soe', sectionNumber: string): Section {
  const file = variant === 'listed' ? 'note_template_listed.json' : 'note_template_soe.json'
  const raw = JSON.parse(
    readFileSync(resolve(REPO_ROOT, 'backend/data', file), 'utf-8'),
  ) as { sections?: Section[] }
  const hit = (raw.sections ?? []).find((s) => String(s.section_number) === sectionNumber)
  expect(hit, `模板缺章节 ${sectionNumber}`).toBeDefined()
  return hit!
}

function tablesOf(sec: Section): Record<string, any> {
  return Object.fromEntries((sec.tables ?? []).map((t: any) => [String(t.name), t]))
}

/** 去注释后再做源码断言（守卫与被守卫源码的注释里都会写反例） */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

const H10_SNAP = (over: Partial<H10SyncSnapshot> = {}): H10SyncSnapshot => ({
  rows: H10_DISCLOSURE_LISTED_ROWS.map((d) => ({
    rowKey: d.rowKey,
    label: d.label,
    currentAmount: 0,
    priorAmount: 0,
    nonRecurringAmount: 0,
    remark: '',
  })) as any,
  trialRows: H10_TRIAL_DETAIL_ROWS.map((d) => ({
    rowKey: d.rowKey,
    label: d.label,
    currentIncome: 0,
    currentCost: 0,
    priorIncome: 0,
    priorCost: 0,
  })) as any,
  noteText: '',
  ...over,
})

const h10Payload = (variant: 'listed' | 'soe', over: Partial<H10SyncSnapshot> = {}) => {
  const rows = variant === 'soe'
    ? (H10_DISCLOSURE_SOE_ROWS.map((d) => ({
        rowKey: d.rowKey, label: d.label,
        currentAmount: 0, priorAmount: 0, nonRecurringAmount: 0, remark: '',
      })) as any)
    : H10_SNAP().rows
  return buildH10SyncPayloads(
    'wp1',
    variant,
    [variant === 'soe' ? 'soe_standalone' : 'listed_standalone'],
    H10_SNAP({ rows, ...over }),
  )[0]
}

const h9ListedPayload = (over: Record<string, unknown> = {}) =>
  buildH9ListedSyncPayloads('wp1', ['listed_standalone'], {
    ...createDefaultListedState(),
    ...over,
  } as any)[0]

const h9SoePayload = (over: Record<string, unknown> = {}) =>
  buildH9SoeSyncPayloads('wp1', ['soe_standalone'], {
    ...createDefaultSoeState(),
    ...over,
  } as any)[0]

// ─────────────────────────────────────────────────────────────────────

describe('P1 章节号 / sheet 名 / 表名逐字命中模板与源 xlsx', () => {
  it('🔴 H10 上市章节号必须是模板的 md 截断值（差一字即新建垃圾章节）', () => {
    expect(H10_LISTED_NOTE_SECTION).toBe('三、资产处置收益（损')
    expect(H10_LISTED_NOTE_SECTION).toHaveLength(10)
    expect(H10_NOTE_SECTION.listed).toBe(H10_LISTED_NOTE_SECTION)
    const sec = loadSection('listed', H10_NOTE_SECTION.listed)
    expect(String(sec.section_number)).toBe(H10_NOTE_SECTION.listed)
    expect(h10Payload('listed').section_id).toBe(H10_NOTE_SECTION.listed)
  })

  it('展示常量与定位常量分离（截断值不直接显示给用户）', () => {
    expect(H10_NOTE_SECTION_DISPLAY.listed).toBe('三、资产处置收益')
    expect(H10_NOTE_SECTION_DISPLAY.listed).not.toBe(H10_NOTE_SECTION.listed)
    expect(H10_NOTE_SECTION_DISPLAY.listed.endsWith('（损')).toBe(false)
  })

  it('H10/H9 其余章节号命中模板', () => {
    expect(String(loadSection('soe', H10_NOTE_SECTION.soe).section_number)).toBe('八、75')
    expect(String(loadSection('listed', H9_NOTE_SECTION.listed).section_number)).toBe('五、47')
    expect(String(loadSection('soe', H9_NOTE_SECTION.soe).section_number)).toBe('八、52')
  })

  it('🔴 H10 国企 sheet 名是「国企」不是「国有企业」', () => {
    expect(H10_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息（国企）')
    expect(H10_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息（上市公司）')
    expect(H9_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息（国企）')
    expect(h10Payload('soe').sheet_name).toBe('附注披露信息（国企）')
  })

  it('推送的每个表名都存在于模板（无孤儿子表）', () => {
    const cases = [
      ['listed', H10_NOTE_SECTION.listed, h10Payload('listed', { trialRows: [{
        rowKey: 'fixed_asset_trial', label: '固定资产试运行销售',
        currentIncome: 100, currentCost: 60, priorIncome: 0, priorCost: 0,
      }] as any })],
      ['soe', H10_NOTE_SECTION.soe, h10Payload('soe')],
      ['listed', H9_NOTE_SECTION.listed, h9ListedPayload()],
      ['soe', H9_NOTE_SECTION.soe, h9SoePayload()],
    ] as const
    for (const [variant, section, payload] of cases) {
      const tpl = new Set(Object.keys(tablesOf(loadSection(variant, section))))
      for (const name of Object.keys(payload.sub_table_data)) {
        if (name.startsWith('_')) continue
        expect(tpl.has(name), `${section} 孤儿子表「${name}」`).toBe(true)
      }
    }
  })

  it('主表名与试运行表名对齐模板', () => {
    const listed = tablesOf(loadSection('listed', H10_NOTE_SECTION.listed))
    expect(Object.keys(listed)).toEqual([H10_MAIN_SUBTABLE.listed, H10_TRIAL_SUBTABLE])
    expect(H10_MAIN_SUBTABLE.listed).toBe('资产处置收益（损失以“-”填列）')
    expect(H10_TRIAL_SUBTABLE).toBe('试运行销售损益')
    const soe = tablesOf(loadSection('soe', H10_NOTE_SECTION.soe))
    expect(Object.keys(soe)).toEqual([H10_MAIN_SUBTABLE.soe])
    expect(Object.keys(tablesOf(loadSection('listed', H9_NOTE_SECTION.listed))))
      .toEqual([H9_LISTED_SUBTABLE.main])
    expect(Object.keys(tablesOf(loadSection('soe', H9_NOTE_SECTION.soe))))
      .toEqual([H9_SOE_SUBTABLE.main])
  })
})

describe('P2 旧表名进 _removed_table_keys 且绕过键已删净', () => {
  it('模板不再含 `项  目`，旧名登记在 legacy 清单', () => {
    for (const [variant, section] of [
      ['listed', H10_NOTE_SECTION.listed],
      ['soe', H10_NOTE_SECTION.soe],
    ] as const) {
      expect(Object.keys(tablesOf(loadSection(variant, section)))).not.toContain('项  目')
    }
    expect([...H10_LEGACY_OBSOLETE_TABLES]).toEqual(['项  目'])
  })

  it('上市载荷发 _removed_table_keys 且不含绕过键', () => {
    const p = h10Payload('listed')
    expect(p.sub_table_data._removed_table_keys as unknown).toEqual(['项  目'])
    for (const k of Object.keys(p.sub_table_data)) {
      expect(k).not.toContain('__trial')
      expect(k).not.toBe('_trial_detail')
    }
    expect(Object.keys(p.columns ?? {})).not.toContain('项  目__trial')
  })

  it('载荷源码里已无绕过键（含反向自检）', () => {
    const raw = readFileSync(
      resolve(REPO_ROOT, 'audit-platform/frontend/src/components/workpaper/composables/h10DisclosureSyncPayload.ts'),
      'utf-8',
    )
    // 注释里会写「不再需要 `项  目__trial`」→ 必须先剥注释，否则误报
    expect(raw).toContain('__trial')
    const src = stripComments(raw)
    expect(src).not.toContain('__trial')
    expect(src).not.toContain('_trial_detail')
  })
})

describe('P4/P5 列定义：两级表头 + flat + 载荷 key ≡ 模板 key', () => {
  it('H10 上市试运行表 5 列两级（group 各 span 2、标签列无 group、不标 flat）', () => {
    const tbl = tablesOf(loadSection('listed', H10_NOTE_SECTION.listed))[H10_TRIAL_SUBTABLE]
    const cols = h10Payload('listed').columns![H10_TRIAL_SUBTABLE]
    expect(cols.map((c) => c.key)).toEqual(
      (tbl.columns as any[]).map((c) => c.key),
    )
    expect(cols.map((c) => c.key)).toEqual([
      'label', 'current_income', 'current_cost', 'prior_income', 'prior_cost',
    ])
    expect(cols.map((c) => c.label)).toEqual(tbl.headers)
    expect(cols.map((c) => c.group ?? null)).toEqual([
      null, '本期发生额', '本期发生额', '上期发生额', '上期发生额',
    ])
    expect(cols.some((c) => c.flat), '两级表头不得标 flat').toBe(false)
    expect(tbl._column_groups).toEqual([
      { group: '本期发生额', start: 1, span: 2 },
      { group: '上期发生额', start: 3, span: 2 },
    ])
  })

  it('其余三表单级且显式 flat、载荷列 key ≡ 模板列 key', () => {
    const cases = [
      ['listed', H10_NOTE_SECTION.listed, H10_MAIN_SUBTABLE.listed,
        h10Payload('listed').columns![H10_MAIN_SUBTABLE.listed]],
      ['soe', H10_NOTE_SECTION.soe, H10_MAIN_SUBTABLE.soe,
        h10Payload('soe').columns![H10_MAIN_SUBTABLE.soe]],
      ['listed', H9_NOTE_SECTION.listed, H9_LISTED_SUBTABLE.main,
        h9ListedPayload().columns![H9_LISTED_SUBTABLE.main]],
      ['soe', H9_NOTE_SECTION.soe, H9_SOE_SUBTABLE.main,
        h9SoePayload().columns![H9_SOE_SUBTABLE.main]],
    ] as const
    for (const [variant, section, table, cols] of cases) {
      const tbl = tablesOf(loadSection(variant, section))[table]
      expect(cols.map((c) => c.key), `${section}/${table}`).toEqual(
        (tbl.columns as any[]).map((c) => c.key),
      )
      expect(cols.map((c) => c.label)).toEqual(tbl.headers)
      expect(cols.some((c) => c.flat === true), `${table} 载荷列未表态 flat`).toBe(true)
      expect(cols.some((c) => c.group), `${table} 单级表头不得声明 group`).toBe(false)
      expect(cols.slice(1).every((c) => c.format === 'amount')).toBe(true)
    }
  })

  it('行键 ⊆ columns.key ∪ 结构标记', () => {
    const extra = new Set(['is_total', 'row_type', 'row_key', 'remark'])
    const cases = [
      h10Payload('listed', {
        rows: [{ rowKey: 'fixed_asset_disposal', label: 'x', currentAmount: 10, priorAmount: 5, nonRecurringAmount: 0, remark: '备注' }] as any,
        trialRows: [{ rowKey: 'rd_sample_sales', label: 'y', currentIncome: 9, currentCost: 3, priorIncome: 1, priorCost: 0 }] as any,
      }),
      h10Payload('soe', {
        rows: [{ rowKey: 'fixed_asset_disposal', label: 'x', currentAmount: 10, priorAmount: 5, nonRecurringAmount: 2, remark: '' }] as any,
      }),
      h9ListedPayload(),
      h9SoePayload(),
    ]
    for (const p of cases) {
      for (const [table, rows] of Object.entries(p.sub_table_data)) {
        if (table.startsWith('_')) continue
        const allowed = new Set([...(p.columns?.[table] ?? []).map((c) => c.key), ...extra])
        for (const row of rows as Record<string, unknown>[]) {
          expect(row).not.toHaveProperty('values')
          for (const k of Object.keys(row)) {
            expect(allowed.has(k), `${table} 未知行键 ${k}`).toBe(true)
          }
        }
      }
    }
  })
})

describe('P3 行集与模板一致（含载荷标签映射有落点）', () => {
  it('H10 两版模板主表行标签覆盖载荷全部映射标签', () => {
    for (const [variant, section, table] of [
      ['listed', H10_NOTE_SECTION.listed, H10_MAIN_SUBTABLE.listed],
      ['soe', H10_NOTE_SECTION.soe, H10_MAIN_SUBTABLE.soe],
    ] as const) {
      const labels = new Set(
        ((tablesOf(loadSection(variant, section))[table].rows ?? []) as any[])
          .map((r) => String(r.label)),
      )
      const p = h10Payload(variant, {
        rows: (variant === 'soe' ? H10_DISCLOSURE_SOE_ROWS : H10_DISCLOSURE_LISTED_ROWS).map((d) => ({
          rowKey: d.rowKey, label: d.label,
          currentAmount: 1, priorAmount: 0, nonRecurringAmount: 0, remark: '',
        })) as any,
      })
      for (const row of p.sub_table_data[table] as Record<string, unknown>[]) {
        expect(labels.has(String(row.label)), `${section} 载荷行「${row.label}」在模板无落点`).toBe(true)
      }
    }
  })

  it('H10 上市主表模板 11 行（10 项目 + 合计），无占位/假行', () => {
    const rows = tablesOf(loadSection('listed', H10_NOTE_SECTION.listed))[H10_MAIN_SUBTABLE.listed].rows as any[]
    expect(rows).toHaveLength(11)
    expect(String(rows[rows.length - 1].label)).toBe('合计')
    expect(rows.some((r) => r.row_type === 'header_label')).toBe(false)
    expect(rows.some((r) => String(r.label).includes('可无限量添加行'))).toBe(false)
    for (const key of ['债务重组', '使用权资产处置利得', '油气资产处置利得']) {
      expect(rows.some((r) => String(r.label).includes(key)), `缺行 ${key}`).toBe(true)
    }
  })

  it('试运行表合计逐列求和（不再压成净额）', () => {
    const p = h10Payload('listed', {
      trialRows: [
        { rowKey: 'fixed_asset_trial', label: '固定资产试运行销售', currentIncome: 100, currentCost: 60, priorIncome: 20, priorCost: 8 },
        { rowKey: 'rd_sample_sales', label: '研发样品销售', currentIncome: 50, currentCost: 30, priorIncome: 0, priorCost: 0 },
      ] as any,
    })
    const rows = p.sub_table_data[H10_TRIAL_SUBTABLE] as Record<string, unknown>[]
    expect(rows).toHaveLength(3)
    const total = rows[2]
    expect(total.is_total).toBe(true)
    expect(total.current_income).toBe(150)
    expect(total.current_cost).toBe(90)
    expect(total.prior_income).toBe(20)
    expect(total.prior_cost).toBe(8)
  })

  it('收入 = 成本 的行不再被当空行丢掉（原实现只看净额）', () => {
    const p = h10Payload('listed', {
      trialRows: [{ rowKey: 'fixed_asset_trial', label: '固定资产试运行销售', currentIncome: 80, currentCost: 80, priorIncome: 0, priorCost: 0 }] as any,
    })
    const rows = p.sub_table_data[H10_TRIAL_SUBTABLE] as Record<string, unknown>[]
    expect(rows).toHaveLength(2)
    expect(rows[0].current_income).toBe(80)
  })

  it('试运行全空时不推该表', () => {
    expect(h10Payload('listed').sub_table_data).not.toHaveProperty(H10_TRIAL_SUBTABLE)
  })
})

describe('P6 `_note_texts` 中文标题与空过滤', () => {
  it('H10：全空无键；有值时带中文 title 且在 sub_table_data 内', () => {
    expect(h10Payload('listed').sub_table_data).not.toHaveProperty('_note_texts')
    expect(h10Payload('soe', { noteText: '   ' }).sub_table_data).not.toHaveProperty('_note_texts')
    const p = h10Payload('soe', { noteText: '本期处置一批闲置固定资产。' })
    expect(p).not.toHaveProperty('_note_texts')
    const texts = p.sub_table_data._note_texts as unknown as Array<Record<string, string>>
    expect(texts).toHaveLength(1)
    expect(texts[0].title).toBe(H10_NOTE_TEXT_TITLES['disclosure-note'])
    expect(/[\u4e00-\u9fa5]/.test(texts[0].title)).toBe(true)
    expect(/^[a-z0-9-]+$/.test(texts[0].title)).toBe(false)
  })

  it('H9：两版标题齐备、空过滤、trim', () => {
    expect(h9ListedPayload().sub_table_data).not.toHaveProperty('_note_texts')
    expect(h9SoePayload({ supplementNote: ' \n ' }).sub_table_data).not.toHaveProperty('_note_texts')
    const soe = h9SoePayload({ supplementNote: '  国资监管补充披露。  ' })
    const t = soe.sub_table_data._note_texts as unknown as Array<Record<string, string>>
    expect(t[0]).toEqual({
      section: 'soe-guidance',
      title: H9_NOTE_TEXT_TITLES['soe-guidance'],
      text: '国资监管补充披露。',
    })
    const listed = h9ListedPayload({
      interest: { total: 1200000, financeExpense: 1000000, capitalized: 200000, year: '2025' },
    })
    const lt = listed.sub_table_data._note_texts as unknown as Array<Record<string, string>>
    expect(lt[0].section).toBe('listed-interest')
    expect(lt[0].title).toBe(H9_NOTE_TEXT_TITLES['listed-interest'])
  })

  it('构造器：空白过滤、未登记 section 回退自身、标题映射覆盖全部 section', () => {
    expect(buildH9NoteTexts([{ section: 'a', text: '  ' }, { section: 'b', text: null }])).toEqual([])
    expect(buildH10NoteTexts([{ section: 'zzz', text: 'x' }])[0].title).toBe('zzz')
    expect(Object.keys(H9_NOTE_TEXT_TITLES).sort()).toEqual(['listed-interest', 'soe-guidance'])
    expect(Object.keys(H10_NOTE_TEXT_TITLES)).toEqual(['disclosure-note'])
  })
})

describe('P7 三个披露 Tab 无自调度', () => {
  const COMPONENTS: Record<string, [string, string]> = {
    'H9 上市': ['h9/core/H9TabDisclosureListed.vue', 'async function syncToNotes'],
    'H9 国企': ['h9/core/H9TabDisclosureSoe.vue', 'async function syncToNotes'],
    'H10 Base': ['h10/core/H10TabDisclosureBase.vue', 'async function syncToNotes'],
  }

  /** 按花括号配对精确截取函数体 */
  function functionBody(source: string, signature: string): string {
    const at = source.indexOf(signature)
    if (at === -1) return ''
    const open = source.indexOf('{', at)
    let depth = 0
    for (let i = open; i < source.length; i++) {
      if (source[i] === '{') depth++
      else if (source[i] === '}') {
        depth--
        if (depth === 0) return source.slice(open, i + 1)
      }
    }
    return source.slice(open)
  }

  it('反向自检：花括号配对截取有效', () => {
    const fake = 'async function syncToNotes() { a(); scheduleAutoSync(x); }\nfunction z(){}'
    expect(functionBody(fake, 'async function syncToNotes')).toContain('scheduleAutoSync')
    expect(functionBody(fake, 'async function nope')).toBe('')
  })

  for (const [name, [rel, sig]] of Object.entries(COMPONENTS)) {
    const raw = readFileSync(
      resolve(REPO_ROOT, 'audit-platform/frontend/src/components/workpaper', rel),
      'utf-8',
    )
    const src = stripComments(raw)

    it(`${name}：反向自检 —— 原始源码含 scheduleAutoSync`, () => {
      expect(raw).toContain('scheduleAutoSync')
    })

    it(`${name}：同步函数体内不得调 scheduleAutoSync（自调度）`, () => {
      const body = functionBody(src, sig)
      expect(body, `未定位到 ${sig} 函数体`).not.toBe('')
      expect(body).not.toContain('scheduleAutoSync')
    })

    it(`${name}：不得使用一次性挂载防护`, () => {
      expect(/_[A-Za-z0-9]*[Mm]ounted\s*=/.test(src)).toBe(false)
    })
  }
})
