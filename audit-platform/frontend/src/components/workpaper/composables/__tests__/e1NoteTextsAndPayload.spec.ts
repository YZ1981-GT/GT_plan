/**
 * e1NoteTextsAndPayload.spec.ts — E1 披露说明分段 + 同步载荷守卫
 *
 * **Validates: Requirements 4.1, 4.2, 6.2, 6.3, 8.4, 8.5, 8.6**
 *
 * Property 13（同步幂等 + 合计行）
 *
 * spec: e1-four-table-extraction-and-disclosure-alignment (Task 8/9)
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

import {
  E1_MAIN_ROWS_LISTED,
  E1_MAIN_ROWS_SOE,
  E1_NOTE_TEXTS_LISTED,
  E1_NOTE_TEXTS_SOE,
  e1LegacyNoteKey,
  e1MainRows,
  e1NoteTextKey,
  e1NoteTexts,
  e1SummableRows,
} from '../e1DisclosureScope'
import {
  E1_MAIN_TABLE,
  E1_NOTE_SECTION,
  E1_NOTE_TOTAL_LABEL,
  E1_RESTRICTED_TABLE,
  buildE1SyncPayload,
  buildNoteTexts,
  type E1DisclosureSnapshot,
} from '../e1NoteSectionMap'

const DISCLOSURE = resolve(__dirname, '../../e1/E1TabDisclosure.vue')

function blankComments(src: string): string {
  const blank = (m: string) => m.replace(/[^\n]/g, ' ')
  return src
    .replace(/\/\*[\s\S]*?\*\//g, blank)
    .replace(/<!--[\s\S]*?-->/g, blank)
    .replace(/(^|[^:])(\/\/[^\n]*)/gm, (_m, pre: string, cmt: string) => pre + blank(cmt))
}

// ─── 文本分段真源 ─────────────────────────────────────────────────────────────

describe('披露说明分段真源', () => {
  it('两变体各 2 段，且都有「受限及境外款项说明」', () => {
    expect(E1_NOTE_TEXTS_LISTED).toHaveLength(2)
    expect(E1_NOTE_TEXTS_SOE).toHaveLength(2)
    expect(E1_NOTE_TEXTS_LISTED[0].key).toBe('restricted')
    expect(E1_NOTE_TEXTS_SOE[0].key).toBe('restricted')
  })

  it('两变体第二段按源模板不同（上市存款利息 / 国企数字货币）', () => {
    expect(E1_NOTE_TEXTS_LISTED[1].key).toBe('interest')
    expect(E1_NOTE_TEXTS_SOE[1].key).toBe('digital')
  })

  it('每段都有中文 title（附注正文缺 title 会渲染成英文键）', () => {
    for (const def of [...E1_NOTE_TEXTS_LISTED, ...E1_NOTE_TEXTS_SOE]) {
      expect(def.title).toBeTruthy()
      expect(/[\u4e00-\u9fa5]/.test(def.title)).toBe(true)
    }
  })

  it('每段都有源 xlsx 单元格引用与指引原文', () => {
    for (const def of [...E1_NOTE_TEXTS_LISTED, ...E1_NOTE_TEXTS_SOE]) {
      expect(def.sourceRef).toMatch(/^A\d+$/)
      expect(def.guidance).toContain('源模板')
    }
  })

  it('AI prompt ≥20 字且含「不得虚构」约束（防诱导自造披露内容）', () => {
    for (const def of [...E1_NOTE_TEXTS_LISTED, ...E1_NOTE_TEXTS_SOE]) {
      expect(def.aiPrompt.length).toBeGreaterThanOrEqual(20)
      expect(def.aiPrompt, `${def.key} 的 prompt 缺「不得虚构」`).toContain('不得虚构')
    }
  })

  it('持久化键按变体与段分开，且与旧键不冲突', () => {
    expect(e1NoteTextKey('soe', 'restricted')).toBe('E1-disclosure-soe-note-restricted')
    expect(e1LegacyNoteKey('soe')).toBe('E1-disclosure-soe-note')
    expect(e1NoteTextKey('soe', 'restricted')).not.toBe(e1LegacyNoteKey('soe'))
  })

  it('段 key 在同变体内唯一', () => {
    for (const v of ['listed', 'soe'] as const) {
      const keys = e1NoteTexts(v).map((d) => d.key)
      expect(new Set(keys).size).toBe(keys.length)
    }
  })
})

// ─── _note_texts 构建 ─────────────────────────────────────────────────────────

describe('_note_texts 构建', () => {
  it('多段：仅非空段进载荷，且带中文 title', () => {
    const out = buildNoteTexts('soe', {
      noteSections: [
        { key: 'restricted', title: '受限及境外款项说明', text: '不存在受限款项。' },
        { key: 'digital', title: '数字货币说明', text: '   ' },
      ],
    })
    expect(out).toHaveLength(1)
    expect(out[0]).toEqual({
      section: 'soe-note-restricted',
      title: '受限及境外款项说明',
      text: '不存在受限款项。',
    })
  })

  it('全空段 → 不产生 _note_texts 条目', () => {
    expect(buildNoteTexts('listed', { noteSections: [{ key: 'a', title: 'T', text: '' }] })).toEqual([])
  })

  it('兼容旧签名（单一说明框）', () => {
    const out = buildNoteTexts('listed', { noteText: '旧内容' })
    expect(out).toEqual([{ section: 'listed-note', title: '货币资金说明', text: '旧内容' }])
  })

  it('title 缺失时兜底为中文（不落英文键）', () => {
    const out = buildNoteTexts('soe', { noteSections: [{ key: 'x', title: '', text: 'v' }] })
    expect(out[0].title).toBe('货币资金说明')
  })
})

// ─── ②表条件表语义 + Property 13 ──────────────────────────────────────────────

const MAIN_ROWS = [
  { key: 'cash', label: '库存现金', endingAmount: 100, openingAmount: 90 },
  { key: 'total', label: '合计', endingAmount: 100, openingAmount: 90 },
]

function snap(over: Partial<E1DisclosureSnapshot> = {}): E1DisclosureSnapshot {
  return { mainRows: MAIN_ROWS, ...over }
}

describe('② 受限表条件表语义（两变体都推）', () => {
  it.each(['listed', 'soe'] as const)('%s：有行时推该表 + 合计行', (variant) => {
    const p = buildE1SyncPayload(variant, 'wp-1', null, snap({
      restrictedRows: [
        { item: '银行承兑汇票保证金', openingAmount: 10, endingAmount: 20, reason: '开票保证金' },
      ],
    }))
    const rows = p.sub_table_data[E1_RESTRICTED_TABLE] as any[]
    expect(rows).toHaveLength(2)
    expect(rows[1].is_total).toBe(true)
    expect(rows[1].label).toBe(E1_NOTE_TOTAL_LABEL)
    expect(rows[1].end_amount).toBe(20)
    expect(rows[1].prior_amount).toBe(10)
    expect(p.columns[E1_RESTRICTED_TABLE]).toBeTruthy()
    expect(p.sub_table_data._removed_table_keys).toBeUndefined()
  })

  it.each(['listed', 'soe'] as const)('%s：管这张表但为空 → 不推空表且进 _removed_table_keys', (variant) => {
    const p = buildE1SyncPayload(variant, 'wp-1', null, snap({ restrictedRows: [] }))
    expect(p.sub_table_data[E1_RESTRICTED_TABLE]).toBeUndefined()
    expect(p.sub_table_data._removed_table_keys).toEqual([E1_RESTRICTED_TABLE])
  })

  it('🔴 `undefined` = 调用方不管这张表 → 跳过且**不**进 _removed_table_keys', () => {
    // 越权删会打断别的底稿推的同名表（K3 vs K7 铁律）
    const p = buildE1SyncPayload('listed', 'wp-1', null, snap())
    expect(p.sub_table_data[E1_RESTRICTED_TABLE]).toBeUndefined()
    expect(p.sub_table_data._removed_table_keys).toBeUndefined()
  })

  it('buildNoteTexts 兼容旧的裸字符串签名（公开 API 不破）', () => {
    expect(buildNoteTexts('listed', '旧文本')).toEqual([
      { section: 'listed-note', title: '货币资金说明', text: '旧文本' },
    ])
    expect(buildNoteTexts('listed', '')).toEqual([])
    expect(buildNoteTexts('listed', null)).toEqual([])
  })

  it('🔴 合计行字面按本章节实证取 `合计`（不套平台的 `合 计`）', () => {
    expect(E1_NOTE_TOTAL_LABEL).toBe('合计')
    expect(E1_NOTE_TOTAL_LABEL).not.toContain(' ')
  })

  it('章节号：上市 五、1 / 国企 八、1', () => {
    expect(E1_NOTE_SECTION.listed).toBe('五、1')
    expect(E1_NOTE_SECTION.soe).toBe('八、1')
  })

  it('Property 13：同一 snapshot 连续两次构建载荷逐字节相等', () => {
    const s = snap({
      restrictedRows: [{ item: 'X', openingAmount: 1, endingAmount: 2, reason: 'r' }],
      noteSections: [{ key: 'restricted', title: '受限及境外款项说明', text: 't' }],
    })
    const a = buildE1SyncPayload('soe', 'wp-1', null, s)
    const b = buildE1SyncPayload('soe', 'wp-1', null, s)
    expect(JSON.stringify(a)).toBe(JSON.stringify(b))
  })

  it('主表合计行标 is_total', () => {
    const p = buildE1SyncPayload('listed', 'wp-1', null, snap())
    const rows = p.sub_table_data['货币资金'] as any[]
    expect(rows.find((r) => r.label === '合计')?.is_total).toBe(true)
  })
})

// ─── 主表双口径投影（Task 15 / Property 16, 17, 18）─────────────────────────────

/** 从真源行集构造快照 mainRows（只带 key/label/金额，**不传 noteLabel**）。 */
function mainRowsFromScope(variant: 'listed' | 'soe') {
  return e1MainRows(variant).map((d, i) => ({
    key: d.key,
    label: d.label,
    endingAmount: i + 1,
    openingAmount: 100 + i,
  }))
}

