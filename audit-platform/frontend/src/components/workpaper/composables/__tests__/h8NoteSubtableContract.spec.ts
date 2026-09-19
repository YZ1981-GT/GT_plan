/**
 * H8 使用权资产披露载荷契约守卫（上市 §五、25 / 国企 §八、26）。
 *
 * 固化本 spec 的三条结论：
 * 1. 载荷列 key ≡ 模板列 key（seed 路径与推送路径同键）；上市列 key = 类别名本身，
 *    模板第 5 列由源模板占位 `……` 展开为 `其他` 就是为了对上底稿默认分类。
 * 2. `_note_texts` 必须在 `sub_table_data` 内、带中文 `title`、空文本过滤、
 *    全空时不产生该键（缺 title 时后端用 `section` 兜底 → 正文出现 `【listed-short-low】`）。
 * 3. `……` 作**行**是真实可扩行（参与 `sumOf`），载荷行集须保留 6 个 `……` 行且与模板逐行一致。
 * 4. 两个 Tab 的 `scheduleAutoSync` 在 `onSave` 回调，`syncToNotes` 函数体内不得自调度。
 *
 * spec: h8-right-of-use-disclosure-alignment (Task 5)
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  H8_LISTED_SUBTABLE,
  H8_NOTE_SECTION,
  H8_SOE_SUBTABLE,
} from '../h8NoteSectionMap'
import {
  H8_NOTE_TEXT_TITLES,
  buildH8ListedSyncPayloads,
  buildH8NoteTexts,
  buildH8SoeSyncPayloads,
} from '../h8DisclosureSyncPayload'
import { H8_LISTED_DEFAULT_CATEGORIES } from '../h8ListedDisclosureModel'
import { createDefaultSoeLayers } from '../h8SoeDisclosureModel'

const REPO_ROOT = resolve(__dirname, '../../../../../../..')

function noteSection(variant: 'listed' | 'soe') {
  const file = variant === 'listed' ? 'note_template_listed.json' : 'note_template_soe.json'
  const raw = JSON.parse(
    readFileSync(resolve(REPO_ROOT, 'backend/data', file), 'utf-8'),
  ) as { sections?: Array<Record<string, any>> }
  return (raw.sections ?? []).find(
    (s) => String(s.section_number).trim() === H8_NOTE_SECTION[variant],
  )
}

function mainTable(variant: 'listed' | 'soe') {
  const sec = noteSection(variant)
  expect(sec, `模板缺 §${H8_NOTE_SECTION[variant]}`).toBeDefined()
  const name = variant === 'listed' ? H8_LISTED_SUBTABLE.movement : H8_SOE_SUBTABLE.movement
  const tbl = (sec!.tables as any[]).find((t) => t.name === name)
  expect(tbl, `模板缺子表「${name}」`).toBeDefined()
  return tbl
}

/** 去注释后再做源码断言（守卫注释里会写反例，否则被数成真实调用） */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

const norm = (s: unknown) => String(s ?? '').replace(/\s+/g, '')

const LISTED_STATE = () => ({
  categories: [...H8_LISTED_DEFAULT_CATEGORIES],
  movement: {} as Record<string, Record<string, number>>,
  noteShortLow: '',
  noteImpairment: '',
})

const SOE_STATE = () => ({ layers: createDefaultSoeLayers(), noteImpairment: '' })

const listedPayload = (over: Partial<ReturnType<typeof LISTED_STATE>> = {}) =>
  buildH8ListedSyncPayloads('wp1', ['listed_standalone'], { ...LISTED_STATE(), ...over })[0]

const soePayload = (over: Partial<ReturnType<typeof SOE_STATE>> = {}) =>
  buildH8SoeSyncPayloads('wp1', ['soe_standalone'], { ...SOE_STATE(), ...over })[0]

