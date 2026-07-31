/**
 * H7 生产性生物资产披露载荷契约守卫（上市 §五、24 / 国企 §八、24）。
 *
 * H7 是 H 循环唯一需要**整体重建**的循环：重建前两个披露 Tab 只有单行只读
 * `movementRows`，既无 `h7NoteSectionMap.ts` 也无载荷，`disclosure-sync-path-buildout`
 * 曾接线后主动撤回。本守卫锁定重建结果。
 *
 * spec: h7-biological-assets-disclosure-rebuild (Task 9)
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  H7_DISCLOSURE_SHEET_NAME,
  H7_LEGACY_OBSOLETE_TABLES,
  H7_LISTED_SUBTABLE,
  H7_NOTE_SECTION,
  H7_SOE_SUBTABLE,
  isH7DisclosureApplicable,
} from '../h7NoteSectionMap'
import {
  H7_NOTE_TEXT_TITLES,
  H7_SOE_COLUMNS,
  buildH7ListedSyncPayloads,
  buildH7NoteTexts,
  buildH7SoeSyncPayloads,
} from '../h7DisclosureSyncPayload'
import {
  H7_COST_MOVEMENT_ROWS,
  H7_FAIR_MOVEMENT_ROWS,
  createDefaultH7Categories,
  emptyMovement,
  setCell,
} from '../h7ListedDisclosureModel'
import { createDefaultSoeBlocks } from '../h7SoeDisclosureModel'

const REPO_ROOT = resolve(__dirname, '../../../../../../..')
const WP = resolve(REPO_ROOT, 'audit-platform/frontend/src/components/workpaper')

type Section = Record<string, any>

function loadSection(variant: 'listed' | 'soe'): Section {
  const file = variant === 'listed' ? 'note_template_listed.json' : 'note_template_soe.json'
  const raw = JSON.parse(
    readFileSync(resolve(REPO_ROOT, 'backend/data', file), 'utf-8'),
  ) as { sections?: Section[] }
  const hit = (raw.sections ?? []).find(
    (s) => String(s.section_number) === H7_NOTE_SECTION[variant],
  )
  expect(hit, `模板缺章节 ${H7_NOTE_SECTION[variant]}`).toBeDefined()
  return hit!
}

function tablesOf(sec: Section): Record<string, any> {
  return Object.fromEntries((sec.tables ?? []).map((t: any) => [String(t.name), t]))
}

/** 去注释后再做源码断言（守卫与被守卫源码的注释里都会写反例） */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

const norm = (s: unknown) => String(s ?? '').replace(/\s+/g, '')

const LISTED_STATE = (over: Record<string, unknown> = {}) => ({
  categories: createDefaultH7Categories(),
  cost: emptyMovement(),
  fair: emptyMovement(),
  notePolicy: '',
  noteImpairment: '',
  noteSupplement: '',
  ...over,
})

const SOE_STATE = (over: Record<string, unknown> = {}) => ({
  cost: createDefaultSoeBlocks(),
  fair: createDefaultSoeBlocks(),
  notePolicy: '',
  noteFairBasis: '',
  noteSupplement: '',
  ...over,
})

const listedPayload = (over: Record<string, unknown> = {}) =>
  buildH7ListedSyncPayloads('wp1', ['listed_standalone'], LISTED_STATE(over) as any)[0]

const soePayload = (over: Record<string, unknown> = {}) =>
  buildH7SoeSyncPayloads('wp1', ['soe_standalone'], SOE_STATE(over) as any)[0]

// ─────────────────────────────────────────────────────────────────────

