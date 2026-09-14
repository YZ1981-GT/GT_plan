/**
 * D1 披露说明文本域键集契约
 *
 * 🔴 「声明了 N 个子节但只有 N−1 个文本域」是平台反复出现的缺陷
 * （D2 缺 `portfolio`、J1 缺两个 Tab 的复核、D1 缺 `transfer`/`badDebtMovement`）：
 * 该段说明**无处录入、AI 无处落笔、附注 `text_content` 永远缺这一节**，
 * 而且不报错、测试不红、只有逐段点开界面才能发现。
 *
 * 本守卫从源码抽三处键集并交叉校验：
 *  - `useD1Disclosure.sectionOrder`（子节顺序，两个变体）
 *  - `D1TabDisclosure.NOTE_SECTION_KEYS`（文本域）
 *  - `d1NoteSectionMap.D1_NOTE_TEXT_ORDER` + `NOTE_TITLES`（同步到附注的小节）
 *
 * spec: .kiro/specs/d1-notes-receivable-disclosure-alignment/
 */
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { D1_NOTE_TEXT_ORDER, buildNoteTexts } from '../d1NoteSectionMap'

const WORKPAPER_ROOT = path.resolve(__dirname, '../..')
const TAB = path.join(WORKPAPER_ROOT, 'd1', 'D1TabDisclosure.vue')
const COMPOSABLE = path.join(WORKPAPER_ROOT, 'composables', 'useD1Disclosure.ts')
const SECTION_MAP = path.join(WORKPAPER_ROOT, 'composables', 'd1NoteSectionMap.ts')

function read(p: string): string {
  return fs.readFileSync(p, 'utf-8')
}

/** 从 `NOTE_SECTION_KEYS = [...] as const` 抽键 */
function noteSectionKeys(): string[] {
  const m = read(TAB).match(/NOTE_SECTION_KEYS\s*=\s*\[([\s\S]*?)\]\s*as const/)
  if (!m) throw new Error('未找到 NOTE_SECTION_KEYS（正则失效）')
  return [...m[1].matchAll(/'([^']+)'/g)].map(x => x[1])
}

/** 从 `sectionOrder = computed(...)` 抽两个变体的子节顺序 */
function sectionOrders(): { listed: string[]; soe: string[] } {
  const m = read(COMPOSABLE).match(/sectionOrder = computed<string\[\]>\(\(\) =>([\s\S]*?)\n\s*\)/)
  if (!m) throw new Error('未找到 sectionOrder（正则失效）')
  const arrays = [...m[1].matchAll(/\[([^\]]+)\]/g)].map(a =>
    [...a[1].matchAll(/'([^']+)'/g)].map(x => x[1]),
  )
  if (arrays.length !== 2) throw new Error(`期望 2 个变体数组，实际 ${arrays.length}`)
  return { listed: arrays[0], soe: arrays[1] }
}

/** 从 `NOTE_TITLES` 抽键 */
function noteTitleKeys(): string[] {
  const m = read(SECTION_MAP).match(/const NOTE_TITLES[^=]*=\s*\{([\s\S]*?)\n\}/)
  if (!m) throw new Error('未找到 NOTE_TITLES（正则失效）')
  return [...m[1].matchAll(/^\s*(\w+):/gm)].map(x => x[1])
}

describe('D1 披露说明文本域键集', () => {
  const keys = noteSectionKeys()
  const orders = sectionOrders()
  const titles = noteTitleKeys()

  it('抽到了三处键集（防正则失效导致守卫空转）', () => {
    expect(keys.length).toBeGreaterThan(0)
    expect(orders.listed.length).toBeGreaterThan(0)
    expect(orders.soe.length).toBeGreaterThan(0)
    expect(titles.length).toBeGreaterThan(0)
  })

  it.each([['listed'], ['soe']] as const)(
    '%s 的每个子节都有说明文本域（categorySummary 与顶部汇总表共用 top）',
    (variant) => {
      const order = orders[variant]
      const missing = order.filter(
        s => s !== 'categorySummary' && !keys.includes(s),
      )
      expect(
        missing,
        `${variant} 子节 ${missing.join('/')} 无说明文本域 → 该段说明无处录入、`
          + 'AI 无处落笔、附注 text_content 永远缺这一节',
      ).toEqual([])
    },
  )

  it('文本域键集 == 附注小节顺序（缺键会让同步静默丢段）', () => {
    expect([...keys].sort()).toEqual([...D1_NOTE_TEXT_ORDER].sort())
  })

  it('每个键都有对应标题（无标题的段落在附注里显示为键名）', () => {
    const missing = keys.filter(k => !titles.includes(k))
    expect(missing).toEqual([])
  })

  it('标题表无多余键（残留键说明子节已删但标题未清）', () => {
    const stale = titles.filter(k => !keys.includes(k))
    expect(stale).toEqual([])
  })

  it('两个新补子节确实在键集内（回归锁）', () => {
    expect(keys).toContain('transfer')
    expect(keys).toContain('badDebtMovement')
  })

  it('buildNoteTexts 按顺序输出非空段落，并带中文标题', () => {
    const out = buildNoteTexts({
      badDebtMovement: '变动说明',
      top: '总体说明',
      transfer: '转应收账款说明',
      pledged: '',
    })
    expect(out.map(x => x.section)).toEqual(['note-top', 'note-transfer', 'note-badDebtMovement'])
    expect(out.map(x => x.title)).toEqual([
      '应收票据说明', '因出票人未履约转应收账款说明', '坏账准备变动说明',
    ])
    // 空段落不输出（附注里不留空小节）
    expect(out.some(x => x.section === 'note-pledged')).toBe(false)
  })

  it('每个键在 Tab 模板里都有 onNoteChange 绑定与 AI 按钮', () => {
    const tab = read(TAB)
    const missingInput: string[] = []
    const missingAi: string[] = []
    for (const k of keys) {
      if (!tab.includes(`onNoteChange('${k}'`)) missingInput.push(k)
      if (!tab.includes(`handleAiGenerate('${k}')`)) missingAi.push(k)
    }
    expect(missingInput, '缺 onNoteChange 绑定 → 文本域改了不落库').toEqual([])
    expect(missingAi, '缺 AI 按钮 → 该段没有 AI 辅助（平台铁律要求每个文本区都有）').toEqual([])
  })
})