describe('P1 子表名与章节号逐字命中模板', () => {
  it('两版章节号与子表名存在', () => {
    expect(H8_NOTE_SECTION.listed).toBe('五、25')
    expect(H8_NOTE_SECTION.soe).toBe('八、26')
    expect(mainTable('listed').name).toBe(H8_LISTED_SUBTABLE.movement)
    expect(mainTable('soe').name).toBe(H8_SOE_SUBTABLE.movement)
  })

  it('载荷 sub_table_data 只含模板已有表名（无孤儿子表）', () => {
    for (const [variant, payload] of [
      ['listed', listedPayload()],
      ['soe', soePayload()],
    ] as const) {
      const tplNames = new Set(((noteSection(variant)!.tables as any[]) || []).map((t) => t.name))
      const pushed = Object.keys(payload.sub_table_data).filter((k) => !k.startsWith('_'))
      for (const name of pushed) {
        expect(tplNames.has(name), `${variant} 孤儿子表「${name}」`).toBe(true)
      }
    }
  })
})

describe('P3 载荷列 key ≡ 模板列 key（seed 与推送同键）', () => {
  it('上市 6 列：项目 + 4 类别 + 合计，key = 类别名本身', () => {
    const tbl = mainTable('listed')
    const cols = listedPayload().columns![H8_LISTED_SUBTABLE.movement]
    expect(cols.map((c) => c.key)).toEqual((tbl.columns as any[]).map((c) => c.key))
    expect(cols.map((c) => c.label)).toEqual(tbl.headers)
    expect(cols.map((c) => c.key)).toEqual([
      'label', '房屋及建筑物', '机器设备', '运输设备', '其他', '合计',
    ])
    expect(cols[0].is_label).toBe(true)
  })

  it('🔴 两版载荷列须显式 flat（否则后端前缀推断造凭空父表头）', () => {
    // 实测缺 flat 时国企投影出 `[{group:'本期',start:2,span:2}]`（本期增加/本期减少被并组）
    for (const [variant, payload, table] of [
      ['listed', listedPayload(), H8_LISTED_SUBTABLE.movement],
      ['soe', soePayload(), H8_SOE_SUBTABLE.movement],
    ] as const) {
      const cols = payload.columns![table]
      expect(cols.some((c) => c.flat === true), `${variant} 载荷列未表态 flat`).toBe(true)
      // 与模板 seed 路径同口径
      const tplCols = mainTable(variant).columns as any[]
      expect(tplCols.some((c) => c.flat === true), `${variant} 模板列未表态 flat`).toBe(true)
      expect(cols.some((c) => c.group), `${variant} 单级表头不得声明 group`).toBe(false)
    }
  })

  it('🔴 模板第 5 列须为 `其他`（源模板 `……` 占位列头展开点），且两侧均无 `……`', () => {
    const tbl = mainTable('listed')
    expect(tbl.headers[4]).toBe('其他')
    expect(tbl.headers).not.toContain('……')
    const cols = listedPayload().columns![H8_LISTED_SUBTABLE.movement]
    expect(cols.map((c) => c.label)).not.toContain('……')
    // 底稿默认分类是模板列的真源
    expect(H8_LISTED_DEFAULT_CATEGORIES.map((c) => c.label)).toEqual(
      (tbl.columns as any[]).slice(1, -1).map((c) => c.label),
    )
  })

  it('国企 5 列：label/begin/increase/decrease/end', () => {
    const tbl = mainTable('soe')
    const cols = soePayload().columns![H8_SOE_SUBTABLE.movement]
    expect(cols.map((c) => c.key)).toEqual((tbl.columns as any[]).map((c) => c.key))
    expect(cols.map((c) => c.label)).toEqual(tbl.headers)
    expect(cols.map((c) => c.key)).toEqual(['label', 'begin', 'increase', 'decrease', 'end'])
    expect(cols.slice(1).every((c) => c.format === 'amount')).toBe(true)
  })

  it('行对象键 ⊆ columns.key ∪ 结构标记（无位置化 values）', () => {
    const cases = [
      ['listed', listedPayload(), H8_LISTED_SUBTABLE.movement, ['is_total', 'is_section']],
      ['soe', soePayload(), H8_SOE_SUBTABLE.movement, ['is_total', 'layer']],
    ] as const
    for (const [variant, payload, table, extra] of cases) {
      const allowed = new Set([
        ...payload.columns![table].map((c) => c.key),
        ...extra,
      ])
      for (const row of payload.sub_table_data[table]) {
        expect(row).not.toHaveProperty('values')
        for (const k of Object.keys(row)) {
          expect(allowed.has(k), `${variant} 未知行键 ${k}`).toBe(true)
        }
      }
    }
  })
})