describe('主表 label / noteLabel 双口径投影', () => {
  it('🔴 soe 载荷首行标签 == 附注 docx 字面「库存现金」，而真源 label 仍是「现金」', () => {
    const p = buildE1SyncPayload('soe', 'wp-1', ['soe_standalone'], {
      mainRows: mainRowsFromScope('soe'),
    })
    const rows = p.sub_table_data[E1_MAIN_TABLE] as Array<Record<string, unknown>>
    // 附注口径（交付件行名，必须与 note_template_soe.json 八、1 逐字一致）
    expect(rows[0].label).toBe('库存现金')
    // 底稿口径（源 xlsx A8 字面）—— 两口径**同时**成立，不是「谁改成谁」
    expect(E1_MAIN_ROWS_SOE[0].label).toBe('现金')
    expect(E1_MAIN_ROWS_SOE[0].noteLabel).toBe('库存现金')
  })

  it('投影不依赖调用方传 noteLabel（按 key 从真源反查，少传不产生孤儿行）', () => {
    // 组件只传 key/label/金额；若投影靠调用方传字段，任何漏传就是一条静默孤儿行
    const rows = buildE1SyncPayload('soe', 'wp-1', [], {
      mainRows: [{ key: 'cash', label: '现金', endingAmount: 1, openingAmount: 2 }],
    }).sub_table_data[E1_MAIN_TABLE] as Array<Record<string, unknown>>
    expect(rows[0].label).toBe('库存现金')
  })

  it('调用方显式传 noteLabel 时优先（覆盖能力保留）', () => {
    const rows = buildE1SyncPayload('soe', 'wp-1', [], {
      mainRows: [
        { key: 'cash', label: '现金', noteLabel: '库存现金（覆盖）', endingAmount: 0, openingAmount: 0 },
      ],
    }).sub_table_data[E1_MAIN_TABLE] as Array<Record<string, unknown>>
    expect(rows[0].label).toBe('库存现金（覆盖）')
  })

  it('未声明 noteLabel 的行原样落 label（listed 侧逐行不变）', () => {
    const p = buildE1SyncPayload('listed', 'wp-1', ['listed_standalone'], {
      mainRows: mainRowsFromScope('listed'),
    })
    const rows = p.sub_table_data[E1_MAIN_TABLE] as Array<Record<string, unknown>>
    expect(rows.map((r) => r.label)).toEqual(E1_MAIN_ROWS_LISTED.map((d) => d.label))
  })

  it('🔴 反向自检：把 mainRow 退回「只用 label」（旧行为替身）→ soe 首行必产出「现金」', () => {
    // 证明上面的投影断言不空转：本地纯函数复现旧实现，必须给出与附注模板不符的行名
    const legacyMainRow = (r: { key: string; label: string }) => ({ label: r.label })
    const legacyRows = mainRowsFromScope('soe').map(legacyMainRow)
    expect(legacyRows[0].label).toBe('现金')
    expect(legacyRows[0].label).not.toBe('库存现金')
  })

  it('🔴 soe 主表 6 行（附注真源是 docx；含末行「其中：存放在境外的款项总额」）', () => {
    const p = buildE1SyncPayload('soe', 'wp-1', ['soe_standalone'], {
      mainRows: mainRowsFromScope('soe'),
    })
    const rows = p.sub_table_data[E1_MAIN_TABLE] as Array<Record<string, unknown>>
    expect(rows).toHaveLength(6)
    expect(rows.map((r) => r.label)).toEqual([
      '库存现金',
      '银行存款',
      '其他货币资金',
      '数字货币',
      '合计',
      '其中：存放在境外的款项总额',
    ])
    // 备注行不得被标成合计行（投影器据 is_total 加粗）
    expect(rows[5].is_total).toBeUndefined()
    expect(rows[4].is_total).toBe(true)
  })

  it('🔴 e1SummableRows 不含 memo 行（境外款项是合计之内的再分解，不参与加总）', () => {
    for (const variant of ['listed', 'soe'] as const) {
      const summable = e1SummableRows(variant)
      expect(summable.some((r) => r.key === 'overseas')).toBe(false)
      expect(summable.some((r) => r.isMemo)).toBe(false)
      expect(summable.some((r) => r.isTotal)).toBe(false)
    }
    // soe：6 行 − 合计 − 境外 = 4 行参与加总
    expect(e1SummableRows('soe').map((r) => r.key)).toEqual([
      'cash', 'bank', 'other_mf', 'digital',
    ])
  })

  it('🔴 soe 不得补「存放财务公司款项」「存款应计利息」（准则口径差异，R5.7）', () => {
    const soeNoteLabels = e1MainRows('soe').map((d) => d.noteLabel ?? d.label)
    expect(soeNoteLabels).not.toContain('存放财务公司款项')
    expect(soeNoteLabels).not.toContain('存款应计利息')
    const listedLabels = e1MainRows('listed').map((d) => d.label)
    expect(listedLabels).toContain('存放财务公司款项')
    expect(listedLabels).toContain('存款应计利息')
  })
})

