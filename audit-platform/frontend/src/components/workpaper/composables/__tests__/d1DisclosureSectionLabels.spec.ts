/**
 * D1 披露页小节标题 ↔ 源模板披露 sheet 小节标题 守卫。
 *
 * 背景（2026-07-31 Wave 6.1 复核发现）：`D1TabDisclosure.sectionLabels` 的 7 条标题
 * 有 5 条与源模板漂移，且**上市主表被标成「（1）」与质押表撞号**（同一页两个「（1）」）。
 * 这类文案漂移 `get_diagnostics` / vitest / vue-tsc 全查不出，只有肉眼逐段看才发现。
 *
 * 裁决者 = 源模板 `backend/wp_templates/D/D1 应收票据.xlsx` 的两个披露 sheet
 * 小节标题行（上市 R6/R14/R20/R31/R37/R92/R107；国企 R5/R11/R45/R60/R66/R74/R80）。
 * 前端测试读不了 xlsx，故把源模板字面固化在此（后端 `test_note_d1_structure.py`
 * 的 `test_table_name_matches_source_sheet_title` 直读 xlsx 交叉锁死表名侧）。
 *
 * spec: .kiro/specs/d1-extraction-chain-completion/ Task 6.1
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const TAB = resolve(__dirname, '../../d1/D1TabDisclosure.vue')

/** 源模板小节标题（逐字）。key = 披露页区块键。 */
const EXPECTED = {
  listed: {
    categorySummary: '应收票据', // R6：主表无小节编号，编号自「（1）期末已质押」起
    pledged: '（1）期末已质押的应收票据',
    endorsed: '（2）期末已背书或贴现但尚未到期的应收票据',
    transfer: '（3）期末因出票人未履约而其转应收账款的票据',
    badDebtClass: '（4）按坏账计提方法分类',
    badDebtMovement: '（5）本期计提、收回或转回的坏账准备情况',
    writeOff: '（6）本期实际核销的应收票据情况',
  },
  soe: {
    categorySummary: '（1）应收票据分类',
    badDebtClass: '（2）坏账准备计提情况',
    badDebtMovement: '（3）本期计提、收回或转回的应收票据坏账准备情况',
    pledged: '（4）期末已质押的应收票据',
    endorsed: '（5）期末已背书或贴现但尚未到期的应收票据',
    transfer: '（6）期末因出票人未履约而其转为应收账款的票据',
    writeOff: '（7）本期实际核销的应收票据',
  },
} as const

/** 从 SFC 源码抽 `sectionLabels` 的两个分支字面量。 */
function readLabels(): { listed: Record<string, string>; soe: Record<string, string> } {
  const src = readFileSync(TAB, 'utf-8')
  const block = src.match(/const sectionLabels = computed[\s\S]*?\n\}\)/)
  if (!block) throw new Error('未找到 sectionLabels（正则失效）')
  const body = block[0]
  const soeStart = body.indexOf("variant === 'soe'")
  if (soeStart < 0) throw new Error('未找到 soe 分支（正则失效）')
  // 两个 return { ... } 对象：第 1 个是 soe，第 2 个是 listed
  const objects = [...body.matchAll(/return \{([\s\S]*?)\n  \}/g)].map(m => m[1])
  if (objects.length !== 2) throw new Error(`sectionLabels 分支数异常：${objects.length}`)
  const parse = (chunk: string): Record<string, string> => {
    const out: Record<string, string> = {}
    for (const m of chunk.matchAll(/^\s*(\w+):\s*'([^']*)'/gm)) out[m[1]] = m[2]
    return out
  }
  return { soe: parse(objects[0]), listed: parse(objects[1]) }
}

describe('D1 披露页小节标题 ↔ 源模板', () => {
  const labels = readLabels()

  it('抽取非空（反向自检：正则失效时上面断言会全绿）', () => {
    expect(Object.keys(labels.listed).length).toBe(7)
    expect(Object.keys(labels.soe).length).toBe(7)
  })

  for (const variant of ['listed', 'soe'] as const) {
    it(`${variant} 七条标题逐字等于源模板小节标题`, () => {
      expect(labels[variant]).toEqual({ ...EXPECTED[variant] })
    })

    it(`${variant} 小节编号不重复（上市主表无编号，不得与质押表撞「（1）」）`, () => {
      const nums = Object.values(labels[variant])
        .map(v => v.match(/^（(\d+)）/)?.[1])
        .filter((v): v is string => Boolean(v))
      expect(nums.length).toBe(new Set(nums).size)
    })
  }

  it('两版措辞本就不同 → 不得被「统一」成同一串', () => {
    expect(labels.listed.transfer).not.toBe(labels.soe.transfer)
    expect(labels.listed.badDebtClass).not.toBe(labels.soe.badDebtClass)
  })

  it('旧漂移文案不复活', () => {
    const all = [...Object.values(labels.listed), ...Object.values(labels.soe)].join('|')
    for (const legacy of ['而将其转应收账款', '且未到期', '且在资产负债表日尚未到期']) {
      expect(all).not.toContain(legacy)
    }
  })
})