describe('P4 行集与模板一致 + `……` 可扩行保留', () => {
  it('上市 39 行且逐行等于模板（空白归一后）', () => {
    const tpl = (mainTable('listed').rows as any[]).map((r) => norm(r.label))
    const rows = listedPayload().sub_table_data[H8_LISTED_SUBTABLE.movement]
    expect(rows).toHaveLength(39)
    expect(rows.map((r) => norm(r.label))).toEqual(tpl)
  })

  it('🔴 上市保留 6 个 `……` 行（真实可扩行，参与 sumOf，不得当占位删除）', () => {
    const rows = listedPayload().sub_table_data[H8_LISTED_SUBTABLE.movement]
    const at = rows.map((r, i) => (norm(r.label) === '……' ? i : -1)).filter((i) => i >= 0)
    expect(at).toEqual([5, 10, 17, 22, 29, 34])
    // 模板侧同样保留
    const tplAt = (mainTable('listed').rows as any[])
      .map((r, i) => (norm(r.label) === '……' ? i : -1))
      .filter((i) => i >= 0)
    expect(tplAt).toEqual(at)
  })

  it('国企 25 行五层且逐行等于模板，推导层增减列为 null（源模板「——」列示约定）', () => {
    const tpl = (mainTable('soe').rows as any[]).map((r) => norm(r.label))
    const rows = soePayload().sub_table_data[H8_SOE_SUBTABLE.movement]
    expect(rows).toHaveLength(25)
    expect(rows.map((r) => norm(r.label))).toEqual(tpl)
    for (const r of rows) {
      if (r.layer === 'net' || r.layer === 'carrying') {
        expect(r.increase, `${r.label} 推导层增列应为 null`).toBeNull()
        expect(r.decrease, `${r.label} 推导层减列应为 null`).toBeNull()
      }
    }
  })
})

describe('P5 `_note_texts` 中文标题与空过滤', () => {
  it('全空时不产生 `_note_texts` 键（两版）', () => {
    expect(listedPayload().sub_table_data).not.toHaveProperty('_note_texts')
    expect(soePayload().sub_table_data).not.toHaveProperty('_note_texts')
    expect(listedPayload({ noteShortLow: '   ', noteImpairment: '\n' }).sub_table_data)
      .not.toHaveProperty('_note_texts')
  })

  it('在 sub_table_data 内、不在载荷顶层（顶层会被 pydantic 静默丢弃）', () => {
    const p = listedPayload({ noteShortLow: '短期租赁费用 12,000.00 元。' })
    expect(p).not.toHaveProperty('_note_texts')
    expect(p.sub_table_data._note_texts).toHaveLength(1)
  })

  it('每条带非空中文 title（不得为英文 section 键）', () => {
    const p = listedPayload({
      noteShortLow: '短期租赁费用 12,000.00 元。',
      noteImpairment: '本期未计提减值。',
    })
    const texts = p.sub_table_data._note_texts as unknown as Array<Record<string, string>>
    expect(texts.map((t) => t.section)).toEqual(['listed-short-low', 'listed-impairment'])
    for (const t of texts) {
      expect(t.title.trim()).not.toBe('')
      expect(/^[a-z0-9-]+$/.test(t.title), `title 仍是英文键：${t.title}`).toBe(false)
      expect(/[\u4e00-\u9fa5]/.test(t.title)).toBe(true)
    }
    const soe = soePayload({ noteImpairment: '本期计提减值 5,000.00 元。' })
    const soeTexts = soe.sub_table_data._note_texts as unknown as Array<Record<string, string>>
    expect(soeTexts[0].section).toBe('soe-impairment')
    expect(soeTexts[0].title).toBe(H8_NOTE_TEXT_TITLES['soe-impairment'])
  })

  it('空白条目被过滤、文本 trim、未登记 section 回退自身（不抛错）', () => {
    expect(buildH8NoteTexts([{ section: 'a', text: '  ' }, { section: 'b', text: null }])).toEqual([])
    expect(buildH8NoteTexts([{ section: 'listed-impairment', text: ' x ' }])).toEqual([
      { section: 'listed-impairment', title: H8_NOTE_TEXT_TITLES['listed-impairment'], text: 'x' },
    ])
    expect(buildH8NoteTexts([{ section: 'unknown-key', text: 'y' }])[0].title).toBe('unknown-key')
  })

  it('标题映射覆盖两版全部文本域 section', () => {
    expect(Object.keys(H8_NOTE_TEXT_TITLES).sort()).toEqual(
      ['listed-impairment', 'listed-short-low', 'soe-impairment'].sort(),
    )
  })
})