// ─── 组件接线 ─────────────────────────────────────────────────────────────────

describe('组件分段接线', () => {
  const SRC = blankComments(readFileSync(DISCLOSURE, 'utf-8'))

  it('反向自检：源码非空', () => {
    expect(SRC).toContain('noteTextDefs')
  })

  it('已改为多段渲染（v-for def in noteTextDefs）', () => {
    expect(SRC).toMatch(/v-for="def in noteTextDefs"/)
  })

  it('单一 noteText 已退役（不得残留旧 ref）', () => {
    expect(SRC).not.toMatch(/const\s+noteText\s*=\s*ref/)
  })

  it('每段都接了 AI 生成（generateNoteText）', () => {
    expect(SRC).toContain('generateNoteText(def)')
    expect(SRC).toContain('def.aiPrompt')
  })

  it('文本域用 @input 回写（@change 会被 EP 在 nextTick 重置抹掉键入）', () => {
    const m = /:placeholder="def.placeholder"[\s\S]{0,200}?@(input|change)=/.exec(SRC)
    expect(m?.[1]).toBe('input')
  })

  it('载荷传 noteSections（不再传单一 noteText）', () => {
    expect(SRC).toContain('noteSections:')
    expect(SRC).not.toMatch(/noteText:\s*noteText\.value/)
  })
})
