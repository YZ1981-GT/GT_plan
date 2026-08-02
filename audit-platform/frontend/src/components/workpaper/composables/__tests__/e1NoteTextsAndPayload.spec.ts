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
  E1_NOTE_TEXTS_LISTED,
  E1_NOTE_TEXTS_SOE,
  e1LegacyNoteKey,
  e1NoteTextKey,
  e1NoteTexts,
} from '../e1DisclosureScope'
import {
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