describe('P2 载荷顶层字段集合 + 适用性门控', () => {
  it('顶层字段符合 SyncFromWorkpaperRequest', () => {
    for (const p of [listedPayload(), soePayload()]) {
      expect(Object.keys(p).sort()).toEqual(
        ['columns', 'current_standard', 'section_id', 'sheet_name', 'sub_table_data', 'wp_id'].sort(),
      )
    }
    expect(listedPayload().current_standard).toBe('listed_standalone')
    expect(soePayload().current_standard).toBe('soe_standalone')
  })

  it('变体不适用时不产生载荷（防跨主体类型写错章节）', () => {
    expect(buildH8ListedSyncPayloads('wp1', ['soe_standalone'], LISTED_STATE())).toEqual([])
    expect(buildH8SoeSyncPayloads('wp1', ['listed_standalone'], SOE_STATE())).toEqual([])
  })
})

describe('P6 两个披露 Tab 无自调度（scheduleAutoSync 在 onSave 回调）', () => {
  const COMPONENTS = {
    listed: 'audit-platform/frontend/src/components/workpaper/h8/core/H8TabDisclosureListed.vue',
    soe: 'audit-platform/frontend/src/components/workpaper/h8/core/H8TabDisclosureSoe.vue',
  } as const

  /** 按花括号配对精确截取函数体（不依赖后续代码布局） */
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

  it('反向自检：花括号配对截取能在含该调用的函数体里检出', () => {
    const fake = 'async function syncToNotes() { a(); scheduleAutoSync(x); }\nfunction z(){}'
    expect(functionBody(fake, 'async function syncToNotes')).toContain('scheduleAutoSync')
    expect(functionBody(fake, 'async function nope')).toBe('')
  })

  for (const [variant, rel] of Object.entries(COMPONENTS)) {
    const raw = readFileSync(resolve(REPO_ROOT, rel), 'utf-8')
    const src = stripComments(raw)

    it(`${variant}：反向自检 —— 原始源码确实含 scheduleAutoSync`, () => {
      expect(raw).toContain('scheduleAutoSync')
    })

    it(`${variant}：syncToNotes 函数体内不得调 scheduleAutoSync`, () => {
      const body = functionBody(src, 'async function syncToNotes')
      expect(body, '未定位到 syncToNotes 函数体').not.toBe('')
      expect(body).not.toContain('scheduleAutoSync')
    })

    it(`${variant}：scheduleAutoSync 接在 onSave 回调（真接入实际数据变更）`, () => {
      expect(/onSave:[^\n]*scheduleAutoSync\(syncToNotes\)/.test(src)).toBe(true)
      // 不得使用一次性挂载防护（会吞掉切走再切回后的第一次编辑）
      expect(/_[A-Za-z0-9]*[Mm]ounted\s*=/.test(src)).toBe(false)
    })
  }
})