describe('P6 章节号 / sheet 名 / 表名逐字命中模板与源 xlsx', () => {
  it('章节号命中模板 section_number', () => {
    expect(H7_NOTE_SECTION.listed).toBe('五、24')
    expect(H7_NOTE_SECTION.soe).toBe('八、24')
    expect(String(loadSection('listed').section_number)).toBe('五、24')
    expect(String(loadSection('soe').section_number)).toBe('八、24')
    expect(listedPayload().section_id).toBe('五、24')
    expect(soePayload().section_id).toBe('八、24')
  })

  it('🔴 国企 sheet 名是「国有企业」，不是 H9/H10 的「国企」', () => {
    expect(H7_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息（国有企业）')
    expect(H7_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息（上市公司）')
    expect(soePayload().sheet_name).toBe('附注披露信息（国有企业）')
    expect(listedPayload().sheet_name).toBe('附注披露信息（上市公司）')
  })

  it('两版表名逐字命中模板（无孤儿子表）', () => {
    expect(Object.keys(tablesOf(loadSection('listed')))).toEqual([
      H7_LISTED_SUBTABLE.cost, H7_LISTED_SUBTABLE.fair,
    ])
    expect(Object.keys(tablesOf(loadSection('soe')))).toEqual([
      H7_SOE_SUBTABLE.cost, H7_SOE_SUBTABLE.fair,
    ])
    for (const [variant, payload] of [
      ['listed', listedPayload()],
      ['soe', soePayload()],
    ] as const) {
      const tpl = new Set(Object.keys(tablesOf(loadSection(variant))))
      for (const name of Object.keys(payload.sub_table_data)) {
        if (name.startsWith('_')) continue
        expect(tpl.has(name), `${variant} 孤儿子表「${name}」`).toBe(true)
      }
    }
  })

  it('变体不适用时不产生载荷', () => {
    expect(buildH7ListedSyncPayloads('wp1', ['soe_standalone'], LISTED_STATE() as any)).toEqual([])
    expect(buildH7SoeSyncPayloads('wp1', ['listed_standalone'], SOE_STATE() as any)).toEqual([])
    expect(isH7DisclosureApplicable('listed', [])).toBe(true)
  })

  it('载荷顶层字段符合 SyncFromWorkpaperRequest', () => {
    for (const p of [listedPayload(), soePayload()]) {
      expect(Object.keys(p).sort()).toEqual(
        ['columns', 'current_standard', 'section_id', 'sheet_name', 'sub_table_data', 'wp_id'].sort(),
      )
    }
    expect(listedPayload().current_standard).toBe('listed_standalone')
    expect(soePayload().current_standard).toBe('soe_standalone')
  })
})

describe('P2 上市两级表头（group = 产业；项目/合计 无 group；不标 flat）', () => {
  it('默认类别下载荷列 key ≡ 模板列 key（两张表同构）', () => {
    const tpl = tablesOf(loadSection('listed'))
    const cols = listedPayload().columns!
    for (const name of [H7_LISTED_SUBTABLE.cost, H7_LISTED_SUBTABLE.fair]) {
      expect(cols[name].map((c) => c.key)).toEqual(
        (tpl[name].columns as any[]).map((c) => c.key),
      )
      expect(cols[name].map((c) => c.label)).toEqual(tpl[name].headers)
    }
    expect(cols[H7_LISTED_SUBTABLE.cost].map((c) => c.key)).toEqual([
      'label', 'crop_1', 'livestock_1', 'forestry_1', 'aquatic_1', 'total',
    ])
  })

  it('group 结构与源模板合并区同构，且不标 flat', () => {
    const cols = listedPayload().columns![H7_LISTED_SUBTABLE.cost]
    expect(cols[0].group).toBeUndefined()
    expect(cols[cols.length - 1].group).toBeUndefined()
    expect(cols.slice(1, -1).map((c) => c.group)).toEqual([
      '种植业', '畜牧养殖业', '林业', '水产业',
    ])
    expect(cols.some((c) => c.flat), '两级表头不得标 flat').toBe(false)
    expect(tablesOf(loadSection('listed'))[H7_LISTED_SUBTABLE.cost]._column_groups).toEqual([
      { group: '种植业', start: 1, span: 1 },
      { group: '畜牧养殖业', start: 2, span: 1 },
      { group: '林业', start: 3, span: 1 },
      { group: '水产业', start: 4, span: 1 },
    ])
  })

  it('新增类别列后该产业 group 跨多列，且列序仍按产业顺序', () => {
    const cats = [
      ...createDefaultH7Categories(),
      { key: 'crop_2', label: '梨树', industry: 'crop' as const },
    ]
    const cols = listedPayload({ categories: cats }).columns![H7_LISTED_SUBTABLE.cost]
    expect(cols.map((c) => c.key)).toEqual([
      'label', 'crop_1', 'crop_2', 'livestock_1', 'forestry_1', 'aquatic_1', 'total',
    ])
    expect(cols.slice(1, -1).map((c) => c.group)).toEqual([
      '种植业', '种植业', '畜牧养殖业', '林业', '水产业',
    ])
  })

  it('`……` 不作列名出现（列头永远收不到数据）', () => {
    for (const p of [listedPayload(), soePayload()]) {
      for (const cols of Object.values(p.columns ?? {})) {
        expect(cols.map((c) => c.label)).not.toContain('……')
      }
    }
  })

  it('国企 5 列单级且显式 flat', () => {
    const tpl = tablesOf(loadSection('soe'))
    for (const name of [H7_SOE_SUBTABLE.cost, H7_SOE_SUBTABLE.fair]) {
      const cols = H7_SOE_COLUMNS[name]
      expect(cols.map((c) => c.key)).toEqual(
        (tpl[name].columns as any[]).map((c) => c.key),
      )
      expect(cols.map((c) => c.label)).toEqual(tpl[name].headers)
      expect(cols.some((c) => c.flat === true), `${name} 未表态 flat`).toBe(true)
      expect(cols.some((c) => c.group), `${name} 单级表头不得声明 group`).toBe(false)
      expect(cols.slice(1).every((c) => c.format === 'amount')).toBe(true)
    }
  })
})

describe('P1/P5 行集与模板一致 + 行键 ⊆ 列键', () => {
  it('上市两表载荷行集逐行等于模板（34 / 11 行）', () => {
    const tpl = tablesOf(loadSection('listed'))
    const p = listedPayload()
    for (const [name, defs] of [
      [H7_LISTED_SUBTABLE.cost, H7_COST_MOVEMENT_ROWS],
      [H7_LISTED_SUBTABLE.fair, H7_FAIR_MOVEMENT_ROWS],
    ] as const) {
      const rows = p.sub_table_data[name] as Record<string, unknown>[]
      expect(rows).toHaveLength(defs.length)
      expect(rows.map((r) => norm(r.label))).toEqual(
        (tpl[name].rows as any[]).map((r) => norm(r.label)),
      )
    }
    expect(p.sub_table_data[H7_LISTED_SUBTABLE.cost]).toHaveLength(34)
    expect(p.sub_table_data[H7_LISTED_SUBTABLE.fair]).toHaveLength(11)
  })

  it('国企默认载荷 = 4 产业 + 合计（5 行），有类别时插在所属产业之后', () => {
    expect(soePayload().sub_table_data[H7_SOE_SUBTABLE.cost]).toHaveLength(5)
    const blocks = createDefaultSoeBlocks()
    blocks[1].categories = [
      { id: 'livestock-1', name: '奶牛', begin: 200, increase: 20, decrease: 2 },
    ]
    const rows = soePayload({ cost: blocks }).sub_table_data[H7_SOE_SUBTABLE.cost] as any[]
    expect(rows.map((r) => r.label)).toEqual([
      '一、种植业', '二、畜牧养殖业', '奶牛', '三、林业', '四、水产业', '合计',
    ])
    expect(rows[2].end).toBe(218)
    expect(rows[5].is_total).toBe(true)
    expect(rows[5].begin).toBe(200)
  })

  it('行键 ⊆ columns.key ∪ 结构标记（无位置化 values）', () => {
    const extras = new Set(['is_total', 'is_section', 'row_kind'])
    for (const p of [listedPayload(), soePayload()]) {
      for (const [table, rows] of Object.entries(p.sub_table_data)) {
        if (table.startsWith('_')) continue
        const allowed = new Set([...(p.columns?.[table] ?? []).map((c) => c.key), ...extras])
        for (const row of rows as Record<string, unknown>[]) {
          expect(row).not.toHaveProperty('values')
          for (const k of Object.keys(row)) {
            expect(allowed.has(k), `${table} 未知行键 ${k}`).toBe(true)
          }
        }
      }
    }
  })

  it('上市派生行在载荷里已算好（合计列 = 各类别列之和）', () => {
    let cost = emptyMovement()
    cost = setCell(cost, 'cost_begin', 'crop_1', 1000)
    cost = setCell(cost, 'cost_begin', 'livestock_1', 500)
    cost = setCell(cost, 'cost_inc_purchase', 'crop_1', 200)
    cost = setCell(cost, 'cost_dec_dispose', 'crop_1', 100)
    const rows = listedPayload({ cost }).sub_table_data[H7_LISTED_SUBTABLE.cost] as any[]
    const pick = (label: string) => rows.find((r) => norm(r.label) === label)!
    expect(pick('1.期初余额').total).toBe(1500)
    expect(pick('4.期末余额').crop_1).toBe(1100)
    expect(pick('4.期末余额').total).toBe(1600)
    expect(pick('一、账面原值').is_section).toBe(true)
  })
})

describe('P7 旧表名进 _removed_table_keys', () => {
  it('模板不再含 `项  目`，旧名登记在 legacy 清单且随载荷发出', () => {
    for (const variant of ['listed', 'soe'] as const) {
      expect(Object.keys(tablesOf(loadSection(variant)))).not.toContain('项  目')
    }
    expect([...H7_LEGACY_OBSOLETE_TABLES]).toEqual(['项  目'])
    expect(listedPayload().sub_table_data._removed_table_keys as unknown).toEqual(['项  目'])
  })
})

describe('P8 `_note_texts` 中文标题与空过滤', () => {
  it('全空时不产生 `_note_texts` 键（两版）', () => {
    expect(listedPayload().sub_table_data).not.toHaveProperty('_note_texts')
    expect(soePayload().sub_table_data).not.toHaveProperty('_note_texts')
    expect(listedPayload({ notePolicy: '  ', noteSupplement: '\n' }).sub_table_data)
      .not.toHaveProperty('_note_texts')
  })

  it('在 sub_table_data 内、不在顶层，且带中文 title', () => {
    const p = listedPayload({
      notePolicy: '采用成本模式计量，按直线法计提折旧。',
      noteSupplement: '期末实物数量 1,200 株。',
    })
    expect(p).not.toHaveProperty('_note_texts')
    const texts = p.sub_table_data._note_texts as unknown as Array<Record<string, string>>
    expect(texts.map((t) => t.section)).toEqual(['listed-policy', 'listed-supplement'])
    for (const t of texts) {
      expect(t.title.trim()).not.toBe('')
      expect(/^[a-z0-9-]+$/.test(t.title), `title 仍是英文键：${t.title}`).toBe(false)
      expect(/[\u4e00-\u9fa5]/.test(t.title)).toBe(true)
    }
    const soe = soePayload({ noteFairBasis: '采用市场法确定公允价值。' })
    const st = soe.sub_table_data._note_texts as unknown as Array<Record<string, string>>
    expect(st[0].section).toBe('soe-fair-basis')
    expect(st[0].title).toBe(H7_NOTE_TEXT_TITLES['soe-fair-basis'])
  })

  it('标题映射覆盖两版全部文本域，构造器空白过滤 + trim + 未登记回退', () => {
    expect(Object.keys(H7_NOTE_TEXT_TITLES).sort()).toEqual([
      'listed-impairment', 'listed-policy', 'listed-supplement',
      'soe-fair-basis', 'soe-policy', 'soe-supplement',
    ].sort())
    expect(buildH7NoteTexts([{ section: 'a', text: '  ' }, { section: 'b', text: null }]))
      .toEqual([])
    expect(buildH7NoteTexts([{ section: 'soe-policy', text: ' x ' }])).toEqual([
      { section: 'soe-policy', title: H7_NOTE_TEXT_TITLES['soe-policy'], text: 'x' },
    ])
    expect(buildH7NoteTexts([{ section: 'zzz', text: 'y' }])[0].title).toBe('zzz')
  })
})

describe('P9 组件：无自调度 / 金额控件合规 / 已接同步链路', () => {
  const COMPONENTS = {
    'H7 上市': 'h7/core/H7TabDisclosureListed.vue',
    'H7 国企': 'h7/core/H7TabDisclosureSoe.vue',
  } as const
  const TABLES = {
    'H7 上市明细表': 'h7/core/H7ListedMovementTable.vue',
    'H7 国企明细表': 'h7/core/H7SoeIndustryTable.vue',
  } as const

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
    const fake = 'async function syncToNotes(): Promise<void> { a(); scheduleAutoSync(x); }\nfunction z(){}'
    expect(functionBody(fake, 'async function syncToNotes')).toContain('scheduleAutoSync')
    expect(functionBody(fake, 'async function nope')).toBe('')
  })

  for (const [name, rel] of Object.entries(COMPONENTS)) {
    const raw = readFileSync(resolve(WP, rel), 'utf-8')
    const src = stripComments(raw)

    it(`${name}：反向自检 —— 原始源码含 scheduleAutoSync`, () => {
      expect(raw).toContain('scheduleAutoSync')
    })

    it(`${name}：syncToNotes 函数体内不得调 scheduleAutoSync（自调度）`, () => {
      const body = functionBody(src, 'async function syncToNotes')
      expect(body, '未定位到 syncToNotes 函数体').not.toBe('')
      expect(body).not.toContain('scheduleAutoSync')
    })

    it(`${name}：已建立同步链路（POST sync-from-workpaper + 自动同步 + projectId 门控）`, () => {
      expect(src).toContain('disclosure-notes/sync-from-workpaper')
      expect(src).toContain('useDisclosureAutoSync')
      expect(src).toContain('!props.projectId')
      // 不得使用一次性挂载防护（会吞掉切走再切回后的第一次编辑）
      expect(/_[A-Za-z0-9]*[Mm]ounted\s*=/.test(src)).toBe(false)
    })

    it(`${name}：inject 在 setup 顶层（写进函数体会点击时抛错被吞）`, () => {
      const injectAt = src.indexOf("inject<((p: Record<string, unknown>) => void) | null>")
      expect(injectAt, '未找到 openReviewDialog 的 inject').toBeGreaterThan(0)
      // inject 之前不得出现 `function ` 之外的包裹（简化判定：不在任何函数体内）
      const before = src.slice(0, injectAt)
      const opens = (before.match(/\basync function |\bfunction /g) || []).length
      const closes = (before.match(/^}/gm) || []).length
      expect(opens, 'inject 被写进了函数体内').toBeLessThanOrEqual(closes)
    })

    it(`${name}：文本域接 AI 且带 loading/只读门控`, () => {
      expect(src).toContain('useDisclosureNoteAi')
      expect(src).toContain('aiLoadingSection === k')
      expect(src).toContain(':disabled="isReadonly"')
    })

    it(`${name}：无自造金额格式化（禁 toLocaleString）`, () => {
      expect(src).not.toContain('toLocaleString')
    })

    it(`${name}：🔴 自持久化（H7 宿主无统一 @save 处理器，只 emit 会让录入刷新即丢）`, () => {
      // 实测踩中：自动同步写进了附注，但 checklist_responses 一条都没有
      expect(src).toContain('checklist-responses')
      expect(src).toContain('api.put(')
      expect(src).toContain("emit('save'")
      // 保存失败必须给用户提示（纯 catch {} 会让数据丢了没人发现）
      expect(/catch\s*\{\s*ElMessage\.error/.test(src)).toBe(true)
    })

    it(`${name}：🔴 不 watch props.allResponses（宿主旧值会覆盖刚录入的数据）`, () => {
      expect(src).toContain('localResponses')
      expect(/watch\(\s*responses/.test(src)).toBe(false)
      expect(/toRef\(props,\s*'allResponses'\)/.test(src)).toBe(false)
    })
  }

  it('🔴 宿主必须传 :applicable-standards（否则变体门控恒开）+ 接 @save', () => {
    const host = stripComments(readFileSync(resolve(WP, 'GtH7BiologicalAssets.vue'), 'utf-8'))
    for (const tag of ['H7TabDisclosureListed', 'H7TabDisclosureSoe']) {
      const at = host.indexOf(`<${tag}`)
      expect(at, `宿主未使用 ${tag}`).toBeGreaterThan(0)
      const block = host.slice(at, host.indexOf('/>', at))
      expect(block, `${tag} 缺 :applicable-standards`).toContain(':applicable-standards')
      expect(block, `${tag} 缺 :project-id`).toContain(':project-id')
      expect(block, `${tag} 缺 @save`).toContain('@save')
    }
    // useHostApplicableStandards 必须在 setup 顶层（inject 依赖）
    expect(host).toContain('useHostApplicableStandards')
  })

  it('🔴 明细表用 store 成员取 fmtAmount（不是模块命名导出）', () => {
    // `import { fmtAmount } from '@/stores/displayPrefs'` 会在**运行时**抛
    // `does not provide an export named 'fmtAmount'` —— Vite 200 / vitest /
    // get_diagnostics 全绿，只有浏览器挂载才暴露（本 spec 实测踩中）
    for (const rel of Object.values(TABLES)) {
      const src = stripComments(readFileSync(resolve(WP, rel), 'utf-8'))
      expect(src).toContain('useDisplayPrefsStore')
      expect(/import\s*\{[^}]*\bfmtAmount\b[^}]*\}\s*from\s*'@\/stores\/displayPrefs'/.test(src))
        .toBe(false)
    }
  })

  for (const [name, rel] of Object.entries(TABLES)) {
    const src = stripComments(readFileSync(resolve(WP, rel), 'utf-8'))

    it(`${name}：金额录入用 WpAmountInput、只读金额走 fmtAmount`, () => {
      expect(src).toContain('WpAmountInput')
      expect(src).toContain('fmtAmount')
      expect(src).not.toContain('el-input-number')
      expect(src).not.toContain('toLocaleString')
    })
  }
})
